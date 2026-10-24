import pytest

from mediachain.core.models import EmbeddingSpace, VectorRecord
from mediachain.storage.qdrant import QdrantVectorStore


@pytest.mark.filterwarnings("ignore:Payload indexes have no effect in the local Qdrant")
async def test_qdrant_embedded_namespace_filter_delete():
    qdrant = pytest.importorskip("qdrant_client")
    client = qdrant.AsyncQdrantClient(location=":memory:")
    store = QdrantVectorStore(client=client)
    space = EmbeddingSpace(model_id="one", model_version="1", dimensions=2)
    other = space.model_copy(update={"model_id": "two"})
    await store.upsert(
        [
            VectorRecord(document_id="a", asset_id="x", values=[1, 0]),
            VectorRecord(document_id="b", asset_id="y", values=[0, 1]),
        ],
        space,
    )
    assert await store.search([1, 0], other, ["a"], 3) == []
    assert (await store.search([1, 0], space, ["a"], 3))[0][0] == "a"
    assert [p[0] for p in await store.search([1, 0], space, ["b"], 3)] == ["b"]
    await store.delete_asset("x")
    assert await store.search([1, 0], space, ["a"], 3) == []
    await store.close()
