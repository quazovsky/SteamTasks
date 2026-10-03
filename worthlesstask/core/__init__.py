"""Core primitives: errors, logging, backoff."""

from .backoff import BackoffPolicy
from .errors import (
    CLOSE_CODE_HINTS,
    FATAL_CLOSE_CODES,
    ConfigError,
    HandshakeError,
    IpcUnavailableError,
    ProtocolError,
    ResolverError,
    RpcError,
    RpcTimeout,
    worthlesstaskError,
    TransportError,
    ValidationError,
    is_fatal_close,
)
from .logging import get_logger, setup_logging

__all__ = [
    "BackoffPolicy",
    "CLOSE_CODE_HINTS",
    "FATAL_CLOSE_CODES",
    "ConfigError",
    "HandshakeError",
    "IpcUnavailableError",
    "ProtocolError",
    "ResolverError",
    "RpcError",
    "RpcTimeout",
    "worthlesstaskError",
    "TransportError",
    "ValidationError",
    "get_logger",
    "is_fatal_close",
    "setup_logging",
]
