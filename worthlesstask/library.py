"""Thread-safe local game library with atomic writes and per-game icons."""
from __future__ import annotations

import hashlib
import json
import os
import re
import shutil
import threading
import time
import urllib.request
from dataclasses import asdict, dataclass, field
from functools import wraps
from pathlib import Path
from typing import Any

from .core.atomic import write_atomic, write_bytes_atomic
from .core.errors import worthlesstaskError
from .core.filelock import file_lock
from .core.logging import get_logger
from .iconfile import is_png, png_to_ico

DEFAULT_LIBRARY_PATH = Path("library.json")
DEFAULT_ICONS_DIR = Path("icons")
MAX_ICON_BYTES = 2 * 1024 * 1024
ICO_MAGIC = b"\x00\x00\x01\x00"

class LibraryError(worthlesstaskError):
    pass

def make_slug(name):
    return re.sub(r"[^a-z0-9]+", "-", str(name).casefold()).strip("-")[:55] or "game"

def is_ico(data):
    return data[:4] == ICO_MAGIC


#: The CDN answers browsers, not the stock urllib identity (403), and the
#: library holds both full ``.../hash.png`` URLs and older extensionless ones
#: (404). Every attempt carries a browser identity.
_CDN_UA = "Mozilla/5.0 (Windows NT 10.0; Win64; x64) worthlesstask/3.1"


def _fetch_catalogue_art(url: str) -> bytes | None:
    """Download catalogue art, or None when it is missing or not a PNG.

    Tries the stored URL first, then the same URL with ``.png`` for entries
    saved before the resolver started keeping the extension. The stock
    ``Python-urllib`` identity is rejected by the CDN, so a browser one is
    sent; stdlib decodes PNG only, anything else falls back to the letter.
    """
    base = (url or "").strip()
    if not base:
        return None
    candidates = [base] if base.lower().endswith(".png") else [base, base + ".png"]
    for candidate in candidates:
        try:
            request = urllib.request.Request(candidate, headers={"User-Agent": _CDN_UA})
            with urllib.request.urlopen(request, timeout=8) as response:
                data = response.read(MAX_ICON_BYTES + 1)
        except Exception:  # noqa: BLE001 - try the next spelling
            continue
        if data and len(data) <= MAX_ICON_BYTES and is_png(data):
            return data
    return None

def _entry_dict(items):
    """Serialise an Entry without the bookkeeping field."""
    return {key: value for key, value in items if key != "_touched"}


#: Argument names supplied to the ``Entry(...)`` call currently in flight, keyed by
#: the id of the instance being built. Set by ``Entry.__init__``, read and removed by
#: ``Entry.__post_init__``, so nothing here outlives one construction.
_EXPLICIT_FIELDS: dict[int, tuple[str, ...]] = {}


def locked(method):
    @wraps(method)
    def call(self, *args, **kwargs):
        with self._lock:
            return method(self, *args, **kwargs)
    return call

