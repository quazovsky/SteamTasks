"""Typed error hierarchy.

Every failure mode in the app has a dedicated class so the supervisor can make a
policy decision (retry / backoff / stop) instead of parsing strings.
"""

from __future__ import annotations

from typing import Any

class worthlesstaskError(Exception):
    """Base class for every error raised by this package."""

# Configuration
class ConfigError(worthlesstaskError):
    """Config file missing, unreadable, or structurally wrong."""

class ValidationError(ConfigError):
    """A field is present but violates a documented constraint."""

    def __init__(self, field: str, message: str) -> None:
        self.field = field
        self.message = message
        super().__init__(f"{field}: {message}")

# Transport
class TransportError(worthlesstaskError):
    """The byte channel to Discord failed."""

class IpcUnavailableError(TransportError):
    """No Discord IPC endpoint could be opened."""

    def __init__(self, tried: list[str]) -> None:
        self.tried = tried
        preview = ", ".join(tried[:4]) + (" ..." if len(tried) > 4 else "")
        super().__init__(
            f"no Discord IPC endpoint accepted a connection (tried {len(tried)}: {preview}). "
            "Is the Discord desktop client running and logged in?"
        )

# Protocol / RPC
class ProtocolError(worthlesstaskError):
    """Framing violation: bad opcode, oversized or malformed payload."""

class HandshakeError(worthlesstaskError):
    """Discord rejected the handshake or closed the socket during setup."""

    def __init__(self, code: int | None, message: str) -> None:
        self.code = code
        self.message = message
        super().__init__(f"Discord closed the connection (code={code}): {message}")

class RpcError(worthlesstaskError):
    """A command frame came back with a Discord-side error."""

    def __init__(self, cmd: str, detail: Any) -> None:
        self.cmd = cmd
        self.detail = detail
        super().__init__(f"{cmd} failed: {detail!r}")

class RpcTimeout(worthlesstaskError):
    """No ack for a command within the deadline."""

    def __init__(self, cmd: str, timeout: float) -> None:
        self.cmd = cmd
        self.timeout = timeout
        super().__init__(f"{cmd} got no acknowledgement within {timeout:g}s")

class ResolverError(worthlesstaskError):
    """Application lookup failed (network, HTTP status, bad payload)."""

# Close codes returned by the Discord client in an OP_CLOSE frame.
CLOSE_INVALID_CLIENT_ID = 4000
CLOSE_INVALID_ORIGIN = 4001
CLOSE_RATE_LIMITED = 4002
CLOSE_TOKEN_REVOKED = 4003
CLOSE_TOKEN_INVALID = 4004

#: Codes that will never succeed on retry. Stop the supervisor.
FATAL_CLOSE_CODES = frozenset(
    {
        CLOSE_INVALID_CLIENT_ID,
        CLOSE_INVALID_ORIGIN,
        CLOSE_TOKEN_REVOKED,
        CLOSE_TOKEN_INVALID,
    }
)

CLOSE_CODE_HINTS = {
    CLOSE_INVALID_CLIENT_ID: (
        "client_id is not a real Discord application id. Create an application in the "
        "Discord Developer Portal and copy its Application ID."
    ),
    CLOSE_INVALID_ORIGIN: "the origin was rejected; nothing to fix locally, report it.",
    CLOSE_RATE_LIMITED: "Discord is rate limiting; backing off.",
    CLOSE_TOKEN_REVOKED: "token revoked; re-authorise the application.",
    CLOSE_TOKEN_INVALID: "token invalid; re-authorise the application.",
}

def is_fatal_close(code: int | None) -> bool:
    return code in FATAL_CLOSE_CODES
