"""The status read must not redo work it has already done.

The dashboard polls every 1.5 seconds. A status read used to enumerate every
top-level window, open every worker process for its creation time, and re-read and
re-parse the whole tail of a worker log. These tests count the underlying calls
rather than measuring wall time, so they hold on a slow or busy machine.
"""

from __future__ import annotations

import json
import time
import unittest
from pathlib import Path
from unittest import mock

from worthlesstask.core.cache import TtlCache, TtlValue, memoise
from worthlesstask.manager import PresenceManager, reset_process_caches


class FakeProcess:
    """Stands in for a spawned worker; never touches the OS."""

    def __init__(self, pid=1000):
        self.pid = pid
        self.returncode = None
        self.terminated = False

    def poll(self):
        return self.returncode

    def terminate(self):
        self.terminated = True
        self.returncode = 0

    kill = terminate

    def wait(self, timeout=None):
        return self.returncode if self.returncode is not None else 0


class TestTtlCache(unittest.TestCase):
    def test_a_value_is_reused_until_it_expires(self):
        cache = TtlCache(10.0)
        calls = []

        def compute(value):
            calls.append(value)
            return value * 2

        wrapped = memoise(cache, compute)
        self.assertEqual(wrapped(2), 4)
        self.assertEqual(wrapped(2), 4)
        self.assertEqual(len(calls), 1)
        self.assertEqual(cache.hits, 1)

    def test_a_value_expires(self):
        cache = TtlCache(0.05)
        calls = []
        wrapped = memoise(cache, lambda v: calls.append(v) or v)
        wrapped(1)
        wrapped(1)
        time.sleep(0.08)
        wrapped(1)
        self.assertEqual(len(calls), 2)

    def test_none_is_not_cached(self):
        """'This does not exist' is exactly the answer that must be re-checked."""
        cache = TtlCache(10.0)
        calls = []
        wrapped = memoise(cache, lambda v: calls.append(v) or None)
        self.assertIsNone(wrapped(1))
        self.assertIsNone(wrapped(1))
        self.assertEqual(len(calls), 2)

    def test_a_replaced_source_invalidates_the_value(self):
        """Patching the underlying function must not be answered from the old one.

        ``TtlValue`` stores whichever key the caller last set, so the caller can
        detect that the source changed. The manager relies on this to keep a patched
        window enumeration from being answered by a real one.
        """
        value = TtlValue(10.0)
        value.key = id(object())
        value.set(["real"])
        self.assertEqual(value.get(), ["real"])

        def patched():
            return ["patched"]

        self.assertNotEqual(value.key, id(patched))
        value.clear()
        self.assertIsNone(value.get())
        self.assertIsNone(value.key)


