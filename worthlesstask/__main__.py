"""``python -m worthlesstask`` entry point."""

from __future__ import annotations

import json
import os
import sys
from pathlib import Path

# A windowed packaged executable has no console streams.
for _stream in ("stdout", "stderr"):
    if getattr(sys, _stream) is None:
        setattr(sys, _stream, open(os.devnull, "w", encoding="utf-8"))

from worthlesstask.cli.app import main


def worker_slug_for(image_name: str, root: Path) -> str | None:
    """The game a copied worker belongs to, identified by its own file name.

    A worker is a copy of this executable named after the game's executable, so the
    file name is the identity. Double-clicking it opens that game's window instead of
    the dashboard.
    """
    wanted = str(image_name).casefold()
    try:
        payload = json.loads((root / "library.json").read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return None
    games = payload.get("games") if isinstance(payload, dict) else None
    for entry in games if isinstance(games, list) else []:
        if not isinstance(entry, dict):
            continue
        exe = str(entry.get("executable") or "").casefold()
        slug = entry.get("slug")
        if exe and exe == wanted and isinstance(slug, str) and slug:
            return slug
    return None


def _frozen_args() -> list[str] | None:
    """Map packaged-executable invocations to the normal CLI.

    The worker is copied to a game's executable name. PyInstaller binaries do not
    understand ``-m worthlesstask`` like a Python interpreter does, so the manager
    uses ``--worker`` for the copied child. Starting the base executable with no
    arguments opens the local dashboard; starting a *worker* copy opens that game,
    which is what makes a double-click behave like launching the game.
    """
    if not getattr(sys, "frozen", False):
        return None
    args = sys.argv[1:]
    if args and args[0] == "--worker":
        return ["presence", *args[1:]]
    if not args:
        exe_path = Path(sys.executable).resolve()
        for root in (exe_path.parent, exe_path.parent.parent, exe_path.parent.parent.parent):
            slug = worker_slug_for(exe_path.name, root)
            if slug:
                return ["presence", "--slug", slug]
        from worthlesstask.paths import appdata_root
        slug = worker_slug_for(exe_path.name, appdata_root())
        if slug:
            return ["presence", "--slug", slug]
        return ["web", "--open"]
    return args


if __name__ == "__main__":
    sys.exit(main(_frozen_args()))
