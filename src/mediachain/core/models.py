"""Serializable domain objects shared by every modality and adapter."""

from __future__ import annotations

import hashlib
import json
import time
from enum import StrEnum
from typing import Any, Self
from uuid import uuid4

from pydantic import BaseModel, ConfigDict, Field, model_validator


def stable_id(*parts: Any) -> str:
    """Hash a canonical JSON identity, independently of Python hash randomization."""
    return hashlib.sha256(
        json.dumps(parts, sort_keys=True, separators=(",", ":"), default=str).encode()
    ).hexdigest()


class Model(BaseModel):
    model_config = ConfigDict(extra="forbid", validate_assignment=True, allow_inf_nan=False)


class Modality(StrEnum):
    TEXT = "text"
    AUDIO = "audio"
    VIDEO = "video"


class Interval(Model):
    start_time: float | None = Field(default=None, ge=0)
    end_time: float | None = Field(default=None, ge=0)

    @model_validator(mode="after")
    def boundaries(self) -> Self:
        if (self.start_time is None) != (self.end_time is None):
            raise ValueError("Both timestamp boundaries must be present or absent")
        if self.start_time is not None and self.end_time is not None:
            if self.end_time < self.start_time:
                raise ValueError("end_time must be >= start_time")
        return self


class Provenance(Model):
    model_id: str
    model_version: str
    operation: str


class MediaStream(Model):
    index: int = Field(ge=0)
    modality: Modality
    codec: str | None = None
    duration: float | None = Field(default=None, ge=0)
    metadata: dict[str, Any] = Field(default_factory=dict)


class MediaAsset(Model):
    id: str
    source: str
    media_type: Modality
    content_hash: str
    owner_id: str = "local"
    duration: float | None = Field(default=None, ge=0)
    streams: list[MediaStream] = Field(default_factory=list)
    metadata: dict[str, Any] = Field(default_factory=dict)


class MediaSegment(Interval):
    id: str
    asset_id: str
    modality: Modality
    content: str | None = None
    metadata: dict[str, Any] = Field(default_factory=dict)


class SourceReference(Interval):
    media_id: str
    document_id: str
    source: str
    modality: Modality


class Document(Interval):
    id: str
    content: str
    modality: Modality
    asset_id: str
    source: str
    segment_id: str | None = None
    metadata: dict[str, Any] = Field(default_factory=dict)
    provenance: list[Provenance] = Field(default_factory=list)

    def reference(self) -> SourceReference:
        return SourceReference(
            media_id=self.asset_id,
            document_id=self.id,
            source=self.source,
            modality=self.modality,
            start_time=self.start_time,
            end_time=self.end_time,
        )


class Entity(Model):
    id: str
    name: str
    kind: str
    metadata: dict[str, Any] = Field(default_factory=dict)


class Event(Interval):
    id: str
    asset_id: str
    description: str
    document_ids: list[str] = Field(default_factory=list)
    entity_ids: list[str] = Field(default_factory=list)


class Timeline(Model):
    asset_id: str
    events: list[Event] = Field(default_factory=list)

    @model_validator(mode="after")
    def same_asset(self) -> Self:
        if any(e.asset_id != self.asset_id for e in self.events):
            raise ValueError("Timeline events must belong to the same asset")
        return self


class TraceEvent(Model):
    name: str
    duration_ms: float = Field(ge=0)
    status: str
    metadata: dict[str, Any] = Field(default_factory=dict)


class ExecutionContext(Model):
    run_id: str = Field(default_factory=lambda: uuid4().hex)
    owner_id: str = "local"
    traces: list[TraceEvent] = Field(default_factory=list)
    token_usage: int = Field(default=0, ge=0)


class ProcessingResult(Model):
    asset: MediaAsset
    documents: list[Document]
    warnings: list[str] = Field(default_factory=list)

    @model_validator(mode="after")
    def consistent(self) -> Self:
        for doc in self.documents:
            if doc.asset_id != self.asset.id or doc.source != self.asset.source:
                raise ValueError("Processed documents must reference their original asset")
            if self.asset.duration is not None and doc.end_time is not None:
                if doc.end_time > self.asset.duration + 0.1:
                    raise ValueError("Document exceeds media duration")
        return self


class RetrievalFilter(Interval):
    media_ids: list[str] | None = None
    modalities: list[Modality] | None = None
    sources: list[str] | None = None
    metadata: dict[str, Any] = Field(default_factory=dict)

    def matches(self, doc: Document) -> bool:
        if self.media_ids is not None and doc.asset_id not in self.media_ids:
            return False
        if self.modalities is not None and doc.modality not in self.modalities:
            return False
        if self.sources is not None and doc.source not in self.sources:
            return False
        if any(doc.metadata.get(k) != v for k, v in self.metadata.items()):
            return False
        if self.start_time is not None:
            return (
                doc.start_time is not None
                and doc.end_time is not None
                and self.end_time is not None
                and doc.start_time <= self.end_time
                and doc.end_time >= self.start_time
            )
        return True


class RetrievalResult(Model):
    document: Document
    score: float
    reason: str = "hybrid"

    @property
    def source(self) -> SourceReference:
        return self.document.reference()


class ModelResponse(Model):
    answer: str
    sources: list[SourceReference] = Field(default_factory=list)
    insufficient_evidence: bool = False
    token_usage: int | None = Field(default=None, ge=0)
    metadata: dict[str, Any] = Field(default_factory=dict)


class ChatMessage(Model):
    role: str
    content: str


class ChatOutput(Model):
    content: str
    token_usage: int | None = Field(default=None, ge=0)


class SpeechSegment(Interval):
    start_time: float = Field(ge=0)
    end_time: float = Field(ge=0)
    text: str
    speaker: str | None = None


class EmbeddingSpace(Model):
    model_id: str
    model_version: str
    dimensions: int = Field(gt=0)

    @property
    def key(self) -> str:
        return stable_id(self.model_dump())


class VectorRecord(Model):
    document_id: str
    asset_id: str
    values: list[float]


class Job(Model):
    id: str
    media_id: str
    owner_id: str
    status: str = "queued"
    error: str | None = None
    created_at: float = Field(default_factory=time.time)
