"""Validated processing limits."""

from typing import Self

from pydantic import Field, model_validator

from .models import Model


class ProcessingConfig(Model):
    chunk_size: int = Field(default=1200, gt=0)
    chunk_overlap: int = Field(default=150, ge=0)
    frame_interval: float = Field(default=5.0, gt=0)
    frame_window: float = Field(default=0.5, ge=0)
    max_frames: int = Field(default=1000, gt=0)
    max_file_bytes: int = Field(default=1024 * 1024 * 1024, gt=0)
    model_timeout: float = Field(default=300, gt=0)
    max_ocr_pages: int = Field(default=200, gt=0)

    @model_validator(mode="after")
    def overlap(self) -> Self:
        if self.chunk_overlap >= self.chunk_size:
            raise ValueError("chunk_overlap must be less than chunk_size")
        return self
