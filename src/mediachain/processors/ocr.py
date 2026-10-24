"""Optional PDF OCR using page rendering plus an injected hosted vision model."""

from __future__ import annotations

import asyncio
from pathlib import Path
from tempfile import TemporaryDirectory

from mediachain.core.interfaces import VisionModel


class VisionPDFOCR:
    def __init__(self, vision: VisionModel, max_pages: int = 200, dpi: int = 160):
        if max_pages <= 0 or dpi <= 0:
            raise ValueError("OCR limits must be positive")
        self.vision = vision
        self.max_pages = max_pages
        self.dpi = dpi
        self.model_id = vision.model_id
        self.model_version = vision.model_version

    async def extract(self, document_path: Path) -> list[str]:
        try:
            import fitz
        except ImportError as exc:
            raise RuntimeError("Install mediachain[ocr] for scanned-PDF OCR") from exc

        document = await asyncio.to_thread(fitz.open, document_path)
        try:
            page_count = min(document.page_count, self.max_pages)
            results: list[str] = []
            with TemporaryDirectory(prefix="mediachain-ocr-") as temp:
                for index in range(page_count):
                    target = Path(temp) / f"page-{index + 1}.png"

                    def render(page_number: int = index, output: Path = target) -> None:
                        page = document.load_page(page_number)
                        pixmap = page.get_pixmap(dpi=self.dpi, alpha=False)
                        pixmap.save(output)

                    await asyncio.to_thread(render)
                    text = await self.vision.describe(
                        target,
                        "Transcribe all visible document text exactly. Return only the text, preserving reading order.",
                    )
                    results.append(text.strip())
            return results
        finally:
            await asyncio.to_thread(document.close)
