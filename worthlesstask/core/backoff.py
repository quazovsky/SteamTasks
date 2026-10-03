"""Reconnection policy: capped exponential backoff with jitter."""

from __future__ import annotations

import random
from dataclasses import dataclass


@dataclass(frozen=True)
class BackoffPolicy:
    """Capped exponential backoff with symmetric jitter.

    ``delay_for(attempt)`` for attempt 1 returns roughly ``base_delay``.
    Jitter spreads reconnects so several clients do not synchronise their retries.
    """

    base_delay: float = 1.0
    factor: float = 2.0
    max_delay: float = 60.0
    jitter: float = 0.25
    max_attempts: int | None = None

    def __post_init__(self) -> None:
        if self.base_delay <= 0:
            raise ValueError("base_delay must be > 0")
        if self.factor < 1:
            raise ValueError("factor must be >= 1")
        if self.max_delay < self.base_delay:
            raise ValueError("max_delay must be >= base_delay")
        if not 0.0 <= self.jitter < 1.0:
            raise ValueError("jitter must be in [0, 1)")
        if self.max_attempts is not None and self.max_attempts < 1:
            raise ValueError("max_attempts must be >= 1 when set")

    def base_for(self, attempt: int) -> float:
        """Deterministic (un-jittered) delay for a 1-based attempt number."""
        if attempt < 1:
            raise ValueError("attempt is 1-based")
        raw = self.base_delay * (self.factor ** (attempt - 1))
        return min(raw, self.max_delay)

    def delay_for(self, attempt: int, rng: random.Random | None = None) -> float:
        """Jittered delay in seconds for a 1-based attempt number."""
        base = self.base_for(attempt)
        if self.jitter == 0:
            return base
        r = (rng or random).uniform(-1.0, 1.0)
        return max(0.0, base * (1.0 + self.jitter * r))

    def should_retry(self, attempt: int) -> bool:
        """Whether attempt ``attempt`` has already failed and another is allowed."""
        if self.max_attempts is None:
            return True
        return attempt < self.max_attempts

    def to_dict(self) -> dict:
        return {
            "base_delay": self.base_delay,
            "factor": self.factor,
            "max_delay": self.max_delay,
            "jitter": self.jitter,
            "max_attempts": self.max_attempts,
        }

    @classmethod
    def from_dict(cls, data: dict | None) -> "BackoffPolicy":
        return cls(**(data or {}))
