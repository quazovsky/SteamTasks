"""Wire format for the Discord IPC protocol.

Every frame is a fixed 8-byte header followed by a UTF-8 JSON body:

    +--------+--------+---------------------+
    | op (4) | len (4)| json body (len)     |     both ints little-endian
    +--------+--------+---------------------+

Reads from a pipe are *not* guaranteed to be frame-aligned or complete, so
:class:`FrameDecoder` is incremental: feed it whatever arrived, get back whole
frames only.
"""

from __future__ import annotations

import json
import struct
from typing import Any, Iterator

from ..core.errors import ProtocolError

OP_HANDSHAKE = 0
OP_FRAME = 1
OP_CLOSE = 2
OP_PING = 3
OP_PONG = 4

OP_NAMES = {
    OP_HANDSHAKE: "HANDSHAKE",
    OP_FRAME: "FRAME",
    OP_CLOSE: "CLOSE",
    OP_PING: "PING",
    OP_PONG: "PONG",
}

OP_BY_NAME = {v: k for k, v in OP_NAMES.items()}

#: Discord never legitimately sends a body larger than a few KB. 8 MiB is a
#: generous ceiling that still stops a desynchronised stream from allocating
#: unbounded memory.
MAX_FRAME_BYTES = 8 * 1024 * 1024

HEADER_SIZE = 8
_HEADER = struct.Struct("<II")


def op_name(op: int) -> str:
    return OP_NAMES.get(op, f"OP_{op}")


def encode_frame(op: int, payload: dict[str, Any] | None = None) -> bytes:
    """Serialise one frame. ``None`` payload becomes an empty JSON object."""
    body = json.dumps(payload if payload is not None else {}, ensure_ascii=False).encode("utf-8")
    if len(body) > MAX_FRAME_BYTES:
        raise ProtocolError(f"refusing to send a {len(body)}-byte frame")
    return _HEADER.pack(op, len(body)) + body


class FrameDecoder:
    """Incremental decoder: ``feed()`` bytes in, complete frames out."""

    __slots__ = ("_buffer",)

    def __init__(self) -> None:
        self._buffer = bytearray()

    def feed(self, chunk: bytes) -> Iterator[tuple[int, Any]]:
        if chunk:
            self._buffer.extend(chunk)

        while True:
            if len(self._buffer) < HEADER_SIZE:
                return
            op, length = _HEADER.unpack_from(self._buffer, 0)
            if length > MAX_FRAME_BYTES:
                raise ProtocolError(
                    f"frame length {length} exceeds the {MAX_FRAME_BYTES}-byte ceiling; "
                    "the stream is desynchronised"
                )
            if len(self._buffer) < HEADER_SIZE + length:
                return

            body = bytes(self._buffer[HEADER_SIZE : HEADER_SIZE + length])
            del self._buffer[: HEADER_SIZE + length]

            if not body:
                yield op, None
                continue
            try:
                yield op, json.loads(body.decode("utf-8"))
            except (UnicodeDecodeError, json.JSONDecodeError) as exc:
                raise ProtocolError(f"frame body is not valid UTF-8 JSON: {exc}") from exc

    def reset(self) -> None:
        self._buffer.clear()

    @property
    def pending_bytes(self) -> int:
        return len(self._buffer)


def handshake_payload(client_id: str, version: int = 1) -> dict[str, Any]:
    """Body of the opening OP_HANDSHAKE frame."""
    return {"v": version, "client_id": str(client_id)}


def set_activity_payload(pid: int, activity: dict[str, Any] | None, nonce: str) -> dict[str, Any]:
    """Body of a SET_ACTIVITY command. ``activity=None`` clears the presence."""
    return {"cmd": "SET_ACTIVITY", "args": {"pid": int(pid), "activity": activity}, "nonce": nonce}


def subscribe_payload(event: str, args: dict[str, Any] | None, nonce: str) -> dict[str, Any]:
    return {"cmd": "SUBSCRIBE", "args": args or {}, "evt": event, "nonce": nonce}
