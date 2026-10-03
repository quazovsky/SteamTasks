"""Turn a game name into the application id the presence should use.

The id is not a constant. Discord can re-issue an application, the catalogue can
gain a better match, and a hand-copied id can simply be wrong. So the id is
treated as something derived from the game name and re-derived whenever the
stored one stops working.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass
from typing import Any

from ..core.errors import ConfigError, ResolverError
from ..core.logging import get_logger
from .resolver import Candidate, DetectableIndex

#: A name-only match below this score is reported as "no confident match".
DEFAULT_MIN_SCORE = 70

@dataclass(frozen=True)
class Identity:
    """The application id to connect with, and where it came from."""

    application_id: str
    name: str
    source: str
    candidate: Candidate | None = None

    def to_dict(self) -> dict[str, Any]:
        return {
            "application_id": self.application_id,
            "name": self.name,
            "source": self.source,
            "matched_on": self.candidate.matched_on if self.candidate else None,
            "score": self.candidate.score if self.candidate else None,
        }

class IdentityResolver:
    """Resolves and re-resolves the application id for a game name."""

    def __init__(
        self,
        index: DetectableIndex | None = None,
        logger: logging.Logger | None = None,
        min_score: int = DEFAULT_MIN_SCORE,
    ) -> None:
        self.log = logger or get_logger()
        self.index = index or DetectableIndex(logger=self.log)
        self.min_score = min_score

    def resolve(self, game_name: str, client_id: str | None = None, force: bool = False) -> Identity:
        """Pick the id to use.

        ``client_id`` is trusted when the catalogue confirms it. If the catalogue
        is reachable but does not know the id, the id is treated as stale and the
        game name is used instead. That keeps the tool alive when Discord
        re-issues an application.
        """
        stored = (client_id or "").strip()

        if stored and not force:
            try:
                known = self.index.by_id(stored)
            except ResolverError as exc:
                self.log.warning(
                    "catalogue unavailable, using the configured application id as-is",
                    extra={"error": str(exc), "application_id": stored},
                )
                return Identity(stored, game_name, "config", None)

            if known is not None:
                return Identity(known.id, known.name, "config-verified", known)

            self.log.warning(
                "configured application id is not in the catalogue; re-resolving by name",
                extra={"application_id": stored, "game": game_name},
            )

        return self.resolve_by_name(game_name)

    def resolve_by_name(self, game_name: str) -> Identity:
        name = (game_name or "").strip()
        if not name:
            raise ConfigError("game_name is required to look up an application id")

        best = self.index.best(name, min_score=self.min_score)
        if best is None:
            near = self.index.search(name, limit=5)
            hint = ", ".join(f"{c.name} ({c.id})" for c in near) or "nothing close"
            raise ResolverError(
                f"no Discord application matched {name!r}. Closest entries: {hint}. "
                f"Run `worthlesstask resolve \"{name}\"` to search, or set client_id explicitly."
            )

        return Identity(best.id, best.name, "catalogue", best)

    def refresh(self, game_name: str) -> Identity:
        """Re-derive the id from a freshly downloaded catalogue."""
        self.index.refresh()
        return self.resolve_by_name(game_name)
