"""OCR a PNG with Windows.Media.Ocr via pywinrt, avoiding every path-based WinRT API.

The agent environment corrupts path strings handed to WinRT file APIs, so the PNG is
read with plain Python and pushed through an in-memory stream instead.
"""
import asyncio
import sys

from winrt.windows.graphics.imaging import BitmapDecoder
from winrt.windows.media.ocr import OcrEngine
from winrt.windows.storage.streams import DataWriter, InMemoryRandomAccessStream
from winrt.windows.globalization import Language


async def recognize(path: str) -> str:
    with open(path, "rb") as fh:
        data = fh.read()

    stream = InMemoryRandomAccessStream()
    writer = DataWriter(stream.get_output_stream_at(0))
    writer.write_bytes(data)
    await writer.store_async()
    await writer.flush_async()
    stream.seek(0)

    decoder = await BitmapDecoder.create_async(stream)
    bitmap = await decoder.get_software_bitmap_async()

    engine = OcrEngine.try_create_from_user_profile_languages() or OcrEngine.try_create_from_language(
        Language("en-US"))
    if engine is None:
        return "OCR_ENGINE_UNAVAILABLE"
    result = await engine.recognize_async(bitmap)
    return "\n".join(line.text for line in result.lines)


if __name__ == "__main__":
    print(asyncio.run(recognize(sys.argv[1])))
