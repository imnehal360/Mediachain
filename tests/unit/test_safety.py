import asyncio
import socket
import sys

import pytest

from mediachain import MediaChain
from mediachain.core.config import ProcessingConfig
from mediachain.core.errors import UnsupportedMediaError
from mediachain.core.models import Document, ProcessingResult, RetrievalFilter
from mediachain.loaders.http import HTTPSLoader
from mediachain.runtime.jobs import asset_lease
from mediachain.runtime.server import validate_server_config
from mediachain.storage.vector import MemoryVectorStore


async def test_remote_loader_rejects_unapproved_and_private_hosts(tmp_path, monkeypatch):
    loader = HTTPSLoader({"example.com"}, tmp_path)
    with pytest.raises(UnsupportedMediaError):
        await loader.load("http://example.com/video.mp4")
    with pytest.raises(UnsupportedMediaError):
        await loader.load("https://user:password@example.com/video.mp4")
    with pytest.raises(UnsupportedMediaError):
        await loader.load("https://other.example/video.mp4")
    monkeypatch.setattr(
        socket,
        "getaddrinfo",
        lambda *a, **kw: [(socket.AF_INET, socket.SOCK_STREAM, 6, "", ("127.0.0.1", 443))],
    )
    with pytest.raises(UnsupportedMediaError, match="non-public"):
        await loader.load("https://example.com/video.mp4")


async def test_index_failure_preserves_committed_generation_and_deletes_stale_cache(tmp_path):
    class FailingStore(MemoryVectorStore):
        fail = False

        async def upsert(self, records, space):
            await super().upsert(records, space)
            if self.fail:
                raise ConnectionError("Staged writes failed")

    source = tmp_path / "source.txt"
    source.write_text("Artificial intelligence provides evidence.")
    vectors = FailingStore()
    chain = MediaChain(data_dir=tmp_path / "data", vector_store=vectors)
    asset = await chain.add(str(source))
    old = await chain.documents.list_documents(RetrievalFilter())

    class Replacement:
        def fingerprint(self):
            return {"processor": "replacement"}

        async def process(self, asset, context):
            return ProcessingResult(
                asset=asset,
                documents=[
                    Document(
                        id="replacement",
                        content="new secret data",
                        asset_id=asset.id,
                        source=asset.source,
                        modality="text",
                    )
                ],
            )

    chain.register_processor("text", Replacement())
    vectors.fail = True
    with pytest.raises(ConnectionError):
        await chain.process(asset.id)
    assert await chain.documents.list_documents(RetrievalFilter()) == old
    assert (await chain.ask("artificial intelligence", [asset.id])).sources[0].document_id == old[
        0
    ].id
    assert not (await chain.ask("new secret", [asset.id])).sources
    await chain.delete(asset.id)
    assert not chain.cache.values
    assert not vectors.records


async def test_concurrent_idempotent_ingestion(tmp_path):
    import asyncio

    source = tmp_path / "source.txt"
    source.write_text("Concurrency is useful.")
    chain = MediaChain(data_dir=tmp_path / "data")
    first, second = await asyncio.gather(chain.add(str(source)), chain.add(str(source)))
    assert first.id == second.id
    assert len(await chain.documents.list_documents(RetrievalFilter())) == 1


async def test_sync_wrappers_reject_running_event_loop(tmp_path):
    chain = MediaChain(data_dir=tmp_path)
    with pytest.raises(RuntimeError, match="await"):
        chain.ask_sync("question")


def test_core_import_does_not_import_optional_provider_libraries():
    import subprocess

    script = "import mediachain,sys; assert not ({'fastapi','av','faster_whisper','qdrant_client','redis','asyncpg','sentence_transformers','huggingface_hub'} & set(sys.modules))"
    subprocess.run([sys.executable, "-c", script], check=True)


def test_hosted_server_configuration_is_explicit(monkeypatch):
    monkeypatch.setenv("MEDIACHAIN_REQUIRE_HOSTED_SERVICES", "true")
    for name in ("DATABASE_URL", "REDIS_URL", "QDRANT_URL", "S3_BUCKET"):
        monkeypatch.delenv(name, raising=False)
    with pytest.raises(ValueError, match="DATABASE_URL.*REDIS_URL.*QDRANT_URL.*S3_BUCKET"):
        validate_server_config()

    monkeypatch.setenv("DATABASE_URL", "postgresql://host/database")
    monkeypatch.setenv("REDIS_URL", "rediss://host/0")
    monkeypatch.setenv("QDRANT_URL", "https://qdrant.example")
    monkeypatch.setenv("S3_BUCKET", "bucket")
    monkeypatch.setenv("MEDIACHAIN_API_KEYS", '{"key":"owner"}')
    validate_server_config()
    monkeypatch.setenv("SPEECH_MODEL", "openai/whisper-large-v3")
    monkeypatch.setenv("SPEECH_PROVIDER", "huggingface")
    monkeypatch.setenv("EMBEDDING_MODEL", "sentence-transformers/all-MiniLM-L6-v2")
    monkeypatch.setenv("EMBEDDING_PROVIDER", "huggingface")
    validate_server_config()
    monkeypatch.setenv("DIARIZATION_MODEL", "speaker-model")
    with pytest.raises(ValueError, match="DIARIZATION_BASE_URL"):
        validate_server_config()


async def test_asset_lease_renews_until_released():
    class Lock:
        renewed = 0
        released = False

        async def acquire(self):
            return True

        async def extend(self, seconds, *, replace_ttl):
            assert seconds == 1
            assert replace_ttl
            self.renewed += 1

        async def release(self):
            self.released = True

    lock = Lock()

    class Redis:
        def lock(self, name, **options):
            assert name == "mediachain:lease:asset"
            assert options["timeout"] == 1
            return lock

    async with asset_lease(Redis(), "asset", lease_seconds=1, renew_every=0.001):
        await asyncio.sleep(0.005)
    assert lock.renewed > 0
    assert lock.released


async def test_cache_invalidation_after_config_change(tmp_path):
    source = tmp_path / "source.txt"
    source.write_text("alpha beta gamma delta epsilon zeta")
    chain = MediaChain(data_dir=tmp_path / "data")
    asset = await chain.add(str(source))
    from mediachain.processors.text import TextProcessor

    chain.register_processor(
        "text", TextProcessor(ProcessingConfig(chunk_size=10, chunk_overlap=0))
    )
    result = await chain.process(asset.id)
    assert len(result.documents) > 1
    assert len(chain.cache.values) > 1
    await chain.delete(asset.id)
    assert not chain.cache.values
