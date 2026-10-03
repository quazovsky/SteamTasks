"""Entry point and subcommand dispatch."""

from __future__ import annotations

import argparse
import json
import os
import signal
import subprocess
import sys
import threading
import time
from pathlib import Path
from typing import Any, Sequence

from .. import __version__
from ..config.schema import SEARCH_PATHS, AppConfig, find_config_file, load_config, save_config
from ..core.errors import (
    ConfigError, IpcUnavailableError, ProtocolError, RpcTimeout, worthlesstaskError,
    TransportError,
)
from ..core.logging import setup_logging
from ..presence.builder import ACTIVITY_TYPE_CODES
from ..presence.resolver import Candidate, DetectableIndex
from ..rpc.client import RpcClient
from ..rpc.supervisor import EXIT_OK, PresenceSupervisor
from .doctor import run_doctor
from ..decoy import (
    decoy_run_argv, ensure_decoy, executable_name_for, logon_task_command,
    validate_task_name,
)
from ..paths import is_frozen
from ..install import (
    InstallError,
    SHORTCUT_NAME,
    appdata_root,
    install,
    source_folder,
    uninstall,
)
from .multi import (
    cmd_add,
    cmd_bootstrap,
    cmd_list,
    cmd_play,
    cmd_presence,
    cmd_queue,
    cmd_stop,
    cmd_web,
)

TASK_NAME = "worthlesstask"