@dataclass
class Entry:
    slug: str
    game_name: str
    application_id: str = ""
    executable: str | None = None
    executable_source: str = "catalogue"
    catalog_icon_url: str | None = None
    icon: str | None = None
    details: str | None = None
    state: str | None = None
    minutes: int | None = None
    activity_type: str = "playing"
    added_at: float = field(default_factory=time.time)
    icon_version: str = ""
    worker_ready: bool = False
    worker_error: str | None = None
    worker_path: str | None = None
    executable_rel: str | None = None
    bypass_mode: str | None = None
    epic_app_id: str | None = None
    steam_app_id: str | None = None
    carrier_app_id: str | None = None

    #: Fields changed in this process. Saving merges only these over what is already
    #: on disk, so two processes editing different fields of one game do not clobber
    #: each other. See Library._merge_persisted.
    _touched: set[str] = field(default_factory=set, repr=False, compare=False)

    def _mark(self, name: str) -> None:
        if name == "_touched":
            return
        try:
            self._touched.add(name)
        except AttributeError:
            # The generated __init__ assigns before this field exists; __post_init__
            # marks the constructor's fields anyway.
            pass

    def __setattr__(self, name, value):
        object.__setattr__(self, name, value)
        self._mark(name)

    def __post_init__(self):
        # Only values actually passed to the constructor count as changed. Marking
        # every field would make a default "outrank" a value another process has
        # already written — the exact data loss this tracking prevents.
        explicit = _EXPLICIT_FIELDS.pop(id(self), None)
        if explicit is None:
            # Not built by Entry.__new__ (dataclasses.replace, unpickling): treat
            # every field as changed rather than silently dropping any.
            self._touched.update(n for n in self.__dataclass_fields__ if n != "_touched")
            return
        self._touched.update(n for n in explicit if n != "_touched")

    def __new__(cls, *args, **kwargs):
        # Runs before __init__, so __post_init__ can tell which arguments were given.
        # An explicit value can equal its default, so presence cannot be inferred
        # from the resulting attribute.
        code = cls.__init__.__code__
        names = code.co_varnames[1:code.co_argcount]
        supplied = set(names[:len(args)]) | set(kwargs)
        instance = super().__new__(cls)
        _EXPLICIT_FIELDS[id(instance)] = tuple(supplied)
        return instance

    @property
    def can_start(self):
        return bool(self.executable)

    @property
    def availability_reason(self):
        """A stable code the dashboard renders in the user's language.

        The page owns the wording (see ``web/i18n.py`` and the page's I18N packs);
        the library only decides *why* an entry may not map to a catalogue process.
        """
        if not self.executable:
            return "reason.no_exe"
        if self.executable_source == "manual":
            return "reason.manual"
        if self.executable_source == "derived":
            return "reason.derived"
        return None

    @property
    def duration_minutes(self):
        return self.minutes if isinstance(self.minutes, int) and self.minutes > 0 else 15

    def to_dict(self):
        # Bookkeeping never leaves the process: it is not part of the API contract.
        data = asdict(self, dict_factory=_entry_dict)
        data.update(duration_minutes=self.duration_minutes,
                    icon_url=f"/api/icon/{self.slug}" if self.icon else self.catalog_icon_url,
                    custom_icon=bool(self.icon), can_start=self.can_start,
                    availability_reason=self.availability_reason)
        return data

    @classmethod
    def from_dict(cls, data):
        return cls(**{k: v for k, v in data.items() if k in cls.__dataclass_fields__})

    def copy(self) -> "Entry":
        """A detached copy that remembers which fields were left alone."""
        clone = Entry.from_dict({k: v for k, v in asdict(self).items()})
        clone._touched = set(self._touched)
        return clone

