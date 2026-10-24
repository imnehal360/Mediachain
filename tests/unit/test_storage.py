from pathlib import Path

import pytest

from mediachain import MediaChain
from mediachain.core.errors import EmbeddingSpaceError
from mediachain.core.models import (
    Document,
    EmbeddingSpace,
    Job,
    MediaAsset,
    Modality,
    RetrievalFilter,
    VectorRecord,
)
from mediachain.runtime.jobs import reconcile_stale_jobs
from mediachain.storage.local import FileObjectStore, SQLiteStore
from mediachain.storage.s3 import S3ObjectStore
from mediachain.storage.vector import MemoryVectorStore


async def test_persist_replace_delete(tmp_path):
    path = tmp_path / "db.sqlite"
    store = SQLiteStore(path)
    asset = MediaAsset(id="a", source="a.txt", media_type="text", content_hash="hash")
    await store.put_asset(asset)
    assert await store.count_assets("local") == 1
    assert await store.list_assets("local", limit=1, offset=0) == [asset]
    doc = Document(id="d", content="hello", modality=Modality.TEXT, asset_id="a", source="a.txt")
    await store.replace_documents("a", [doc])
    await store.replace_documents("a", [doc])
    store = SQLiteStore(path)
    assert await store.get_asset("a") == asset
    assert await store.list_documents(RetrievalFilter()) == [doc]
    await store.delete_asset("a")
    assert await store.list_documents(RetrievalFilter()) == []


async def test_vectors_atomic_and_space_checked():
    store = MemoryVectorStore()
    space = EmbeddingSpace(model_id="a", model_version="1", dimensions=2)
    await store.upsert([VectorRecord(document_id="a", asset_id="x", values=[1, 0])], space)
    with pytest.raises(EmbeddingSpaceError):
        await store.upsert([VectorRecord(document_id="b", asset_id="x", values=[1])], space)
    with pytest.raises(EmbeddingSpaceError):
        await store.search([1, 0], space.model_copy(update={"model_id": "b"}), ["a"], 2)
    assert await store.search([1, 0], space, ["a"], 2) == [("a", 1)]
    await store.delete_asset("x")
    assert not store.records


async def test_object_confinement(tmp_path):
    store = FileObjectStore(tmp_path / "objects")
    with pytest.raises(ValueError):
        await store.resolve("../secret")


async def test_s3_object_roundtrip_and_confinement(tmp_path):
    objects: dict[tuple[str, str], bytes] = {}

    class Client:
        def upload_file(self, source: str, bucket: str, key: str) -> None:
            objects[(bucket, key)] = Path(source).read_bytes()

        def download_file(self, bucket: str, key: str, target: str) -> None:
            Path(target).write_bytes(objects[(bucket, key)])

        def delete_object(self, *, Bucket: str, Key: str) -> None:
            objects.pop((Bucket, Key), None)

    source = tmp_path / "source.txt"
    source.write_text("remote evidence")
    store = S3ObjectStore("bucket", tmp_path / "cache", client=Client())
    cached = Path(await store.put("asset/original.txt", source))
    assert cached.read_text() == "remote evidence"
    cached.unlink()
    assert (await store.resolve("asset/original.txt")).read_text() == "remote evidence"
    await store.delete("asset/original.txt")
    assert not objects
    with pytest.raises(ValueError):
        await store.resolve("../secret")


async def test_stale_running_jobs_are_reconciled(tmp_path):
    store = SQLiteStore(tmp_path / "jobs.sqlite")
    asset = MediaAsset(id="asset", source="a.txt", media_type="text", content_hash="hash")
    await store.put_asset(asset)
    job = Job(id="job", media_id=asset.id, owner_id="local", status="running", updated_at=1)
    await store.put_job(job)
    chain = MediaChain(document_store=store, metadata_store=store, data_dir=tmp_path / "data")
    assert await reconcile_stale_jobs(chain, stale_after=1) == 1
    reconciled = await store.get_job(job.id)
    assert reconciled is not None
    assert reconciled.status == "failed"
    assert reconciled.finished_at is not None
