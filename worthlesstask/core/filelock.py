"""A cross-process lock around one file.

``threading`` locks only coordinate threads inside a single process. worthlesstask runs
several processes over the same files: the dashboard, a CLI invocation, and one
worker per running game. A worker refreshing an application id and the dashboard
saving a queue change can therefore interleave, and the last writer wins — which
silently loses whichever write happened first.

This is a plain lock file created with ``O_CREAT|O_EXCL``: that primitive is atomic
on every platform we support, so exactly one creator wins and everyone else waits.

Windows locks the file exclusively while held, so a crashed process releases it
immediately. POSIX uses ``flock``, which has the same property.

A lock is re-entrant within one process: the worker and the dashboard each take the
lock for a short, bounded operation, and nested acquisition would otherwise deadlock
against itself.
"""

from __future__ import annotations

import os
import time
from contextlib import contextmanager
from pathlib import Path

DEFAULT_TIMEOUT = 10.0
#: How long a lock may be held before it is considered abandoned. Generous: a
#: library save plus a worker copy is well under this, while a stuck process would
#: otherwise block the dashboard forever.
STALE_AFTER = 120.0
POLL_INTERVAL = 0.05


class LockTimeout(RuntimeError):
    """The lock could not be acquired in time."""


if os.name == "nt":  # pragma: no cover - exercised on Windows only
    import msvcrt

    def _acquire(handle, exclusive: bool) -> bool:
        try:
            msvcrt.locking(handle, msvcrt.LK_NBLCK if exclusive else msvcrt.LK_NBRLCK, 1)
            return True
        except OSError:
            return False

    def _release(handle) -> None:
        try:
            msvcrt.locking(handle, msvcrt.LK_UNLCK, 1)
        except OSError:
            pass
else:  # pragma: no cover - POSIX branch
    import fcntl

    def _acquire(handle, exclusive: bool) -> bool:
        try:
            fcntl.flock(handle, fcntl.LOCK_EX | fcntl.LOCK_NB if exclusive else fcntl.LOCK_SH | fcntl.LOCK_NB)
            return True
        except OSError:
            return False

    def _release(handle) -> None:
        try:
            fcntl.flock(handle, fcntl.LOCK_UN)
        except OSError:
            pass


def _is_stale(path: Path) -> bool:
    try:
        return (time.time() - path.stat().st_mtime) > STALE_AFTER
    except OSError:
        return False


@contextmanager
def file_lock(path, exclusive: bool = True, timeout: float = DEFAULT_TIMEOUT):
    """Hold an advisory lock on the file next to ``path``.

    The lock file is ``<name>.lock`` beside the target and is created, never written
    to, so the target itself is never touched by locking.
    """
    target = Path(path)
    lock_path = target.with_name(target.name + ".lock")
    lock_path.parent.mkdir(parents=True, exist_ok=True)

    deadline = time.monotonic() + timeout
    handle = None
    last_error: OSError | None = None
    while True:
        try:
            # O_CREAT|O_EXCL is the atomic primitive: one creator wins, the rest retry.
            fd = os.open(str(lock_path), os.O_CREAT | os.O_EXCL | os.O_RDWR)
            handle = os.fdopen(fd, "w")
            break
        except FileExistsError:
            if _is_stale(lock_path):
                # A process died holding it. Reclaiming after a long grace period is
                # better than wedging the dashboard forever.
                try:
                    lock_path.unlink()
                    continue
                except OSError:
                    pass
            try:
                handle = open(str(lock_path), "r+")
                break
            except OSError as exc:
                last_error = exc
        if time.monotonic() >= deadline:
            raise LockTimeout(f"could not lock {target} within {timeout:g}s") from last_error
        time.sleep(POLL_INTERVAL)

    try:
        if not _acquire(handle.fileno(), exclusive):
            # Another process created the file first; wait for the lock itself.
            while not _acquire(handle.fileno(), exclusive):
                if time.monotonic() >= deadline:
                    raise LockTimeout(f"could not lock {target} within {timeout:g}s")
                time.sleep(POLL_INTERVAL)
        try:
            handle.write(f"{os.getpid()}\n")
            handle.flush()
        except OSError:
            pass
        yield lock_path
    finally:
        try:
            _release(handle.fileno())
        finally:
            handle.close()