class Library:
    def __init__(self, path=DEFAULT_LIBRARY_PATH, icons_dir=DEFAULT_ICONS_DIR, logger=None):
        self.path = Path(path).resolve()
        self.icons_dir = Path(icons_dir).resolve()
        self.log = logger or get_logger()
        self._lock = threading.RLock()
        self._entries, self._queue = {}, []
        self.load()

    def _recovery_order(self):
        """Files to try when reading the library, best first.

        ``save`` writes a temp file and renames it into place, and keeps the previous
        version as ``.bak``. If the main file is ever damaged — a kill during the
        rename is enough — those copies are what keeps the library from being lost.
        """
        return (self.path,
                self.path.with_name(self.path.name + ".writing"),
                self.path.with_name(self.path.name + ".bak"))

    @locked
    def load(self):
        with file_lock(self.path, exclusive=False):
            return self._load_locked()

    def _load_locked(self):
        if not self.path.exists():
            self._entries, self._queue = {}, []
            return
        payload = None
        recovered_from = None
        for candidate in self._recovery_order():
            try:
                payload = json.loads(candidate.read_text(encoding="utf-8"))
            except (OSError, ValueError):
                continue
            recovered_from = candidate
            break
        if payload is None:
            raise LibraryError(
                f"Не удалось прочитать библиотеку: {self.path} и резервные копии повреждены")
        if recovered_from != self.path:
            # A damaged main file must not stop the app: continue from the copy.
            self.log.warning("library recovered from a backup",
                             extra={"used": str(recovered_from), "damaged": str(self.path)})
        items = payload.get("games") if isinstance(payload, dict) else payload
        if not isinstance(items, list):
            raise LibraryError("Ожидался список игр")
        entries = {}
        for item in items:
            if not isinstance(item, dict) or not item.get("game_name"):
                continue
            item = dict(item)
            item["slug"] = item.get("slug") or make_slug(item["game_name"])
            if not re.fullmatch(r"[a-z0-9][a-z0-9-]{0,63}", str(item["slug"])):
                raise LibraryError("Недопустимый идентификатор в библиотеке")
            entry = Entry.from_dict(item)
            entries[entry.slug] = entry
        self._entries = entries
        queue = payload.get("queue", []) if isinstance(payload, dict) else []
        self._queue = list(dict.fromkeys(s for s in queue if isinstance(s, str) and s in entries))

    @locked
    def save(self):
        # The lock spans the whole read-modify-write of the file on disk, so a worker
        # refreshing an id and the dashboard saving a queue change cannot interleave.
        with file_lock(self.path):
            self._save_locked()

    def _merge_persisted(self) -> None:
        """Fold in changes another process has written since our last read.

        Two processes can hold the same library: the dashboard edits a queue or an
        icon, a worker refreshes an application id. Writing our whole in-memory state
        would silently drop whatever the other one changed, because each side is
        holding a snapshot that predates the other's edit.

        Only fields changed *here* are pushed over what is on disk, so disjoint edits
        to the same game both survive. Anything we never touched comes from disk,
        which is the newer authority.
        """
        if not self.path.exists():
            return
        try:
            payload = json.loads(self.path.read_text(encoding="utf-8"))
        except (OSError, ValueError):
            return  # Unreadable: keep our version rather than losing it.
        if not isinstance(payload, dict):
            return

        disk: dict[str, dict] = {}
        for item in payload.get("games") or []:
            if isinstance(item, dict) and item.get("slug"):
                disk[str(item["slug"])] = item

        for slug, entry in list(self._entries.items()):
            if not entry._touched:
                continue
            saved = disk.get(slug)
            if saved is None:
                continue
            for name in entry.__dataclass_fields__:
                if name == "_touched" or name in entry._touched:
                    continue
                if name in saved:
                    setattr(entry, name, saved[name])

    def _save_locked(self):
        self._merge_persisted()
        payload = {"games": [asdict(e, dict_factory=_entry_dict) for e in self._entries.values()],
                   "queue": self._queue}
        temp = self.path.with_name(self.path.name + ".writing")
        backup = self.path.with_name(self.path.name + ".bak")
        try:
            self.path.parent.mkdir(parents=True, exist_ok=True)
            write_atomic(temp, json.dumps(payload, ensure_ascii=False, indent=2))
            if self.path.exists():
                # Keep the last known-good file so a damaged write cannot lose the library.
                shutil.copy2(self.path, backup)
            os.replace(temp, self.path)
        except OSError as exc:
            raise LibraryError(f"Не удалось сохранить библиотеку: {exc}") from exc
        finally:
            temp.unlink(missing_ok=True)

    @locked
    def entries(self):
        return sorted(self._entries.values(), key=lambda e: e.added_at)

    @locked
    def get(self, slug):
        return self._entries.get(slug)

    @locked
    def unique_slug(self, name):
        base = make_slug(name)
        slug, i = base, 2
        while slug in self._entries:
            slug, i = f"{base}-{i}", i+1
        return slug

    @locked
    def add(self, game_name, application_id, executable=None, **extra):
        if not isinstance(game_name, str) or not game_name.strip() or len(game_name) > 256:
            raise LibraryError("Укажите название игры до 256 символов")
        for entry in self._entries.values():
            if (application_id and entry.application_id == application_id) or entry.game_name.casefold() == game_name.casefold():
                entry.application_id = application_id or entry.application_id
                entry.executable = executable
                for key, value in extra.items():
                    if key in Entry.__dataclass_fields__ and key not in ("slug", "added_at"):
                        setattr(entry, key, value)
                self.save()
                return entry
        entry = Entry(slug=self.unique_slug(game_name), game_name=game_name,
                      application_id=application_id, executable=executable,
                      **{k:v for k,v in extra.items() if k in Entry.__dataclass_fields__ and k not in ("slug", "game_name", "application_id", "executable")})
        self._entries[entry.slug] = entry
        self.save()
        return entry

    @locked
    def update(self, slug, **fields):
        entry = self.get(slug)
        if not entry:
            raise LibraryError("Игра не найдена")
        for key, value in fields.items():
            if key in Entry.__dataclass_fields__ and key not in ("slug", "added_at"):
                setattr(entry, key, value)
        self.save()
        return entry

    @locked
    def update_many(self, changes: dict[str, dict]) -> list:
        """Apply per-slug field changes and save **once**.

        Setting one field across a hundred games used to mean a hundred full
        serialisations, each copying a backup and replacing the file. One write is
        also atomic where a hundred were not: an interruption left mixed durations.
        """
        updated = []
        for slug, fields in (changes or {}).items():
            entry = self._entries.get(slug)
            if entry is None:
                continue
            for key, value in fields.items():
                if key in Entry.__dataclass_fields__ and key not in ("slug", "added_at"):
                    setattr(entry, key, value)
            updated.append(entry)
        self.save()
        return updated

    @locked
    def remove(self, slug):
        if slug not in self._entries:
            return False
        icon = self.icon_path(slug)
        derived = [self.icons_dir / f"{slug}.from-upload.ico",
                   self.icons_dir / f"{slug}.auto.ico",
                   self.icons_dir / f"{slug}.auto.png"]
        del self._entries[slug]
        self._queue = [s for s in self._queue if s != slug]
        self.save()
        if icon:
            icon.unlink(missing_ok=True)
        for extra in derived:
            extra.unlink(missing_ok=True)
        return True

    @property
    def queue(self):
        with self._lock:
            return [s for s in self._queue if s in self._entries]

    @locked
    def set_queue(self, slugs):
        self._queue = list(dict.fromkeys(s for s in slugs if s in self._entries))
        self.save()
        return self.queue

    @locked
    def icon_path(self, slug):
        entry = self.get(slug)
        if not entry or not entry.icon:
            return None
        path = (self.icons_dir / entry.icon).resolve()
        if path.parent != self.icons_dir:
            raise LibraryError("Иконка должна находиться в папке icons")
        return path

    def window_icon_path(self, slug):
        """A .ico file the native window can load for this game, or None.

        The user's uploaded icon wins; a PNG upload is converted, because
        ``LoadImageW`` reads only ICO containers. With no upload at all the
        catalogue's own art — the same picture the dashboard shows — is
        downloaded once and cached, so every game gets its real icon in the
        title bar and on the taskbar instead of a drawn letter.
        """
        entry = self.get(slug)
        if not entry:
            return None
        try:
            user = self.icon_path(slug)
        except LibraryError:
            user = None
        if user:
            if user.suffix.lower() == ".ico":
                return user
            converted = self.icons_dir / f"{slug}.from-upload.ico"
            if not converted.exists():
                data = user.read_bytes()
                if not is_png(data):
                    return None  # jpg/bmp uploads cannot be decoded in stdlib
                write_bytes_atomic(converted, png_to_ico(data))
            return converted
        return self.fetch_catalog_icon(slug)

    def fetch_catalog_icon(self, slug):
        """Download the catalogue art for ``slug`` and cache it as PNG + ICO.

        Returns the ``.auto.ico`` path, or None when the entry has no art URL
        or the download/conversion fails. Art is optional and never fatal:
        the caller falls back to the drawn placeholder.
        """
        entry = self.get(slug)
        if not entry or not entry.catalog_icon_url:
            return None
        cache = self.icons_dir / f"{slug}.auto.ico"
        if cache.exists():
            return cache
        try:
            data = _fetch_catalogue_art(entry.catalog_icon_url)
            if data is None:
                return None
            self.icons_dir.mkdir(parents=True, exist_ok=True)
            write_bytes_atomic(cache, png_to_ico(data))
            write_bytes_atomic(self.icons_dir / f"{slug}.auto.png", data)
            self.log.info("catalogue icon cached for the window", extra={"slug": slug})
            return cache
        except Exception as exc:  # noqa: BLE001 - art is optional, never fatal
            self.log.warning("catalogue icon not fetched", extra={"slug": slug, "error": str(exc)})
            return None

    def site_icon_path(self, slug):
        """The picture the dashboard should serve for this game, if cached locally.

        Uploads first, then the downloaded catalogue art — the same bytes the
        window shows, so the site and the taskbar never disagree.
        """
        entry = self.get(slug)
        if not entry:
            return None
        try:
            user = self.icon_path(slug)
        except LibraryError:
            user = None
        if user and user.is_file():
            return user
        cached = self.icons_dir / f"{slug}.auto.png"
        if cached.is_file():
            return cached
        return None

    @locked
    def set_icon(self, slug, data, original_name):
        entry = self.get(slug)
        if not entry:
            raise LibraryError("Игра не найдена")
        if not data or len(data) > MAX_ICON_BYTES:
            raise LibraryError("Выберите непустую иконку размером до 2 МиБ")
        suffix = Path(original_name).suffix.lower()
        signatures = {".ico": is_ico(data), ".png": data.startswith(b"\x89PNG\r\n\x1a\n"),
                      ".jpg": data.startswith(b"\xff\xd8"), ".jpeg": data.startswith(b"\xff\xd8"),
                      ".bmp": data.startswith(b"BM"), ".webp": data.startswith(b"RIFF") and data[8:12] == b"WEBP"}
        if not signatures.get(suffix):
            raise LibraryError("Формат файла не соответствует иконке: ICO, PNG, JPG, BMP или WebP")
        self.icons_dir.mkdir(parents=True, exist_ok=True)
        previous = self.icon_path(slug)
        name = f"{slug}{suffix}"
        path = self.icons_dir / name
        # Atomic: a torn icon leaves metadata pointing at a file that cannot be read.
        write_bytes_atomic(path, data)
        entry.icon, entry.icon_version = name, hashlib.sha256(data).hexdigest()[:12]
        self.save()
        if previous and previous != path:
            previous.unlink(missing_ok=True)
        # A new upload invalidates the converted window icon, if any.
        (self.icons_dir / f"{slug}.from-upload.ico").unlink(missing_ok=True)
        return entry
