"""Regression coverage for nonblocking control, exact argv and truthful RPC state."""
from __future__ import annotations

import json
import threading
import time
import unittest
from datetime import datetime, timezone
from pathlib import Path
from unittest import mock

from worthlesstask.manager import ManagerError
from tests.test_manager import ManagerTestCase


class TestLifecycleRegressions(ManagerTestCase):
    def test_state_reads_do_not_wait_for_slow_spawn_and_duplicate_is_ignored(self):
        entered, release = threading.Event(), threading.Event()
        original = self.recorder

        def slow_spawn(argv, env, cwd):
            entered.set()
            if not release.wait(3):
                raise RuntimeError("Test release timed out")
            return original(argv, env, cwd)

        manager = self.manager()
        manager._spawn = slow_spawn
        try:
            start = time.monotonic()
            manager.request_play("arknights-endfield")
            self.assertLess(time.monotonic() - start, .5)
            self.assertTrue(entered.wait(1))
            start = time.monotonic()
            snapshot = manager.status()
            self.assertLess(time.monotonic() - start, .2)
            self.assertEqual(snapshot["operation"]["kind"], "start")
            self.assertIsNone(snapshot["active"])
            manager.request_play("arknights-endfield")
            with self.assertRaises(ManagerError):
                manager.request_play("the-forest")
        finally:
            release.set()
            self.wait_operation(manager)
        self.assertEqual(len(original.calls), 1)
        self.assertEqual(manager.status()["active"]["rpc_state"], "connecting")

    def test_invalid_target_does_not_stop_current_game(self):
        manager = self.manager()
        manager.play("arknights-endfield")
        first = self.recorder.processes[0]
        self.library.update("the-forest", executable="../escape.exe")
        with self.assertRaises(ManagerError):
            manager.play("the-forest")
        self.assertFalse(first.terminated)
        self.assertEqual(manager.active_slug, "arknights-endfield")

    def test_missing_executable_does_not_stop_current_game(self):
        manager = self.manager()
        manager.play("arknights-endfield")
        (self.root / "theforestvr.exe").unlink()
        with self.assertRaises(ManagerError):
            manager.play("the-forest")
        self.assertFalse(self.recorder.processes[0].terminated)

    def test_non_executable_bytes_are_rejected(self):
        (self.root / "endfield.exe").write_text("not an executable", encoding="utf-8")
        with self.assertRaises(ManagerError):
            self.manager().play("arknights-endfield")
        self.assertEqual(self.recorder.calls, [])

    def test_cli_arguments_are_separate_absolute_values(self):
        manager = self.manager()
        manager.play("arknights-endfield")
        argv = self.recorder.last_argv
        self.assertEqual(argv[1:4], ["-m", "worthlesstask", "presence"])
        for flag in ("--library", "--icons", "--log-file"):
            value = argv[argv.index(flag)+1]
            self.assertTrue(Path(value).is_absolute(), value)
            self.assertFalse(value.startswith('"'))
        self.assertEqual(argv[argv.index("--slug")+1], "arknights-endfield")

    def test_frozen_child_has_no_python_module_flags(self):
        manager = self.manager()
        captured = {}
        original = manager._spawn
        def spawn(argv, env, cwd):
            captured.update(argv=argv, env=env)
            return original(argv, env, cwd)
        manager._spawn = spawn
        with mock.patch("worthlesstask.manager.sys.frozen", True, create=True):
            manager.play("arknights-endfield")
        self.assertEqual(captured["argv"][1], "--worker")
        self.assertNotIn("-m", captured["argv"])
        self.assertEqual(captured["env"]["PYINSTALLER_RESET_ENVIRONMENT"], "1")

    def test_failed_spawn_is_visible_after_accepted_request(self):
        manager = self.manager()
        manager._spawn = mock.Mock(side_effect=PermissionError("Access denied to executable"))
        manager.request_play("arknights-endfield")
        state = self.wait_operation(manager)
        self.assertIsNone(state["active"])
        self.assertIn("Access denied", state["last_error"])
        self.assertIsNone(state["operation"])

    def test_disconnected_and_stale_logs_do_not_claim_rpc_success(self):
        manager = self.manager()
        manager.play("arknights-endfield")
        instance = manager._instance
        log = self.root / "logs" / "arknights-endfield.log"
        def record(seconds, event, **fields):
            return json.dumps({"ts": datetime.fromtimestamp(seconds, timezone.utc).isoformat(),
                               "event": event, "level": "INFO", **fields}) + "\n"
        log.write_text(record(instance.started_at-10, "presence set"), encoding="utf-8")
        self.assertEqual(manager.status()["active"]["rpc_state"], "connecting")
        with log.open("a", encoding="utf-8") as stream:
            stream.write(record(instance.started_at+1, "presence set"))
        self.assertEqual(manager.status()["active"]["rpc_state"], "connected")
        with log.open("a", encoding="utf-8") as stream:
            stream.write(record(instance.started_at+2, "connection lost", reason="test disconnect"))
        self.assertEqual(manager.status()["active"]["rpc_state"], "reconnecting")

    def test_early_exit_reports_failure_and_allows_retry(self):
        manager = self.manager()
        manager.play("arknights-endfield")
        self.recorder.processes[0].exit_code = 2
        (self.root / "logs" / "arknights-endfield.startup.log").write_text(
            "Unable to start worker", encoding="utf-8")
        state = manager.status()
        self.assertIsNone(state["active"])
        self.assertIn("2", state["last_error"])
        manager.play("arknights-endfield")
        self.assertEqual(len(self.recorder.calls), 2)

    def test_invalid_id_and_activity_are_rejected_before_spawning(self):
        for fields in ({"application_id": "oops"}, {"activity_type": "unknown"}):
            with self.subTest(fields=fields):
                self.library.update("the-forest", application_id="363409179668512788",
                                    activity_type="playing")
                self.library.update("the-forest", **fields)
                with self.assertRaises(ManagerError):
                    self.manager().play("the-forest")
        self.assertEqual(self.recorder.calls, [])

    def test_reused_pid_is_not_adopted(self):
        manager = self.manager()
        manager.play("arknights-endfield")
        with mock.patch("worthlesstask.manager.process_identity", return_value="different-time"):
            other = self.manager()
        self.assertIsNone(other.active_slug)


