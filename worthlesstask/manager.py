"""Serialize process changes without blocking state reads or waiting for RPC in HTTP."""
from __future__ import annotations

import ctypes
import json
import logging
import os
import re
import subprocess
import sys
import threading
import time
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from typing import Any, Callable, Protocol

from .config.schema import AppConfig
from .core.atomic import write_atomic
from .core.cache import TtlCache, TtlValue, memoise
from .core.errors import worthlesstaskError
from .core.logging import get_logger
from .decoy import ensure_decoy, validate_image_name
from .library import Entry, Library

CREATE_NO_WINDOW = 0x08000000
SCHEDULER_INTERVAL = 1.0
WM_CLOSE = 0x0010

#: One slot in the rotation. Shared with the CLI so both entry points reject the
#: same values instead of drifting apart.
MIN_QUEUE_MINUTES = 1
MAX_QUEUE_MINUTES = 1440

if os.name == "nt":
    from ctypes import wintypes as _wintypes

    _user32 = ctypes.WinDLL("user32", use_last_error=True)
    _user32.PostMessageW.argtypes = [
        _wintypes.HWND, _wintypes.UINT, _wintypes.WPARAM, _wintypes.LPARAM
    ]
else:  # pragma: no cover - the window only exists on Windows
    _user32 = None

class ManagerError(worthlesstaskError):
    """An actionable launch or lifecycle error."""

class Process(Protocol):
    pid: int
    def poll(self) -> int | None: ...
    def terminate(self) -> None: ...
    def kill(self) -> None: ...
    def wait(self, timeout: float | None = None) -> int: ...

@dataclass
class Instance:
    slug: str
    pid: int
    started_at: float
    process: Process
    reason: str = "manual"
    image_path: str = ""
    identity: str | None = None
    worker_pid: int | None = None
    worker_identity: str | None = None
    @property
    def uptime(self) -> float:
        return max(0, time.time() - self.started_at)


def _default_spawn(argv: list[str], env: dict[str, str], cwd: Path) -> Process:
    log_path = Path(argv[argv.index("--log-file") + 1]).with_suffix(".startup.log")
    with log_path.open("wb") as output:
        return subprocess.Popen(argv, env=env, cwd=str(cwd), shell=False,
                                stdin=subprocess.DEVNULL, stdout=output, stderr=output,
                                creationflags=CREATE_NO_WINDOW if os.name == "nt" else 0)


_kernel_handle = None
_kernel_lock = threading.Lock()


def _kernel():
    """The kernel32 binding, built once.

    Rebuilding it per call meant a fresh ``WinDLL`` and four argtype assignments for
    every process query, and a status read makes several.
    """
    global _kernel_handle
    if _kernel_handle is not None:
        return _kernel_handle
    with _kernel_lock:
        if _kernel_handle is None:
            from ctypes import wintypes as w

            k = ctypes.WinDLL("kernel32", use_last_error=True)
            k.OpenProcess.argtypes = [w.DWORD, w.BOOL, w.DWORD]
            k.OpenProcess.restype = w.UINT  # process HANDLE
            k.CloseHandle.argtypes = [w.HANDLE]
            k.GetExitCodeProcess.argtypes = [w.HANDLE, ctypes.POINTER(w.DWORD)]
            k.TerminateProcess.argtypes = [w.HANDLE, w.UINT]
            k.GetProcessTimes.argtypes = [w.HANDLE] + [ctypes.POINTER(w.FILETIME)] * 4
            _kernel_handle = k
    return _kernel_handle


#: Process facts do not change within one poll interval, but asking for them costs
#: a handle open plus a Win32 call each. See core.cache for the TTL rationale.
PROCESS_CACHE_TTL = 0.75
WINDOW_CACHE_TTL = 0.5
_identity_cache = TtlCache(PROCESS_CACHE_TTL, "process_identity")
_image_path_cache = TtlCache(PROCESS_CACHE_TTL, "process_image_path")
_window_cache = TtlValue(WINDOW_CACHE_TTL, "visible_windows")


