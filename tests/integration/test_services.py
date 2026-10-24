"""Opt-in tests against explicitly configured disposable services."""

import os
import time
from uuid import uuid4

import pytest

from mediachain.core.models import Document, Job, MediaAsset, RetrievalFilter


@pytest.mark.services
@pytest.mark.skipif(
    not os.getenv("MEDIACHAIN_TEST_POSTGRES"), reason="No disposable PostgreSQL configured"
)
async def test_postgres_transaction_restart_recovery_and_cascade(tmp_path):
    asyncpg = pytest.importorskip("asyncpg")
    from mediachain import MediaChain
    from mediachain.runtime.jobs import reconcile_stale_jobs
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
        job = Job(
            id=identity,
            media_id=identity,
            owner_id=identity,
            status="running",
            started_at=time.time() - 7200,
            updated_at=time.time() - 7200,
        )
        await store.put_job(job)
        chain = MediaChain(document_store=store, metadata_store=store, data_dir=tmp_path)
        assert await reconcile_stale_jobs(chain, stale_after=3600) == 1
        assert (await store.get_job(identity)).status == "failed"

        # A new pool must observe the same committed state after an application restart.
        await store.close()
        store = await PostgresStore.connect(os.environ["MEDIACHAIN_TEST_POSTGRES"])
        assert await store.get_asset(identity) == asset
        assert await store.list_documents(RetrievalFilter(media_ids=[identity])) == [document]
        assert (await store.get_job(identity)).status == "failed"

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
        await cache.close()
        cache = RedisCache(url, prefix=identity + ":")
        assert await cache.get("b:1") == "two"
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


@pytest.mark.services
@pytest.mark.skipif(
    not os.getenv("MEDIACHAIN_TEST_QDRANT"), reason="No disposable Qdrant configured"
)
async def test_qdrant_remote_restart_and_delete():
    pytest.importorskip("qdrant_client")
    from mediachain.core.models import EmbeddingSpace, VectorRecord
    from mediachain.storage.qdrant import QdrantVectorStore

    identity = "test_" + uuid4().hex
    space = EmbeddingSpace(model_id="integration", model_version="1", dimensions=2)
    record = VectorRecord(document_id=identity, asset_id=identity, values=[1.0, 0.0])
    store = QdrantVectorStore(os.environ["MEDIACHAIN_TEST_QDRANT"], collection=identity)
    try:
        await store.upsert([record], space)
        assert (await store.search([1.0, 0.0], space, [identity], 1))[0][0] == identity
        await store.close()

        # Collection discovery, reads, and deletion must work with a fresh client.
        store = QdrantVectorStore(os.environ["MEDIACHAIN_TEST_QDRANT"], collection=identity)
        assert (await store.search([1.0, 0.0], space, [identity], 1))[0][0] == identity
        await store.delete_asset(identity)
        assert await store.search([1.0, 0.0], space, [identity], 1) == []
    finally:
        collection = f"{identity}_{space.key}"
        if await store.client.collection_exists(collection):
            await store.client.delete_collection(collection)
        await store.close()