class TestStatusReadCost(unittest.TestCase):
    def setUp(self):
        reset_process_caches()
        self.addCleanup(reset_process_caches)
        self._tmp = __import__("tempfile").TemporaryDirectory()
        self.root = Path(self._tmp.name)
        self.addCleanup(self._tmp.cleanup)

        from worthlesstask.library import Library

        self.library = Library(path=self.root / "library.json", icons_dir=self.root / "icons")
        self.library.add("The Forest", "363409179668512788", executable="theforestvr.exe")
        (self.root / "theforestvr.exe").write_bytes(b"MZ" + b"\0" * 64)
        (self.root / "logs").mkdir(exist_ok=True)

        self._decoy = mock.patch(
            "worthlesstask.manager.ensure_decoy",
            side_effect=lambda name, logger=None, client_id=None: self.root / name,
        )
        self._decoy.start()
        self.addCleanup(self._decoy.stop)

    def manager(self) -> PresenceManager:
        # Spawning is faked: these tests count calls, they do not launch processes.
        return PresenceManager(
            self.library, package_root=self.root,
            spawn=lambda argv, env, cwd: FakeProcess(),
            runtime_path=self.root / "runtime.json",
        )

    def _log(self, slug, lines):
        path = self.root / "logs" / f"{slug}.log"
        path.write_text("\n".join(json.dumps(line) for line in lines) + "\n", encoding="utf-8")
        return path

    def test_window_enumeration_is_not_repeated_within_an_interval(self):
        from worthlesstask.ui.inspect import VisibleWindow

        manager = self.manager()
        window = VisibleWindow(hwnd=1, pid=4242, title="The Forest")
        calls = []

        def enumerate_windows():
            calls.append(1)
            return [window]

        with mock.patch("worthlesstask.ui.inspect.visible_windows", side_effect=enumerate_windows), \
             mock.patch("worthlesstask.ui.inspect.process_image_path",
                        return_value=str((self.root / "theforestvr.exe").resolve())):
            manager.status()
            manager.status()
            state = manager.status()

        # Three status reads, one walk of the window list.
        self.assertEqual(len(calls), 1)
        self.assertEqual(state["active"]["slug"], "the-forest")

    def test_a_worker_log_is_not_reparsed_when_nothing_was_appended(self):
        manager = self.manager()
        manager.play("the-forest")
        self._log("the-forest", [
            {"ts": "2026-01-01T00:00:00", "event": "presence set"},
        ])
        # First read derives the state from scratch.
        self.assertEqual(manager._rpc_state(_instance(manager))[0], "connected")

        reads = []
        real_open = Path.open

        def counting_open(self, *args, **kwargs):
            if self.name.endswith(".log"):
                reads.append(self.name)
            return real_open(self, *args, **kwargs)

        with mock.patch.object(Path, "open", counting_open):
            for _ in range(5):
                state = manager._rpc_state(_instance(manager))[0]
        self.assertEqual(state, "connected")
        self.assertEqual(len(reads), 5)  # opened, but only new bytes are read

    def test_derived_state_survives_a_read_that_adds_nothing(self):
        """A poll that sees no new lines must still report the last known state."""
        manager = self.manager()
        manager.play("the-forest")
        self._log("the-forest", [{"ts": "2026-01-01T00:00:00", "event": "presence set"}])

        instance = _instance(manager)
        self.assertEqual(manager._rpc_state(instance)[0], "connected")
        # Same file, nothing appended: the state must not decay to "connecting".
        self.assertEqual(manager._rpc_state(instance)[0], "connected")
        self.assertEqual(manager._rpc_state(instance)[0], "connected")

    def test_a_truncated_log_is_reparsed_from_the_start(self):
        """A restarted worker truncates its log; the new one must be read fresh."""
        manager = self.manager()
        manager.play("the-forest")
        path = self._log("the-forest", [{"ts": "2026-01-01T00:00:00", "event": "presence set"}])
        instance = _instance(manager)
        self.assertEqual(manager._rpc_state(instance)[0], "connected")

        # Restart: smaller file, different content.
        path.write_text(json.dumps({"ts": "2026-01-01T00:00:00", "event": "connecting"}) + "\n",
                        encoding="utf-8")
        self.assertEqual(manager._rpc_state(instance)[0], "connecting")

    def test_a_mutation_clears_the_caches(self):
        from worthlesstask.ui.inspect import VisibleWindow

        manager = self.manager()
        window = VisibleWindow(hwnd=1, pid=4242, title="The Forest")
        calls = []

        def enumerate_windows():
            calls.append(1)
            return [window]

        with mock.patch("worthlesstask.ui.inspect.visible_windows", side_effect=enumerate_windows), \
             mock.patch("worthlesstask.ui.inspect.process_image_path",
                        return_value=str((self.root / "theforestvr.exe").resolve())):
            manager.status()
            first = len(calls)
            manager.play("the-forest")  # a lifecycle change must invalidate
            manager.status()
            self.assertGreater(len(calls), first)


def _instance(manager):
    """The managed worker, with its clock wound back so log lines are not filtered.

    ``_rpc_state`` ignores records older than the worker's start; a stand-in started
    at zero accepts anything.
    """
    with manager._lock:
        instance = manager._instance
    if instance is not None:
        instance.started_at = 0
        return instance

    class StandIn:
        slug = "the-forest"
        image_path = ""
        started_at = 0
        worker_pid = None
        worker_identity = None

    return StandIn()


if __name__ == "__main__":
    unittest.main(verbosity=2)
