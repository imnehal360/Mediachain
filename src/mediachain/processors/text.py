"""Text/PDF/HTML extraction and deterministic overlapping character chunks."""

from __future__ import annotations

import asyncio
import re
from html.parser import HTMLParser
from pathlib import Path
from typing import Any

from mediachain.core.config import ProcessingConfig
from mediachain.core.errors import ConfigurationError
from mediachain.core.models import (
    Document,
    ExecutionContext,
    MediaAsset,
    Modality,
    ProcessingResult,
    stable_id,
)


class HTMLText(HTMLParser):
    def __init__(self) -> None:
        super().__init__()
        self.parts: list[str] = []
        self.hidden = 0

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        if tag in ("script", "style"):
            self.hidden += 1

    def handle_endtag(self, tag: str) -> None:
        if tag in ("script", "style"):
            self.hidden = max(0, self.hidden - 1)

    def handle_data(self, data: str) -> None:
        if not self.hidden:
            self.parts.append(data)


class TextProcessor:
    def __init__(self, config: ProcessingConfig | None = None):
        self.config = config or ProcessingConfig()

    def fingerprint(self) -> dict[str, Any]:
        return {
            "processor": "text-v1",
            "chunk_size": self.config.chunk_size,
            "chunk_overlap": self.config.chunk_overlap,
        }

    async def process(self, asset: MediaAsset, context: ExecutionContext) -> ProcessingResult:
        def extract() -> ProcessingResult:
            path = Path(asset.source)
            pages: list[tuple[int | None, str]]
            if path.suffix.lower() == ".pdf":
                try:
                    from pypdf import PdfReader
                except ImportError as exc:
                    raise ConfigurationError("Install mediachain[pdf] for PDF extraction") from exc
                pages = [
                    (i + 1, p.extract_text() or "") for i, p in enumerate(PdfReader(path).pages)
                ]
            else:
                text = path.read_text(encoding="utf-8")
                if path.suffix.lower() in (".html", ".htm"):
                    parser = HTMLText()
                    parser.feed(text)
                    text = "\n".join(parser.parts)
                pages = [(None, text)]
            docs = []
            for page, raw in pages:
                text = re.sub(r"\s+", " ", raw).strip()
                step = self.config.chunk_size - self.config.chunk_overlap
                for start in range(0, len(text), step):
                    content = text[start : start + self.config.chunk_size]
                    docs.append(
                        Document(
                            id=stable_id(asset.id, self.fingerprint(), page, start, content),
                            asset_id=asset.id,
                            source=asset.source,
                            modality=Modality.TEXT,
                            content=content,
                            metadata={
                                "page": page,
                                "offset": start,
                                "processing": self.fingerprint(),
                            },
                        )
                    )
                    if start + self.config.chunk_size >= len(text):
                        break
            return ProcessingResult(
                asset=asset,
                documents=docs,
                warnings=[] if docs else ["No extractable text; scanned PDFs require OCR"],
            )

        return await asyncio.to_thread(extract)
