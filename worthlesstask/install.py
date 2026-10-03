"""Install, update and remove a deployed copy of worthlesstask.

The program is a single executable plus one renamed copy per game. Installing it
means copying that folder somewhere stable and giving the user a shortcut, which
the program can do for itself — no second installer technology needed.

Two targets:

``Program Files``
    Machine-wide. Needs elevation; the command says so plainly when it is missing
    instead of failing halfway.
``%LOCALAPPDATA%\\Programs\\worthlesstask``
    Per-user, always writable, no elevation.

Neither target holds mutable data: the library, icons, logs, worker executables
and the session record all live under ``%LOCALAPPDATA%\\worthlesstask``
(see :mod:`worthlesstask.paths`), so a Program Files install stays read-only.
"""

from __future__ import annotations

import os
import shutil
import subprocess
import sys
from dataclasses import dataclass
from pathlib import Path

from . import __version__
from .paths import APP_NAME, appdata_root, is_frozen, package_root

SHORTCUT_NAME = f"{APP_NAME}.lnk"
UNINSTALL_KEY = r"Software\Microsoft\Windows\CurrentVersion\Uninstall\worthlesstask"


class InstallError(RuntimeError):
    """An install step failed in a way the user can act on."""


@dataclass
class InstallPaths:
    target: Path
    exe: Path
    per_user: bool


KNOWN_FOLDERS = {
    "roaming": "{3EB685DB-65F9-4CF6-A03A-E3EF65729F3D}",
    "local": "{F1B32785-6FBA-4FCF-9D55-7B8E7F157091}",
    "programs": "{0139D44E-6AFE-49F2-8690-3DAFCAE6FFB8}",   # Start Menu\Programs
    "desktop": "{B4BFCC3A-DB2C-424C-B029-7FE99A87C641}",
}


def known_folder(name: str) -> Path:
    """A real Windows folder path, without trusting the environment.

    ``APPDATA`` and ``ProgramFiles`` are not always present in the process that
    launches an installer, and a wrong guess silently puts shortcuts where nobody
    looks. The shell knows the answer, so ask it.
    """
    fallback = {
        "roaming": Path(os.environ.get("APPDATA", str(Path.home() / "AppData" / "Roaming"))),
        "local": Path(os.environ.get("LOCALAPPDATA", str(Path.home() / "AppData" / "Local"))),
        "programs": Path(os.environ.get("APPDATA", str(Path.home() / "AppData" / "Roaming")))
                    / "Microsoft" / "Windows" / "Start Menu" / "Programs",
        "desktop": Path(os.environ.get("USERPROFILE", str(Path.home()))) / "Desktop",
    }[name]
    if os.name != "nt":
        return fallback
    try:
        import ctypes
        from ctypes import wintypes

        class GUID(ctypes.Structure):
            _fields_ = [("Data1", wintypes.DWORD), ("Data2", wintypes.WORD),
                        ("Data3", wintypes.WORD), ("Data4", ctypes.c_ubyte * 8)]

        hexed = KNOWN_FOLDERS[name].strip("{}").split("-")
        guid = GUID(int(hexed[0], 16), int(hexed[1], 16), int(hexed[2], 16),
                    (ctypes.c_ubyte * 8)(*[int(hexed[3][i:i + 2], 16) for i in (0, 2, 4, 6, 8, 10, 12, 14)]))
        path = ctypes.c_wchar_p()
        shell32 = ctypes.windll.shell32
        shell32.SHGetKnownFolderPath.argtypes = [ctypes.POINTER(GUID), wintypes.DWORD,
                                                 wintypes.HANDLE, ctypes.POINTER(ctypes.c_wchar_p)]
        if shell32.SHGetKnownFolderPath(ctypes.byref(guid), 0, None, ctypes.byref(path)) == 0:
            resolved = Path(path.value)
            ctypes.windll.ole32.CoTaskMemFree(path)
            return resolved
    except (OSError, AttributeError, ValueError):
        pass
    return fallback