class TestPrepareOnAdd(ManagerTestCase):
    def test_prepare_marks_the_entry_ready(self):
        manager = self.manager()
        path = manager.prepare("arknights-endfield")
        self.assertEqual(path, self.root / "endfield.exe")
        entry = self.library.get("arknights-endfield")
        self.assertTrue(entry.worker_ready)
        self.assertIsNone(entry.worker_error)
        self.assertEqual(entry.worker_path, str(self.root / "endfield.exe"))

    def test_prepare_failure_is_recorded_not_raised_into_the_library(self):
        manager = self.manager()
        with mock.patch("worthlesstask.manager.ensure_decoy",
                        side_effect=ValueError("Файл уже существует и не принадлежит worthlesstask")):
            with self.assertRaises(ManagerError):
                manager.prepare("arknights-endfield")
        entry = self.library.get("arknights-endfield")
        self.assertFalse(entry.worker_ready)
        self.assertIn("не принадлежит", entry.worker_error)

    def test_prepare_rejects_a_game_without_an_executable(self):
        self.library.add("No Exe", "1456485028350656512")
        with self.assertRaises(ManagerError):
            self.manager().prepare("no-exe")

    def test_launch_marks_the_entry_ready(self):
        manager = self.manager()
        manager.play("arknights-endfield")
        self.assertTrue(self.library.get("arknights-endfield").worker_ready)

    def test_adding_a_game_creates_its_executable(self):
        from worthlesstask.web.server import Dashboard
        dashboard = Dashboard(self.library, self.manager(), resolver=mock.Mock())
        dashboard.resolver.resolve_by_name.return_value = mock.Mock(
            application_id="1384276457596911676",
            candidate=mock.Mock(executables=("peak.exe",), icon_url=None),
        )
        with mock.patch("worthlesstask.manager.ensure_decoy",
                        side_effect=lambda name, logger=None, client_id=None: self.root / name):
            (self.root / "peak.exe").write_bytes(b"MZ" + b"\0" * 32)
            payload = dashboard.add_game("PEAK")
        self.assertTrue(payload["worker_ready"])
        self.assertTrue((self.root / "peak.exe").is_file())

    def test_add_and_run_starts_the_session(self):
        from worthlesstask.web.server import Dashboard
        manager = self.manager()
        dashboard = Dashboard(self.library, manager, resolver=mock.Mock())
        dashboard.resolver.resolve_by_name.return_value = mock.Mock(
            application_id="1384276457596911676",
            candidate=mock.Mock(executables=("peak.exe",), icon_url=None),
        )
        (self.root / "peak.exe").write_bytes(b"MZ" + b"\0" * 32)
        with mock.patch("worthlesstask.manager.ensure_decoy",
                        side_effect=lambda name, logger=None, client_id=None: self.root / name):
            dashboard.add_game("PEAK", autostart=True)
        self.wait_operation(manager)
        self.assertEqual(manager.active_slug, "peak")


