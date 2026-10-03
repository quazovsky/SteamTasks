"""Short-lived memoisation for expensive, repeated lookups.

The dashboard polls state every 1.5 seconds, and a single status read used to
enumerate every top-level window and open every worker process to ask for its
creation time and image path. Those are Win32 calls that do not change meaningfully
within one poll interval, so they are cached for a fraction of a second.

The TTLs are deliberately short: long enough to collapse the several calls made
inside one status read, short enough that a test which mocks a change still sees it
on the next poll. Anything that mutates process state clears the caches outright.
"""

from __future__ import annotations

import threading
import time
from typing import Any, Callable


class TtlCache:
    """A tiny thread-safe key/value cache with a per-entry lifetime."""

    def __init__(self, ttl: float, name: str = "cache"):
        self.ttl = ttl
        self.name = name
        self._data: dict[Any, tuple[float, Any]] = {}
        self._lock = threading.Lock()
        self.hits = 0
        self.misses = 0

    def get(self, key: Any) -> Any | None:
        now = time.monotonic()
        with self._lock:
            entry = self._data.get(key)
            if entry is not None and (now - entry[0]) < self.ttl:
                self.hits += 1
                return entry[1]
            self.misses += 1
            return None

    def set(self, key: Any, value: Any) -> Any:
        with self._lock:
            self._data[key] = (time.monotonic(), value)
        return value

    def clear(self) -> None:
        with self._lock:
            self._data.clear()

    def __len__(self) -> int:
        with self._lock:
            return len(self._data)


#: A callable list memoised for one interval — used for window enumeration, which
#: returns a collection rather than a single value.
class TtlValue:
    def __init__(self, ttl: float, name: str = "value"):
        self.ttl = ttl
        self.name = name
        self._value: Any = None
        self._at = 0.0
        self._has = False
        self._lock = threading.Lock()
        #: Optional identity of the source the value came from. Changing it
        #: invalidates the entry, so a replaced function is never answered from the
        #: result of the one it replaced.
        self.key: Any = None

    def get(self) -> Any | None:
        with self._lock:
            if self._has and (time.monotonic() - self._at) < self.ttl:
                return self._value
            return None

    def set(self, value: Any) -> Any:
        with self._lock:
            self._value = value
            self._at = time.monotonic()
            self._has = True
        return value

    def clear(self) -> None:
        with self._lock:
            self._value = None
            self._has = False
            self.key = None


def memoise(cache: TtlCache, func: Callable[..., Any]) -> Callable[..., Any]:
    """Wrap ``func`` so its results are served from ``cache`` for one TTL.

    ``None`` results are not cached: "this pid does not exist" is exactly the kind
    of answer that must be re-checked, since the process may have appeared.
    """

    def wrapper(*args: Any, **kwargs: Any) -> Any:
        if kwargs:
            return func(*args, **kwargs)
        cached = cache.get(args)
        if cached is not None:
            return cached
        value = func(*args)
        if value is not None:
            cache.set(args, value)
        return value

    wrapper.__name__ = getattr(func, "__name__", "memoised")
    wrapper.__wrapped__ = func  # type: ignore[attr-defined]
    return wrapper
