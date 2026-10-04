"""Optional authenticated REST API. The SDK never imports this module."""

from __future__ import annotations

import asyncio
import secrets
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from pathlib import Path
from tempfile import TemporaryDirectory
from typing import Any

from fastapi import Depends, FastAPI, File, HTTPException, Request, UploadFile
from fastapi.exceptions import RequestValidationError
from fastapi.responses import FileResponse, JSONResponse
from fastapi.staticfiles import StaticFiles
from pydantic import Field
from starlette.exceptions import HTTPException as StarletteHTTPException

from mediachain.core.errors import MediaChainError
from mediachain.core.models import Document, Job, MediaAsset, Model, ModelResponse, RetrievalFilter
from mediachain.loaders.local import FORMATS
from mediachain.runtime.client import MediaChain
from mediachain.runtime.jobs import JobQueue, LocalJobQueue, asset_lease


class QueryRequest(Model):
    question: str = Field(min_length=1, max_length=10000)
    media_ids: list[str] | None = None
    filters: RetrievalFilter | None = None
    include_sources: bool = True


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
    queue: JobQueue | None = None,
    max_upload_bytes: int = 100 * 1024 * 1024,
    redis: Any = None,
    frontend_dir: str | Path | None = None,
) -> FastAPI:
    """Map bearer API keys to owner IDs. No unauthenticated default is provided."""
    if not api_keys and development_owner is None:
        raise ValueError("Configure API keys or explicitly opt into development_owner")
    if max_upload_bytes <= 0 or (
        api_keys and any(not key or not owner for key, owner in api_keys.items())
    ):
        raise ValueError("Invalid upload limit or empty API key/owner")
    jobs = queue or LocalJobQueue(chain)

    @asynccontextmanager
    async def lifespan(app: FastAPI) -> AsyncIterator[None]:
        yield
        await jobs.close()

    app = FastAPI(title="MediaChain", version="0.1.0", lifespan=lifespan)
    app.add_middleware(BodyLimit, limit=max_upload_bytes + 65536)

    async def owner(request: Request) -> str:
        authorization = request.headers.get("authorization", "")
        token = authorization[7:] if authorization.startswith("Bearer ") else ""
        for key, value in (api_keys or {}).items():
            if secrets.compare_digest(token, key):
                return value
        if development_owner is not None and not api_keys:
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
            "max_upload_bytes": max_upload_bytes,
            "formats": [
                suffix for suffix, modality in FORMATS.items() if modality in chain.processors
            ],
            "answer_mode": "generative" if chain.rag.llm else "extractive",
        }

    @app.get("/api/v1/media", response_model=list[MediaAsset])
    async def list_media(owner_id: str = Depends(owner)) -> list[MediaAsset]:
        return await chain.metadata.list_assets(owner_id)

    @app.get("/api/v1/jobs", response_model=list[Job])
    async def list_jobs(owner_id: str = Depends(owner)) -> list[Job]:
        return await chain.metadata.list_jobs(owner_id)

    @app.get("/api/v1/media/{media_id}/documents", response_model=list[Document])
    async def documents(media_id: str, owner_id: str = Depends(owner)) -> list[Document]:
        await owned(media_id, owner_id)
        return await chain.documents.list_documents(RetrievalFilter(media_ids=[media_id]))

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

    if frontend_dir is not None and Path(frontend_dir).is_dir():
        app.mount("/", StaticFiles(directory=frontend_dir, html=True), name="frontend")
    return app
