"""FFmpeg subprocess lifecycle with bounded execution and cancellation."""

from __future__ import annotations

import asyncio
import json
from pathlib import Path
from typing import Any

from mediachain.core.errors import ConfigurationError, ProcessingError
from mediachain.core.models import MediaAsset, MediaStream, Modality


async def command(*args: str, timeout: float = 300) -> bytes:  # noqa: ASYNC109
    try:
        process = await asyncio.create_subprocess_exec(
            *args, stdout=asyncio.subprocess.PIPE, stderr=asyncio.subprocess.PIPE
        )
    except FileNotFoundError as exc:
        raise ConfigurationError(f"{args[0]} is required; install FFmpeg") from exc
    try:
        async with asyncio.timeout(timeout):
            stdout, _stderr = await process.communicate()
    except BaseException:
        if process.returncode is None:
            process.kill()
        await process.communicate()
        raise
    if process.returncode:
        # FFmpeg diagnostics can include private paths and source content.
        raise ProcessingError(f"{args[0]} failed with exit code {process.returncode}")
    return stdout


async def probe(asset: MediaAsset) -> MediaAsset:
    data: dict[str, Any] = json.loads(
        await command(
            "ffprobe",
            "-v",
            "error",
            "-protocol_whitelist",
            "file,pipe",
            "-format_whitelist",
            "mov,matroska,mp3,wav,flac,ogg,aac",
            "-show_format",
            "-show_streams",
            "-of",
            "json",
            asset.source,
        )
    )
    streams = []
    for s in data.get("streams", []):
        if s["codec_type"] in ("audio", "video"):
            duration = s.get("duration")
            streams.append(
                MediaStream(
                    index=s["index"],
                    modality=Modality(s["codec_type"]),
                    codec=s.get("codec_name"),
                    duration=float(duration) if duration not in (None, "N/A") else None,
                    metadata={
                        k: s[k] for k in ("width", "height", "sample_rate", "start_time") if k in s
                    },
                )
            )
    if not streams or not any(s.modality == asset.media_type for s in streams):
        raise ProcessingError("Container does not contain the expected media stream")
    duration = data.get("format", {}).get("duration")
    return MediaAsset.model_validate(
        {
            **asset.model_dump(),
            "streams": streams,
            "duration": float(duration) if duration not in (None, "N/A") else None,
            "metadata": {
                **asset.metadata,
                "timeline_origin": float(data.get("format", {}).get("start_time", 0)),
            },
        }
    )


def audio_offset(asset: MediaAsset) -> float:
    """First decoded audio sample offset on the original media timeline."""
    stream = next(s for s in asset.streams if s.modality == Modality.AUDIO)
    start = stream.metadata.get("start_time", 0)
    return max(
        0.0, float(start if start != "N/A" else 0) - float(asset.metadata.get("timeline_origin", 0))
    )


async def extract_audio(source: Path, destination: Path) -> Path:
    await command(
        "ffmpeg",
        "-nostdin",
        "-v",
        "error",
        "-y",
        "-protocol_whitelist",
        "file,pipe",
        "-format_whitelist",
        "mov,matroska,mp3,wav,flac,ogg,aac",
        "-i",
        str(source),
        "-map",
        "0:a:0",
        "-vn",
        "-ac",
        "1",
        "-ar",
        "16000",
        "-c:a",
        "pcm_s16le",
        str(destination),
    )
    return destination


async def extract_frame(source: Path, timestamp: float, destination: Path) -> Path:
    if timestamp < 0:
        raise ValueError("timestamp must be nonnegative")
    await command(
        "ffmpeg",
        "-nostdin",
        "-v",
        "error",
        "-y",
        "-ss",
        str(timestamp),
        "-protocol_whitelist",
        "file,pipe",
        "-format_whitelist",
        "mov,matroska",
        "-i",
        str(source),
        "-frames:v",
        "1",
        str(destination),
    )
    if not await asyncio.to_thread(destination.exists):
        raise ProcessingError("No frame at the requested timestamp")
    return destination
