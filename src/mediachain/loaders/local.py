"""Bounded local file inspection. Loading does not run model inference."""

from __future__ import annotations

import asyncio
import hashlib
from pathlib import Path

from mediachain.core.errors import UnsupportedMediaError
from mediachain.core.models import MediaAsset, Modality, stable_id

FORMATS = {
    ".txt": Modality.TEXT,
    ".md": Modality.TEXT,
    ".pdf": Modality.TEXT,
    ".html": Modality.TEXT,
    ".htm": Modality.TEXT,
    ".wav": Modality.AUDIO,
    ".mp3": Modality.AUDIO,
    ".m4a": Modality.AUDIO,
    ".flac": Modality.AUDIO,
    ".ogg": Modality.AUDIO,
    ".mp4": Modality.VIDEO,
    ".mov": Modality.VIDEO,
    ".mkv": Modality.VIDEO,
    ".webm": Modality.VIDEO,
}


class LocalLoader:
    """Stream-hash supported files; do not read an entire media asset into memory."""

    def __init__(self, max_bytes: int = 1024**3):
        self.max_bytes = max_bytes

    async def load(self, source: str, owner_id: str = "local") -> MediaAsset:
        def inspect() -> MediaAsset:
            path = Path(source).resolve(strict=True)
            modality = FORMATS.get(path.suffix.lower())
            if modality is None or not path.is_file():
                raise UnsupportedMediaError("Unsupported file type or non-regular file")
            digest = hashlib.sha256()
            size = 0
            with path.open("rb") as stream:
                while block := stream.read(1024 * 1024):
                    size += len(block)
                    if size > self.max_bytes:
                        raise UnsupportedMediaError("Media exceeds configured file-size limit")
                    digest.update(block)
            if size == 0:
                raise UnsupportedMediaError("Empty media file")
            return MediaAsset(
                id=stable_id(owner_id, digest.hexdigest(), path.suffix.lower()),
                source=str(path),
                media_type=modality,
                content_hash=digest.hexdigest(),
                owner_id=owner_id,
                metadata={"size_bytes": size, "suffix": path.suffix.lower()},
            )

        return await asyncio.to_thread(inspect)
