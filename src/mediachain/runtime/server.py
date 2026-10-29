"""Shared environment-driven dependency factory for API and ARQ workers."""

from __future__ import annotations

import asyncio
import json
import os
from typing import Any

from mediachain.agents import AgentLimits
from mediachain.api.app import create_app
from mediachain.core.config import ProcessingConfig
from mediachain.models.providers import (
    FasterWhisperSpeech,
    HTTPChatModel,
    HTTPDiarizationModel,
    HTTPEmbeddingModel,
    HTTPSpeechModel,
    HTTPVisionModel,
    HuggingFaceEmbeddingModel,
    HuggingFaceSpeech,
)
from mediachain.processors.ocr import VisionPDFOCR
from mediachain.runtime.client import MediaChain
from mediachain.runtime.jobs import (
    ARQJobQueue,
    JobQueue,
    LocalJobQueue,
    process_media,
    reconcile_stale_jobs,
)
from mediachain.storage.cache import RedisCache
from mediachain.storage.postgres import PostgresStore
from mediachain.storage.qdrant import QdrantVectorStore
from mediachain.storage.s3 import S3ObjectStore

HOSTED_SETTINGS = ("DATABASE_URL", "REDIS_URL", "QDRANT_URL", "S3_BUCKET")


def enabled(name: str) -> bool:
    return os.environ.get(name, "").lower() in {"1", "true", "yes"}


def validate_server_config() -> None:
    if not enabled("MEDIACHAIN_REQUIRE_HOSTED_SERVICES"):
        return
    if enabled("MEDIACHAIN_DISABLE_AUTH"):
        raise ValueError("MEDIACHAIN_DISABLE_AUTH cannot be used with hosted services")
    missing = [name for name in HOSTED_SETTINGS if not os.environ.get(name)]
    if missing:
        raise ValueError("Missing required hosted settings: " + ", ".join(missing))
    try:
        keys = json.loads(os.environ.get("MEDIACHAIN_API_KEYS", "{}"))
    except json.JSONDecodeError as exc:
        raise ValueError("MEDIACHAIN_API_KEYS must be valid JSON") from exc
    if not isinstance(keys, dict) or not keys:
        raise ValueError("MEDIACHAIN_API_KEYS must contain at least one workspace key")
    model_errors = []
    if (os.environ.get("CHAT_MODEL") or os.environ.get("VISION_MODEL")) and not os.environ.get(
        "MODEL_BASE_URL"
    ):
        model_errors.append("MODEL_BASE_URL")
    if (
        os.environ.get("SPEECH_MODEL")
        and os.environ.get("SPEECH_PROVIDER", "").lower() != "huggingface"
        and not os.environ.get("SPEECH_BASE_URL")
    ):
        model_errors.append("SPEECH_BASE_URL")
    if os.environ.get("DIARIZATION_MODEL") and not os.environ.get("DIARIZATION_BASE_URL"):
        model_errors.append("DIARIZATION_BASE_URL")
    if (
        os.environ.get("EMBEDDING_MODEL")
        and os.environ.get("EMBEDDING_PROVIDER", "").lower() != "huggingface"
        and not os.environ.get("EMBEDDING_BASE_URL")
    ):
        model_errors.append("EMBEDDING_BASE_URL")
    if os.environ.get("OCR_MODEL") and not (
        os.environ.get("OCR_BASE_URL") or os.environ.get("MODEL_BASE_URL")
    ):
        model_errors.append("OCR_BASE_URL")
    verify = enabled("VERIFY_GROUNDED_ANSWERS")
    if verify and not (os.environ.get("VERIFIER_MODEL") or os.environ.get("CHAT_MODEL")):
        model_errors.append("VERIFIER_MODEL")
    if verify and not (os.environ.get("VERIFIER_BASE_URL") or os.environ.get("MODEL_BASE_URL")):
        model_errors.append("VERIFIER_BASE_URL")
    if model_errors:
        raise ValueError("Missing hosted model settings: " + ", ".join(dict.fromkeys(model_errors)))


def csv_setting(name: str) -> list[str]:
    return [value.strip() for value in os.environ.get(name, "").split(",") if value.strip()]


