"""Make the presence process look like the game's own executable.

Discord matches a running process against the catalogue's ``executables`` entry,
so the presence has to be reported by a process whose image name is that
executable. A copy of the interpreter renamed to the target works, provided it
sits in the interpreter's own directory next to ``python3xx.dll`` so it still
finds its stdlib.

The catalogue stores executables as relative paths (``win64/marvel-win64-shipping.exe``)
and matches them as a *suffix of the running process path*, not by bare file name.
For frozen builds the worker copy therefore lands in the catalogue's subdirectory
when one is listed; a flat copy goes completely unseen for such games, which is
why Marvel Rivals never started a detection session. Source builds keep the
worker flat beside the interpreter's stdlib and rely on bare-name entries.
"""

from __future__ import annotations

import hashlib
import json
import re
import logging
import os
import sys
from pathlib import Path

from .core.logging import get_logger
from .paths import cache_dir, is_frozen, package_root, worker_dir
from .presence.resolver import DetectableIndex


def executable_name_for(client_id: str, logger: logging.Logger | None = None) -> str | None:
    """The catalogue's expected image name for an application id."""
    log = logger or get_logger()
    index = DetectableIndex(cache_path=cache_dir() / "detectable.json", logger=log)
    candidate = index.by_id(client_id)
    if candidate and candidate.executables:
        first = candidate.executables[0].replace("\\", "/")
        return first.rsplit("/", 1)[-1]
    if candidate is not None:
        from .presence.quests import resolve_bypass_plan
        plan = resolve_bypass_plan(client_id, candidate.name, index=index, logger=log)
        if plan.bypass_mode != "derived" and plan.image_name:
            return plan.image_name
    return None


def validate_image_name(image_name: str) -> str:
    if (not isinstance(image_name, str) or len(image_name) > 180
            or not re.fullmatch(r"[A-Za-z0-9][A-Za-z0-9_. '\-!()+]*\.exe", image_name, re.IGNORECASE)
            or ".." in image_name
            or image_name.split(".")[0].upper() in {"CON", "PRN", "AUX", "NUL", *(f"COM{i}" for i in range(10)), *(f"LPT{i}" for i in range(10))}):
        raise ValueError("Ожидается имя .exe без пути и командных символов")
    return image_name


def derive_image_name(game_name: str) -> str:
    """Invent an executable name for a game the catalogue does not publish one for.

    Discord matches a running process against its own catalogue, so a derived name is
    a guess: the presence and the window will work, but detection is only guaranteed
    when the name matches what the real game ships. The user can override it.
    """
    stem = re.sub(r"[^a-z0-9]+", "", str(game_name).casefold())[:120]
    return f"{stem or 'game'}.exe"


def _valid_subdir_prefix(prefix: str) -> bool:
    if not prefix or len(prefix) > 180 or ".." in prefix:
        return False
    for segment in prefix.split("/"):
        if not segment or segment in {".", ".."}:
            return False
        if not re.fullmatch(r"[A-Za-z0-9_. '\-!()+]{1,120}", segment):
            return False
    return True


def catalogue_subdir_for(image_name: str, client_id: str | None,
                         logger: logging.Logger | None = None) -> str:
    """The directory prefix Discord expects in front of the image name.

    The catalogue lists executables as relative paths and the detector matches the
    whole suffix, so a game whose every entry carries a directory (Marvel Rivals:
    ``win64/marvel-win64-shipping.exe``) is only detected when the process path
    really ends with that directory. Returns the first matching prefix, or an
    empty string when the catalogue lists the bare name (``wwm.exe`` matches
    anywhere) or knows nothing about the id.
    """
    if not client_id or not re.fullmatch(r"[0-9]{17,20}", str(client_id)):
        return ""
    log = logger or get_logger()
    index = DetectableIndex(cache_path=cache_dir() / "detectable.json", logger=log)
    candidate = index.by_id(client_id)
    wanted = str(image_name).casefold()
    matched_in_candidate = False
    if candidate:
        for raw in candidate.executables:
            parts = str(raw).replace("\\", "/").lstrip(">").split("/")
            if parts[-1].casefold() == wanted:
                matched_in_candidate = True
                if len(parts) > 1:
                    prefix = "/".join(parts[:-1])
                    if _valid_subdir_prefix(prefix):
                        return prefix
        if matched_in_candidate:
            return ""
    # Carrier fallback: when a game has no executables of its own (e.g. EA SPORTS FC 27)
    # and uses a franchise/carrier executable from another detectable entry, preserve
    # the carrier's required directory suffix so Discord's process scanner matches it.
    for entry in index.entries():
        raw_list = entry.get("executables") if isinstance(entry, dict) else getattr(entry, "executables", ())
        for raw in raw_list or ():
            name = raw.get("name") if isinstance(raw, dict) else raw
            if not name:
                continue
            parts = str(name).replace("\\", "/").lstrip(">").split("/")
            if len(parts) > 1 and parts[-1].casefold() == wanted:
                prefix = "/".join(parts[:-1])
                if _valid_subdir_prefix(prefix):
                    return prefix
    return ""