def is_admin() -> bool:
    """True with elevation. Non-Windows is never admin here: no ctypes needed."""
    if os.name != "nt":
        return False
    try:
        import ctypes

        return bool(ctypes.windll.shell32.IsUserAnAdmin())
    except (OSError, AttributeError):
        return False


def default_target(per_user: bool) -> Path:
    if per_user:
        return Path(os.environ.get("LOCALAPPDATA", str(Path.home()))) / "Programs" / APP_NAME
    program_files = os.environ.get("ProgramFiles") or r"C:\Program Files"
    return Path(program_files) / APP_NAME


def resolve_target(requested: str | None, per_user: bool, allow_admin: bool) -> InstallPaths:
    if requested:
        target = Path(os.path.abspath(requested))
        per_user = not _is_under(target, Path(os.environ.get("ProgramFiles", r"C:\Program Files")))
    else:
        target = default_target(per_user)
    if not per_user and not allow_admin and not is_admin():
        raise InstallError(
            f"Installing to {target} needs elevation. Run this from an administrator "
            f"prompt, or pass --per-user to install into "
            f"{default_target(True)} instead."
        )
    return InstallPaths(target=target, exe=target / f"{APP_NAME}.exe", per_user=per_user)


def _is_under(path: Path, parent: Path) -> bool:
    try:
        path.resolve().relative_to(Path(parent).resolve())
        return True
    except (ValueError, OSError):
        return False


def find_source_folder() -> Path:
    """The folder holding the program and its workers, wherever it is being run from.

    Run from a packaged build it is the executable's own folder. Run from a source
    tree it is ``dist\\worthlesstask`` — the portable folder — or ``outputs``.
    """
    candidates = [package_root(), Path.cwd(), Path.cwd() / "dist" / APP_NAME,
                  package_root() / "dist" / APP_NAME]
    for candidate in candidates:
        if (candidate / f"{APP_NAME}.exe").is_file():
            return candidate.resolve()
    return package_root()


def source_folder() -> Path:
    """The folder holding the running program and its workers."""
    return find_source_folder()


#: Never copied into an installation: generated state, sources and build output.
SKIP_NAMES = {
    ".cache", "logs", "icons", "build", "dist", "tests", "outputs", "installer",
    "tools", ".workbuddy-ai", "__pycache__", ".git", ".venv",
}
SKIP_SUFFIXES = {".bak", ".log", ".pyc", ".pyo", ".spec", ".png", ".md", ".cjs"}
SKIP_FILES = {"runtime.json", "config.json", "library.json", "worthlesstask.log"}
#: Present in a source tree, absent from a portable folder - never installed.
SKIP_SOURCE_DIRS = {"worthlesstask", "tests", "tools", "assets", "installer", "logs", "icons",
                    ".cache", "build", "dist", "outputs"}


def _skip(entry: Path) -> bool:
    """Keep the installation to the program and its worker executables only."""
    name = entry.name
    if name in SKIP_NAMES or name in SKIP_FILES:
        return True
    if name.startswith("."):
        return True
    if entry.is_dir():
        return name in SKIP_SOURCE_DIRS
    if entry.suffix.lower() in SKIP_SUFFIXES:
        return True
    return name.endswith(".writing")


def install(target: str | None = None, per_user: bool = False, allow_admin: bool = True,
            launch: bool = False) -> InstallPaths:
    """Copy the program to ``target``, create shortcuts, register uninstall."""
    paths = resolve_target(target, per_user, allow_admin)
    source = source_folder()
    if not (source / f"{APP_NAME}.exe").is_file():
        raise InstallError(
            f"{source} does not hold {APP_NAME}.exe. Install from the built folder "
            f"(dist\\worthlesstask) or from a packaged build."
        )

    try:
        paths.target.mkdir(parents=True, exist_ok=True)
        for entry in sorted(source.iterdir()):
            if _skip(entry):
                continue
            destination = paths.target / entry.name
            if entry.is_dir():
                shutil.copytree(entry, destination, dirs_exist_ok=True)
            else:
                shutil.copy2(entry, destination)
    except OSError as exc:
        raise InstallError(f"Could not copy the program to {paths.target}: {exc}") from exc

    _write_uninstaller(paths)
    _create_shortcuts(paths)
    _register_uninstall(paths)
    if launch:
        _open(paths.exe, working_dir=paths.target)
    return paths


