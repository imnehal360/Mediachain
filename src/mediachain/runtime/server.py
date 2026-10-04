"""Shared environment-driven dependency factory for API and ARQ workers."""

from __future__ import annotations

import json
import os
from typing import Any

from mediachain.api.app import create_app
from mediachain.models.providers import FasterWhisperSpeech, HTTPChatModel, HTTPVisionModel
from mediachain.runtime.client import MediaChain
from mediachain.runtime.jobs import ARQJobQueue, JobQueue, LocalJobQueue, process_media
from mediachain.storage.cache import RedisCache
from mediachain.storage.postgres import PostgresStore
from mediachain.storage.qdrant import QdrantVectorStore


async def build_chain() -> MediaChain:
    data_dir = os.environ.get("MEDIACHAIN_DATA_DIR", ".mediachain")
    kwargs: dict[str, Any] = {"data_dir": data_dir}
    if dsn := os.environ.get("DATABASE_URL"):
        store = await PostgresStore.connect(dsn)
        kwargs.update(metadata_store=store, document_store=store)
    if url := os.environ.get("QDRANT_URL"):
        kwargs["vector_store"] = QdrantVectorStore(url)
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
    if model := os.environ.get("SPEECH_MODEL"):
        kwargs["speech"] = FasterWhisperSpeech(model)
    if model := os.environ.get("EMBEDDING_MODEL"):
        from mediachain.embeddings.local import SentenceTransformerEmbeddings

        kwargs["embeddings"] = SentenceTransformerEmbeddings(
            model,
            os.environ.get("EMBEDDING_REVISION", "main"),
            int(os.environ.get("EMBEDDING_DIMENSIONS", "384")),
        )
    return MediaChain(**kwargs)


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
                redis = None
                queue = LocalJobQueue(chain)
                if url := os.environ.get("REDIS_URL"):
                    from arq import create_pool
                    from arq.connections import RedisSettings

                    redis = await create_pool(RedisSettings.from_dsn(url))
                    queue = ARQJobQueue(chain, redis)
                self.app = create_app(
                    chain,
                    api_keys=json.loads(os.environ.get("MEDIACHAIN_API_KEYS", "{}")),
                    queue=queue,
                    redis=redis,
                    frontend_dir=os.environ.get("MEDIACHAIN_FRONTEND_DIR", "frontend/dist"),
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
