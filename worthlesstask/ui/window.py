"""The window the presence process owns.

Discord decides a game is running from its process and window scan, not from Rich
Presence, so the process has to own a real window titled after the game. It also
serves as the operator surface: connection state, live counters, the last error,
and a start/stop control.

Drawn with user32/gdi32 directly; this interpreter has no tkinter and the project
takes no dependencies. Everything inside the window is painted by this module --
there are no child controls -- so the layout is computed once per size in
:meth:`PresenceWindow._layout` and every pixel is ours.

Design notes
------------
* Near-black matte surfaces with thin warm outlines and one restrained
  accent for thin lines and small glyphs -- no filled washes, no glows, no
  decorative stripes. Text is a solid light ink in grayscale antialiasing,
  never ClearType fringes. Depth comes only from a faint drop shadow.
* One rounded card carries the sidebar (brand, exactly two entries: home and
  about) and the session content -- a real Windows launcher.
* The title bar holds an EN/RU switch; every string in the window exists in
  both languages.
* The window never animates: a 1 Hz timer repaints only when a displayed
  string changed, and closing destroys the window at once.
* The window is a plain (non-layered) top-level window: ``WS_CAPTION`` is set and
  ``WS_EX_LAYERED`` is deliberately **not** — Discord's process detector reads
  window flags and ignores layered popup windows, which broke quest detection in
  the 2026-09-21 build. The window is fully opaque; no DWM blur is requested.
* The game's own art (the same picture the dashboard shows, cached as .ico)
  is loaded at three sizes: 32px for the title bar, 48px for the taskbar and
  the window class, hero size for the session view. Without art the tiles
  show the game's initial on a flat accent fill.
* Glyphs are line art drawn with GDI primitives -- no emoji, no image assets.
"""

from __future__ import annotations

import ctypes
import math
import os
import threading
import time
from ctypes import wintypes
from pathlib import Path

from .. import __version__ as APP_VERSION
from ..core.errors import worthlesstaskError
from ..core.logging import get_logger
from ..rpc.supervisor import PresenceSupervisor

# Messages
WM_NULL = 0x0000
WM_DESTROY = 0x0002
WM_SIZE = 0x0005
WM_PAINT = 0x000F
WM_CLOSE = 0x0010
WM_ERASEBKGND = 0x0014
WM_SETCURSOR = 0x0020
WM_GETMINMAXINFO = 0x0024
WM_NCCALCSIZE = 0x0083
WM_NCPAINT = 0x0085
WM_NCHITTEST = 0x0084
WM_TIMER = 0x0113
WM_MOUSEMOVE = 0x0200
WM_LBUTTONDOWN = 0x0201
WM_LBUTTONUP = 0x0202
WM_MOUSELEAVE = 0x02A3
WM_DPICHANGED = 0x02E0
WM_SETICON = 0x0080
#: Posted by the supervisor thread once it has stopped, so the window can flip the
#: action button back to "Запустить" without closing itself.
WM_APP_STOPPED = 0x8000 + 1

ICON_SMALL = 0
ICON_BIG = 1
IMAGE_ICON = 1
LR_LOADFROMFILE = 0x0010
LR_DEFAULTSIZE = 0x0040
DI_NORMAL = 0x0003

WS_OVERLAPPED = 0x00000000
WS_POPUP = 0x80000000
WS_CAPTION = 0x00C00000  # WS_BORDER | WS_DLGFRAME — required by Discord's window-flag detector
WS_THICKFRAME = 0x00040000
WS_MINIMIZEBOX = 0x00020000
WS_SYSMENU = 0x00080000
WS_VISIBLE = 0x10000000
WS_CLIPCHILDREN = 0x02000000
WS_CLIPSIBLINGS = 0x04000000
WS_EX_APPWINDOW = 0x00040000
WS_EX_LAYERED = 0x00080000

CS_VREDRAW = 0x0001
CS_HREDRAW = 0x0002

#: CreateWindowExW x/y: let Windows pick the default position. ctypes wraps the
#: unsigned literal to the signed c_int (-2147483648) the API expects.
CW_USEDEFAULT = 0x80000000

SW_MINIMIZE = 6
SW_MAXIMIZE = 3
SW_RESTORE = 9
SWP_NOSIZE = 0x0001
SWP_NOMOVE = 0x0002
SWP_NOZORDER = 0x0004
SWP_NOACTIVATE = 0x0010
SWP_FRAMECHANGED = 0x0020
SIZE_MAXIMIZED = 2

HTNOWHERE = 0
HTCLIENT = 1
HTCAPTION = 2
HTLEFT = 10
HTRIGHT = 11
HTTOP = 12
HTTOPLEFT = 13
HTTOPRIGHT = 14
HTBOTTOM = 15
HTBOTTOMLEFT = 16
HTBOTTOMRIGHT = 17

IDC_ARROW = 32512
IDC_HAND = 32649
IDC_SIZEWE = 32644
IDC_SIZENS = 32645
IDC_SIZENWSE = 32642
IDC_SIZENESW = 32643
#: Name -> ``IDC_*`` resource id, loaded lazily and cached per window.
CURSORS = {
    "arrow": IDC_ARROW,
    "hand": IDC_HAND,
    "sizewe": IDC_SIZEWE,
    "sizens": IDC_SIZENS,
    "sizenwse": IDC_SIZENWSE,
    "sizenesw": IDC_SIZENESW,
}

CF_UNICODETEXT = 13
GMEM_MOVEABLE = 0x0002

SRCCOPY = 0x00CC0020
DIB_RGB_COLORS = 0
BI_RGB = 0
AC_SRC_OVER = 0
AC_SRC_ALPHA = 1
GRADIENT_FILL_RECT_H = 0x00000000
GRADIENT_FILL_RECT_V = 0x00000001

NULL_BRUSH = 5
HOLLOW_BRUSH = NULL_BRUSH
#: A pen that draws nothing, for the pen slot. NULL_BRUSH (5) is a *brush*:
#: selecting it replaces the fill brush, so every _fill_round silently went
#: hollow. The old code only ever filled by accident, when garbage high RAX
#: bits made the SelectObject fail and leave the real brush in place.
NULL_PEN = 8
PS_SOLID = 0
PS_NULL = 5

DT_LEFT = 0x00000000
DT_CENTER = 0x00000001
DT_RIGHT = 0x00000002
DT_VCENTER = 0x00000004
DT_WORDBREAK = 0x00000010
DT_SINGLELINE = 0x00000020
DT_NOPREFIX = 0x00000800
DT_CALCRECT = 0x00000400

TRANSPARENT = 1
DEFAULT_CHARSET = 1
#: Grayscale antialiasing, not ClearType: on a matte black surface ClearType's
#: colour fringes read as harsh/jagged edges, while grayscale stays soft.
ANTIALIASED_QUALITY = 4
CLEARTYPE_QUALITY = 5
FW_NORMAL = 400
FW_MEDIUM = 500
FW_SEMIBOLD = 600

DWM_BB_ENABLE = 0x00000001
DWM_BB_BLURREGION = 0x00000002
DWM_BB_TRANSITIONONMAXIMIZED = 0x00000004
DWMWA_USE_IMMERSIVE_DARK_MODE = 20
DWMWA_WINDOW_CORNER_PREFERENCE = 33
DWMWA_BORDER_COLOR = 34
DWMWCP_ROUND = 2
DWMWCP_SMALL = 3
DWMWA_COLOR_NONE = 0xFFFFFFFE

TIMER_ID = 1
#: Hover fade for the caption buttons and the language switch. Armed only
#: while a fade is in flight (~120 ms each way); the window never repaints
#: on a schedule otherwise.
TIMER_HOVER = 4
HOVER_TICK_MS = 30
HOVER_STEP = 0.35
#: The window never animates on its own: the 1 Hz timer re-reads the supervisor
#: stats and repaints only when a displayed string actually changed. The old
#: exit-shrink animation and the ambient repaint timer are gone on purpose —
#: a launcher must open and close instantly and sit still.

#: Logical (96 DPI) layout metrics. Everything is scaled by the window DPI.
#: The window is a launcher, not a toast: a 236px graphite sidebar carries the
#: brand and the two navigation entries, the rest is the session view. Kept
#: deliberately restrained: a launcher that fills every pixel with detail reads
#: as a toy, so the ornament is one glow, one hairline and the sheen.
CARD_INSET = 0
CARD_RADIUS = 12
TITLEBAR_HEIGHT = 46
TITLE_BUTTON = 30
TITLE_BUTTON_GAP = 6
TITLE_BUTTON_PAD = 12
SIDEBAR_WIDTH = 214
SIDEBAR_PAD = 18
BRAND_TILE = 48
NAV_ITEM_HEIGHT = 46
NAV_GAP = 12
CONTENT_PAD = 24
CONTENT_GAP = 18
HERO_ICON = 64
STATS_HEIGHT = 78
STATS_GAP = 12
ERROR_COLLAPSED = 64
#: Expanded panel: a 10px gap above the 40px footer row (metrics line + copy
#: button), so the collapsed block plus its expansion stays in proportion.
ERROR_FOOTER = 50
ACTION_WIDTH = 300
ACTION_HEIGHT = 50
ACTION_GAP = 20
FOOTER_GAP = 14
FOOTER_HEIGHT = 24

DEFAULT_WIDTH = 760
#: The stack (title bar, hero, stat cards, console panel, button and the footer
#: readout) needs 442; the default is a little taller so the panel has air.
#: ``WM_GETMINMAXINFO`` refuses to go below the computed minimum, which is what
#: clipped the button before.
DEFAULT_HEIGHT = 520
MIN_WIDTH = 660

# Palette (RGB tuples; GDI wants BGR, _rgb does the swap)
# Deep matte black with one muted burnt-orange accent. Every text colour is a
# solid ink, never a blend, so it stays readable. No gradients, no glows, no
# decorative stripes: depth comes only from a faint drop shadow.
COLOR_BG = (10, 9, 8)
COLOR_CARD = (16, 14, 11)
COLOR_CARD_EDGE = (70, 56, 40)
COLOR_SIDE = (16, 14, 11)
COLOR_LINE = (48, 40, 31)
COLOR_PANEL = (16, 14, 11)
COLOR_PANEL_EDGE = (64, 52, 38)
#: Thin outlines around panels, tiles and the card edge. Visible but quiet.
COLOR_FRAME = (70, 56, 40)
#: The single restrained accent for thin lines and small glyphs.
COLOR_OUTLINE = (150, 95, 40)
COLOR_ACCENT = (160, 78, 18)
COLOR_ACCENT_HOT = (180, 90, 22)
COLOR_ACCENT_PRESS = (126, 60, 10)
COLOR_TITLE = (240, 234, 226)
COLOR_BODY = (214, 205, 192)
COLOR_MUTED = (168, 154, 134)
COLOR_OK = (240, 138, 52)
COLOR_BUSY = (255, 196, 110)
COLOR_ERROR = (243, 84, 74)
COLOR_WARN = (255, 170, 70)
COLOR_CLOSE_HOT = (200, 60, 50)
COLOR_BUTTON_TEXT = (255, 255, 255)
COLOR_HOVER_FILL = (32, 27, 22)


class WindowError(worthlesstaskError):
    """The native window could not be created."""


def _rgb(rgb: tuple[int, int, int]) -> int:
    r, g, b = rgb
    return r | (g << 8) | (b << 16)


def _blend(fg: tuple[int, int, int], bg: tuple[int, int, int], alpha: float) -> tuple[int, int, int]:
    """Mix ``fg`` over ``bg``. Exact on flat fills, which is all this window has."""
    alpha = 0.0 if alpha < 0.0 else 1.0 if alpha > 1.0 else alpha
    return (
        int(round(fg[0] * alpha + bg[0] * (1.0 - alpha))),
        int(round(fg[1] * alpha + bg[1] * (1.0 - alpha))),
        int(round(fg[2] * alpha + bg[2] * (1.0 - alpha))),
    )


def _in(rect: tuple[int, int, int, int] | None, x: int, y: int) -> bool:
    if rect is None:
        return False
    return rect[0] <= x < rect[2] and rect[1] <= y < rect[3]


#: Per-process, so the DPI mode is only ever chosen once.
_DPI_DONE = False


def _ensure_dpi_awareness() -> None:
    """Opt into per-monitor DPI before any window exists.

    Called from :meth:`PresenceWindow.run`, which is the first entry point that
    creates a window. Doing it at import time would change the DPI mode of any
    process that merely imports this module (the CLI, the tests).
    """
    global _DPI_DONE
    if _DPI_DONE:
        return
    _DPI_DONE = True
    if not hasattr(ctypes, "WinDLL"):
        return
    try:
        ctypes.windll.shcore.SetProcessDpiAwareness(2)  # PROCESS_PER_MONITOR_DPI_AWARE
        return
    except Exception:  # noqa: BLE001 - already set, or no shcore (pre-8.1)
        pass
    try:
        # DPI_AWARENESS_CONTEXT_PER_MONITOR_AWARE_V2
        ctypes.windll.user32.SetProcessDpiAwarenessContext(ctypes.c_void_p(-4))
    except Exception:  # noqa: BLE001
        pass