def _write_uninstaller(paths: InstallPaths) -> None:
    """Ship an ``uninstall.cmd`` next to the program so removal is one click."""
    script = "\r\n".join([
        "@echo off",
        f'"{paths.exe}" uninstall --installed "%~dp0" --yes',
        "",
    ])
    (paths.target / "uninstall.cmd").write_text(script, encoding="utf-8")


def _shortcut(link: Path, target: Path, working_dir: Path, icon: Path, description: str) -> bool:
    """Write a Windows ``.lnk`` file.

    Shell links have a documented binary layout, so this needs no COM, no
    PowerShell and no elevated process — which also means it cannot silently fail
    the way an out-of-process helper does.
    """
    if os.name != "nt":
        return False
    # Preferred: let the shell build the link. Fall back to writing the documented
    # binary layout if no helper is available, so a shortcut is never simply missing.
    if _shortcut_via_shell(link, target, working_dir, icon, description) and link.is_file():
        return True
    try:
        link.parent.mkdir(parents=True, exist_ok=True)
        link.write_bytes(_link_payload(target, working_dir, icon, description))
    except OSError:
        return False
    return link.is_file()


def _link_payload(target: Path, working_dir: Path, icon: Path, description: str) -> bytes:
    import struct

    HAS_LINK_INFO = 0x00000002
    HAS_NAME = 0x00000004
    HAS_RELATIVE_PATH = 0x00000008
    HAS_WORKING_DIR = 0x00000010
    HAS_ICON_LOCATION = 0x00000040
    IS_UNICODE = 0x00000080
    flags = (HAS_LINK_INFO | HAS_RELATIVE_PATH | HAS_WORKING_DIR | HAS_ICON_LOCATION | IS_UNICODE)
    if description:
        flags |= HAS_NAME
    header = struct.pack("<IIQQIIIiiIII",
                         0x0000004C, 0x00021401, 0, 0,
                         flags, 0, 0, 0, 0, 0, 0, 0)

    def string(value: str) -> bytes:
        return struct.pack("<H", len(value)) + value.encode("utf-16-le")

    # LinkInfo: header, flags, then the local base path as an ASCII string.
    base = str(target)
    info = struct.pack("<IIIIIiiiII", 0x1C + len(base) + 1, 0x1C, 1, 0, 0, 0, 0, 0, 0, 0)
    info += base.encode("ascii", "replace") + b"\x00"

    body = info
    if description:
        body += string(description)
    body += string(str(target))
    body += string(str(working_dir))
    body += string(str(icon))
    return header + body


def _run_powershell(script: str, *args: str) -> bool:
    """Run a PowerShell ``param()`` block with positional arguments.

    PowerShell binds trailing arguments to a ``param()`` block, which is the only
    reliable way to pass values through ``-Command`` — ``$args`` inside a plain
    script body does not receive them.
    """
    command = ["powershell", "-NoProfile", "-ExecutionPolicy", "Bypass", "-Command", script]
    command += list(args)
    try:
        result = subprocess.run(command, capture_output=True, timeout=60, check=False)
    except (OSError, subprocess.TimeoutExpired):
        return False
    return result.returncode == 0


