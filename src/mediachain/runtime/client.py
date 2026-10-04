"""Public SDK: ingest, process, index, retrieve, ask and delete unified media."""

from __future__ import annotations

import asyncio
import json
from pathlib import Path
from typing import Any

from mediachain.core.config import ProcessingConfig
from mediachain.core.errors import ConfigurationError
from mediachain.core.interfaces import (
    Cache,
    ChatModel,
    DocumentStore,
    EmbeddingModel,
    Loader,
    MetadataStore,
    ObjectStore,
    Processor,
    SpeechToTextModel,
    VectorStore,
    VisionModel,
)
from mediachain.core.models import (
    ExecutionContext,
    MediaAsset,
    Modality,
    ModelResponse,
    ProcessingResult,
    RetrievalFilter,
    VectorRecord,
    stable_id,
)
from mediachain.embeddings.local import HashEmbeddings
from mediachain.loaders.local import LocalLoader
from mediachain.observability.tracing import span
from mediachain.processors.audio import AudioProcessor
from mediachain.processors.text import TextProcessor
from mediachain.processors.video import VideoProcessor
from mediachain.rag.engine import RAGEngine
from mediachain.retrieval.hybrid import HybridRetriever
from mediachain.storage.cache import MemoryCache
from mediachain.storage.local import FileObjectStore, SQLiteStore
from mediachain.storage.vector import MemoryVectorStore, validate_vector