# Argument parsing
def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="worthlesstask",
        description="Set an authentic \"Playing <game>\" Rich Presence on Discord and keep it alive.",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog=(
            "multi-game workflow:\n"
            "  worthlesstask web                              local dashboard, pick games in the browser\n"
            "  worthlesstask add --game \"Dead by Daylight\"    resolve the id and add the game\n"
            "  worthlesstask list                             library, queue and what is running\n"
            "  worthlesstask play dead-by-daylight            start one game\n"
            "  worthlesstask queue a b c --minutes 15 --start rotate through games\n"
            "\n"
            "single game:\n"
            "  worthlesstask launch                           re-launch as the game executable with a window\n"
            "  worthlesstask doctor                           check Discord IPC, config and payload\n"
            "  worthlesstask resolve \"The Forest\"             list candidate applications\n"
        ),
    )
    parser.add_argument("--version", action="version", version=f"worthlesstask {__version__}")
    parser.add_argument("--config", help="path to config.json")
    parser.add_argument("--log-level", default=None, help="DEBUG | INFO | WARNING | ERROR")
    parser.add_argument("--log-file", default=None, help="JSONL log destination ('-' disables)")
    parser.add_argument("--json", action="store_true", help="machine-readable output")

    # Connection overrides shared by every command that talks to Discord.
    conn = argparse.ArgumentParser(add_help=False)
    conn.add_argument("--client-id", help="Discord application id to connect with")
    conn.add_argument("--game", help="game name; with --resolve-client-id it is looked up automatically")
    conn.add_argument("--resolve-client-id", action="store_true",
                      help="use the game's own Discord application id (authentic presence)")
    conn.add_argument("--details", help="activity line 1 (2-128 chars)")
    conn.add_argument("--state", help="activity line 2 (2-128 chars)")
    conn.add_argument("--type", dest="activity_type", choices=sorted(ACTIVITY_TYPE_CODES),
                      help="activity type (Discord rejects 'streaming' over RPC)")
    conn.add_argument("--large-image", help="asset key registered on the application")
    conn.add_argument("--large-text", help="tooltip for the large image")
    conn.add_argument("--small-image", help="asset key registered on the application")
    conn.add_argument("--small-text", help="tooltip for the small image")
    conn.add_argument("--button", action="append", default=None, metavar="LABEL|URL",
                      help="up to 2 buttons, e.g. --button \"Wiki|https://example.com\"")
    conn.add_argument("--party", metavar="CURRENT|MAX", help="party size, e.g. --party 1|4")
    conn.add_argument("--party-id", help="party id")
    conn.add_argument("--no-elapsed", action="store_true", help="do not show the elapsed timer")
    conn.add_argument("--refresh", type=float, help="seconds between presence refreshes (>= 5)")

    # The same global switches are accepted after the subcommand too, so
    # `worthlesstask run --log-file -` works. SUPPRESS stops the subcommand copies
    # from clobbering values already parsed before the subcommand.
    globalish = argparse.ArgumentParser(add_help=False)
    globalish.add_argument("--config", default=argparse.SUPPRESS)
    globalish.add_argument("--log-level", default=argparse.SUPPRESS)
    globalish.add_argument("--log-file", default=argparse.SUPPRESS)
    globalish.add_argument("--json", action="store_true", default=argparse.SUPPRESS)

    sub = parser.add_subparsers(dest="command")

    run = sub.add_parser("run", parents=[globalish, conn], help="hold the presence (foreground)")
    run.add_argument("--max-attempts", type=int, default=None,
                     help="give up after N consecutive reconnect failures")
    run.add_argument("--backoff-base", type=float, default=None, help="initial retry delay, seconds")
    run.add_argument("--backoff-max", type=float, default=None, help="maximum retry delay, seconds")
    run.add_argument("--keep-on-exit", action="store_true",
                     help="do not clear the presence when shutting down")
    run.add_argument("--window", action="store_true",
                     help="show a real window titled with the game name (Discord's game "
                          "detector inspects top-level windows, not just process names)")

    smoke = sub.add_parser("set", parents=[globalish, conn], help="set the presence once")
    smoke.add_argument("--hold", type=float, default=0.0,
                       help="seconds to hold before clearing (0 = clear immediately after the ack)")
    smoke.add_argument("--keep", action="store_true", help="leave the presence in place after exiting")

    sub.add_parser("clear", parents=[globalish], help="clear the presence")
    sub.add_parser("doctor", parents=[globalish], help="diagnose the environment")

    show = sub.add_parser("show", parents=[globalish, conn], help="print the effective config and payload")

    resolve = sub.add_parser("resolve", parents=[globalish], help="find a game's original Discord application")
    resolve.add_argument("query", help="game name, alias or executable")
    resolve.add_argument("--limit", type=int, default=10)
    resolve.add_argument("--no-cache", action="store_true", help="bypass the local catalogue cache")

    init = sub.add_parser("init", parents=[globalish], help="write config.json")
    init.add_argument("--game", required=True, help="game name")
    init.add_argument("--client-id", help="use this application id instead of resolving the game's own")
    init.add_argument("--output", default="config.json")
    init.add_argument("--force", action="store_true", help="overwrite an existing file")

    autostart = sub.add_parser("autostart", parents=[globalish], help="keep the presence running from logon")
    autostart.add_argument("--remove", action="store_true")
    autostart.add_argument("--apply", action="store_true", help="actually create/remove the entry")

    sub.add_parser(
        "launch",
        parents=[globalish, conn],
        help="one-shot: re-launch as the game's own executable with a window",
    )

    store = argparse.ArgumentParser(add_help=False)
    store.add_argument("--library", help="path to library.json")
    store.add_argument("--icons", help="directory holding per-game icons")

    add = sub.add_parser(
        "add", parents=[globalish, store],
        help="look a game up by name and add it to the library",
    )
    add.add_argument("--game", required=True, help="game name, e.g. \"Dead by Daylight\"")

    sub.add_parser(
        "list", parents=[globalish, store],
        help="show the library, the queue and what is currently running",
    )

    play = sub.add_parser("play", parents=[globalish, store], help="start one game's presence")
    play.add_argument("slug", help="library slug, see `worthlesstask list`")

    sub.add_parser("stop", parents=[globalish, store], help="stop the running presence")

    queue = sub.add_parser("queue", parents=[globalish, store], help="set the rotation queue")
    queue.add_argument("slugs", nargs="*", help="slugs to rotate through, in order")
    queue.add_argument("--minutes", type=int, help="minutes per game")
    queue.add_argument("--start", action="store_true", help="start rotating now and stay in the foreground")

    web = sub.add_parser("web", parents=[globalish, store], help="run the local dashboard")
    web.add_argument("--host", default="127.0.0.1", help="interface to bind (default: loopback only)")
    web.add_argument("--port", type=int, default=8787)
    web.add_argument("--open", action="store_true", help="open the dashboard in the browser")
    web.add_argument("--start-queue", action="store_true", help="start the queue as soon as the dashboard is up")

    sub.add_parser(
        "bootstrap", parents=[globalish, store],
        help="download the Discord catalogue and build every game's executable",
    )

    installer = sub.add_parser(
        "install", parents=[globalish],
        help="copy this program into Program Files or %%LOCALAPPDATA%% and add shortcuts",
    )
    installer.add_argument("--target", help="destination folder (default: Program Files, or "
                                           "%%LOCALAPPDATA%%\\Programs\\worthlesstask with --per-user)")
    installer.add_argument("--per-user", action="store_true", help="install without elevation")
    installer.add_argument("--launch", action="store_true", help="start the dashboard afterwards")

    remover = sub.add_parser("uninstall", parents=[globalish], help="remove an installed copy")
    remover.add_argument("--installed", help="folder to remove (default: the running folder)")
    remover.add_argument("--purge-data", action="store_true",
                         help="also delete the library, icons and logs under %%LOCALAPPDATA%%")
    remover.add_argument("--yes", action="store_true", help="do not ask for confirmation")

    presence = sub.add_parser(
        "presence", parents=[globalish, store],
        help="internal: hold the presence for one library entry",
    )
    # --slug drives the library flow; --config drives a standalone decoy
    # (launch re-exec, or a logon task). One of the two is required.
    presence.add_argument("--slug", required=False)
    presence.add_argument("-epicapp", "--epicapp", default=None, help=argparse.SUPPRESS)

    return parser

