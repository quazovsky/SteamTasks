"""Byte channels to the local Discord client.

Windows uses ``\\\\.\\pipe\\discord-ipc-N``, everything else an AF_UNIX socket at
``$XDG_RUNTIME_DIR/discord-ipc-N``.

The Windows transport goes through ``ctypes`` rather than ``open()`` because a
synchronous pipe handle serialises I/O. Measured against the live Discord pipe on
Windows 11 / CPython 3.13: with a blocking read pending in a reader thread, a
write from another thread did not return for 9.5 s, and Discord closed the socket
with 1006 "Handshake timeout". FILE_FLAG_OVERLAPPED plus an event per operation
keeps reads and writes independent.
"""

from __future__ import annotations

import ctypes
import os
import socket
import time
from abc import ABC, abstractmethod
from pathlib import Path

from ..core.errors import IpcUnavailableError, TransportError

IPC_PIPE_PREFIX = "discord-ipc-"
IPC_RANGE = range(10)

#: Set this to bypass discovery, e.g. ``DISCORD_IPC_PATH=/run/user/1000/discord-ipc-0``.
ENV_IPC_PATH = "DISCORD_IPC_PATH"

INFINITE = 0xFFFFFFFF
DEFAULT_IO_TIMEOUT_MS = 15_000

class Transport(ABC):
    """A duplex byte channel with exact-length reads."""

    name: str = "<transport>"

    @abstractmethod
    def read_exact(self, size: int) -> bytes:
        """Read exactly ``size`` bytes, or fewer only at end-of-stream."""

    @abstractmethod
    def write_all(self, data: bytes) -> None: ...

    @abstractmethod
    def close(self) -> None: ...

    def describe(self) -> str:
        return self.name

# POSIX: AF_UNIX stream socket
class SocketTransport(Transport):
    """AF_UNIX stream socket (Linux, macOS)."""

    def __init__(self, sock: socket.socket, name: str) -> None:
        self._sock = sock
        self.name = name
        self._closed = False

    def read_exact(self, size: int) -> bytes:
        chunks: list[bytes] = []
        remaining = size
        while remaining > 0:
            try:
                chunk = self._sock.recv(remaining)
            except OSError as exc:
                if self._closed:
                    return b"".join(chunks)
                raise TransportError(f"recv failed on {self.name}: {exc}") from exc
            if not chunk:
                return b"".join(chunks)
            chunks.append(chunk)
            remaining -= len(chunk)
        return b"".join(chunks)

    def write_all(self, data: bytes) -> None:
        try:
            self._sock.sendall(data)
        except OSError as exc:
            if self._closed:
                raise TransportError(f"send after close on {self.name}") from exc
            raise TransportError(f"send failed on {self.name}: {exc}") from exc

    def close(self) -> None:
        if self._closed:
            return
        self._closed = True
        try:
            self._sock.close()
        except Exception:  # noqa: BLE001
            pass

