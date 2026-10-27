"""Restricted single-video YouTube downloads for local ingestion."""

from __future__ import annotations

import asyncio
import re
import shutil
from dataclasses import dataclass
from pathlib import Path
from typing import Any
from urllib.parse import parse_qs, urlparse

from mediachain.core.errors import ConfigurationError, RemoteMediaError

YOUTUBE_HOSTS = {
    "youtube.com",
    "www.youtube.com",
    "m.youtube.com",
    "music.youtube.com",
    "youtu.be",
}
VIDEO_SUFFIXES = {".mp4", ".webm", ".mkv", ".mov"}


@dataclass(frozen=True)
class DownloadedMedia:
    path: Path
    title: str
    webpage_url: str
    duration: float | None


def validate_youtube_url(value: str) -> str:
    url = value.strip()
    if len(url) > 2048:
        raise RemoteMediaError("YouTube URL is too long")
    parsed = urlparse(url)
    host = (parsed.hostname or "").lower().rstrip(".")
    if parsed.scheme != "https" or host not in YOUTUBE_HOSTS:
        raise RemoteMediaError("Only HTTPS YouTube video URLs are supported")
    try:
        port = parsed.port
    except ValueError as exc:
        raise RemoteMediaError("Invalid YouTube URL") from exc
    if parsed.username or parsed.password or port not in (None, 443):
        raise RemoteMediaError("Invalid YouTube URL")
    parts = [part for part in parsed.path.split("/") if part]
    if host == "youtu.be":
        has_video = bool(parts)
    else:
        has_video = bool(parse_qs(parsed.query).get("v")) or (
            len(parts) >= 2 and parts[0] in {"embed", "live", "shorts"}
        )
    if not has_video:
        raise RemoteMediaError("Paste one YouTube video URL, not a channel or playlist")
    return url


def _safe_title(value: Any) -> str:
    title = re.sub(r"[\x00-\x1f\\/:*?\"<>|]+", " ", str(value or "YouTube video"))
    return re.sub(r"\s+", " ", title).strip()[:180] or "YouTube video"


def _download(
    url: str,
    destination: Path,
    max_bytes: int,
    max_duration_seconds: float,
) -> DownloadedMedia:
    destination.mkdir(parents=True, exist_ok=True)
    try:
        import yt_dlp
        from yt_dlp.utils import DownloadError
    except ImportError as exc:
        raise ConfigurationError("Install the youtube extra to import YouTube media") from exc

    node = shutil.which("node")
    ffmpeg = shutil.which("ffmpeg")
    if not node:
        raise ConfigurationError("Node.js is required for YouTube imports")
    if not ffmpeg:
        raise ConfigurationError("FFmpeg is required for YouTube imports")

    def match_filter(info: dict[str, Any], *, incomplete: bool) -> str | None:
        if info.get("is_live") or info.get("live_status") in {"is_live", "is_upcoming"}:
            return "Live and upcoming videos are not supported"
        duration = info.get("duration")
        if not incomplete and duration is not None and float(duration) > max_duration_seconds:
            return "Video exceeds the configured duration limit"
        return None

    options: dict[str, Any] = {
        "allowed_extractors": ["youtube"],
        "cachedir": False,
        "check_formats": "selected",
        "ffmpeg_location": str(Path(ffmpeg).parent),
        "format": "bv*[height<=480]+ba/b[height<=480]/b",
        "js_runtimes": {"node": {"path": node}},
        "match_filter": match_filter,
        "max_filesize": max_bytes,
        "merge_output_format": "mp4",
        "noplaylist": True,
        "noprogress": True,
        "outtmpl": str(destination / "download.%(ext)s"),
        "overwrites": True,
        "quiet": True,
        "remote_components": [],
        "socket_timeout": 30,
        "windowsfilenames": True,
    }
    try:
        with yt_dlp.YoutubeDL(options) as downloader:
            info = downloader.extract_info(url, download=True)
    except DownloadError as exc:
        raise RemoteMediaError("YouTube could not download this video") from exc
    candidates = [
        path
        for path in destination.iterdir()
        if path.is_file() and path.suffix.lower() in VIDEO_SUFFIXES
    ]
    if not candidates:
        raise RemoteMediaError("YouTube did not provide a supported video file")
    path = max(candidates, key=lambda item: item.stat().st_size)
    if path.stat().st_size > max_bytes:
        raise RemoteMediaError("Downloaded video exceeds the configured size limit")
    duration = info.get("duration") if isinstance(info, dict) else None
    return DownloadedMedia(
        path=path,
        title=_safe_title(info.get("title") if isinstance(info, dict) else None),
        webpage_url=str((info.get("webpage_url") if isinstance(info, dict) else None) or url),
        duration=float(duration) if duration is not None else None,
    )


async def download_youtube(
    url: str,
    destination: Path,
    max_bytes: int,
    max_duration_seconds: float,
) -> DownloadedMedia:
    """Download one validated public YouTube video without playlists or live streams."""
    validated = validate_youtube_url(url)
    return await asyncio.to_thread(
        _download,
        validated,
        destination,
        max_bytes,
        max_duration_seconds,
    )