# Helpers
def _parse_buttons(raw: list[str] | None) -> list[dict[str, str]] | None:
    if not raw:
        return None
    buttons: list[dict[str, str]] = []
    for item in raw:
        if "|" not in item:
            raise ConfigError(f"--button expects 'LABEL|URL', got {item!r}")
        label, url = item.split("|", 1)
        buttons.append({"label": label.strip(), "url": url.strip()})
    return buttons

def _parse_party(raw: str | None) -> list[int] | None:
    if not raw:
        return None
    if "|" not in raw:
        raise ConfigError(f"--party expects 'CURRENT|MAX', got {raw!r}")
    current, maximum = raw.split("|", 1)
    try:
        return [int(current.strip()), int(maximum.strip())]
    except ValueError as exc:
        # int() raising here escaped main()'s handlers and printed a traceback.
        raise ConfigError(f"--party expects whole numbers, got {raw!r}") from exc

def _overrides(args: argparse.Namespace, base_backoff=None) -> dict[str, Any]:
    game = getattr(args, "game", None)
    overrides: dict[str, Any] = {
        "client_id": getattr(args, "client_id", None),
        "game_name": game,
        "activity_type": getattr(args, "activity_type", None),
        "details": getattr(args, "details", None),
        "state": getattr(args, "state", None),
        "large_image": getattr(args, "large_image", None),
        "large_text": getattr(args, "large_text", None),
        "small_image": getattr(args, "small_image", None),
        "small_text": getattr(args, "small_text", None),
        "party_id": getattr(args, "party_id", None),
        "refresh_interval": getattr(args, "refresh", None),
        "log_level": getattr(args, "log_level", None),
        "log_file": getattr(args, "log_file", None),
        "buttons": _parse_buttons(getattr(args, "button", None)),
        "party_size": _parse_party(getattr(args, "party", None)),
    }
    # Switching games on the command line must not leave a stale tooltip from the
    # config file pointing at the previous game.
    if game and not getattr(args, "large_text", None):
        overrides["large_text"] = game
    if getattr(args, "no_elapsed", False):
        overrides["show_elapsed"] = False
    if getattr(args, "keep_on_exit", False):
        overrides["clear_on_exit"] = False
    # Backoff flags are independent: --backoff-base alone must work, and supplying
    # one must not silently reset the others to their defaults.
    if any(getattr(args, name, None) is not None
           for name in ("max_attempts", "backoff_base", "backoff_max")):
        overrides["backoff"] = _backoff_override(args, base_backoff)
    return overrides


