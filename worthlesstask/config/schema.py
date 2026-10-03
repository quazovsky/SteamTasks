"""Configuration: defaults -> file -> environment -> CLI overrides, then validate.

Validation runs at startup, so a malformed ``client_id`` fails immediately instead
of surfacing as a Discord close code 4000 on the first connect.
"""

from __future__ import annotations

import json
import os
from dataclasses import asdict, dataclass, field
from pathlib import Path
from typing import Any, Mapping

from ..core.atomic import write_atomic
from ..core.backoff import BackoffPolicy
from ..core.errors import ConfigError, ValidationError
from ..presence.builder import ACTIVITY_TYPE_CODES, validate_buttons

DEFAULT_CONFIG_NAME = "config.json"
ENV_PREFIX = "WORTHLESSTASK_"

#: Search order when ``--config`` is not given.
SEARCH_PATHS = (
    Path.cwd() / DEFAULT_CONFIG_NAME,
    Path.cwd() / "worthlesstask.json",
    Path.home() / ".worthlesstask" / DEFAULT_CONFIG_NAME,
)

#: Below this, the periodic refresh would be indistinguishable from a reconnect storm.
MIN_REFRESH_INTERVAL = 5.0

@dataclass
class AppConfig:
    """Everything the supervisor needs to hold one presence."""

    client_id: str
    game_name: str
    activity_type: str = "playing"

    details: str | None = None
    state: str | None = None
    show_elapsed: bool = True

    large_image: str | None = None
    large_text: str | None = None
    small_image: str | None = None
    small_text: str | None = None

    buttons: list[dict[str, str]] = field(default_factory=list)
    party_size: list[int] | None = None
    party_id: str | None = None

    refresh_interval: float = 60.0
    command_timeout: float = 15.0
    handshake_timeout: float = 20.0
    clear_on_exit: bool = True

    log_level: str = "INFO"
    log_file: str | None = "worthlesstask.log"
    ipc_path: str | None = None

    backoff: BackoffPolicy = field(default_factory=BackoffPolicy)

    # Validation
    def validate(self) -> None:
        # The application id is optional: when it is absent it is derived from
        # game_name against Discord's catalogue before the first connection.
        cid = str(self.client_id or "").strip()
        if cid:
            if not cid.isdigit():
                raise ValidationError(
                    "client_id",
                    f"{cid!r} is not a numeric snowflake. Leave it empty to look the game up "
                    "by name, or copy the Application ID from the Discord Developer Portal.",
                )
            if len(cid) < 17:
                raise ValidationError(
                    "client_id",
                    f"{cid!r} is only {len(cid)} digits; Discord application ids are 17-19 digits. "
                    "Did you paste a public key or a secret instead?",
                )

        if not str(self.game_name or "").strip():
            raise ValidationError("game_name", "is required")

        if str(self.activity_type).lower() not in ACTIVITY_TYPE_CODES:
            raise ValidationError(
                "activity_type",
                f"must be one of {', '.join(sorted(ACTIVITY_TYPE_CODES))}",
            )

        validate_buttons(self.buttons)

        if self.party_size is not None:
            if not isinstance(self.party_size, list) or len(self.party_size) != 2:
                raise ValidationError("party_size", "must be a two-element array, e.g. [1, 4]")
            if not all(isinstance(v, int) for v in self.party_size):
                raise ValidationError("party_size", "both elements must be integers")

        if self.refresh_interval < MIN_REFRESH_INTERVAL:
            raise ValidationError(
                "refresh_interval",
                f"must be >= {MIN_REFRESH_INTERVAL:g}s to avoid hammering the IPC socket",
            )
        if self.command_timeout <= 0:
            raise ValidationError("command_timeout", "must be > 0")
        if self.handshake_timeout <= 0:
            raise ValidationError("handshake_timeout", "must be > 0")

    # Serialisation
    def to_dict(self) -> dict[str, Any]:
        data = asdict(self)
        data["backoff"] = self.backoff.to_dict()
        return data

    def to_json(self) -> str:
        return json.dumps(self.to_dict(), indent=2, ensure_ascii=False)

    def masked(self) -> dict[str, Any]:
        """Config view safe to print: the client id is not a secret, but keep it short."""
        data = self.to_dict()
        data["client_id"] = f"{self.client_id[:6]}...{self.client_id[-4:]}" if self.client_id else ""
        return data