class TestDerivedExecutable(ManagerTestCase):
    """Games the catalogue publishes no executable for still get a usable worker."""

    def fake_decoy(self, image, logger=None, client_id=None):
        """Stand in for ensure_decoy: materialise the worker so checks can read it."""
        path = self.root / image
        path.write_bytes(b"MZ" + b"\0" * 32)
        return path

    def add_without_catalogue_executable(self, name="Resident Evil Requiem"):
        from worthlesstask.web.server import Dashboard
        dashboard = Dashboard(self.library, self.manager(), resolver=mock.Mock())
        dashboard.resolver.resolve_by_name.return_value = mock.Mock(
            application_id="1456485028350656512",
            candidate=mock.Mock(executables=(), icon_url=None),
        )
        with mock.patch("worthlesstask.manager.ensure_decoy", side_effect=self.fake_decoy):
            return dashboard.add_game(name)

    def test_derived_name_and_worker_created(self):
        payload = self.add_without_catalogue_executable()
        self.assertEqual(payload["executable"], "residentevilrequiem.exe")
        self.assertEqual(payload["executable_source"], "derived")
        self.assertTrue(payload["can_start"])
        self.assertTrue(payload["worker_ready"])
        self.assertTrue((self.root / "residentevilrequiem.exe").is_file())

    def test_derived_name_is_flagged_as_outside_the_catalogue(self):
        payload = self.add_without_catalogue_executable()
        self.assertEqual("reason.derived", payload["availability_reason"])
        self.assertIsNone(self.library.get("arknights-endfield").availability_reason)

    def test_catalogue_name_is_preferred_when_present(self):
        from worthlesstask.web.server import Dashboard
        dashboard = Dashboard(self.library, self.manager(), resolver=mock.Mock())
        dashboard.resolver.resolve_by_name.return_value = mock.Mock(
            application_id="1384276457596911676",
            candidate=mock.Mock(executables=("peak/peak.exe",), icon_url=None),
        )
        (self.root / "peak.exe").write_bytes(b"MZ" + b"\0" * 32)
        with mock.patch("worthlesstask.manager.ensure_decoy",
                        side_effect=lambda image, logger=None, client_id=None: self.root / image):
            payload = dashboard.add_game("PEAK")
        self.assertEqual(payload["executable"], "peak.exe")
        self.assertEqual(payload["executable_source"], "catalogue")
        self.assertIsNone(payload["availability_reason"])

    def test_manual_override_is_validated_and_prepared(self):
        from worthlesstask.web.server import Dashboard
        payload = self.add_without_catalogue_executable()
        slug = payload["slug"]
        dashboard = Dashboard(self.library, self.manager(), resolver=mock.Mock())
        dashboard.resolver.index.by_id.return_value = None  # nothing in the catalogue
        with mock.patch("worthlesstask.manager.ensure_decoy", side_effect=self.fake_decoy):
            updated = dashboard.set_executable(slug, "re9.exe")
        self.assertEqual(updated["executable"], "re9.exe")
        self.assertEqual(updated["executable_source"], "manual")
        self.assertTrue(updated["worker_ready"])
        self.assertEqual("reason.manual", updated["availability_reason"])

    def test_a_hand_typed_name_that_matches_the_catalogue_is_not_flagged(self):
        """Typing the right name must not leave a warning on the card."""
        from worthlesstask.web.server import Dashboard
        slug = self.add_without_catalogue_executable()["slug"]
        dashboard = Dashboard(self.library, self.manager(), resolver=mock.Mock())
        dashboard.resolver.index.by_id.return_value = mock.Mock(
            executables=("win64/marvel-win64-shipping.exe",))
        with mock.patch("worthlesstask.manager.ensure_decoy", side_effect=self.fake_decoy):
            updated = dashboard.set_executable(slug, "Marvel-Win64-Shipping.exe")
        self.assertEqual(updated["executable_source"], "catalogue")
        self.assertIsNone(updated["availability_reason"])

    def test_a_hand_typed_name_outside_the_catalogue_warns_about_matching(self):
        from worthlesstask.web.server import Dashboard
        slug = self.add_without_catalogue_executable()["slug"]
        dashboard = Dashboard(self.library, self.manager(), resolver=mock.Mock())
        dashboard.resolver.index.by_id.return_value = mock.Mock(
            executables=("win64/marvel-win64-shipping.exe",))
        with mock.patch("worthlesstask.manager.ensure_decoy", side_effect=self.fake_decoy):
            updated = dashboard.set_executable(slug, "totally-made-up.exe")
        self.assertEqual(updated["executable_source"], "manual")
        self.assertEqual("reason.manual", updated["availability_reason"])
        self.assertNotEqual("reason.derived", updated["availability_reason"])

    def test_manual_override_rejects_a_path_or_metacharacters(self):
        from worthlesstask.web.server import Dashboard
        slug = self.add_without_catalogue_executable()["slug"]
        dashboard = Dashboard(self.library, self.manager(), resolver=mock.Mock())
        for bad in ("../evil.exe", "C:/windows/system32/cmd.exe", "game.exe & del", "game", ""):
            with self.subTest(bad=bad):
                with self.assertRaises(Exception):
                    dashboard.set_executable(slug, bad)
        self.assertEqual(self.library.get(slug).executable, "residentevilrequiem.exe")

    def test_derived_game_can_be_played(self):
        payload = self.add_without_catalogue_executable()
        manager = self.manager()
        manager.play(payload["slug"])
        self.assertEqual(manager.active_slug, payload["slug"])

    def test_derive_image_name(self):
        from worthlesstask.decoy import derive_image_name, validate_image_name

        self.assertEqual(derive_image_name("Resident Evil Requiem"), "residentevilrequiem.exe")
        self.assertEqual(derive_image_name("  ...  "), "game.exe")
        validate_image_name(derive_image_name("Some Game 2: Revenge!"))

