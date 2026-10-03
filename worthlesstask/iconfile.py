"""PNG to ICO conversion in pure stdlib.

Discord's catalogue publishes game art as PNG, but ``LoadImageW`` -- the call
that puts an icon in the title bar and the taskbar -- only reads ICO files with
BMP entries. This module decodes a PNG (no interlace, 8-bit depth, greyscale,
RGB or RGBA) and wraps the pixels into a classic multi-size ICO.

The decoder is deliberately small: it exists for one file shape, the CDN's
256x256 RGBA icons, and anything it cannot parse is reported as an error so the
caller can fall back to the drawn placeholder.
"""

from __future__ import annotations

import struct
import zlib

PNG_SIGNATURE = b"\x89PNG\r\n\x1a\n"

_FILTER_NONE, _FILTER_SUB, _FILTER_UP, _FILTER_AVERAGE, _FILTER_PAETH = 0, 1, 2, 3, 4


class IconError(ValueError):
    """The PNG cannot be turned into an ICO."""


def is_png(data: bytes) -> bool:
    return isinstance(data, (bytes, bytearray)) and bytes(data[:8]) == PNG_SIGNATURE


def _decode_png(data: bytes) -> tuple[int, int, bytes]:
    """Return ``(width, height, rgba)`` for an 8-bit non-interlaced PNG."""
    if not is_png(data):
        raise IconError("not a PNG file")
    pos, width, height, depth, color, interlace = 8, 0, 0, 0, 0, 0
    idat = bytearray()
    palette: list[tuple[int, int, int]] = []
    trns = bytes()
    while pos + 8 <= len(data):
        length, kind = struct.unpack(">I4s", data[pos:pos + 8])
        pos += 8
        chunk = data[pos:pos + length]
        pos += length + 4  # CRC
        if kind == b"IHDR":
            width, height, depth, color = struct.unpack(">IIBB", chunk[:10])
            interlace = chunk[12]
        elif kind == b"PLTE":
            palette = [tuple(chunk[i:i + 3]) for i in range(0, len(chunk), 3)]
        elif kind == b"tRNS":
            trns = chunk
        elif kind == b"IDAT":
            idat.extend(chunk)
        elif kind == b"IEND":
            break
    if interlace:
        raise IconError("interlaced PNG is not supported")
    if depth != 8:
        raise IconError(f"unsupported bit depth {depth}")
    channels = {0: 1, 2: 3, 3: 1, 4: 2, 6: 4}.get(color)
    if channels is None:
        raise IconError(f"unsupported colour type {color}")
    if width <= 0 or height <= 0 or width > 4096 or height > 4096:
        raise IconError("unsupported image size")
    raw = zlib.decompress(bytes(idat))
    stride = width * channels
    expected = (stride + 1) * height
    if len(raw) < expected:
        raise IconError("truncated PNG pixel data")
    rows = bytearray(height * stride)
    prev = bytearray(stride)
    for y in range(height):
        base = y * (stride + 1)
        filt = raw[base]
        line = bytearray(raw[base + 1:base + 1 + stride])
        if filt == _FILTER_SUB:
            for i in range(channels, stride):
                line[i] = (line[i] + line[i - channels]) & 0xFF
        elif filt == _FILTER_UP:
            for i in range(stride):
                line[i] = (line[i] + prev[i]) & 0xFF
        elif filt == _FILTER_AVERAGE:
            for i in range(stride):
                left = line[i - channels] if i >= channels else 0
                line[i] = (line[i] + ((left + prev[i]) >> 1)) & 0xFF
        elif filt == _FILTER_PAETH:
            for i in range(stride):
                left = line[i - channels] if i >= channels else 0
                up = prev[i]
                upleft = prev[i - channels] if i >= channels else 0
                p = left + up - upleft
                pa, pb, pc = abs(p - left), abs(p - up), abs(p - upleft)
                pred = left if pa <= pb and pa <= pc else (up if pb <= pc else upleft)
                line[i] = (line[i] + pred) & 0xFF
        elif filt != _FILTER_NONE:
            raise IconError(f"unknown filter {filt}")
        rows[y * stride:(y + 1) * stride] = line
        prev = line
    rgba = bytearray(width * height * 4)
    for y in range(height):
        for x in range(width):
            src = (y * width + x) * channels
            dst = (y * width + x) * 4
            if color == 6:
                rgba[dst:dst + 4] = rows[src:src + 4]
            elif color == 2:
                rgba[dst:dst + 3] = rows[src:src + 3]
                rgba[dst + 3] = 255
            elif color == 0:
                grey = rows[src]
                rgba[dst] = rgba[dst + 1] = rgba[dst + 2] = grey
                rgba[dst + 3] = 255
            elif color == 3:
                index = rows[src]
                if index >= len(palette):
                    raise IconError("palette index out of range")
                rgba[dst:dst + 3] = bytes(palette[index])
                rgba[dst + 3] = trns[index] if index < len(trns) else 255
    return width, height, bytes(rgba)


