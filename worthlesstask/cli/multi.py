"""Commands for the multi-game workflow: library, manager, dashboard."""

from __future__ import annotations

import argparse
import json
import sys
import threading
from pathlib import Path
from typing import Any

from ..config.schema import AppConfig
from ..core.errors import worthlesstaskError
from ..core.logging import setup_logging
from .. import steamlib
from ..library import DEFAULT_ICONS_DIR, DEFAULT_LIBRARY_PATH, Library, LibraryError
from ..manager import (
    MAX_QUEUE_MINUTES, MIN_QUEUE_MINUTES, ManagerError, PresenceManager,
)
from ..paths import default_icons_dir, default_library_path, log_dir
from ..presence.identity import IdentityResolver

EXIT_OK = 0


def _library(args: argparse.Namespace) -> Library:
    path = Path(getattr(args, "library", None)) if getattr(args, "library", None) else default_library_path()
    icons = Path(getattr(args, "icons", None)) if getattr(args, "icons", None) else default_icons_dir()
    return Library(path=path, icons_dir=icons)


def _manager(args: argparse.Namespace, library: Library, logger) -> PresenceManager:
    # Logs and the runtime record live beside the library, not beside the program:
    # an installed build runs from a read-only Program Files folder.
    root = library.path.parent
    return PresenceManager(library, logger=logger, package_root=root, runtime_path=root / "runtime.json")


def _identity_refresher(entry, library: Library, logger):
    def refresh() -> str:
        identity = IdentityResolver(logger=logger).refresh(entry.game_name)
        library.update(entry.slug, application_id=identity.application_id)
        return identity.application_id

    return refresh


def _config_refresher(config, config_path, logger):
    """Re-derive the application id and write it back to the config file.

    Same self-healing as the library path, but for the single-game flow where the
    config file is the only store.
    """
    def refresh() -> str:
        from ..config.schema import save_config

        identity = IdentityResolver(logger=logger).refresh(config.game_name)
        config.client_id = identity.application_id
        save_config(config, config_path)
        return identity.application_id

    return refresh


def cmd_add(args: argparse.Namespace) -> int:
    logger = setup_logging(getattr(args, "log_level", None) or "INFO", None, True)
    library = _library(args)
    resolver = IdentityResolver(logger=logger)

    identity = resolver.resolve_by_name(args.game)
    candidate = identity.candidate
    catalogue_exes = list(candidate.executables) if candidate else []
    raw_app_id = getattr(candidate, "steam_app_id", None) if candidate else None
    app_id = raw_app_id if isinstance(raw_app_id, str) else None
    raw_icon = getattr(candidate, "icon_url", None) if candidate else None
    cand_icon_url = raw_icon if isinstance(raw_icon, str) else None
    # Same resolution the single-game `launch` command uses, so the two entry points
    # cannot disagree about which executable a game is.
    executable, source = steamlib.resolve_image_name(args.game, app_id, catalogue_exes)
    from ..presence.quests import resolve_bypass_plan
    plan = resolve_bypass_plan(
        identity.application_id,
        args.game,
        index=resolver.index,
        logger=logger,
    )
    if source == "derived" and plan.bypass_mode != "derived":
        executable = plan.image_name
        source = plan.executable_source

    entry = library.add(
        args.game,
        identity.application_id,
        executable=executable,
        executable_source=source,
        catalog_icon_url=cand_icon_url or plan.icon_url,
        executable_rel=plan.executable_rel,
        bypass_mode=plan.bypass_mode,
        epic_app_id=plan.epic_app_id,
        steam_app_id=plan.steam_app_id or app_id,
        carrier_app_id=plan.carrier_app_id,
    )
    logger.info(
        "game added",
        extra={
            "slug": entry.slug,
            "application_id": entry.application_id,
            "matched_on": candidate.matched_on if candidate else None,
            "executable": entry.executable,
            "executable_source": source,
            "bypass_mode": plan.bypass_mode,
            "steam_app_id": app_id,
        },
    )
    # Same art the dashboard shows: cache it now so the window and the
    # taskbar carry the game's real icon.
    try:
        library.fetch_catalog_icon(entry.slug)
    except LibraryError as exc:
        logger.warning("catalogue art not cached",
                       extra={"slug": entry.slug, "error": str(exc)})
    print(f"{entry.slug}\t{entry.game_name}\t{entry.application_id}\t{entry.executable or '-'}\t{source}")
    if source == "installed":
        print("info: the executable matches the file present in the installed game", file=sys.stderr)
    elif source == "derived":
        print(
            "warning: the catalogue lists no executable for this game, so the name was "
            "derived from the title. Discord matches processes against its own catalogue, "
            "so playtime may not be credited. Pass the real file name to correct it.",
            file=sys.stderr,
        )
    return EXIT_OK