# NOTE (2026-09-26): GDI/USER object handles are 32-bit handle-table values, but
# on this machine the kernel leaves garbage in the high 32 bits of RAX for some
# of them (every CreateSolidBrush came back 0xFFFFFFFF????????, SelectObject
# then failed and every solid fill painted black). Declaring the restype as a
# 32-bit UINT makes ctypes truncate the garbage. Real 64-bit values (HMODULE,
# pointers, LRESULT) keep their pointer restypes and are never truncated.
if hasattr(ctypes, "WinDLL"):
    _user32 = ctypes.WinDLL("user32", use_last_error=True)
    _gdi32 = ctypes.WinDLL("gdi32", use_last_error=True)
    _kernel32 = ctypes.WinDLL("kernel32", use_last_error=True)
    try:
        _msimg32 = ctypes.WinDLL("msimg32", use_last_error=True)
    except OSError:  # pragma: no cover - present on every supported Windows
        _msimg32 = None
    try:
        _dwmapi = ctypes.WinDLL("dwmapi", use_last_error=True)
    except OSError:  # pragma: no cover
        _dwmapi = None

    LRESULT = ctypes.c_ssize_t
    HGDIOBJ = wintypes.HGDIOBJ
    WNDPROC = ctypes.WINFUNCTYPE(
        LRESULT, wintypes.HWND, wintypes.UINT, wintypes.WPARAM, wintypes.LPARAM
    )

    class WNDCLASSW(ctypes.Structure):
        _fields_ = [
            ("style", wintypes.UINT),
            ("lpfnWndProc", WNDPROC),
            ("cbClsExtra", ctypes.c_int),
            ("cbWndExtra", ctypes.c_int),
            ("hInstance", wintypes.HINSTANCE),
            ("hIcon", wintypes.HICON),
            ("hCursor", wintypes.HANDLE),
            ("hbrBackground", wintypes.HBRUSH),
            ("lpszMenuName", wintypes.LPCWSTR),
            ("lpszClassName", wintypes.LPCWSTR),
        ]

    class MSG(ctypes.Structure):
        _fields_ = [
            ("hwnd", wintypes.HWND),
            ("message", wintypes.UINT),
            ("wParam", wintypes.WPARAM),
            ("lParam", wintypes.LPARAM),
            ("time", wintypes.DWORD),
            ("pt", wintypes.POINT),
        ]

    class RECT(ctypes.Structure):
        _fields_ = [
            ("left", ctypes.c_long),
            ("top", ctypes.c_long),
            ("right", ctypes.c_long),
            ("bottom", ctypes.c_long),
        ]

    class PAINTSTRUCT(ctypes.Structure):
        _fields_ = [
            ("hdc", wintypes.HDC),
            ("fErase", wintypes.BOOL),
            ("rcPaint", RECT),
            ("fRestore", wintypes.BOOL),
            ("fIncUpdate", wintypes.BOOL),
            ("rgbReserved", wintypes.BYTE * 32),
        ]

    class MINMAXINFO(ctypes.Structure):
        _fields_ = [
            ("ptReserved", wintypes.POINT),
            ("ptMaxSize", wintypes.POINT),
            ("ptMaxPosition", wintypes.POINT),
            ("ptMinTrackSize", wintypes.POINT),
            ("ptMaxTrackSize", wintypes.POINT),
        ]

    class MONITORINFO(ctypes.Structure):
        _fields_ = [
            ("cbSize", wintypes.DWORD),
            ("rcMonitor", RECT),
            ("rcWork", RECT),
            ("dwFlags", wintypes.DWORD),
        ]

    class TRACKMOUSEEVENT(ctypes.Structure):
        _fields_ = [
            ("cbSize", wintypes.DWORD),
            ("dwFlags", wintypes.DWORD),
            ("hwndTrack", wintypes.HWND),
            ("dwHoverTime", wintypes.DWORD),
        ]

    class TRIVERTEX(ctypes.Structure):
        _fields_ = [
            ("x", ctypes.c_long),
            ("y", ctypes.c_long),
            ("Red", ctypes.c_ushort),
            ("Green", ctypes.c_ushort),
            ("Blue", ctypes.c_ushort),
            ("Alpha", ctypes.c_ushort),
        ]

    class GRADIENT_RECT(ctypes.Structure):
        _fields_ = [("UpperLeft", ctypes.c_ulong), ("LowerRight", ctypes.c_ulong)]

    class BLENDFUNCTION(ctypes.Structure):
        _fields_ = [
            ("BlendOp", wintypes.BYTE),
            ("BlendFlags", wintypes.BYTE),
            ("SourceConstantAlpha", wintypes.BYTE),
            ("AlphaFormat", wintypes.BYTE),
        ]

    class BITMAPINFOHEADER(ctypes.Structure):
        _fields_ = [
            ("biSize", wintypes.DWORD),
            ("biWidth", ctypes.c_long),
            ("biHeight", ctypes.c_long),
            ("biPlanes", wintypes.WORD),
            ("biBitCount", wintypes.WORD),
            ("biCompression", wintypes.DWORD),
            ("biSizeImage", wintypes.DWORD),
            ("biXPelsPerMeter", ctypes.c_long),
            ("biYPelsPerMeter", ctypes.c_long),
            ("biClrUsed", wintypes.DWORD),
            ("biClrImportant", wintypes.DWORD),
        ]

    class BITMAPINFO(ctypes.Structure):
        _fields_ = [("bmiHeader", BITMAPINFOHEADER), ("bmiColors", wintypes.DWORD * 3)]

    class DWM_BLURBEHIND(ctypes.Structure):
        _fields_ = [
            ("dwFlags", wintypes.DWORD),
            ("fEnable", wintypes.BOOL),
            ("hRgnBlur", wintypes.HRGN),
            ("fTransitionOnMaximized", wintypes.BOOL),
        ]

    _user32.RegisterClassW.argtypes = [ctypes.POINTER(WNDCLASSW)]
    _user32.RegisterClassW.restype = wintypes.ATOM
    _user32.CreateWindowExW.argtypes = [
        wintypes.DWORD, wintypes.LPCWSTR, wintypes.LPCWSTR, wintypes.DWORD,
        ctypes.c_int, ctypes.c_int, ctypes.c_int, ctypes.c_int,
        wintypes.HWND, wintypes.HMENU, wintypes.HINSTANCE, wintypes.LPVOID,
    ]
    _user32.CreateWindowExW.restype = wintypes.UINT  # HWND
    _user32.DefWindowProcW.argtypes = [
        wintypes.HWND, wintypes.UINT, wintypes.WPARAM, wintypes.LPARAM
    ]
    _user32.DefWindowProcW.restype = LRESULT
    _user32.SetWindowTextW.argtypes = [wintypes.HWND, wintypes.LPCWSTR]
    _user32.GetWindowTextW.argtypes = [wintypes.HWND, wintypes.LPWSTR, ctypes.c_int]
    _user32.SetTimer.argtypes = [wintypes.HWND, wintypes.UINT, wintypes.UINT, wintypes.LPVOID]
    _user32.SetTimer.restype = wintypes.UINT
    _user32.KillTimer.argtypes = [wintypes.HWND, wintypes.UINT]
    _user32.GetMessageW.argtypes = [ctypes.POINTER(MSG), wintypes.HWND, wintypes.UINT, wintypes.UINT]
    _user32.GetMessageW.restype = wintypes.BOOL
    _user32.LoadCursorW.argtypes = [wintypes.HINSTANCE, wintypes.LPCWSTR]
    _user32.LoadCursorW.restype = wintypes.UINT  # HCURSOR
    _user32.SetCursor.argtypes = [wintypes.HANDLE]
    _user32.SetCursor.restype = wintypes.UINT  # previous HCURSOR
    _user32.PostQuitMessage.argtypes = [ctypes.c_int]
    _user32.SendMessageW.argtypes = [
        wintypes.HWND, wintypes.UINT, wintypes.WPARAM, wintypes.LPARAM
    ]
    _user32.SendMessageW.restype = LRESULT
    _user32.PostMessageW.argtypes = [wintypes.HWND, wintypes.UINT, wintypes.WPARAM, wintypes.LPARAM]
    _user32.FillRect.argtypes = [wintypes.HDC, ctypes.POINTER(RECT), wintypes.HBRUSH]
    _user32.DrawTextW.argtypes = [
        wintypes.HDC, wintypes.LPCWSTR, ctypes.c_int, ctypes.POINTER(RECT), wintypes.UINT
    ]
    _user32.DrawTextW.restype = ctypes.c_int
    _user32.GetClientRect.argtypes = [wintypes.HWND, ctypes.POINTER(RECT)]
    _user32.GetWindowRect.argtypes = [wintypes.HWND, ctypes.POINTER(RECT)]
    _user32.InvalidateRect.argtypes = [wintypes.HWND, ctypes.POINTER(RECT), wintypes.BOOL]
    _user32.DestroyWindow.argtypes = [wintypes.HWND]
    _user32.TranslateMessage.argtypes = [ctypes.POINTER(MSG)]
    _user32.DispatchMessageW.argtypes = [ctypes.POINTER(MSG)]
    _user32.DispatchMessageW.restype = LRESULT
    _user32.LoadImageW.argtypes = [
        wintypes.HINSTANCE, wintypes.LPCWSTR, wintypes.UINT,
        ctypes.c_int, ctypes.c_int, wintypes.UINT,
    ]
    _user32.LoadImageW.restype = wintypes.UINT  # HICON
    _user32.DrawIconEx.argtypes = [
        wintypes.HDC, ctypes.c_int, ctypes.c_int, wintypes.HICON,
        ctypes.c_int, ctypes.c_int, wintypes.UINT, wintypes.HANDLE, wintypes.UINT,
    ]
    _user32.DestroyIcon.argtypes = [wintypes.HICON]
    _user32.BeginPaint.argtypes = [wintypes.HWND, ctypes.POINTER(PAINTSTRUCT)]
    _user32.BeginPaint.restype = wintypes.UINT  # HDC
    _user32.EndPaint.argtypes = [wintypes.HWND, ctypes.POINTER(PAINTSTRUCT)]
    _user32.SetWindowPos.argtypes = [
        wintypes.HWND, wintypes.HWND, ctypes.c_int, ctypes.c_int,
        ctypes.c_int, ctypes.c_int, wintypes.UINT,
    ]
    _user32.ShowWindow.argtypes = [wintypes.HWND, ctypes.c_int]
    _user32.IsZoomed.argtypes = [wintypes.HWND]
    _user32.IsZoomed.restype = wintypes.BOOL
    _user32.IsIconic.argtypes = [wintypes.HWND]
    _user32.IsIconic.restype = wintypes.BOOL
    _user32.SetCapture.argtypes = [wintypes.HWND]
    _user32.ReleaseCapture.argtypes = []
    _user32.GetCursorPos.argtypes = [ctypes.POINTER(wintypes.POINT)]
    _user32.TrackMouseEvent.argtypes = [ctypes.POINTER(TRACKMOUSEEVENT)]
    _user32.SetWindowRgn.argtypes = [wintypes.HWND, wintypes.HRGN, wintypes.BOOL]
    _user32.GetDC.argtypes = [wintypes.HWND]
    _user32.GetDC.restype = wintypes.UINT  # HDC
    _user32.ReleaseDC.argtypes = [wintypes.HWND, wintypes.HDC]
    _user32.MonitorFromWindow.argtypes = [wintypes.HWND, wintypes.DWORD]
    _user32.MonitorFromWindow.restype = wintypes.UINT  # HMONITOR
    _user32.GetMonitorInfoW.argtypes = [wintypes.HANDLE, ctypes.POINTER(MONITORINFO)]
    _user32.ScreenToClient.argtypes = [wintypes.HWND, ctypes.POINTER(wintypes.POINT)]
    try:
        _user32.GetDpiForWindow.argtypes = [wintypes.HWND]
        _user32.GetDpiForWindow.restype = wintypes.UINT
    except AttributeError:  # pragma: no cover - pre-1607
        pass

    _kernel32.GetModuleHandleW.argtypes = [wintypes.LPCWSTR]
    _kernel32.GetModuleHandleW.restype = wintypes.HMODULE
    _kernel32.GlobalAlloc.argtypes = [wintypes.UINT, ctypes.c_size_t]
    _kernel32.GlobalAlloc.restype = wintypes.UINT  # HGLOBAL
    _kernel32.GlobalLock.argtypes = [wintypes.HGLOBAL]
    _kernel32.GlobalLock.restype = ctypes.c_void_p
    _kernel32.GlobalUnlock.argtypes = [wintypes.HGLOBAL]
    _kernel32.GlobalFree.argtypes = [wintypes.HGLOBAL]
    _user32.OpenClipboard.argtypes = [wintypes.HWND]
    _user32.EmptyClipboard.argtypes = []
    _user32.CloseClipboard.argtypes = []
    _user32.SetClipboardData.argtypes = [wintypes.UINT, wintypes.HANDLE]
    _user32.SetClipboardData.restype = wintypes.UINT  # clipboard owns it

    _gdi32.CreateSolidBrush.argtypes = [wintypes.DWORD]
    _gdi32.CreateSolidBrush.restype = wintypes.UINT  # HBRUSH
    _gdi32.CreatePen.argtypes = [ctypes.c_int, ctypes.c_int, wintypes.DWORD]
    _gdi32.CreatePen.restype = wintypes.UINT  # HPEN
    _gdi32.GetStockObject.argtypes = [ctypes.c_int]
    _gdi32.GetStockObject.restype = wintypes.UINT  # HGDIOBJ
    _gdi32.CreateFontW.argtypes = [
        ctypes.c_int, ctypes.c_int, ctypes.c_int, ctypes.c_int, ctypes.c_int,
        wintypes.DWORD, wintypes.DWORD, wintypes.DWORD, wintypes.DWORD,
        wintypes.DWORD, wintypes.DWORD, wintypes.DWORD, wintypes.DWORD, wintypes.LPCWSTR,
    ]
    _gdi32.CreateFontW.restype = wintypes.UINT  # HFONT
    _gdi32.SelectObject.argtypes = [wintypes.HDC, HGDIOBJ]
    _gdi32.SelectObject.restype = wintypes.UINT  # previous HGDIOBJ
    _gdi32.GetDeviceCaps.argtypes = [wintypes.HDC, ctypes.c_int]
    _gdi32.GetDeviceCaps.restype = ctypes.c_int
    _gdi32.DeleteObject.argtypes = [HGDIOBJ]
    _gdi32.SetTextColor.argtypes = [wintypes.HDC, wintypes.DWORD]
    _gdi32.SetBkMode.argtypes = [wintypes.HDC, ctypes.c_int]
    _gdi32.GetTextExtentPoint32W.argtypes = [
        wintypes.HDC, wintypes.LPCWSTR, ctypes.c_int, ctypes.POINTER(wintypes.SIZE)
    ]
    _gdi32.CreateRoundRectRgn.argtypes = [
        ctypes.c_int, ctypes.c_int, ctypes.c_int, ctypes.c_int, ctypes.c_int, ctypes.c_int
    ]
    _gdi32.CreateRoundRectRgn.restype = wintypes.UINT  # HRGN
    _gdi32.SelectClipRgn.argtypes = [wintypes.HDC, wintypes.HRGN]
    _gdi32.CreateCompatibleDC.argtypes = [wintypes.HDC]
    _gdi32.CreateCompatibleDC.restype = wintypes.UINT  # HDC
    _gdi32.DeleteDC.argtypes = [wintypes.HDC]
    _gdi32.CreateCompatibleBitmap.argtypes = [wintypes.HDC, ctypes.c_int, ctypes.c_int]
    _gdi32.CreateCompatibleBitmap.restype = wintypes.UINT  # HBITMAP
    _gdi32.CreateDIBSection.argtypes = [
        wintypes.HDC, ctypes.POINTER(BITMAPINFO), wintypes.UINT,
        ctypes.POINTER(ctypes.c_void_p), wintypes.HANDLE, wintypes.DWORD,
    ]
    _gdi32.CreateDIBSection.restype = wintypes.UINT  # HBITMAP
    _gdi32.BitBlt.argtypes = [
        wintypes.HDC, ctypes.c_int, ctypes.c_int, ctypes.c_int, ctypes.c_int,
        wintypes.HDC, ctypes.c_int, ctypes.c_int, wintypes.DWORD,
    ]
    _gdi32.MoveToEx.argtypes = [
        wintypes.HDC, ctypes.c_int, ctypes.c_int, ctypes.POINTER(wintypes.POINT)
    ]
    _gdi32.LineTo.argtypes = [wintypes.HDC, ctypes.c_int, ctypes.c_int]
    _gdi32.Polyline.argtypes = [wintypes.HDC, ctypes.POINTER(wintypes.POINT), ctypes.c_int]
    _gdi32.Polygon.argtypes = [wintypes.HDC, ctypes.POINTER(wintypes.POINT), ctypes.c_int]
    _gdi32.Rectangle.argtypes = [
        wintypes.HDC, ctypes.c_int, ctypes.c_int, ctypes.c_int, ctypes.c_int
    ]
    _gdi32.RoundRect.argtypes = [
        wintypes.HDC, ctypes.c_int, ctypes.c_int, ctypes.c_int, ctypes.c_int,
        ctypes.c_int, ctypes.c_int,
    ]
    _gdi32.Ellipse.argtypes = [
        wintypes.HDC, ctypes.c_int, ctypes.c_int, ctypes.c_int, ctypes.c_int
    ]
    _gdi32.SetPixelV.argtypes = [wintypes.HDC, ctypes.c_int, ctypes.c_int, wintypes.DWORD]
    _gdi32.SetPixelV.restype = wintypes.DWORD

    if _msimg32 is not None:
        _msimg32.GradientFill.argtypes = [
            wintypes.HDC, ctypes.POINTER(TRIVERTEX), ctypes.c_ulong,
            ctypes.POINTER(GRADIENT_RECT), ctypes.c_ulong, ctypes.c_ulong,
        ]
        _msimg32.AlphaBlend.argtypes = [
            wintypes.HDC, ctypes.c_int, ctypes.c_int, ctypes.c_int, ctypes.c_int,
            wintypes.HDC, ctypes.c_int, ctypes.c_int, ctypes.c_int, ctypes.c_int,
            BLENDFUNCTION,
        ]

    if _dwmapi is not None:
        _dwmapi.DwmEnableBlurBehindWindow.argtypes = [
            wintypes.HWND, ctypes.POINTER(DWM_BLURBEHIND)
        ]
        _dwmapi.DwmSetWindowAttribute.argtypes = [
            wintypes.HWND, wintypes.DWORD, ctypes.c_void_p, wintypes.DWORD
        ]
        _dwmapi.DwmSetWindowAttribute.restype = ctypes.c_long

    try:
        _gdiplus = ctypes.WinDLL("gdiplus", use_last_error=True)
    except OSError:  # pragma: no cover
        _gdiplus = None

    class GdiplusStartupInput(ctypes.Structure):
        _fields_ = [
            ("GdiplusVersion", ctypes.c_uint32),
            ("DebugEventCallback", ctypes.c_void_p),
            ("SuppressBackgroundThread", wintypes.BOOL),
            ("SuppressExternalCodecs", wintypes.BOOL),
        ]

    class GpPointF(ctypes.Structure):
        _fields_ = [("X", ctypes.c_float), ("Y", ctypes.c_float)]

    if _gdiplus is not None:
        try:
            _gdiplus.GdiplusStartup.argtypes = [
                ctypes.POINTER(ctypes.c_size_t),
                ctypes.POINTER(GdiplusStartupInput),
                ctypes.c_void_p,
            ]
            _gdiplus.GdiplusStartup.restype = ctypes.c_int
            _gdiplus.GdipCreateFromHDC.argtypes = [wintypes.HDC, ctypes.POINTER(ctypes.c_void_p)]
            _gdiplus.GdipCreateFromHDC.restype = ctypes.c_int
            _gdiplus.GdipDeleteGraphics.argtypes = [ctypes.c_void_p]
            _gdiplus.GdipDeleteGraphics.restype = ctypes.c_int
            _gdiplus.GdipSetSmoothingMode.argtypes = [ctypes.c_void_p, ctypes.c_int]
            _gdiplus.GdipSetSmoothingMode.restype = ctypes.c_int
            _gdiplus.GdipSetPixelOffsetMode.argtypes = [ctypes.c_void_p, ctypes.c_int]
            _gdiplus.GdipSetPixelOffsetMode.restype = ctypes.c_int
            _gdiplus.GdipCreatePath.argtypes = [ctypes.c_int, ctypes.POINTER(ctypes.c_void_p)]
            _gdiplus.GdipCreatePath.restype = ctypes.c_int
            _gdiplus.GdipDeletePath.argtypes = [ctypes.c_void_p]
            _gdiplus.GdipDeletePath.restype = ctypes.c_int
            _gdiplus.GdipAddPathArc.argtypes = [
                ctypes.c_void_p,
                ctypes.c_float, ctypes.c_float, ctypes.c_float, ctypes.c_float,
                ctypes.c_float, ctypes.c_float,
            ]
            _gdiplus.GdipAddPathArc.restype = ctypes.c_int
            _gdiplus.GdipAddPathRectangle.argtypes = [
                ctypes.c_void_p,
                ctypes.c_float, ctypes.c_float, ctypes.c_float, ctypes.c_float,
            ]
            _gdiplus.GdipAddPathRectangle.restype = ctypes.c_int
            _gdiplus.GdipClosePathFigures.argtypes = [ctypes.c_void_p]
            _gdiplus.GdipClosePathFigures.restype = ctypes.c_int
            _gdiplus.GdipCreateSolidFill.argtypes = [ctypes.c_uint32, ctypes.POINTER(ctypes.c_void_p)]
            _gdiplus.GdipCreateSolidFill.restype = ctypes.c_int
            _gdiplus.GdipDeleteBrush.argtypes = [ctypes.c_void_p]
            _gdiplus.GdipDeleteBrush.restype = ctypes.c_int
            _gdiplus.GdipFillPath.argtypes = [ctypes.c_void_p, ctypes.c_void_p, ctypes.c_void_p]
            _gdiplus.GdipFillPath.restype = ctypes.c_int
            _gdiplus.GdipCreatePen1.argtypes = [
                ctypes.c_uint32, ctypes.c_float, ctypes.c_int, ctypes.POINTER(ctypes.c_void_p)
            ]
            _gdiplus.GdipCreatePen1.restype = ctypes.c_int
            _gdiplus.GdipSetPenStartCap.argtypes = [ctypes.c_void_p, ctypes.c_int]
            _gdiplus.GdipSetPenEndCap.argtypes = [ctypes.c_void_p, ctypes.c_int]
            _gdiplus.GdipSetPenLineJoin.argtypes = [ctypes.c_void_p, ctypes.c_int]
            _gdiplus.GdipDeletePen.argtypes = [ctypes.c_void_p]
            _gdiplus.GdipDeletePen.restype = ctypes.c_int
            _gdiplus.GdipDrawPath.argtypes = [ctypes.c_void_p, ctypes.c_void_p, ctypes.c_void_p]
            _gdiplus.GdipDrawPath.restype = ctypes.c_int
            _gdiplus.GdipFillEllipse.argtypes = [
                ctypes.c_void_p, ctypes.c_void_p,
                ctypes.c_float, ctypes.c_float, ctypes.c_float, ctypes.c_float,
            ]
            _gdiplus.GdipFillEllipse.restype = ctypes.c_int
            _gdiplus.GdipDrawEllipse.argtypes = [
                ctypes.c_void_p, ctypes.c_void_p,
                ctypes.c_float, ctypes.c_float, ctypes.c_float, ctypes.c_float,
            ]
            _gdiplus.GdipDrawEllipse.restype = ctypes.c_int
            _gdiplus.GdipDrawLine.argtypes = [
                ctypes.c_void_p, ctypes.c_void_p,
                ctypes.c_float, ctypes.c_float, ctypes.c_float, ctypes.c_float,
            ]
            _gdiplus.GdipDrawLine.restype = ctypes.c_int
            _gdiplus.GdipDrawLines.argtypes = [
                ctypes.c_void_p, ctypes.c_void_p, ctypes.POINTER(GpPointF), ctypes.c_int
            ]
            _gdiplus.GdipDrawLines.restype = ctypes.c_int
            _gdiplus.GdipFillPolygon.argtypes = [
                ctypes.c_void_p, ctypes.c_void_p, ctypes.POINTER(GpPointF), ctypes.c_int, ctypes.c_int
            ]
            _gdiplus.GdipFillPolygon.restype = ctypes.c_int
        except AttributeError:  # pragma: no cover
            _gdiplus = None


