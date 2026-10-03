"""Choosing the executable name: prefer what the real install actually contains."""

from __future__ import annotations

import tempfile
import unittest
from pathlib import Path

from worthlesstask.steamlib import install_dir, installed_executables, library_roots, pick_executable

DBD = ["deadbydaylight-win64-shipping.exe", "dead by daylight/deadbydaylight.exe",
       "deadbydaylight-egs-shipping.exe", "deadbydaylight.exe"]
FOREST = ["theforest.exe", "the forest/theforestvr.exe"]
PEAK = ["peak/peak.exe"]


class TestPickExecutable(unittest.TestCase):
    def test_prefers_a_name_present_in_the_install(self):
        name, source = pick_executable(DBD, {"deadbydaylight.exe", "easyanticheat_eos_setup.exe"})
        self.assertEqual(name, "deadbydaylight.exe")
        self.assertEqual(source, "installed")

    def test_install_match_is_case_insensitive(self):
        name, source = pick_executable(FOREST, {"theforest.exe", "theforestvr.exe"})
        self.assertEqual(name, "theforest.exe")
        self.assertEqual(source, "installed")

    def test_falls_back_to_the_plainest_catalogue_name(self):
        self.assertEqual(pick_executable(DBD, set()), ("deadbydaylight-win64-shipping.exe", "catalogue"))
        self.assertEqual(pick_executable(FOREST, set()), ("theforest.exe", "catalogue"))
        self.assertEqual(pick_executable(PEAK, set()), ("peak.exe", "catalogue"))

    def test_never_picks_an_installer_or_launcher(self):
        """Observed in the live catalogue: both games listed a decoy-looking name."""
        runescape = ["win64/rsdragonwilds-win64-shipping.exe",
                     "rsdragonwilds/epiconlineservicesinstaller.exe"]
        self.assertEqual(pick_executable(runescape, set()),
                         ("rsdragonwilds-win64-shipping.exe", "catalogue"))

        rivals = ["marvelrivals/marvelrivals_launcher.exe", "win64/marvel-win64-test.exe",
                  "win64/marvel.exe", "win64/marvel-win64-shipping.exe"]
        self.assertEqual(pick_executable(rivals, set()), ("marvel-win64-shipping.exe", "catalogue"))

    def test_prefers_the_non_vr_build(self):
        forest = ["the forest/theforestvr.exe", "theforest.exe"]
        self.assertEqual(pick_executable(forest, set()), ("theforest.exe", "catalogue"))

    def test_install_still_outranks_the_guess(self):
        runescape = ["win64/rsdragonwilds-win64-shipping.exe",
                     "rsdragonwilds/epiconlineservicesinstaller.exe"]
        name, source = pick_executable(runescape, {"epiconlineservicesinstaller.exe"})
        self.assertEqual((name, source), ("epiconlineservicesinstaller.exe", "installed"))

    def test_falls_back_to_all_names_when_every_name_is_rejected(self):
        self.assertEqual(pick_executable(["game-launcher.exe"], set()),
                         ("game-launcher.exe", "catalogue"))

    def test_strips_any_directory_part(self):
        self.assertEqual(pick_executable(PEAK, set())[0], "peak.exe")

    def test_no_catalogue_names_means_derived(self):
        self.assertEqual(pick_executable([], {"game.exe"}), (None, "derived"))

    def test_ignores_installed_files_that_are_not_catalogue_names(self):
        name, source = pick_executable(DBD, {"unitycrashhandler64.exe"})
        self.assertEqual((name, source), ("deadbydaylight-win64-shipping.exe", "catalogue"))

    def test_blank_candidates_are_dropped(self):
        self.assertEqual(pick_executable(["", "  "], set()), (None, "derived"))


class TestInstallLookup(unittest.TestCase):
    def test_library_roots_are_directories(self):
        for root in library_roots():
            self.assertTrue(root.is_dir(), root)

    def test_install_dir_of_an_uninstalled_app_is_none(self):
        self.assertIsNone(install_dir("999999999"))

    def test_install_dir_rejects_a_non_numeric_id(self):
        self.assertIsNone(install_dir("../../etc"))

    def test_installed_executables_of_an_uninstalled_app_is_empty(self):
        self.assertEqual(installed_executables("999999999"), set())

    def test_reads_a_synthetic_library(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            game = root / "steamapps" / "common" / "Some Game"
            game.mkdir(parents=True)
            (game / "SomeGame.exe").write_bytes(b"MZ")
            (game / "UnityCrashHandler64.exe").write_bytes(b"MZ")
            (root / "steamapps" / "appmanifest_12345.acf").write_text(
                '"AppState"\n{\n\t"appid"\t"12345"\n\t"installdir"\t"Some Game"\n}\n',
                encoding="utf-8",
            )
            self.assertEqual(install_dir("12345", [root]), game)
            self.assertEqual(installed_executables("12345"), set(), "default roots do not include the temp lib")

    def test_library_roots_include_paths_from_vdf(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            extra = root / "extra-library"
            (extra / "steamapps").mkdir(parents=True)
            (root / "steamapps").mkdir(parents=True, exist_ok=True)
            (root / "steamapps" / "libraryfolders.vdf").write_text(
                '"libraryfolders"\n{\n\t"1"\n\t{\n\t\t"path"\t\t"%s"\n\t}\n}\n' % str(extra).replace("\\", "\\\\"),
                encoding="utf-8",
            )
            roots = library_roots(root)
            self.assertIn(root, roots)
            self.assertIn(extra, roots)


if __name__ == "__main__":
    unittest.main()


class TestWorkerIdentity(unittest.TestCase):
    """A copied worker must recognise itself from its own file name."""

    def setUp(self):
        import tempfile

        from worthlesstask.__main__ import worker_slug_for

        self._tmp = tempfile.TemporaryDirectory()
        self.root = Path(self._tmp.name)
        self.worker_slug_for = worker_slug_for
        (self.root / "library.json").write_text(
            '{"games": [{"slug": "the-forest", "game_name": "The Forest",'
            ' "executable": "theforest.exe"},'
            ' {"slug": "peak", "game_name": "PEAK", "executable": "peak.exe"},'
            ' {"slug": "no-exe", "game_name": "None", "executable": null}],'
            ' "queue": []}',
            encoding="utf-8",
        )

    def tearDown(self):
        self._tmp.cleanup()

    def test_matches_the_worker_name(self):
        self.assertEqual(self.worker_slug_for("theforest.exe", self.root), "the-forest")

    def test_match_is_case_insensitive(self):
        self.assertEqual(self.worker_slug_for("TheForest.EXE", self.root), "the-forest")

    def test_the_base_executable_is_not_a_worker(self):
        self.assertIsNone(self.worker_slug_for("worthlesstask-v3.exe", self.root))

    def test_an_unrelated_name_is_not_a_worker(self):
        self.assertIsNone(self.worker_slug_for("chrome.exe", self.root))

    def test_a_missing_library_is_not_a_worker(self):
        self.assertIsNone(self.worker_slug_for("theforest.exe", self.root / "nope"))
