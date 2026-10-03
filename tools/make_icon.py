"""Generate the application icon: assets/worthlesstask.ico.

dj asked for a real icon so the Task Manager / taskbar shows the app instead of a
blank placeholder. The file is embedded into the executable at build time
(PyInstaller ``--icon``, csc ``/win32icon``), which is what the shell reads.

No image library is available in the packaged interpreter, so the rasteriser and
both container writers (PNG for 256px, BMP/DIB for the smaller sizes) live here --
pure stdlib (zlib + struct).
"""

from __future__ import annotations

import math
import struct
import zlib
from pathlib import Path

SIZES = (256, 128, 64, 48, 32, 24, 16)
OUT = Path(__file__).resolve().parents[1] / "assets" / "worthlesstask.ico"

# Matte warm black tile, orange mark -- the same identity as the dashboard favicon.
TILE_TOP = (28, 21, 14)
TILE_BOTTOM = (10, 8, 6)
EDGE = (255, 138, 43)
EDGE_DIM = (168, 70, 12)
MARK = (255, 163, 77)
MARK_SOFT = (233, 106, 22)
SS = 3  # supersampling factor


def _lerp(a: int, b: int, t: float) -> int:
    return int(round(a + (b - a) * t))


def _rounded_box_alpha(x: float, y: float, size: float, radius: float) -> float:
    """Coverage of a rounded square, sampled with a 3x3 grid inside one pixel."""
    hits = 0
    for sy in range(SS):
        for sx in range(SS):
            px = x + (sx + 0.5) / SS
            py = y + (sy + 0.5) / SS
            dx = max(radius - px, px - (size - radius), 0.0)
            dy = max(radius - py, py - (size - radius), 0.0)
            if dx * dx + dy * dy <= radius * radius:
                hits += 1
    return hits / (SS * SS)


def _ring_alpha(x: float, y: float, cx: float, cy: float, radius: float, width: float) -> float:
    """Coverage of an anti-aliased ring (used for the diamond)."""
    hits = 0
    for sy in range(SS):
        for sx in range(SS):
            px = x + (sx + 0.5) / SS
            py = y + (sy + 0.5) / SS
            # rotate 45 degrees: the diamond is a circle in this space
            u = (px - cx + py - cy) / math.sqrt(2.0)
            v = (py - cy - (px - cx)) / math.sqrt(2.0)
            distance = math.hypot(u, v)
            if abs(distance - radius) <= width / 2.0:
                hits += 1
    return hits / (SS * SS)


def _dot_alpha(x: float, y: float, cx: float, cy: float, radius: float) -> float:
    hits = 0
    for sy in range(SS):
        for sx in range(SS):
            px = x + (sx + 0.5) / SS
            py = y + (sy + 0.5) / SS
            if math.hypot(px - cx, py - cy) <= radius:
                hits += 1
    return hits / (SS * SS)


def render(size: int) -> bytes:
    """RGBA rows for one icon size, top-down."""
    radius = size * 0.22
    cx = cy = size / 2.0
    ring_radius = size * 0.27
    ring_width = max(1.6, size * 0.052)
    dot_radius = max(1.0, size * 0.058)
    rows = []
    for y in range(size):
        row = bytearray()
        for x in range(size):
            box = _rounded_box_alpha(x, y, size, radius)
            if box <= 0.0:
                row += bytes((0, 0, 0, 0))
                continue
            t = y / max(1, size - 1)
            base = tuple(_lerp(TILE_TOP[i], TILE_BOTTOM[i], t) for i in range(3))
            # A thin bright inner edge (a few pixels, not a wide glow -- at 16-32px a
            # wide border turns to mush), never bleeding past the rounded shape.
            edge_w = max(1.0, size * 0.022)
            edge_t = min(1.0, min(x, y, size - 1 - x, size - 1 - y) / edge_w)
            if edge_t < 1.0:
                strength = 0.8 * (1.0 - edge_t) * (1.0 - 0.4 * t) * min(1.0, box * 1.8)
                base = tuple(
                    _lerp(base[i], _lerp(EDGE[i], EDGE_DIM[i], t), strength) for i in range(3)
                )
            ring = _ring_alpha(x, y, cx, cy, ring_radius, ring_width)
            dot = _dot_alpha(x, y, cx, cy, dot_radius)
            mark = max(ring, dot)
            if mark > 0.0:
                mark_color = MARK if dot >= ring else MARK_SOFT
                base = tuple(_lerp(base[i], mark_color[i], mark) for i in range(3))
            row += bytes((base[0], base[1], base[2], int(round(255 * box))))
        rows.append(bytes(row))
    return b"".join(rows)


def png(size: int, rgba: bytes) -> bytes:
    """Minimal RGBA PNG writer."""
    raw = bytearray()
    stride = size * 4
    for y in range(size):
        raw.append(0)  # filter: none
        raw += rgba[y * stride:(y + 1) * stride]

    def chunk(tag: bytes, data: bytes) -> bytes:
        return (
            struct.pack(">I", len(data))
            + tag
            + data
            + struct.pack(">I", zlib.crc32(tag + data) & 0xFFFFFFFF)
        )

    header = struct.pack(">IIBBBBB", size, size, 8, 6, 0, 0, 0)
    return (
        b"\x89PNG\r\n\x1a\n"
        + chunk(b"IHDR", header)
        + chunk(b"IDAT", zlib.compress(bytes(raw), 9))
        + chunk(b"IEND", b"")
    )


def dib(size: int, rgba: bytes) -> bytes:
    """32-bit BMP/DIB entry (bottom-up BGRA + AND mask) for the smaller sizes."""
    header = struct.pack(
        "<IiiHHIIiiII", 40, size, size * 2, 1, 32, 0, size * size * 4, 0, 0, 0, 0
    )
    pixels = bytearray()
    stride = size * 4
    for y in range(size - 1, -1, -1):  # bottom-up
        line = rgba[y * stride:(y + 1) * stride]
        for x in range(size):
            r, g, b, a = line[x * 4:x * 4 + 4]
            pixels += bytes((b, g, r, a))
    mask_stride = ((size + 31) // 32) * 4
    mask = bytearray()
    for y in range(size - 1, -1, -1):
        line = rgba[y * stride:(y + 1) * stride]
        bits = bytearray(mask_stride)
        for x in range(size):
            if line[x * 4 + 3] == 0:
                bits[x // 8] |= 0x80 >> (x % 8)
        mask += bits
    return header + bytes(pixels) + bytes(mask)


def build() -> Path:
    images = []
    for size in SIZES:
        rgba = render(size)
        images.append((size, png(size, rgba) if size >= 256 else dib(size, rgba)))
    header = struct.pack("<HHH", 0, 1, len(images))
    offset = 6 + 16 * len(images)
    entries = bytearray()
    blobs = bytearray()
    for size, data in images:
        entries += struct.pack(
            "<BBBBHHII",
            0 if size >= 256 else size,
            0 if size >= 256 else size,
            0, 0, 1, 32, len(data), offset,
        )
        blobs += data
        offset += len(data)
    OUT.parent.mkdir(parents=True, exist_ok=True)
    OUT.write_bytes(bytes(header) + bytes(entries) + bytes(blobs))
    return OUT


if __name__ == "__main__":
    path = build()
    print(f"wrote {path} ({path.stat().st_size} bytes, sizes {SIZES})")
