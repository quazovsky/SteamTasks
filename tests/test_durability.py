"""Durability: cross-process locking, atomic writes, bounded fetch, single clear.

These cover the failure modes that lose data or wedge the dashboard rather than the
happy paths, which the other suites already exercise.
"""

from __future__ import annotations

import argparse
import json
import os
import urllib.error
import subprocess
import sys
import tempfile
import threading
import time
import unittest
from pathlib import Path
from unittest import mock

from worthlesstask.core.atomic import write_atomic, write_bytes_atomic, write_json_atomic
from worthlesstask.core.filelock import LockTimeout, file_lock
from worthlesstask.library import Library

REPO = Path(__file__).resolve().parents[1]


class TestFileLock(unittest.TestCase):
    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        self.root = Path(self._tmp.name)
        self.target = self.root / "library.json"
        self.target.write_text("{}", encoding="utf-8")

    def tearDown(self):
        self._tmp.cleanup()

    def test_lock_is_mutually_exclusive_across_threads(self):
        order = []

        def worker(index):
            with file_lock(self.target):
                order.append(f"enter{index}")
                time.sleep(0.05)
                order.append(f"exit{index}")

        threads = [threading.Thread(target=worker, args=(i,)) for i in range(3)]
        for thread in threads:
            thread.start()
        for thread in threads:
            thread.join()

        # No overlap: every enter must be followed by its own exit.
        for i, event in enumerate(order):
            if event.startswith("enter"):
                self.assertEqual(order[i + 1], "exit" + event[-1])

    def test_lock_is_mutually_exclusive_across_processes(self):
        """Two real OS processes must not hold the file at the same time."""
        script = (
            "import sys, time\n"
            "sys.path.insert(0, sys.argv[1])\n"
            "from worthlesstask.core.filelock import file_lock\n"
            "with file_lock(sys.argv[2]):\n"
            "    print('held', flush=True)\n"
            "    time.sleep(1.0)\n"
        )
        first = subprocess.Popen(
            [sys.executable, "-c", script, str(REPO), str(self.target)],
            stdout=subprocess.PIPE, text=True,
        )
        self.assertEqual(first.stdout.readline().strip(), "held")

        started = time.monotonic()
        with file_lock(self.target, timeout=5.0):
            waited = time.monotonic() - started
        first.wait(timeout=10)
        # The second holder had to wait for the first process to let go.
        self.assertGreater(waited, 0.05)

    def test_timeout_raises_rather_than_hanging(self):
        held = threading.Event()

        def holder():
            with file_lock(self.target, timeout=5.0):
                held.set()
                time.sleep(1.0)

        thread = threading.Thread(target=holder)
        thread.start()
        held.wait(5)
        try:
            with self.assertRaises(LockTimeout):
                with file_lock(self.target, timeout=0.15):
                    pass
        finally:
            thread.join(timeout=10)


class TestAtomicWrites(unittest.TestCase):
    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        self.root = Path(self._tmp.name)

    def tearDown(self):
        self._tmp.cleanup()

    def test_no_temp_file_is_left_behind(self):
        target = self.root / "a.json"
        write_json_atomic(target, {"ok": True})
        self.assertEqual(json.loads(target.read_text(encoding="utf-8")), {"ok": True})
        leftovers = [p.name for p in self.root.iterdir() if p.name != "a.json"]
        self.assertEqual(leftovers, [])

    def test_bytes_are_written_whole(self):
        target = self.root / "icon.ico"
        payload = bytes(range(256)) * 64
        write_bytes_atomic(target, payload)
        self.assertEqual(target.read_bytes(), payload)

    def test_a_failure_leaves_the_previous_file_intact(self):
        target = self.root / "a.txt"
        target.write_text("original", encoding="utf-8")
        with mock.patch("worthlesstask.core.atomic.os.fsync", side_effect=OSError("disk gone")):
            with self.assertRaises(OSError):
                write_atomic(target, "replacement")
        self.assertEqual(target.read_text(encoding="utf-8"), "original")
        leftovers = [p.name for p in self.root.iterdir() if p.name != "a.txt"]
        self.assertEqual(leftovers, [])


