"""Streaming PyAV sampling with bounded memory and configurable policies."""

from __future__ import annotations

import asyncio
from collections.abc import AsyncIterator, Generator
from pathlib import Path
from typing import Any

from mediachain.core.errors import ConfigurationError, ProcessingError


class IntervalSampler:
    def __init__(self, interval: float = 5, max_frames: int = 1000):
        if interval <= 0 or max_frames <= 0:
            raise ValueError("interval and max_frames must be positive")
        self.interval, self.max_frames = interval, max_frames

    def fingerprint(self) -> dict[str, Any]:
        return {"sampler": "interval-v1", "interval": self.interval, "max_frames": self.max_frames}

    def _frames(self, path: Path, destination: Path) -> Generator[tuple[Path, float], None, None]:
        try:
            import av
        except ImportError as exc:
            raise ConfigurationError("Install mediachain[media] for frame sampling") from exc
        next_time, count = 0.0, 0
        with av.open(
            str(path),
            options={"protocol_whitelist": "file,pipe", "format_whitelist": "mov,matroska"},
        ) as container:
            for frame in container.decode(video=0):
                if frame.time is None:
                    continue
                timestamp = float(frame.time)
                if timestamp < next_time:
                    continue
                if count >= self.max_frames:
                    raise ProcessingError(
                        "Frame limit exceeded; increase sampling interval or max_frames"
                    )
                image_path = destination / f"{count:06d}.jpg"
                frame.to_image().save(image_path)
                yield image_path, timestamp
                count += 1
                next_time = timestamp + self.interval

    async def sample(self, path: Path, destination: Path) -> AsyncIterator[tuple[Path, float]]:
        iterator = self._frames(path, destination)
        try:
            while True:
                # Shield one decoder step so cancellation cannot close an executing generator.
                step = asyncio.create_task(asyncio.to_thread(next, iterator, None))
                try:
                    item = await asyncio.shield(step)
                except asyncio.CancelledError:
                    await step
                    raise
                if item is None:
                    break
                yield item
        finally:
            await asyncio.to_thread(iterator.close)


class SceneSampler(IntervalSampler):
    """Sample perceptual scene changes using mean normalized thumbnail differences."""

    def __init__(self, threshold: float = 0.2, min_interval: float = 0.5, max_frames: int = 1000):
        super().__init__(min_interval, max_frames)
        if not 0 < threshold <= 1:
            raise ValueError("threshold must be in (0, 1]")
        self.threshold = threshold

    def fingerprint(self) -> dict[str, Any]:
        return {**super().fingerprint(), "sampler": "scene-v1", "threshold": self.threshold}

    def _frames(self, path: Path, destination: Path) -> Generator[tuple[Path, float], None, None]:
        try:
            import av
            from PIL import ImageChops, ImageStat
        except ImportError as exc:
            raise ConfigurationError("Install mediachain[media] for scene sampling") from exc
        previous = None
        last, count = -self.interval, 0
        with av.open(
            str(path),
            options={"protocol_whitelist": "file,pipe", "format_whitelist": "mov,matroska"},
        ) as container:
            for frame in container.decode(video=0):
                if frame.time is None or float(frame.time) < last + self.interval:
                    continue
                image = frame.to_image()
                thumbnail = image.resize((32, 32)).convert("RGB")
                difference = (
                    1.0
                    if previous is None
                    else sum(ImageStat.Stat(ImageChops.difference(previous, thumbnail)).mean)
                    / (3 * 255)
                )
                previous = thumbnail
                if difference < self.threshold:
                    continue
                if count >= self.max_frames:
                    raise ProcessingError("Scene sampling exceeds max_frames")
                target = destination / f"{count:06d}.jpg"
                image.save(target)
                last = float(frame.time)
                yield target, last
                count += 1
