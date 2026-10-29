"""Shared speech path used by both audio and video assets."""

from __future__ import annotations

import asyncio
from pathlib import Path
from tempfile import TemporaryDirectory
from typing import Any

from mediachain.core.interfaces import DiarizationModel, SpeechToTextModel
from mediachain.core.models import (
    Document,
    ExecutionContext,
    MediaAsset,
    Modality,
    ProcessingResult,
    Provenance,
    stable_id,
)
from mediachain.modalities.audio.ffmpeg import audio_offset, extract_audio, probe
from mediachain.observability.tracing import span


class AudioProcessor:
    def __init__(
        self,
        speech: SpeechToTextModel,
        diarization: DiarizationModel | None = None,
        timeout: float = 300,
    ):
        self.speech, self.diarization, self.timeout = speech, diarization, timeout

    def fingerprint(self) -> dict[str, Any]:
        return {
            "processor": "audio-v3",
            "speech": [self.speech.model_id, self.speech.model_version],
            "diarization": [self.diarization.model_id, self.diarization.model_version]
            if self.diarization
            else None,
        }

    async def transcribe(
        self, asset: MediaAsset, audio_path: Path, context: ExecutionContext
    ) -> list[Document]:
        async with asyncio.timeout(self.timeout):
            with span(context, "model.transcribe"):
                segments = await self.speech.transcribe(audio_path)
            speakers = await self.diarization.diarize(audio_path) if self.diarization else []
        docs = []
        offset = audio_offset(asset) if asset.streams else 0
        for segment in segments:
            start = segment.start_time + offset
            end = segment.end_time + offset
            # Speech models can estimate an ending beyond the final audio sample.
            # Keep citations on the original media timeline and drop out-of-range speech.
            if asset.duration is not None:
                if start >= asset.duration:
                    continue
                end = min(end, asset.duration)
            speaker = segment.speaker
            matches = [
                (
                    max(
                        0, min(segment.end_time, s.end_time) - max(segment.start_time, s.start_time)
                    ),
                    s.speaker,
                )
                for s in speakers
            ]
            if matches:
                best = max(matches, key=lambda pair: pair[0])
                if best[0] > 0:
                    speaker = best[1]
            if not segment.text.strip():
                continue
            provenance = [
                Provenance(
                    model_id=self.speech.model_id,
                    model_version=self.speech.model_version,
                    operation="transcribe",
                )
            ]
            if self.diarization:
                provenance.append(
                    Provenance(
                        model_id=self.diarization.model_id,
                        model_version=self.diarization.model_version,
                        operation="diarize",
                    )
                )
            docs.append(
                Document(
                    id=stable_id(asset.id, self.fingerprint(), segment.model_dump()),
                    asset_id=asset.id,
                    source=asset.source,
                    modality=Modality.AUDIO,
                    content=segment.text,
                    start_time=start,
                    end_time=end,
                    metadata={"speaker": speaker, "processing": self.fingerprint()},
                    provenance=provenance,
                )
            )
        return docs

    async def process(self, asset: MediaAsset, context: ExecutionContext) -> ProcessingResult:
        asset = await probe(asset)
        with TemporaryDirectory(prefix="mediachain-audio-") as temp:
            audio = await extract_audio(Path(asset.source), Path(temp) / "audio.wav")
            docs = await self.transcribe(asset, audio, context)
        return ProcessingResult(asset=asset, documents=docs)