# Windows: named pipe over overlapped I/O
if os.name == "nt":
    from ctypes import wintypes

    _kernel32 = ctypes.WinDLL("kernel32", use_last_error=True)

    GENERIC_READ = 0x80000000
    GENERIC_WRITE = 0x40000000
    OPEN_EXISTING = 3
    FILE_FLAG_OVERLAPPED = 0x40000000
    ERROR_IO_PENDING = 997
    WAIT_OBJECT_0 = 0
    WAIT_TIMEOUT = 258

    class _OVERLAPPED(ctypes.Structure):
        _fields_ = [
            ("Internal", ctypes.c_void_p),
            ("InternalHigh", ctypes.c_void_p),
            ("Offset", wintypes.DWORD),
            ("OffsetHigh", wintypes.DWORD),
            ("hEvent", wintypes.HANDLE),
        ]

    _kernel32.CreateFileW.argtypes = [
        wintypes.LPCWSTR, wintypes.DWORD, wintypes.DWORD, ctypes.c_void_p,
        wintypes.DWORD, wintypes.DWORD, wintypes.HANDLE,
    ]
    _kernel32.CreateFileW.restype = wintypes.UINT  # file HANDLE
    _kernel32.ReadFile.argtypes = [
        wintypes.HANDLE, ctypes.c_void_p, wintypes.DWORD,
        ctypes.POINTER(wintypes.DWORD), ctypes.POINTER(_OVERLAPPED),
    ]
    _kernel32.ReadFile.restype = wintypes.BOOL
    _kernel32.WriteFile.argtypes = _kernel32.ReadFile.argtypes
    _kernel32.WriteFile.restype = wintypes.BOOL
    _kernel32.CreateEventW.argtypes = [
        ctypes.c_void_p, wintypes.BOOL, wintypes.BOOL, wintypes.LPCWSTR,
    ]
    _kernel32.CreateEventW.restype = wintypes.UINT  # event HANDLE
    _kernel32.WaitForSingleObject.argtypes = [wintypes.HANDLE, wintypes.DWORD]
    _kernel32.WaitForSingleObject.restype = wintypes.DWORD
    _kernel32.GetOverlappedResult.argtypes = [
        wintypes.HANDLE, ctypes.POINTER(_OVERLAPPED),
        ctypes.POINTER(wintypes.DWORD), wintypes.BOOL,
    ]
    _kernel32.GetOverlappedResult.restype = wintypes.BOOL
    _kernel32.CancelIoEx.argtypes = [wintypes.HANDLE, ctypes.POINTER(_OVERLAPPED)]
    _kernel32.CancelIoEx.restype = wintypes.BOOL
    _kernel32.CloseHandle.argtypes = [wintypes.HANDLE]
    _kernel32.CloseHandle.restype = wintypes.BOOL

class WindowsPipeTransport(Transport):
    """Named pipe opened with ``FILE_FLAG_OVERLAPPED``.

    Every read and write gets its own ``OVERLAPPED`` + event, so a blocking read
    in the reader thread never stalls a write from the caller's thread.
    """

    def __init__(self, path: str, io_timeout_ms: int = DEFAULT_IO_TIMEOUT_MS) -> None:
        handle = _kernel32.CreateFileW(
            path,
            GENERIC_READ | GENERIC_WRITE,
            0,  # no sharing: one client per pipe instance
            None,
            OPEN_EXISTING,
            FILE_FLAG_OVERLAPPED,
            None,
        )
        if handle == wintypes.HANDLE(-1).value or not handle:
            error = ctypes.get_last_error()
            raise OSError(error, f"CreateFileW failed for {path}", path)
        self._handle = handle
        self.name = path
        self._io_timeout_ms = io_timeout_ms
        self._closed = False

    # -- primitives ----------------------------------------------------- #
    def _run_overlapped(self, operation, buffer, size: int, timeout_ms: int) -> int:
        overlapped = _OVERLAPPED()
        event = _kernel32.CreateEventW(None, True, False, None)
        if not event:
            raise TransportError(f"CreateEventW failed ({ctypes.get_last_error()})")
        overlapped.hEvent = event
        try:
            ok = operation(self._handle, buffer, size, None, ctypes.byref(overlapped))
            if not ok:
                error = ctypes.get_last_error()
                if error != ERROR_IO_PENDING:
                    raise TransportError(f"I/O failed on {self.name} (error {error})")

            status = _kernel32.WaitForSingleObject(event, timeout_ms)
            if status == WAIT_TIMEOUT:
                _kernel32.CancelIoEx(self._handle, ctypes.byref(overlapped))
                _kernel32.WaitForSingleObject(event, 2_000)
                raise TransportError(f"I/O timed out after {timeout_ms} ms on {self.name}")
            if status != WAIT_OBJECT_0:
                raise TransportError(f"WaitForSingleObject returned {status} on {self.name}")

            transferred = wintypes.DWORD(0)
            if not _kernel32.GetOverlappedResult(
                self._handle, ctypes.byref(overlapped), ctypes.byref(transferred), False
            ):
                error = ctypes.get_last_error()
                if self._closed:
                    return 0
                raise TransportError(f"GetOverlappedResult failed on {self.name} (error {error})")
            return int(transferred.value)
        finally:
            _kernel32.CloseHandle(event)

    def read_exact(self, size: int) -> bytes:
        chunks: list[bytes] = []
        remaining = size
        while remaining > 0:
            if self._closed:
                break
            buffer = ctypes.create_string_buffer(remaining)
            try:
                transferred = self._run_overlapped(
                    _kernel32.ReadFile, buffer, remaining, INFINITE
                )
            except TransportError:
                if self._closed:
                    break
                raise
            if transferred == 0:
                break
            chunks.append(buffer.raw[:transferred])
            remaining -= transferred
        return b"".join(chunks)

    def write_all(self, data: bytes) -> None:
        if self._closed:
            raise TransportError(f"write after close on {self.name}")
        buffer = ctypes.create_string_buffer(data, len(data))
        written = self._run_overlapped(_kernel32.WriteFile, buffer, len(data), self._io_timeout_ms)
        if written != len(data):
            raise TransportError(f"short write on {self.name}: {written}/{len(data)} bytes")

    def close(self) -> None:
        if self._closed:
            return
        self._closed = True
        try:
            _kernel32.CancelIoEx(self._handle, None)
        except Exception:  # noqa: BLE001
            pass
        try:
            _kernel32.CloseHandle(self._handle)
        except Exception:  # noqa: BLE001
            pass