def decoy_path(
    image_name: str,
    client_id: str | None = None,
    *,
    subdir_override: str | None = None,
) -> Path:
    validate_image_name(image_name)
    # Source builds must keep the copy beside the interpreter's stdlib, so the
    # catalogue subdirectory is honoured only in frozen builds — the ones whose
    # workers are self-contained and can run from anywhere.
    subdir = ""
    if is_frozen():
        if subdir_override:
            norm = str(subdir_override).replace("\\", "/").lstrip(">").strip("/")
            if "/" in norm and norm.lower().endswith(".exe"):
                norm = norm.rsplit("/", 1)[0]
            elif norm.lower().endswith(".exe"):
                norm = ""
            if norm and _valid_subdir_prefix(norm):
                subdir = norm
        if not subdir:
            subdir = catalogue_subdir_for(image_name, client_id)
    base = worker_dir()
    return base / subdir / image_name if subdir else base / image_name


def current_image_name() -> str:
    return Path(sys.executable).resolve().name


def is_running_as(image_name: str) -> bool:
    return current_image_name().casefold() == image_name.casefold()


def is_blank(path: Path) -> bool:
    """True when a file is nothing but zero bytes.

    Killing a worker mid-copy leaves a correctly sized file filled with zeros. That can
    never be somebody's real program, so it is safe to treat as our own damaged output
    rather than refusing to touch it.
    """
    try:
        with path.open("rb") as stream:
            while chunk := stream.read(1 << 20):
                if chunk.strip(b"\x00"):
                    return False
    except OSError:
        return False
    return True


def write_marker(target: Path, digest: str) -> None:
    """Record the hash of a worker we wrote, atomically.

    A marker damaged by an interrupted write is worse than no marker: it makes the file
    look foreign, and :func:`ensure_decoy` then refuses to touch it. Write through a
    temp file so the marker is either the old one or the new one, never a fragment.
    """
    marker = target.with_suffix(".worthlesstask.json")
    temp = marker.with_name(marker.name + ".writing")
    temp.write_text(json.dumps({"sha256": digest}), encoding="utf-8")
    os.replace(temp, marker)


def _open_exclusive(path: Path) -> int:
    """Open ``path`` for writing, failing if anything is already there.

    ``O_CREAT|O_EXCL`` is the atomic primitive: it fails when the path exists, and it
    never follows a link that resolves elsewhere. That is the difference from
    ``shutil.copy2``, which opens an existing path for writing and therefore writes
    through a symlink to wherever it points.

    The worker folder is user-writable, so a link planted there would otherwise let a
    prepared copy land on any file the user can write.
    """
    flags = os.O_WRONLY | os.O_CREAT | os.O_EXCL
    flags |= getattr(os, "O_BINARY", 0)
    flags |= getattr(os, "O_NOFOLLOW", 0)
    return os.open(str(path), flags)