def _backoff_override(args: argparse.Namespace, base_backoff=None):
    """A backoff policy with only the supplied fields changed.

    Starting from the existing policy keeps its factor and jitter; rebuilding from
    defaults discarded them, so `--backoff-base` alone quietly changed retry timing
    in ways the user did not ask for.
    """
    from ..core.backoff import BackoffPolicy

    current = base_backoff or BackoffPolicy()
    changes = {
        "max_attempts": getattr(args, "max_attempts", None),
        "base_delay": getattr(args, "backoff_base", None),
        "max_delay": getattr(args, "backoff_max", None),
    }
    fields = {
        "max_attempts": current.max_attempts,
        "base_delay": current.base_delay,
        "max_delay": current.max_delay,
        "factor": current.factor,
        "jitter": current.jitter,
    }
    fields.update({key: value for key, value in changes.items() if value is not None})
    return BackoffPolicy(**fields)

def _resolve_client_id(game_name: str, logger) -> str:
    index = DetectableIndex(logger=logger)
    candidate = index.best(game_name, min_score=70)
    if candidate is None:
        raise ConfigError(
            f"no Discord application matched {game_name!r}. "
            "Run `worthlesstask resolve <name>` to see what the catalogue contains, "
            "or pass --client-id explicitly."
        )
    return candidate.id

def _config_path(args: argparse.Namespace) -> Path | None:
    try:
        return find_config_file(getattr(args, "config", None))
    except ConfigError:
        return None

def _remember_identity(config: AppConfig, path: Path | None, logger) -> None:
    """Write the resolved id back so the next run needs no lookup."""
    if path is None:
        logger.debug("no config file to update with the resolved id")
        return
    try:
        save_config(config, path)
        logger.info("resolved id written to config", extra={"path": str(path)})
    except OSError as exc:
        logger.warning("could not persist the resolved id", extra={"error": str(exc)})

def _make_identity_refresher(config: AppConfig, path: Path | None, logger):
    """Callback the supervisor calls when Discord rejects the application id."""

    def refresh() -> str:
        from ..presence.identity import IdentityResolver

        identity = IdentityResolver(logger=logger).refresh(config.game_name)
        if identity.application_id != config.client_id:
            config.client_id = identity.application_id
            _remember_identity(config, path, logger)
        return identity.application_id

    return refresh

def _resolve_identity(config: AppConfig, args: argparse.Namespace, logger=None) -> AppConfig:
    """Derive the application id from the game name and remember it.

    Runs for every command, so a new game only ever needs a name in the config.
    When the stored id is not in Discord's catalogue it is treated as stale and
    re-derived. That is what survives Discord re-issuing an application.
    """
    from ..presence.identity import IdentityResolver

    log = logger or setup_logging(config.log_level, None, False)
    resolver = IdentityResolver(logger=log)
    force = bool(getattr(args, "resolve_client_id", False))

    identity = resolver.resolve(config.game_name, config.client_id, force=force)
    changed = identity.application_id != config.client_id
    config.client_id = identity.application_id
    if not config.large_text:
        config.large_text = identity.name
    config.validate()

    log.info(
        "application id resolved",
        extra={"game": config.game_name, **identity.to_dict(), "changed": changed},
    )
    if changed:
        _remember_identity(config, _config_path(args), log)
    return config

def _load(args: argparse.Namespace, require: bool = True) -> AppConfig:
    path = getattr(args, "config", None)
    # Load once without overrides to learn the current backoff policy, so the flags
    # can change individual fields instead of replacing the whole thing.
    base = None
    try:
        base = load_config(path=path, require_file=require).backoff
    except worthlesstaskError:
        base = None
    config = load_config(
        path=path,
        overrides=_overrides(args, base_backoff=base),
        require_file=require,
    )
    return _resolve_identity(config, args)

def _print_candidates(candidates: list[Candidate], as_json: bool) -> None:
    if as_json:
        print(json.dumps([c.to_dict() for c in candidates], indent=2, ensure_ascii=False))
        return
    if not candidates:
        print("no matches")
        return
    print(f"{'score':>5}  {'application id':<20} {'name':<34} matched on")
    for candidate in candidates:
        print(f"{candidate.score:>5}  {candidate.id:<20} {candidate.name[:33]:<34} {candidate.matched_on}")

