"""Concurrent audio and visual processing with common original-source provenance."""

from __future__ import annotations

import asyncio
from pathlib import Path
from tempfile import TemporaryDirectory
from typing import Any

from mediachain.core.config import ProcessingConfig
from mediachain.core.interfaces import FrameSampler, VisionModel
from mediachain.core.models import (
    Document,
    ExecutionContext,
    MediaAsset,
    Modality,
    ProcessingResult,
    Provenance,
    stable_id,
)
from mediachain.modalities.audio.ffmpeg import extract_audio, probe
from mediachain.modalities.video.sampling import IntervalSampler
from mediachain.observability.tracing import span
from mediachain.processors.audio import AudioProcessor


class VideoProcessor:
    def __init__(
        self,
        vision: VisionModel,
        audio: AudioProcessor | None = None,
        sampler: FrameSampler | None = None,
        config: ProcessingConfig | None = None,
    ):
        self.vision, self.audio = vision, audio
        self.config = config or ProcessingConfig()
        self.sampler = sampler or IntervalSampler(
            self.config.frame_interval, self.config.max_frames
        )

    def fingerprint(self) -> dict[str, Any]:
        return {
            "processor": "video-v4",
            "vision": [self.vision.model_id, self.vision.model_version],
            "audio": self.audio.fingerprint() if self.audio else None,
            "sampler": self.sampler.fingerprint(),
            "window": self.config.frame_window,
        }

    def _sampler_for(self, asset: MediaAsset) -> FrameSampler:
        if type(self.sampler) is not IntervalSampler or asset.duration is None:
            return self.sampler
        interval = max(self.sampler.interval, asset.duration / self.sampler.max_frames)
        return IntervalSampler(interval, self.sampler.max_frames)

    async def process(self, asset: MediaAsset, context: ExecutionContext) -> ProcessingResult:
        asset = await probe(asset)
        warnings: list[str] = []
        with TemporaryDirectory(prefix="mediachain-video-") as temp:
            directory = Path(temp)

            async def speech() -> list[Document]:
                if not any(s.modality == Modality.AUDIO for s in asset.streams):
                    warnings.append("Video has no audio stream")
                    return []
                if self.audio is None:
                    warnings.append("No speech model configured; audio was not transcribed")
                    return []
                path = await extract_audio(Path(asset.source), directory / "audio.wav")
                return await self.audio.transcribe(asset, path, context)

            async def visual() -> list[Document]:
                docs = []
                sampler = self._sampler_for(asset)
                async for path, timestamp in sampler.sample(Path(asset.source), directory):
                    timestamp = max(
                        0.0, timestamp - float(asset.metadata.get("timeline_origin", 0))
                    )
                    if asset.duration is not None and timestamp >= asset.duration:
                        await asyncio.to_thread(path.unlink)
                        continue
                    async with asyncio.timeout(self.config.model_timeout):
                        with span(context, "model.vision"):
                            description = await self.vision.describe(
                                path,
                                "Describe only visible content, including readable text and diagrams.",
                            )
                    end = timestamp + self.config.frame_window
                    if asset.duration is not None:
                        end = min(end, asset.duration)
                    docs.append(
                        Document(
                            id=stable_id(asset.id, self.fingerprint(), timestamp, description),
                            asset_id=asset.id,
                            source=asset.source,
                            modality=Modality.VIDEO,
                            content=description,
                            start_time=timestamp,
                            end_time=end,
                            metadata={
                                "sample_time": timestamp,
                                "sampling": sampler.fingerprint(),
                                "processing": self.fingerprint(),
                                "observation_window": True,
                            },
                            provenance=[
                                Provenance(
                                    model_id=self.vision.model_id,
                                    model_version=self.vision.model_version,
                                    operation="describe",
                                )
                            ],
                        )
                    )
                    await asyncio.to_thread(path.unlink)
                return docs

            async with asyncio.TaskGroup() as group:
                audio_task = group.create_task(speech())
                visual_task = group.create_task(visual())
            return ProcessingResult(
                asset=asset, documents=audio_task.result() + visual_task.result(), warnings=warnings
            )
