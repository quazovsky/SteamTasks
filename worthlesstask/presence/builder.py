"""Presence construction and validation.

Every constraint enforced here was observed from Discord's own validator on the
live IPC socket, not copied from documentation. The probe results:

===========================  ==============================================
field                        observed rule
===========================  ==============================================
``details``                  string, 2..128 characters
``state``                    string, <= 128 characters
``buttons``                  at most 2 items; ``label`` <= 32 chars;
                             ``url`` must be a parseable URL
``timestamps.start``         must be a *number* (ms); ISO strings are rejected
``type``                     one of ``[0, 2, 3, 5]``; streaming (1) is rejected
``party.size``               any integers accepted, even ``[0, 0]``
``assets.*_image``           must be an asset **key owned by the application**;
                             unknown keys and ``mp:`` URLs are silently dropped
``name``                     ignored for display; the shown name comes from
                             ``application_id``
===========================  ==============================================
"""

from __future__ import annotations

import time
from typing import Any, Iterable
from urllib.parse import urlparse

from ..core.errors import ValidationError

#: ``playing`` maps to 0. Discord rejects 1 (streaming) over RPC.
ACTIVITY_TYPE_CODES: dict[str, int] = {
    "playing": 0,
    "listening": 2,
    "watching": 3,
    "competing": 5,
}

TEXT_MIN_LENGTH = 2
TEXT_MAX_LENGTH = 128
BUTTONS_MAX = 2
BUTTON_LABEL_MAX_LENGTH = 32

#: Advisory only. Discord was not observed to enforce it.
BUTTON_URL_ADVISORY_MAX = 512


def resolve_activity_type(value: str | int) -> int:
    """Map ``"playing"``/``"watching"``/… or a raw code to Discord's int."""
    if isinstance(value, int):
        if value not in ACTIVITY_TYPE_CODES.values():
            raise ValidationError(
                "activity_type",
                f"code {value} is rejected by Discord; allowed: {sorted(ACTIVITY_TYPE_CODES.values())}",
            )
        return value
    key = str(value).strip().lower()
    if key not in ACTIVITY_TYPE_CODES:
        raise ValidationError(
            "activity_type",
            f"unknown type {value!r}; allowed: {', '.join(sorted(ACTIVITY_TYPE_CODES))}",
        )
    return ACTIVITY_TYPE_CODES[key]


def _validate_text(field: str, value: Any, *, required_min: int = TEXT_MIN_LENGTH) -> None:
    if not isinstance(value, str):
        raise ValidationError(field, f"must be a string, got {type(value).__name__}")
    if required_min and len(value) < required_min:
        raise ValidationError(field, f"must be at least {required_min} characters (Discord rejects shorter)")
    if len(value) > TEXT_MAX_LENGTH:
        raise ValidationError(field, f"must be at most {TEXT_MAX_LENGTH} characters, got {len(value)}")


def _validate_url(value: Any) -> None:
    if not isinstance(value, str) or not value:
        raise ValidationError("buttons.url", "must be a non-empty string")
    parsed = urlparse(value)
    if parsed.scheme not in ("http", "https") or not parsed.netloc:
        raise ValidationError("buttons.url", f"{value!r} is not a valid http(s) URL")
    if len(value) > BUTTON_URL_ADVISORY_MAX:
        raise ValidationError("buttons.url", f"longer than the advisory limit of {BUTTON_URL_ADVISORY_MAX}")


def validate_buttons(buttons: Iterable[dict[str, Any]]) -> None:
    buttons = list(buttons)
    if len(buttons) > BUTTONS_MAX:
        raise ValidationError("buttons", f"at most {BUTTONS_MAX} items, got {len(buttons)}")
    for index, button in enumerate(buttons):
        if not isinstance(button, dict):
            raise ValidationError("buttons", f"item {index} must be an object")
        label = button.get("label")
        if not isinstance(label, str) or not label:
            raise ValidationError("buttons", f"item {index} needs a non-empty 'label'")
        if len(label) > BUTTON_LABEL_MAX_LENGTH:
            raise ValidationError(
                "buttons",
                f"item {index} label is {len(label)} chars, max {BUTTON_LABEL_MAX_LENGTH}",
            )
        _validate_url(button.get("url"))


def build_activity(
    *,
    game_name: str,
    activity_type: str | int = "playing",
    details: str | None = None,
    state: str | None = None,
    started_at: float | None = None,
    large_image: str | None = None,
    large_text: str | None = None,
    small_image: str | None = None,
    small_text: str | None = None,
    buttons: Iterable[dict[str, Any]] | None = None,
    party_size: Iterable[int] | None = None,
    party_id: str | None = None,
    validate: bool = True,
) -> dict[str, Any]:
    """Assemble a SET_ACTIVITY payload body.

    ``game_name`` is sent for logging and for clients that still read it; the
    name Discord actually displays comes from the application id.
    """
    if not isinstance(game_name, str) or not game_name.strip():
        raise ValidationError("game_name", "must be a non-empty string")

    code = resolve_activity_type(activity_type)

    activity: dict[str, Any] = {"name": game_name, "type": code, "instance": False}

    if details is not None:
        activity["details"] = details
    if state is not None:
        activity["state"] = state

    if started_at is not None:
        activity["timestamps"] = {"start": int(started_at * 1000)}

    assets: dict[str, Any] = {}
    if large_image:
        assets["large_image"] = large_image
    if large_text:
        assets["large_text"] = large_text
    if small_image:
        assets["small_image"] = small_image
    if small_text:
        assets["small_text"] = small_text
    if assets:
        activity["assets"] = assets

    if buttons:
        activity["buttons"] = [{"label": b["label"], "url": b["url"]} for b in buttons]

    if party_size is not None:
        size = [int(v) for v in party_size]
        if len(size) != 2:
            raise ValidationError("party_size", "must contain exactly two integers")
        party: dict[str, Any] = {"size": size}
        if party_id:
            party["id"] = party_id
        activity["party"] = party

    if validate:
        validate_activity(activity)

    return activity