def _install_signal_handlers(stop_event: threading.Event) -> None:
    def handler(signum, _frame):  # noqa: ANN001
        stop_event.set()

    for sig in (signal.SIGINT, signal.SIGTERM):
        try:
            signal.signal(sig, handler)
        except (ValueError, OSError):
            pass  # not on the main thread, or unsupported on this platform

# Commands
def cmd_run(args: argparse.Namespace) -> int:
    config = _load(args)
    logger = setup_logging(config.log_level, config.log_file, True)
    refresher = _make_identity_refresher(config, _config_path(args), logger)

    if getattr(args, "window", False):
        from ..decoy import current_image_name, executable_name_for
        from ..ui.window import run_with_window_supervised

        expected = executable_name_for(config.client_id, logger=logger)
        if expected and current_image_name().casefold() != expected.casefold():
            logger.warning(
                "process image does not match the game executable; Discord will not register "
                "the game, so use `worthlesstask launch` instead",
                extra={"running_as": current_image_name(), "expected": expected},
            )
        logger.info("starting in window mode", extra={"title": config.game_name})
        # The window owns a supervisor that clears on exit. Asking whether it did
        # avoids a second handshake, which Discord throttles.
        exit_code, cleared = run_with_window_supervised(
            config, logger=logger, identity_refresher=refresher)
        if config.clear_on_exit and not cleared:
            _clear_best_effort(config, logger)
        return exit_code

    supervisor = PresenceSupervisor(config, logger=logger, identity_refresher=refresher)
    stop_event = threading.Event()
    _install_signal_handlers(stop_event)
    try:
        return supervisor.run(stop_event)
    finally:
        # The supervisor clears on its way out. Clearing again would open a second
        # IPC connection for no effect, and Discord throttles those handshakes.
        if config.clear_on_exit and not supervisor.stats.cleared:
            _clear_best_effort(config, logger)

def _connect_with_retry(config: AppConfig, logger, attempts: int = 3) -> RpcClient:
    """Connect, retrying transient failures.

    Discord throttles IPC handshakes after a burst of connections: the socket
    opens but READY can take tens of seconds, or never arrive. Retrying is the
    documented remedy for a one-shot command.
    """
    last_error: Exception | None = None
    for attempt in range(1, attempts + 1):
        client = RpcClient(
            client_id=config.client_id,
            logger=logger,
            command_timeout=config.command_timeout,
            handshake_timeout=config.handshake_timeout,
        )
        try:
            client.connect()
            return client
        except (IpcUnavailableError, RpcTimeout, TransportError, ProtocolError, OSError) as exc:
            # Transport/protocol faults and "Discord is not running" are all
            # transient here. Anything else — a fatal close code, for instance —
            # propagates, because retrying cannot change it.
            last_error = exc
            if attempt < attempts:
                logger.warning(
                    "connect attempt failed; retrying",
                    extra={"attempt": attempt, "of": attempts, "error": str(exc)},
                )
                time.sleep(min(2.0 * attempt, 5.0))
        finally:
            # Always closed: a client left open leaks a reader thread, and the
            # non-retryable paths below never reach the close in the loop body.
            client.close()
    assert last_error is not None
    raise last_error

def cmd_set(args: argparse.Namespace) -> int:
    config = _load(args)
    logger = setup_logging(config.log_level, None, True)
    supervisor = PresenceSupervisor(
        config,
        logger=logger,
        identity_refresher=_make_identity_refresher(config, _config_path(args), logger),
    )
    client = _connect_with_retry(config, logger)
    try:
        supervisor.apply(client)
        if args.hold > 0:
            logger.info("holding presence", extra={"seconds": args.hold})
            deadline = time.monotonic() + args.hold
            while time.monotonic() < deadline:
                if client.wait_closed(min(1.0, max(0.0, deadline - time.monotonic()))):
                    logger.warning("connection lost during hold")
                    break
        if not args.keep:
            client.clear_activity()
            logger.info("presence cleared")
    finally:
        client.close()
    return EXIT_OK

