import pytest

from mediachain.core.errors import EmbeddingSpaceError
from mediachain.core.models import (
    Document,
    EmbeddingSpace,
    MediaAsset,
    Modality,
    RetrievalFilter,
    VectorRecord,
)
from mediachain.storage.local import FileObjectStore, SQLiteStore
from mediachain.storage.vector import MemoryVectorStore


async def test_persist_replace_delete(tmp_path):
    path = tmp_path / "db.sqlite"
    store = SQLiteStore(path)
    asset = MediaAsset(id="a", source="a.txt", media_type="text", content_hash="hash")
    await store.put_asset(asset)
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