def reset_process_caches() -> None:
    """Drop every memoised process and window fact. Used after a lifecycle change."""
    _identity_cache.clear()
    _image_path_cache.clear()
    _window_cache.clear()


def _raw_identity(pid: int) -> str | None:
    if os.name != "nt":
        return None
    from ctypes import wintypes as w

    k = _kernel()
    handle = k.OpenProcess(0x1000, False, pid)
    if not handle:
        return None
    try:
        times = [w.FILETIME() for _ in range(4)]
        if not k.GetProcessTimes(handle, *(ctypes.byref(t) for t in times)):
            return None
        return str((times[0].dwHighDateTime << 32) | times[0].dwLowDateTime)
    finally:
        k.CloseHandle(handle)


def _raw_image_path(pid: int) -> str | None:
    # Resolved at call time, so a test (or a patched transport) is honoured rather
    # than whatever the module happened to hold when this was first called.
    from .ui import inspect as inspect_module

    return inspect_module.process_image_path(pid)


_cached_identity = memoise(_identity_cache, _raw_identity)
_cached_image_path = memoise(_image_path_cache, _raw_image_path)


def process_identity(pid: int) -> str | None:
    """Creation time prevents a recycled PID from being adopted or terminated."""
    return _cached_identity(int(pid))


def process_image_path_cached(pid: int) -> str | None:
    """The image path of ``pid``, memoised for one poll interval."""
    return _cached_image_path(int(pid))


def process_started_at(pid: int) -> float | None:
    """Unix timestamp when a process was created, so log filtering can use it."""
    if os.name != "nt":
        return None
    from ctypes import wintypes as w
    k = _kernel()
    handle = k.OpenProcess(0x1000, False, pid)
    if not handle:
        return None
    try:
        times = [w.FILETIME() for _ in range(4)]
        if not k.GetProcessTimes(handle, *(ctypes.byref(t) for t in times)):
            return None
        ticks = (times[0].dwHighDateTime << 32) | times[0].dwLowDateTime
        return ticks / 10_000_000 - 11_644_473_600  # FILETIME epoch -> unix
    finally:
        k.CloseHandle(handle)


class PidProcess:
    def __init__(self, pid: int, identity: str | None = None):
        self.pid, self.identity = int(pid), identity

    def poll(self):
        if self.identity and process_identity(self.pid) != self.identity:
            return 0
        if os.name != "nt":
            try:
                os.kill(self.pid, 0)
                return None
            except OSError:
                return 0
        k = _kernel()
        handle = k.OpenProcess(0x1000, False, self.pid)
        if not handle:
            return 0
        try:
            code = ctypes.c_ulong()
            if not k.GetExitCodeProcess(handle, ctypes.byref(code)):
                return 1
            return None if code.value == 259 else code.value
        finally:
            k.CloseHandle(handle)

    def terminate(self):
        if self.poll() is not None:
            return
        if os.name != "nt":
            os.kill(self.pid, 15)
            return
        k = _kernel()
        handle = k.OpenProcess(0x1001, False, self.pid)
        if not handle:
            raise OSError("Не удалось открыть процесс для остановки")
        try:
            if not k.TerminateProcess(handle, 0):
                raise ctypes.WinError(ctypes.get_last_error())
        finally:
            k.CloseHandle(handle)

    kill = terminate

    def wait(self, timeout=None):
        deadline = time.monotonic() + (timeout or 10)
        while time.monotonic() < deadline:
            code = self.poll()
            if code is not None:
                return code
            time.sleep(.05)
        raise subprocess.TimeoutExpired(str(self.pid), timeout)