def cmd_clear(_args: argparse.Namespace) -> int:
    logger = setup_logging("INFO", None, True)
    try:
        config = load_config(require_file=True)
    except ConfigError as exc:
        logger.error("cannot clear without a config", extra={"error": str(exc)})
        return 1
    _clear_best_effort(config, logger)
    return EXIT_OK

def _clear_best_effort(config: AppConfig, logger) -> None:
    try:
        client = RpcClient(client_id=config.client_id, logger=logger)
        client.connect()
        client.clear_activity()
        client.close()
        logger.info("presence cleared")
    except worthlesstaskError as exc:
        logger.debug("clear on exit skipped", extra={"error": str(exc)})

def cmd_doctor(args: argparse.Namespace) -> int:
    config: AppConfig | None = None
    error: str | None = None
    try:
        config = load_config(path=getattr(args, "config", None), require_file=False)
    except worthlesstaskError as exc:
        error = str(exc)
    return run_doctor(config=config, config_error=error, as_json=getattr(args, "json", False))

def cmd_show(args: argparse.Namespace) -> int:
    config = load_config(
        path=getattr(args, "config", None), overrides=_overrides(args), require_file=False
    )
    config = _resolve_identity(config, args)
    supervisor = PresenceSupervisor(config)
    payload = supervisor.build()
    if getattr(args, "json", False):
        print(json.dumps({"config": config.masked(), "activity": payload}, indent=2, ensure_ascii=False))
        return EXIT_OK

    print("effective configuration")
    for key, value in config.masked().items():
        if key == "backoff":
            continue
        print(f"  {key:<18} {value}")
    print("\nactivity payload sent to Discord")
    print(json.dumps(payload, indent=2, ensure_ascii=False))
    print("\nnote: the name shown in your profile comes from the application id, not from 'name'.")
    return EXIT_OK

def cmd_resolve(args: argparse.Namespace) -> int:
    logger = setup_logging("INFO", None, False)
    try:
        index = DetectableIndex(logger=logger)
        index.entries(force_refresh=bool(args.no_cache))
        candidates = index.search(args.query, limit=args.limit)
    except worthlesstaskError as exc:
        print(f"resolve failed: {exc}", file=sys.stderr)
        return 1
    _print_candidates(candidates, getattr(args, "json", False))
    return EXIT_OK if candidates else 1

def cmd_init(args: argparse.Namespace) -> int:
    logger = setup_logging("INFO", None, False)
    target = Path(args.output).expanduser()
    if target.exists() and not args.force:
        print(f"{target} already exists; pass --force to overwrite", file=sys.stderr)
        return 1

    client_id = args.client_id
    matched_on = "explicit --client-id"
    if not client_id:
        index = DetectableIndex(logger=logger)
        candidate = index.best(args.game, min_score=70)
        if candidate is None:
            print(
                f"no Discord application matched {args.game!r}; "
                f"run `worthlesstask resolve \"{args.game}\"` or pass --client-id",
                file=sys.stderr,
            )
            return 1
        client_id = candidate.id
        matched_on = f"{candidate.matched_on} (score {candidate.score})"
        print(f"resolved {candidate.name!r} -> {client_id}  [{matched_on}]")

    config = AppConfig(
        client_id=client_id,
        game_name=args.game,
        details=None,
        state=None,
        large_text=args.game,
    )
    config.validate()
    written = save_config(config, target)
    print(f"wrote {written}")
    print(f"next: worthlesstask doctor && worthlesstask run")
    return EXIT_OK

def _launch_config_path(args: argparse.Namespace) -> str | None:
    """The config the re-executed decoy should load.

    The child is a different process image and may start in a different directory, so
    a path only survives if it is absolute.
    """
    return _autostart_config_path(args)


def _autostart_config_path(args: argparse.Namespace) -> str | None:
    """The config a logon task should use.

    A relative path would be resolved against the task's working directory, which is
    not the user's shell, so it is made absolute here.
    """
    from ..config.schema import find_config_file

    explicit = getattr(args, "config", None)
    if explicit:
        return os.path.abspath(explicit)
    found = find_config_file(explicit)
    return os.path.abspath(found) if found else None