# Discovery
def _windows_pipe_paths() -> list[str]:
    return [rf"\\.\pipe\{IPC_PIPE_PREFIX}{i}" for i in IPC_RANGE]

def _posix_socket_dirs() -> list[str]:
    home = Path.home()
    candidates: list[str | None] = [
        os.environ.get("XDG_RUNTIME_DIR"),
        os.environ.get("TMPDIR"),
        os.environ.get("TMP"),
        os.environ.get("TEMP"),
        "/tmp",
        str(home / "snap" / "discord" / "current" / ".config" / "discord"),
        str(home / ".var" / "app" / "com.discordapp.Discord" / "config" / "discord"),
        str(home / ".config" / "discord"),
    ]
    seen: list[str] = []
    for raw in candidates:
        if not raw:
            continue
        resolved = os.path.realpath(raw)
        if resolved not in seen:
            seen.append(resolved)
    return seen

def candidate_paths() -> list[str]:
    """Every IPC endpoint worth trying, most-likely first."""
    override = os.environ.get(ENV_IPC_PATH)
    if override:
        return [p for p in override.split(os.pathsep) if p]

    if os.name == "nt":
        return _windows_pipe_paths()
    return [os.path.join(d, f"{IPC_PIPE_PREFIX}{i}") for d in _posix_socket_dirs() for i in IPC_RANGE]

def open_transport(path: str, timeout: float = 2.0) -> Transport:
    """Open one specific endpoint.

    Raises ``OSError`` when the endpoint does not exist or refuses the
    connection; the caller treats that as "try the next candidate".
    """
    if os.name == "nt":
        return WindowsPipeTransport(path)
    sock = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
    sock.settimeout(timeout)
    try:
        sock.connect(path)
    except OSError:
        sock.close()
        raise
    sock.settimeout(None)
    return SocketTransport(sock, path)

def connect_any(timeout: float = 2.0) -> Transport:
    """Open the first endpoint that answers, or raise :class:`IpcUnavailableError`."""
    tried: list[str] = []
    for path in candidate_paths():
        tried.append(path)
        try:
            return open_transport(path, timeout=timeout)
        except OSError:
            continue
        except Exception:  # noqa: BLE001 - discovery must never abort the scan
            continue
    raise IpcUnavailableError(tried)

def is_discord_running() -> bool:
    """Cheap liveness check: does any IPC endpoint accept a connection?"""
    try:
        transport = connect_any(timeout=1.0)
    except IpcUnavailableError:
        return False
    transport.close()
    return True

def wait_for_ipc(timeout: float = 0.0, interval: float = 1.0) -> bool:
    """Poll for Discord IPC. ``timeout=0`` performs a single check."""
    deadline = time.monotonic() + timeout
    while True:
        if is_discord_running():
            return True
        if time.monotonic() >= deadline:
            return False
        time.sleep(interval)
