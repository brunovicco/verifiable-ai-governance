"""Transport-independent errors raised by application services."""

from enum import StrEnum

type ErrorDetail = str | dict[str, object]


class ErrorKind(StrEnum):
    """Stable categories that transport adapters map to their own protocols."""

    FORBIDDEN = "forbidden"
    NOT_FOUND = "not_found"
    CONFLICT = "conflict"
    UNPROCESSABLE = "unprocessable"
    PAYLOAD_TOO_LARGE = "payload_too_large"
    UNSUPPORTED_MEDIA_TYPE = "unsupported_media_type"
    DEPENDENCY_UNAVAILABLE = "dependency_unavailable"


class ApplicationError(Exception):
    """Describe an expected application failure without importing FastAPI."""

    def __init__(self, kind: ErrorKind, detail: ErrorDetail) -> None:
        """Initialize an error with a stable kind and client-safe detail."""
        super().__init__(str(detail))
        self.kind = kind
        self.detail = detail
