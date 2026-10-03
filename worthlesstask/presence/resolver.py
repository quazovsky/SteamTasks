"""Resolve a game name to its Discord application.

Discord publishes the catalogue its game detector uses at
``/api/v9|v10/applications/detectable``. The endpoint answers without
authentication and returns one entry per detectable application, carrying the
application id, the display name, aliases and the executables the detector looks
for.

Using the game's own application id is what makes a presence look authentic:
Discord takes the name shown in a profile from the application, not from the
``name`` field of the activity payload.
"""

from __future__ import annotations

import json
import logging
import random
import re
import time
import urllib.error
import urllib.request
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Callable, Iterable

from ..core.atomic import write_atomic
from ..core.errors import ResolverError
from ..core.logging import get_logger

#: Tried in order. Discord has moved this endpoint between versions before, so a
#: version bump on their side degrades to the next candidate instead of breaking.
ENDPOINT_CANDIDATES = (
    "https://discord.com/api/v10/applications/detectable",
    "https://cdn.discordapp.com/detectables/games-v1.json",
    "https://discord.com/api/v9/applications/detectable",
)
DETECTABLE_URL = ENDPOINT_CANDIDATES[0]
USER_AGENT = "worthlesstask/1.0"
DEFAULT_TTL_SECONDS = 24 * 60 * 60

#: Discord's catalogue is ~13 MB today. The cap is generous but finite, so a
#: hostile or broken response cannot exhaust memory.
MAX_CATALOGUE_BYTES = 32 * 1024 * 1024
#: Long enough for a slow connection, short enough not to wedge the dashboard.
FETCH_TIMEOUT = 20.0
FETCH_ATTEMPTS = 3
FETCH_BACKOFF = 0.75
FETCH_BACKOFF_MAX = 6.0

_NON_ALNUM = re.compile(r"[^a-z0-9]+")

def normalize(text: Any) -> str:
    return _NON_ALNUM.sub("", str(text).casefold())

def executables_of(entry: dict[str, Any]) -> tuple[str, ...]:
    """Executable names for a catalogue entry, preferring win32 non-launchers.

    Discord ships this as a list of objects, but the shape has varied, so plain
    strings are accepted too.
    """
    raw = entry.get("executables")
    if not isinstance(raw, list):
        return ()
    non_launchers: list[str] = []
    launchers: list[str] = []
    other_os: list[str] = []
    for item in raw:
        if isinstance(item, str):
            cleaned = item.strip().lstrip(">")
            if cleaned:
                non_launchers.append(cleaned)
        elif isinstance(item, dict) and item.get("name"):
            cleaned = str(item["name"]).strip().lstrip(">")
            if not cleaned:
                continue
            os_name = str(item.get("os") or "win32").casefold()
            if os_name not in ("win32", ""):
                other_os.append(cleaned)
                continue
            if item.get("is_launcher"):
                launchers.append(cleaned)
            else:
                non_launchers.append(cleaned)
    if non_launchers:
        return tuple(non_launchers)
    if launchers:
        return tuple(launchers)
    return tuple(other_os)

def executable_name(entry: dict[str, Any]) -> str | None:
    """Bare file name of the first executable, without any directory part."""
    for name in executables_of(entry):
        return name.replace("\\", "/").rsplit("/", 1)[-1]
    return None

def steam_app_id_of(entry: dict[str, Any]) -> str | None:
    """The Steam application id from ``third_party_skus``, when Discord lists one."""
    skus = entry.get("third_party_skus")
    for sku in skus if isinstance(skus, list) else []:
        if isinstance(sku, dict) and str(sku.get("distributor", "")).casefold() == "steam":
            value = str(sku.get("id") or sku.get("sku") or "")
            if value.isdigit():
                return value
    return None

def epic_app_id_of(entry: dict[str, Any]) -> str | None:
    """The Epic application id from ``third_party_skus``, when Discord lists one."""
    skus = entry.get("third_party_skus")
    for sku in skus if isinstance(skus, list) else []:
        if isinstance(sku, dict) and str(sku.get("distributor", "")).casefold() == "epic":
            value = str(sku.get("id") or sku.get("sku") or "").strip()
            if value:
                return value
    return None


def is_valid_entry(entry: Any) -> bool:
    return (
        isinstance(entry, dict)
        and str(entry.get("id", "")).isdigit()
        and bool(entry.get("name"))
    )

@dataclass(frozen=True)
class Candidate:
    """One match from the detectable catalogue."""

    id: str
    name: str
    score: int
    matched_on: str
    icon_hash: str | None = None
    cover_image_hash: str | None = None
    hook: bool = False
    executables: tuple[str, ...] = field(default_factory=tuple)
    steam_app_id: str | None = None
    epic_app_id: str | None = None

    @property
    def icon_url(self) -> str | None:
        if not self.icon_hash:
            return None
        return f"https://cdn.discordapp.com/app-icons/{self.id}/{self.icon_hash}.png"

    def to_dict(self) -> dict[str, Any]:
        return {
            "id": self.id,
            "name": self.name,
            "score": self.score,
            "matched_on": self.matched_on,
            "icon_hash": self.icon_hash,
            "icon_url": self.icon_url,
            "hook": self.hook,
            "executables": list(self.executables),
            "steam_app_id": self.steam_app_id,
            "epic_app_id": self.epic_app_id,
        }

