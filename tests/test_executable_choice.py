"""The impersonated executable must be the real game binary.

Discord lists several executables per game and the first is frequently not the game:
a launcher, a VR build, an installer. Naming the wrong one produces a presence that
looks correct in the profile while Discord's process scanner never matches it — so no
quest is ever credited. This is the difference that matters, and it is easy to get
silently wrong.
"""

from __future__ import annotations

import unittest
from pathlib import Path
from unittest import mock

from worthlesstask import steamlib


class TestResolveImageName(unittest.TestCase):
    def setUp(self):
        self._tmp = __import__("tempfile").TemporaryDirectory()
        self.install = Path(self._tmp.name)
        self.addCleanup(self._tmp.cleanup)

    def _install_with(self, *names):
        """A real install folder; resolution reads it the way production does."""
        for name in names:
            (self.install / name).write_bytes(b"MZ" + b"\0" * 16)
        return mock.patch.object(steamlib, "install_dir", return_value=self.install)

    def test_prefers_a_name_present_in_the_install(self):
        """The catalogue's first entry is a launcher; the real binary is later."""
        names = ["marvelrivals/marvelrivals_launcher.exe", "marvel-win64-shipping.exe"]
        with self._install_with("marvel-win64-shipping.exe"):
            chosen, source = steamlib.resolve_image_name("Marvel Rivals", "1", names)
        self.assertEqual(chosen, "marvel-win64-shipping.exe")
        self.assertEqual(source, "installed")

    def test_avoids_a_vr_build_when_the_game_is_not_installed(self):
        names = ["the forest/theforestvr.exe", "theforest.exe"]
        with mock.patch.object(steamlib, "install_dir", return_value=None):
            chosen, source = steamlib.resolve_image_name("The Forest", "2", names)
        self.assertEqual(chosen, "theforest.exe")  # the VR build is not chosen
        self.assertEqual(source, "catalogue")

    def test_strips_a_directory_prefix(self):
        names = ["subdir/game.exe"]
        chosen, _ = steamlib.resolve_image_name("Game", "3", names)
        self.assertEqual(chosen, "game.exe")

    def test_falls_back_to_a_derived_name(self):
        chosen, source = steamlib.resolve_image_name("Some Unknown Game", "4", [])
        self.assertEqual(chosen, "someunknowngame.exe")
        self.assertEqual(source, "derived")

    def test_no_name_and_no_game_gives_nothing(self):
        self.assertEqual(steamlib.resolve_image_name("", "5", []), (None, "derived"))

    def test_an_unreadable_install_does_not_break_resolution(self):
        with mock.patch.object(steamlib, "installed_executables", side_effect=OSError("denied")):
            chosen, source = steamlib.resolve_image_name("The Forest", "2",
                                                         ["theforestvr.exe", "theforest.exe"])
        self.assertEqual(chosen, "theforest.exe")

    def test_installed_matching_is_case_insensitive(self):
        """Windows installs differ in case from the catalogue."""
        names = ["DeadByDaylight.exe"]
        with self._install_with("deadbydaylight.exe"):
            chosen, source = steamlib.resolve_image_name("Dead by Daylight", "6", names)
        self.assertEqual(chosen, "DeadByDaylight.exe")  # catalogue spelling preserved
        self.assertEqual(source, "installed")


class TestLaunchUsesTheSameResolution(unittest.TestCase):
    """`launch` and the multi-game flow must agree, or one of them lies."""

    def _config(self):
        from worthlesstask.config.schema import AppConfig

        return AppConfig(client_id="1461154307171811401", game_name="Marvel Rivals")

    def test_launch_prefers_the_installed_binary(self):
        from worthlesstask.cli.app import launch_image_name

        config = self._config()
        install = Path(__import__("tempfile").mkdtemp())
        (install / "marvel-win64-shipping.exe").write_bytes(b"MZ" + b"\0" * 16)
        with mock.patch("worthlesstask.cli.app.DetectableIndex") as index, \
             mock.patch.object(steamlib, "install_dir", return_value=install):
            index.return_value.by_id.return_value = mock.Mock(
                executables=["marvelrivals_launcher.exe", "marvel-win64-shipping.exe"])
            chosen, source = launch_image_name(config)

        self.assertEqual(chosen, "marvel-win64-shipping.exe")
        self.assertEqual(source, "installed")

    def test_launch_survives_a_catalogue_failure(self):
        """Offline or a broken cache must still produce a launchable name."""
        from worthlesstask.cli.app import launch_image_name

        with mock.patch("worthlesstask.cli.app.DetectableIndex",
                        side_effect=OSError("no network")), \
             mock.patch("worthlesstask.decoy.executable_name_for",
                        side_effect=OSError("no network")):
            chosen, source = launch_image_name(self._config())
        self.assertEqual(chosen, "marvelrivals.exe")  # derived from the game name
        self.assertEqual(source, "derived")

    def test_add_and_launch_agree(self):
        """Both go through steamlib.resolve_image_name — assert that, not a copy."""
        import inspect

        from worthlesstask.cli import multi

        source = inspect.getsource(multi.cmd_add)
        self.assertIn("resolve_image_name", source)
        # The old inline installed/pick/derived chain is gone from cmd_add.
        self.assertNotIn("pick_executable", source)


if __name__ == "__main__":
    unittest.main(verbosity=2)