# Loading
_KNOWN_FIELDS = set(AppConfig.__dataclass_fields__)

def _coerce(name: str, value: Any) -> Any:
    """Turn CLI strings / env strings into the field's real type."""
    if value is None:
        return None
    target = AppConfig.__dataclass_fields__[name].type
    text = str(target)
    if name == "backoff":
        return value
    if "bool" in text:
        if isinstance(value, bool):
            return value
        return str(value).strip().lower() in ("1", "true", "yes", "on")
    if "float" in text:
        return float(value)
    if "int" in text:
        return int(value)
    if "list" in text and isinstance(value, str):
        parsed = json.loads(value)
        return parsed
    return value

def _from_mapping(mapping: Mapping[str, Any], source: str) -> dict[str, Any]:
    unknown = sorted(set(mapping) - _KNOWN_FIELDS)
    if unknown:
        raise ConfigError(
            f"{source}: unknown field(s) {', '.join(unknown)}. "
            f"Known fields: {', '.join(sorted(_KNOWN_FIELDS))}"
        )
    values: dict[str, Any] = {}
    for key, value in mapping.items():
        if key == "backoff":
            values[key] = BackoffPolicy.from_dict(value)
        else:
            values[key] = value
    return values

def _from_env(environ: Mapping[str, str]) -> dict[str, Any]:
    values: dict[str, Any] = {}
    for key, raw in environ.items():
        if not key.startswith(ENV_PREFIX):
            continue
        field_name = key[len(ENV_PREFIX) :].lower()
        if field_name not in _KNOWN_FIELDS:
            continue
        if field_name == "backoff":
            continue
        try:
            values[field_name] = _coerce(field_name, raw)
        except (ValueError, json.JSONDecodeError) as exc:
            raise ConfigError(f"{key}={raw!r} is not a valid value for {field_name}: {exc}") from exc
    return values

def find_config_file(explicit: str | Path | None = None) -> Path | None:
    if explicit:
        path = Path(explicit).expanduser()
        if not path.exists():
            raise ConfigError(f"config file not found: {path}")
        return path
    for candidate in SEARCH_PATHS:
        if candidate.exists():
            return candidate
    return None

def load_config(
    path: str | Path | None = None,
    overrides: Mapping[str, Any] | None = None,
    environ: Mapping[str, str] | None = None,
    require_file: bool = False,
) -> AppConfig:
    """Build a validated :class:`AppConfig`.

    Precedence, lowest first: dataclass defaults, config file, environment,
    explicit ``overrides``.
    """
    environ = os.environ if environ is None else environ
    merged: dict[str, Any] = {}

    config_path = find_config_file(path)
    if config_path is None:
        if require_file:
            raise ConfigError(
                "no config file found. Looked in: "
                + ", ".join(str(p) for p in SEARCH_PATHS)
                + f". Run `worthlesstask init` to create one, or pass --config."
            )
    else:
        try:
            raw = json.loads(config_path.read_text(encoding="utf-8"))
        except json.JSONDecodeError as exc:
            raise ConfigError(f"{config_path}: invalid JSON: {exc}") from exc
        except OSError as exc:
            raise ConfigError(f"{config_path}: cannot read: {exc}") from exc
        if not isinstance(raw, dict):
            raise ConfigError(f"{config_path}: top level must be a JSON object")
        merged.update(_from_mapping(raw, str(config_path)))

    merged.update(_from_env(environ))

    if overrides:
        clean = {k: v for k, v in overrides.items() if v is not None}
        merged.update(_from_mapping(clean, "command line"))

    try:
        config = AppConfig(**merged)
    except TypeError as exc:
        raise ConfigError(f"cannot build config: {exc}") from exc

    config.validate()
    return config

def save_config(config: AppConfig, path: str | Path) -> Path:
    target = Path(path).expanduser()
    # Atomic: the config is read by workers at startup. A half-written file there
    # takes the whole presence down with a parse error.
    write_atomic(target, config.to_json())
    return target

EXAMPLE = AppConfig(
    client_id="000000000000000000",
    game_name="The Forest",
    details="Surviving",
    state="In game",
    large_text="The Forest",
    refresh_interval=60.0,
)
