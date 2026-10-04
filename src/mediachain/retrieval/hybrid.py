"""Prefiltered hybrid retrieval and same-asset temporal evidence expansion."""

from __future__ import annotations

import math
from collections import Counter

from mediachain.core.interfaces import DocumentStore, EmbeddingModel, Reranker, VectorStore
from mediachain.core.models import RetrievalFilter, RetrievalResult
from mediachain.embeddings.local import tokens
from mediachain.temporal.alignment import overlaps


class HybridRetriever:
    def __init__(
        self,
        documents: DocumentStore,
        vectors: VectorStore,
        embeddings: EmbeddingModel,
        reranker: Reranker | None = None,
        temporal_expansion: bool = True,
    ):
        self.documents, self.vectors, self.embeddings = documents, vectors, embeddings
        self.reranker, self.temporal_expansion = reranker, temporal_expansion

    async def retrieve(
        self, query: str, filters: RetrievalFilter | None = None, limit: int = 8
    ) -> list[RetrievalResult]:
        if limit <= 0 or not query.strip():
            return []
        candidates = await self.documents.list_documents(filters or RetrievalFilter())
        if not candidates:
            return []
        by_id = {d.id: d for d in candidates}
        query_terms = set(tokens(query))
        counts = {d.id: Counter(tokens(d.content)) for d in candidates}
        df = {term: sum(term in c for c in counts.values()) for term in query_terms}
        keyword = []
        for doc in candidates:
            count = counts[doc.id]
            score = sum(
                (1 + math.log(count[t])) * math.log(1 + len(candidates) / (1 + df[t]))
                for t in query_terms
                if count[t]
            )
            if score > 0:
                keyword.append((doc.id, score))
        keyword.sort(key=lambda p: (-p[1], p[0]))
        vector = (await self.embeddings.embed([query]))[0]
        semantic = await self.vectors.search(
            vector, self.embeddings.space, list(by_id), max(limit * 4, 20)
        )
        # Negative/zero cosine carries no positive evidence. Hash vectors require keyword support.
        semantic = [
            (i, s)
            for i, s in semantic
            if i in by_id
            and s > 0
            and (
                self.embeddings.space.model_id != "lexical-hash"
                or any(t in counts[i] for t in query_terms)
            )
        ]
        fused: dict[str, float] = {}
        for ranked in (keyword, semantic):
            for rank, (doc_id, _) in enumerate(ranked, 1):
                fused[doc_id] = fused.get(doc_id, 0) + 1 / (60 + rank)
        ranked_results = [
            RetrievalResult(document=by_id[i], score=s)
            for i, s in sorted(fused.items(), key=lambda p: (-p[1], p[0]))
        ]
        if self.reranker:
            ranked_results = await self.reranker.rerank(query, ranked_results[: max(limit * 4, 20)])
            if any(
                r.document.id not in by_id or r.document != by_id[r.document.id]
                for r in ranked_results
            ):
                raise ValueError("Reranker returned unknown or modified evidence")
        # Pair each primary hit with overlapping other-modality evidence before consuming the budget.
        output: list[RetrievalResult] = []
        seen: set[str] = set()
        for result in ranked_results:
            if result.document.id not in seen:
                output.append(result)
                seen.add(result.document.id)
            if len(output) >= limit:
                break
            if self.temporal_expansion:
                for doc in candidates:
                    if (
                        doc.id not in seen
                        and doc.asset_id == result.document.asset_id
                        and doc.modality != result.document.modality
                        and overlaps(doc, result.document)
                    ):
                        output.append(
                            RetrievalResult(
                                document=doc, score=result.score, reason="temporal_overlap"
                            )
                        )
                        seen.add(doc.id)
                        if len(output) >= limit:
                            break
            if len(output) >= limit:
                break
        return output
