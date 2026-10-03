"""Autostart must schedule the decoy, not the plain interpreter.

Discord credits a game from its process and window scan, not from Rich Presence.
A logon task that ran ``python -m worthlesstask run`` would publish the presence while
no process matched the game, so the game would never be registered. The task has to
run the renamed copy of the program, in window mode.
"""

from __future__ import annotations

import argparse
import os
import tempfile
import unittest
from pathlib import Path
from unittest import mock

from worthlesstask.cli import app as app_module

IS_WINDOWS = os.name == "nt"


class TestAutostartCommand(unittest.TestCase):
    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        self.root = Path(self._tmp.name)

    def tearDown(self):
        self._tmp.cleanup()

    def _args(self, config: str | None = None):
        return argparse.Namespace(remove=False, apply=False, config=config, json=False)

    def _config_file(self, client_id="1461154307171811401", game="ARKNIGHTS: ENDFIELD"):
        import json

        path = self.root / "config.json"
        path.write_text(json.dumps({"client_id": client_id, "game_name": game}), encoding="utf-8")
        return str(path)

    def _task_string(self, config):
        decoy = self.root / "endfield.exe"
        decoy.write_bytes(b"MZ")
        with mock.patch.object(app_module, "ensure_decoy", return_value=decoy), \
             mock.patch.object(app_module, "executable_name_for", return_value="endfield.exe"):
            command = app_module._autostart_command(self._args(config))
        self.assertEqual(command[0], "schtasks")
        return command[command.index("/tr") + 1]

    @unittest.skipUnless(IS_WINDOWS, "autostart is Windows-only")
    def test_task_runs_the_decoy_in_window_mode(self):
        config = self._config_file()
        task = self._task_string(config)
        # Paths are compared case-insensitively: temp dirs differ in case per host.
        lowered = task.casefold()
        self.assertIn("endfield.exe", lowered)
        self.assertIn("--window", lowered)
        self.assertIn(config.casefold(), lowered)
        # The plain interpreter must not be what the task runs.
        self.assertNotIn("python", task.lower())

    @unittest.skipUnless(IS_WINDOWS, "autostart is Windows-only")
    def test_a_packaged_task_runs_worker_mode(self):
        """A packaged decoy has no -m: it takes --worker directly."""
        config = self._config_file()
        decoy = self.root / "endfield.exe"
        decoy.write_bytes(b"MZ")
        from worthlesstask import decoy as decoy_module

        with mock.patch.object(app_module, "ensure_decoy", return_value=decoy), \
             mock.patch.object(app_module, "executable_name_for", return_value="endfield.exe"), \
             mock.patch.object(decoy_module, "is_frozen", return_value=True):
            command = app_module._autostart_command(self._args(config))
        task = command[command.index("/tr") + 1]
        self.assertIn("--worker", task)
        self.assertNotIn(" -m ", task)

    @unittest.skipUnless(IS_WINDOWS, "autostart is Windows-only")
    def test_a_relative_config_is_made_absolute(self):
        """The task starts in the task scheduler's directory, not the user's shell."""
        config = self._config_file()
        task = self._task_string(config)
        marker = "--config "
        after = task[task.index(marker) + len(marker):].split('"')[0]
        self.assertTrue(Path(after).is_absolute(), after)

    @unittest.skipUnless(IS_WINDOWS, "autostart is Windows-only")
    def test_missing_config_is_reported_not_crashed(self):
        with mock.patch("worthlesstask.config.schema.find_config_file", return_value=None):
            with self.assertRaises(app_module.AutostartError) as ctx:
                app_module._autostart_command(self._args(None))
        self.assertIn("config", str(ctx.exception).lower())

    @unittest.skipUnless(IS_WINDOWS, "autostart is Windows-only")
    def test_remove_builds_a_delete_command(self):
        args = self._args()
        args.remove = True
        command = app_module._autostart_command(args)
        self.assertEqual(command[:3], ["schtasks", "/delete", "/tn"])

    def test_presence_requires_a_source_of_truth(self):
        """presence takes either a library entry or a config file — never neither."""
        with self.assertRaises(SystemExit):
            app_module.main(["presence"])


if __name__ == "__main__":
    unittest.main(verbosity=2)