def _candidate(entry: dict[str, Any], score: int, matched_on: str) -> Candidate:
    return Candidate(
        id=str(entry.get("id")),
        name=str(entry.get("name") or ""),
        score=score,
        matched_on=matched_on,
        icon_hash=entry.get("icon_hash"),
        cover_image_hash=entry.get("cover_image_hash"),
        hook=bool(entry.get("hook")),
        executables=executables_of(entry),
        steam_app_id=steam_app_id_of(entry),
        epic_app_id=epic_app_id_of(entry),
    )

def score_entry(entry: dict[str, Any], query: str) -> tuple[int, str]:
    """Rank one entry against a query. Higher is better; 0 means no match."""
    q = normalize(query)
    if not q:
        return 0, ""

    n = normalize(entry.get("name") or "")
    if n == q:
        return 100, "name-exact"
    if n.startswith(q):
        return 85, "name-prefix"
    if q in n:
        return 70, "name-substring"

    aliases = entry.get("aliases")
    for alias in aliases if isinstance(aliases, list) else []:
        a = normalize(alias)
        if a == q:
            return 95, f"alias:{alias}"
        if a and q in a:
            return 60, f"alias-substring:{alias}"

    for raw in executables_of(entry):
        base = raw.replace("\\", "/").rsplit("/", 1)[-1].casefold()
        stem = base[:-4] if base.endswith(".exe") else base
        if q in (normalize(base), normalize(stem)):
            return 75, f"executable:{raw}"
        if q and q in normalize(base):
            return 50, f"executable-substring:{raw}"

    return 0, ""

