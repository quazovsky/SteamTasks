"""Dump Win32 window properties for a given pid (detection forensics)."""
import ctypes
import json
import sys
from ctypes import wintypes

user32 = ctypes.windll.user32
dwmapi = ctypes.windll.dwmapi
kernel32 = ctypes.windll.kernel32

GWL_STYLE = -16
GWL_EXSTYLE = -20
WS_VISIBLE = 0x10000000
WS_EX_LAYERED = 0x00080000
WS_EX_APPWINDOW = 0x00040000
WS_EX_TOOLWINDOW = 0x00000080
DWMWA_CLOAKED = 14
PROCESS_QUERY_LIMITED_INFORMATION = 0x1000


def probe(pid):
    out = []

    def cb(hwnd, _):
        lpid = wintypes.DWORD()
        user32.GetWindowThreadProcessId(hwnd, ctypes.byref(lpid))
        if lpid.value != pid:
            return True
        # title / class
        buf = ctypes.create_unicode_buffer(512)
        user32.GetWindowTextW(hwnd, buf, 512)
        title = buf.value
        buf2 = ctypes.create_unicode_buffer(512)
        user32.GetClassNameW(hwnd, buf2, 512)
        cls = buf2.value
        style = user32.GetWindowLongPtrW(hwnd, GWL_STYLE) & 0xFFFFFFFF
        exstyle = user32.GetWindowLongPtrW(hwnd, GWL_EXSTYLE) & 0xFFFFFFFF
        visible = bool(user32.IsWindowVisible(hwnd))
        iconic = bool(user32.IsIconic(hwnd))
        # layered attributes
        color = wintypes.COLORREF()
        alpha = ctypes.c_ubyte()
        flags = wintypes.DWORD()
        la_ok = bool(user32.GetLayeredWindowAttributes(
            hwnd, ctypes.byref(color), ctypes.byref(alpha), ctypes.byref(flags)))
        # per-pixel alpha (UpdateLayeredWindow) => GetLayeredWindowAttributes fails
        cloaked = wintypes.DWORD()
        dm = dwmapi.DwmGetWindowAttribute(
            hwnd, DWMWA_CLOAKED, ctypes.byref(cloaked), ctypes.sizeof(cloaked))
        rect = wintypes.RECT()
        user32.GetWindowRect(hwnd, ctypes.byref(rect))
        # window placement show state
        wp = wintypes.SHOW_WINDOW_PARAMS() if hasattr(wintypes, 'SHOW_WINDOW_PARAMS') else None
        info = {
            "hwnd": int(hwnd),
            "title": title,
            "class": cls,
            "visible": visible,
            "minimized": iconic,
            "style": hex(style),
            "ex_style": hex(exstyle),
            "WS_VISIBLE": bool(style & WS_VISIBLE),
            "WS_EX_LAYERED": bool(exstyle & WS_EX_LAYERED),
            "WS_EX_APPWINDOW": bool(exstyle & WS_EX_APPWINDOW),
            "WS_EX_TOOLWINDOW": bool(exstyle & WS_EX_TOOLWINDOW),
            "layered_attrs_ok": la_ok,
            "layered_alpha": int(alpha.value) if la_ok else None,
            "layered_flags": int(flags.value) if la_ok else None,
            "cloaked": int(cloaked.value) if dm == 0 else None,
            "rect": [rect.left, rect.top, rect.right, rect.bottom],
        }
        out.append(info)
        return True

    WNDENUMPROC = ctypes.WINFUNCTYPE(wintypes.BOOL, wintypes.HWND, wintypes.LPARAM)
    user32.EnumWindows(WNDENUMPROC(cb), 0)
    return out


def proc_path(pid):
    h = kernel32.OpenProcess(PROCESS_QUERY_LIMITED_INFORMATION, False, pid)
    if not h:
        return None
    try:
        buf = ctypes.create_unicode_buffer(1024)
        n = wintypes.DWORD(1024)
        if kernel32.QueryFullProcessImageNameW(h, 0, buf, ctypes.byref(n)):
            return buf.value
        return None
    finally:
        kernel32.CloseHandle(h)


def main():
    pid = int(sys.argv[1])
    result = {"pid": pid, "exe": proc_path(pid), "windows": probe(pid)}
    print(json.dumps(result, indent=2, ensure_ascii=False))


if __name__ == "__main__":
    main()
