"""Activity builder tests.

The expected values encode the constraints observed on the live Discord IPC
socket (see the module docstring of ``worthlesstask.presence.builder``).
"""

from __future__ import annotations

import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from worthlesstask.core.errors import ValidationError
from worthlesstask.presence.builder import (
    ACTIVITY_TYPE_CODES,
    build_activity,
    diff_dropped,
    resolve_activity_type,
    validate_activity,
)


class TestActivityType(unittest.TestCase):
    def test_named_types(self):
        self.assertEqual(resolve_activity_type("playing"), 0)
        self.assertEqual(resolve_activity_type("listening"), 2)
        self.assertEqual(resolve_activity_type("watching"), 3)
        self.assertEqual(resolve_activity_type("competing"), 5)

    def test_streaming_is_not_offered(self):
        self.assertNotIn("streaming", ACTIVITY_TYPE_CODES)
        with self.assertRaises(ValidationError):
            resolve_activity_type("streaming")

    def test_raw_codes(self):
        self.assertEqual(resolve_activity_type(3), 3)
        with self.assertRaises(ValidationError):
            resolve_activity_type(1)
        with self.assertRaises(ValidationError):
            resolve_activity_type(9)


class TestBuildActivity(unittest.TestCase):
    def test_minimal(self):
        activity = build_activity(game_name="The Forest")
        self.assertEqual(activity["name"], "The Forest")
        self.assertEqual(activity["type"], 0)
        self.assertFalse(activity["instance"])

    def test_elapsed_timestamp_is_milliseconds(self):
        activity = build_activity(game_name="G", started_at=1_700_000_000.5)
        self.assertEqual(activity["timestamps"]["start"], 1_700_000_000_500)
        self.assertIsInstance(activity["timestamps"]["start"], int)

    def test_details_and_state_pass_through(self):
        activity = build_activity(game_name="G", details="Surviving", state="In game")
        self.assertEqual(activity["details"], "Surviving")
        self.assertEqual(activity["state"], "In game")

    def test_assets_are_nested(self):
        activity = build_activity(game_name="G", large_image="key", large_text="tip")
        self.assertEqual(activity["assets"], {"large_image": "key", "large_text": "tip"})

    def test_party_size(self):
        activity = build_activity(game_name="G", party_size=[1, 4], party_id="p")
        self.assertEqual(activity["party"], {"size": [1, 4], "id": "p"})

    def test_party_size_requires_two_elements(self):
        with self.assertRaises(ValidationError):
            build_activity(game_name="G", party_size=[1, 2, 3])

    def test_empty_game_name_is_rejected(self):
        for value in ("", "   ", None):
            with self.subTest(value=value), self.assertRaises(ValidationError):
                build_activity(game_name=value)  # type: ignore[arg-type]


class TestValidatedLimits(unittest.TestCase):
    """Boundaries as reported by Discord's own validator."""

    def test_details_minimum(self):
        with self.assertRaises(ValidationError):
            build_activity(game_name="G", details="x")
        build_activity(game_name="G", details="xx")

    def test_details_maximum(self):
        build_activity(game_name="G", details="x" * 128)
        with self.assertRaises(ValidationError):
            build_activity(game_name="G", details="x" * 129)

    def test_state_maximum(self):
        build_activity(game_name="G", state="x" * 128)
        with self.assertRaises(ValidationError):
            build_activity(game_name="G", state="y" * 129)

    def test_details_must_be_a_string(self):
        with self.assertRaises(ValidationError):
            build_activity(game_name="G", details=5)  # type: ignore[arg-type]

    def test_button_count(self):
        button = {"label": "a", "url": "https://example.com"}
        build_activity(game_name="G", buttons=[button, dict(button)])
        with self.assertRaises(ValidationError):
            build_activity(game_name="G", buttons=[button, dict(button), dict(button)])

    def test_button_label_boundary(self):
        build_activity(game_name="G", buttons=[{"label": "L" * 32, "url": "https://e.com"}])
        with self.assertRaises(ValidationError):
            build_activity(game_name="G", buttons=[{"label": "L" * 33, "url": "https://e.com"}])

    def test_button_url_must_parse(self):
        with self.assertRaises(ValidationError):
            build_activity(game_name="G", buttons=[{"label": "a", "url": "notaurl"}])

    def test_http_is_allowed(self):
        build_activity(game_name="G", buttons=[{"label": "a", "url": "http://example.com"}])

    def test_timestamp_must_be_numeric(self):
        with self.assertRaises(ValidationError):
            validate_activity({"type": 0, "timestamps": {"start": "2026-09-12T06:00:00Z"}})

    def test_invalid_type_code(self):
        with self.assertRaises(ValidationError):
            validate_activity({"type": 1})
        with self.assertRaises(ValidationError):
            validate_activity({"type": 9})


class TestDiffDropped(unittest.TestCase):
    def test_detects_stripped_assets(self):
        sent = {"type": 0, "details": "ok", "assets": {"large_image": "missing", "large_text": "t"}}
        echoed = {"type": 0, "details": "ok", "assets": {"large_text": "t"}}
        dropped = diff_dropped(sent, echoed)
        self.assertIn("assets.large_image", dropped)

    def test_no_diff_when_echo_matches(self):
        sent = {"type": 0, "details": "ok"}
        self.assertEqual(diff_dropped(sent, dict(sent)), {})

    def test_missing_key_is_reported(self):
        self.assertIn("details", diff_dropped({"type": 0, "details": "ok"}, {"type": 0}))

    def test_non_dict_echo_is_ignored(self):
        self.assertEqual(diff_dropped({"type": 0}, None), {})


if __name__ == "__main__":
    unittest.main(verbosity=2)