async def build_chain() -> MediaChain:
    validate_server_config()
    data_dir = os.environ.get("MEDIACHAIN_DATA_DIR", ".mediachain")
    kwargs: dict[str, Any] = {
        "data_dir": data_dir,
        "config": ProcessingConfig(
            frame_interval=float(os.environ.get("MEDIACHAIN_FRAME_INTERVAL", "5")),
            max_frames=int(os.environ.get("MEDIACHAIN_MAX_FRAMES", "1000")),
            speech_timeout=(
                float(os.environ["MEDIACHAIN_SPEECH_TIMEOUT"])
                if os.environ.get("MEDIACHAIN_SPEECH_TIMEOUT")
                else None
            ),
        ),
    }
    if bucket := os.environ.get("S3_BUCKET"):
        kwargs["object_store"] = S3ObjectStore(
            bucket,
            os.path.join(data_dir, "object-cache"),
            prefix=os.environ.get("S3_PREFIX", "mediachain"),
            region=os.environ.get("AWS_REGION") or None,
            endpoint_url=os.environ.get("S3_ENDPOINT_URL") or None,
        )
    if dsn := os.environ.get("DATABASE_URL"):
        store = await PostgresStore.connect(dsn)
        kwargs.update(metadata_store=store, document_store=store)
    if url := os.environ.get("QDRANT_URL"):
        kwargs["vector_store"] = QdrantVectorStore(
            url,
            api_key=os.environ.get("QDRANT_API_KEY") or None,
        )
    if url := os.environ.get("REDIS_URL"):
        kwargs["cache"] = RedisCache(url)
    if model := os.environ.get("CHAT_MODEL"):
        kwargs["llm"] = HTTPChatModel(
            model, os.environ["MODEL_BASE_URL"], os.environ.get("MODEL_API_KEY", "")
        )
    if model := os.environ.get("VISION_MODEL"):
        kwargs["vision"] = HTTPVisionModel(
            model, os.environ["MODEL_BASE_URL"], os.environ.get("MODEL_API_KEY", "")
        )
    if model := os.environ.get("OCR_MODEL"):
        ocr_vision = HTTPVisionModel(
            model,
            os.environ.get("OCR_BASE_URL") or os.environ["MODEL_BASE_URL"],
            os.environ.get("OCR_API_KEY", os.environ.get("MODEL_API_KEY", "")),
        )
        kwargs["ocr"] = VisionPDFOCR(
            ocr_vision,
            max_pages=int(os.environ.get("OCR_MAX_PAGES", "200")),
        )
    if model := os.environ.get("SPEECH_MODEL"):
        if os.environ.get("SPEECH_PROVIDER", "").lower() == "huggingface":
            kwargs["speech"] = HuggingFaceSpeech(
                model,
                os.environ.get("SPEECH_API_KEY", os.environ.get("MODEL_API_KEY", "")),
                provider=os.environ.get("SPEECH_HF_PROVIDER", "auto"),
                model_version=os.environ.get("SPEECH_MODEL_REVISION", "configured"),
            )
        elif url := os.environ.get("SPEECH_BASE_URL"):
            kwargs["speech"] = HTTPSpeechModel(
                model,
                url,
                os.environ.get("SPEECH_API_KEY", os.environ.get("MODEL_API_KEY", "")),
            )
        else:
            kwargs["speech"] = FasterWhisperSpeech(model)
    if model := os.environ.get("DIARIZATION_MODEL"):
        kwargs["diarization"] = HTTPDiarizationModel(
            model,
            os.environ["DIARIZATION_BASE_URL"],
            os.environ.get("DIARIZATION_API_KEY", os.environ.get("MODEL_API_KEY", "")),
        )
    if model := os.environ.get("EMBEDDING_MODEL"):
        dimensions = int(os.environ.get("EMBEDDING_DIMENSIONS", "384"))
        if os.environ.get("EMBEDDING_PROVIDER", "").lower() == "huggingface":
            kwargs["embeddings"] = HuggingFaceEmbeddingModel(
                model,
                os.environ.get("EMBEDDING_API_KEY", os.environ.get("MODEL_API_KEY", "")),
                dimensions,
                provider=os.environ.get("EMBEDDING_HF_PROVIDER", "hf-inference"),
                model_version=os.environ.get("EMBEDDING_REVISION", "configured"),
            )
        elif url := os.environ.get("EMBEDDING_BASE_URL"):
            kwargs["embeddings"] = HTTPEmbeddingModel(
                model,
                url,
                dimensions,
                os.environ.get("EMBEDDING_API_KEY", os.environ.get("MODEL_API_KEY", "")),
                os.environ.get("EMBEDDING_REVISION", "configured"),
            )
        else:
            from mediachain.embeddings.local import SentenceTransformerEmbeddings

            kwargs["embeddings"] = SentenceTransformerEmbeddings(
                model,
                os.environ.get("EMBEDDING_REVISION", "main"),
                dimensions,
            )
    if os.environ.get("VERIFY_GROUNDED_ANSWERS", "").lower() in {"1", "true", "yes"}:
        kwargs["verifier"] = HTTPChatModel(
            os.environ.get("VERIFIER_MODEL") or os.environ["CHAT_MODEL"],
            os.environ.get("VERIFIER_BASE_URL") or os.environ["MODEL_BASE_URL"],
            os.environ.get("VERIFIER_API_KEY", os.environ.get("MODEL_API_KEY", "")),
        )
    return MediaChain(**kwargs)