_GDIP_TOKEN = ctypes.c_size_t(0)
_GDIP_READY = False


def _ensure_gdip() -> bool:
    global _GDIP_READY
    if _GDIP_READY:
        return True
    if not hasattr(ctypes, "WinDLL") or _gdiplus is None:
        return False
    try:
        startup = GdiplusStartupInput(1, None, False, False)
        if _gdiplus.GdiplusStartup(ctypes.byref(_GDIP_TOKEN), ctypes.byref(startup), None) == 0:
            _GDIP_READY = True
            return True
    except Exception:  # noqa: BLE001
        pass
    return False


def _argb(rgb: tuple[int, int, int], alpha: int = 255) -> int:
    r, g, b = rgb
    return ((alpha & 0xFF) << 24) | ((r & 0xFF) << 16) | ((g & 0xFF) << 8) | (b & 0xFF)


def _gdip_round_path(
    left: float, top: float, right: float, bottom: float, radius: float
) -> ctypes.c_void_p | None:
    if not _ensure_gdip():
        return None
    w = max(0.0, float(right - left))
    h = max(0.0, float(bottom - top))
    if w <= 0.0 or h <= 0.0:
        return None
    path = ctypes.c_void_p()
    if _gdiplus.GdipCreatePath(0, ctypes.byref(path)) != 0 or not path:
        return None
    r = max(0.0, min(float(radius), w * 0.5, h * 0.5))
    if r <= 0.5:
        _gdiplus.GdipAddPathRectangle(path, float(left), float(top), w, h)
    else:
        d = r * 2.0
        x, y = float(left), float(top)
        _gdiplus.GdipAddPathArc(path, x, y, d, d, 180.0, 90.0)
        _gdiplus.GdipAddPathArc(path, x + w - d, y, d, d, 270.0, 90.0)
        _gdiplus.GdipAddPathArc(path, x + w - d, y + h - d, d, d, 0.0, 90.0)
        _gdiplus.GdipAddPathArc(path, x, y + h - d, d, d, 90.0, 90.0)
        _gdiplus.GdipClosePathFigures(path)
    return path