class MediaChain:
    """Orchestrate media ingestion, indexing, retrieval, and grounded responses.

    Providers and storage adapters are injected through the constructor. With no
    optional providers configured, the client offers a credential-free local text
    workflow backed by SQLite, filesystem objects, lexical hash embeddings, and an
    extractive evidence response.

    Args:
        llm: Optional chat model used to generate grounded answers.
        speech: Optional speech-to-text provider for audio and video.
        vision: Optional vision provider for video frames.
        embeddings: Embedding provider. Defaults to deterministic hash embeddings.
        vector_store: Vector index. Defaults to an in-memory index.
        document_store: Persistent document store. Defaults to local SQLite.
        metadata_store: Persistent media metadata store. Defaults to local SQLite.
        object_store: Storage for managed source files. Defaults to the local filesystem.
        cache: Processing and embedding cache. Defaults to an in-memory cache.
        loader: Source loader. Defaults to trusted local paths only.
        config: Processing limits and sampling configuration.
        data_dir: Directory used by default local storage adapters.
    """

    def __init__(
        self,
        *,
        llm: ChatModel | None = None,
        speech: SpeechToTextModel | None = None,
        vision: VisionModel | None = None,
        embeddings: EmbeddingModel | None = None,
        vector_store: VectorStore | None = None,
        document_store: DocumentStore | None = None,
        metadata_store: MetadataStore | None = None,
        object_store: ObjectStore | None = None,
        cache: Cache | None = None,
        loader: Loader | None = None,
        config: ProcessingConfig | None = None,
        data_dir: str | Path = ".mediachain",
    ):
        self.config = config or ProcessingConfig()
        root = Path(data_dir)
        local = (
            SQLiteStore(root / "metadata.sqlite")
            if document_store is None or metadata_store is None
            else None
        )
        self.documents: DocumentStore = document_store or local  # type: ignore[assignment]
        self.metadata: MetadataStore = metadata_store or local  # type: ignore[assignment]
        self.objects = object_store or FileObjectStore(root / "objects")
        self.embeddings = embeddings or HashEmbeddings()
        self.vectors = vector_store or MemoryVectorStore()
        self.cache = cache or MemoryCache()
        self.loader = loader or LocalLoader(self.config.max_file_bytes)
        self.processors: dict[Modality, Processor] = {Modality.TEXT: TextProcessor(self.config)}
        audio = AudioProcessor(speech, timeout=self.config.model_timeout) if speech else None
        if audio:
            self.processors[Modality.AUDIO] = audio
        if vision:
            self.processors[Modality.VIDEO] = VideoProcessor(vision, audio, config=self.config)
        self.retriever = HybridRetriever(self.documents, self.vectors, self.embeddings)
        self.rag = RAGEngine(self.retriever, llm)
        self._locks: dict[str, asyncio.Lock] = {}
        self._ready: set[str] = set()

    def _lock(self, asset_id: str) -> asyncio.Lock:
        return self._locks.setdefault(asset_id, asyncio.Lock())

    def register_processor(self, modality: Modality, processor: Processor) -> None:
        """Register or replace the processor for a media modality."""
        if not isinstance(processor, Processor):
            raise ConfigurationError("Processor does not satisfy the Processor protocol")
        self.processors[modality] = processor

    def register_loader(self, loader: Loader) -> None:
        """Replace the source loader used by future ingestion operations."""
        if not isinstance(loader, Loader):
            raise ConfigurationError("Loader does not satisfy the Loader protocol")
        self.loader = loader

    async def load(self, source: str, owner_id: str = "local") -> MediaAsset:
        """Copy a source into managed storage without processing or indexing it."""
        asset = await self.loader.load(source, owner_id)
        async with self._lock(asset.id):
            existing = await self.metadata.get_asset(asset.id)
            if existing:
                return existing
            key = f"{asset.id}/original{asset.metadata.get('suffix', Path(source).suffix)}"
            stored = await self.objects.put(key, Path(asset.source))
            asset = asset.model_copy(
                update={
                    "source": stored,
                    "metadata": {
                        **asset.metadata,
                        "object_key": key,
                        "original_name": Path(source).name,
                    },
                }
            )
            await self.metadata.put_asset(asset)
            return asset

    async def add(
        self, source: str, owner_id: str = "local", context: ExecutionContext | None = None
    ) -> MediaAsset:
        """Load, process, and index a source, returning the managed media asset."""
        asset = await self.load(source, owner_id)
        result = await self.process(asset.id, context)
        return result.asset

    async def _index(self, documents: list[Any], owner_id: str) -> None:
        for start in range(0, len(documents), 64):
            batch = documents[start : start + 64]
            vectors: list[list[float]] = []
            missing: list[int] = []
            keys = [
                "asset:"
                + d.asset_id
                + ":"
                + stable_id("embedding", owner_id, d.content, self.embeddings.space.key)
                for d in batch
            ]
            for i, key in enumerate(keys):
                cached = await self.cache.get(key)
                vectors.append(json.loads(cached) if cached else [])
                if cached is None:
                    missing.append(i)
            if missing:
                generated = await self.embeddings.embed([batch[i].content for i in missing])
                if len(generated) != len(missing):
                    raise ValueError("Embedding provider returned the wrong number of vectors")
                for i, vector in zip(missing, generated, strict=True):
                    validate_vector(vector, self.embeddings.space)
                    vectors[i] = vector
                    await self.cache.set(keys[i], json.dumps(vector))
            await self.vectors.upsert(
                [
                    VectorRecord(document_id=d.id, asset_id=d.asset_id, values=v)
                    for d, v in zip(batch, vectors, strict=True)
                ],
                self.embeddings.space,
            )

    async def process(
        self, asset_id: str, context: ExecutionContext | None = None
    ) -> ProcessingResult:
        """Process and atomically commit a previously loaded media asset."""
        async with self._lock(asset_id):
            asset = await self.metadata.get_asset(asset_id)
            if asset is None:
                raise KeyError(asset_id)
            processor = self.processors.get(asset.media_type)
            if processor is None:
                raise ConfigurationError(
                    f"Configure a {asset.media_type} processor and its model providers"
                )
            ctx = context or ExecutionContext(owner_id=asset.owner_id)
            key = (
                "asset:"
                + asset.id
                + ":"
                + stable_id("process-v1", asset.content_hash, processor.fingerprint())
            )
            cached = await self.cache.get(key)
            with span(ctx, "process"):
                result = (
                    ProcessingResult.model_validate_json(cached)
                    if cached
                    else await processor.process(asset, ctx)
                )
            with span(ctx, "index"):
                await self._index(result.documents, asset.owner_id)
                # Atomic committed document generation, after every vector has been staged.
                await self.documents.replace_documents(asset.id, result.documents)
                await self.metadata.put_asset(result.asset)
                await self.vectors.delete_asset(asset.id, [d.id for d in result.documents])
                await self.cache.set(key, result.model_dump_json())
                self._ready.add(asset.id)
            return result

    async def _restore_vectors(self, assets: list[MediaAsset]) -> None:
        if not isinstance(self.vectors, MemoryVectorStore):
            return
        for asset in assets:
            async with self._lock(asset.id):
                if asset.id not in self._ready:
                    docs = await self.documents.list_documents(
                        RetrievalFilter(media_ids=[asset.id])
                    )
                    await self._index(docs, asset.owner_id)
                    self._ready.add(asset.id)

    async def ask(
        self,
        query: str,
        media_ids: list[str] | None = None,
        *,
        owner_id: str = "local",
        filters: RetrievalFilter | None = None,
        context: ExecutionContext | None = None,
    ) -> ModelResponse:
        """Answer a question using retrieved evidence from authorized media.

        When no chat model is configured, the response contains a deterministic
        extractive view of the retrieved evidence rather than generated text.
        """
        assets = await self.metadata.list_assets(owner_id)
        allowed = {a.id for a in assets}
        selected = (
            media_ids
            if media_ids is not None
            else (
                filters.media_ids if filters and filters.media_ids is not None else sorted(allowed)
            )
        )
        if any(i not in allowed for i in selected):
            raise KeyError("Unknown media")
        if filters and filters.media_ids is not None:
            selected = [i for i in selected if i in filters.media_ids]
        await self._restore_vectors([a for a in assets if a.id in selected])
        scoped = (filters or RetrievalFilter()).model_copy(update={"media_ids": selected})
        async with asyncio.timeout(self.config.model_timeout):
            return await self.rag.ask(query, scoped, context)

    async def summarize(
        self,
        media_ids: list[str] | None = None,
        *,
        owner_id: str = "local",
        filters: RetrievalFilter | None = None,
        focus: str | None = None,
        context: ExecutionContext | None = None,
    ) -> ModelResponse:
        """Summarize selected media from retrieved, cited evidence.

        This uses the same grounding rules as ``ask``: the response is either an
        extractive evidence view or a model answer with validated source citations.
        """
        question = "Summarize the available evidence"
        if focus and focus.strip():
            question += " about " + focus.strip()
        return await self.ask(
            question,
            media_ids,
            owner_id=owner_id,
            filters=filters,
            context=context,
        )

    async def delete(self, asset_id: str) -> None:
        """Delete an asset and its documents, vectors, cache entries, and managed file."""
        async with self._lock(asset_id):
            asset = await self.metadata.get_asset(asset_id)
            if asset is None:
                return
            await self.vectors.delete_asset(asset_id)
            await self.cache.delete_prefix("asset:" + asset_id + ":")
            await self.documents.delete_documents(asset_id)
            if key := asset.metadata.get("object_key"):
                await self.objects.delete(key)
            await self.metadata.delete_asset(asset_id)
            self._ready.discard(asset_id)

    def add_sync(self, source: str, owner_id: str = "local") -> MediaAsset:
        """Synchronous wrapper for :meth:`add` outside a running event loop."""
        self._check_sync()
        return asyncio.run(self.add(source, owner_id))

    def ask_sync(
        self, query: str, media_ids: list[str] | None = None, *, owner_id: str = "local"
    ) -> ModelResponse:
        """Synchronous wrapper for :meth:`ask` outside a running event loop."""
        self._check_sync()
        return asyncio.run(self.ask(query, media_ids, owner_id=owner_id))

    def summarize_sync(
        self,
        media_ids: list[str] | None = None,
        *,
        owner_id: str = "local",
        filters: RetrievalFilter | None = None,
        focus: str | None = None,
    ) -> ModelResponse:
        """Synchronous wrapper for :meth:`summarize` outside a running event loop."""
        self._check_sync()
        return asyncio.run(
            self.summarize(media_ids, owner_id=owner_id, filters=filters, focus=focus)
        )

    @staticmethod
    def _check_sync() -> None:
        try:
            asyncio.get_running_loop()
        except RuntimeError:
            return
        raise RuntimeError("Use await in a running event loop")
