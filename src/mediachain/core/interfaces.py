"""Async dependency-injection contracts. Providers implement these structurally."""

from collections.abc import AsyncIterator
from pathlib import Path
from typing import Any, Protocol, runtime_checkable

from .models import (
    ChatMessage,
    ChatOutput,
    Document,
    EmbeddingSpace,
    ExecutionContext,
    Job,
    MediaAsset,
    ProcessingResult,
    RetrievalFilter,
    RetrievalResult,
    SpeechSegment,
    VectorRecord,
)


@runtime_checkable
class Loader(Protocol):
    async def load(self, source: str, owner_id: str = "local") -> MediaAsset: ...


@runtime_checkable
class Processor(Protocol):
    def fingerprint(self) -> dict[str, Any]: ...
    async def process(self, asset: MediaAsset, context: ExecutionContext) -> ProcessingResult: ...


class ModelProvider(Protocol):
    model_id: str
    model_version: str


@runtime_checkable
class ChatModel(ModelProvider, Protocol):
    async def generate(self, messages: list[ChatMessage]) -> ChatOutput: ...


@runtime_checkable
class VisionModel(ModelProvider, Protocol):
    async def describe(self, image_path: Path, prompt: str) -> str: ...


@runtime_checkable
class SpeechToTextModel(ModelProvider, Protocol):
    async def transcribe(self, audio_path: Path) -> list[SpeechSegment]: ...


@runtime_checkable
class TextToSpeechModel(ModelProvider, Protocol):
    async def synthesize(self, text: str, destination: Path) -> Path: ...


@runtime_checkable
class DiarizationModel(ModelProvider, Protocol):
    async def diarize(self, audio_path: Path) -> list[SpeechSegment]: ...


@runtime_checkable
class EmbeddingModel(Protocol):
    space: EmbeddingSpace

    async def embed(self, texts: list[str]) -> list[list[float]]: ...


class NativeMediaEmbeddingModel(Protocol):
    space: EmbeddingSpace

    async def embed_media(self, paths: list[Path]) -> list[list[float]]: ...


@runtime_checkable
class Reranker(Protocol):
    async def rerank(self, query: str, results: list[RetrievalResult]) -> list[RetrievalResult]: ...


@runtime_checkable
class VectorStore(Protocol):
    async def upsert(self, records: list[VectorRecord], space: EmbeddingSpace) -> None: ...
    async def search(
        self, vector: list[float], space: EmbeddingSpace, document_ids: list[str], limit: int
    ) -> list[tuple[str, float]]: ...
    async def delete_asset(self, asset_id: str, keep_ids: list[str] | None = None) -> None: ...


@runtime_checkable
class DocumentStore(Protocol):
    async def replace_documents(self, asset_id: str, documents: list[Document]) -> None: ...
    async def list_documents(self, filters: RetrievalFilter) -> list[Document]: ...
    async def delete_documents(self, asset_id: str) -> None: ...


@runtime_checkable
class MetadataStore(Protocol):
    async def put_asset(self, asset: MediaAsset) -> None: ...
    async def get_asset(self, asset_id: str) -> MediaAsset | None: ...
    async def list_assets(self, owner_id: str) -> list[MediaAsset]: ...
    async def delete_asset(self, asset_id: str) -> None: ...
    async def put_job(self, job: Job) -> None: ...
    async def get_job(self, job_id: str) -> Job | None: ...
    async def list_jobs(self, owner_id: str) -> list[Job]: ...


@runtime_checkable
class ObjectStore(Protocol):
    async def put(self, key: str, source: Path) -> str: ...
    async def resolve(self, key: str) -> Path: ...
    async def delete(self, key: str) -> None: ...


@runtime_checkable
class Cache(Protocol):
    async def get(self, key: str) -> str | None: ...
    async def set(self, key: str, value: str, ttl: int = 3600) -> None: ...
    async def delete(self, key: str) -> None: ...
    async def delete_prefix(self, prefix: str) -> None: ...


@runtime_checkable
class Retriever(Protocol):
    async def retrieve(
        self, query: str, filters: RetrievalFilter | None = None, limit: int = 8
    ) -> list[RetrievalResult]: ...


@runtime_checkable
class Runnable(Protocol):
    async def ainvoke(self, value: Any, context: ExecutionContext | None = None) -> Any: ...


@runtime_checkable
class Tool(Protocol):
    name: str
    description: str

    async def invoke(self, arguments: dict[str, Any], context: ExecutionContext) -> Any: ...


class Frame(ModelProvider, Protocol):
    path: Path
    timestamp: float


class FrameSampler(Protocol):
    def fingerprint(self) -> dict[str, Any]: ...
    def sample(self, path: Path, destination: Path) -> AsyncIterator[tuple[Path, float]]: ...
