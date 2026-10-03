"""The presence manager: one game at a time, switching, queue, adoption."""

from __future__ import annotations

import json
import sys
import tempfile
import unittest
from pathlib import Path
from unittest import mock

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from worthlesstask.library import Library
from worthlesstask.manager import (
    Instance, ManagerError, PidProcess, PresenceManager, reset_process_caches,
)


class FakeProcess:
    def __init__(self, pid: int) -> None:
        self.pid = pid
        self.exit_code: int | None = None
        self.terminated = False

    def poll(self):
        return self.exit_code

    def terminate(self):
        self.terminated = True
        self.exit_code = 0

    def kill(self):
        self.terminated = True
        self.exit_code = 0

    def wait(self, timeout=None):
        self.exit_code = 0
        return 0


class Recorder:
    """Captures spawn calls and hands out fake processes."""

    def __init__(self) -> None:
        self.calls: list[list[str]] = []
        self.processes: list[FakeProcess] = []
        self._next_pid = 1000

    def __call__(self, argv, env, cwd):
        self.calls.append(list(argv))
        process = FakeProcess(self._next_pid)
        self._next_pid += 1
        self.processes.append(process)
        return process

    @property
    def last_argv(self) -> list[str]:
        return self.calls[-1]


class ManagerTestCase(unittest.TestCase):
    def setUp(self):
        # Process and window lookups are memoised for one poll interval. Tests must
        # start from empty caches, or a value from the previous test is reused.
        reset_process_caches()
        self.addCleanup(reset_process_caches)
        self._tmp = tempfile.TemporaryDirectory()
        self.root = Path(self._tmp.name)
        self.library = Library(path=self.root / "library.json", icons_dir=self.root / "icons")
        self.library.add("ARKNIGHTS: ENDFIELD", "1461154307171811401", executable="endfield.exe")
        self.library.add("The Forest", "363409179668512788", executable="theforestvr.exe")
        self.recorder = Recorder()
        self.runtime = self.root / "runtime.json"
        for name in ("endfield.exe", "theforestvr.exe"):
            (self.root / name).write_bytes(b"MZ" + b"\0" * 64)
        self._patch = mock.patch(
            "worthlesstask.manager.ensure_decoy", side_effect=lambda name, logger=None, client_id=None: self.root / name
        )
        self._patch.start()
        identity_patch = mock.patch("worthlesstask.manager.process_identity", return_value="test-creation-time")
        identity_patch.start()
        self.addCleanup(identity_patch.stop)
        windows_patch = mock.patch("worthlesstask.ui.inspect.windows_for_pid", return_value=[])
        windows_patch.start()
        self.addCleanup(windows_patch.stop)

    def tearDown(self):
        self._patch.stop()
        self._tmp.cleanup()

    def manager(self) -> PresenceManager:
        return PresenceManager(
            self.library,
            package_root=self.root,
            spawn=self.recorder,
            runtime_path=self.runtime,
        )

    def wait_operation(self, manager, timeout: float = 3.0):
        """Wait until an accepted asynchronous operation has finished."""
        import threading
        import time

        deadline = time.monotonic() + timeout
        while time.monotonic() < deadline:
            state = manager.status()
            if not state["operation"]:
                return state
            threading.Event().wait(.005)
        self.fail("Process operation did not finish")


class TestPlayAndStop(ManagerTestCase):
    def test_play_spawns_the_game_executable(self):
        manager = self.manager()
        status = manager.play("arknights-endfield")
        self.assertEqual(status["active"]["slug"], "arknights-endfield")
        self.assertEqual(Path(self.recorder.last_argv[0]).name, "endfield.exe")
        self.assertIn("presence", self.recorder.last_argv)
        self.assertIn("arknights-endfield", self.recorder.last_argv)

    def test_play_unknown_slug(self):
        with self.assertRaises(ManagerError):
            self.manager().play("ghost")

    def test_play_without_executable_is_refused(self):
        self.library.add("No Exe", "1")
        with self.assertRaises(ManagerError) as ctx:
            self.manager().play("no-exe")
        self.assertIn("executable", str(ctx.exception))

    def test_switching_stops_the_previous_game(self):
        manager = self.manager()
        manager.play("arknights-endfield")
        first = self.recorder.processes[0]
        manager.play("the-forest")
        self.assertTrue(first.terminated)
        self.assertEqual(manager.active_slug, "the-forest")

    def test_playing_the_active_game_is_a_no_op(self):
        manager = self.manager()
        manager.play("arknights-endfield")
        manager.play("arknights-endfield")
        self.assertEqual(len(self.recorder.calls), 1)

    def test_stop_terminates_and_clears(self):
        manager = self.manager()
        manager.play("arknights-endfield")
        manager.stop()
        self.assertIsNone(manager.active_slug)
        self.assertTrue(self.recorder.processes[0].terminated)

    def test_stop_when_idle_is_harmless(self):
        manager = self.manager()
        self.assertIsNone(manager.stop()["active"])

    def test_dead_child_is_reaped(self):
        manager = self.manager()
        manager.play("arknights-endfield")
        self.recorder.processes[0].exit_code = 1
        self.assertIsNone(manager.active_slug)


