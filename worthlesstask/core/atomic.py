"""Write a file so no reader can ever see a partial one.

Every file this program owns — the library, the config, the catalogue cache, the
session record — is read by another process while it may be being written. A plain
``write_text`` leaves a window where the file is truncated or half-written; a crash
in that window turns a working file into a corrupt one.

The pattern is always the same: write to a sibling temp file, flush it, fsync it so
the data is on disk and not just in a buffer, then ``os.replace`` it into place.
``os.replace`` is atomic on POSIX and Windows, so a reader sees either the old
contents or the new ones, never a mix.
"""

from __future__ import annotations

import json
import os
import tempfile
from pathlib import Path


def write_atomic(path, text: str, encoding: str = "utf-8") -> Path:
    """Replace ``path`` with ``text`` atomically, keeping nothing behind on failure."""
    target = Path(path)
    target.parent.mkdir(parents=True, exist_ok=True)

    # A fixed suffix keeps any stray temp file recognisable and matches the
    # recovery names the library already looks for.
    fd, temp_name = tempfile.mkstemp(dir=str(target.parent), prefix=target.name, suffix=".writing")
    try:
        with os.fdopen(fd, "w", encoding=encoding) as handle:
            handle.write(text)
            handle.flush()
            os.fsync(handle.fileno())
        os.replace(temp_name, target)
    except BaseException:
        try:
            os.unlink(temp_name)
        except OSError:
            pass
        raise
    return target


def write_bytes_atomic(path, data: bytes) -> Path:
    """Replace ``path`` with ``data`` atomically. Same guarantees as :func:`write_atomic`."""
    target = Path(path)
    target.parent.mkdir(parents=True, exist_ok=True)
    fd, temp_name = tempfile.mkstemp(dir=str(target.parent), prefix=target.name, suffix=".writing")
    try:
        with os.fdopen(fd, "wb") as handle:
            handle.write(data)
            handle.flush()
            os.fsync(handle.fileno())
        os.replace(temp_name, target)
    except BaseException:
        try:
            os.unlink(temp_name)
        except OSError:
            pass
        raise
    return target


def write_json_atomic(path, payload, encoding: str = "utf-8", **json_kwargs) -> Path:
    """Atomically write ``payload`` as JSON."""
    kwargs = {"ensure_ascii": False, "indent": 2}
    kwargs.update(json_kwargs)
    return write_atomic(path, json.dumps(payload, **kwargs), encoding=encoding)
