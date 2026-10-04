"""Explicit plugin registration with API-version and structural contract checks."""

from __future__ import annotations

from typing import Any

from mediachain.core import interfaces as contracts
from mediachain.core.errors import ConfigurationError

CONTRACTS = {
    "loader": contracts.Loader,
    "processor": contracts.Processor,
    "chat": contracts.ChatModel,
    "speech": contracts.SpeechToTextModel,
    "vision": contracts.VisionModel,
    "tts": contracts.TextToSpeechModel,
    "embeddings": contracts.EmbeddingModel,
    "reranker": contracts.Reranker,
    "retriever": contracts.Retriever,
    "vector_store": contracts.VectorStore,
    "document_store": contracts.DocumentStore,
    "metadata_store": contracts.MetadataStore,
    "object_store": contracts.ObjectStore,
    "cache": contracts.Cache,
    "tool": contracts.Tool,
}


class PluginRegistry:
    api_version = "1"

    def __init__(self) -> None:
        self._plugins: dict[tuple[str, str], Any] = {}

    def register(self, kind: str, name: str, plugin: Any, api_version: str = "1") -> None:
        if api_version != self.api_version:
            raise ConfigurationError("Incompatible plugin API version")
        if kind not in CONTRACTS or not isinstance(plugin, CONTRACTS[kind]):
            raise ConfigurationError(f"Plugin does not satisfy {kind!r} contract")
        if (kind, name) in self._plugins:
            raise ConfigurationError("Plugin name already registered")
        self._plugins[kind, name] = plugin

    def get(self, kind: str, name: str) -> Any:
        try:
            return self._plugins[kind, name]
        except KeyError as exc:
            raise ConfigurationError(f"Unknown plugin: {kind}/{name}") from exc
