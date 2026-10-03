"""Decoy-executable helpers — pure logic, no process is actually replaced."""

from __future__ import annotations

import os
import sys
import unittest
import sys
from pathlib import Path
from unittest import mock

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from worthlesstask import decoy as decoy_module
from worthlesstask.decoy import (
    discard_decoy,
    ensure_decoy,
    is_blank,
    current_image_name,
    decoy_path,
    decoy_run_argv,
    ensure_decoy,
    is_running_as,
    relaunch_argv,
)

IS_WINDOWS = os.name == "nt"
ENDFIELD_ID = "1461154307171811401"


class TestNaming(unittest.TestCase):
    def test_current_image_name_matches_interpreter(self):
        self.assertEqual(current_image_name().casefold(), Path(sys.executable).name.casefold())

    def test_is_running_as_self(self):
        self.assertTrue(is_running_as(current_image_name()))
        self.assertFalse(is_running_as("definitely-not-this-process.exe"))

    def test_decoy_path_sits_in_the_worker_dir(self):
        from worthlesstask.paths import worker_dir

        path = decoy_path("endfield.exe")
        self.assertEqual(path.parent, worker_dir())
        self.assertEqual(path.name, "endfield.exe")

    def test_catalogue_subdir_is_honoured_in_frozen_builds(self):
        """Marvel Rivals lists only prefixed executables: the worker must land in win64/."""
        candidate = mock.Mock(
            executables=("win64/marvel-win64-test.exe", "win64/marvel-win64-shipping.exe"))
        with mock.patch.object(decoy_module, "is_frozen", return_value=True), \
             mock.patch.object(decoy_module, "DetectableIndex") as index_cls:
            index_cls.return_value.by_id.return_value = candidate
            from worthlesstask.paths import worker_dir
            path = decoy_path("marvel-win64-shipping.exe", client_id="1314395942253756416")
            self.assertEqual(path, worker_dir() / "win64" / "marvel-win64-shipping.exe")

    def test_bare_catalogue_name_stays_flat_even_when_frozen(self):
        """wwm.exe is listed without a directory: any location matches, keep it flat."""
        candidate = mock.Mock(executables=("where winds meet.exe", "wwm.exe"))
        with mock.patch.object(decoy_module, "is_frozen", return_value=True), \
             mock.patch.object(decoy_module, "DetectableIndex") as index_cls:
            index_cls.return_value.by_id.return_value = candidate
            from worthlesstask.paths import worker_dir
            path = decoy_path("wwm.exe", client_id="1437509662303059998")
            self.assertEqual(path, worker_dir() / "wwm.exe")

    def test_source_builds_keep_the_worker_flat(self):
        """An interpreter copy needs its stdlib beside it, so prefix applies frozen-only."""
        candidate = mock.Mock(executables=("win64/marvel-win64-shipping.exe",))
        with mock.patch.object(decoy_module, "is_frozen", return_value=False), \
             mock.patch.object(decoy_module, "DetectableIndex") as index_cls:
            index_cls.return_value.by_id.return_value = candidate
            from worthlesstask.paths import worker_dir
            path = decoy_path("marvel-win64-shipping.exe", client_id="1314395942253756416")
            self.assertEqual(path, worker_dir() / "marvel-win64-shipping.exe")


class TestEnsureDecoy(unittest.TestCase):
    def test_returns_source_when_name_already_matches(self):
        self.assertEqual(ensure_decoy(current_image_name()), Path(sys.executable).resolve())

    @unittest.skipUnless(IS_WINDOWS, "windows-only")
    def test_creates_a_copy_with_the_requested_name(self):
        target = ensure_decoy("worthlesstask-test-decoy.exe")
        try:
            self.assertTrue(target.exists())
            self.assertEqual(target.name, "worthlesstask-test-decoy.exe")
            self.assertEqual(target.stat().st_size, Path(sys.executable).resolve().stat().st_size)
            # Idempotent: a second call must not rewrite it.
            first_mtime = target.stat().st_mtime_ns
            ensure_decoy("worthlesstask-test-decoy.exe")
            self.assertEqual(target.stat().st_mtime_ns, first_mtime)
        finally:
            target.unlink(missing_ok=True)
            target.with_suffix(".worthlesstask.json").unlink(missing_ok=True)


class TestRelaunchArgv(unittest.TestCase):
    def test_argv_shape(self):
        argv = relaunch_argv(Path("C:/x/endfield.exe"), None, frozen=False)
        self.assertEqual(argv[0], "C:\\x\\endfield.exe" if os.name == "nt" else "C:/x/endfield.exe")
        self.assertIn("-m", argv)
        self.assertIn("worthlesstask", argv)
        self.assertIn("presence", argv)
        self.assertIn("--window", argv)

    def test_config_path_is_forwarded(self):
        argv = relaunch_argv(Path("endfield.exe"), "config.json", frozen=False)
        self.assertEqual(argv[argv.index("--config") + 1], "config.json")

    def test_extra_args_appended(self):
        argv = relaunch_argv(Path("endfield.exe"), None, ["--refresh", "30"], frozen=False)
        self.assertTrue(argv[-2:] == ["--refresh", "30"])

    def test_frozen_build_uses_worker_mode(self):
        """A packaged exe has no -m: it only understands --worker."""
        argv = relaunch_argv(Path("C:/x/endfield.exe"), "C:/c/config.json", frozen=True)
        self.assertEqual(argv[0], "C:\\x\\endfield.exe" if os.name == "nt" else "C:/x/endfield.exe")
        self.assertNotIn("-m", argv)
        self.assertNotIn("worthlesstask", argv)
        self.assertNotIn("run", argv)
        self.assertEqual(argv[1], "--worker")
        self.assertEqual(argv[argv.index("--config") + 1], "C:/c/config.json")
        self.assertIn("--window", argv)


