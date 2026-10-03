"""Presence construction and application resolution."""

from .builder import (
    ACTIVITY_TYPE_CODES,
    BUTTONS_MAX,
    BUTTON_LABEL_MAX_LENGTH,
    TEXT_MAX_LENGTH,
    TEXT_MIN_LENGTH,
    build_activity,
    diff_dropped,
    resolve_activity_type,
    validate_activity,
    validate_buttons,
)
from .identity import DEFAULT_MIN_SCORE, Identity, IdentityResolver
from .resolver import (
    DETECTABLE_URL,
    ENDPOINT_CANDIDATES,
    Candidate,
    DetectableIndex,
    executable_name,
    executables_of,
    is_valid_entry,
    normalize,
    score_entry,
    search_offline,
)

__all__ = [
    "ACTIVITY_TYPE_CODES",
    "BUTTONS_MAX",
    "BUTTON_LABEL_MAX_LENGTH",
    "DEFAULT_MIN_SCORE",
    "DETECTABLE_URL",
    "ENDPOINT_CANDIDATES",
    "TEXT_MAX_LENGTH",
    "TEXT_MIN_LENGTH",
    "Candidate",
    "DetectableIndex",
    "Identity",
    "IdentityResolver",
    "build_activity",
    "diff_dropped",
    "executable_name",
    "executables_of",
    "is_valid_entry",
    "normalize",
    "resolve_activity_type",
    "score_entry",
    "search_offline",
    "validate_activity",
    "validate_buttons",
]
