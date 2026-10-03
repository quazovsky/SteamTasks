"""RPC client: handshake, commands, ping/pong, drop detection.

A dedicated reader thread owns every read; callers only write, behind a lock, and
wait on futures. A dropped connection therefore shows up through
:meth:`RpcClient.wait_closed` rather than as an exception at a random call site.
"""

from __future__ import annotations

import logging
import queue
import struct
import threading
import uuid
from concurrent.futures import Future
from typing import Any, Callable

from ..core.errors import (
    CLOSE_CODE_HINTS,
    HandshakeError,
    ProtocolError,
    RpcError,
    RpcTimeout,
    TransportError,
    is_fatal_close,
)
from ..core.logging import get_logger
from . import protocol
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
from .transport import Transport, connect_any

DEFAULT_COMMAND_TIMEOUT = 15.0
#: Discord throttles IPC handshakes after a burst of connections, so the reply can
#: take several seconds. A generous ceiling avoids giving up on a slow-but-valid
#: handshake; a genuinely dead socket still fails fast with a close frame.
DEFAULT_HANDSHAKE_TIMEOUT = 20.0

class RpcClient:
    """One connection to the local Discord client."""

    def __init__(
        self,
        client_id: str,
        logger: logging.Logger | None = None,
        transport_factory: Callable[[], Transport] = connect_any,
        command_timeout: float = DEFAULT_COMMAND_TIMEOUT,
        handshake_timeout: float = DEFAULT_HANDSHAKE_TIMEOUT,
    ) -> None:
        self.client_id = str(client_id)
        self.log = logger or get_logger()
        self._transport_factory = transport_factory
        self._command_timeout = command_timeout
        self._handshake_timeout = handshake_timeout

        self._transport: Transport | None = None
        self._decoder = FrameDecoder()
        self._reader: threading.Thread | None = None
        self._write_lock = threading.Lock()
        self._pending: dict[str, Future] = {}
        self._pending_lock = threading.Lock()
        self._events: queue.Queue[dict[str, Any]] = queue.Queue()
        self._closed = threading.Event()
        # True once this connection has cleared the presence. The flag also lives on
        # the instance, so a caller that kept a reference to a client the supervisor
        # already closed can still see that clearing is done.
        self.cleared = False
        self._close_code: int | None = None
        self._close_reason: str = ""
        self._ready_payload: dict[str, Any] | None = None
        self._user: dict[str, Any] | None = None

    # State
    @property
    def ready(self) -> bool:
        return self._ready_payload is not None and not self._closed.is_set()

    @property
    def closed(self) -> bool:
        return self._closed.is_set()

    @property
    def close_code(self) -> int | None:
        return self._close_code

    @property
    def close_reason(self) -> str:
        return self._close_reason

    @property
    def user(self) -> dict[str, Any] | None:
        """The Discord account the presence is attached to (from READY)."""
        return self._user

    # Lifecycle
    def connect(self) -> dict[str, Any]:
        """Open the transport, complete the handshake, return the READY payload.

        Raises:
            IpcUnavailableError: no Discord IPC endpoint answered.
            HandshakeError: Discord closed the socket during setup.
            RpcTimeout: Discord accepted the socket but never answered.
        """
        if self._transport is not None:
            raise RuntimeError("client is single-use; construct a new one to reconnect")

        self._transport = self._transport_factory()
        self.log.debug("ipc connected", extra={"endpoint": self._transport.describe()})

        self._reader = threading.Thread(
            target=self._read_loop, name="discord-rpc-reader", daemon=True
        )
        self._reader.start()

        self._write(OP_HANDSHAKE, handshake_payload(self.client_id))

        deadline = threading.Event()
        timer = threading.Timer(self._handshake_timeout, deadline.set)
        timer.daemon = True
        timer.start()
        try:
            while not deadline.is_set():
                if self._closed.is_set():
                    raise HandshakeError(self._close_code, self._close_reason or "closed during handshake")
                try:
                    event = self._events.get(timeout=0.1)
                except queue.Empty:
                    continue
                if event.get("evt") == "READY":
                    self._ready_payload = event.get("data") or {}
                    self._user = self._ready_payload.get("user")
                    self.log.debug(
                        "handshake complete",
                        extra={
                            "user": (self._user or {}).get("username"),
                            "user_id": (self._user or {}).get("id"),
                        },
                    )
                    return self._ready_payload
        finally:
            timer.cancel()

        raise RpcTimeout("HANDSHAKE", self._handshake_timeout)

    def close(self, clear: bool = False) -> None:
        """Close the transport. Discord drops the presence once the socket dies."""
        if clear:
            if self.ready:
                try:
                    self.clear_activity()
                    self.cleared = True
                except Exception:  # noqa: BLE001 - shutdown path, best effort
                    pass
            else:
                # Nothing was set, so there is nothing to clear. Marking it here stops
                # the caller from opening another connection just to clear nothing.
                self.cleared = True
        transport, self._transport = self._transport, None
        self._closed.set()
        if transport is not None:
            transport.close()
        reader = self._reader
        if reader is not None and reader.is_alive() and reader is not threading.current_thread():
            reader.join(timeout=2.0)
        self._fail_pending(TransportError("connection closed"))

    def wait_closed(self, timeout: float) -> bool:
        """Block up to ``timeout`` seconds. True if the connection dropped."""
        return self._closed.wait(timeout)

    # Commands
    def set_activity(self, activity: dict[str, Any] | None) -> dict[str, Any]:
        """Send SET_ACTIVITY. ``None`` clears the presence."""
        return self._command(
            "SET_ACTIVITY",
            lambda nonce: set_activity_payload(self._pid(), activity, nonce),
        )

    def clear_activity(self) -> dict[str, Any]:
        return self.set_activity(None)

    def subscribe(self, event: str, args: dict[str, Any] | None = None) -> dict[str, Any]:
        return self._command(
            "SUBSCRIBE",
            lambda nonce: protocol.subscribe_payload(event, args, nonce),
            expect_ack=False,
        )

    def _command(
        self,
        cmd: str,
        build: Callable[[str], dict[str, Any]],
        expect_ack: bool = True,
    ) -> dict[str, Any]:
        if self._closed.is_set():
            raise TransportError(f"cannot send {cmd}: connection is closed")

        nonce = str(uuid.uuid4())
        future: Future = Future()
        with self._pending_lock:
            self._pending[nonce] = future

        try:
            self._write(OP_FRAME, build(nonce))
            if not expect_ack:
                return {}
            try:
                result = future.result(timeout=self._command_timeout)
            except TimeoutError as exc:
                raise RpcTimeout(cmd, self._command_timeout) from exc
            return result
        finally:
            with self._pending_lock:
                self._pending.pop(nonce, None)

    @staticmethod
    def _pid() -> int:
        import os

        return os.getpid()

    # Transport plumbing
    def _write(self, op: int, payload: dict[str, Any] | None) -> None:
        transport = self._transport
        if transport is None:
            raise TransportError("transport is not open")
        frame = encode_frame(op, payload)
        with self._write_lock:
            transport.write_all(frame)

    def _read_loop(self) -> None:
        transport = self._transport
        assert transport is not None
        try:
            while not self._closed.is_set():
                header = transport.read_exact(protocol.HEADER_SIZE)
                if len(header) < protocol.HEADER_SIZE:
                    self._close_reason = self._close_reason or "end of stream"
                    break
                _, length = struct.unpack("<II", header)
                body = transport.read_exact(length) if length else b""
                if length and len(body) < length:
                    self._close_reason = self._close_reason or "truncated frame"
                    break
                for op, payload in self._decoder.feed(header + body):
                    if not self._handle(op, payload):
                        return
        except (TransportError, ProtocolError) as exc:
            self._close_reason = str(exc)
            self.log.debug("reader stopped", extra={"reason": str(exc)})
        except Exception as exc:  # noqa: BLE001 - reader must never kill the process
            # Keep Discord's own close reason if one was already recorded.
            self._close_reason = self._close_reason or f"unexpected reader failure: {exc}"
            self.log.warning("reader crashed", extra={"error": str(exc)})
        finally:
            self._closed.set()
            self._fail_pending(TransportError(self._close_reason or "connection closed"))

    def _handle(self, op: int, payload: Any) -> bool:
        """Handle one frame. Returns False to stop the reader."""
        if op == OP_PING:
            try:
                self._write(OP_PONG, payload if isinstance(payload, dict) else {})
            except TransportError:
                return False
            return True

        if op == OP_CLOSE:
            data = payload if isinstance(payload, dict) else {}
            self._close_code = data.get("code")
            self._close_reason = data.get("message") or "closed by Discord"
            hint = CLOSE_CODE_HINTS.get(self._close_code)
            self.log.warning(
                "Discord closed the connection",
                extra={
                    "code": self._close_code,
                    "close_message": self._close_reason,
                    "hint": hint,
                    "fatal": is_fatal_close(self._close_code),
                },
            )
            return False

        if op == OP_FRAME:
            data = payload if isinstance(payload, dict) else {}
            nonce = data.get("nonce")
            if nonce:
                with self._pending_lock:
                    future = self._pending.get(nonce)
                if future is not None and not future.done():
                    error = self._extract_error(data)
                    if error is not None:
                        future.set_exception(error)
                    else:
                        future.set_result(data.get("data"))
                    return True
            if data.get("evt"):
                self._events.put(data)
            return True

        self.log.debug("ignoring unknown opcode", extra={"op": op, "name": op_name(op)})
        return True

    @staticmethod
    def _extract_error(data: dict[str, Any]) -> Exception | None:
        """Discord reports command failures as a bare ``{code, message}`` body."""
        if data.get("evt") == "ERROR":
            return RpcError(str(data.get("cmd", "unknown")), data.get("data"))
        body = data.get("data")
        if isinstance(body, dict) and "code" in body and "message" in body:
            return RpcError(str(data.get("cmd", "unknown")), body)
        return None

    def _fail_pending(self, exc: Exception) -> None:
        with self._pending_lock:
            pending = list(self._pending.values())
            self._pending.clear()
        for future in pending:
            if not future.done():
                future.set_exception(exc)