def cmd_list(args: argparse.Namespace) -> int:
    logger = setup_logging("INFO", None, False)
    library = _library(args)
    manager = _manager(args, library, logger)
    status = manager.status()

    if getattr(args, "json", False):
        print(json.dumps(status, indent=2, ensure_ascii=False))
        return EXIT_OK

    active = status["active"]
    print(f"active: {active['game_name'] + ' (pid ' + str(active['pid']) + ')' if active else '-'}")
    queue = status["queue"]
    print(f"queue:  {' -> '.join(queue) if queue else '-'}")
    print()
    if not status["games"]:
        print("library is empty; add a game with `worthlesstask add --game \"<name>\"`")
        return EXIT_OK

    print(f"{'slug':<24} {'game':<28} {'app id':<20} {'exe':<18} {'min':>4}  icon")
    for game in status["games"]:
        mark = "*" if active and game["slug"] == active["slug"] else " "
        print(
            f"{mark}{game['slug']:<23} {game['game_name'][:27]:<28} {game['application_id']:<20} "
            f"{(game['executable'] or '-')[:17]:<18} {game['duration_minutes']:>4}  {'yes' if game['icon'] else '-'}"
        )
    return EXIT_OK


def cmd_play(args: argparse.Namespace) -> int:
    logger = setup_logging("INFO", None, True)
    library = _library(args)
    manager = _manager(args, library, logger)
    manager.play(args.slug)
    status = manager.status()
    active = status["active"]
    logger.info("playing", extra={"slug": active["slug"], "pid": active["pid"]} if active else {})
    return EXIT_OK


def cmd_stop(args: argparse.Namespace) -> int:
    logger = setup_logging("INFO", None, True)
    library = _library(args)
    manager = _manager(args, library, logger)
    manager.stop(reason="cli")
    return EXIT_OK


def cmd_queue(args: argparse.Namespace) -> int:
    logger = setup_logging("INFO", None, True)
    library = _library(args)
    manager = _manager(args, library, logger)

    minutes = getattr(args, "minutes", None)
    if minutes is not None:
        # The web route enforces this range; the CLI must not accept values that
        # route would reject.
        if not isinstance(minutes, int) or not MIN_QUEUE_MINUTES <= minutes <= MAX_QUEUE_MINUTES:
            print(f"minutes must be a whole number between {MIN_QUEUE_MINUTES} and "
                  f"{MAX_QUEUE_MINUTES}", file=sys.stderr)
            return 2
        for slug in args.slugs:
            if library.get(slug):
                library.update(slug, minutes=minutes)
    queue = manager.set_queue(args.slugs)
    print("queue:", " -> ".join(queue) if queue else "-")
    if not queue:
        return EXIT_OK
    if args.start:
        manager.advance(reason="cli-start")
        stop_event = threading.Event()
        try:
            manager.run_scheduler(stop_event)
        except KeyboardInterrupt:
            pass
        finally:
            stop_event.set()
            manager.stop(reason="cli-exit")
    return EXIT_OK


def cmd_presence(args: argparse.Namespace) -> int:
    """Child worker: hold the presence for one library entry.

    Two shapes reach this command.

    * ``presence --slug <slug>`` — a worker spawned by the manager, driven by the
      library. This is the normal case.
    * ``presence --config <file>`` — a decoy started on its own by ``launch`` or by
      a logon task. There is no library involved; the config file is the whole
      description of the game, and --window is on so the window exists for
      Discord's process and window scanner to find.
    """
    from ..ui.window import run_with_window

    log_dir()
    config_path = getattr(args, "config", None)
    if config_path:
        from ..config.schema import load_config

        config = load_config(path=config_path, require_file=True)
        config.validate()
        config.log_file = args.log_file or str(log_dir() / "launch.log")
        logger = setup_logging(config.log_level, config.log_file, True)
        logger.info("presence worker starting from a config file",
                    extra={"game": config.game_name, "window": True})
        return run_with_window(
            config,
            logger=logger,
            identity_refresher=_config_refresher(config, config_path, logger),
            icon_path=None,
        )

    library = _library(args)
    entry = library.get(args.slug)
    if entry is None:
        print(f"no game with slug {args.slug!r}", file=sys.stderr)
        return 2

    config = AppConfig(
        client_id=entry.application_id,
        game_name=entry.game_name,
        activity_type=entry.activity_type,
        details=entry.details,
        state=entry.state,
        log_file=args.log_file or None,
        log_level=getattr(args, "log_level", None) or "INFO",
    )
    config.validate()
    # A worker started by hand (double-click) gets no --log-file, but the panel reads
    # this file to tell "process running" from "Discord confirmed". Default to the same
    # place the manager uses.
    log_file = args.log_file or str(log_dir() / f"{entry.slug}.log")
    config.log_file = log_file
    logger = setup_logging(config.log_level, log_file, True)
    icon = library.window_icon_path(entry.slug)
    logger.info(
        "presence worker starting",
        extra={"slug": entry.slug, "game": entry.game_name, "icon": str(icon) if icon else None,
               "worker_pid": __import__("os").getpid(),
               "worker_identity": __import__("worthlesstask.manager", fromlist=["process_identity"]).process_identity(__import__("os").getpid())},
    )
    return run_with_window(
        config,
        logger=logger,
        identity_refresher=_identity_refresher(entry, library, logger),
        icon_path=icon,
    )