def write_worker(source: Path, target: Path) -> None:
    """Copy ``source`` to ``target`` atomically and without following links.

    The content is written to a sibling temp file created exclusively, fsynced, then
    moved into place. A reader therefore sees either the old worker or the new one,
    never a half-written executable — and an interrupted copy cannot leave the
    zero-filled file that used to need special handling downstream.
    """
    temp = target.with_name(target.name + ".copy")
    fd = _open_exclusive(temp)
    try:
        with open(source, "rb") as stream:
            while chunk := stream.read(1 << 20):
                os.write(fd, chunk)
        os.fsync(fd)
    except BaseException:
        os.close(fd)
        try:
            os.unlink(temp)
        except OSError:
            pass
        raise
    os.close(fd)
    try:
        # Re-checked immediately before the rename: the path may have been swapped
        # while the copy was being written. Renaming onto a link would put the file
        # wherever it points.
        if target.is_symlink():
            raise ValueError(f"Нельзя записать EXE через символическую ссылку: {target}")
        os.replace(temp, target)
    except BaseException:
        try:
            os.unlink(temp)
        except OSError:
            pass
        raise


def ensure_decoy(
    image_name: str,
    logger: logging.Logger | None = None,
    client_id: str | None = None,
    *,
    subdir_override: str | None = None,
) -> Path:
    """Return a path to an interpreter copy named ``image_name``.

    Re-copies only when the source interpreter is newer or the copy is missing.

    A path that already holds something we did not write is never overwritten: the
    hash and the ownership marker decide, and a link is refused outright.
    """
    validate_image_name(image_name)
    log = logger or get_logger()
    source = Path(sys.executable).resolve()
    if source.name.casefold() == image_name.casefold():
        return source
    target = (
        decoy_path(image_name, client_id, subdir_override=subdir_override)
        if subdir_override
        else decoy_path(image_name, client_id)
    )
    target.parent.mkdir(parents=True, exist_ok=True)
    marker = target.with_suffix(".worthlesstask.json")
    def digest(path):
        with path.open("rb") as stream:
            return hashlib.file_digest(stream, "sha256").hexdigest()
    expected = digest(source)
    if target.is_symlink():
        raise ValueError("Нельзя использовать символическую ссылку вместо EXE")
    if target.exists():
        actual = digest(target)
        if actual == expected:
            return target
        try:
            owned = json.loads(marker.read_text(encoding="utf-8"))
        except (OSError, ValueError):
            owned = {}
        if owned.get("sha256") != actual:
            if not is_blank(target):
                raise ValueError(f"Файл уже существует и не принадлежит worthlesstask: {target}")
            log.warning("replacing a zero-filled worker left by an interrupted copy",
                        extra={"path": str(target)})
    write_worker(source, target)
    write_marker(target, expected)
    log.info("worker executable prepared", extra={"path": str(target)})
    return target