class AutostartError(Exception):
    """Autostart cannot be set up, in a way the user can act on."""


def _autostart_command(args: argparse.Namespace) -> list[str]:
    """The ``schtasks`` argv that schedules the presence at logon.

    Kept separate from :func:`cmd_autostart` so the command can be asserted without
    touching the task scheduler.
    """
    if args.remove:
        return ["schtasks", "/delete", "/tn", validate_task_name(TASK_NAME), "/f"]

    from ..config.schema import load_config

    config_path = _autostart_config_path(args)
    if not config_path:
        raise AutostartError(
            "no config.json found. Run `worthlesstask init --game \"<name>\"` first, "
            "or pass --config <file>."
        )

    config = load_config(path=config_path, require_file=True)
    image_name = executable_name_for(config.client_id)
    if not image_name:
        raise AutostartError(
            f"the Discord catalogue lists no executable for application id "
            f"{config.client_id}. Autostart needs the game's own app id."
        )

    decoy = ensure_decoy(image_name, client_id=config.client_id)
    # Built by the shared helper so the task name is validated and every
    # interpolated part is quoted; a config path with a space must not split.
    return logon_task_command(decoy, task_name=TASK_NAME, window=True,
                              config_path=config_path)


def cmd_autostart(args: argparse.Namespace) -> int:
    """Schedule the presence at logon.

    The task runs the *decoy* — a copy of the program renamed to the game's
    executable — in window mode. Running the plain interpreter would publish the
    presence while Discord's process and window scanner saw no matching process, so
    the game would never be registered and a quest would not be credited.
    """
    if os.name != "nt":
        print("autostart is implemented for Windows only.", file=sys.stderr)
        print("On Linux/macOS, add this to your session startup instead:", file=sys.stderr)
        print('  worthlesstask launch &', file=sys.stderr)
        return 1

    try:
        command = _autostart_command(args)
    except AutostartError as exc:
        print(str(exc), file=sys.stderr)
        return 1

    # Quote for display so the printed command is actually copy-pasteable into cmd.exe:
    # the /tr value already contains quotes, so inner ones must be backslash-escaped.
    printable = " ".join(
        f'"{part.replace(chr(34), chr(92) + chr(34))}"' if " " in part else part
        for part in command
    )
    if not args.apply:
        print("dry run. Re-run with --apply to execute:")
        print(f"  {printable}")
        return EXIT_OK

    result = subprocess.run(command, capture_output=True, text=True, check=False)
    if result.returncode != 0:
        print(result.stdout.strip() or result.stderr.strip(), file=sys.stderr)
        return result.returncode
    action = "removed" if args.remove else "installed"
    print(f"{action} logon task {TASK_NAME!r}")
    return EXIT_OK

def cmd_install(args: argparse.Namespace) -> int:
    """Copy the running program into a stable folder and register it."""
    try:
        paths = install(
            target=getattr(args, "target", None),
            per_user=bool(getattr(args, "per_user", False)),
            launch=bool(getattr(args, "launch", False)),
        )
    except InstallError as exc:
        print(str(exc), file=sys.stderr)
        return 1
    print(f"installed to {paths.target}")
    print(f"shortcuts: {SHORTCUT_NAME} on the desktop and in the Start Menu")
    print(f"data:      {appdata_root()}")
    return EXIT_OK


def cmd_uninstall(args: argparse.Namespace) -> int:
    """Remove an installed copy and its shortcuts."""
    if not getattr(args, "yes", False):
        target = Path(getattr(args, "installed", None)).resolve() if getattr(args, "installed", None) else source_folder()
        print(f"this removes {target}")
        answer = input("continue? [y/N] ").strip().casefold()
        if answer not in ("y", "yes"):
            print("cancelled")
            return EXIT_OK
    try:
        removed = uninstall(installed=getattr(args, "installed", None),
                            purge_data=bool(getattr(args, "purge_data", False)))
    except InstallError as exc:
        print(str(exc), file=sys.stderr)
        return 1
    print(f"removed {removed}")
    return EXIT_OK


