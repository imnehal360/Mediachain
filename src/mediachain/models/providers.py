"""Optional real adapters. No models are downloaded at module import time."""

from __future__ import annotations

import asyncio
import base64
import wave
from pathlib import Path
from typing import Any

from mediachain.core.models import ChatMessage, ChatOutput, EmbeddingSpace, SpeechSegment


class FasterWhisperSpeech:
    def __init__(
        self,
        model_id: str = "base",
        model_version: str = "default",
        device: str = "cpu",
        compute_type: str = "int8",
    ):
        self.model_id, self.model_version = model_id, model_version
        self.device, self.compute_type = device, compute_type
        self._model: Any = None
        self._lock = asyncio.Lock()

    async def transcribe(self, audio_path: Path) -> list[SpeechSegment]:
        def run() -> list[SpeechSegment]:
            if self._model is None:
                from faster_whisper import WhisperModel

                self._model = WhisperModel(
                    self.model_id, device=self.device, compute_type=self.compute_type
                )
            segments, _ = self._model.transcribe(str(audio_path), vad_filter=True)
            return [
                SpeechSegment(text=s.text, start_time=s.start, end_time=s.end) for s in segments
            ]

        async with self._lock:
            return await asyncio.to_thread(run)


class HTTPChatModel:
    """Chat-completions protocol adapter for compatible hosted or local servers."""

    def __init__(
        self,
        model_id: str,
        base_url: str,
        api_key: str = "",
        model_version: str = "configured",
        timeout: float = 120,
        max_tokens: int = 2048,
    ):
        self.model_id, self.model_version = model_id, model_version
        self.base_url, self.api_key = base_url.rstrip("/"), api_key
        self.timeout, self.max_tokens = timeout, max_tokens

    async def request(self, messages: list[dict[str, Any]]) -> ChatOutput:
        import httpx

        headers = {"Authorization": f"Bearer {self.api_key}"} if self.api_key else {}
        async with httpx.AsyncClient(timeout=self.timeout) as client:
            response = await client.post(
                self.base_url + "/chat/completions",
                headers=headers,
                json={"model": self.model_id, "messages": messages, "max_tokens": self.max_tokens},
            )
            response.raise_for_status()
            data = response.json()
            return ChatOutput(
                content=data["choices"][0]["message"]["content"],
                token_usage=data.get("usage", {}).get("total_tokens"),
            )

    async def generate(self, messages: list[ChatMessage]) -> ChatOutput:
        return await self.request([m.model_dump() for m in messages])


class HTTPVisionModel(HTTPChatModel):
    async def describe(self, image_path: Path, prompt: str) -> str:
        encoded = base64.b64encode(await asyncio.to_thread(image_path.read_bytes)).decode()
        result = await self.request(
            [
                {
                    "role": "user",
                    "content": [
                        {"type": "text", "text": prompt},
                        {
                            "type": "image_url",
                            "image_url": {"url": "data:image/jpeg;base64," + encoded},
                        },
                    ],
                }
            ]
        )
        return result.content


class HTTPSpeechModel:
    """OpenAI-compatible hosted audio transcription adapter."""

    def __init__(
        self,
        model_id: str,
        base_url: str,
        api_key: str = "",
        model_version: str = "configured",
        timeout: float = 600,
    ):
        self.model_id, self.model_version = model_id, model_version
        self.base_url, self.api_key = base_url.rstrip("/"), api_key
        self.timeout = timeout

    async def transcribe(self, audio_path: Path) -> list[SpeechSegment]:
        import httpx

        headers = {"Authorization": f"Bearer {self.api_key}"} if self.api_key else {}
        content = await asyncio.to_thread(audio_path.read_bytes)
        async with httpx.AsyncClient(timeout=self.timeout) as client:
            response = await client.post(
                self.base_url + "/audio/transcriptions",
                headers=headers,
                data={"model": self.model_id, "response_format": "verbose_json"},
                files={"file": (audio_path.name, content, "audio/wav")},
            )
            response.raise_for_status()
            data = response.json()
        return [
            SpeechSegment(
                text=segment["text"],
                start_time=float(segment["start"]),
                end_time=float(segment["end"]),
            )
            for segment in data.get("segments", [])
        ]


class HuggingFaceSpeech:
    """Timestamped ASR through Hugging Face Inference Providers."""

    def __init__(
        self,
        model_id: str,
        api_key: str,
        *,
        provider: str = "auto",
        model_version: str = "configured",
        timeout: float = 600,
        client: Any = None,
    ):
        self.model_id, self.model_version = model_id, model_version
        if client is None:
            from huggingface_hub import AsyncInferenceClient

            client = AsyncInferenceClient(provider=provider, token=api_key, timeout=timeout)
        self.client = client

    @staticmethod
    async def _duration(audio_path: Path) -> float:
        def read() -> float:
            with wave.open(str(audio_path), "rb") as audio:
                return audio.getnframes() / audio.getframerate()

        return await asyncio.to_thread(read)

    async def transcribe(self, audio_path: Path) -> list[SpeechSegment]:
        result = await self.client.automatic_speech_recognition(
            audio_path,
            model=self.model_id,
            extra_body={"return_timestamps": True},
        )
        chunks = result.chunks or []
        duration: float | None = None
        segments = []
        for chunk in chunks:
            start, end = chunk.timestamp
            if end is None:
                duration = duration or await self._duration(audio_path)
                end = duration
            segments.append(
                SpeechSegment(
                    text=chunk.text,
                    start_time=max(0.0, float(start or 0)),
                    end_time=max(0.0, float(end)),
                )
            )
        if not segments and result.text.strip():
            duration = duration or await self._duration(audio_path)
            segments.append(
                SpeechSegment(text=result.text, start_time=0.0, end_time=max(0.0, duration))
            )
        return segments


