"""Local ephemeral jobs and an ARQ adapter; no custom distributed queue."""

from __future__ import annotations

import asyncio
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from typing import Any, Protocol
from uuid import uuid4

from mediachain.core.models import ExecutionContext, Job
from mediachain.runtime.client import MediaChain


class JobQueue(Protocol):
    async def enqueue(self, media_id: str, owner_id: str) -> Job: ...
    async def close(self) -> None: ...


class LocalJobQueue:
    """For one-process development only. Jobs cannot survive process termination."""

    def __init__(self, chain: MediaChain):
        self.chain = chain
        self.tasks: set[asyncio.Task[None]] = set()

    async def enqueue(self, media_id: str, owner_id: str) -> Job:
        job = Job(id=uuid4().hex, media_id=media_id, owner_id=owner_id)
        await self.chain.metadata.put_job(job)
        task = asyncio.create_task(self._run(job))
        self.tasks.add(task)
        task.add_done_callback(self.tasks.discard)
        return job

    async def _run(self, job: Job) -> None:
        job.status = "running"
        await self.chain.metadata.put_job(job)
        try:
            await self.chain.process(job.media_id, ExecutionContext(owner_id=job.owner_id))
            job.status = "completed"
        except asyncio.CancelledError:
            job.status = "cancelled"
            raise
        except Exception:
            job.status, job.error = (
                "failed",
                "Processing failed; inspect configured providers and server traces",
            )
        finally:
            if await self.chain.metadata.get_asset(job.media_id):
                await self.chain.metadata.put_job(job)

    async def close(self) -> None:
        for task in self.tasks:
            task.cancel()
        await asyncio.gather(*list(self.tasks), return_exceptions=True)


class ARQJobQueue:
    def __init__(self, chain: MediaChain, redis: Any):
        self.chain, self.redis = chain, redis

    async def enqueue(self, media_id: str, owner_id: str) -> Job:
        job = Job(id=uuid4().hex, media_id=media_id, owner_id=owner_id)
        await self.chain.metadata.put_job(job)
        try:
            await self.redis.enqueue_job("process_media", job.id, _job_id=job.id)
        except Exception:
            job.status, job.error = "failed", "Queue unavailable"
            await self.chain.metadata.put_job(job)
            raise
        return job

    async def close(self) -> None:
        await self.redis.aclose()


@asynccontextmanager
async def asset_lease(redis: Any, asset_id: str) -> AsyncIterator[None]:
    """Lease outlives the configured ARQ 1800s job timeout. All writers must use it."""
    async with redis.lock("mediachain:lease:" + asset_id, timeout=3600, blocking_timeout=30):
        yield


async def process_media(ctx: dict[str, Any], job_id: str) -> None:
    chain: MediaChain = ctx["chain"]
    job = await chain.metadata.get_job(job_id)
    if job is None:
        return
    async with asset_lease(ctx["redis"], job.media_id):
        asset = await chain.metadata.get_asset(job.media_id)
        if asset is None or asset.owner_id != job.owner_id:
            return
        await LocalJobQueue(chain)._run(job)
