"""Find where Steam actually installed a game, and which executables are inside.

Discord publishes *several* executable names per application and the first one is
often a build variant (`-shipping`, `-egs`, a VR binary). Picking blindly can name
the decoy after a file the real install does not have. Reading the install
directory gives the authoritative answer, so the decoy matches what is on disk.
"""

from __future__ import annotations

import logging
import os
import re
from pathlib import Path

from .core.logging import get_logger

DEFAULT_STEAM_ROOTS = (
    Path("C:/Program Files (x86)/Steam"),
    Path("C:/Program Files/Steam"),
    Path.home() / ".steam" / "steam",
    Path.home() / "Library" / "Application Support" / "Steam",
)

_PATH_LINE = re.compile(r'"path"\s+"([^"]+)"')
_INSTALLDIR_LINE = re.compile(r'"installdir"\s+"([^"]+)"')
_LIBRARYFOLDERS = "steamapps/libraryfolders.vdf"


def library_roots(steam_root: Path | None = None) -> list[Path]:
    """Every Steam library folder, including extra drives from libraryfolders.vdf."""
    roots: list[Path] = []
    candidates = [steam_root] if steam_root else list(DEFAULT_STEAM_ROOTS)
    for base in candidates:
        if base is None or not base.is_dir():
            continue
        if base not in roots:
            roots.append(base)
        manifest = base / _LIBRARYFOLDERS
        try:
            text = manifest.read_text(encoding="utf-8", errors="replace")
        except OSError:
            continue
        for raw in _PATH_LINE.findall(text):
            path = Path(raw.replace("\\\\", "/"))
            if path.is_dir() and path not in roots:
                roots.append(path)
    return roots


def install_dir(app_id: str, roots: list[Path] | None = None) -> Path | None:
    """The folder Steam installed an application into, from its appmanifest."""
    if not app_id or not str(app_id).isdigit():
        return None
    for root in roots if roots is not None else library_roots():
        manifest = root / "steamapps" / f"appmanifest_{app_id}.acf"
        try:
            text = manifest.read_text(encoding="utf-8", errors="replace")
        except OSError:
            continue
        match = _INSTALLDIR_LINE.search(text)
        if not match:
            continue
        folder = root / "steamapps" / "common" / match.group(1)
        if folder.is_dir():
            return folder
    return None


def installed_executables(app_id: str, depth: int = 3, limit: int = 400) -> set[str]:
    """Lower-cased exe basenames present in a game's install folder."""
    folder = install_dir(app_id)
    if folder is None:
        return set()
    found: set[str] = set()
    root_depth = len(folder.parts)
    for current, dirs, files in os.walk(folder):
        if len(Path(current).parts) - root_depth >= depth:
            dirs[:] = []
        for name in files:
            if name.casefold().endswith(".exe"):
                found.add(name.casefold())
                if len(found) >= limit:
                    return found
    return found


def pick_executable(catalogue_names: list[str], installed: set[str]) -> tuple[str | None, str]:
    """Choose the catalogue name to use, and say where the choice came from.

    Order of preference: a name that exists in the real install, then the plainest
    catalogue name (a build variant is a poor default), then nothing.
    """
    names = [str(n).replace("\\", "/").rsplit("/", 1)[-1].strip() for n in catalogue_names if n]
    names = [n for n in names if n]
    if not names:
        return None, "derived"
    if installed:
        for name in names:
            if name.casefold() in installed:
                return name, "installed"
    return _plainest(names), "catalogue"


#: Never the game itself — installers, crash handlers, anti-cheat, test builds.
_NEVER = (
    "installer", "setup", "unins", "crashhandler", "crashreport", "redist", "vcredist",
    "dxsetup", "anticheat", "epiconlineservices", "launcher", "-test", "-server",
    "dedicatedserver", "helper", "report",
)
#: Real game binaries for Unreal titles carry these; a bare name usually does not.
_VARIANT = ("-shipping", "shipping", "win64", "win32")
#: Acceptable, but only when nothing better exists.
_SOFT = ("vr", "egs")


def _plainest(names: list[str]) -> str:
    """Best guess when the game is not installed and the install cannot decide.

    Drop anything that is plainly not the game, then prefer an Unreal-style
    ``-shipping`` binary over a bare or variant name.
    """
    usable = [n for n in names if not any(t in n[:-4].casefold() for t in _NEVER)]
    pool = usable or names

    def rank(name: str) -> tuple[int, int, int, str]:
        stem = name[:-4].casefold()
        soft = sum(token in stem for token in _SOFT)
        not_unreal = 0 if any(token in stem for token in _VARIANT) else 1
        return (soft, not_unreal, len(stem), stem)

    return sorted(pool, key=rank)[0]


def resolve_image_name(
    game_name: str,
    app_id: str | None,
    catalogue_names: list[str] | None = None,
    logger: logging.Logger | None = None,
) -> tuple[str | None, str]:
    """The executable name to impersonate, and where that choice came from.

    Discord lists several executables per game and the first is often not the game —
    a launcher, a VR build, an installer. The multi-game flow already preferred a name
    that exists in the real Steam install; the single-game ``launch`` command took
    ``catalogue[0]`` and could therefore name a file Discord would never match, so the
    presence looked right while no quest was credited.

    Both entry points now go through here. Falls back to a name derived from the title
    when the catalogue publishes nothing, which is a guess but a launchable one.
    """
    names = [str(n) for n in (catalogue_names or []) if n]
    if names:
        installed: set[str] = set()
        if app_id:
            try:
                installed = installed_executables(app_id)
            except OSError as exc:
                if logger:
                    logger.debug("steam install not readable", extra={"error": str(exc)})
        chosen, source = pick_executable(names, installed)
        if chosen:
            return chosen, source
    if game_name:
        from .decoy import derive_image_name

        return derive_image_name(game_name), "derived"
    return None, "derived"


def describe(app_id: str, logger: logging.Logger | None = None) -> dict:
    """Small diagnostic view, used by the CLI and tests."""
    log = logger or get_logger()
    folder = install_dir(app_id)
    log.debug("steam install lookup", extra={"app_id": app_id, "folder": str(folder) if folder else None})
    return {"app_id": app_id, "install_dir": str(folder) if folder else None,
            "executables": sorted(installed_executables(app_id))}
