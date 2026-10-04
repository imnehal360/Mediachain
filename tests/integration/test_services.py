"""Opt-in tests against explicitly configured disposable services."""

import os
from uuid import uuid4

import pytest

from mediachain.core.models import Document, Job, MediaAsset, RetrievalFilter


@pytest.mark.services
@pytest.mark.skipif(
    not os.getenv("MEDIACHAIN_TEST_POSTGRES"), reason="No disposable PostgreSQL configured"
)
async def test_postgres_transaction_and_cascade():
    asyncpg = pytest.importorskip("asyncpg")
    from mediachain.storage.postgres import PostgresStore

    store = await PostgresStore.connect(os.environ["MEDIACHAIN_TEST_POSTGRES"])
    identity = "test-" + uuid4().hex
    asset = MediaAsset(
        id=identity, source="test.txt", media_type="text", content_hash="test", owner_id=identity
    )
    document = Document(
        id=identity, asset_id=identity, source="test.txt", content="test", modality="text"
    )
    try:
        await store.put_asset(asset)
        await store.replace_documents(identity, [document])
        with pytest.raises(asyncpg.UniqueViolationError):
            await store.replace_documents(identity, [document, document])
        assert await store.list_documents(RetrievalFilter(media_ids=[identity])) == [document]
        await store.put_job(Job(id=identity, media_id=identity, owner_id=identity))
        await store.delete_asset(identity)
        assert not await store.get_job(identity)
        assert not await store.list_documents(RetrievalFilter(media_ids=[identity]))
    finally:
        await store.delete_asset(identity)
        await store.close()


@pytest.mark.services
@pytest.mark.skipif(not os.getenv("MEDIACHAIN_TEST_REDIS"), reason="No disposable Redis configured")
async def test_redis_cache_prefix_and_arq_worker(tmp_path):
    pytest.importorskip("arq")
    from arq import create_pool
    from arq.connections import RedisSettings
    from arq.worker import Worker

    from mediachain import MediaChain
    from mediachain.runtime.jobs import process_media
    from mediachain.storage.cache import RedisCache

    identity = "test-" + uuid4().hex
    url = os.environ["MEDIACHAIN_TEST_REDIS"]
    cache = RedisCache(url, prefix=identity + ":")
    redis = await create_pool(RedisSettings.from_dsn(url))
    chain = MediaChain(data_dir=tmp_path, cache=cache)
    source = tmp_path / "test.txt"
    source.write_text("Test artificial intelligence")
    asset = await chain.load(str(source))
    job = Job(id=identity, media_id=asset.id, owner_id="local")
    queue_name = identity + ":queue"
    try:
        await cache.set("a:1", "one")
        await cache.set("b:1", "two")
        await cache.delete_prefix("a:")
        assert await cache.get("a:1") is None and await cache.get("b:1") == "two"
        await chain.metadata.put_job(job)
        await redis.enqueue_job("process_media", job.id, _job_id=job.id, _queue_name=queue_name)
        worker = Worker(
            [process_media],
            redis_pool=redis,
            queue_name=queue_name,
            burst=True,
            handle_signals=False,
            ctx={"chain": chain},
            keep_result=0,
        )
        await worker.async_run()
        assert (await chain.metadata.get_job(job.id)).status == "completed"
    finally:
        await chain.delete(asset.id)
        await cache.delete_prefix("")
        await cache.close()
        await redis.delete(queue_name)
        await redis.aclose()
