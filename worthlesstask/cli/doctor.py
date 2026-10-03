"""Environment diagnostics. Run this first when the presence does not appear."""

from __future__ import annotations

import json
import os
import platform
import sys
from dataclasses import dataclass
from typing import Any

from ..config.schema import AppConfig, find_config_file
from ..core.errors import IpcUnavailableError, ResolverError, worthlesstaskError
from ..presence.builder import build_activity
from ..presence.resolver import DETECTABLE_URL, DetectableIndex
from ..rpc.transport import candidate_paths, connect_any, is_discord_running
from ..ui.inspect import find_windows_titled, process_name

OK = "OK"
WARN = "WARN"
FAIL = "FAIL"


@dataclass
class Check:
    name: str
    status: str
    detail: str

    def to_dict(self) -> dict[str, str]:
        return {"check": self.name, "status": self.status, "detail": self.detail}


def _endpoint_check() -> tuple[Check, str | None]:
    paths = candidate_paths()
    try:
        transport = connect_any(timeout=2.0)
    except IpcUnavailableError as exc:
        return (
            Check(
                "discord_ipc",
                FAIL,
                f"no endpoint accepted a connection ({len(exc.tried)} tried). "
                "Start the Discord desktop client and log in.",
            ),
            None,
        )
    name = transport.describe()
    transport.close()
    return (
        Check("discord_ipc", OK, f"connected to {name} (of {len(paths)} candidate endpoint(s))"),
        name,
    )


def _window_check(config: AppConfig | None) -> Check:
    """What Discord's game detector would see for our process.

    Discord matches on the executable name *and* inspects top-level windows, so a
    presence reported by a windowless process is not credited.
    """
    if config is None:
        return Check("presence_window", WARN, "no config, cannot match a window against a game")

    expected_exe: str | None = None
    try:
        candidate = DetectableIndex().by_id(config.client_id)
        if candidate and candidate.executables:
            expected_exe = candidate.executables[0].replace("\\", "/").rsplit("/", 1)[-1]
    except worthlesstaskError:
        expected_exe = None

    windows = find_windows_titled(config.game_name)
    if not windows:
        return Check(
            "presence_window",
            WARN,
            f"no visible window titled {config.game_name!r}. Discord inspects top-level "
            "windows, so start with `run --window` to give the detector something to match.",
        )

    for window in windows:
        image = process_name(window.pid)
        if expected_exe and image and image.casefold() == expected_exe.casefold():
            return Check(
                "presence_window",
                OK,
                f"hwnd {window.hwnd} pid {window.pid} image {image} title {window.title!r}",
            )

    first = windows[0]
    return Check(
        "presence_window",
        WARN,
        f"window {first.title!r} is owned by {process_name(first.pid)!r}, "
        f"expected image {expected_exe!r}",
    )


def run_doctor(config: AppConfig | None = None, config_error: str | None = None, as_json: bool = False) -> int:
    checks: list[Check] = []

    checks.append(
        Check(
            "platform",
            OK if os.name == "nt" else WARN,
            f"{platform.system()} {platform.release()} · python {sys.version.split()[0]}",
        )
    )

    endpoint, endpoint_name = _endpoint_check()
    checks.append(endpoint)
    checks.append(
        Check(
            "discord_process",
            OK if is_discord_running() else FAIL,
            "IPC socket is live" if is_discord_running() else "no Discord IPC socket found",
        )
    )

    config_file = None
    try:
        config_file = find_config_file(None)
    except worthlesstaskError:
        config_file = None
    if config_error:
        checks.append(Check("config", FAIL, config_error))
    elif config is None:
        checks.append(
            Check(
                "config",
                WARN,
                "no config file found. Run `worthlesstask init --game \"<name>\"` "
                "(environment variables can supply values too)",
            )
        )
    else:
        checks.append(
            Check(
                "config",
                OK,
                f"{config_file or '<environment>'} · game={config.game_name!r} "
                f"app_id={config.client_id} type={config.activity_type}",
            )
        )

    if config is not None:
        try:
            activity = build_activity(
                game_name=config.game_name,
                activity_type=config.activity_type,
                details=config.details,
                state=config.state,
                started_at=0.0 if config.show_elapsed else None,
                large_image=config.large_image,
                large_text=config.large_text,
                small_image=config.small_image,
                small_text=config.small_text,
                buttons=config.buttons,
                party_size=config.party_size,
                party_id=config.party_id,
            )
            checks.append(Check("activity_payload", OK, json.dumps(activity, ensure_ascii=False)[:160]))
        except worthlesstaskError as exc:
            checks.append(Check("activity_payload", FAIL, str(exc)))

    try:
        index = DetectableIndex()
        entries = index.entries()
        checks.append(
            Check("detectable_catalogue", OK, f"{len(entries)} applications from {DETECTABLE_URL}")
        )
    except ResolverError as exc:
        checks.append(Check("detectable_catalogue", WARN, f"{exc} (only needed for `resolve`/`init`)"))

    checks.append(_window_check(config))

    failures = sum(1 for c in checks if c.status == FAIL)
    warnings = sum(1 for c in checks if c.status == WARN)

    if as_json:
        print(json.dumps({"checks": [c.to_dict() for c in checks], "failures": failures}, indent=2))
    else:
        print(f"worthlesstask doctor — {platform.system()} {platform.release()}\n")
        for check in checks:
            print(f"  [{check.status:<4}] {check.name:<22} {check.detail}")
        print()
        if endpoint_name:
            print(f"  transport: {endpoint_name}")
        print(f"  {failures} failure(s), {warnings} warning(s)")

    return 1 if failures else 0
