"""Concurrent library edits, CLI validation, and scheduler resilience.

These cover the remaining audit items: disjoint edits to one game surviving each
other, backoff/party/queue flags behaving independently and predictably, and the
queue scheduler recording a failure instead of dying silently.
"""

from __future__ import annotations

import argparse
import io
import tempfile
import threading
import unittest
from contextlib import redirect_stderr, redirect_stdout
from pathlib import Path
from unittest import mock

from worthlesstask.core.errors import ConfigError, worthlesstaskError
from worthlesstask.library import Library


def _args(**kwargs):
    base = dict(config=None, log_level=None, log_file=None, json=False, window=False)
    base.update(kwargs)
    return argparse.Namespace(**base)


class TestConcurrentEditsSurvive(unittest.TestCase):
    """Two processes editing different fields of one game must both persist."""

    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        self.root = Path(self._tmp.name)
        self.path = self.root / "library.json"

    def tearDown(self):
        self._tmp.cleanup()

    def library(self) -> Library:
        return Library(path=self.path, icons_dir=self.root / "icons")

    def test_disjoint_field_edits_both_survive(self):
        first = self.library()
        first.add("The Forest", "363409179668512788", executable="theforestvr.exe")

        # A second process: the dashboard changing the rotation length.
        second = self.library()
        second.update("the-forest", minutes=45)

        # Meanwhile the first process refreshes the application id from an older view.
        first.update("the-forest", application_id="999999999999999999")

        third = self.library()
        entry = third.get("the-forest")
        self.assertEqual(entry.application_id, "999999999999999999")
        self.assertEqual(entry.minutes, 45, "the dashboard's change must not be lost")

    def test_only_changed_fields_are_written(self):
        library = self.library()
        library.add("The Forest", "363409179668512788", executable="theforestvr.exe")

        other = self.library()
        other.update("the-forest", minutes=45)

        # This instance has never touched `minutes`; saving must not reset it.
        library.update("the-forest", application_id="111111111111111111")
        self.assertEqual(self.library().get("the-forest").minutes, 45)

    def test_a_new_entry_is_written_in_full(self):
        library = self.library()
        library.add("PEAK", "1384276457596911676", executable="peak.exe")
        reloaded = self.library().get("peak")
        self.assertEqual(reloaded.game_name, "PEAK")
        self.assertEqual(reloaded.executable, "peak.exe")

    def test_bookkeeping_does_not_reach_the_api_or_disk(self):
        library = self.library()
        library.add("PEAK", "1384276457596911676", executable="peak.exe")
        entry = library.get("peak")

        self.assertNotIn("_touched", entry.to_dict())
        import json

        on_disk = json.loads(self.path.read_text(encoding="utf-8"))
        self.assertNotIn("_touched", on_disk["games"][0])


class TestCliValidation(unittest.TestCase):
    def test_party_with_non_numeric_values_raises_config_error(self):
        from worthlesstask.cli.app import _parse_party

        with self.assertRaises(ConfigError):
            _parse_party("nope|x")
        with self.assertRaises(ConfigError):
            _parse_party("1|")

    def test_party_accepts_whitespace(self):
        from worthlesstask.cli.app import _parse_party

        self.assertEqual(_parse_party(" 1 | 4 "), [1, 4])

    def test_backoff_base_alone_is_applied(self):
        from worthlesstask.cli.app import _backoff_override

        args = argparse.Namespace(max_attempts=None, backoff_base=5.0, backoff_max=None)
        policy = _backoff_override(args)
        self.assertEqual(policy.base_delay, 5.0)
        self.assertIsNone(policy.max_attempts)

    def test_backoff_override_keeps_the_existing_factor_and_jitter(self):
        """Rebuilding from defaults used to discard the configured curve."""
        from worthlesstask.cli.app import _backoff_override
        from worthlesstask.core.backoff import BackoffPolicy

        base = BackoffPolicy(base_delay=1.0, factor=3.0, max_delay=60.0, jitter=0.5,
                             max_attempts=7)
        args = argparse.Namespace(max_attempts=None, backoff_base=2.0, backoff_max=None)
        policy = _backoff_override(args, base_backoff=base)

        self.assertEqual(policy.base_delay, 2.0)   # changed
        self.assertEqual(policy.factor, 3.0)       # preserved
        self.assertEqual(policy.jitter, 0.5)       # preserved
        self.assertEqual(policy.max_attempts, 7)   # preserved

    def test_no_backoff_flags_means_no_override(self):
        from worthlesstask.cli.app import _overrides

        args = argparse.Namespace(button=None, party=None, no_elapsed=False,
                                  keep_on_exit=False, max_attempts=None,
                                  backoff_base=None, backoff_max=None)
        self.assertNotIn("backoff", _overrides(args))