def _scale_box(rgba: bytes, width: int, height: int, size: int) -> bytes:
    """Area-average resample to ``size``x``size``.

    The old nearest-neighbour downscale turned diagonal art into staircases at
    16-32px, which is exactly what the taskbar shows. Averaging the covered
    source box keeps edges straight.
    """
    out = bytearray(size * size * 4)
    x_ratio = width / size
    y_ratio = height / size
    for y in range(size):
        y0 = int(y * y_ratio)
        y1 = max(y0 + 1, int((y + 1) * y_ratio))
        for x in range(size):
            x0 = int(x * x_ratio)
            x1 = max(x0 + 1, int((x + 1) * x_ratio))
            total = [0, 0, 0, 0]
            count = 0
            for src_y in range(y0, min(y1, height)):
                for src_x in range(x0, min(x1, width)):
                    src = (src_y * width + src_x) * 4
                    for channel in range(4):
                        total[channel] += rgba[src + channel]
                    count += 1
            dst = (y * size + x) * 4
            for channel in range(4):
                out[dst + channel] = total[channel] // max(1, count)
    return bytes(out)


def _scale_nearest(rgba: bytes, width: int, height: int, size: int) -> bytes:
    return _scale_box(rgba, width, height, size)


def _ico_entry(size: int, rgba: bytes) -> bytes:
    """One BMP-formatted icon image: 32-bit XOR rows bottom-up plus an empty AND mask."""
    header = struct.pack(
        "<IiiHHIIiiII", 40, size, size * 2, 1, 32, 0, size * size * 4, 0, 0, 0, 0
    )
    xor = bytearray(size * size * 4)
    for y in range(size):
        src_row = y * size * 4
        dst_row = (size - 1 - y) * size * 4
        for x in range(size):
            src = src_row + x * 4
            dst = dst_row + x * 4
            xor[dst] = rgba[src + 2]      # B
            xor[dst + 1] = rgba[src + 1]  # G
            xor[dst + 2] = rgba[src]      # R
            xor[dst + 3] = rgba[src + 3]  # A
    mask_row = ((size + 31) // 32) * 4
    mask = bytes(mask_row * size)
    return header + bytes(xor) + mask


def png_to_ico(data: bytes, sizes: tuple[int, ...] = (16, 20, 24, 28, 32, 40, 48, 64)) -> bytes:
    """Convert a PNG to a multi-size ICO the classic ``LoadImageW`` can read."""
    width, height, rgba = _decode_png(data)
    entries: list[tuple[int, bytes]] = []
    for size in sizes:
        scaled = rgba if size == width == height else _scale_nearest(rgba, width, height, size)
        entries.append((size, _ico_entry(size, scaled)))
    out = bytearray(struct.pack("<HHH", 0, 1, len(entries)))
    offset = 6 + 16 * len(entries)
    for size, blob in entries:
        byte_size = size if size < 256 else 0
        out.extend(struct.pack("<BBBBHHII", byte_size, byte_size, 0, 0, 1, 32, len(blob), offset))
        offset += len(blob)
    for _, blob in entries:
        out.extend(blob)
    return bytes(out)
