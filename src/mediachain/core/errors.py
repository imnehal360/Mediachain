"""Structured framework errors suitable for API translation."""


class MediaChainError(Exception):
    code = "mediachain_error"


class ConfigurationError(MediaChainError):
    code = "configuration_error"


class UnsupportedMediaError(MediaChainError):
    code = "unsupported_media"


class RemoteMediaError(MediaChainError):
    code = "remote_media_error"


class ProcessingError(MediaChainError):
    code = "processing_error"


class EmbeddingSpaceError(MediaChainError):
    code = "embedding_space_mismatch"


class GroundingError(MediaChainError):
    code = "invalid_citation"


class BudgetExceeded(MediaChainError):
    code = "budget_exceeded"
