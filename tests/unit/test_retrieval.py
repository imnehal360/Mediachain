import json

import pytest

from mediachain.core.errors import GroundingError
from mediachain.core.models import (
    ChatOutput,
    Document,
    Event,
    ExecutionContext,
    RetrievalFilter,
    VectorRecord,
)
from mediachain.embeddings.local import HashEmbeddings
from mediachain.rag.engine import ContextBuilder, RAGEngine
from mediachain.retrieval.hybrid import HybridRetriever
from mediachain.storage.local import SQLiteStore
from mediachain.storage.vector import MemoryVectorStore
from mediachain.temporal.alignment import align, nearby, overlaps


def doc(id, modality="audio", asset="a", start=120, end=140, text="revenue grew"):
    return Document(
        id=id,
        content=text,
        modality=modality,
        asset_id=asset,
        source=asset + ".mp4",
        start_time=start,
        end_time=end,
    )


def test_temporal_alignment_and_nearby():
    a, b, c = doc("a"), doc("b", "video", start=125, end=150), doc("c", "video", asset="b")
    assert overlaps(a, b)
    assert align([a, b, c]) == [("a", "b")]
    assert overlaps(a, doc("d", start=140, end=140))
    event = Event(id="e", asset_id="a", description="revenue", start_time=150, end_time=160)
    assert nearby([event], "a", 145, 5) == [event]
    assert nearby([event], "b", 145, 5) == []


async def test_filtered_fusion_and_temporal_expansion(tmp_path):
    store, vectors, embeddings = SQLiteStore(tmp_path / "db"), MemoryVectorStore(), HashEmbeddings()
    documents = [
        doc("a"),
        doc("b", "video", start=125, end=125.5, text="blue bar chart"),
        doc("c", asset="b"),
    ]
    await store.replace_documents("a", documents[:2])
    await store.replace_documents("b", documents[2:])
    values = await embeddings.embed([d.content for d in documents])
    await vectors.upsert(
        [
            VectorRecord(document_id=d.id, asset_id=d.asset_id, values=v)
            for d, v in zip(documents, values, strict=True)
        ],
        embeddings.space,
    )
    retriever = HybridRetriever(store, vectors, embeddings)
    result = await retriever.retrieve("revenue", RetrievalFilter(media_ids=["a"]))
    assert [r.document.id for r in result] == ["a", "b"]
    assert result[1].reason == "temporal_overlap"
    assert await retriever.retrieve("revenue", RetrievalFilter(media_ids=[])) == []
    assert await retriever.retrieve("revenue", RetrievalFilter(start_time=200, end_time=220)) == []
    assert (
        len(
            await retriever.retrieve(
                "revenue", RetrievalFilter(modalities=["audio"], media_ids=["a"])
            )
        )
        == 1
    )
    assert await retriever.retrieve("unrelatedzzzz", RetrievalFilter(media_ids=["a"])) == []


async def test_grounded_citations_and_no_evidence():
    from mediachain.core.models import RetrievalResult

    class Retriever:
        async def retrieve(self, query, filters=None, limit=8):
            return [RetrievalResult(document=doc("d"), score=1)] if query else []

    class Model:
        model_id, model_version = "test", "1"
        bad = False

        async def generate(self, messages):
            return ChatOutput(
                content=json.dumps(
                    {"answer": "Revenue grew", "citation_ids": ["fake" if self.bad else "d"]}
                ),
                token_usage=10,
            )

    model = Model()
    engine = RAGEngine(Retriever(), model)
    context = ExecutionContext()
    response = await engine.ask("revenue", context=context)
    assert response.sources[0].start_time == 120
    assert context.token_usage == 10
    model.bad = True
    with pytest.raises(GroundingError):
        await engine.ask("revenue")
    assert (await engine.ask("")).insufficient_evidence
    assert (
        await RAGEngine(Retriever(), model, ContextBuilder(1)).ask("revenue")
    ).insufficient_evidence


async def test_optional_answer_verification():
    from mediachain.core.models import RetrievalResult

    class Retriever:
        async def retrieve(self, query, filters=None, limit=8):
            return [RetrievalResult(document=doc("d"), score=1)]

    class AnswerModel:
        model_id, model_version = "answer", "1"

        async def generate(self, messages):
            return ChatOutput(
                content=json.dumps({"answer": "Revenue grew", "citation_ids": ["d"]}),
                token_usage=3,
            )

    class Verifier:
        model_id, model_version = "verifier", "1"
        supported = True

        async def generate(self, messages):
            return ChatOutput(
                content=json.dumps({"supported": self.supported, "reason": "checked"}),
                token_usage=2,
            )

    verifier = Verifier()
    response = await RAGEngine(Retriever(), AnswerModel(), verifier=verifier).ask("revenue")
    assert response.metadata["verified"] is True
    assert response.token_usage == 5
    verifier.supported = False
    with pytest.raises(GroundingError, match="failed evidence verification"):
        await RAGEngine(Retriever(), AnswerModel(), verifier=verifier).ask("revenue")