if __name__ == "__main__":
    unittest.main()


class TestExternalWorkerDiscovery(ManagerTestCase):
    """A worker the user double-clicked must show up and be stoppable."""

    def test_finds_a_worker_started_by_hand(self):
        from worthlesstask.ui.inspect import VisibleWindow

        manager = self.manager()
        window = VisibleWindow(hwnd=1, pid=4242, title="The Forest")
        with mock.patch("worthlesstask.ui.inspect.visible_windows", return_value=[window]), \
             mock.patch("worthlesstask.ui.inspect.process_image_path",
                        return_value=str((self.root / "theforestvr.exe").resolve())):
            state = manager.status()
        self.assertEqual(state["active"]["slug"], "the-forest")
        self.assertEqual(state["active"]["reason"], "external")
        self.assertEqual(state["active"]["pid"], 4242)

    def test_ignores_a_window_whose_process_is_a_different_file(self):
        from worthlesstask.ui.inspect import VisibleWindow

        manager = self.manager()
        window = VisibleWindow(hwnd=1, pid=4242, title="The Forest")
        with mock.patch("worthlesstask.ui.inspect.visible_windows", return_value=[window]), \
             mock.patch("worthlesstask.ui.inspect.process_image_path",
                        return_value=r"C:/Windows/explorer.exe"):
            self.assertIsNone(manager.status()["active"])

    def test_ignores_an_unrelated_window_title(self):
        from worthlesstask.ui.inspect import VisibleWindow

        manager = self.manager()
        window = VisibleWindow(hwnd=1, pid=4242, title="Some Other App")
        with mock.patch("worthlesstask.ui.inspect.visible_windows", return_value=[window]):
            self.assertIsNone(manager.status()["active"])

    def test_the_newest_worker_owns_the_session(self):
        """Discord keeps one activity, so the panel must report the most recent one."""
        from worthlesstask.ui.inspect import VisibleWindow

        manager = self.manager()
        manager.play("arknights-endfield")
        window = VisibleWindow(hwnd=1, pid=4242, title="The Forest")
        with mock.patch("worthlesstask.ui.inspect.visible_windows", return_value=[window]), \
             mock.patch("worthlesstask.ui.inspect.process_image_path",
                        return_value=str((self.root / "theforestvr.exe").resolve())), \
             mock.patch("worthlesstask.manager.process_started_at",
                        return_value=manager.status()["active"]["uptime_s"] * 0 + 2_000_000_000):
            state = manager.status()
        self.assertEqual(state["active"]["slug"], "the-forest", "the newer external worker wins")
        self.assertEqual(state["active"]["also_running"], 1)

    def test_an_older_external_worker_does_not_displace_the_managed_one(self):
        from worthlesstask.ui.inspect import VisibleWindow

        manager = self.manager()
        manager.play("arknights-endfield")
        window = VisibleWindow(hwnd=1, pid=4242, title="The Forest")
        with mock.patch("worthlesstask.ui.inspect.visible_windows", return_value=[window]), \
             mock.patch("worthlesstask.ui.inspect.process_image_path",
                        return_value=str((self.root / "theforestvr.exe").resolve())), \
             mock.patch("worthlesstask.manager.process_started_at", return_value=1_000_000_000):
            state = manager.status()
        self.assertEqual(state["active"]["slug"], "arknights-endfield")
        self.assertEqual(state["active"]["also_running"], 1)

    def test_stop_closes_every_worker(self):
        from worthlesstask.ui.inspect import VisibleWindow

        manager = self.manager()
        manager.play("arknights-endfield")
        windows = [VisibleWindow(hwnd=1, pid=4242, title="The Forest")]
        with mock.patch("worthlesstask.ui.inspect.visible_windows", side_effect=lambda: list(windows)), \
             mock.patch("worthlesstask.ui.inspect.process_image_path",
                        return_value=str((self.root / "theforestvr.exe").resolve())), \
             mock.patch("worthlesstask.manager.PidProcess.poll", return_value=0):
            self.assertEqual(manager.status()["active"]["also_running"], 1)
            windows.clear()
            self.assertIsNone(manager.stop()["active"])

    def test_discovered_worker_can_be_stopped(self):
        from worthlesstask.ui.inspect import VisibleWindow

        manager = self.manager()
        windows = [VisibleWindow(hwnd=1, pid=4242, title="The Forest")]
        with mock.patch("worthlesstask.ui.inspect.visible_windows", side_effect=lambda: list(windows)), \
             mock.patch("worthlesstask.ui.inspect.process_image_path",
                        return_value=str((self.root / "theforestvr.exe").resolve())):
            self.assertEqual(manager.active_slug, "the-forest")
            windows.clear()  # stopping the worker closes its window
            self.assertIsNone(manager.stop()["active"])