def cmd_web(args: argparse.Namespace) -> int:
    from ..web.server import Dashboard, find_free_port, is_dashboard_running, serve

    logger = setup_logging(getattr(args, "log_level", None) or "INFO",
                           args.log_file or str(log_dir() / "worthlesstask.log"), True)
    library = _library(args)
    manager = _manager(args, library, logger)
    dashboard = Dashboard(library, manager, logger=logger)

    host = args.host
    port = args.port

    if _port_taken(host, port):
        if is_dashboard_running(host, port, library_path=library.path):
            if args.open:
                import webbrowser
                webbrowser.open(f"http://{host}:{port}")
            print(f"dashboard is already running at http://{host}:{port}", file=sys.stderr)
            return EXIT_OK
        try:
            port = find_free_port(host, port + 1)
        except ManagerError as exc:
            logger.error("cannot bind the dashboard", extra={"error": str(exc)})
            return 1
        logger.warning("port busy, using the next free one", extra={"requested": args.port, "using": port})

    def ready(url):
        if args.open:
            import webbrowser
            webbrowser.open(url)
        if getattr(args, "start_queue", False):
            dashboard.start_scheduler()
        bootstrap(manager, library, logger)

    try:
        return serve(dashboard, host=host, port=port, stop_event=threading.Event(), on_ready=ready)
    except KeyboardInterrupt:
        return EXIT_OK


def _port_taken(host: str, port: int) -> bool:
    from ..web.server import default_port_is_free

    return not default_port_is_free(host, port)


def bootstrap(manager, library, logger) -> dict:
    """Fetch what the program needs and build every worker executable.

    Two things are fetched or built after an install: Discord's detectable
    catalogue, and one renamed copy of this program per game. Failures are
    recorded per game and never abort startup — the dashboard must still come up
    so the user can fix an executable name by hand.
    """
    report = {"catalogue": None, "prepared": [], "failed": [], "sync": None}
    index = None
    try:
        index = IdentityResolver(logger=logger).index
        report["catalogue"] = len(index.entries())
        logger.info("catalogue ready", extra={"entries": report["catalogue"]})
    except worthlesstaskError as exc:
        logger.warning("catalogue unavailable; the dashboard will retry on search",
                       extra={"error": str(exc)})
    try:
        from ..presence.quests import sync_library_with_discord
        report["sync"] = sync_library_with_discord(
            library, index=index, logger=logger, auto_add_quests=True
        )
    except Exception as exc:  # noqa: BLE001 - sync is best-effort on startup
        logger.warning("discord quest sync skipped", extra={"error": str(exc)})
    for entry in library.entries():
        if not entry.executable:
            continue
        try:
            manager.prepare(entry.slug)
            report["prepared"].append(entry.slug)
        except (worthlesstaskError, OSError) as exc:
            report["failed"].append({"slug": entry.slug, "error": str(exc)})
            logger.warning("worker not prepared", extra={"slug": entry.slug, "error": str(exc)})
    return report


def cmd_bootstrap(args: argparse.Namespace) -> int:
    logger = setup_logging(getattr(args, "log_level", None) or "INFO", None, True)
    library = _library(args)
    manager = _manager(args, library, logger)
    report = bootstrap(manager, library, logger)
    print(f"catalogue entries: {report['catalogue']}")
    for slug in report["prepared"]:
        print(f"prepared {slug}")
    for item in report["failed"]:
        print(f"failed   {item['slug']}: {item['error']}", file=sys.stderr)
    if getattr(args, "json", False):
        print(json.dumps(report, ensure_ascii=False))
    return EXIT_OK if not report["failed"] else 1
