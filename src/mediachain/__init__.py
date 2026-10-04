"""MediaChain: one composable framework for text, audio, video and time."""

from mediachain.core.config import ProcessingConfig
from mediachain.core.models import (
    Document,
    ExecutionContext,
    MediaAsset,
    Modality,
    ModelResponse,
    RetrievalFilter,
    SourceReference,
)
from mediachain.runtime.client import MediaChain

__all__ = [
    "MediaChain",
    "Document",
    "ExecutionContext",
    "MediaAsset",
    "ModelResponse",
    "Modality",
    "ProcessingConfig",
    "RetrievalFilter",
    "SourceReference",
]
__version__ = "0.1.0"