def validate_activity(activity: dict[str, Any]) -> None:
    """Raise :class:`ValidationError` for anything Discord will reject."""
    if not isinstance(activity, dict):
        raise ValidationError("activity", "must be an object")

    code = activity.get("type")
    if code not in ACTIVITY_TYPE_CODES.values():
        raise ValidationError(
            "activity.type",
            f"must be one of {sorted(ACTIVITY_TYPE_CODES.values())}, got {code!r}",
        )

    if "details" in activity:
        _validate_text("details", activity["details"])
    if "state" in activity:
        _validate_text("state", activity["state"])

    timestamps = activity.get("timestamps")
    if timestamps is not None:
        if not isinstance(timestamps, dict):
            raise ValidationError("timestamps", "must be an object")
        for key in ("start", "end"):
            if key in timestamps and not isinstance(timestamps[key], (int, float)):
                raise ValidationError(
                    f"timestamps.{key}",
                    "must be a number (unix milliseconds); ISO strings are rejected by Discord",
                )

    if "buttons" in activity:
        validate_buttons(activity["buttons"])

    assets = activity.get("assets")
    if assets is not None:
        if not isinstance(assets, dict):
            raise ValidationError("assets", "must be an object")
        for key in ("large_image", "small_image"):
            if key in assets and not isinstance(assets[key], str):
                raise ValidationError(f"assets.{key}", "must be a string")
        for key in ("large_text", "small_text"):
            if key in assets and not isinstance(assets[key], str):
                raise ValidationError(f"assets.{key}", "must be a string")

    party = activity.get("party")
    if party is not None:
        if not isinstance(party, dict):
            raise ValidationError("party", "must be an object")
        size = party.get("size")
        if size is not None:
            if not isinstance(size, (list, tuple)) or len(size) != 2:
                raise ValidationError("party.size", "must be a two-element array")
            for value in size:
                if not isinstance(value, int):
                    raise ValidationError("party.size", "both elements must be integers")


#: Discord recomputes ``timestamps.start`` when it stores an activity (it keeps the
#: elapsed origin but rewrites the value), so a few seconds of drift is expected and
#: must not be reported as a rewrite.
TIMESTAMP_TOLERANCE_S = 5.0

#: Fields Discord is expected to strip or own; their absence is not a surprise.
IGNORED_ECHO_KEYS = frozenset({"instance"})


def _values_differ(sent: Any, echoed: Any) -> bool:
    if isinstance(sent, bool) or isinstance(echoed, bool):
        return sent is not echoed
    if isinstance(sent, (int, float)) and isinstance(echoed, (int, float)):
        return abs(float(sent) - float(echoed)) > 1e-9
    return sent != echoed


def _diff(prefix: str, sent: Any, echoed: Any, out: dict[str, tuple[Any, Any]]) -> None:
    if prefix.split(".")[-1] == "start" and isinstance(sent, (int, float)) \
            and isinstance(echoed, (int, float)):
        # Timestamp drift is expected; only a large jump means it was rewritten.
        if abs(float(sent) - float(echoed)) > TIMESTAMP_TOLERANCE_S * 1000:
            out[prefix] = (sent, echoed)
        return
    if isinstance(sent, dict):
        if not isinstance(echoed, dict):
            out[prefix] = (sent, echoed)
            return
        for key, value in sent.items():
            child = f"{prefix}.{key}" if prefix else str(key)
            if key not in echoed:
                out[child] = (value, None)
            else:
                _diff(child, value, echoed[key], out)
        return
    if _values_differ(sent, echoed):
        out[prefix] = (sent, echoed)


def diff_dropped(
    sent: dict[str, Any], echoed: dict[str, Any] | None
) -> dict[str, tuple[Any, Any]]:
    """Report fields Discord silently dropped **or rewrote**.

    Discord echoes the stored activity back in the ack, so comparing it with what
    was sent reveals both discarded fields — most often ``assets`` keys that do not
    belong to the application — and values it changed. The docstring used to claim
    "dropped or rewrote" while only absent keys were detected, so a rewritten
    ``details``, ``state`` or asset value passed silently.
    """
    if not isinstance(echoed, dict):
        return {}
    dropped: dict[str, tuple[Any, Any]] = {}
    for key, value in sent.items():
        if key in IGNORED_ECHO_KEYS:
            continue
        if key not in echoed:
            dropped[str(key)] = (value, None)
            continue
        _diff(str(key), value, echoed[key], dropped)
    return dropped


def elapsed_started_at(clock=time.time) -> float:
    return clock()
