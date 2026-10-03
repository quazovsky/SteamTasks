"""Writing and deleting a worker must never happen through a path we do not control.

The worker folder is user-writable. Anything that opens an existing path for writing
— `shutil.copy2` did — can be redirected by a link planted at that path, so a
"prepared worker" lands on a file the attacker chose. Exclusive creation closes that,
and the same reasoning applies to deletion: unlinking through a link deletes someone
else's file.

Real symlinks are not creatable in every environment (Windows needs a privilege or
Developer Mode), so the link cases are exercised by making `is_symlink` report true
rather than by creating one. The properties under test — refuse, don't follow, don't
clobber — are the same either way.
"""

from __future__ import annotations

import hashlib
import os
import sys
import tempfile
import unittest
from pathlib import Path
from unittest import mock

from worthlesstask import decoy as decoy_module
from worthlesstask.decoy import discard_decoy, ensure_decoy, is_blank, write_worker


class DecoyTestCase(unittest.TestCase):
    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        self.root = Path(self._tmp.name)
        self.addCleanup(self._tmp.cleanup)
        self.source = self.root / "source.exe"
        self.source.write_bytes(b"MZ" + b"\0" * 128)
        # Point decoy_path at this test's folder instead of the real worker dir.
        self._patch = mock.patch.object(
            decoy_module, "decoy_path", lambda name, client_id=None: self.root / name)
        self._patch.start()
        self.addCleanup(self._patch.stop)
        self._exe = mock.patch.object(
            decoy_module.sys, "executable", str(self.source))
        self._exe.start()
        self.addCleanup(self._exe.stop)

    def digest(self, path):
        return hashlib.sha256(path.read_bytes()).hexdigest()


class TestExclusiveWrite(DecoyTestCase):
    def test_a_new_worker_is_written(self):
        target = self.root / "game.exe"
        write_worker(self.source, target)
        self.assertTrue(target.is_file())
        self.assertEqual(target.read_bytes(), self.source.read_bytes())

    def test_no_temporary_file_is_left_behind(self):
        write_worker(self.source, self.root / "game.exe")
        names = sorted(p.name for p in self.root.iterdir())
        self.assertEqual(names, ["game.exe", "source.exe"])

    def test_it_replaces_a_normal_file_cleanly(self):
        """Needed to recover a blank worker left by an interrupted copy."""
        target = self.root / "game.exe"
        target.write_bytes(b"\0" * 16)
        write_worker(self.source, target)
        self.assertEqual(target.read_bytes(), self.source.read_bytes())

    def test_a_link_is_never_written_through(self):
        target = self.root / "game.exe"
        target.write_bytes(b"victim")
        with mock.patch.object(Path, "is_symlink", return_value=True):
            with self.assertRaises(ValueError) as ctx:
                write_worker(self.source, target)
        self.assertIn("символическую ссылку", str(ctx.exception))
        # Nothing was overwritten and no temp file was left behind.
        self.assertEqual(target.read_bytes(), b"victim")
        self.assertEqual(sorted(p.name for p in self.root.iterdir()),
                         ["game.exe", "source.exe"])

    def test_a_failed_write_leaves_no_partial_file(self):
        target = self.root / "game.exe"
        with mock.patch.object(decoy_module.os, "fsync", side_effect=OSError("disk")):
            with self.assertRaises(OSError):
                write_worker(self.source, target)
        self.assertFalse(target.exists())


class TestEnsureDecoyRefuses(DecoyTestCase):
    def test_a_foreign_file_is_not_overwritten(self):
        target = self.root / "game.exe"
        target.write_bytes(b"a real program, not ours")
        with self.assertRaises(ValueError) as ctx:
            ensure_decoy("game.exe")
        self.assertIn("не принадлежит worthlesstask", str(ctx.exception))
        self.assertEqual(target.read_bytes(), b"a real program, not ours")

    def test_a_link_is_refused(self):
        target = self.root / "game.exe"
        target.write_bytes(b"whatever")
        with mock.patch.object(Path, "is_symlink", return_value=True):
            with self.assertRaises(ValueError) as ctx:
                ensure_decoy("game.exe")
        self.assertIn("символическую ссылку", str(ctx.exception))

    def test_an_owned_blank_file_is_replaced(self):
        """An interrupted copy left a zero-filled file; that one is ours to fix."""
        target = self.root / "game.exe"
        target.write_bytes(b"\0" * 32)
        (self.root / "game.worthlesstask.json").write_text(
            '{"sha256": "stale"}', encoding="utf-8")
        self.assertTrue(is_blank(target))

        result = ensure_decoy("game.exe")
        self.assertEqual(result, target)
        self.assertEqual(target.read_bytes(), self.source.read_bytes())

    def test_an_up_to_date_worker_is_left_alone(self):
        target = self.root / "game.exe"
        write_worker(self.source, target)
        before = target.stat().st_mtime_ns
        ensure_decoy("game.exe")  # hash matches → returns early, no rewrite
        self.assertEqual(target.stat().st_mtime_ns, before)

    def test_the_marker_records_the_hash(self):
        ensure_decoy("game.exe")
        marker = self.root / "game.worthlesstask.json"
        self.assertEqual(
            __import__("json").loads(marker.read_text(encoding="utf-8"))["sha256"],
            self.digest(self.source),
        )


class TestDiscardDecoyRefuses(DecoyTestCase):
    def test_our_worker_is_deleted_with_its_marker(self):
        ensure_decoy("game.exe")
        marker = self.root / "game.worthlesstask.json"
        self.assertTrue((self.root / "game.exe").exists())
        self.assertTrue(discard_decoy("game.exe"))
        self.assertFalse((self.root / "game.exe").exists())
        self.assertFalse(marker.exists())

    def test_a_foreign_file_is_not_deleted(self):
        target = self.root / "game.exe"
        target.write_bytes(b"not ours")
        (self.root / "game.worthlesstask.json").write_text(
            '{"sha256": "not-matching"}', encoding="utf-8")
        self.assertFalse(discard_decoy("game.exe"))
        self.assertTrue(target.exists())

    def test_a_link_is_not_deleted_through(self):
        target = self.root / "game.exe"
        write_worker(self.source, target)
        # A link must be refused even when the marker and hash would otherwise
        # authorise deletion.
        with mock.patch.object(Path, "is_symlink", return_value=True):
            self.assertFalse(discard_decoy("game.exe"))
        self.assertTrue(target.exists())

    def test_a_missing_file_is_not_an_error(self):
        self.assertFalse(discard_decoy("ghost.exe"))


if __name__ == "__main__":
    unittest.main(verbosity=2)