def launch_image_name(config, logger=None) -> tuple[str | None, str]:
    """The executable to impersonate, resolved the way the multi-game flow resolves it.

    Discord lists several executables per game and the first is often not the game —
    a launcher, a VR build, an installer. Taking ``catalogue[0]`` could therefore name
    a file Discord would never match: the presence looked right while no quest was
    credited. The installed-game check is what makes the choice real.
    """
    from ..decoy import executable_name_for
    from .. import steamlib

    names = []
    try:
        candidate = executable_name_for(config.client_id, logger=logger)
    except Exception:  # noqa: BLE001 - a catalogue failure must not block launch
        candidate = None
    # executable_name_for returns the first name; all of them are needed to choose.
    try:
        index = DetectableIndex(logger=logger)
        entry = index.by_id(config.client_id)
        if entry is not None and entry.executables:
            names = [str(n) for n in entry.executables]
    except Exception:  # noqa: BLE001
        names = []
    if not names and candidate:
        names = [candidate]
    return steamlib.resolve_image_name(config.game_name, config.client_id, names, logger=logger)


def cmd_launch(args: argparse.Namespace) -> int:
    """Prepare the decoy executable and re-exec into window mode under that name."""
    from ..decoy import ensure_decoy, is_running_as, reexec, relaunch_argv
    from ..ui.window import run_with_window_supervised

    config = _load(args)
    logger = setup_logging(config.log_level, config.log_file, True)

    image_name, source = launch_image_name(config, logger=logger)
    if not image_name:
        raise ConfigError(
            f"the Discord catalogue has no executable listed for application id "
            f"{config.client_id}. `launch` needs the game's own app id. Run "
            f"`worthlesstask init --game \"{config.game_name}\" --force` first."
        )
    logger.info("game executable resolved",
                extra={"image": image_name, "source": source, "game": config.game_name})

    if is_running_as(image_name):
        logger.info("already running as the expected image", extra={"image": image_name})
        # The window owns a supervisor that clears on exit; only clear here if it did
        # not, otherwise a second IPC handshake gets throttled for nothing.
        exit_code, cleared = run_with_window_supervised(
            config, logger=logger,
            identity_refresher=_make_identity_refresher(config, _config_path(args), logger))
        if config.clear_on_exit and not cleared:
            _clear_best_effort(config, logger)
        return exit_code

    path = ensure_decoy(image_name, logger=logger, client_id=config.client_id)
    argv = relaunch_argv(path, _launch_config_path(args))
    package_root = Path(__file__).resolve().parents[2]
    logger.info(
        "re-launching as the game executable",
        extra={"image": image_name, "path": str(path), "game": config.game_name},
    )
    reexec(path, argv, package_root)
    return EXIT_OK  # unreachable: reexec replaces the process

COMMANDS = {
    "run": cmd_run,
    "launch": cmd_launch,
    "set": cmd_set,
    "clear": cmd_clear,
    "doctor": cmd_doctor,
    "show": cmd_show,
    "resolve": cmd_resolve,
    "init": cmd_init,
    "autostart": cmd_autostart,
    "add": cmd_add,
    "list": cmd_list,
    "play": cmd_play,
    "stop": cmd_stop,
    "queue": cmd_queue,
    "web": cmd_web,
    "presence": cmd_presence,
    "bootstrap": cmd_bootstrap,
    "install": cmd_install,
    "uninstall": cmd_uninstall,
}

def main(argv: Sequence[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)

    if args.command is None:
        parser.print_help()
        return 0

    handler = COMMANDS.get(args.command)
    if handler is None:  # pragma: no cover - argparse rejects unknown commands
        parser.error(f"unknown command {args.command!r}")
        return 2

    # presence needs one source of truth: a library entry or a config file.
    if args.command == "presence" and not args.slug and not getattr(args, "config", None):
        parser.error("presence requires --slug or --config")
        return 2

    try:
        return handler(args)
    except ConfigError as exc:
        print(f"configuration error: {exc}", file=sys.stderr)
        return 2
    except worthlesstaskError as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 1
    except KeyboardInterrupt:
        return 130
