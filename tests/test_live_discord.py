"""Live integration tests against the running Discord client.

Hermetic by default: everything here is skipped unless ``WORTHLESSTASK_LIVE=1``,
because these tests open a real IPC connection and briefly publish a presence on
the signed-in account.

Run with::

    WORTHLESSTASK_LIVE=1 python -m unittest tests.test_live_discord -v
"""

from __future__ import annotations

import os
import sys
import threading
import time
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from worthlesstask.config.schema import AppConfig
from worthlesstask.core.backoff import BackoffPolicy
from worthlesstask.core.logging import setup_logging
from worthlesstask.core.errors import IpcUnavailableError, RpcTimeout
from worthlesstask.presence.resolver import DetectableIndex
from worthlesstask.rpc.client import RpcClient
from worthlesstask.rpc.supervisor import EXIT_ATTEMPTS_EXHAUSTED, EXIT_OK, PresenceSupervisor
from worthlesstask.rpc.transport import is_discord_running

LIVE = os.environ.get("WORTHLESSTASK_LIVE") == "1"
GAME = os.environ.get("WORTHLESSTASK_TEST_GAME", "The Forest")


@unittest.skipUnless(LIVE, "set WORTHLESSTASK_LIVE=1 to run live Discord tests")
class LiveDiscordTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        if not is_discord_running():
            raise unittest.SkipTest("Discord is not running")
        cls.log = setup_logging("INFO", None, True)
        index = DetectableIndex()
        candidate = index.best(GAME)
        if candidate is None:
            raise unittest.SkipTest(f"cannot resolve {GAME!r} in the detectable catalogue")
        cls.app_id = candidate.id
        cls.game_name = candidate.name
        cls.log.info("live test target", extra={"game": cls.game_name, "application_id": cls.app_id})

    def _config(self, **overrides) -> AppConfig:
        base = dict(
            client_id=self.app_id,
            game_name=self.game_name,
            log_file=None,
            backoff=BackoffPolicy(base_delay=0.2, factor=2.0, max_delay=1.0, jitter=0.0),
        )
        base.update(overrides)
        config = AppConfig(**base)
        config.validate()
        return config

    # ------------------------------------------------------------------ #
    def _connect(self, attempts: int = 4, delay: float = 4.0) -> RpcClient:
        """Connect, tolerating Discord's IPC handshake throttling.

        After a burst of connections Discord opens the socket but withholds READY
        for tens of seconds. That is a property of the client, not a bug here, so
        the tests retry rather than flake.
        """
        last: Exception | None = None
        for attempt in range(1, attempts + 1):
            client = RpcClient(client_id=self.app_id, logger=self.log, handshake_timeout=30.0)
            try:
                client.connect()
                return client
            except (IpcUnavailableError, RpcTimeout) as exc:
                last = exc
                client.close()
                self.log.warning(
                    "live test connect throttled",
                    extra={"attempt": attempt, "of": attempts, "error": str(exc)},
                )
                time.sleep(delay)
        raise AssertionError(f"could not connect after {attempts} attempts: {last}")

    def test_handshake_reports_the_signed_in_user(self):
        client = self._connect()
        try:
            self.assertTrue(client.ready)
            user = client.user or {}
            self.assertTrue(user.get("username"), "READY should carry the account")
        finally:
            client.close()

    def test_set_and_clear_activity(self):
        client = self._connect()
        try:
            echoed = client.set_activity(
                {
                    "name": self.game_name,
                    "type": 0,
                    "details": "integration test",
                    "state": "live",
                    "instance": False,
                }
            )
            self.assertIsInstance(echoed, dict)
            # Discord echoes the stored activity, including the application id it
            # resolved from the handshake — that is the proof it accepted it.
            self.assertEqual(str(echoed.get("application_id")), self.app_id)
            client.clear_activity()
        finally:
            client.close()

    def test_invalid_client_id_is_a_fatal_close(self):
        client = RpcClient(client_id="123456789012345678", logger=self.log)
        with self.assertRaises(Exception) as ctx:
            client.connect()
        message = str(ctx.exception)
        self.assertIn("4000", message, f"expected an invalid-client-id close, got: {message}")
        client.close()

    def test_supervisor_holds_then_stops_cleanly(self):
        """Connect, keep the presence alive across a refresh, then stop on request.

        Discord throttles IPC handshakes after a burst of connections, so the test
        waits for the connection instead of assuming a fixed latency.
        """
        config = self._config(refresh_interval=5.0, clear_on_exit=True, handshake_timeout=30.0)
        supervisor = PresenceSupervisor(config, logger=self.log)
        stop_event = threading.Event()
        result: dict[str, int] = {}

        def run() -> None:
            result["code"] = supervisor.run(stop_event)

        worker = threading.Thread(target=run, name="supervisor-test", daemon=True)
        started = time.monotonic()
        worker.start()

        deadline = started + 60.0
        while supervisor.stats.connections == 0 and time.monotonic() < deadline:
            time.sleep(0.2)
        self.assertEqual(
            supervisor.stats.connections,
            1,
            f"supervisor never connected (last error: {supervisor.stats.last_error})",
        )

        # Hold long enough to cross one refresh interval.
        time.sleep(6.0)
        stop_event.set()
        worker.join(timeout=20.0)

        self.assertFalse(worker.is_alive(), "supervisor did not stop")
        self.assertEqual(result.get("code"), EXIT_OK)
        self.assertEqual(supervisor.stats.drops, 0)
        self.assertGreaterEqual(
            supervisor.stats.updates, 2, "expected the initial set plus at least one refresh"
        )

    def test_supervisor_backs_off_when_ipc_is_missing(self):
        """A bogus endpoint must produce retries with growing delays, then give up."""
        os.environ["DISCORD_IPC_PATH"] = r"\\.\pipe\worthlesstask-does-not-exist"
        try:
            config = self._config(
                backoff=BackoffPolicy(
                    base_delay=0.3, factor=2.0, max_delay=5.0, jitter=0.0, max_attempts=3
                )
            )
            supervisor = PresenceSupervisor(config, logger=self.log)
            started = time.monotonic()
            code = supervisor.run(threading.Event())
            elapsed = time.monotonic() - started
        finally:
            os.environ.pop("DISCORD_IPC_PATH", None)

        self.assertEqual(code, EXIT_ATTEMPTS_EXHAUSTED)
        self.assertEqual(supervisor.stats.connections, 0)
        self.assertEqual(supervisor.stats.errors, 3)
        # 3 attempts -> delays of 0.3 + 0.6 + 1.2 (the last wait is skipped on give-up)
        self.assertGreaterEqual(elapsed, 0.9)

    def test_missing_ipc_raises_a_typed_error(self):
        os.environ["DISCORD_IPC_PATH"] = r"\\.\pipe\worthlesstask-does-not-exist"
        try:
            client = RpcClient(client_id=self.app_id, logger=self.log)
            with self.assertRaises(IpcUnavailableError):
                client.connect()
        finally:
            os.environ.pop("DISCORD_IPC_PATH", None)


if __name__ == "__main__":
    unittest.main(verbosity=2)