class TestQueueMinutesValidation(unittest.TestCase):
    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        self.root = Path(self._tmp.name)
        self.addCleanup(self._tmp.cleanup)
        from worthlesstask.library import Library

        self.library = Library(path=self.root / "library.json", icons_dir=self.root / "icons")
        self.library.add("The Forest", "363409179668512788", executable="theforestvr.exe")
        (self.root / "theforestvr.exe").write_bytes(b"MZ" + b"\0" * 64)

    def _run(self, minutes):
        from worthlesstask.cli.multi import cmd_queue

        args = argparse.Namespace(library=str(self.root / "library.json"),
                                  icons=str(self.root / "icons"),
                                  slugs=["the-forest"], minutes=minutes, start=False)
        out = io.StringIO()
        with redirect_stdout(out), redirect_stderr(out):
            return cmd_queue(args), out.getvalue()

    def test_a_negative_duration_is_rejected(self):
        code, printed = self._run(-5)
        self.assertEqual(code, 2)
        self.assertIn("minutes", printed.lower())
        self.assertIsNone(self.library.get("the-forest").minutes)

    def test_zero_is_rejected(self):
        code, _ = self._run(0)
        self.assertEqual(code, 2)

    def test_an_out_of_range_duration_is_rejected(self):
        code, _ = self._run(10_000)
        self.assertEqual(code, 2)

    def test_a_valid_duration_is_accepted(self):
        code, _ = self._run(45)
        self.assertEqual(code, 0)
        # Re-read: cmd_queue works from its own Library instance.
        from worthlesstask.library import Library

        saved = Library(path=self.root / "library.json", icons_dir=self.root / "icons")
        self.assertEqual(saved.get("the-forest").minutes, 45)


class TestSchedulerResilience(unittest.TestCase):
    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        self.root = Path(self._tmp.name)
        self.addCleanup(self._tmp.cleanup)
        from worthlesstask.library import Library

        self.library = Library(path=self.root / "library.json", icons_dir=self.root / "icons")
        self.library.add("The Forest", "363409179668512788", executable="theforestvr.exe")
        (self.root / "theforestvr.exe").write_bytes(b"MZ" + b"\0" * 64)

    def manager(self):
        from worthlesstask.manager import PresenceManager

        return PresenceManager(library=self.library, package_root=self.root,
                               spawn=lambda *a, **k: mock.Mock(pid=1, poll=lambda: None),
                               runtime_path=self.root / "runtime.json")

    def test_an_expected_failure_stops_the_scheduler_and_records_it(self):
        from worthlesstask.manager import ManagerError

        manager = self.manager()
        stop = threading.Event()
        with mock.patch.object(manager, "tick",
                               side_effect=ManagerError("Некорректный идентификатор игры")):
            manager.run_scheduler(stop)
        self.assertTrue(stop.is_set())
        self.assertEqual(manager._last_error, "Некорректный идентификатор игры")

    def test_an_unexpected_failure_is_recorded_not_raised(self):
        """A crash here used to kill the thread and leave the UI claiming it ran."""
        manager = self.manager()
        stop = threading.Event()
        with mock.patch.object(manager, "tick", side_effect=RuntimeError("boom")):
            manager.run_scheduler(stop)  # must not raise
        self.assertTrue(stop.is_set())
        self.assertIn("boom", manager._last_error)
        self.assertIn("RuntimeError", manager._last_error)

    def test_a_stop_requested_upfront_does_no_work(self):
        manager = self.manager()
        stop = threading.Event()
        stop.set()
        with mock.patch.object(manager, "tick") as tick:
            manager.run_scheduler(stop)
        tick.assert_not_called()


if __name__ == "__main__":
    unittest.main(verbosity=2)