async def check_chain(chain: MediaChain) -> bool:
    resources = {
        id(item): item for item in (chain.metadata, chain.vectors, chain.cache, chain.objects)
    }

    async def check(resource: Any) -> bool:
        healthcheck = getattr(resource, "healthcheck", None)
        return bool(await healthcheck()) if healthcheck else True

    try:
        return all(await asyncio.gather(*(check(resource) for resource in resources.values())))
    except Exception:
        return False


async def close_chain(chain: MediaChain) -> None:
    for resource in (chain.metadata, chain.vectors, chain.cache):
        if hasattr(resource, "close"):
            await resource.close()


class Server:
    """ASGI lifespan initializes async clients on the server event loop."""

    def __init__(self) -> None:
        self.app: Any = None

    async def __call__(self, scope: Any, receive: Any, send: Any) -> None:
        if scope["type"] == "lifespan":
            await receive()
            chain = None
            queue: JobQueue | None = None
            try:
                chain = await build_chain()
                await reconcile_stale_jobs(chain)
                redis = None
                queue = LocalJobQueue(chain)
                if url := os.environ.get("REDIS_URL"):
                    from arq import create_pool
                    from arq.connections import RedisSettings

                    redis = await create_pool(RedisSettings.from_dsn(url))
                    queue = ARQJobQueue(chain, redis)
                self.app = create_app(
                    chain,
                    api_keys=(
                        None
                        if enabled("MEDIACHAIN_DISABLE_AUTH")
                        else json.loads(os.environ.get("MEDIACHAIN_API_KEYS", "{}"))
                    ),
                    development_owner=(
                        os.environ.get("MEDIACHAIN_LOCAL_OWNER", "local-user")
                        if enabled("MEDIACHAIN_DISABLE_AUTH")
                        else None
                    ),
                    development_local_only=enabled("MEDIACHAIN_DISABLE_AUTH"),
                    queue=queue,
                    redis=redis,
                    frontend_dir=os.environ.get("MEDIACHAIN_FRONTEND_DIR", "frontend/dist"),
                    readiness=lambda: check_chain(chain),
                    allowed_origins=csv_setting("MEDIACHAIN_ALLOWED_ORIGINS"),
                    trusted_hosts=csv_setting("MEDIACHAIN_TRUSTED_HOSTS"),
                    rate_limit_per_minute=int(
                        os.environ.get("MEDIACHAIN_RATE_LIMIT_PER_MINUTE", "120")
                    ),
                    max_remote_bytes=int(
                        os.environ.get("MEDIACHAIN_REMOTE_MAX_BYTES", "524288000")
                    ),
                    max_remote_duration_seconds=float(
                        os.environ.get("MEDIACHAIN_REMOTE_MAX_DURATION_SECONDS", "14400")
                    ),
                    agent_limits=AgentLimits(
                        max_steps=int(os.environ.get("MEDIACHAIN_AGENT_MAX_STEPS", "6")),
                        max_tool_calls=int(os.environ.get("MEDIACHAIN_AGENT_MAX_TOOL_CALLS", "3")),
                        timeout=float(os.environ.get("MEDIACHAIN_AGENT_TIMEOUT", "90")),
                        max_tokens=int(os.environ.get("MEDIACHAIN_AGENT_MAX_TOKENS", "50000")),
                        max_observation_chars=int(
                            os.environ.get("MEDIACHAIN_AGENT_MAX_OBSERVATION_CHARS", "12000")
                        ),
                    ),
                )
                await send({"type": "lifespan.startup.complete"})
            except Exception:
                await send(
                    {
                        "type": "lifespan.startup.failed",
                        "message": "MediaChain configuration or service connection failed",
                    }
                )
                if chain:
                    await close_chain(chain)
                return
            await receive()
            if queue:
                await queue.close()
            await close_chain(chain)
            await send({"type": "lifespan.shutdown.complete"})
        else:
            await self.app(scope, receive, send)


async def startup(ctx: dict[str, Any]) -> None:
    ctx["chain"] = await build_chain()
    await reconcile_stale_jobs(ctx["chain"])


async def shutdown(ctx: dict[str, Any]) -> None:
    await close_chain(ctx["chain"])


class WorkerSettings:
    functions = [process_media]
    on_startup = startup
    on_shutdown = shutdown
    job_timeout = 1800
    max_jobs = 4


# ARQ reads this at startup; imports remain confined to the optional server module.
if os.environ.get("REDIS_URL"):
    from arq.connections import RedisSettings

    WorkerSettings.redis_settings = RedisSettings.from_dsn(os.environ["REDIS_URL"])  # type: ignore[attr-defined]

app = Server()
