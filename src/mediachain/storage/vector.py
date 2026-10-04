"""Explicit embedding spaces and a small local cosine index."""

from __future__ import annotations

import math

from mediachain.core.errors import EmbeddingSpaceError
from mediachain.core.models import EmbeddingSpace, VectorRecord


def validate_vector(vector: list[float], space: EmbeddingSpace) -> None:
    if len(vector) != space.dimensions or not all(math.isfinite(x) for x in vector):
        raise EmbeddingSpaceError("Vector must be finite and match declared dimensions")


class MemoryVectorStore:
    def __init__(self) -> None:
        self.space: EmbeddingSpace | None = None
        self.records: dict[str, VectorRecord] = {}

    def _space(self, space: EmbeddingSpace) -> None:
        if self.space is not None and self.space != space:
            raise EmbeddingSpaceError("Index belongs to a different embedding space")

    async def upsert(self, records: list[VectorRecord], space: EmbeddingSpace) -> None:
        self._space(space)
        for record in records:
            validate_vector(record.values, space)
        self.space = space.model_copy(deep=True)
        self.records.update({r.document_id: r.model_copy(deep=True) for r in records})

    async def search(
        self, vector: list[float], space: EmbeddingSpace, document_ids: list[str], limit: int
    ) -> list[tuple[str, float]]:
        self._space(space)
        validate_vector(vector, space)
        norm = math.sqrt(sum(v * v for v in vector))
        if not norm:
            return []
        scored = []
        for doc_id in document_ids:
            record = self.records.get(doc_id)
            if record is None:
                continue
            denominator = norm * math.sqrt(sum(v * v for v in record.values))
            score = (
                sum(a * b for a, b in zip(vector, record.values, strict=True)) / denominator
                if denominator
                else 0
            )
            scored.append((doc_id, score))
        return sorted(scored, key=lambda pair: (-pair[1], pair[0]))[:limit]

    async def delete_asset(self, asset_id: str, keep_ids: list[str] | None = None) -> None:
        keep = set(keep_ids or [])
        self.records = {
            k: v for k, v in self.records.items() if v.asset_id != asset_id or k in keep
        }
