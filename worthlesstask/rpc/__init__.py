"""Discord IPC transport, framing and connection supervision."""

from .client import RpcClient
from .protocol import (
    OP_CLOSE,
    OP_FRAME,
    OP_HANDSHAKE,
    OP_PING,
    OP_PONG,
    FrameDecoder,
    encode_frame,
    handshake_payload,
    op_name,
    set_activity_payload,
)
from .supervisor import (
    EXIT_ATTEMPTS_EXHAUSTED,
    EXIT_FATAL,
    EXIT_OK,
    PresenceSupervisor,
    SupervisorStats,
)
from .transport import (
    Transport,
    candidate_paths,
    connect_any,
    is_discord_running,
    open_transport,
    wait_for_ipc,
)

__all__ = [
    "EXIT_ATTEMPTS_EXHAUSTED",
    "EXIT_FATAL",
    "EXIT_OK",
    "OP_CLOSE",
    "OP_FRAME",
    "OP_HANDSHAKE",
    "OP_PING",
    "OP_PONG",
    "FrameDecoder",
    "PresenceSupervisor",
    "RpcClient",
    "SupervisorStats",
    "Transport",
    "candidate_paths",
    "connect_any",
    "encode_frame",
    "handshake_payload",
    "is_discord_running",
    "op_name",
    "open_transport",
    "set_activity_payload",
    "wait_for_ipc",
]