def discard_decoy(image_name: str, logger: logging.Logger | None = None,
                  client_id: str | None = None) -> bool:
    """Delete a worker copy this program created, and its ownership marker.

    Removing a game must not leave a 9 MB executable behind, but a file is only
    deleted when the marker proves we wrote it — anything else is left alone.
    """
    validate_image_name(image_name)
    log = logger or get_logger()
    target = decoy_path(image_name, client_id)
    marker = target.with_suffix(".worthlesstask.json")
    if not target.exists():
        marker.unlink(missing_ok=True)
        return False
    if target.is_symlink():
        log.warning("refusing to delete through a symbolic link", extra={"path": str(target)})
        return False
    try:
        with target.open("rb") as stream:
            actual = hashlib.file_digest(stream, "sha256").hexdigest()
        owned = json.loads(marker.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        log.warning("refusing to delete a file with no ownership marker",
                    extra={"path": str(target)})
        return False
    if owned.get("sha256") != actual:
        log.warning("refusing to delete a file we did not write",
                    extra={"path": str(target)})
        return False
    if target.is_symlink():
        # Re-checked after the marker read: the path could have been swapped while we
        # were verifying. Deleting through a link would remove someone else's file.
        log.warning("refusing to delete a path that became a link",
                    extra={"path": str(target)})
        return False
    try:
        target.unlink()
    except OSError as exc:
        log.warning("worker executable not removed", extra={"path": str(target), "error": str(exc)})
        return False
    marker.unlink(missing_ok=True)
    log.info("worker executable removed", extra={"path": str(target)})
    return True


def relaunch_argv(path: Path, config_path: str | None, extra: list[str] | None = None,
                  frozen: bool | None = None) -> list[str]:
    """argv for re-executing this package under the decoy interpreter.

    A packaged executable cannot run ``-m worthlesstask``: its entry point only
    understands ``--worker`` (which maps to the ``presence`` command) or no
    arguments at all. Passing ``-m`` to a frozen build made ``launch`` re-exec into
    an unrecognised argument and never open the window.
    """
    if frozen is None:
        frozen = is_frozen()
    return decoy_run_argv(path, config_path, frozen=frozen, window=True) + (extra or [])


def reexec(path: Path, argv: list[str], package_root: Path) -> None:
    """Replace the current process with ``path`` running ``argv``.

    ``PYTHONPATH`` is set so ``-m worthlesstask`` resolves regardless of the caller's
    working directory. On Windows this is a spawn + exit, so the resulting process
    image really is the decoy.
    """
    existing = os.environ.get("PYTHONPATH", "")
    parts = [str(package_root)] + ([existing] if existing else [])
    os.environ["PYTHONPATH"] = os.pathsep.join(parts)
    os.execv(str(path), argv)


def decoy_run_argv(path: Path, config_path: str | None, frozen: bool | None = None,
                  window: bool = True) -> list[str]:
    """argv that runs the decoy in single-game (config-driven) mode.

    A decoy started on its own — by a logon task, or by ``launch`` re-execing — has
    no library and no slug; it has a config file. In a packaged build the decoy is a
    full copy of the program, so it takes ``--worker`` directly. From source it is a
    copy of the interpreter, which needs ``-m worthlesstask`` to find the package.
    """
    if frozen is None:
        frozen = is_frozen()
    if frozen:
        argv = [str(path), "--worker"]
    else:
        argv = [str(path), "-m", "worthlesstask", "presence"]
    if config_path:
        argv += ["--config", str(config_path)]
    if window:
        argv.append("--window")
    return argv


DEFAULT_TASK_NAME = "worthlesstask"


#: schtasks accepts almost anything as a task name, and an unvalidated one lets a
#: caller smuggle extra switches into the command line.
TASK_NAME_RE = re.compile(r"^[A-Za-z0-9][A-Za-z0-9 _.-]{0,63}$")


def validate_task_name(task_name: str) -> str:
    """Reject anything that is not a plain task name.

    The name is interpolated into a ``schtasks /tn`` command line. Without this, a
    value containing quotes or spaces could add switches to the command.
    """
    name = str(task_name or "")
    if not TASK_NAME_RE.fullmatch(name):
        raise ValueError(
            f"invalid task name {task_name!r}: use letters, digits, spaces, dots, "
            f"hyphens and underscores only"
        )
    return name


def logon_task_command(
    decoy_path: Path,
    task_name: str = DEFAULT_TASK_NAME,
    window: bool = True,
    config_path: str | None = None,
    frozen: bool | None = None,
) -> list[str]:
    """argv for ``schtasks`` that starts the presence at logon.

    The program is the *decoy* — a copy named after the game's executable — never the
    plain interpreter. Running ``python.exe`` would publish the presence while
    Discord's process and window scanner saw no matching process, so the game would
    never be registered and a quest would not be credited.

    The arguments come from :func:`decoy_run_argv`, so a packaged decoy gets
    ``--worker`` and a source one gets ``-m worthlesstask``.
    """
    validate_task_name(task_name)
    argv = decoy_run_argv(decoy_path, config_path, frozen=frozen, window=window)

    # Quote every interpolated part: a path with a space would otherwise split into
    # separate arguments.
    def quote(part) -> str:
        text = str(part)
        return f'"{text}"' if (" " in text or '"' in text) else text

    inner = " ".join(quote(part) for part in argv)
    return [
        "schtasks", "/create",
        "/tn", task_name,
        "/sc", "onlogon",
        "/tr", f"cmd /c {inner}",
        "/f",
    ]


def remove_task_command(task_name: str = DEFAULT_TASK_NAME) -> list[str]:
    return ["schtasks", "/delete", "/tn", validate_task_name(task_name), "/f"]


def quote_for_display(argv: list[str]) -> str:
    """Render an argv the way it must be typed into cmd.exe (inner quotes escaped)."""
    return " ".join(
        f'"{part.replace(chr(34), chr(92) + chr(34))}"' if " " in part else part
        for part in argv
    )