class PresenceManager:
    def __init__(self, library: Library, logger=None, package_root=None, spawn=None,
                 clock: Callable[[], float] = time.time, runtime_path=None):
        self.library = library
        self.log = logger or get_logger()
        self.package_root = (Path(package_root) if package_root else
                             Path(sys.executable).resolve().parent if getattr(sys, "frozen", False)
                             else Path(__file__).resolve().parents[1]).resolve()
        self._spawn = spawn or _default_spawn
        self._clock = clock
        self.runtime_path = Path(runtime_path) if runtime_path else self.package_root / "runtime.json"
        self._instance = None
        self._lock = threading.RLock()
        self._control = threading.Lock()
        self._last_error = None
        self._operation = None
        #: Worker-log read offsets, so a status read only parses what was appended.
        self._log_cursor: dict[str, int] = {}
        #: Derived RPC state per slug; see _rpc_state.
        self._rpc_cache: dict[str, dict] = {}
        self._adopt()

    def _adopt(self):
        try:
            payload = json.loads(self.runtime_path.read_text(encoding="utf-8"))
            if not isinstance(payload, dict):
                return
            pid, slug = payload.get("pid"), payload.get("slug")
            identity = payload.get("identity")
            if not isinstance(pid, int) or not isinstance(slug, str) or not self.library.get(slug):
                return
            # Legacy PID-only records are not authority to stop an arbitrary process.
            if not identity or process_identity(pid) != identity:
                return
            from .ui.inspect import process_image_path
            if process_image_path(pid) != payload.get("image_path"):
                return
            process = PidProcess(pid, identity)
            if process.poll() is None:
                self._instance = Instance(slug, pid, float(payload["started_at"]), process,
                                          "adopted", payload["image_path"], identity)
        except (OSError, ValueError, TypeError, KeyError):
            return

    def _find_external_worker(self, managed=(), windows=None):
        """A worker the user started by hand (double-clicking the game's exe).

        Such a process owns a visible window titled with the game name. Managed
        workers are skipped by pid **and by image path**, because a one-file
        PyInstaller build runs the real application as a child of its bootloader:
        the spawned pid and the pid that owns the window are different processes
        running the same file.

        ``windows`` overrides the enumeration, which keeps this testable without
        depending on the cache lifetime.
        """
        if os.name != "nt":
            return None

        by_title = {e.game_name.casefold(): e for e in self.library.entries() if e.executable}
        if not by_title:
            return None
        skip_pids = {worker.pid for worker in managed}
        skip_paths = {os.path.normcase(worker.image_path) for worker in managed if worker.image_path}
        for window in (windows if windows is not None else self._visible_windows()):
            if window.pid in skip_pids:
                continue
            entry = by_title.get(window.title.casefold())
            if entry is None:
                continue
            path = process_image_path_cached(window.pid)
            if not path:
                continue
            if os.path.normcase(path) in skip_paths:
                continue
            if os.path.basename(path).casefold() != entry.executable.casefold():
                continue
            return entry.slug, window.pid, path
        return None

    def _running_workers(self, windows=None):
        """Every worker currently running: the managed child plus any started by hand.

        Two can coexist — the user double-clicks a game's exe while the panel holds a
        session. Discord keeps only the most recent activity, so the caller must
        report the newest one rather than pretending there is a single session.
        """
        workers: list[Instance] = []
        with self._lock:
            instance = self._instance
        if instance is not None:
            if instance.process.poll() is None:
                workers.append(instance)
            else:
                code = instance.process.poll()
                detail = self._tail(
                    self.package_root / "logs" / f"{instance.slug}.startup.log", 2000).strip()
                with self._lock:
                    if self._instance is instance:
                        self._instance = None
                        if code:
                            self._last_error = f"Процесс завершился с кодом {code}. {detail[-700:]}"
                        self._forget_runtime()
                self.log.info("presence process exited",
                              extra={"slug": instance.slug, "pid": instance.pid, "code": code})
        external = self._find_external_worker(managed=workers, windows=windows)
        if external:
            slug, pid, path = external
            started = process_started_at(pid) or self._clock()
            workers.append(Instance(slug, pid, started, PidProcess(pid, process_identity(pid)),
                                    "external", path, process_identity(pid)))
        return workers

    def _remember_runtime(self, instance):
        payload = {key: getattr(instance, key) for key in
                   ("slug", "pid", "started_at", "reason", "image_path", "identity")}
        # Atomic: the dashboard reads this on startup, and a truncated record would
        # make it ignore a session that is still running.
        write_atomic(self.runtime_path, json.dumps(payload))

    def _forget_runtime(self):
        self.runtime_path.unlink(missing_ok=True)

    @property
    def active_slug(self):
        return (self.status().get("active") or {}).get("slug")

    def _tail(self, path: Path, size=16384):
        try:
            with path.open("rb") as stream:
                stream.seek(max(0, path.stat().st_size - size))
                return stream.read(size).decode("utf-8", "replace")
        except OSError:
            return ""

    def _tail_lines(self, path: Path, size=16384) -> str:
        """The end of a worker log, re-reading only what is new.

        Status reads happen every 1.5 seconds and each one used to re-read and
        re-parse the whole tail. Worker logs only ever grow between restarts, so the
        byte offset and the already-derived state are kept: a read that adds nothing
        costs nothing.

        A worker restart truncates the file — the size goes down, or the inode
        changes — which drops the cached offset, so a new worker's log is parsed from
        the beginning.
        """
        try:
            stat = path.stat()
        except OSError:
            self._log_cursor.pop(str(path), None)
            return ""

        if stat.st_size <= size:
            # Small enough to read whole; no point tracking an offset.
            self._log_cursor.pop(str(path), None)
            return self._tail(path, size)

        key = str(path)
        offset = self._log_cursor.get(key)
        if offset is None or offset > stat.st_size:
            offset = max(0, stat.st_size - size)

        try:
            with path.open("rb") as stream:
                stream.seek(offset)
                chunk = stream.read(max(0, stat.st_size - offset)).decode("utf-8", "replace")
        except OSError:
            self._log_cursor.pop(key, None)
            return ""

        self._log_cursor[key] = stat.st_size
        return chunk

    def _rpc_state(self, instance, chunk: str | None = None):
        """Derive the RPC state from a worker log, without redoing finished work.

        The log is read incrementally, so only newly appended lines are parsed. The
        derived state is kept as well: a read that adds no lines must still report the
        last known state rather than falling back to "connecting".

        A restart truncates the log. That shrinks the file, which resets both the read
        offset and the cached state, so a new worker is parsed from the beginning.

        ``chunk`` overrides the read, which keeps this testable: the caller supplies
        the log content instead of depending on cached file state.
        """
        slug = getattr(instance, "slug", "")
        path = self.package_root / "logs" / f"{instance.slug}.log"
        try:
            size = path.stat().st_size
        except OSError:
            size = -1

        cached = self._rpc_cache.get(slug) if chunk is None else None
        if cached is not None and cached.get("size", -1) > size:
            # Truncated: the worker restarted.
            cached = None
            self._rpc_cache.pop(slug, None)

        if cached is None:
            state, error, last_ack = "connecting", None, None
        else:
            state, error, last_ack = cached["state"], cached["error"], cached["ack"]

        if chunk is None:
            chunk = self._tail_lines(path, size=1 << 20)

        if chunk:
            for line in chunk.splitlines():
                try:
                    record = json.loads(line)
                except ValueError:
                    continue
                try:
                    if datetime.fromisoformat(record["ts"]).timestamp() < instance.started_at:
                        continue
                    event = record.get("event", "")
                    if event == "presence worker starting":
                        worker_pid = record.get("worker_pid")
                        identity = record.get("worker_identity")
                        if isinstance(worker_pid, int) and identity:
                            actual_path = process_image_path_cached(worker_pid)
                            if (actual_path and os.path.normcase(actual_path) == os.path.normcase(instance.image_path)
                                    and process_identity(worker_pid) == identity):
                                instance.worker_pid, instance.worker_identity = worker_pid, identity
                    if event == "presence set":
                        state, error, last_ack = "connected", None, record["ts"]
                    elif event in ("connection lost", "reconnecting", "refresh failed; reconnecting",
                                   "Discord IPC unavailable; will retry", "handshake failed; will retry",
                                   "connection error; will retry"):
                        state, error = "reconnecting", record.get("error") or record.get("reason")
                    elif record.get("level") == "ERROR":
                        state, error = "error", record.get("error") or event
                except (ValueError, KeyError, TypeError):
                    continue
            if chunk is not None:
                self._rpc_cache[slug] = {"state": state, "error": error, "ack": last_ack, "size": size}

        if state == "connecting" and self._clock() - instance.started_at > 30:
            error = "Процесс запущен, но RPC ещё не подтверждён. Проверьте настольный Discord."
        return state, error, last_ack

    def status(self):
        with self._lock:
            operation = dict(self._operation) if self._operation else None
        workers = self._running_workers()
        active = None
        if workers:
            # Discord keeps one activity, so the most recently started worker owns it.
            current = max(workers, key=lambda w: w.started_at)
            entry = self.library.get(current.slug)
            rpc, error, ack = self._rpc_state(current)
            active = {"slug": current.slug, "game_name": entry.game_name if entry else current.slug,
                      "pid": current.pid,
                      "uptime_s": round(max(0, self._clock() - current.started_at), 1),
                      "reason": current.reason, "rpc_state": rpc, "rpc_error": error,
                      "last_ack": ack, "image_path": current.image_path,
                      "also_running": len(workers) - 1}
        return {"active": active, "operation": operation, "queue": self.library.queue,
                "next_switch_in_s": self._seconds_until_switch(), "last_error": self._last_error,
                "games": [entry.to_dict() for entry in self.library.entries()]}

    def validate_entry(self, slug):
        if not isinstance(slug, str) or not re.fullmatch(r"[a-z0-9][a-z0-9-]{0,63}", slug):
            raise ManagerError("Некорректный идентификатор игры")
        entry = self.library.get(slug)
        if entry is None:
            raise ManagerError(f"Игра {slug!r} не найдена в библиотеке")
        if not entry.executable:
            raise ManagerError("Каталог не содержит executable для этой игры. Автоматический запуск недоступен.")
        try:
            validate_image_name(entry.executable)
            if not re.fullmatch(r"[0-9]{17,20}", entry.application_id or ""):
                raise ValueError("Application ID должен содержать 17–20 цифр")
            config = AppConfig(client_id=entry.application_id, game_name=entry.game_name,
                               details=entry.details, state=entry.state, activity_type=entry.activity_type)
            config.validate()
            from .rpc.supervisor import PresenceSupervisor
            PresenceSupervisor(config).build()
        except (ValueError, TypeError, worthlesstaskError) as exc:
            raise ManagerError(f"Проверьте параметры игры: {exc}") from exc
        if not self.package_root.is_dir() or not self.library.path.is_file():
            raise ManagerError("Не найдена папка приложения или файл библиотеки")
        return entry

    def prepare(self, slug):
        """Build the worker executable for a game so a later launch is instant.

        Called right after a game is added, so the file the process image must match
        already exists by the time the user presses Запустить.
        """
        with self._lock:
            if self._operation:
                raise ManagerError("Дождитесь завершения запуска или остановки")
        entry = self.validate_entry(slug)
        try:
            interpreter = ensure_decoy(entry.executable, logger=self.log,
                                       client_id=entry.application_id)
            if not interpreter.is_file():
                raise ManagerError(f"EXE не найден: {interpreter}")
            with interpreter.open("rb") as stream:
                if stream.read(2) != b"MZ":
                    raise ManagerError("Подготовленный файл не является Windows EXE")
        except (worthlesstaskError, OSError, ValueError) as exc:
            self.library.update(slug, worker_ready=False, worker_error=str(exc))
            self.log.warning("worker executable not prepared", extra={"slug": slug, "error": str(exc)})
            raise ManagerError(str(exc)) from exc
        self.library.update(slug, worker_ready=True, worker_error=None, worker_path=str(interpreter))
        self.log.info("worker executable ready", extra={"slug": slug, "path": str(interpreter)})
        return interpreter

    def _begin(self, kind, slug=None, asynchronous=False, reason="manual"):
        with self._lock:
            if self._operation:
                if self._operation["kind"] == kind and self._operation["slug"] == slug:
                    return self.status()
                raise ManagerError("Другая операция ещё выполняется. Дождитесь её завершения.")
            if kind == "start" and self._instance and self._instance.slug == slug and self._instance.process.poll() is None:
                return self.status()
            if kind == "start":
                self.validate_entry(slug)
            self._operation = {"kind": kind, "slug": slug, "status": "pending"}
            self._last_error = None
        def execute():
            try:
                with self._control:
                    if kind == "start":
                        entry = self.validate_entry(slug)
                        interpreter = ensure_decoy(entry.executable, logger=self.log,
                                                   client_id=entry.application_id)
                        if not interpreter.is_file():
                            raise ManagerError(f"EXE не найден: {interpreter}")
                        with interpreter.open("rb") as stream:
                            if stream.read(2) != b"MZ":
                                raise ManagerError("Подготовленный файл не является Windows EXE")
                        self.library.update(slug, worker_ready=True, worker_error=None,
                                            worker_path=str(interpreter))
                        self._stop_current()
                        instance = self._spawn_presence(entry, reason, interpreter)
                        with self._lock:
                            self._instance = instance
                            self._remember_runtime(instance)
                    else:
                        self._stop_current()
            except Exception as exc:
                self.log.exception("process operation failed")
                with self._lock:
                    self._last_error = str(exc)
                if not asynchronous:
                    if isinstance(exc, ManagerError):
                        raise
                    raise ManagerError(str(exc)) from exc
            finally:
                with self._lock:
                    self._operation = None
        if asynchronous:
            threading.Thread(target=execute, name="process-control", daemon=True).start()
        else:
            execute()
        # Process state just changed: memoised windows and process facts are stale,
        # and any worker log we had been reading belongs to the previous worker.
        reset_process_caches()
        with self._lock:
            self._log_cursor.clear()
            self._rpc_cache.clear()
        return self.status()

    def play(self, slug, reason="manual"):
        return self._begin("start", slug, reason=reason)

    def request_play(self, slug):
        return self._begin("start", slug, asynchronous=True)

    def stop(self, reason="manual"):
        return self._begin("stop", reason=reason)

    def request_stop(self):
        return self._begin("stop", asynchronous=True)

    def _spawn_presence(self, entry, reason, interpreter):
        logs = self.package_root / "logs"
        logs.mkdir(exist_ok=True)
        argv = ([str(interpreter), "--worker"] if getattr(sys, "frozen", False)
                else [str(interpreter), "-m", "worthlesstask", "presence"])
        argv += ["--slug", entry.slug, "--library", str(self.library.path.resolve()),
                 "--icons", str(self.library.icons_dir.resolve()), "--log-file", str(logs / f"{entry.slug}.log")]
        if getattr(entry, "epic_app_id", None):
            argv.append(f"-epicapp={entry.epic_app_id}")
        env = dict(os.environ)
        env["PYTHONPATH"] = os.pathsep.join([str(self.package_root), env.get("PYTHONPATH", "")])
        # Each one-file worker must own its extraction directory, not reuse its parent's.
        if getattr(sys, "frozen", False):
            env["PYINSTALLER_RESET_ENVIRONMENT"] = "1"
        started = self._clock()
        process = self._spawn(argv, env, self.package_root)
        return Instance(entry.slug, process.pid, started, process, reason,
                        str(interpreter.resolve()), process_identity(process.pid))

    def _stop_current(self):
        """Stop every running worker, including one the user started by hand."""
        for worker in self._running_workers():
            self._terminate(worker)
        with self._lock:
            self._instance = None
            self._forget_runtime()

    def _visible_windows(self):
        """Every top-level window, memoised for one interval.

        Enumerating windows walks the whole shell window list. A single status read
        can ask twice, and the dashboard asks every 1.5s, so the result is reused for
        a fraction of a second. Mutations clear it.

        The cache is keyed on the enumeration function as well: patching it — as the
        tests do — swaps in a different object, so a patched enumeration is never
        answered from a previous, real one.
        """
        from .ui import inspect as inspect_module

        visible_windows = inspect_module.visible_windows
        key = (id(visible_windows), getattr(visible_windows, "__module__", ""))
        cached = _window_cache.get() if _window_cache.key == key else None
        if cached is not None:
            return cached
        _window_cache.key = key
        return _window_cache.set(visible_windows())

    def _close_windows_of(self, instance):
        """Ask every window belonging to this worker to close.

        Matched by image path, not pid: a one-file PyInstaller worker runs the real
        application as a child of its bootloader, so the window is owned by a
        different process than the one that was spawned. Closing the window is the
        clean shutdown — the child then exits on its own.
        """
        from .ui.inspect import process_image_path, visible_windows

        wanted = os.path.normcase(instance.image_path) if instance.image_path else None
        posted = 0
        for window in visible_windows():
            if wanted and os.path.normcase(process_image_path(window.pid) or "") != wanted:
                continue
            _user32.PostMessageW(window.hwnd, WM_CLOSE, 0, 0)
            posted += 1
        return posted

    def _terminate(self, instance):
        process = instance.process
        if process.poll() is not None:
            return
        try:
            if os.name == "nt" and self._close_windows_of(instance):
                try:
                    process.wait(timeout=5)
                    return
                except subprocess.TimeoutExpired:
                    pass
            process.terminate()
            process.wait(timeout=5)
        except subprocess.TimeoutExpired:
            process.kill()
            process.wait(timeout=5)

    def clear_session(self):
        """Stop every worker and forget the session record.

        Different from :meth:`stop`: nothing is left behind — the runtime file and the
        last error are cleared, so the panel returns to a clean state.
        """
        self._stop_current()
        with self._lock:
            self._last_error = None
            self._operation = None
        self._forget_runtime()
        self.log.info("session cleared")
        return self.status()

    def set_queue(self, slugs):
        if not isinstance(slugs, list) or any(not isinstance(s, str) for s in slugs):
            raise ManagerError("Очередь должна быть списком игр")
        for slug in slugs:
            self.validate_entry(slug)
        return self.library.set_queue(list(dict.fromkeys(slugs)))

    def _seconds_until_switch(self):
        instance = self._instance
        if not instance or not self.library.queue:
            return None
        entry = self.library.get(instance.slug)
        if not entry:
            return None
        return round(max(0, entry.duration_minutes*60 - (self._clock()-instance.started_at)), 1)

    def advance(self, reason="queue"):
        queue = self.library.queue
        if not queue:
            return None
        current = self.active_slug
        nxt = queue[(queue.index(current)+1) % len(queue)] if current in queue else queue[0]
        if nxt == current:
            self.stop()
        return self.play(nxt, reason=reason)

    def tick(self):
        remaining = self._seconds_until_switch()
        if remaining is not None and remaining <= 0 and not self._operation:
            return self.advance()
        return None

    def run_scheduler(self, stop_event):
        """Advance the rotation until asked to stop or something breaks.

        An unexpected exception used to kill this thread silently: the panel kept
        reporting a running queue that was no longer advancing. Now every failure is
        recorded, the scheduler stops, and the reason is visible.
        """
        while not stop_event.wait(SCHEDULER_INTERVAL):
            try:
                self.tick()
            except worthlesstaskError as exc:
                # An expected, explainable failure: stop and report it.
                with self._lock:
                    self._last_error = str(exc)
                self.log.warning("queue stopped", extra={"error": str(exc)})
                stop_event.set()
            except Exception as exc:  # noqa: BLE001 - a scheduler must never die quietly
                with self._lock:
                    self._last_error = f"Очередь остановлена: {type(exc).__name__}: {exc}"
                self.log.exception("queue scheduler failed", extra={"error": str(exc)})
                stop_event.set()