class TestDecoyRunArgv(unittest.TestCase):
    """A decoy started on its own — by launch, or by a logon task."""

    def test_frozen_decoy_runs_worker_directly(self):
        argv = decoy_run_argv(Path("C:/x/endfield.exe"), "C:/c/config.json", frozen=True)
        self.assertEqual(argv[:2], ["C:\\x\\endfield.exe" if os.name == "nt" else "C:/x/endfield.exe", "--worker"])
        self.assertIn("--config", argv)
        self.assertIn("--window", argv)

    def test_source_decoy_runs_the_module(self):
        argv = decoy_run_argv(Path("C:/x/endfield.exe"), "C:/c/config.json", frozen=False)
        self.assertIn("-m", argv)
        self.assertIn("worthlesstask", argv)
        self.assertIn("presence", argv)
        self.assertIn("--window", argv)

    def test_window_can_be_dropped(self):
        argv = decoy_run_argv(Path("endfield.exe"), None, frozen=True, window=False)
        self.assertNotIn("--window", argv)


if __name__ == "__main__":
    unittest.main(verbosity=2)


class TestDiscardDecoy(unittest.TestCase):
    """Removing a game must delete its worker — but only one we wrote."""

    def setUp(self):
        import tempfile

        self._tmp = tempfile.TemporaryDirectory()
        self.root = Path(self._tmp.name)
        self._patches = [
            mock.patch.object(decoy_module, "decoy_path", lambda name, client_id=None: self.root / name),
        ]
        for p in self._patches:
            p.start()

    def tearDown(self):
        for p in self._patches:
            p.stop()
        self._tmp.cleanup()

    def _write_owned(self, name: str, body: bytes = b"MZ payload"):
        import hashlib
        import json

        path = self.root / name
        path.write_bytes(body)
        digest = hashlib.sha256(body).hexdigest()
        path.with_suffix(".worthlesstask.json").write_text(json.dumps({"sha256": digest}), encoding="utf-8")
        return path

    def test_deletes_an_owned_worker_and_its_marker(self):
        path = self._write_owned("game.exe")
        self.assertTrue(discard_decoy("game.exe"))
        self.assertFalse(path.exists())
        self.assertFalse(path.with_suffix(".worthlesstask.json").exists())

    def test_refuses_a_file_with_no_marker(self):
        path = self.root / "foreign.exe"
        path.write_bytes(b"MZ not ours")
        self.assertFalse(discard_decoy("foreign.exe"))
        self.assertTrue(path.exists())

    def test_refuses_when_the_marker_hash_does_not_match(self):
        path = self._write_owned("game.exe")
        path.write_bytes(b"MZ replaced by someone else")
        self.assertFalse(discard_decoy("game.exe"))
        self.assertTrue(path.exists())

    def test_missing_file_is_not_an_error(self):
        self.assertFalse(discard_decoy("never-existed.exe"))

    def test_rejects_a_path_instead_of_a_name(self):
        with self.assertRaises(ValueError):
            discard_decoy("../escape.exe")


class TestBlankWorkerRecovery(unittest.TestCase):
    """An interrupted copy leaves a zero-filled file; it must be replaced, not refused."""

    def setUp(self):
        import tempfile

        self._tmp = tempfile.TemporaryDirectory()
        self.root = Path(self._tmp.name)
        self._patch = mock.patch.object(decoy_module, "decoy_path", lambda name, client_id=None: self.root / name)
        self._patch.start()

    def tearDown(self):
        self._patch.stop()
        self._tmp.cleanup()

    def test_a_zero_filled_file_is_detected(self):
        path = self.root / "zero.exe"
        path.write_bytes(b"\x00" * 4096)
        self.assertTrue(is_blank(path))

    def test_a_real_file_is_not_blank(self):
        path = self.root / "real.exe"
        path.write_bytes(b"MZ" + b"\x00" * 4094)
        self.assertFalse(is_blank(path))

    def test_a_missing_file_is_not_blank(self):
        self.assertFalse(is_blank(self.root / "nope.exe"))

    def test_ensure_decoy_replaces_a_zero_filled_worker(self):
        source = Path(sys.executable).resolve()
        target = self.root / "zeroed.exe"
        target.write_bytes(b"\x00" * target_size(source))
        target.with_suffix(".worthlesstask.json").write_text('{"sha256": "stale"}', encoding="utf-8")
        result = ensure_decoy("zeroed.exe")
        self.assertEqual(result, target)
        self.assertGreater(target.stat().st_size, 0)
        self.assertEqual(target.read_bytes()[:2], b"MZ")

    def test_ensure_decoy_still_refuses_a_foreign_file(self):
        target = self.root / "someone-elses.exe"
        target.write_bytes(b"MZ not ours, but real")
        with self.assertRaises(ValueError):
            ensure_decoy("someone-elses.exe")


def target_size(source: Path) -> int:
    return source.stat().st_size