class DetectableIndex:
    """Cached, searchable view of Discord's detectable-application catalogue."""

    def __init__(
        self,
        cache_path: str | Path = ".cache/detectable.json",
        ttl_seconds: int = DEFAULT_TTL_SECONDS,
        logger: logging.Logger | None = None,
        fetch: Callable[[str], bytes] | None = None,
    ) -> None:
        self.cache_path = Path(cache_path)
        self.ttl_seconds = ttl_seconds
        self.log = logger or get_logger()
        self._fetch = fetch or self._http_fetch
        self._entries: list[dict[str, Any]] | None = None
        self.source: str = "none"

    # Loading
    @staticmethod
    def _http_fetch(url: str) -> bytes:
        """Fetch ``url`` with a bounded body and a bounded number of attempts.

        Two failure modes are handled explicitly.

        *Unbounded response.* ``response.read()`` allocates whatever the peer sends.
        A hostile or broken endpoint could exhaust memory, so the body is read in
        chunks and rejected past :data:`MAX_CATALOGUE_BYTES`.

        *Transient failure.* A dropped connection or a 5xx is worth retrying; a 404
        is not. Retries are few, back off exponentially, and jitter so that several
        processes starting together do not retry in lockstep.
        """
        last_error: ResolverError | None = None
        for attempt in range(FETCH_ATTEMPTS):
            request = urllib.request.Request(url, headers={"User-Agent": USER_AGENT})
            try:
                with urllib.request.urlopen(request, timeout=FETCH_TIMEOUT) as response:
                    if response.status != 200:
                        raise ResolverError(f"{url} returned HTTP {response.status}")
                    body = bytearray()
                    while chunk := response.read(1 << 16):
                        body += chunk
                        if len(body) > MAX_CATALOGUE_BYTES:
                            raise ResolverError(
                                f"{url} exceeded {MAX_CATALOGUE_BYTES // (1 << 20)} MiB; refusing to read more"
                            )
                    return bytes(body)
            except urllib.error.HTTPError as exc:
                # 4xx other than 429 is a real answer: retrying cannot change it.
                if exc.code < 500 and exc.code != 429:
                    raise ResolverError(f"{url} returned HTTP {exc.code}") from exc
                last_error = ResolverError(f"{url} returned HTTP {exc.code}")
            except (urllib.error.URLError, TimeoutError, ConnectionError) as exc:
                reason = getattr(exc, "reason", exc)
                last_error = ResolverError(f"{url} unreachable: {reason}")
            except OSError as exc:
                # HTTPError subclasses OSError, so it is handled above by code; this
                # catches the rest (DNS, reset, refused).
                reason = getattr(exc, "reason", exc)
                last_error = ResolverError(f"{url} unreachable: {reason}")
            if attempt + 1 < FETCH_ATTEMPTS:
                delay = min(FETCH_BACKOFF * (2 ** attempt), FETCH_BACKOFF_MAX)
                delay *= 0.75 + (random.random() * 0.5)  # jitter: avoid a retry stampede
                time.sleep(delay)
        raise last_error or ResolverError(f"{url} could not be fetched")

    def _read_cache(self) -> tuple[float, list[dict[str, Any]]] | None:
        """The cached catalogue, or None when there is nothing usable.

        A cache is untrusted input: it can be truncated by a crash, hand-edited, or
        written by an older version. Any of those must read as "no cache" rather than
        raising, because falling back to the network is always available.
        """
        try:
            payload = json.loads(self.cache_path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError, UnicodeDecodeError):
            return None
        if not isinstance(payload, dict):
            return None
        try:
            fetched_at = float(payload.get("fetched_at", 0) or 0)
        except (TypeError, ValueError):
            fetched_at = 0.0
        entries = payload.get("entries")
        if not isinstance(entries, list):
            return None
        return fetched_at, [e for e in entries if is_valid_entry(e)]

    def _write_cache(self, entries: list[dict[str, Any]]) -> None:
        try:
            self.cache_path.parent.mkdir(parents=True, exist_ok=True)
            # Atomic: several processes share this cache, and a truncated one turns
            # every search into a full network fetch.
            write_atomic(
                self.cache_path,
                json.dumps({"fetched_at": time.time(), "entries": entries}),
            )
        except OSError as exc:
            self.log.warning("resolver cache not written", extra={"error": str(exc)})

    def _fetch_catalogue(self) -> list[dict[str, Any]]:
        """Try each known endpoint version until one yields a usable payload."""
        errors: list[str] = []
        for url in ENDPOINT_CANDIDATES:
            try:
                raw = self._fetch(url)
            except ResolverError as exc:
                errors.append(str(exc))
                continue
            except Exception as exc:  # noqa: BLE001 - a fetch helper we do not own
                # Callers branch on ResolverError to decide whether a stale cache is
                # usable, so anything else has to be normalised here.
                errors.append(f"{url}: {type(exc).__name__}: {exc}")
                continue
            try:
                payload = json.loads(raw.decode("utf-8"))
            except (UnicodeDecodeError, json.JSONDecodeError) as exc:
                errors.append(f"{url}: malformed JSON ({exc})")
                continue
            if not isinstance(payload, list):
                errors.append(f"{url}: payload is {type(payload).__name__}, expected a list")
                continue
            entries = [e for e in payload if is_valid_entry(e)]
            if not entries:
                errors.append(f"{url}: no usable entries")
                continue
            self.source = url
            return entries
        raise ResolverError("; ".join(errors) or "no detectable-application endpoint responded")

    def entries(self, force_refresh: bool = False) -> list[dict[str, Any]]:
        """The catalogue, refreshed when the on-disk copy is stale.

        A failed refresh falls back to the cached copy regardless of age: a working
        but outdated catalogue beats no catalogue.
        """
        if self._entries is not None and not force_refresh:
            return self._entries

        # Read the cache even for a forced refresh: if the network fails, a stale
        # catalogue is still far better than none, and the whole point of the cache
        # is to keep search working offline.
        cached = self._read_cache()
        if cached is not None and not force_refresh:
            fetched_at, entries = cached
            age = time.time() - fetched_at
            if age < self.ttl_seconds and entries:
                self.log.debug("catalogue from cache", extra={"entries": len(entries), "age_s": int(age)})
                self._entries = entries
                self.source = "cache"
                return entries

        try:
            entries = self._fetch_catalogue()
        except ResolverError as exc:
            if cached is not None and cached[1]:
                self.log.warning(
                    "catalogue refresh failed, using stale cache",
                    extra={"error": str(exc), "entries": len(cached[1])},
                )
                self._entries = cached[1]
                self.source = "stale-cache"
                return cached[1]
            raise

        self._write_cache(entries)
        self._entries = entries
        self.log.info("catalogue loaded", extra={"entries": len(entries), "source": self.source})
        return entries

    # Searching
    def search(self, query: str, limit: int = 10) -> list[Candidate]:
        scored: list[tuple[int, str, dict[str, Any]]] = []
        for entry in self.entries():
            score, matched_on = score_entry(entry, query)
            if score:
                scored.append((score, matched_on, entry))

        scored.sort(key=lambda item: (-item[0], str(item[2].get("name", "")).casefold()))
        return [_candidate(entry, score, matched) for score, matched, entry in scored[: max(0, limit)]]

    def best(self, query: str, min_score: int = 70) -> Candidate | None:
        """Single best match, or None when nothing clears ``min_score``."""
        results = self.search(query, limit=1)
        if results and results[0].score >= min_score:
            return results[0]
        return None

    def by_id(self, app_id: str) -> Candidate | None:
        wanted = str(app_id)
        for entry in self.entries():
            if str(entry.get("id")) == wanted:
                return _candidate(entry, 100, "id")
        return None

    def refresh(self) -> list[dict[str, Any]]:
        return self.entries(force_refresh=True)

def search_offline(entries: Iterable[dict[str, Any]], query: str, limit: int = 10) -> list[Candidate]:
    """Search an entry list already in memory."""
    index = DetectableIndex(cache_path=Path("."), fetch=lambda _url: b"[]")
    index._entries = [e for e in entries if is_valid_entry(e)]
    return index.search(query, limit=limit)