def _shortcut_via_shell(link: Path, target: Path, working_dir: Path, icon: Path,
                        description: str) -> bool:
    script = (
        "param($Link,$Target,$WorkDir,$Icon,$Description) "
        "$s=(New-Object -COM WScript.Shell).CreateShortcut($Link);"
        "$s.TargetPath=$Target;$s.WorkingDirectory=$WorkDir;"
        "$s.IconLocation=$Icon;$s.Description=$Description;$s.Save()"
    )
    return _run_powershell(script, str(link), str(target), str(working_dir), str(icon), description)


def _create_shortcuts(paths: InstallPaths) -> list[Path]:
    icon = paths.target / "worthlesstask.ico"
    created: list[Path] = []
    desktop = known_folder("desktop")
    menu_root = known_folder("programs")
    folders = [desktop]
    for root in (menu_root, Path(r"C:\ProgramData\Microsoft\Windows\Start Menu\Programs")):
        candidate = root / APP_NAME
        try:
            candidate.mkdir(parents=True, exist_ok=True)
        except OSError:
            continue
        folders.append(candidate)
    for folder in folders:
        link = folder / SHORTCUT_NAME
        if _shortcut(link, paths.exe, paths.target, icon, f"{APP_NAME} - Discord game status"):
            created.append(link)
    return created


def _register_uninstall(paths: InstallPaths) -> None:
    if os.name != "nt":
        return
    script = (
        "param($Key,$Name,$Version,$Location,$Icon,$Uninstall) "
        "New-Item -Path $Key -Force | Out-Null;"
        "Set-ItemProperty -Path $Key -Name DisplayName -Value $Name;"
        "Set-ItemProperty -Path $Key -Name DisplayVersion -Value $Version;"
        "Set-ItemProperty -Path $Key -Name Publisher -Value $Name;"
        "Set-ItemProperty -Path $Key -Name InstallLocation -Value $Location;"
        "Set-ItemProperty -Path $Key -Name DisplayIcon -Value $Icon;"
        "Set-ItemProperty -Path $Key -Name UninstallString -Value $Uninstall;"
        "Set-ItemProperty -Path $Key -Name NoModify -Value 1;"
        "Set-ItemProperty -Path $Key -Name NoRepair -Value 1"
    )
    uninstaller = f'"{paths.exe}" uninstall --installed "{paths.target}" --yes'
    _run_powershell(script, f"HKCU:\\{UNINSTALL_KEY}",
                    APP_NAME, __version__, str(paths.target), str(paths.exe), uninstaller)


def _open(exe: Path, working_dir: Path) -> None:
    try:
        subprocess.Popen([str(exe)], cwd=str(working_dir),
                         creationflags=0x08000000 if os.name == "nt" else 0)
    except OSError:
        pass


def uninstall(installed: str | None = None, purge_data: bool = False) -> Path:
    """Remove an installed copy. Falls back to the folder this program runs from."""
    target = Path(os.path.abspath(installed)) if installed else source_folder()
    if not target.is_dir():
        raise InstallError(f"{target} is not a folder")
    if not installed and target == source_folder():
        # Removing the folder we are running from cannot work on Windows.
        raise InstallError(
            f"Refusing to delete {target} while running from it. Pass --installed "
            f"<folder> to remove an installed copy."
        )

    for folder in _shortcut_folders():
        link = folder / SHORTCUT_NAME
        link.unlink(missing_ok=True)
    for folder in [Path(os.environ.get("APPDATA", str(Path.home()))) / "Microsoft" / "Windows"
                   / "Start Menu" / "Programs" / APP_NAME]:
        shutil.rmtree(folder, ignore_errors=True)
    _run_powershell("param($Key) Remove-Item -Path $Key -Recurse -Force -ErrorAction SilentlyContinue",
                    f"HKCU:\\{UNINSTALL_KEY}")
    if purge_data:
        shutil.rmtree(appdata_root(), ignore_errors=True)
    shutil.rmtree(target, ignore_errors=True)
    return target


def _shortcut_folders() -> list[Path]:
    return [known_folder("desktop"), known_folder("programs") / APP_NAME]
