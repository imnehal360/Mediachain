"""Optional authenticated REST API. The SDK never imports this module."""

from __future__ import annotations

import asyncio
import ipaddress
import json
import logging
import secrets
import time
from collections.abc import AsyncIterator, Awaitable, Callable
from contextlib import asynccontextmanager
from pathlib import Path
from tempfile import TemporaryDirectory
from typing import Any

from fastapi import Depends, FastAPI, File, HTTPException, Query, Request, Response, UploadFile
from fastapi.exceptions import RequestValidationError
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse, JSONResponse
from fastapi.staticfiles import StaticFiles
from pydantic import Field
from starlette.exceptions import HTTPException as StarletteHTTPException
from starlette.middleware.trustedhost import TrustedHostMiddleware

from mediachain.agents import Agent, AgentLimits, AgentRun, media_tools
from mediachain.core.errors import BudgetExceeded, GroundingError, MediaChainError
from mediachain.core.models import (
    Document,
    ExecutionContext,
    Job,
    MediaAsset,
    Model,
    ModelResponse,
    RetrievalFilter,
    SourceReference,
)
from mediachain.loaders.local import FORMATS
from mediachain.loaders.youtube import DownloadedMedia, download_youtube
from mediachain.runtime.client import MediaChain
from mediachain.runtime.jobs import JobQueue, LocalJobQueue, asset_lease

logger = logging.getLogger("mediachain.api")


class QueryRequest(Model):
    question: str = Field(min_length=1, max_length=10000)
    media_ids: list[str] | None = None
    filters: RetrievalFilter | None = None
    include_sources: bool = True


class SummaryRequest(Model):
    media_ids: list[str] | None = None
    filters: RetrievalFilter | None = None
    focus: str | None = Field(default=None, max_length=10000)
    include_sources: bool = True


class AgentQueryRequest(Model):
    question: str = Field(min_length=1, max_length=10000)
    media_ids: list[str] | None = None
    include_sources: bool = True


class URLUploadRequest(Model):
    url: str = Field(min_length=1, max_length=2048)


YouTubeDownload = Callable[[str, Path, int, float], Awaitable[DownloadedMedia]]


def agent_sources(run: AgentRun) -> list[SourceReference]:
    observed: dict[str, SourceReference] = {}
    observed_order: list[str] = []

    def remember(reference: SourceReference) -> None:
        if reference.document_id not in observed:
            observed_order.append(reference.document_id)
        observed[reference.document_id] = reference

    for step in run.steps:
        observation = step.observation
        records = observation if isinstance(observation, list) else []
        if isinstance(observation, dict):
            for source in observation.get("sources", []):
                reference = SourceReference.model_validate(source)
                remember(reference)
        for item in records:
            if not isinstance(item, dict):
                continue
            document = item.get("document", item)
            if not isinstance(document, dict) or not {
                "id",
                "asset_id",
                "source",
                "modality",
            }.issubset(document):
                continue
            reference = Document.model_validate(document).reference()
            remember(reference)
    citation_ids = []
    for citation_id in dict.fromkeys(run.citation_ids):
        normalized = citation_id
        if citation_id not in observed and citation_id.isdigit():
            position = int(citation_id) - 1
            if 0 <= position < len(observed_order):
                normalized = observed_order[position]
        citation_ids.append(normalized)
    if any(citation_id not in observed for citation_id in citation_ids):
        raise GroundingError("Agent cited an identifier absent from tool observations")
    if not run.insufficient_evidence and not citation_ids:
        raise GroundingError("A supported agent answer must cite tool evidence")
    return [observed[citation_id] for citation_id in citation_ids]


def agent_fallback(
    response: ModelResponse,
    *,
    tool_calls: list[dict[str, Any]],
    agent_tokens: int = 0,
    limit_reached: bool = False,
) -> ModelResponse:
    return response.model_copy(
        update={
            "token_usage": agent_tokens + (response.token_usage or 0),
            "metadata": {
                **response.metadata,
                "mode": "agentic",
                "tool_calls": tool_calls,
                "grounding_fallback": True,
                "agent_limit_reached": limit_reached,
            },
        }
    )


class BodyTooLarge(HTTPException):
    def __init__(self) -> None:
        super().__init__(413, "Upload exceeds limit")