class TestMalformedCache(unittest.TestCase):
    """A damaged cache must read as 'no cache', never raise."""

    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        self.cache = Path(self._tmp.name) / "detectable.json"

    def tearDown(self):
        self._tmp.cleanup()

    def _index(self):
        from worthlesstask.presence.resolver import DetectableIndex

        return DetectableIndex(cache_path=self.cache, fetch=mock.Mock(return_value=b"[]"))

    def test_a_non_object_payload_is_ignored(self):
        self.cache.write_text("[]", encoding="utf-8")
        self.assertIsNone(self._index()._read_cache())

    def test_a_null_timestamp_is_ignored(self):
        self.cache.write_text('{"fetched_at": null, "entries": []}', encoding="utf-8")
        fetched_at, entries = self._index()._read_cache()
        self.assertEqual(fetched_at, 0.0)
        self.assertEqual(entries, [])

    def test_truncated_json_is_ignored(self):
        self.cache.write_text('{"fetched_at": 1.0, "entries": [', encoding="utf-8")
        self.assertIsNone(self._index()._read_cache())

    def test_entries_of_the_wrong_shape_are_dropped(self):
        self.cache.write_text('{"fetched_at": 1.0, "entries": [1, "x", null]}', encoding="utf-8")
        _, entries = self._index()._read_cache()
        self.assertEqual(entries, [])

    def test_a_forced_refresh_falls_back_to_a_stale_cache(self):
        """Offline, a stale catalogue is far better than none."""
        self.cache.write_text(
            json.dumps({"fetched_at": 1.0, "entries": [{"id": "1", "name": "Test"}]}),
            encoding="utf-8",
        )
        index = self._index()
        # urllib raises URLError, which is what the retry loop handles as transient.
        index._fetch = mock.Mock(side_effect=urllib.error.URLError("offline"))
        with mock.patch("worthlesstask.presence.resolver.time.sleep"):
            entries = index.entries(force_refresh=True)
        self.assertEqual(len(entries), 1)
        self.assertEqual(index.source, "stale-cache")


