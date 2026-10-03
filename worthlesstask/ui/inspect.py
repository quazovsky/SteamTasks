"""Inspection helpers: what Discord's detector would see for our process.

Discord enumerates processes and top-level windows, so this module answers the
two questions that matter when a presence is not being credited:

* is there a process whose image name matches the game's executable?
* does that process own a visible top-level window, and what is its title?
"""

from __future__ import annotations

import ctypes
import os
from ctypes import wintypes
from dataclasses import dataclass

if hasattr(ctypes, "WinDLL"):
    _user32 = ctypes.WinDLL("user32", use_last_error=True)
    _kernel32 = ctypes.WinDLL("kernel32", use_last_error=True)

    _WNDENUMPROC = ctypes.WINFUNCTYPE(
        wintypes.BOOL, wintypes.HWND, wintypes.LPARAM
    )
    _user32.EnumWindows.argtypes = [_WNDENUMPROC, wintypes.LPARAM]
    _user32.EnumWindows.restype = wintypes.BOOL
    _user32.IsWindowVisible.argtypes = [wintypes.HWND]
    _user32.IsWindowVisible.restype = wintypes.BOOL
    _user32.GetWindowTextLengthW.argtypes = [wintypes.HWND]
    _user32.GetWindowTextLengthW.restype = ctypes.c_int
    _user32.GetWindowTextW.argtypes = [wintypes.HWND, wintypes.LPWSTR, ctypes.c_int]
    _user32.GetWindowTextW.restype = ctypes.c_int
    _user32.GetWindowThreadProcessId.argtypes = [
        wintypes.HWND, ctypes.POINTER(wintypes.DWORD)
    ]
    _user32.GetWindowThreadProcessId.restype = wintypes.DWORD

    _PROCESS_QUERY_LIMITED_INFORMATION = 0x1000
    _kernel32.OpenProcess.argtypes = [wintypes.DWORD, wintypes.BOOL, wintypes.DWORD]
    _kernel32.OpenProcess.restype = wintypes.UINT  # process HANDLE
    _kernel32.QueryFullProcessImageNameW.argtypes = [
        wintypes.HANDLE, wintypes.DWORD, wintypes.LPWSTR, ctypes.POINTER(wintypes.DWORD)
    ]
    _kernel32.QueryFullProcessImageNameW.restype = wintypes.BOOL
    _kernel32.CloseHandle.argtypes = [wintypes.HANDLE]


@dataclass(frozen=True)
class VisibleWindow:
    hwnd: int
    pid: int
    title: str

    def to_dict(self) -> dict:
        return {"hwnd": self.hwnd, "pid": self.pid, "title": self.title}


def visible_windows() -> list[VisibleWindow]:
    """Every visible top-level window on the desktop, with its owning pid."""
    if not hasattr(ctypes, "WinDLL"):
        return []

    found: list[VisibleWindow] = []

    def callback(hwnd, _lparam):
        if not _user32.IsWindowVisible(hwnd):
            return True
        length = _user32.GetWindowTextLengthW(hwnd)
        if length <= 0:
            return True
        buffer = ctypes.create_unicode_buffer(length + 1)
        _user32.GetWindowTextW(hwnd, buffer, length + 1)
        pid = wintypes.DWORD(0)
        _user32.GetWindowThreadProcessId(hwnd, ctypes.byref(pid))
        found.append(VisibleWindow(hwnd=int(hwnd), pid=int(pid.value), title=buffer.value))
        return True

    _user32.EnumWindows(_WNDENUMPROC(callback), 0)
    return found


def process_image_path(pid: int) -> str | None:
    """Full image path for a pid, or None when it cannot be queried."""
    if not hasattr(ctypes, "WinDLL"):
        return None
    handle = _kernel32.OpenProcess(_PROCESS_QUERY_LIMITED_INFORMATION, False, pid)
    if not handle:
        return None
    try:
        size = wintypes.DWORD(32768)
        buffer = ctypes.create_unicode_buffer(size.value)
        if not _kernel32.QueryFullProcessImageNameW(handle, 0, buffer, ctypes.byref(size)):
            return None
        return buffer.value
    finally:
        _kernel32.CloseHandle(handle)


def process_name(pid: int) -> str | None:
    path = process_image_path(pid)
    if not path:
        return None
    return os.path.basename(path)


def windows_for_pid(pid: int) -> list[VisibleWindow]:
    return [window for window in visible_windows() if window.pid == pid]


def process_is_alive(pid: int) -> bool:
    return process_image_path(pid) is not None


def find_windows_titled(fragment: str) -> list[VisibleWindow]:
    needle = fragment.casefold()
    return [window for window in visible_windows() if needle in window.title.casefold()]