class BodyLimit:
    def __init__(self, app: Any, limit: int):
        self.app, self.limit = app, limit

    async def __call__(self, scope: Any, receive: Any, send: Any) -> None:
        if scope["type"] != "http":
            await self.app(scope, receive, send)
            return
        size = 0

        async def limited_receive() -> Any:
            nonlocal size
            message = await receive()
            size += len(message.get("body", b""))
            if size > self.limit:
                raise BodyTooLarge()
            return message

        try:
            await self.app(scope, limited_receive, send)
        except BodyTooLarge:
            await JSONResponse(
                {"error": {"code": "file_too_large", "message": "Upload exceeds limit"}},
                status_code=413,
            )(scope, receive, send)


def create_app(
    chain: MediaChain,
    *,
    api_keys: dict[str, str] | None = None,
    development_owner: str | None = None,
    development_local_only: bool = False,
    queue: JobQueue | None = None,
    max_upload_bytes: int = 100 * 1024 * 1024,
    max_remote_bytes: int = 500 * 1024 * 1024,
    max_remote_duration_seconds: float = 4 * 60 * 60,
    youtube_download: YouTubeDownload | None = download_youtube,
    redis: Any = None,
    frontend_dir: str | Path | None = None,
    readiness: Callable[[], Awaitable[bool]] | None = None,
    allowed_origins: list[str] | None = None,
    trusted_hosts: list[str] | None = None,
    rate_limit_per_minute: int = 120,
    agent_limits: AgentLimits | None = None,
) -> FastAPI:
    """Map bearer API keys to owners, with explicit local-only development access."""
    if not api_keys and development_owner is None:
        raise ValueError("Configure API keys or explicitly opt into development_owner")
    if (
        max_upload_bytes <= 0
        or max_remote_bytes <= 0
        or max_remote_duration_seconds <= 0
        or rate_limit_per_minute < 0
        or (api_keys and any(not key or not owner for key, owner in api_keys.items()))
    ):
        raise ValueError("Invalid upload limit or empty API key/owner")
    jobs = queue or LocalJobQueue(chain)

    @asynccontextmanager
    async def lifespan(app: FastAPI) -> AsyncIterator[None]:
        yield
        await jobs.close()

    app = FastAPI(title="MediaChain", version="0.1.0", lifespan=lifespan)
    app.add_middleware(BodyLimit, limit=max_upload_bytes + 65536)
    if trusted_hosts:
        app.add_middleware(TrustedHostMiddleware, allowed_hosts=trusted_hosts)
    if allowed_origins:
        app.add_middleware(
            CORSMiddleware,
            allow_origins=allowed_origins,
            allow_credentials=False,
            allow_methods=["GET", "POST", "DELETE", "OPTIONS"],
            allow_headers=["Authorization", "Content-Type", "X-Request-ID"],
        )

    local_rate_limits: dict[tuple[str, int], int] = {}

    @app.middleware("http")
    async def request_context(request: Request, call_next: Any) -> Response:
        request_id = secrets.token_hex(12)
        started = time.perf_counter()
        response = await call_next(request)
        response.headers["X-Request-ID"] = request_id
        response.headers["X-Content-Type-Options"] = "nosniff"
        response.headers["X-Frame-Options"] = "DENY"
        response.headers["Referrer-Policy"] = "no-referrer"
        response.headers["Permissions-Policy"] = "camera=(), microphone=(), geolocation=()"
        logger.info(
            json.dumps(
                {
                    "event": "http_request",
                    "request_id": request_id,
                    "method": request.method,
                    "path": request.url.path,
                    "status": response.status_code,
                    "duration_ms": round((time.perf_counter() - started) * 1000, 2),
                },
                separators=(",", ":"),
            )
        )
        return response

    @app.get("/health")
    async def health() -> dict[str, str]:
        """Process liveness check. It intentionally exposes no configuration."""
        return {"status": "ok"}

    @app.get("/ready")
    async def ready() -> JSONResponse:
        available = await readiness() if readiness else True
        return JSONResponse(
            {"status": "ready" if available else "unavailable"},
            status_code=200 if available else 503,
        )

    async def owner(request: Request) -> str:
        authorization = request.headers.get("authorization", "")
        token = authorization[7:] if authorization.startswith("Bearer ") else ""
        for key, value in (api_keys or {}).items():
            if secrets.compare_digest(token, key):
                if rate_limit_per_minute:
                    window = int(time.time() // 60)
                    if redis is not None:
                        rate_key = f"mediachain:rate:{value}:{window}"
                        count = int(await redis.incr(rate_key))
                        if count == 1:
                            await redis.expire(rate_key, 61)
                    else:
                        # Development fallback; production uses the shared Redis counter.
                        for item in list(local_rate_limits):
                            if item[1] < window:
                                local_rate_limits.pop(item, None)
                        identity = (value, window)
                        count = local_rate_limits.get(identity, 0) + 1
                        local_rate_limits[identity] = count
                    if count > rate_limit_per_minute:
                        raise HTTPException(
                            429, "Rate limit exceeded", headers={"Retry-After": "60"}
                        )
                return value
        if development_owner is not None and not api_keys:
            if development_local_only:
                client_host = request.client.host if request.client else ""
                try:
                    is_loopback = ipaddress.ip_address(client_host).is_loopback
                except ValueError:
                    is_loopback = client_host.lower() == "localhost"
                if not is_loopback:
                    raise HTTPException(403, "Local access only")
            return development_owner
        raise HTTPException(401, "Valid bearer credentials required")

    async def owned(media_id: str, owner_id: str) -> MediaAsset:
        asset = await chain.metadata.get_asset(media_id)
        if asset is None or asset.owner_id != owner_id:
            raise HTTPException(404, "Media not found")
        return asset

    @app.get("/api/v1/config")
    async def configuration(owner_id: str = Depends(owner)) -> dict[str, Any]:
        return {
            "owner": owner_id,
            "authentication_required": bool(api_keys),
            "max_upload_bytes": max_upload_bytes,
            "max_remote_bytes": max_remote_bytes,
            "max_remote_duration_seconds": max_remote_duration_seconds,
            "youtube_url_enabled": youtube_download is not None,
            "formats": [
                suffix for suffix, modality in FORMATS.items() if modality in chain.processors
            ],
            "answer_mode": "generative" if chain.rag.llm else "extractive",
            "agent_available": chain.rag.llm is not None,
        }

    @app.get("/api/v1/media", response_model=list[MediaAsset])
    async def list_media(
        response: Response,
        owner_id: str = Depends(owner),
        offset: int = Query(default=0, ge=0),
        limit: int = Query(default=100, ge=1, le=500),
    ) -> list[MediaAsset]:
        response.headers["X-Total-Count"] = str(await chain.metadata.count_assets(owner_id))
        return await chain.metadata.list_assets(owner_id, limit, offset)

    @app.get("/api/v1/jobs", response_model=list[Job])
    async def list_jobs(
        response: Response,
        owner_id: str = Depends(owner),
        offset: int = Query(default=0, ge=0),
        limit: int = Query(default=100, ge=1, le=500),
    ) -> list[Job]:
        response.headers["X-Total-Count"] = str(await chain.metadata.count_jobs(owner_id))
        return await chain.metadata.list_jobs(owner_id, limit, offset)

    @app.get("/api/v1/media/{media_id}/documents", response_model=list[Document])
    async def documents(
        media_id: str,
        response: Response,
        owner_id: str = Depends(owner),
        offset: int = Query(default=0, ge=0),
        limit: int = Query(default=100, ge=1, le=500),
    ) -> list[Document]:
        await owned(media_id, owner_id)
        items = await chain.documents.list_documents(RetrievalFilter(media_ids=[media_id]))
        response.headers["X-Total-Count"] = str(len(items))
        return items[offset : offset + limit]

    @app.get("/api/v1/media/{media_id}/content")
    async def content(media_id: str, owner_id: str = Depends(owner)) -> FileResponse:
        asset = await owned(media_id, owner_id)
        key = asset.metadata.get("object_key")
        if not key:
            raise HTTPException(404, "Original file unavailable")
        path = await chain.objects.resolve(key)
        if not path.is_file():
            raise HTTPException(404, "Original file unavailable")
        return FileResponse(
            path,
            filename=asset.metadata.get("original_name", path.name),
            headers={"X-Content-Type-Options": "nosniff", "Cache-Control": "no-store"},
        )

    @app.exception_handler(StarletteHTTPException)
    async def http_error(request: Request, exc: StarletteHTTPException) -> JSONResponse:
        return JSONResponse(
            {"error": {"code": str(exc.status_code), "message": str(exc.detail)}},
            status_code=exc.status_code,
            headers=exc.headers,
        )

    @app.exception_handler(MediaChainError)
    async def domain_error(request: Request, exc: MediaChainError) -> JSONResponse:
        return JSONResponse({"error": {"code": exc.code, "message": str(exc)}}, status_code=422)

    @app.exception_handler(RequestValidationError)
    async def validation_error(request: Request, exc: RequestValidationError) -> JSONResponse:
        return JSONResponse(
            {
                "error": {
                    "code": "validation_error",
                    "message": "Invalid request",
                    "fields": [list(e["loc"]) for e in exc.errors()],
                }
            },
            status_code=422,
        )

    @app.exception_handler(KeyError)
    async def missing(request: Request, exc: KeyError) -> JSONResponse:
        return JSONResponse(
            {"error": {"code": "not_found", "message": "Media not found"}}, status_code=404
        )

    @app.exception_handler(Exception)
    async def unexpected(request: Request, exc: Exception) -> JSONResponse:
        return JSONResponse(
            {"error": {"code": "internal_error", "message": "Request failed"}}, status_code=500
        )

    @app.post("/api/v1/media", response_model=MediaAsset, status_code=201)
    async def upload(file: UploadFile = File(...), owner_id: str = Depends(owner)) -> MediaAsset:
        suffix = Path(file.filename or "").suffix.lower()
        if suffix not in FORMATS:
            raise HTTPException(415, "Unsupported media type")
        with TemporaryDirectory(prefix="mediachain-upload-") as temp:
            path = Path(temp) / ("upload" + suffix)
            total = 0
            stream = await asyncio.to_thread(path.open, "wb")
            try:
                while chunk := await file.read(1024 * 1024):
                    total += len(chunk)
                    if total > max_upload_bytes:
                        raise HTTPException(413, "Upload exceeds limit")
                    await asyncio.to_thread(stream.write, chunk)
            finally:
                await asyncio.to_thread(stream.close)
                await file.close()
            # Decode/probe before accepting files; extension alone is not validation.
            asset = await chain.loader.load(str(path), owner_id)
            if asset.media_type != "text":
                from mediachain.modalities.audio.ffmpeg import probe

                await probe(asset)
            elif suffix == ".pdf":
                header = await asyncio.to_thread(lambda: path.open("rb").read(5))
                if header != b"%PDF-":
                    raise HTTPException(415, "Invalid PDF file")
            else:
                try:
                    await asyncio.to_thread(path.read_text, encoding="utf-8")
                except UnicodeError as exc:
                    raise HTTPException(415, "Invalid UTF-8 text") from exc
            loaded = await chain.load(str(path), owner_id)
            # Preserve the client filename without using it as a filesystem path.
            loaded.metadata["original_name"] = Path(
                (file.filename or "upload").replace("\\", "/")
            ).name
            await chain.metadata.put_asset(loaded)
            return loaded

    @app.post("/api/v1/media/url", response_model=MediaAsset, status_code=201)
    async def upload_url(body: URLUploadRequest, owner_id: str = Depends(owner)) -> MediaAsset:
        if youtube_download is None:
            raise HTTPException(503, "YouTube imports are not configured")
        with TemporaryDirectory(prefix="mediachain-youtube-") as temp:
            downloaded = await youtube_download(
                body.url,
                Path(temp),
                max_remote_bytes,
                max_remote_duration_seconds,
            )
            if downloaded.path.suffix.lower() not in {".mp4", ".mov", ".mkv", ".webm"}:
                raise HTTPException(415, "YouTube did not provide a supported video")
            loaded = await chain.load(str(downloaded.path), owner_id)
            loaded = loaded.model_copy(
                update={
                    "duration": downloaded.duration,
                    "metadata": {
                        **loaded.metadata,
                        "original_name": downloaded.title + downloaded.path.suffix.lower(),
                        "remote_url": downloaded.webpage_url,
                        "remote_provider": "youtube",
                    },
                }
            )
            await chain.metadata.put_asset(loaded)
            return loaded

    @app.get("/api/v1/media/{media_id}", response_model=MediaAsset)
    async def get_media(media_id: str, owner_id: str = Depends(owner)) -> MediaAsset:
        return await owned(media_id, owner_id)

    @app.delete("/api/v1/media/{media_id}", status_code=204)
    async def delete_media(media_id: str, owner_id: str = Depends(owner)) -> None:
        await owned(media_id, owner_id)
        if redis is None:
            await chain.delete(media_id)
        else:
            async with asset_lease(redis, media_id):
                await chain.delete(media_id)

    @app.post("/api/v1/media/{media_id}/process", response_model=Job, status_code=202)
    async def process(media_id: str, owner_id: str = Depends(owner)) -> Job:
        await owned(media_id, owner_id)
        return await jobs.enqueue(media_id, owner_id)

    @app.get("/api/v1/jobs/{job_id}", response_model=Job)
    async def get_job(job_id: str, owner_id: str = Depends(owner)) -> Job:
        job = await chain.metadata.get_job(job_id)
        if job is None or job.owner_id != owner_id:
            raise HTTPException(404, "Job not found")
        return job

    @app.post("/api/v1/query", response_model=ModelResponse)
    async def query(body: QueryRequest, owner_id: str = Depends(owner)) -> ModelResponse:
        response = await chain.ask(
            body.question, body.media_ids, owner_id=owner_id, filters=body.filters
        )
        return response if body.include_sources else response.model_copy(update={"sources": []})

    @app.post("/api/v1/summarize", response_model=ModelResponse)
    async def summarize(body: SummaryRequest, owner_id: str = Depends(owner)) -> ModelResponse:
        response = await chain.summarize(
            body.media_ids,
            owner_id=owner_id,
            filters=body.filters,
            focus=body.focus,
        )
        return response if body.include_sources else response.model_copy(update={"sources": []})

    @app.post("/api/v1/agent/query", response_model=ModelResponse)
    async def agent_query(body: AgentQueryRequest, owner_id: str = Depends(owner)) -> ModelResponse:
        if chain.rag.llm is None:
            raise HTTPException(503, "Agent analysis requires a chat model")
        if body.media_ids is not None:
            for media_id in body.media_ids:
                await owned(media_id, owner_id)
        context = ExecutionContext(owner_id=owner_id)
        agent = Agent(
            chain.rag.llm,
            media_tools(chain, owner_id, media_ids=body.media_ids),
            agent_limits,
        )
        try:
            run = await agent.run_detailed(body.question, context)
        except (BudgetExceeded, TimeoutError):
            grounded = await chain.ask(
                body.question,
                body.media_ids,
                owner_id=owner_id,
                context=context,
            )
            response = agent_fallback(grounded, tool_calls=[], limit_reached=True)
            return response if body.include_sources else response.model_copy(update={"sources": []})
        tool_calls = []
        for step in run.steps:
            result_count = len(step.observation) if isinstance(step.observation, list) else 1
            if isinstance(step.observation, dict) and isinstance(
                step.observation.get("sources"), list
            ):
                result_count = len(step.observation["sources"])
            tool_calls.append(
                {
                    "tool": step.tool,
                    "arguments": step.arguments,
                    "result_count": result_count,
                }
            )
        try:
            sources = agent_sources(run)
        except GroundingError:
            grounded = await chain.ask(
                body.question,
                body.media_ids,
                owner_id=owner_id,
                context=context,
            )
            response = agent_fallback(grounded, tool_calls=tool_calls, agent_tokens=run.token_usage)
            return response if body.include_sources else response.model_copy(update={"sources": []})
        response = ModelResponse(
            answer=run.answer,
            sources=sources,
            insufficient_evidence=run.insufficient_evidence,
            token_usage=run.token_usage,
            metadata={"mode": "agentic", "tool_calls": tool_calls},
        )
        return response if body.include_sources else response.model_copy(update={"sources": []})

    if frontend_dir is not None and Path(frontend_dir).is_dir():
        app.mount("/", StaticFiles(directory=frontend_dir, html=True), name="frontend")
    return app