class TestBoundedFetch(unittest.TestCase):
    """The catalogue fetch must not allocate without limit, and must retry transiently."""

    def _response(self, chunks):
        response = mock.MagicMock()
        response.status = 200
        response.read.side_effect = chunks
        response.__enter__ = mock.Mock(return_value=response)
        response.__exit__ = mock.Mock(return_value=False)
        return response

    def test_an_oversized_body_is_rejected(self):
        from worthlesstask.core.errors import ResolverError
        from worthlesstask.presence.resolver import MAX_CATALOGUE_BYTES, DetectableIndex

        index = DetectableIndex(cache_path=Path(tempfile.mkdtemp()) / "c.json")
        chunks = [b"x" * (1 << 16)] * ((MAX_CATALOGUE_BYTES // (1 << 16)) + 2) + [b""]
        with mock.patch("urllib.request.urlopen", return_value=self._response(chunks)):
            with mock.patch("worthlesstask.presence.resolver.time.sleep"):
                with self.assertRaises(ResolverError) as ctx:
                    index._fetch_catalogue()
        self.assertIn("MiB", str(ctx.exception))

    def test_a_transient_failure_is_retried(self):
        from worthlesstask.presence.resolver import DetectableIndex
        import urllib.error

        index = DetectableIndex(cache_path=Path(tempfile.mkdtemp()) / "c.json")
        payload = json.dumps([{"id": "1", "name": "Test"}]).encode("utf-8")
        chunks = [payload, b""]
        attempts = []

        def flaky(*_args, **_kwargs):
            attempts.append(1)
            if len(attempts) == 1:
                raise urllib.error.URLError("connection reset")
            return self._response(chunks)

        with mock.patch("urllib.request.urlopen", side_effect=flaky):
            with mock.patch("worthlesstask.presence.resolver.time.sleep"):
                entries = index._fetch_catalogue()
        self.assertEqual(len(entries), 1)
        self.assertEqual(len(attempts), 2)

    def test_a_404_is_not_retried(self):
        from worthlesstask.core.errors import ResolverError
        from worthlesstask.presence.resolver import DetectableIndex
        import urllib.error

        index = DetectableIndex(cache_path=Path(tempfile.mkdtemp()) / "c.json")
        attempts = []

        def not_found(request, *_args, **_kwargs):
            # Count only the primary endpoint: the resolver tries each candidate
            # version once, so a per-URL count is what proves "not retried".
            if "v10" in (request.full_url if hasattr(request, "full_url") else str(request)):
                attempts.append(1)
            raise urllib.error.HTTPError("u", 404, "nope", None, None)

        with mock.patch("urllib.request.urlopen", side_effect=not_found):
            with mock.patch("worthlesstask.presence.resolver.time.sleep"):
                with self.assertRaises(ResolverError):
                    index._fetch_catalogue()
        self.assertEqual(len(attempts), 1)


class TestSingleClearOnExit(unittest.TestCase):
    """Clearing twice costs a second handshake and gets the client throttled."""

    def test_client_records_that_it_cleared(self):
        from worthlesstask.rpc.client import RpcClient

        client = RpcClient(client_id="1")
        self.assertFalse(client.cleared)
        with mock.patch.object(type(client), "ready", new_callable=mock.PropertyMock,
                               return_value=True), \
             mock.patch.object(client, "clear_activity") as clear:
            client.close(clear=True)
        self.assertTrue(client.cleared)
        clear.assert_called_once()

    def test_a_client_that_never_connected_counts_as_cleared(self):
        """Nothing was set, so there is nothing to clear."""
        from worthlesstask.rpc.client import RpcClient

        client = RpcClient(client_id="1")
        client.close(clear=True)
        self.assertTrue(client.cleared)

    def test_supervisor_reports_that_it_cleared(self):
        from worthlesstask.config.schema import AppConfig
        from worthlesstask.rpc.supervisor import PresenceSupervisor

        config = AppConfig(client_id="1", game_name="Test")
        supervisor = PresenceSupervisor(config)
        client = mock.Mock()
        client.cleared = True
        client.connect.side_effect = OSError("no discord")
        stop_event = threading.Event()
        stop_event.set()
        with mock.patch.object(supervisor, "_client_factory", return_value=client):
            supervisor.run(stop_event)
        self.assertTrue(supervisor.stats.cleared)

    def test_cmd_run_clears_only_when_the_supervisor_did_not(self):
        """The gate: a second clear means a second IPC handshake for nothing."""
        from worthlesstask.config.schema import AppConfig
        from worthlesstask.cli import app as app_module

        def run_with(cleared):
            config = AppConfig(client_id="1", game_name="Test", clear_on_exit=True)
            supervisor = mock.Mock()
            supervisor.stats.cleared = cleared
            supervisor.run.return_value = 0
            args = argparse.Namespace(window=False, config=None, log_level=None,
                                      log_file=None, json=False)
            with mock.patch.object(app_module, "_load", return_value=config), \
                 mock.patch.object(app_module, "setup_logging"), \
                 mock.patch.object(app_module, "_make_identity_refresher"), \
                 mock.patch.object(app_module, "_install_signal_handlers"), \
                 mock.patch.object(app_module, "PresenceSupervisor", return_value=supervisor), \
                 mock.patch.object(app_module, "_clear_best_effort") as clear:
                app_module.cmd_run(args)
                return clear

        self.assertFalse(run_with(cleared=True).called)
        self.assertTrue(run_with(cleared=False).called)


class TestLibraryWritesAreAtomic(unittest.TestCase):
    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        self.root = Path(self._tmp.name)

    def tearDown(self):
        self._tmp.cleanup()

    def test_save_leaves_no_temp_files(self):
        library = Library(path=self.root / "library.json", icons_dir=self.root / "icons")
        library.add("Test Game", "999")
        # The lock file is meant to persist — it is what coordinates processes — but
        # no .writing fragment may survive a save.
        names = sorted(p.name for p in self.root.iterdir())
        self.assertNotIn("library.json.writing", names)
        self.assertEqual([n for n in names if n.endswith(".json")], ["library.json"])

    def test_a_failed_save_keeps_the_previous_library(self):
        library = Library(path=self.root / "library.json", icons_dir=self.root / "icons")
        library.add("First", "1")
        with mock.patch("worthlesstask.library.os.replace", side_effect=OSError("nope")):
            with self.assertRaises(Exception):
                library.add("Second", "2")
        reloaded = Library(path=self.root / "library.json", icons_dir=self.root / "icons")
        self.assertEqual([e.game_name for e in reloaded.entries()], ["First"])


if __name__ == "__main__":
    unittest.main(verbosity=2)
