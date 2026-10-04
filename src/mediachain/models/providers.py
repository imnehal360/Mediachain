"""Optional real adapters. No models are downloaded at module import time."""

from __future__ import annotations

import asyncio
import base64
from pathlib import Path
from typing import Any

from mediachain.core.models import ChatMessage, ChatOutput, SpeechSegment


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
