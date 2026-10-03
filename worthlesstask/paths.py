"""Where runtime data lives.

The dashboard writes a lot next to the executable: the game library, worker
executables, icons, logs and the runtime session record. Under ``Program Files``
that is not writable for a standard user, so an installed build keeps all mutable
state under ``%LOCALAPPDATA%`` instead. A portable build — one folder holding the
executable — keeps everything beside it, which is what makes the folder movable.
"""

from __future__ import annotations

import os
import sys
from pathlib import Path

APP_NAME = "worthlesstask"


def is_frozen() -> bool:
    return bool(getattr(sys, "frozen", False))


def package_root() -> Path:
    """The directory the program runs from."""
    if is_frozen():
        return Path(sys.executable).resolve().parent
    return Path(__file__).resolve().parents[1]


def appdata_root() -> Path:
    """Per-user writable root, used by installed builds."""
    if os.name == "nt":
        base = os.environ.get("LOCALAPPDATA") or os.environ.get("APPDATA")
        if base:
            return Path(base) / APP_NAME
        return Path.home() / "AppData" / "Local" / APP_NAME
    return Path.home() / ".local" / "share" / APP_NAME.lower()


def data_root() -> Path:
    """Root for everything the program writes.

    Installed builds: ``%LOCALAPPDATA%\\worthlesstask``.
    Portable and source builds: the folder the executable lives in.
    """
    return _ensure(appdata_root()) if is_frozen() else _ensure(package_root())


def _ensure(path: Path) -> Path:
    path.mkdir(parents=True, exist_ok=True)
    return path


def data_dir(name: str) -> Path:
    return _ensure(data_root() / name)


def worker_dir() -> Path:
    """Where worker executables are written.

    Frozen workers are self-contained: the one-file bootloader extracts its own
    dependencies, so a copy runs from anywhere. Source workers are copies of
    ``python.exe`` and must stay beside the interpreter to find their stdlib.
    """
    return data_dir("workers") if is_frozen() else package_root()


def log_dir() -> Path:
    return data_dir("logs")


def cache_dir() -> Path:
    return data_dir(".cache")


def default_library_path() -> Path:
    return data_root() / "library.json"


def default_icons_dir() -> Path:
    return data_dir("icons")
