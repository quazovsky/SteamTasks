"""Discord's ack echo must reveal rewrites, not only dropped keys.

``diff_dropped`` documented "dropped or rewrote" but only detected absent keys, so a
silently rewritten ``details``, ``state``, ``type`` or asset value went unreported.
That is the whole point of comparing the echo.
"""

from __future__ import annotations

import unittest

from worthlesstask.presence.builder import diff_dropped


class TestDroppedKeys(unittest.TestCase):
    def test_an_absent_field_is_dropped(self):
        sent = {"type": 0, "details": "ok"}
        self.assertIn("details", diff_dropped(sent, {"type": 0}))

    def test_an_identical_echo_reports_nothing(self):
        sent = {"type": 0, "details": "ok", "state": "playing"}
        self.assertEqual(diff_dropped(sent, dict(sent)), {})

    def test_no_echo_reports_nothing(self):
        self.assertEqual(diff_dropped({"type": 0}, None), {})
        self.assertEqual(diff_dropped({"type": 0}, "not a dict"), {})

    def test_instance_is_expected_to_vanish(self):
        """Discord strips `instance`; that is not a surprise worth reporting."""
        self.assertEqual(diff_dropped({"type": 0, "instance": True}, {"type": 0}), {})

    def test_a_whole_section_disappearing(self):
        sent = {"type": 0, "assets": {"large_image": "key", "large_text": "tip"}}
        dropped = diff_dropped(sent, {"type": 0})
        self.assertIn("assets", dropped)
        self.assertEqual(dropped["assets"][1], None)


class TestRewrittenValues(unittest.TestCase):
    """The behaviour the docstring promised and the code did not deliver."""

    def test_a_rewritten_details_is_reported(self):
        sent = {"type": 0, "details": "Surviving"}
        dropped = diff_dropped(sent, {"type": 0, "details": "Surviving "})
        self.assertIn("details", dropped)
        self.assertEqual(dropped["details"], ("Surviving", "Surviving "))

    def test_a_rewritten_state_is_reported(self):
        sent = {"type": 0, "state": "In game"}
        self.assertIn("state", diff_dropped(sent, {"type": 0, "state": "in-game"}))

    def test_a_rewritten_type_is_reported(self):
        sent = {"type": 0}
        dropped = diff_dropped(sent, {"type": 2})
        self.assertIn("type", dropped)
        self.assertEqual(dropped["type"], (0, 2))

    def test_a_rewritten_asset_value_is_reported(self):
        sent = {"type": 0, "assets": {"large_image": "mykey", "large_text": "tip"}}
        dropped = diff_dropped(sent, {"type": 0, "assets": {"large_image": "other",
                                                            "large_text": "tip"}})
        self.assertIn("assets.large_image", dropped)
        self.assertEqual(dropped["assets.large_image"], ("mykey", "other"))
        # The untouched sibling must not be reported.
        self.assertNotIn("assets.large_text", dropped)

    def test_a_dropped_asset_key_is_still_reported(self):
        sent = {"type": 0, "assets": {"large_image": "mykey"}}
        dropped = diff_dropped(sent, {"type": 0, "assets": {}})
        self.assertIn("assets.large_image", dropped)
        self.assertEqual(dropped["assets.large_image"][1], None)

    def test_nested_party_size_changes_are_reported(self):
        sent = {"type": 0, "party": {"size": [1, 4]}}
        dropped = diff_dropped(sent, {"type": 0, "party": {"size": [1, 5]}})
        self.assertIn("party.size", dropped)

    def test_booleans_compare_strictly(self):
        """1 and True must not be treated as equal — Discord is picky about type."""
        # `instance` is deliberately ignored, so exercise this on a normal field.
        sent = {"type": 0, "party": {"privacy": True}}
        self.assertIn("party.privacy", diff_dropped(sent, {"type": 0, "party": {"privacy": 1}}))

    def test_numbers_compare_by_value(self):
        self.assertEqual(diff_dropped({"type": 0}, {"type": 0.0}), {})
        self.assertIn("type", diff_dropped({"type": 0}, {"type": 2}))


class TestTimestampTolerance(unittest.TestCase):
    """Discord recomputes timestamps.start; small drift is not a rewrite."""

    def test_small_drift_is_ignored(self):
        sent = {"type": 0, "timestamps": {"start": 1_700_000_000_000}}
        echoed = {"type": 0, "timestamps": {"start": 1_700_000_001_000}}
        self.assertEqual(diff_dropped(sent, echoed), {})

    def test_a_large_jump_is_reported(self):
        sent = {"type": 0, "timestamps": {"start": 1_700_000_000_000}}
        echoed = {"type": 0, "timestamps": {"start": 1_600_000_000_000}}
        dropped = diff_dropped(sent, echoed)
        self.assertIn("timestamps.start", dropped)

    def test_a_missing_timestamp_is_reported(self):
        sent = {"type": 0, "timestamps": {"start": 1_700_000_000_000}}
        self.assertIn("timestamps.start", diff_dropped(sent, {"type": 0, "timestamps": {}}))


class TestVersionCoherence(unittest.TestCase):
    """One version, reported consistently."""

    def test_health_reports_the_package_version(self):
        from worthlesstask import __version__
        from worthlesstask.web.server import APP_VERSION

        self.assertEqual(APP_VERSION, __version__)

    def test_the_server_header_uses_it_too(self):
        from worthlesstask import __version__
        from worthlesstask.web.server import Handler

        self.assertEqual(Handler.server_version, f"worthlesstask/{__version__}")

    def test_the_cli_reports_the_same_version(self):
        from worthlesstask import __version__
        from worthlesstask.cli.app import build_parser

        self.assertEqual(build_parser().prog, "worthlesstask")
        self.assertRegex(__version__, r"^\d+\.\d+")


if __name__ == "__main__":
    unittest.main(verbosity=2)
