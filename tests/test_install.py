"""Install, uninstall and portable-layout behaviour."""

import os
import sys
import tempfile
import unittest
from pathlib import Path
from unittest import mock

from worthlesstask import install as install_module
from worthlesstask.install import (
    InstallError,
    _skip,
    default_target,
    find_source_folder,
    install,
    resolve_target,
    uninstall,
)
from worthlesstask.paths import appdata_root, data_root, is_frozen, worker_dir

IS_WINDOWS = os.name == "nt"


class TestSkipRules(unittest.TestCase):
    """An installation must carry the program and its workers, nothing else."""

    def test_generated_state_is_not_installed(self):
        for name in ("logs", ".cache", "icons", "runtime.json", "worthlesstask.log",
                     "library.json", "config.json", "worthlesstask"):
            self.assertTrue(_skip(Path(name)), name)

    def test_program_and_workers_are_installed(self):
        for name in ("worthlesstask.exe", "residentevilrequiem.exe", "worthlesstask.ico",
                     "config.example.json", "RUN.cmd"):
            self.assertFalse(_skip(Path(name)), name)

    def test_backups_and_temp_files_are_skipped(self):
        for name in ("library.json.bak", "x.writing", "x.pyc", "README.md", "shot.png"):
            self.assertTrue(_skip(Path(name)), name)


class TestTargets(unittest.TestCase):
    def test_per_user_default_is_writable(self):
        target = default_target(True)
        self.assertEqual(target.name, "worthlesstask")
        self.assertIn("Programs", str(target))

    def test_explicit_target_outside_program_files_is_per_user(self):
        with tempfile.TemporaryDirectory() as tmp:
            paths = resolve_target(tmp, per_user=False, allow_admin=False)
            self.assertTrue(paths.per_user)
            self.assertEqual(paths.exe.name, "worthlesstask.exe")

    def test_program_files_without_elevation_is_refused(self):
        with mock.patch.object(install_module, "is_admin", return_value=False):
            with self.assertRaises(InstallError):
                resolve_target(None, per_user=False, allow_admin=False)

    def test_program_files_is_allowed_when_elevated(self):
        with mock.patch.object(install_module, "is_admin", return_value=True):
            paths = resolve_target(None, per_user=False, allow_admin=True)
        self.assertFalse(paths.per_user)


class TestInstallRoundTrip(unittest.TestCase):
    """Install into a scratch folder and take it back out again."""

    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        self.source = Path(self._tmp.name) / "portable"
        self.target = Path(self._tmp.name) / "installed"
        self.source.mkdir()
        (self.source / "worthlesstask.exe").write_bytes(b"MZ fake")
        (self.source / "residentevilrequiem.exe").write_bytes(b"MZ fake")
        (self.source / "library.json").write_text("{}", encoding="utf-8")
        (self.source / "logs").mkdir()
        (self.source / "logs" / "old.log").write_text("x", encoding="utf-8")
        (self.source / "icons").mkdir()
        self._patches = [
            mock.patch.object(install_module, "find_source_folder", return_value=self.source),
            mock.patch.object(install_module, "_create_shortcuts", return_value=[]),
            mock.patch.object(install_module, "_register_uninstall", return_value=None),
        ]
        for patch in self._patches:
            patch.start()

    def tearDown(self):
        for patch in self._patches:
            patch.stop()
        self._tmp.cleanup()

    def test_install_copies_only_the_program(self):
        paths = install(target=str(self.target))
        names = sorted(p.name for p in self.target.iterdir())
        self.assertEqual(
            names, sorted(["worthlesstask.exe", "residentevilrequiem.exe", "uninstall.cmd"]))
        self.assertEqual(paths.exe, self.target / "worthlesstask.exe")

    def test_install_is_idempotent(self):
        install(target=str(self.target))
        first = (self.target / "worthlesstask.exe").stat().st_mtime_ns
        install(target=str(self.target))
        self.assertEqual((self.target / "worthlesstask.exe").stat().st_mtime_ns, first)

    def test_uninstall_removes_the_folder(self):
        install(target=str(self.target))
        self.assertTrue(self.target.is_dir())
        removed = uninstall(installed=str(self.target))
        self.assertEqual(removed, self.target)
        self.assertFalse(self.target.exists())

    def test_uninstall_refuses_the_folder_we_run_from(self):
        with mock.patch.object(install_module, "source_folder", return_value=self.source):
            with self.assertRaises(InstallError):
                uninstall(installed=None)


class TestSelfInstallFromPortable(unittest.TestCase):
    def test_source_folder_is_found_from_the_portable_layout(self):
        root = Path(__file__).resolve().parents[1]
        portable = root / "dist" / "worthlesstask"
        if not (portable / "worthlesstask.exe").is_file():
            self.skipTest("portable folder not built")
        with mock.patch.object(install_module, "Path", Path):
            found = find_source_folder()
        self.assertTrue((found / "worthlesstask.exe").is_file())


class TestDataLocation(unittest.TestCase):
    def test_source_runs_and_frozen_runs_differ(self):
        # Nothing is asserted about the environment: the point is that the choice is
        # made in one place and follows the packaging mode.
        self.assertEqual(is_frozen(), bool(getattr(sys, "frozen", False)))

    def test_installed_build_writes_outside_the_program_folder(self):
        if not is_frozen():
            self.skipTest("frozen-only behaviour")
        self.assertNotEqual(data_root(), Path(sys.executable).resolve().parent)
        self.assertTrue(str(worker_dir()).startswith(str(appdata_root())))


if __name__ == "__main__":
    unittest.main(verbosity=2)