class TestRuntimeState(ManagerTestCase):
    def test_runtime_file_written_and_removed(self):
        manager = self.manager()
        manager.play("arknights-endfield")
        payload = json.loads(self.runtime.read_text(encoding="utf-8"))
        self.assertEqual(payload["slug"], "arknights-endfield")
        manager.stop()
        self.assertFalse(self.runtime.exists())

    def test_a_later_process_adopts_the_running_presence(self):
        manager = self.manager()
        manager.play("arknights-endfield")
        pid = manager.status()["active"]["pid"]

        # A fresh manager in another process must see the same presence.
        with mock.patch.object(PidProcess, "poll", return_value=None), mock.patch(
            "worthlesstask.ui.inspect.process_image_path", return_value=str((self.root / "endfield.exe").resolve())
        ):
            second = PresenceManager(
                self.library, package_root=self.root, spawn=self.recorder, runtime_path=self.runtime
            )
            self.assertEqual(second.active_slug, "arknights-endfield")
            self.assertEqual(second.status()["active"]["pid"], pid)

    def test_stale_runtime_file_is_ignored(self):
        self.runtime.write_text(json.dumps({"slug": "arknights-endfield", "pid": 999999}), encoding="utf-8")
        with mock.patch.object(PidProcess, "poll", return_value=1):
            manager = PresenceManager(
                self.library, package_root=self.root, spawn=self.recorder, runtime_path=self.runtime
            )
        self.assertIsNone(manager.active_slug)
        # A legacy PID-only record is not authority to operate on a process.
        self.assertTrue(self.runtime.exists())

    def test_runtime_file_for_a_removed_game_is_ignored(self):
        self.runtime.write_text(json.dumps({"slug": "ghost", "pid": 1}), encoding="utf-8")
        manager = PresenceManager(
            self.library, package_root=self.root, spawn=self.recorder, runtime_path=self.runtime
        )
        self.assertIsNone(manager.active_slug)


class TestQueue(ManagerTestCase):
    def test_advance_moves_to_the_next_entry(self):
        manager = self.manager()
        manager.set_queue(["arknights-endfield", "the-forest"])
        manager.play("arknights-endfield")
        manager.advance()
        self.assertEqual(manager.active_slug, "the-forest")

    def test_advance_wraps_around(self):
        manager = self.manager()
        manager.set_queue(["arknights-endfield", "the-forest"])
        manager.play("the-forest")
        manager.advance()
        self.assertEqual(manager.active_slug, "arknights-endfield")

    def test_advance_without_a_queue_does_nothing(self):
        manager = self.manager()
        manager.play("arknights-endfield")
        self.assertIsNone(manager.advance())
        self.assertEqual(manager.active_slug, "arknights-endfield")

    def test_tick_switches_only_after_the_slot_elapses(self):
        manager = self.manager()
        manager.set_queue(["arknights-endfield", "the-forest"])
        manager.play("arknights-endfield")
        self.assertIsNone(manager.tick(), "must not switch while time remains")

        # Pretend the slot is over.
        manager._instance.started_at -= 16 * 60
        manager.tick()
        self.assertEqual(manager.active_slug, "the-forest")

    def test_seconds_until_switch(self):
        manager = self.manager()
        manager.set_queue(["arknights-endfield"])
        manager.play("arknights-endfield")
        remaining = manager.status()["next_switch_in_s"]
        self.assertIsNotNone(remaining)
        self.assertLessEqual(remaining, 15 * 60)
        self.assertGreater(remaining, 15 * 60 - 30)

    def test_no_countdown_without_a_queue(self):
        manager = self.manager()
        manager.play("arknights-endfield")
        self.assertIsNone(manager.status()["next_switch_in_s"])


class TestStatus(ManagerTestCase):
    def test_status_lists_the_library(self):
        status = self.manager().status()
        self.assertEqual(len(status["games"]), 2)
        self.assertIsNone(status["active"])

    def test_status_marks_the_active_game(self):
        manager = self.manager()
        manager.play("the-forest")
        status = manager.status()
        self.assertEqual(status["active"]["game_name"], "The Forest")
        self.assertIn("uptime_s", status["active"])


if __name__ == "__main__":
    unittest.main(verbosity=2)
