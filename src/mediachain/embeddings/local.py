"""Offline lexical baseline and a real Sentence Transformers adapter."""

from __future__ import annotations

import asyncio
import hashlib
import math
import re
from typing import Any

from mediachain.core.models import EmbeddingSpace


def tokens(text: str) -> list[str]:
    return re.findall(r"\w+", text.casefold())


class HashEmbeddings:
    """Deterministic bag-of-words feature hashing; not semantic model inference."""

    def __init__(self, dimensions: int = 256):
        self.space = EmbeddingSpace(
            model_id="lexical-hash", model_version="1", dimensions=dimensions
        )

    async def embed(self, texts: list[str]) -> list[list[float]]:
        def encode() -> list[list[float]]:
            vectors = []
            for text in texts:
                vector = [0.0] * self.space.dimensions
                for token in tokens(text):
                    value = int.from_bytes(hashlib.sha256(token.encode()).digest()[:8], "big")
                    vector[value % self.space.dimensions] += 1
                norm = math.sqrt(sum(v * v for v in vector)) or 1
                vectors.append([v / norm for v in vector])
            return vectors

        return await asyncio.to_thread(encode)


class SentenceTransformerEmbeddings:
    def __init__(
        self,
        model_id: str = "sentence-transformers/all-MiniLM-L6-v2",
        revision: str = "main",
        dimensions: int = 384,
        batch_size: int = 32,
    ):
        self.space = EmbeddingSpace(
            model_id=model_id, model_version=revision, dimensions=dimensions
        )
        self.batch_size = batch_size
        self._model: Any = None
        self._lock = asyncio.Lock()

    async def embed(self, texts: list[str]) -> list[list[float]]:
        def encode() -> list[list[float]]:
            if self._model is None:
                from sentence_transformers import SentenceTransformer

                self._model = SentenceTransformer(
                    self.space.model_id, revision=self.space.model_version
                )
            values: list[list[float]] = self._model.encode(
                texts, batch_size=self.batch_size, normalize_embeddings=True
            ).tolist()
            if any(len(v) != self.space.dimensions for v in values):
                raise ValueError("Configured dimensions do not match model output")
            return values

        async with self._lock:
            return await asyncio.to_thread(encode)