class TestProcessTimestamps(ManagerTestCase):
    def test_started_at_is_none_for_a_missing_process(self):
        from worthlesstask.manager import process_started_at

        self.assertIsNone(process_started_at(999_999_999))

    def test_started_at_is_close_to_now_for_this_process(self):
        import os
        import time

        from worthlesstask.manager import process_started_at

        started = process_started_at(os.getpid())
        self.assertIsNotNone(started)
        self.assertLess(abs(time.time() - started), 86_400)


class TestBootloaderChildIsNotMistakenForExternal(ManagerTestCase):
    """A one-file PyInstaller worker runs the app as a child of its bootloader.

    The spawned pid and the pid owning the window differ, but both run the same
    file. Discovery must not report the managed worker's own child as external.
    """

    def test_managed_child_window_is_not_reported_as_also_running(self):
        from worthlesstask.ui.inspect import VisibleWindow

        manager = self.manager()
        manager.play("the-forest")
        managed_path = str((self.root / "theforestvr.exe").resolve())
        # The window belongs to the child, not to the pid that was spawned.
        child_window = VisibleWindow(hwnd=1, pid=999_001, title="The Forest")
        with mock.patch("worthlesstask.ui.inspect.visible_windows", return_value=[child_window]), \
             mock.patch("worthlesstask.ui.inspect.process_image_path", return_value=managed_path):
            state = manager.status()
        self.assertEqual(state["active"]["slug"], "the-forest")
        self.assertEqual(state["active"]["reason"], "manual")
        self.assertEqual(state["active"]["also_running"], 0)

    def test_a_different_game_window_is_still_external(self):
        from worthlesstask.ui.inspect import VisibleWindow

        manager = self.manager()
        manager.play("the-forest")
        other = VisibleWindow(hwnd=1, pid=999_002, title="ARKNIGHTS: ENDFIELD")
        with mock.patch("worthlesstask.ui.inspect.visible_windows", return_value=[other]), \
             mock.patch("worthlesstask.ui.inspect.process_image_path",
                        return_value=str((self.root / "endfield.exe").resolve())), \
             mock.patch("worthlesstask.manager.process_started_at", return_value=2_000_000_000):
            state = manager.status()
        self.assertEqual(state["active"]["also_running"], 1)
