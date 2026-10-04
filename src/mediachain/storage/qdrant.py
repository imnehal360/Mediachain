"""Qdrant adapter: each collection is bound to a complete embedding-space identity."""

from __future__ import annotations

import asyncio
from typing import Any
from uuid import NAMESPACE_URL, uuid5

from mediachain.core.models import EmbeddingSpace, VectorRecord
from mediachain.storage.vector import validate_vector


def point_id(document_id: str) -> str:
    return str(uuid5(NAMESPACE_URL, "mediachain:" + document_id))


class QdrantVectorStore:
    def __init__(
        self, url: str = "http://localhost:6333", collection: str = "mediachain", client: Any = None
    ):
        from qdrant_client import AsyncQdrantClient

        self.client = client or AsyncQdrantClient(url=url)
        self.collection = collection
        self._collections: set[str] = set()
        self._lock = asyncio.Lock()

    async def _ensure(self, space: EmbeddingSpace) -> str:
        from qdrant_client import models

        name = f"{self.collection}_{space.key}"
        async with self._lock:
            if name not in self._collections:
                if not await self.client.collection_exists(name):
                    try:
                        await self.client.create_collection(
                            name,
                            vectors_config=models.VectorParams(
                                size=space.dimensions, distance=models.Distance.COSINE
                            ),
                        )
                    except Exception:
                        if not await self.client.collection_exists(name):
                            raise
                self._collections.add(name)
        return name

    async def upsert(self, records: list[VectorRecord], space: EmbeddingSpace) -> None:
        from qdrant_client import models

        for record in records:
            validate_vector(record.values, space)
        name = await self._ensure(space)
        for start in range(0, len(records), 128):
            await self.client.upsert(
                collection_name=name,
                wait=True,
                points=[
                    models.PointStruct(
                        id=point_id(r.document_id),
                        vector=r.values,
                        payload={"document_id": r.document_id, "asset_id": r.asset_id},
                    )
                    for r in records[start : start + 128]
                ],
            )

    async def search(
        self, vector: list[float], space: EmbeddingSpace, document_ids: list[str], limit: int
    ) -> list[tuple[str, float]]:
        from qdrant_client import models

        validate_vector(vector, space)
        if not document_ids:
            return []
        name = await self._ensure(space)
        result = await self.client.query_points(
            collection_name=name,
            query=vector,
            limit=limit,
            query_filter=models.Filter(
                must=[models.HasIdCondition(has_id=[point_id(i) for i in document_ids])]
            ),
        )
        return [(str(p.payload["document_id"]), float(p.score)) for p in result.points if p.payload]

    async def delete_asset(self, asset_id: str, keep_ids: list[str] | None = None) -> None:
        from qdrant_client import models

        # Discover persisted collections too; deletion must work after a process restart.
        names = (await self.client.get_collections()).collections
        for collection in names:
            if not collection.name.startswith(self.collection + "_"):
                continue
            where = models.Filter(
                must=[
                    models.FieldCondition(key="asset_id", match=models.MatchValue(value=asset_id))
                ],
                must_not=[models.HasIdCondition(has_id=[point_id(i) for i in keep_ids])]
                if keep_ids
                else None,
            )
            await self.client.delete(
                collection_name=collection.name,
                points_selector=models.FilterSelector(filter=where),
                wait=True,
            )

    async def close(self) -> None:
        await self.client.close()