class PresenceWindow:
    """Native window plus the supervisor running behind it.

    The window never blocks: the supervisor runs in its own thread and the window
    only ever reads :attr:`PresenceSupervisor.stats` (a plain dataclass) while
    painting. The 1-second timer re-reads those fields and repaints only when one
    of the displayed strings actually changed.
    """

    def __init__(
        self,
        config,
        logger=None,
        supervisor: PresenceSupervisor | None = None,
        title: str | None = None,
        identity_refresher=None,
        icon_path: str | Path | None = None,
    ) -> None:
        self.config = config
        self.log = logger or get_logger()
        self._identity_refresher = identity_refresher
        self.supervisor = supervisor or PresenceSupervisor(
            config, logger=self.log, identity_refresher=identity_refresher
        )
        self.title = title or config.game_name
        self.icon_path = Path(icon_path) if icon_path else None
        self.stop_event = threading.Event()
        self.exit_code = 0

        self._hwnd: int | None = None
        self._instance: int | None = None
        self._wndproc_ref = None
        self._class_name = f"worthlesstaskWindow{int(time.time() * 1000) % 10_000_000}"
        self._worker: threading.Thread | None = None
        self._destroyed = False
        self._closing = False
        self._restart_pending = False

        # GDI bookkeeping: every object/DC created is tracked and released once.
        self._objects: list[int] = []
        self._dcs: list[int] = []
        self._brushes: dict[tuple[int, int, int], int] = {}
        self._brush_colors: dict[int, tuple[int, int, int]] = {}
        self._pens: dict[tuple[int, int, int, int], int] = {}
        self._pen_info: dict[int, tuple[tuple[int, int, int], int]] = {}
        self._fonts: dict[tuple[float, int, str], int] = {}
        self._cursors: dict[str, int] = {}
        self._icon_small = 0
        self._icon_big = 0
        self._icon_hero = 0
        self._dwm_blur = False
        self._dwm_rounded = False
        self._gp: ctypes.c_void_p | None = None

        # Layout / interaction state
        self._scale = 1.0
        self._client = (DEFAULT_WIDTH, DEFAULT_HEIGHT)
        self._lay: dict = {}
        self._hot: str | None = None
        self._pressed: str | None = None
        #: Caption-button fade positions, 0.0 (idle) .. 1.0 (hovered/pressed).
        self._hover: dict[str, float] = {}
        self._mouse: tuple[int, int] | None = None
        self._tracking_leave = False
        self._dragging = False
        self._drag_origin = (0, 0, 0, 0)
        self._drag_moved = False
        self._last_click = 0.0
        self._expanded = False
        self._error_height = 0
        self._last_display: tuple | None = None
        #: 0 = home, 1 = about. The sidebar is the only navigation in the window.
        self._nav = 0
        #: Interface language, flipped by the EN/RU switch in the title bar.
        self._lang = "ru"
        #: Set once if the paint pass ever raises, so the guard logs only the first.
        self._paint_failed = False

        # ``_rendered`` backs :meth:`_set_text`: the OS window title is only written
        # when it actually changes, which keeps Discord's window scan quiet.
        self._rendered: dict[int, str] = {}

    # ------------------------------------------------------------------ GDI cache
    def _track(self, handle: int) -> int:
        if handle:
            self._objects.append(handle)
        return handle

    def _brush(self, rgb: tuple[int, int, int]) -> int:
        handle = self._brushes.get(rgb)
        if handle is None:
            handle = self._track(_gdi32.CreateSolidBrush(_rgb(rgb)))
            self._brushes[rgb] = handle
            self._brush_colors[handle] = rgb
        return handle

    def _pen(self, rgb: tuple[int, int, int], width: int = 1, style: int = PS_SOLID) -> int:
        key = (rgb[0], rgb[1], rgb[2], width)
        handle = self._pens.get(key)
        if handle is None:
            handle = self._track(_gdi32.CreatePen(style, width, _rgb(rgb)))
            self._pens[key] = handle
            self._pen_info[handle] = (rgb, width)
        return handle

    def _font(self, size: float, weight: int = FW_NORMAL, face: str = "Segoe UI") -> int:
        key = (size, weight, face)
        handle = self._fonts.get(key)
        if handle is None:
            pixels = max(1, int(round(size * self._scale)))
            handle = self._track(
                _gdi32.CreateFontW(
                    -pixels, 0, 0, 0, weight, 0, 0, 0,
                    DEFAULT_CHARSET, 0, 0, CLEARTYPE_QUALITY, 0, face,
                )
            )
            self._fonts[key] = handle
        return handle

    def _release_resources(self) -> None:
        if self._gp and _gdiplus is not None:
            try:
                _gdiplus.GdipDeleteGraphics(self._gp)
            except Exception:  # noqa: BLE001
                pass
        self._gp = None
        for handle in self._objects:
            try:
                _gdi32.DeleteObject(handle)
            except Exception:  # noqa: BLE001
                pass
        for dc in self._dcs:
            try:
                _gdi32.DeleteDC(dc)
            except Exception:  # noqa: BLE001
                pass
        self._objects.clear()
        self._dcs.clear()
        self._brushes.clear()
        self._brush_colors.clear()
        self._pens.clear()
        self._pen_info.clear()
        self._fonts.clear()
        self._cursors.clear()
        for handle in (self._icon_small, self._icon_big, self._icon_hero):
            if handle:
                try:
                    _user32.DestroyIcon(handle)
                except Exception:  # noqa: BLE001
                    pass
        self._icon_small = 0
        self._icon_big = 0
        self._icon_hero = 0

    def _open_gp(self, hdc: int) -> tuple[ctypes.c_void_p | None, bool]:
        if self._gp:
            return self._gp, False
        if not _ensure_gdip() or not hdc:
            return None, False
        gp = ctypes.c_void_p()
        if _gdiplus.GdipCreateFromHDC(hdc, ctypes.byref(gp)) != 0 or not gp:
            return None, False
        _gdiplus.GdipSetSmoothingMode(gp, 4)
        _gdiplus.GdipSetPixelOffsetMode(gp, 4)
        return gp, True

    def _close_gp(self, gp: ctypes.c_void_p | None, owned: bool) -> None:
        if owned and gp and _gdiplus is not None:
            _gdiplus.GdipDeleteGraphics(gp)

    # ------------------------------------------------------------- flat panels

    def _panel(
        self, hdc: int, rect: tuple[int, int, int, int], radius: int,
        fill: tuple[int, int, int], edge: tuple[int, int, int] | None = None,
    ) -> None:
        """A matte panel with one crisp anti-aliased warm outline."""
        self._fill_round(hdc, rect, radius, self._brush(fill))
        self._stroke_round(hdc, rect, radius, edge or COLOR_FRAME, 1)

    # ------------------------------------------------------------- small drawing
    def _fill_round(
        self, hdc: int, rect: tuple[int, int, int, int], radius: int,
        brush: int, pen: int | None = None,
    ) -> None:
        left, top, right, bottom = rect
        if right - left <= 0 or bottom - top <= 0:
            return
        fill_rgb = self._brush_colors.get(brush)
        pen_spec = self._pen_info.get(pen) if pen is not None else None
        if radius <= 0 and fill_rgb is not None and pen_spec is None:
            box = RECT(int(left), int(top), int(right), int(bottom))
            _user32.FillRect(hdc, ctypes.byref(box), brush)
            return
        gp, owned = self._open_gp(hdc)
        if gp and (fill_rgb is not None or pen_spec is not None):
            try:
                inset = 0.5 if pen_spec is not None else 0.0
                path = _gdip_round_path(
                    left + inset, top + inset, right - inset, bottom - inset, max(0, radius)
                )
                if path:
                    try:
                        if fill_rgb is not None:
                            gbrush = ctypes.c_void_p()
                            if _gdiplus.GdipCreateSolidFill(_argb(fill_rgb), ctypes.byref(gbrush)) == 0 and gbrush:
                                _gdiplus.GdipFillPath(gp, gbrush, path)
                                _gdiplus.GdipDeleteBrush(gbrush)
                        if pen_spec is not None:
                            p_rgb, p_w = pen_spec
                            gpen = ctypes.c_void_p()
                            if _gdiplus.GdipCreatePen1(_argb(p_rgb), float(max(1, p_w)), 2, ctypes.byref(gpen)) == 0 and gpen:
                                _gdiplus.GdipDrawPath(gp, gpen, path)
                                _gdiplus.GdipDeletePen(gpen)
                        return
                    finally:
                        _gdiplus.GdipDeletePath(path)
            finally:
                self._close_gp(gp, owned)
        old_brush = _gdi32.SelectObject(hdc, brush)
        old_pen = _gdi32.SelectObject(
            hdc, pen if pen is not None else _gdi32.GetStockObject(NULL_PEN)
        )
        _gdi32.RoundRect(hdc, left, top, right, bottom, radius * 2, radius * 2)
        _gdi32.SelectObject(hdc, old_brush)
        _gdi32.SelectObject(hdc, old_pen)

    def _stroke_round(
        self, hdc: int, rect: tuple[int, int, int, int], radius: int,
        color: tuple[int, int, int], width: int = 1,
    ) -> None:
        self._fill_round(hdc, rect, radius, _gdi32.GetStockObject(HOLLOW_BRUSH), self._pen(color, width))

    def _line(
        self, hdc: int, x1: float, y1: float, x2: float, y2: float,
        color: tuple[int, int, int], width: float = 1,
    ) -> None:
        gp, owned = self._open_gp(hdc)
        if gp:
            try:
                gpen = ctypes.c_void_p()
                if _gdiplus.GdipCreatePen1(_argb(color), float(max(1.0, width)), 2, ctypes.byref(gpen)) == 0 and gpen:
                    _gdiplus.GdipSetPenStartCap(gpen, 2)
                    _gdiplus.GdipSetPenEndCap(gpen, 2)
                    _gdiplus.GdipDrawLine(gp, gpen, float(x1), float(y1), float(x2), float(y2))
                    _gdiplus.GdipDeletePen(gpen)
                    return
            finally:
                self._close_gp(gp, owned)
        old_pen = _gdi32.SelectObject(hdc, self._pen(color, max(1, int(round(width)))))
        _gdi32.MoveToEx(hdc, int(x1), int(y1), None)
        _gdi32.LineTo(hdc, int(x2), int(y2))
        _gdi32.SelectObject(hdc, old_pen)

    def _polyline(
        self, hdc: int, points: list[tuple[float, float]],
        color: tuple[int, int, int], width: float = 1,
    ) -> None:
        if len(points) < 2:
            return
        gp, owned = self._open_gp(hdc)
        if gp:
            try:
                gpen = ctypes.c_void_p()
                if _gdiplus.GdipCreatePen1(_argb(color), float(max(1.0, width)), 2, ctypes.byref(gpen)) == 0 and gpen:
                    _gdiplus.GdipSetPenStartCap(gpen, 2)
                    _gdiplus.GdipSetPenEndCap(gpen, 2)
                    _gdiplus.GdipSetPenLineJoin(gpen, 2)
                    arr = (GpPointF * len(points))(*(GpPointF(float(x), float(y)) for x, y in points))
                    _gdiplus.GdipDrawLines(gp, gpen, arr, len(points))
                    _gdiplus.GdipDeletePen(gpen)
                    return
            finally:
                self._close_gp(gp, owned)
        array = (wintypes.POINT * len(points))(*(wintypes.POINT(int(x), int(y)) for x, y in points))
        old_pen = _gdi32.SelectObject(hdc, self._pen(color, max(1, int(round(width)))))
        old_brush = _gdi32.SelectObject(hdc, _gdi32.GetStockObject(HOLLOW_BRUSH))
        _gdi32.Polyline(hdc, array, len(points))
        _gdi32.SelectObject(hdc, old_pen)
        _gdi32.SelectObject(hdc, old_brush)

    def _polygon(
        self, hdc: int, points: list[tuple[float, float]], color: tuple[int, int, int]
    ) -> None:
        if len(points) < 3:
            return
        gp, owned = self._open_gp(hdc)
        if gp:
            try:
                gbrush = ctypes.c_void_p()
                if _gdiplus.GdipCreateSolidFill(_argb(color), ctypes.byref(gbrush)) == 0 and gbrush:
                    arr = (GpPointF * len(points))(*(GpPointF(float(x), float(y)) for x, y in points))
                    _gdiplus.GdipFillPolygon(gp, gbrush, arr, len(points), 0)
                    _gdiplus.GdipDeleteBrush(gbrush)
                    return
            finally:
                self._close_gp(gp, owned)
        array = (wintypes.POINT * len(points))(*(wintypes.POINT(int(x), int(y)) for x, y in points))
        old_brush = _gdi32.SelectObject(hdc, self._brush(color))
        old_pen = _gdi32.SelectObject(hdc, _gdi32.GetStockObject(NULL_PEN))
        _gdi32.Polygon(hdc, array, len(points))
        _gdi32.SelectObject(hdc, old_brush)
        _gdi32.SelectObject(hdc, old_pen)

    def _dot(
        self, hdc: int, cx: float, cy: float, radius: float, color: tuple[int, int, int]
    ) -> None:
        gp, owned = self._open_gp(hdc)
        if gp:
            try:
                gbrush = ctypes.c_void_p()
                if _gdiplus.GdipCreateSolidFill(_argb(color), ctypes.byref(gbrush)) == 0 and gbrush:
                    r = float(radius)
                    _gdiplus.GdipFillEllipse(gp, gbrush, float(cx) - r, float(cy) - r, r * 2.0, r * 2.0)
                    _gdiplus.GdipDeleteBrush(gbrush)
                    return
            finally:
                self._close_gp(gp, owned)
        old_brush = _gdi32.SelectObject(hdc, self._brush(color))
        old_pen = _gdi32.SelectObject(hdc, _gdi32.GetStockObject(NULL_PEN))
        _gdi32.Ellipse(hdc, int(cx - radius), int(cy - radius), int(cx + radius), int(cy + radius))
        _gdi32.SelectObject(hdc, old_brush)
        _gdi32.SelectObject(hdc, old_pen)

    def _ellipse_stroke(
        self, hdc: int, left: float, top: float, right: float, bottom: float,
        color: tuple[int, int, int], width: float = 1,
    ) -> None:
        gp, owned = self._open_gp(hdc)
        if gp:
            try:
                gpen = ctypes.c_void_p()
                if _gdiplus.GdipCreatePen1(_argb(color), float(max(1.0, width)), 2, ctypes.byref(gpen)) == 0 and gpen:
                    _gdiplus.GdipDrawEllipse(
                        gp, gpen, float(left), float(top), float(right - left), float(bottom - top)
                    )
                    _gdiplus.GdipDeletePen(gpen)
                    return
            finally:
                self._close_gp(gp, owned)
        old_pen = _gdi32.SelectObject(hdc, self._pen(color, max(1, int(round(width)))))
        old_brush = _gdi32.SelectObject(hdc, _gdi32.GetStockObject(HOLLOW_BRUSH))
        _gdi32.Ellipse(hdc, int(left), int(top), int(right), int(bottom))
        _gdi32.SelectObject(hdc, old_pen)
        _gdi32.SelectObject(hdc, old_brush)

    def _text(
        self, hdc: int, text: str, rect: tuple[int, int, int, int], font: int,
        color: tuple[int, int, int],
        flags: int = DT_LEFT | DT_VCENTER | DT_SINGLELINE | DT_NOPREFIX,
    ) -> None:
        if not text:
            return
        old_font = _gdi32.SelectObject(hdc, font)
        _gdi32.SetBkMode(hdc, TRANSPARENT)
        _gdi32.SetTextColor(hdc, _rgb(color))
        box = RECT(rect[0], rect[1], rect[2], rect[3])
        _user32.DrawTextW(hdc, text, -1, ctypes.byref(box), flags)
        _gdi32.SelectObject(hdc, old_font)

    def _text_width(self, hdc: int, text: str, font: int) -> int:
        old_font = _gdi32.SelectObject(hdc, font)
        size = wintypes.SIZE()
        _gdi32.GetTextExtentPoint32W(hdc, text, len(text), ctypes.byref(size))
        _gdi32.SelectObject(hdc, old_font)
        return int(size.cx)

    def _fit_text(self, hdc: int, text: str, font: int, max_width: int) -> str:
        """Truncate with a real ellipsis character, measured, not guessed."""
        if not text or max_width <= 0:
            return ""
        if self._text_width(hdc, text, font) <= max_width:
            return text
        ellipsis = "…"
        low, high = 0, len(text)
        while low < high:
            middle = (low + high + 1) // 2
            if self._text_width(hdc, text[:middle] + ellipsis, font) <= max_width:
                low = middle
            else:
                high = middle - 1
        return text[:low].rstrip() + ellipsis

    def _clip_round(
        self, hdc: int, rect: tuple[int, int, int, int], radius: int
    ) -> None:
        region = _gdi32.CreateRoundRectRgn(
            rect[0], rect[1], rect[2] + 1, rect[3] + 1, radius * 2, radius * 2
        )
        _gdi32.SelectClipRgn(hdc, region)
        _gdi32.DeleteObject(region)

    def _unclip(self, hdc: int) -> None:
        _gdi32.SelectClipRgn(hdc, None)

    # --------------------------------------------------------------------- icons
    def _icon(
        self, hdc: int, name: str, rect: tuple[int, int, int, int],
        color: tuple[int, int, int], width: float = 1.4,
    ) -> None:
        left, top, right, bottom = rect
        box_w = right - left
        box_h = bottom - top
        if box_w <= 0 or box_h <= 0:
            return
        stroke = max(1.15, float(width) * self._scale)

        def px(fx: float) -> float:
            return left + box_w * fx

        def py(fy: float) -> float:
            return top + box_h * fy

        if name == "min":
            self._line(hdc, px(0.22), py(0.5), px(0.78), py(0.5), color, stroke)
        elif name == "max":
            self._polyline(
                hdc,
                [
                    (px(0.18), py(0.18)),
                    (px(0.82), py(0.18)),
                    (px(0.82), py(0.82)),
                    (px(0.18), py(0.82)),
                    (px(0.18), py(0.18)),
                ],
                color,
                stroke,
            )
        elif name == "restore":
            self._polyline(
                hdc,
                [
                    (px(0.32), py(0.32)),
                    (px(0.32), py(0.16)),
                    (px(0.84), py(0.16)),
                    (px(0.84), py(0.68)),
                    (px(0.68), py(0.68)),
                ],
                color,
                stroke,
            )
            self._polyline(
                hdc,
                [
                    (px(0.16), py(0.32)),
                    (px(0.68), py(0.32)),
                    (px(0.68), py(0.84)),
                    (px(0.16), py(0.84)),
                    (px(0.16), py(0.32)),
                ],
                color,
                stroke,
            )
        elif name == "close":
            self._line(hdc, px(0.26), py(0.26), px(0.74), py(0.74), color, stroke)
            self._line(hdc, px(0.74), py(0.26), px(0.26), py(0.74), color, stroke)
        elif name == "updates":
            self._ellipse_stroke(hdc, px(0.12), py(0.12), px(0.88), py(0.88), color, stroke)
            self._line(hdc, px(0.5), py(0.68), px(0.5), py(0.32), color, stroke)
            self._polyline(
                hdc,
                [(px(0.34), py(0.48)), (px(0.5), py(0.32)), (px(0.66), py(0.48))],
                color, stroke,
            )
        elif name == "reconnects":
            self._line(hdc, px(0.16), py(0.36), px(0.84), py(0.36), color, stroke)
            self._polyline(
                hdc,
                [(px(0.66), py(0.20)), (px(0.84), py(0.36)), (px(0.66), py(0.52))],
                color, stroke,
            )
            self._line(hdc, px(0.84), py(0.64), px(0.16), py(0.64), color, stroke)
            self._polyline(
                hdc,
                [(px(0.34), py(0.48)), (px(0.16), py(0.64)), (px(0.34), py(0.80))],
                color, stroke,
            )
        elif name == "uptime":
            self._ellipse_stroke(hdc, px(0.12), py(0.12), px(0.88), py(0.88), color, stroke)
            self._line(hdc, px(0.5), py(0.5), px(0.5), py(0.28), color, stroke)
            self._line(hdc, px(0.5), py(0.5), px(0.68), py(0.60), color, stroke)
        elif name == "warning":
            self._polyline(
                hdc,
                [(px(0.5), py(0.14)), (px(0.88), py(0.84)), (px(0.12), py(0.84)), (px(0.5), py(0.14))],
                color, stroke,
            )
            self._line(hdc, px(0.5), py(0.40), px(0.5), py(0.60), color, stroke)
            self._dot(hdc, px(0.5), py(0.73), max(1.2, stroke * 0.65), color)
        elif name == "chevron_down":
            self._polyline(
                hdc, [(px(0.24), py(0.38)), (px(0.5), py(0.64)), (px(0.76), py(0.38))], color, stroke
            )
        elif name == "chevron_up":
            self._polyline(
                hdc, [(px(0.24), py(0.62)), (px(0.5), py(0.36)), (px(0.76), py(0.62))], color, stroke
            )
        elif name == "copy":
            self._stroke_round(
                hdc, (int(px(0.14)), int(py(0.14)), int(px(0.66)), int(py(0.66))),
                max(2, int(round(2 * self._scale))), color, max(1, int(round(stroke))),
            )
            self._stroke_round(
                hdc, (int(px(0.34)), int(py(0.34)), int(px(0.86)), int(py(0.86))),
                max(2, int(round(2 * self._scale))), color, max(1, int(round(stroke))),
            )
        elif name == "stop":
            # A power mark, not a filled square: dj banned the square glyph.
            cx, cy = px(0.5), py(0.52)
            rx = (px(1.0) - px(0.0)) * 0.35
            ry = (py(1.0) - py(0.0)) * 0.35
            self._polyline(
                hdc,
                [
                    (cx + rx * math.cos(math.radians(130 + step * (280.0 / 24))),
                     cy - ry * math.sin(math.radians(130 + step * (280.0 / 24))))
                    for step in range(25)
                ],
                color, stroke,
            )
            self._line(hdc, cx, py(0.10), cx, cy, color, stroke)
        elif name == "play":
            self._polygon(
                hdc, [(px(0.26), py(0.18)), (px(0.82), py(0.5)), (px(0.26), py(0.82))], color
            )
        elif name == "home":
            self._polyline(
                hdc, [(px(0.14), py(0.47)), (px(0.5), py(0.15)), (px(0.86), py(0.47))], color, stroke,
            )
            self._polyline(
                hdc,
                [(px(0.27), py(0.43)), (px(0.27), py(0.85)), (px(0.73), py(0.85)), (px(0.73), py(0.43))],
                color, stroke,
            )
            self._line(hdc, px(0.44), py(0.85), px(0.44), py(0.6), color, stroke)
            self._line(hdc, px(0.56), py(0.85), px(0.56), py(0.6), color, stroke)
        elif name == "info":
            self._ellipse_stroke(hdc, px(0.13), py(0.13), px(0.87), py(0.87), color, stroke)
            self._dot(hdc, px(0.5), py(0.32), max(1.2, stroke * 0.65), color)
            self._line(hdc, px(0.5), py(0.47), px(0.5), py(0.72), color, stroke)

    # -------------------------------------------------------------------- layout
    def _scale_for(self, value: float) -> int:
        return int(round(value * self._scale))

    def _stack_height(self) -> int:
        """Logical card height the window needs, from the card top to the footer."""
        return (
            TITLEBAR_HEIGHT
            + CONTENT_PAD
            + HERO_ICON
            + CONTENT_GAP
            + STATS_HEIGHT
            + CONTENT_GAP
            + ERROR_COLLAPSED
            + ACTION_GAP
            + ACTION_HEIGHT
            + FOOTER_GAP
            + FOOTER_HEIGHT
            + CONTENT_PAD
        )

    def _min_client(self) -> tuple[int, int]:
        return (
            self._scale_for(MIN_WIDTH),
            self._scale_for(self._stack_height() + CARD_INSET * 2),
        )

    # -------------------------------------------------------------------- layout
    def _layout(self) -> dict:
        s = self._scale_for
        width, height = self._client
        inset = s(CARD_INSET)
        card = (inset, inset, width - inset, height - inset)
        lay: dict = {"card": card, "width": width, "height": height}

        # Title bar ------------------------------------------------------------
        bar = s(TITLEBAR_HEIGHT)
        titlebar = (card[0], card[1], card[2], card[1] + bar)
        lay["titlebar"] = titlebar
        lay["title_rule"] = (card[0], titlebar[3], card[2], titlebar[3])
        button, gap, pad = s(TITLE_BUTTON), s(TITLE_BUTTON_GAP), s(TITLE_BUTTON_PAD)
        top = titlebar[1] + (bar - button) // 2
        right = titlebar[2] - pad
        lay["btn_close"] = (right - button, top, right, top + button)
        lay["btn_max"] = (lay["btn_close"][0] - gap - button, top, lay["btn_close"][0] - gap, top + button)
        lay["btn_min"] = (lay["btn_max"][0] - gap - button, top, lay["btn_max"][0] - gap, top + button)
        mark = s(18)
        lang_w, lang_h = s(36), s(22)
        lang_top = titlebar[1] + (bar - lang_h) // 2
        lang_left = card[0] + s(14) + mark + s(10)
        lay["lang_en"] = (lang_left, lang_top, lang_left + lang_w, lang_top + lang_h)
        lay["lang_ru"] = (lang_left + lang_w + s(4), lang_top,
                          lang_left + lang_w + s(4) + lang_w, lang_top + lang_h)
        lay["title_icon"] = (card[0] + s(14), titlebar[1] + (bar - mark) // 2, card[0] + s(14) + mark, titlebar[1] + (bar - mark) // 2 + mark)
        lay["title_text"] = (lay["lang_ru"][2] + s(10), titlebar[1], lay["btn_min"][0] - s(12), titlebar[3])

        # Sidebar --------------------------------------------------------------
        # Exactly two entries, then the sheet ends: the brand block, a divider and
        # the two navigation rows. Nothing else lives here on purpose.
        side_w = min(s(SIDEBAR_WIDTH), max(s(186), width // 3))
        side = (card[0], titlebar[3], card[0] + side_w, card[3])
        lay["side"] = side
        inner_l, inner_r = side[0] + s(SIDEBAR_PAD), side[2] - s(SIDEBAR_PAD)
        tile = s(BRAND_TILE)
        brand_top = side[1] + s(26)
        lay["brand_tile"] = (inner_l, brand_top, inner_l + tile, brand_top + tile)
        lay["brand_name"] = (inner_l, brand_top + tile + s(14), inner_r, brand_top + tile + s(38))
        lay["brand_caption"] = (inner_l, brand_top + tile + s(38), inner_r, brand_top + tile + s(54))
        rule_y = brand_top + tile + s(70)
        lay["side_rule"] = (inner_l, rule_y, inner_r, rule_y)
        nav_h, nav_gap = s(NAV_ITEM_HEIGHT), s(NAV_GAP)
        nav_top = rule_y + s(20)
        lay["nav_home"] = (inner_l, nav_top, inner_r, nav_top + nav_h)
        lay["nav_about"] = (inner_l, nav_top + nav_h + nav_gap, inner_r, nav_top + nav_h + nav_gap + nav_h)

        # Content --------------------------------------------------------------
        left, right_c = side[2] + s(CONTENT_GAP), card[2] - s(CONTENT_PAD)
        y = titlebar[3] + s(CONTENT_PAD)
        icon = s(HERO_ICON)
        lay["hero_icon"] = (left, y, left + icon, y + icon)
        status_len = len(self._status_label())
        pill_h = s(28)
        pill_w = min(max(s(132), s(38 + status_len * 7)), (right_c - left) // 2)
        pill = (right_c - pill_w, y + (icon - pill_h) // 2, right_c, y + (icon - pill_h) // 2 + pill_h)
        lay["status_pill"] = pill
        dot = s(8)
        middle = (pill[1] + pill[3]) // 2
        lay["status_dot"] = (pill[0] + s(13), middle - dot // 2, pill[0] + s(13) + dot, middle - dot // 2 + dot)
        lay["status_text"] = (lay["status_dot"][2] + s(8), pill[1], pill[2] - s(12), pill[3])
        lay["hero_name"] = (left + icon + s(16), y + s(4), pill[0] - s(12), y + s(32))
        y += icon + s(CONTENT_GAP)

        stat_h, stat_gap, pad_in = s(STATS_HEIGHT), s(STATS_GAP), s(13)
        stat_w = max(s(112), (right_c - left - 2 * stat_gap) // 3)
        columns = []
        for index in range(3):
            x0 = left + index * (stat_w + stat_gap)
            rect = (x0, y, x0 + stat_w, y + stat_h)
            columns.append({
                "rect": rect,
                "icon": (rect[0] + pad_in, rect[1] + pad_in, rect[0] + pad_in + s(14), rect[1] + pad_in + s(14)),
                "label": (rect[0] + pad_in + s(20), rect[1] + pad_in - s(2), rect[2] - pad_in, rect[1] + pad_in + s(16)),
                "value": (rect[0] + pad_in, rect[1] + pad_in + s(20), rect[2] - pad_in, rect[1] + pad_in + s(50)),
            })
        lay["stats"] = columns
        y += stat_h + s(CONTENT_GAP)

        foot_y = card[3] - s(CONTENT_PAD) - s(FOOTER_HEIGHT)
        lay["foot_rule"] = (left, foot_y, right_c, foot_y)
        lay["foot_left"] = (left, foot_y + s(5), left + s(132), foot_y + s(FOOTER_HEIGHT))
        lay["foot_right"] = (left + s(136), foot_y + s(5), right_c, foot_y + s(FOOTER_HEIGHT))
        action_h = s(ACTION_HEIGHT)
        action_bottom = foot_y - s(FOOTER_GAP)
        action_w = min(s(ACTION_WIDTH), right_c - left)
        action_left = left + ((right_c - left) - action_w) // 2
        lay["action"] = (action_left, action_bottom - action_h, action_left + action_w, action_bottom)
        # The about view fills the whole content column, hero and stats included.
        lay["about"] = (left, titlebar[3] + s(CONTENT_PAD), right_c, lay["action"][1] - s(ACTION_GAP))

        # The console panel takes the leftover height, but only up to a point: past
        # that the slack becomes air above the button instead of a huge empty box.
        room = lay["action"][1] - s(ACTION_GAP) - (y + s(ERROR_COLLAPSED) + self._error_height)
        error_h = s(ERROR_COLLAPSED) + self._error_height + max(0, min(room, s(22)))
        error = (left, y, right_c, y + error_h)
        lay["error"] = error
        lay["error_bar"] = (error[0] + s(2), error[1] + s(12), error[0] + s(5), error[3] - s(12))
        lay["error_icon"] = (error[0] + s(18), error[1] + s(20), error[0] + s(36), error[1] + s(38))
        chev = s(12)
        lay["error_chevron"] = (error[2] - chev * 2, error[1] + s(24), error[2] - chev, error[1] + s(36))
        text_l = error[0] + s(46)
        lay["error_label"] = (text_l, error[1] + s(11), error[2] - s(38), error[1] + s(29))
        lay["error_preview"] = (text_l, error[1] + s(30), error[2] - s(38), error[1] + s(50))
        lay["copy"] = None
        lay["error_full"] = None
        lay["error_metrics"] = None
        if self._expanded and self._error_height:
            full_top = error[1] + s(ERROR_COLLAPSED) + s(10)
            lay["error_full"] = (text_l, full_top, error[2] - s(24), full_top + self._error_height - s(ERROR_FOOTER))
            copy_w, copy_h = s(100), s(28)
            lay["copy"] = (error[2] - s(24) - copy_w, error[3] - s(14) - copy_h, error[2] - s(24), error[3] - s(14))
            lay["error_metrics"] = (text_l, error[3] - s(14) - copy_h, lay["copy"][0] - s(12), error[3] - s(14))
        return lay

    # ---------------------------------------------------------------- state text
    #: Every user-facing string, Russian and English. The title-bar switch flips
    #: :attr:`_lang` and the next 1 Hz tick repaints with the other language.
    STRINGS = {
        "nav_home": ("Главная", "Home"),
        "nav_about": ("О приложении", "About"),
        "state_ok": ("подключено", "connected"),
        "state_no_link": ("нет связи с Discord", "no Discord connection"),
        "state_lost": ("соединение потеряно", "connection lost"),
        "state_connecting": ("подключение…", "connecting…"),
        "stat_updates": ("ОБНОВЛЕНИЙ", "UPDATES"),
        "stat_reconnects": ("ПЕРЕПОДКЛЮЧЕНИЙ", "RECONNECTS"),
        "stat_uptime": ("В РАБОТЕ", "ACTIVE"),
        "min": ("мин", "min"),
        "last_error": ("Последняя ошибка:", "Last error:"),
        "action_stop": ("Остановить", "Stop"),
        "action_start": ("Запустить", "Start"),
        "copy": ("Копировать", "Copy"),
        "about_title": ("О приложении", "About"),
        "about_text": (
            "worthlesstask держит настоящее окно с названием игры, поэтому Discord считает игру запущенной.",
            "worthlesstask owns a real window titled after the game, so Discord treats the game as running.",
        ),
        "row_app": ("ПРИЛОЖЕНИЕ", "APP"),
        "row_game": ("ИГРА", "GAME"),
        "row_session": ("СЕССИЯ", "SESSION"),
        "row_window": ("ОКНО", "WINDOW"),
        "session_on": ("активна", "active"),
        "session_off": ("остановлена", "stopped"),
        "err_no_ipc": ("Запусти приложение Discord", "Start the Discord app"),
        "err_no_ack": (
            "Discord не ответил на подключение — пробую снова",
            "Discord did not answer the handshake — retrying",
        ),
        "err_4002": (
            "Discord ограничивает подключения — пауза перед повтором",
            "Discord is throttling connections — pausing before retry",
        ),
        "err_closed": ("Соединение с Discord закрыто", "Discord connection closed"),
    }

    def _t(self, key: str) -> str:
        pair = self.STRINGS[key]
        return pair[0] if self._lang == "ru" else pair[1]

    def _state(self) -> tuple[str, tuple[int, int, int]]:
        """Connection state as a (token, colour) pair. Stats only, never the thread.

        Lower-case on purpose: these are tokens, :meth:`_display` capitalises the
        first letter for the status row.
        """
        stats = self.supervisor.stats
        if stats.connected:
            return self._t("state_ok"), COLOR_OK
        if stats.last_error:
            return self._t("state_no_link"), COLOR_ERROR
        if stats.drops:
            return self._t("state_lost"), COLOR_ERROR
        return self._t("state_connecting"), COLOR_BUSY

    def _metrics_text(self) -> str:
        """Compact one-line summary of the counters.

        The design shows the same numbers in the stat cards; this form is the
        canonical text version (used by the diagnostics footer of the expanded
        console panel and by tests/test_window.py).
        """
        stats = self.supervisor.stats
        if self._lang == "ru":
            return (
                f"Обновлений {stats.updates}   ·   переподключений {stats.reconnects}   ·   "
                f"в работе {self._uptime_text()}"
            )
        return (
            f"Updates {stats.updates}   ·   reconnects {stats.reconnects}   ·   "
            f"active {self._uptime_text()}"
        )

    def _raw_error(self) -> str:
        return (self.supervisor.stats.last_error or "").strip()

    def _friendly_error(self, raw: str) -> str:
        """Translate transport failures the operator can act on.

        "no Discord IPC endpoint accepted a connection (tried ...)" is accurate but
        useless in a one-line UI, and it was being clipped mid-sentence. Anything
        unrecognised is shown verbatim rather than hidden.
        """
        if not raw:
            return ""
        lowered = raw.lower()
        if "no discord ipc endpoint" in lowered or "discord desktop client running" in lowered:
            return self._t("err_no_ipc")
        if "discord-ipc" in lowered and ("error 6" in lowered or "error 2" in lowered):
            # The pipe is gone: Discord is closed or restarting.
            return self._t("err_no_ipc")
        if "no acknowledgement within" in lowered:
            return self._t("err_no_ack")
        if "code=4002" in lowered:
            return self._t("err_4002")
        if "connection is closed" in lowered:
            return self._t("err_closed")
        return raw

    def _error_text(self) -> str:
        return f"{self._t('last_error')} {self._friendly_error(self._raw_error()) or '—'}"

    def _uptime_text(self) -> str:
        """``15 мин`` under an hour, ``01:23:45`` after -- and 0 while stopped.

        ``stats.uptime`` is derived from ``stats.started_at``, which does not move
        when the supervisor stops, so the running flag is what makes a stopped
        window read zero (bug f).
        """
        unit = self._t("min")
        if not self._running():
            return f"0 {unit}"
        seconds = max(0, int(self.supervisor.stats.uptime))
        if seconds < 3600:
            return f"{seconds // 60} {unit}"
        hours, rest = divmod(seconds, 3600)
        minutes, secs = divmod(rest, 60)
        return f"{hours:02d}:{minutes:02d}:{secs:02d}"

    def _running(self) -> bool:
        """True while the supervisor thread is working on a connection."""
        worker = self._worker
        return bool(worker is not None and worker.is_alive() and not self.stop_event.is_set())

    def _status_label(self) -> str:
        token, _ = self._state()
        return token[:1].upper() + token[1:] if token else token

    def _action_label(self) -> str:
        return self._t("action_stop") if self._running() else self._t("action_start")

    def _display(self) -> tuple:
        """Every string the paint pass shows; a change here means a repaint."""
        return (
            self._lang,
            self._status_label(),
            str(self.supervisor.stats.updates),
            str(self.supervisor.stats.reconnects),
            self._uptime_text(),
            self._friendly_error(self._raw_error()) or "—",
            self._action_label(),
            self._expanded,
            self._nav,
        )

    # ------------------------------------------------------------------ painting
    def _paint(self, hdc: int) -> None:
        """Paint with a guard: a bug must never leave a blank window behind.

        ctypes swallows exceptions raised inside the window procedure, so a single
        typo used to leave the user staring at an unpainted white rectangle with
        nothing in any log. The failure is now logged once and the window falls
        back to a flat matte card with the game name on it.
        """
        gp, owned = self._open_gp(hdc)
        self._gp = gp
        try:
            self._paint_design(hdc)
        except Exception:  # noqa: BLE001
            if not self._paint_failed:
                self._paint_failed = True
                self.log.exception("window paint failed; using the flat fallback")
            self._paint_fallback(hdc)
        finally:
            self._gp = None
            self._close_gp(gp, owned)

    def _paint_fallback(self, hdc: int) -> None:
        width, height = self._client
        self._fill_round(hdc, (0, 0, width, height), 0, self._brush(COLOR_BG))
        inset = self._scale_for(CARD_INSET)
        card = (inset, inset, width - inset, height - inset)
        self._fill_round(hdc, card, self._scale_for(CARD_RADIUS), self._brush(COLOR_CARD))
        self._text(
            hdc, self.title,
            (card[0] + self._scale_for(20), card[1] + self._scale_for(20),
             card[2] - self._scale_for(20), card[1] + self._scale_for(48)),
            self._font(13, FW_SEMIBOLD), COLOR_TITLE,
        )

    def _paint_design(self, hdc: int) -> None:
        width, height = self._client
        if width <= 0 or height <= 0:
            return
        lay = self._lay = self._layout()

        card = lay["card"]
        self._fill_round(hdc, (0, 0, width, height), 0, self._brush(COLOR_CARD))
        self._paint_sidebar(hdc, lay)
        self._paint_content(hdc, lay)
        self._paint_titlebar(hdc, lay)
        if not self._dwm_rounded and not self._zoomed():
            self._stroke_round(hdc, card, self._scale_for(CARD_RADIUS), COLOR_FRAME, 1)

    def _paint_sidebar(self, hdc: int, lay: dict) -> None:
        s = self._scale_for
        side = lay["side"]
        side_bg = _blend(COLOR_BG, COLOR_SIDE, 0.55)
        self._fill_round(hdc, side, 0, self._brush(side_bg))
        self._line(hdc, side[2] - 1, side[1], side[2] - 1, side[3], COLOR_FRAME, 1)

        # Brand block: the game's own icon, then its name and the caption.
        tile = lay["brand_tile"]
        self._brand_tile(hdc, tile, side_bg)
        name_font = self._font(13.5, FW_SEMIBOLD)
        name_box = lay["brand_name"]
        self._text(
            hdc, self._fit_text(hdc, self.title, name_font, name_box[2] - name_box[0]),
            name_box, name_font, COLOR_TITLE,
        )
        self._text(
            hdc, "Game Launcher & Assistant", lay["brand_caption"],
            self._font(9.5, FW_MEDIUM), COLOR_MUTED,
        )
        rule = lay["side_rule"]
        self._line(hdc, rule[0], rule[1], rule[2], rule[1], COLOR_LINE, 1)

        # Two navigation rows with active indicator and smooth hover states.
        self._nav_item(hdc, lay["nav_home"], "home", self._t("nav_home"), 0)
        self._nav_item(hdc, lay["nav_about"], "info", self._t("nav_about"), 1)

    def _brand_tile(
        self, hdc: int, rect: tuple[int, int, int, int], backdrop: tuple[int, int, int] = COLOR_SIDE
    ) -> None:
        radius = self._scale_for(10)
        if self._icon_hero:
            self._clip_round(hdc, rect, radius)
            try:
                _user32.DrawIconEx(
                    hdc, rect[0], rect[1], self._icon_hero,
                    rect[2] - rect[0], rect[3] - rect[1], 0, None, DI_NORMAL,
                )
            except Exception:  # noqa: BLE001
                self._letter_tile(hdc, rect, radius, self._font(20, FW_SEMIBOLD))
            self._unclip(hdc)
            self._stroke_round(
                hdc, (rect[0] - 1, rect[1] - 1, rect[2] + 1, rect[3] + 1),
                radius + 1, backdrop, 2,
            )
        else:
            self._letter_tile(hdc, rect, radius, self._font(20, FW_SEMIBOLD))
        self._stroke_round(hdc, rect, radius, COLOR_FRAME, 1)

    def _nav_item(
        self, hdc: int, rect: tuple[int, int, int, int], glyph: str, label: str, index: int,
    ) -> None:
        s = self._scale_for
        key = "nav_home" if index == 0 else "nav_about"
        active = self._nav == index
        hot = self._hot == key and not active
        radius = s(9)
        if active:
            self._fill_round(
                hdc, rect, radius, self._brush(_blend(COLOR_ACCENT, COLOR_CARD, 0.22))
            )
            self._stroke_round(hdc, rect, radius, _blend(COLOR_OUTLINE, COLOR_FRAME, 0.55), 1)
            bar_h = s(18)
            mid_y = (rect[1] + rect[3]) // 2
            self._fill_round(
                hdc,
                (rect[0] + s(4), mid_y - bar_h // 2, rect[0] + s(7), mid_y + bar_h // 2),
                s(2),
                self._brush(COLOR_OK),
            )
        elif hot:
            self._fill_round(hdc, rect, radius, self._brush(COLOR_HOVER_FILL))
            self._stroke_round(hdc, rect, radius, COLOR_LINE, 1)

        middle = (rect[1] + rect[3]) // 2
        icon = (rect[0] + s(16), middle - s(9), rect[0] + s(34), middle + s(9))
        self._icon(hdc, glyph, icon, COLOR_OK if active else (COLOR_BODY if hot else COLOR_MUTED), 1.35)
        font = self._font(12.5, FW_SEMIBOLD if active else FW_MEDIUM)
        color = COLOR_TITLE if (active or hot) else COLOR_MUTED
        self._text(hdc, label, (icon[2] + s(12), rect[1], rect[2] - s(12), rect[3]), font, color)

    def _paint_content(self, hdc: int, lay: dict) -> None:
        if self._nav == 1:
            self._paint_about(hdc, lay)
        else:
            self._paint_hero(hdc, lay)
            self._paint_stats(hdc, lay)
            self._paint_error(hdc, lay)
        self._paint_action(hdc, lay)
        self._paint_footer(hdc, lay)

    def _paint_hero(self, hdc: int, lay: dict) -> None:
        s = self._scale_for
        icon = lay["hero_icon"]
        radius = s(13)
        if self._icon_hero:
            self._clip_round(hdc, icon, radius)
            try:
                _user32.DrawIconEx(
                    hdc, icon[0], icon[1], self._icon_hero,
                    icon[2] - icon[0], icon[3] - icon[1], 0, None, DI_NORMAL,
                )
            except Exception:  # noqa: BLE001
                self._letter_tile(hdc, icon, radius, self._font(26, FW_SEMIBOLD))
            self._unclip(hdc)
            self._stroke_round(
                hdc, (icon[0] - 1, icon[1] - 1, icon[2] + 1, icon[3] + 1),
                radius + 1, COLOR_CARD, 2,
            )
        else:
            self._letter_tile(hdc, icon, radius, self._font(26, FW_SEMIBOLD))
        self._stroke_round(hdc, icon, radius, _blend(COLOR_OUTLINE, COLOR_FRAME, 0.45), 1)

        name_font = self._font(19, FW_SEMIBOLD)
        name_box = lay["hero_name"]
        self._text(
            hdc, self._fit_text(hdc, self.title, name_font, name_box[2] - name_box[0]),
            name_box, name_font, COLOR_TITLE,
        )
        sub_box = (name_box[0], name_box[3] + s(2), name_box[2], icon[3] - s(2))
        sub_font = self._font(10, FW_MEDIUM)
        app_id = getattr(self.config, "client_id", "") or "—"
        sub_label = f"Discord Rich Presence  ·  ID {app_id}"
        self._text(
            hdc, self._fit_text(hdc, sub_label, sub_font, sub_box[2] - sub_box[0]),
            sub_box, sub_font, COLOR_MUTED,
        )

        pill = lay["status_pill"]
        _, color = self._state()
        radius_pill = (pill[3] - pill[1]) // 2
        self._fill_round(hdc, pill, radius_pill, self._brush(_blend(color, COLOR_CARD, 0.14)))
        self._stroke_round(hdc, pill, radius_pill, _blend(color, COLOR_FRAME, 0.72), 1)
        dot = lay["status_dot"]
        center = ((dot[0] + dot[2]) / 2.0, (dot[1] + dot[3]) / 2.0)
        dot_r = (dot[2] - dot[0]) / 2.0
        self._dot(hdc, center[0], center[1], dot_r + s(2), _blend(color, COLOR_CARD, 0.28))
        self._dot(hdc, center[0], center[1], dot_r, color)
        pill_font = self._font(11.5, FW_SEMIBOLD)
        box = lay["status_text"]
        self._text(
            hdc, self._fit_text(hdc, self._status_label(), pill_font, box[2] - box[0]),
            box, pill_font, COLOR_TITLE,
        )

    def _paint_stats(self, hdc: int, lay: dict) -> None:
        stats = self.supervisor.stats
        values = (str(stats.updates), str(stats.reconnects), self._uptime_text())
        names = ("updates", "reconnects", "uptime")
        labels = (self._t("stat_updates"), self._t("stat_reconnects"), self._t("stat_uptime"))
        label_font = self._font(9.5, FW_SEMIBOLD)
        value_font = self._font(20, FW_SEMIBOLD)
        card_fill = _blend(COLOR_HOVER_FILL, COLOR_PANEL, 0.42)
        for column, name, label, value in zip(lay["stats"], names, labels, values):
            rect = column["rect"]
            self._panel(hdc, rect, self._scale_for(10), card_fill, COLOR_PANEL_EDGE)
            self._icon(hdc, name, column["icon"], COLOR_OK, 1.3)
            self._text(hdc, label, column["label"], label_font, COLOR_MUTED)
            self._text(hdc, value, column["value"], value_font, COLOR_TITLE)

    def _paint_error(self, hdc: int, lay: dict) -> None:
        block = lay["error"]
        has_error = bool(self._raw_error())
        radius = self._scale_for(10)
        fill = (34, 22, 19) if has_error else _blend(COLOR_HOVER_FILL, COLOR_PANEL, 0.28)
        edge = _blend(COLOR_ERROR, COLOR_FRAME, 0.45) if has_error else COLOR_PANEL_EDGE
        self._panel(hdc, block, radius, fill, edge)
        bar_color = COLOR_ERROR if has_error else (COLOR_OK if self.supervisor.stats.connected else COLOR_LINE)
        self._fill_round(
            hdc, lay["error_bar"], self._scale_for(2),
            self._brush(bar_color),
        )
        if has_error:
            self._icon(hdc, "warning", lay["error_icon"], COLOR_ERROR, 1.3)
        else:
            self._icon(hdc, "info", lay["error_icon"], COLOR_OK if self.supervisor.stats.connected else COLOR_MUTED, 1.25)
        self._text(
            hdc, self._t("last_error"), lay["error_label"],
            self._font(9, FW_SEMIBOLD), COLOR_MUTED,
        )
        preview = self._friendly_error(self._raw_error()) or "—"
        preview_font = self._font(12, FW_MEDIUM)
        preview_box = lay["error_preview"]
        self._text(
            hdc, self._fit_text(hdc, preview, preview_font, preview_box[2] - preview_box[0]),
            preview_box, preview_font, COLOR_BODY,
        )
        if has_error:
            self._icon(
                hdc, "chevron_up" if self._expanded else "chevron_down",
                lay["error_chevron"], COLOR_MUTED, 1.25,
            )

        if not self._expanded or lay["error_full"] is None:
            return
        self._text(
            hdc, preview, lay["error_full"],
            self._font(10.5, FW_NORMAL, "Consolas"), COLOR_BODY,
            DT_LEFT | DT_WORDBREAK | DT_NOPREFIX,
        )
        self._text(
            hdc, self._metrics_text(), lay["error_metrics"],
            self._font(9.5), COLOR_MUTED,
        )
        copy = lay["copy"]
        if copy is None:
            return
        hot = self._hot == "copy" and has_error
        self._fill_round(
            hdc, copy, self._scale_for(7),
            self._brush(COLOR_HOVER_FILL if hot else COLOR_CARD),
        )
        self._stroke_round(hdc, copy, self._scale_for(7), COLOR_OUTLINE if hot else COLOR_FRAME, 1)
        color = COLOR_BUTTON_TEXT if hot else (COLOR_TITLE if has_error else COLOR_MUTED)
        glyph = self._scale_for(13)
        label = self._t("copy")
        font = self._font(10.5, FW_MEDIUM)
        text_w = self._text_width(hdc, label, font)
        start = copy[0] + ((copy[2] - copy[0]) - (glyph + self._scale_for(7) + text_w)) // 2
        middle = (copy[1] + copy[3]) // 2
        self._icon(hdc, "copy", (start, middle - glyph // 2, start + glyph, middle - glyph // 2 + glyph), color, 1.2)
        self._text(hdc, label, (start + glyph + self._scale_for(7), copy[1], copy[2], copy[3]), font, color)

    def _paint_about(self, hdc: int, lay: dict) -> None:
        s = self._scale_for
        block = lay["about"]
        self._panel(hdc, block, s(10), _blend(COLOR_HOVER_FILL, COLOR_PANEL, 0.35), COLOR_PANEL_EDGE)
        pad = s(24)
        self._text(
            hdc, self._t("about_title"),
            (block[0] + pad, block[1] + s(16), block[2] - pad, block[1] + s(42)),
            self._font(16, FW_SEMIBOLD), COLOR_TITLE,
        )
        self._text(
            hdc, self._t("about_text"),
            (block[0] + pad, block[1] + s(46), block[2] - pad, block[1] + s(84)),
            self._font(10.5), COLOR_BODY,
            DT_LEFT | DT_WORDBREAK | DT_NOPREFIX,
        )
        rows = (
            (self._t("row_app"), f"worthlesstask {APP_VERSION}"),
            (self._t("row_game"), self.title),
            (self._t("row_session"),
             self._t("session_on") if self._running() else self._t("session_off")),
            (self._t("row_window"),
             f"{self._client[0]}×{self._client[1]} · DPI {int(self._scale * 100)}%"),
        )
        label_font = self._font(9.5, FW_SEMIBOLD)
        value_font = self._font(11, FW_MEDIUM)
        label_w = s(140)
        y = block[1] + s(102)
        for label, value in rows:
            self._text(hdc, label, (block[0] + pad, y, block[0] + pad + label_w, y + s(22)),
                       label_font, COLOR_MUTED)
            value_box = (block[0] + pad + label_w, y, block[2] - pad, y + s(22))
            self._text(
                hdc, self._fit_text(hdc, value, value_font, value_box[2] - value_box[0]),
                value_box, value_font, COLOR_TITLE,
            )
            y += s(36)

    def _paint_action(self, hdc: int, lay: dict) -> None:
        rect = lay["action"]
        pressed = self._pressed == "action"
        hot = self._hot == "action" or pressed
        running = self._running()
        if pressed:
            fill = COLOR_ACCENT_PRESS
            rect = (rect[0], rect[1] + self._scale_for(1), rect[2], rect[3] + self._scale_for(1))
            edge = COLOR_OUTLINE
        elif hot:
            fill = COLOR_ACCENT_HOT
            edge = COLOR_OK
        elif running:
            fill = _blend(COLOR_ACCENT, COLOR_CARD, 0.78)
            edge = COLOR_OUTLINE
        else:
            fill = COLOR_ACCENT
            edge = COLOR_OK
        radius = (rect[3] - rect[1]) // 2
        self._fill_round(hdc, rect, radius, self._brush(fill))
        self._stroke_round(hdc, rect, radius, edge, 1)

        glyph = self._scale_for(15)
        label = self._action_label()
        font = self._font(13.5, FW_SEMIBOLD)
        text_w = self._text_width(hdc, label, font)
        start = rect[0] + ((rect[2] - rect[0]) - (glyph + self._scale_for(10) + text_w)) // 2
        middle = (rect[1] + rect[3]) // 2
        self._icon(
            hdc, "stop" if running else "play",
            (start, middle - glyph // 2, start + glyph, middle - glyph // 2 + glyph),
            COLOR_BUTTON_TEXT, 1.45,
        )
        self._text(
            hdc, label, (start + glyph + self._scale_for(10), rect[1], rect[2], rect[3]),
            font, COLOR_BUTTON_TEXT,
        )

    def _paint_footer(self, hdc: int, lay: dict) -> None:
        rule = lay["foot_rule"]
        self._line(hdc, rule[0], rule[1], rule[2], rule[1], COLOR_LINE, 1)
        font = self._font(9.5)
        self._text(
            hdc, f"worthlesstask {APP_VERSION}", lay["foot_left"], font, COLOR_MUTED,
        )
        self._text(
            hdc, self._metrics_text(), lay["foot_right"], font, COLOR_MUTED,
            DT_RIGHT | DT_VCENTER | DT_SINGLELINE | DT_NOPREFIX,
        )

    def _paint_titlebar(self, hdc: int, lay: dict) -> None:
        titlebar = lay["titlebar"]
        bar_bg = _blend(COLOR_BG, COLOR_CARD, 0.5)
        self._fill_round(hdc, titlebar, 0, self._brush(bar_bg))
        icon = lay["title_icon"]
        small_font = self._font(8.5, FW_SEMIBOLD)
        if self._icon_small:
            try:
                _user32.DrawIconEx(
                    hdc, icon[0], icon[1], self._icon_small,
                    icon[2] - icon[0], icon[3] - icon[1], 0, None, DI_NORMAL,
                )
            except Exception:  # noqa: BLE001 - a missing icon is never fatal
                self._letter_tile(hdc, icon, max(3, (icon[2] - icon[0]) // 4), small_font)
        else:
            self._letter_tile(hdc, icon, max(3, (icon[2] - icon[0]) // 4), small_font)

        title_font = self._font(11.5, FW_SEMIBOLD)
        title_box = lay["title_text"]
        self._text(
            hdc, self._fit_text(hdc, self.title, title_font, title_box[2] - title_box[0]),
            title_box, title_font, COLOR_TITLE,
        )
        rule = lay["title_rule"]
        self._line(hdc, rule[0], rule[1], rule[2], rule[1], COLOR_FRAME, 1)
        self._paint_lang(hdc, lay)

        for key, glyph in (
            ("btn_min", "min"),
            ("btn_max", "max" if not self._zoomed() else "restore"),
            ("btn_close", "close"),
        ):
            rect = lay[key]
            fade = self._hover.get(key, 0.0)
            if fade > 0.0:
                color = (COLOR_CLOSE_HOT if key == "btn_close" else COLOR_HOVER_FILL)
                self._fill_round(
                    hdc, rect, self._scale_for(6),
                    self._brush(_blend(color, bar_bg, fade)),
                )
            pressed = self._pressed == key
            glyph_color = (
                COLOR_BUTTON_TEXT if (fade > 0.5 and key == "btn_close") else COLOR_TITLE
            )
            inset = self._scale_for(8) - (self._scale_for(1) if pressed else 0)
            self._icon(
                hdc, glyph,
                (rect[0] + inset, rect[1] + inset, rect[2] - inset, rect[3] - inset),
                glyph_color, 1.25,
            )

    def _paint_lang(self, hdc: int, lay: dict) -> None:
        """The EN/RU switch, like the one on the dashboard."""
        font = self._font(9.5, FW_SEMIBOLD)
        for key, code in (("lang_en", "en"), ("lang_ru", "ru")):
            rect = lay[key]
            active = self._lang == code
            fade = self._hover.get(key, 0.0)
            radius = (rect[3] - rect[1]) // 2
            if active:
                fill = _blend(COLOR_ACCENT, COLOR_CARD, 0.28 + 0.15 * fade)
                edge = _blend(COLOR_OK, COLOR_OUTLINE, fade)
                color = COLOR_TITLE
                self._fill_round(hdc, rect, radius, self._brush(fill))
            else:
                if fade > 0.05:
                    self._fill_round(
                        hdc, rect, radius, self._brush(_blend(COLOR_HOVER_FILL, COLOR_CARD, fade))
                    )
                edge = _blend(COLOR_OUTLINE, COLOR_FRAME, fade)
                color = COLOR_TITLE if fade > 0.5 else COLOR_MUTED
            self._stroke_round(hdc, rect, radius, edge, 1)
            self._text(hdc, code.upper(), rect, font, color,
                       DT_CENTER | DT_VCENTER | DT_SINGLELINE | DT_NOPREFIX)

    def _letter_tile(self, hdc: int, rect: tuple[int, int, int, int], radius: int, font: int) -> None:
        """Warm dark tile with a crisp initial. Only used when no art exists."""
        self._fill_round(hdc, rect, radius, self._brush(_blend(COLOR_ACCENT, COLOR_CARD, 0.25)))
        letter = (self.title or "?").strip()[:1].upper() or "?"
        self._text(
            hdc, letter, rect, font, COLOR_BUTTON_TEXT,
            DT_CENTER | DT_VCENTER | DT_SINGLELINE | DT_NOPREFIX,
        )

    # ------------------------------------------------------------------- window
    def _zoomed(self) -> bool:
        if not self._hwnd:
            return False
        try:
            return bool(_user32.IsZoomed(self._hwnd))
        except Exception:  # noqa: BLE001
            return False

    def _cursor(self, name: str) -> int:
        handle = self._cursors.get(name)
        if handle is None:
            resource = CURSORS.get(name, IDC_ARROW)
            handle = _user32.LoadCursorW(None, ctypes.c_wchar_p(resource)) or 0
            self._cursors[name] = handle
        return handle

    def _invalidate(self) -> None:
        if self._hwnd and not self._destroyed:
            _user32.InvalidateRect(self._hwnd, None, False)

    def _hit_test(self, x: int, y: int) -> str | None:
        lay = self._lay or self._layout()
        # Browser-style hitboxes: the clickable area of the caption buttons runs a
        # few pixels past the drawn glyph and meets the window edge, so a click
        # near the corner always lands on Close.
        pad = self._scale_for(5)
        for key in ("btn_close", "btn_max", "btn_min"):
            rect = lay.get(key)
            if rect is None:
                continue
            if _in((rect[0] - pad, rect[1] - pad, rect[2] + pad, rect[3] + pad), x, y):
                return key
        for key in ("action", "copy", "lang_en", "lang_ru"):
            if _in(lay.get(key), x, y):
                return key
        for key in ("nav_home", "nav_about"):
            if _in(lay.get(key), x, y):
                return key
        if _in(lay.get("error"), x, y):
            return "error" if self._raw_error() else None
        if _in(lay.get("titlebar"), x, y):
            return "title"
        return None

    def _resize_border(self, x: int, y: int) -> int:
        if self._zoomed():
            return HTCLIENT
        width, height = self._client
        band = self._scale_for(6)
        left = x < band
        right = x >= width - band
        top = y < band
        bottom = y >= height - band
        if top and left:
            return HTTOPLEFT
        if top and right:
            return HTTOPRIGHT
        if bottom and left:
            return HTBOTTOMLEFT
        if bottom and right:
            return HTBOTTOMRIGHT
        if left:
            return HTLEFT
        if right:
            return HTRIGHT
        if top:
            return HTTOP
        if bottom:
            return HTBOTTOM
        return HTCLIENT

    def _apply_round_region(self) -> None:
        if not self._hwnd:
            return
        # Never apply a 1-bit window region to a top-level window with WS_CAPTION:
        # Windows responds to SetWindowRgn by disabling DWM composited framing and
        # falling back to the legacy Windows 7 Aero non-client frame.
        _user32.SetWindowRgn(self._hwnd, None, True)

    def _apply_backdrop(self) -> None:
        """Configure DWM dark mode, native anti-aliased rounded corners, and warm border."""
        if _dwmapi is None or not self._hwnd:
            return
        self._dwm_blur = False
        self._dwm_rounded = False
        try:
            dark = ctypes.c_int(1)  # matte theme: DWM chrome follows dark
            _dwmapi.DwmSetWindowAttribute(
                self._hwnd, DWMWA_USE_IMMERSIVE_DARK_MODE, ctypes.byref(dark), ctypes.sizeof(dark)
            )
        except Exception:  # noqa: BLE001
            pass
        try:
            corner = ctypes.c_int(DWMWCP_ROUND)
            hr = _dwmapi.DwmSetWindowAttribute(
                self._hwnd, DWMWA_WINDOW_CORNER_PREFERENCE, ctypes.byref(corner), ctypes.sizeof(corner)
            )
            self._dwm_rounded = (hr == 0)
        except Exception:  # noqa: BLE001
            self._dwm_rounded = False
        try:
            border = ctypes.c_uint(_rgb(COLOR_FRAME))
            _dwmapi.DwmSetWindowAttribute(
                self._hwnd, DWMWA_BORDER_COLOR, ctypes.byref(border), ctypes.sizeof(border)
            )
        except Exception:  # noqa: BLE001
            pass
        try:
            class _MARGINS(ctypes.Structure):
                _fields_ = [
                    ("cxLeftWidth", ctypes.c_int),
                    ("cxRightWidth", ctypes.c_int),
                    ("cyTopHeight", ctypes.c_int),
                    ("cyBottomHeight", ctypes.c_int),
                ]

            m = _MARGINS(0, 0, 0, 0)
            _dwmapi.DwmExtendFrameIntoClientArea(self._hwnd, ctypes.byref(m))
        except Exception:  # noqa: BLE001
            pass

    def _on_message(self, hwnd, msg, wparam, lparam):
        if msg == WM_PAINT:
            paint = PAINTSTRUCT()
            hdc = _user32.BeginPaint(hwnd, ctypes.byref(paint))
            try:
                width, height = self._client
                memdc = _gdi32.CreateCompatibleDC(hdc)
                bitmap = _gdi32.CreateCompatibleBitmap(hdc, max(1, width), max(1, height))
                old = _gdi32.SelectObject(memdc, bitmap)
                self._paint(memdc)
                _gdi32.BitBlt(hdc, 0, 0, width, height, memdc, 0, 0, SRCCOPY)
                _gdi32.SelectObject(memdc, old)
                _gdi32.DeleteObject(bitmap)
                _gdi32.DeleteDC(memdc)
            finally:
                _user32.EndPaint(hwnd, ctypes.byref(paint))
            return 0
        if msg == WM_ERASEBKGND:
            return 1
        if msg == WM_SIZE:
            self._client = (lparam & 0xFFFF, (lparam >> 16) & 0xFFFF)
            self._apply_round_region()
            self._invalidate()
            return 0
        if msg == WM_TIMER:
            if wparam == TIMER_HOVER:
                self._hover_tick()
            else:
                self._refresh_text()
            return 0
        if msg == WM_APP_STOPPED:
            if self._restart_pending and not self._destroyed and not self._closing:
                self._begin_restart()
            self._invalidate()
            return 0
        if msg == WM_GETMINMAXINFO:
            self._on_minmax(ctypes.cast(lparam, ctypes.POINTER(MINMAXINFO)).contents)
            return 0
        if msg == WM_NCCALCSIZE:
            # No non-client area, unconditionally: the client area is the whole
            # window, so Windows never draws a caption, a border or a frame no
            # matter what wParam carries. The WS_CAPTION style flag stays set --
            # Discord's detector reads the flags, not the pixels.
            return 0
        if msg == WM_NCACTIVATE:
            # DefWindowProcW repaints the native title bar and Aero frame on focus
            # changes if this message is not handled. Return 1 (TRUE) so the active
            # state updates without drawing non-client chrome.
            return 1
        if msg == WM_NCPAINT:
            # Nothing non-client to paint, even if the system asks.
            return 0
        if msg == WM_NCHITTEST:
            x = ctypes.c_short(lparam & 0xFFFF).value
            y = ctypes.c_short((lparam >> 16) & 0xFFFF).value
            screen = wintypes.POINT(x, y)
            _user32.ScreenToClient(hwnd, ctypes.byref(screen))
            return self._resize_border(screen.x, screen.y)
        if msg == WM_SETCURSOR:
            hit = lparam & 0xFFFF
            if hit == HTCLIENT:
                _user32.SetCursor(self._cursor("hand" if self._hit_test_cursor() else "arrow"))
                return 1
            if hit in (HTLEFT, HTRIGHT):
                _user32.SetCursor(self._cursor("sizewe"))
                return 1
            if hit in (HTTOP, HTBOTTOM):
                _user32.SetCursor(self._cursor("sizens"))
                return 1
            if hit in (HTTOPLEFT, HTBOTTOMRIGHT):
                _user32.SetCursor(self._cursor("sizenwse"))
                return 1
            if hit in (HTTOPRIGHT, HTBOTTOMLEFT):
                _user32.SetCursor(self._cursor("sizenesw"))
                return 1
            return 1
        if msg == WM_MOUSEMOVE:
            self._on_mouse_move(ctypes.c_short(lparam & 0xFFFF).value, ctypes.c_short((lparam >> 16) & 0xFFFF).value)
            return 0
        if msg == WM_LBUTTONDOWN:
            self._on_button_down(
                ctypes.c_short(lparam & 0xFFFF).value,
                ctypes.c_short((lparam >> 16) & 0xFFFF).value,
            )
            return 0
        if msg == WM_LBUTTONUP:
            self._on_button_up(
                ctypes.c_short(lparam & 0xFFFF).value,
                ctypes.c_short((lparam >> 16) & 0xFFFF).value,
            )
            return 0
        if msg == WM_MOUSELEAVE:
            self._tracking_leave = False
            if self._hot is not None:
                self._hot = None
                self._ensure_hover_timer()
                self._invalidate()
            return 0
        if msg == WM_DPICHANGED:
            self._on_dpi_changed(lparam)
            return 0
        if msg == WM_CLOSE:
            if self._destroyed or self._closing:
                return 0
            # Closing is instant: stop the session and destroy the window.
            # Nothing here blocks the message loop.
            self._request_stop()
            self._begin_close()
            return 0
        if msg == WM_DESTROY:
            self._destroyed = True
            _user32.KillTimer(hwnd, TIMER_ID)
            _user32.KillTimer(hwnd, TIMER_HOVER)
            _user32.PostQuitMessage(0)
            return 0
        return _user32.DefWindowProcW(hwnd, msg, wparam, lparam)

    def _hover_target(self, key: str) -> float:
        return 1.0 if (self._hot == key or self._pressed == key) else 0.0

    def _ensure_hover_timer(self) -> None:
        """Run the fade only while a button is mid-transition."""
        if not self._hwnd or self._destroyed:
            return
        keys = ("btn_min", "btn_max", "btn_close", "lang_en", "lang_ru")
        if any(abs(self._hover.get(key, 0.0) - self._hover_target(key)) > 0.01
               for key in keys):
            _user32.SetTimer(self._hwnd, TIMER_HOVER, HOVER_TICK_MS, None)
        else:
            _user32.KillTimer(self._hwnd, TIMER_HOVER)

    def _hover_tick(self) -> None:
        keys = ("btn_min", "btn_max", "btn_close", "lang_en", "lang_ru")
        settled = True
        for key in keys:
            current = self._hover.get(key, 0.0)
            target = self._hover_target(key)
            if abs(current - target) <= 0.01:
                self._hover[key] = target
                continue
            step = HOVER_STEP if target > current else -HOVER_STEP
            value = current + step
            if (step > 0 and value > target) or (step < 0 and value < target):
                value = target
            self._hover[key] = value
            settled = False
        if settled and self._hwnd and not self._destroyed:
            _user32.KillTimer(self._hwnd, TIMER_HOVER)
        self._invalidate()

    def _begin_close(self) -> None:
        """Destroy the window at once. Closing is instant by design."""
        if not self._hwnd or self._destroyed:
            return
        self._closing = True
        _user32.DestroyWindow(self._hwnd)

    def _hit_test_cursor(self) -> bool:
        """True when the hovered pixel is something the user can click."""
        point = self._mouse
        if point is None:
            return False
        return self._hit_test(point[0], point[1]) in (
            "btn_close", "btn_max", "btn_min", "action", "copy", "error",
            "nav_home", "nav_about", "lang_en", "lang_ru",
        )

    def _on_mouse_move(self, x: int, y: int) -> None:
        self._mouse = (x, y)
        if self._dragging:
            self._drag_to()
            return
        if not self._tracking_leave:
            track = TRACKMOUSEEVENT()
            track.cbSize = ctypes.sizeof(TRACKMOUSEEVENT)
            track.dwFlags = 0x00000002  # TME_LEAVE
            track.hwndTrack = self._hwnd
            _user32.TrackMouseEvent(ctypes.byref(track))
            self._tracking_leave = True
        hit = self._hit_test(x, y)
        if hit == "title":
            hit = None
        if hit != self._hot:
            self._hot = hit
            self._ensure_hover_timer()
            self._invalidate()

    def _on_button_down(self, x: int, y: int) -> None:
        hit = self._hit_test(x, y)
        if hit == "title":
            now = time.monotonic()
            if now - self._last_click < 0.35:
                self._last_click = 0.0
                self._toggle_maximize()
                return
            self._last_click = now
            point = wintypes.POINT()
            _user32.GetCursorPos(ctypes.byref(point))
            box = RECT()
            _user32.GetWindowRect(self._hwnd, ctypes.byref(box))
            self._dragging = True
            self._drag_moved = False
            self._drag_origin = (point.x, point.y, box.left, box.top)
            _user32.SetCapture(self._hwnd)
            return
        if hit in ("btn_close", "btn_max", "btn_min", "action", "copy", "error",
                   "nav_home", "nav_about", "lang_en", "lang_ru"):
            self._pressed = hit
            if hit in ("btn_close", "btn_max", "btn_min", "lang_en", "lang_ru"):
                self._hover[hit] = 1.0
                self._ensure_hover_timer()
            self._invalidate()

    def _on_button_up(self, x: int, y: int) -> None:
        if self._dragging:
            self._dragging = False
            _user32.ReleaseCapture()
            return
        pressed, self._pressed = self._pressed, None
        hit = self._hit_test(x, y)
        if pressed is None:
            return
        self._ensure_hover_timer()
        self._invalidate()
        if pressed != hit:
            return
        if pressed == "lang_en" and self._lang != "en":
            self._lang = "en"
            self.log.info("window language changed", extra={"lang": "en"})
            self._invalidate()
        elif pressed == "lang_ru" and self._lang != "ru":
            self._lang = "ru"
            self.log.info("window language changed", extra={"lang": "ru"})
            self._invalidate()
        if pressed == "btn_close":
            _user32.PostMessageW(self._hwnd, WM_CLOSE, 0, 0)
        elif pressed == "btn_min":
            _user32.ShowWindow(self._hwnd, SW_MINIMIZE)
        elif pressed == "btn_max":
            self._toggle_maximize()
        elif pressed == "action":
            self._toggle_run()
        elif pressed in ("nav_home", "nav_about"):
            view = 0 if pressed == "nav_home" else 1
            if self._nav != view:
                self._nav = view
                self.log.info("view changed", extra={"view": ("home", "about")[view]})
            self._invalidate()
        elif pressed == "error":
            self._toggle_error()
        elif pressed == "copy":
            self._copy_error()

    def _drag_to(self) -> None:
        point = wintypes.POINT()
        _user32.GetCursorPos(ctypes.byref(point))
        origin_x, origin_y, window_x, window_y = self._drag_origin
        delta_x = point.x - origin_x
        delta_y = point.y - origin_y
        if not self._drag_moved and abs(delta_x) + abs(delta_y) > 3:
            self._drag_moved = True
            if self._zoomed():
                # Restore under the cursor instead of leaving it stuck maximised.
                _user32.ShowWindow(self._hwnd, SW_RESTORE)
                box = RECT()
                _user32.GetWindowRect(self._hwnd, ctypes.byref(box))
                window_x = point.x - (box.right - box.left) // 2
                window_y = point.y - self._scale_for(20)
                self._drag_origin = (point.x, point.y, window_x, window_y)
                return
        if not self._drag_moved:
            return
        _user32.SetWindowPos(
            self._hwnd, None, window_x + delta_x, window_y + delta_y, 0, 0,
            SWP_NOSIZE | SWP_NOZORDER | SWP_NOACTIVATE,
        )

    def _toggle_maximize(self) -> None:
        if self._zoomed():
            _user32.ShowWindow(self._hwnd, SW_RESTORE)
        else:
            _user32.ShowWindow(self._hwnd, SW_MAXIMIZE)
        self._apply_round_region()
        self._invalidate()

    def _on_minmax(self, info: MINMAXINFO) -> None:
        minimum_w, minimum_h = self._min_client()
        info.ptMinTrackSize.x = minimum_w
        info.ptMinTrackSize.y = minimum_h
        if not self._hwnd:
            return
        monitor = _user32.MonitorFromWindow(self._hwnd, 2)  # MONITOR_DEFAULTTONEAREST
        if not monitor:
            return
        data = MONITORINFO()
        data.cbSize = ctypes.sizeof(MONITORINFO)
        if not _user32.GetMonitorInfoW(monitor, ctypes.byref(data)):
            return
        work, screen = data.rcWork, data.rcMonitor
        info.ptMaxPosition.x = work.left - screen.left
        info.ptMaxPosition.y = work.top - screen.top
        info.ptMaxSize.x = work.right - work.left
        info.ptMaxSize.y = work.bottom - work.top

    def _on_dpi_changed(self, lparam) -> None:
        box = ctypes.cast(lparam, ctypes.POINTER(RECT)).contents
        self._scale = self._dpi_scale()
        # Brushes and pens are DPI-independent, but fonts are not; drop them so the
        # next paint recreates them at the new scale. The hero icon is reloaded
        # too, so it stays crisp instead of stretching.
        self._fonts.clear()
        if self._icon_hero:
            try:
                _user32.DestroyIcon(self._icon_hero)
            except Exception:  # noqa: BLE001
                pass
            self._icon_hero = 0
        self._load_hero_icon()
        _user32.SetWindowPos(
            self._hwnd, None, box.left, box.top, box.right - box.left, box.bottom - box.top,
            SWP_NOZORDER | SWP_NOACTIVATE | SWP_FRAMECHANGED,
        )
        self._client = (box.right - box.left, box.bottom - box.top)
        self._apply_round_region()
        self._invalidate()

    # ------------------------------------------------------------------ actions
    def _toggle_error(self) -> None:
        """Grow/shrink the window so the full error text is never clipped."""
        if not self._raw_error():
            return
        self._expanded = not self._expanded
        self._error_height = self._measure_error_height() if self._expanded else 0
        width, height = self._client
        target = self._scale_for(self._stack_height() + CARD_INSET * 2) + self._error_height
        new_height = height if target <= height else target
        _user32.SetWindowPos(
            self._hwnd, None, 0, 0, width, new_height,
            SWP_NOMOVE | SWP_NOZORDER | SWP_NOACTIVATE,
        )
        self._client = (width, new_height)
        self._apply_round_region()
        self._invalidate()

    def _measure_error_height(self) -> int:
        """Extra card height the expanded panel needs, in device pixels."""
        text = self._friendly_error(self._raw_error())
        if not text:
            return 0
        hdc = _user32.GetDC(self._hwnd)
        try:
            font = self._font(10.5, FW_NORMAL, "Consolas")
            s = self._scale_for
            width = (
                self._client[0] - s(2 * CARD_INSET) - s(SIDEBAR_WIDTH) - s(CONTENT_GAP)
                - 2 * s(CONTENT_PAD) - s(72)
            )
            box = RECT(0, 0, max(40, width), 0)
            _gdi32.SelectObject(hdc, font)
            _user32.DrawTextW(
                hdc, text, -1, ctypes.byref(box), DT_LEFT | DT_WORDBREAK | DT_NOPREFIX | DT_CALCRECT
            )
            measured = box.bottom - box.top
        finally:
            _user32.ReleaseDC(self._hwnd, hdc)
        extra = measured + self._scale_for(ERROR_FOOTER)
        extra = max(self._scale_for(70), min(extra, self._scale_for(260)))
        return min(extra, max(0, self._work_area_height() - self._scale_for(self._stack_height() + 2 * CARD_INSET + 8)))

    def _work_area_height(self) -> int:
        """Height of the work area of the monitor the window is on."""
        if not self._hwnd:
            return self._scale_for(1000)
        monitor = _user32.MonitorFromWindow(self._hwnd, 2)  # MONITOR_DEFAULTTONEAREST
        if not monitor:
            return self._scale_for(1000)
        data = MONITORINFO()
        data.cbSize = ctypes.sizeof(MONITORINFO)
        if not _user32.GetMonitorInfoW(monitor, ctypes.byref(data)):
            return self._scale_for(1000)
        return data.rcWork.bottom - data.rcWork.top

    def _copy_error(self) -> None:
        text = self._friendly_error(self._raw_error())
        if not text:
            return
        if _copy_to_clipboard(text):
            self.log.info("last error copied to the clipboard", extra={"length": len(text)})
        else:
            self.log.warning("clipboard copy failed")

    def _toggle_run(self) -> None:
        if self._running():
            # Only sets the event; the supervisor thread does the waiting, so the
            # window never blocks here (bug e).
            self._request_stop()
            return
        if self._worker is not None and self._worker.is_alive():
            # The previous run has been asked to stop but its thread has not
            # returned yet. Restarting from WM_APP_STOPPED keeps two supervisors
            # from ever overlapping -- clearing stop_event while the old thread is
            # still between iterations would revive it.
            self._restart_pending = True
        else:
            self._begin_restart()
        self._invalidate()

    def _begin_restart(self) -> None:
        """Swap in a fresh supervisor (so uptime restarts at zero) and run it."""
        self._restart_pending = False
        self.supervisor = PresenceSupervisor(
            self.config, logger=self.log, identity_refresher=self._identity_refresher
        )
        self._worker = threading.Thread(
            target=self._run_supervisor, name="presence-supervisor", daemon=True
        )
        self.stop_event.clear()
        self._worker.start()

    def _request_stop(self) -> None:
        if not self.stop_event.is_set():
            self.log.info("stop requested from window")
            self.stop_event.set()

    # --------------------------------------------------------------------- text
    def _set_text(self, handle: int, text: str) -> None:
        """Write only when the value actually changed, which avoids needless repaints."""
        if self._rendered.get(handle) == text:
            return
        self._rendered[handle] = text
        _user32.SetWindowTextW(handle, text)

    def _sync_title(self) -> None:
        """Keep the OS title equal to the game name -- Discord scans window titles."""
        if self._hwnd:
            self._set_text(self._hwnd, self.title)

    def _refresh_text(self) -> None:
        """1 Hz tick: repaint only when one of the displayed strings changed."""
        if not self._hwnd or self._destroyed:
            return
        self._sync_title()
        snapshot = self._display()
        if snapshot != self._last_display:
            self._last_display = snapshot
            self._invalidate()

    # -------------------------------------------------------------------- window
    def _dpi_scale(self) -> float:
        if self._hwnd:
            try:
                dpi = int(_user32.GetDpiForWindow(self._hwnd))
                if dpi > 0:
                    return dpi / 96.0
            except Exception:  # noqa: BLE001 - pre-1607
                pass
        screen = _user32.GetDC(None)
        if screen:
            try:
                dpi = int(_gdi32.GetDeviceCaps(screen, 88))  # LOGPIXELSX
                if dpi > 0:
                    return dpi / 96.0
            except Exception:  # noqa: BLE001
                pass
            finally:
                _user32.ReleaseDC(None, screen)
        return 1.0

    def _load_chrome_icons(self) -> None:
        """Load the game's own art for the title bar, the taskbar and the class.

        Three separate handles at the sizes the shell actually shows: 32px for
        the title bar, 48px for the taskbar and the window class. One
        ``LR_DEFAULTSIZE`` handle stretched everywhere is what made the old
        taskbar icon a blurry mess. A missing or unreadable file leaves all
        three at zero and the painted tiles fall back to the initial.
        """
        if not self.icon_path or not self.icon_path.exists():
            return
        path = str(self.icon_path)
        self._icon_small = _user32.LoadImageW(None, path, IMAGE_ICON, 32, 32, LR_LOADFROMFILE) or 0
        self._icon_big = _user32.LoadImageW(None, path, IMAGE_ICON, 48, 48, LR_LOADFROMFILE) or 0
        if not self._icon_small and not self._icon_big:
            self.log.warning(
                "icon could not be loaded; the window keeps the drawn placeholder",
                extra={"path": path},
            )
            return
        self.log.info("window icon applied", extra={"path": path})

    def _load_hero_icon(self) -> None:
        """The session-view icon at the painted hero size."""
        if not self.icon_path or not self.icon_path.exists():
            return
        size = self._scale_for(HERO_ICON)
        self._icon_hero = _user32.LoadImageW(
            None, str(self.icon_path), IMAGE_ICON, size, size, LR_LOADFROMFILE
        ) or 0

    def _create_window(self) -> None:
        self._instance = _kernel32.GetModuleHandleW(None)
        self._load_chrome_icons()
        wndclass = WNDCLASSW()
        wndclass.style = CS_HREDRAW | CS_VREDRAW
        wndclass.lpfnWndProc = self._wndproc_ref
        wndclass.hInstance = self._instance
        wndclass.lpszClassName = self._class_name
        wndclass.hIcon = self._icon_big
        wndclass.hCursor = _user32.LoadCursorW(None, ctypes.c_wchar_p(IDC_ARROW))
        wndclass.hbrBackground = None  # every pixel is painted in WM_PAINT

        if not _user32.RegisterClassW(ctypes.byref(wndclass)):
            error = ctypes.get_last_error()
            if error != 1410:  # class already exists
                raise WindowError(f"RegisterClassW failed ({error})")

        # Discord's process detector reads the window FLAGS, not the pixels.
        # The two requirements proven live (2026-09-25 A/B against build 619060):
        #   * WS_CAPTION must be present  (the old window had it; popup-without-caption
        #     is what the detector ignores),
        #   * WS_EX_LAYERED must be ABSENT (layered = overlay-class windows; the old
        #     detected window was never layered, every non-detected one was).
        # WM_NCCALCSIZE still gives the whole rect to the client, so the card remains
        # the only visible chrome — this is the same trick browsers use to keep a
        # caption flag while drawing their own title bar.
        style = WS_CAPTION | WS_THICKFRAME | WS_MINIMIZEBOX | WS_SYSMENU | WS_VISIBLE | WS_CLIPCHILDREN | WS_CLIPSIBLINGS
        self._hwnd = _user32.CreateWindowExW(
            WS_EX_APPWINDOW, self._class_name, self.title, style,
            CW_USEDEFAULT, CW_USEDEFAULT,
            self._scale_for(DEFAULT_WIDTH), self._scale_for(DEFAULT_HEIGHT),
            None, None, self._instance, None,
        )
        if not self._hwnd:
            raise WindowError(f"CreateWindowExW failed ({ctypes.get_last_error()})")

        self._scale = self._dpi_scale()
        self._client = (self._scale_for(DEFAULT_WIDTH), self._scale_for(DEFAULT_HEIGHT))
        self._load_hero_icon()

        if self._icon_small:
            _user32.SendMessageW(self._hwnd, WM_SETICON, ICON_SMALL, self._icon_small)
        if self._icon_big:
            _user32.SendMessageW(self._hwnd, WM_SETICON, ICON_BIG, self._icon_big)

        self._apply_backdrop()
        self._apply_round_region()
        # Force the frame recalculation now that the class and procedure are in
        # place, so the frameless client area is settled before the window shows.
        _user32.SetWindowPos(
            self._hwnd, None, 0, 0, 0, 0,
            SWP_NOMOVE | SWP_NOSIZE | SWP_NOZORDER | SWP_NOACTIVATE | SWP_FRAMECHANGED,
        )
        self._sync_title()
        self._last_display = self._display()
        # The only timer: re-read the supervisor stats once a second and repaint
        # only when a displayed string actually changed. The window sits still.
        _user32.SetTimer(self._hwnd, TIMER_ID, 1000, None)
        self.log.info(
            "presence window created",
            extra={
                "title": self.title,
                "hwnd": int(self._hwnd),
                "dpi_scale": round(self._scale, 3),
                "dwm_blur": self._dwm_blur,
            },
        )

    def _start_worker(self) -> None:
        """Initial start: the window is not up yet, so no restart can be pending."""
        self._worker = threading.Thread(
            target=self._run_supervisor, name="presence-supervisor", daemon=True
        )
        self._worker.start()

    def _run_supervisor(self) -> None:
        try:
            self.exit_code = self.supervisor.run(self.stop_event)
        except Exception:  # noqa: BLE001 - the window must survive a worker crash
            self.exit_code = 2
            self.log.exception("RPC worker failed")
        finally:
            if self._hwnd and not self._destroyed:
                _user32.PostMessageW(self._hwnd, WM_APP_STOPPED, 0, 0)

    def run(self) -> int:
        """Start the supervisor, show the window, block until it closes."""
        if not hasattr(ctypes, "WinDLL"):
            raise WindowError("window mode is Windows-only")

        _ensure_dpi_awareness()
        self._wndproc_ref = WNDPROC(self._on_message)
        self._create_window()
        self._start_worker()

        message = MSG()
        try:
            while True:
                result = _user32.GetMessageW(ctypes.byref(message), None, 0, 0)
                if result == 0:
                    break
                if result == -1:
                    raise WindowError("GetMessageW failed")
                _user32.TranslateMessage(ctypes.byref(message))
                _user32.DispatchMessageW(ctypes.byref(message))
        finally:
            self.stop_event.set()
            if self._worker is not None:
                self._worker.join(timeout=20.0)
            self._release_resources()
        return self.exit_code


def _copy_to_clipboard(text: str) -> bool:
    """Put ``text`` on the Windows clipboard as CF_UNICODETEXT.

    ctypes rather than ``tkinter``: the bundled interpreter has no tkinter, and the
    project takes no dependencies. The clipboard is opened at most a few times per
    session, so a short retry loop is enough for the (rare) case where another
    process holds it.
    """
    if not hasattr(ctypes, "WinDLL"):
        return False
    if not _user32.OpenClipboard(None):
        time.sleep(0.05)
        if not _user32.OpenClipboard(None):
            return False
    handle = None
    try:
        _user32.EmptyClipboard()
        data = (text + "\0").encode("utf-16-le")
        handle = _kernel32.GlobalAlloc(GMEM_MOVEABLE, len(data))
        if not handle:
            return False
        pointer = _kernel32.GlobalLock(handle)
        if not pointer:
            return False
        ctypes.memmove(pointer, data, len(data))
        _kernel32.GlobalUnlock(handle)
        if not _user32.SetClipboardData(CF_UNICODETEXT, handle):
            return False
        handle = None  # ownership passed to the clipboard
        return True
    except Exception:  # noqa: BLE001 - clipboard failures are never fatal
        return False
    finally:
        if handle:
            _kernel32.GlobalFree(handle)
        _user32.CloseClipboard()


def run_with_window(config, logger=None, identity_refresher=None, icon_path=None) -> int:
    return run_with_window_supervised(config, logger=logger,
                                      identity_refresher=identity_refresher,
                                      icon_path=icon_path)[0]


def run_with_window_supervised(config, logger=None, identity_refresher=None,
                               icon_path=None) -> tuple[int, bool]:
    """Run the windowed presence. Returns the exit code and whether it cleared.

    The second value lets the caller skip its own clear: the supervisor already
    clears on the way out, and clearing twice costs a second IPC handshake, which
    Discord throttles.
    """
    window = PresenceWindow(
        config,
        logger=logger,
        identity_refresher=identity_refresher,
        icon_path=icon_path,
    )
    code = window.run()
    return code, bool(getattr(window.supervisor.stats, "cleared", False))