class HTTPDiarizationModel:
    """Hosted diarization adapter using a simple multipart JSON-segment contract."""

    def __init__(
        self,
        model_id: str,
        base_url: str,
        api_key: str = "",
        model_version: str = "configured",
        timeout: float = 600,
    ):
        self.model_id, self.model_version = model_id, model_version
        self.base_url, self.api_key = base_url.rstrip("/"), api_key
        self.timeout = timeout

    async def diarize(self, audio_path: Path) -> list[SpeechSegment]:
        import httpx

        headers = {"Authorization": f"Bearer {self.api_key}"} if self.api_key else {}
        content = await asyncio.to_thread(audio_path.read_bytes)
        async with httpx.AsyncClient(timeout=self.timeout) as client:
            response = await client.post(
                self.base_url + "/audio/diarizations",
                headers=headers,
                data={"model": self.model_id},
                files={"file": (audio_path.name, content, "audio/wav")},
            )
            response.raise_for_status()
            data = response.json()
        return [
            SpeechSegment(
                text=segment.get("text", ""),
                speaker=str(segment["speaker"]),
                start_time=float(segment["start"]),
                end_time=float(segment["end"]),
            )
            for segment in data.get("segments", [])
        ]


class HTTPEmbeddingModel:
    """OpenAI-compatible hosted text embedding adapter."""

    def __init__(
        self,
        model_id: str,
        base_url: str,
        dimensions: int,
        api_key: str = "",
        model_version: str = "configured",
        timeout: float = 120,
    ):
        self.space = EmbeddingSpace(
            model_id=model_id,
            model_version=model_version,
            dimensions=dimensions,
        )
        self.base_url, self.api_key = base_url.rstrip("/"), api_key
        self.timeout = timeout

    async def embed(self, texts: list[str]) -> list[list[float]]:
        import httpx

        headers = {"Authorization": f"Bearer {self.api_key}"} if self.api_key else {}
        async with httpx.AsyncClient(timeout=self.timeout) as client:
            response = await client.post(
                self.base_url + "/embeddings",
                headers=headers,
                json={"model": self.space.model_id, "input": texts},
            )
            response.raise_for_status()
            rows = sorted(response.json()["data"], key=lambda row: row["index"])
        return [[float(value) for value in row["embedding"]] for row in rows]


class HuggingFaceEmbeddingModel:
    """Hosted feature-extraction embeddings through Hugging Face Inference Providers."""

    def __init__(
        self,
        model_id: str,
        api_key: str,
        dimensions: int,
        *,
        provider: str = "hf-inference",
        model_version: str = "configured",
        timeout: float = 120,
        client: Any = None,
    ):
        self.space = EmbeddingSpace(
            model_id=model_id,
            model_version=model_version,
            dimensions=dimensions,
        )
        if client is None:
            from huggingface_hub import AsyncInferenceClient

            client = AsyncInferenceClient(provider=provider, token=api_key, timeout=timeout)
        self.client = client

    async def embed(self, texts: list[str]) -> list[list[float]]:
        if not texts:
            return []
        result = await self.client.feature_extraction(
            texts,
            model=self.space.model_id,
            normalize=True,
            truncate=True,
        )
        rows: list[list[float]] = result.tolist()
        if rows and isinstance(rows[0], (int, float)):
            rows = [rows]  # type: ignore[list-item]
        vectors = [[float(value) for value in row] for row in rows]
        if len(vectors) != len(texts):
            raise ValueError("Hugging Face returned the wrong number of embeddings")
        if any(len(vector) != self.space.dimensions for vector in vectors):
            raise ValueError("Configured dimensions do not match Hugging Face model output")
        return vectors


class SentenceTransformerReranker:
    def __init__(self, model_id: str = "cross-encoder/ms-marco-MiniLM-L-6-v2"):
        self.model_id = model_id
        self._model: Any = None

    async def rerank(self, query: str, results: list[Any]) -> list[Any]:
        if not results:
            return []

        def run() -> list[Any]:
            if self._model is None:
                from sentence_transformers import CrossEncoder

                self._model = CrossEncoder(self.model_id)
            scores = self._model.predict([(query, r.document.content) for r in results])
            return sorted(
                [
                    r.model_copy(update={"score": float(s)})
                    for r, s in zip(results, scores, strict=True)
                ],
                key=lambda r: -r.score,
            )

        return await asyncio.to_thread(run)
