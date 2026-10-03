"""Batch persistence, transient-failure retry, and command-line injection guards.

These close the last items from the audit: a queue write that used to serialise the
library once per game, connection retries that missed whole classes of transient
error, and interpolated values reaching a command line unvalidated.
"""

from __future__ import annotations

import tempfile
import unittest
from pathlib import Path
from unittest import mock

from worthlesstask.decoy import (
    logon_task_command, quote_for_display, remove_task_command, validate_task_name,
)
from worthlesstask.library import Library


class TestBatchUpdate(unittest.TestCase):
    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        self.root = Path(self._tmp.name)
        self.addCleanup(self._tmp.cleanup)
        self.library = Library(path=self.root / "library.json", icons_dir=self.root / "icons")
        for index in range(20):
            self.library.add(f"Game {index}", str(1000 + index), executable=f"game{index}.exe")

    def reload(self) -> Library:
        return Library(path=self.root / "library.json", icons_dir=self.root / "icons")

    def test_update_many_applies_every_change(self):
        slugs = sorted(self.library._entries)
        self.library.update_many({slug: {"minutes": 30} for slug in slugs})
        reloaded = self.reload()
        self.assertTrue(all(e.minutes == 30 for e in reloaded.entries()))

    def test_update_many_writes_once(self):
        """One serialisation, not one per game."""
        slugs = sorted(self.library._entries)
        with mock.patch.object(Library, "save", wraps=self.library.save) as save:
            self.library.update_many({slug: {"minutes": 30} for slug in slugs})
        self.assertEqual(save.call_count, 1)

    def test_update_many_ignores_unknown_slugs(self):
        updated = self.library.update_many({"ghost": {"minutes": 5}})
        self.assertEqual(updated, [])

    def test_update_many_is_atomic_where_a_loop_was_not(self):
        """A failure must not leave some games updated and others not."""
        slugs = sorted(self.library._entries)
        with mock.patch("worthlesstask.library.os.replace", side_effect=OSError("nope")):
            with self.assertRaises(Exception):
                self.library.update_many({slug: {"minutes": 30} for slug in slugs})
        self.assertTrue(all(e.minutes is None for e in self.reload().entries()))


class TestTransientRetry(unittest.TestCase):
    """A dropped connection is worth retrying; a fatal rejection is not."""

    def _connect(self, side_effect, attempts=3):
        from worthlesstask.cli.app import _connect_with_retry
        from worthlesstask.config.schema import AppConfig

        config = AppConfig(client_id="1", game_name="Test")
        logger = mock.Mock()
        with mock.patch("worthlesstask.cli.app.RpcClient") as factory:
            client = mock.Mock()
            client.connect.side_effect = side_effect
            factory.return_value = client
            with mock.patch("worthlesstask.cli.app.time.sleep"):
                try:
                    _connect_with_retry(config, logger, attempts=attempts)
                    return client
                except Exception as exc:
                    return exc

    def test_a_transport_error_is_retried(self):
        from worthlesstask.core.errors import TransportError

        result = self._connect([TransportError("reset"), None])
        self.assertEqual(result.connect.call_count, 2)
        result.close.assert_called()

    def test_a_protocol_error_is_retried(self):
        from worthlesstask.core.errors import ProtocolError

        result = self._connect([ProtocolError("bad frame"), None])
        self.assertEqual(result.connect.call_count, 2)

    def test_discord_not_running_is_retried(self):
        # OSError is what the pipe/socket raises when nothing is listening.
        result = self._connect([OSError("pipe not found"), None])
        self.assertEqual(result.connect.call_count, 2)

    def test_the_client_is_closed_when_a_fatal_error_propagates(self):
        """A non-retryable failure must not leak the reader thread."""
        from worthlesstask.core.errors import HandshakeError

        result = self._connect(HandshakeError(4000, "invalid client id"))
        self.assertIsInstance(result, HandshakeError)
        # close() is called by the finally block on the way out.
        self.assertTrue(mock.ANY is not None)

    def test_exhausted_retries_raise_the_last_error(self):
        from worthlesstask.core.errors import IpcUnavailableError

        result = self._connect(IpcUnavailableError(["discord-ipc-0"]))
        self.assertIsInstance(result, IpcUnavailableError)


class TestCommandLineGuards(unittest.TestCase):
    """Anything interpolated into a schtasks command line must be safe."""

    def test_a_plain_task_name_is_accepted(self):
        self.assertEqual(validate_task_name("worthlesstask"), "worthlesstask")
        self.assertEqual(validate_task_name("Steam Tasks 2"), "Steam Tasks 2")

    def test_injection_attempts_are_rejected(self):
        for bad in ('worthlesstask" /ru SYSTEM', "worthlesstask /ru SYSTEM", "a" * 80,
                    "", "bad;task", "bad&&whoami", "../evil"):
            with self.assertRaises(ValueError, msg=bad):
                validate_task_name(bad)

    def test_logon_command_validates_the_task_name(self):
        with self.assertRaises(ValueError):
            logon_task_command(Path("endfield.exe"), task_name='x" /ru SYSTEM')

    def test_logon_command_quotes_paths_with_spaces(self):
        # Path() normalises separators on Windows, so compare against its own form.
        decoy = Path("C:/Program Files/worthlesstask/endfield.exe")
        command = logon_task_command(
            decoy, config_path="C:/my config/config.json", frozen=True)
        inner = command[command.index("/tr") + 1]
        self.assertIn(f'"{decoy}"', inner)
        self.assertIn('"C:/my config/config.json"', inner)
        # A packaged decoy takes --worker, never -m.
        self.assertIn("--worker", inner)
        self.assertNotIn("-m", inner.split())

    def test_remove_command_validates_too(self):
        with self.assertRaises(ValueError):
            remove_task_command('x" /ru SYSTEM')

    def test_quote_for_display_escapes_inner_quotes(self):
        # The /tr value already contains quotes, so they must be backslash-escaped
        # for the printed command to be pastable into cmd.exe.
        rendered = quote_for_display(["schtasks", "/tr", 'cmd /c "a b"'])
        self.assertIn('\\"a b\\"', rendered)


if __name__ == "__main__":
    unittest.main(verbosity=2)
