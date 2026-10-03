"""Library persistence, slugs, queue and icon handling."""

from __future__ import annotations

import json
import sys
import tempfile
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from worthlesstask.library import Entry, Library, LibraryError, is_ico, make_slug

ICO = b"\x00\x00\x01\x00" + b"\x00" * 60


class LibraryTestCase(unittest.TestCase):
    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        self.root = Path(self._tmp.name)
        self.library = Library(path=self.root / "library.json", icons_dir=self.root / "icons")

    def tearDown(self):
        self._tmp.cleanup()


class TestSlugs(unittest.TestCase):
    def test_basic(self):
        self.assertEqual(make_slug("Dead by Daylight"), "dead-by-daylight")

    def test_punctuation_and_case(self):
        self.assertEqual(make_slug("ARKNIGHTS: ENDFIELD"), "arknights-endfield")

    def test_empty_falls_back(self):
        self.assertEqual(make_slug("!!!"), "game")


class TestIcoDetection(unittest.TestCase):
    def test_valid(self):
        self.assertTrue(is_ico(ICO))

    def test_png_is_not_an_ico(self):
        self.assertFalse(is_ico(b"\x89PNG\r\n\x1a\n"))

    def test_png_to_ico_covers_shell_sizes(self):
        import struct

        from worthlesstask.iconfile import png_to_ico

        png = TestCatalogArt._png(8)
        blob = png_to_ico(png)
        count = struct.unpack("<H", blob[4:6])[0]
        sizes = set()
        for i in range(count):
            entry = blob[6 + i * 16:6 + (i + 1) * 16]
            width, height = entry[0], entry[1]
            sizes.add(width or 256)
            sizes.add(height or 256)
        for size in (16, 32, 48, 64):
            self.assertIn(size, sizes)


class TestEntries(LibraryTestCase):
    def test_add_and_get(self):
        entry = self.library.add("Dead by Daylight", "357607133254254632", executable="dbd.exe")
        self.assertEqual(entry.slug, "dead-by-daylight")
        self.assertIs(self.library.get("dead-by-daylight"), entry)

    def test_add_is_idempotent_by_name(self):
        self.library.add("PEAK", "1384276457596911676", executable="peak.exe")
        self.library.add("PEAK", "1384276457596911676", executable="peak.exe")
        self.assertEqual(len(self.library.entries()), 1)

    def test_duplicate_slug_gets_a_suffix(self):
        self.library.add("Game", "1")
        entry = self.library.add("game", "2")
        self.assertEqual(entry.slug, "game")
        self.assertEqual(len(self.library.entries()), 1)

    def test_remove(self):
        self.library.add("PEAK", "1")
        self.assertTrue(self.library.remove("peak"))
        self.assertFalse(self.library.remove("peak"))
        self.assertEqual(self.library.entries(), [])

    def test_update(self):
        self.library.add("PEAK", "1")
        self.library.update("peak", minutes=30, details="Playing")
        self.assertEqual(self.library.get("peak").minutes, 30)
        self.assertEqual(self.library.get("peak").details, "Playing")

    def test_update_unknown_slug(self):
        with self.assertRaises(LibraryError):
            self.library.update("nope", minutes=5)

    def test_default_duration(self):
        self.library.add("PEAK", "1")
        self.assertEqual(self.library.get("peak").duration_minutes, 15)
        self.library.update("peak", minutes=7)
        self.assertEqual(self.library.get("peak").duration_minutes, 7)


class TestPersistence(LibraryTestCase):
    def test_round_trip(self):
        self.library.add("PEAK", "1384276457596911676", executable="peak.exe")
        self.library.set_queue(["peak"])

        reopened = Library(path=self.root / "library.json", icons_dir=self.root / "icons")
        self.assertEqual(len(reopened.entries()), 1)
        self.assertEqual(reopened.queue, ["peak"])
        self.assertEqual(reopened.get("peak").executable, "peak.exe")

    def test_computed_fields_are_not_written(self):
        self.library.add("PEAK", "1")
        raw = json.loads((self.root / "library.json").read_text(encoding="utf-8"))
        self.assertNotIn("icon_url", raw["games"][0])
        self.assertNotIn("duration_minutes", raw["games"][0])

    def test_missing_file_is_an_empty_library(self):
        self.assertEqual(self.library.entries(), [])

    def test_corrupt_file_raises(self):
        (self.root / "library.json").write_text("{not json", encoding="utf-8")
        with self.assertRaises(LibraryError):
            Library(path=self.root / "library.json", icons_dir=self.root / "icons")

    def test_entries_without_a_name_are_skipped(self):
        (self.root / "library.json").write_text(
            json.dumps({"games": [{"slug": "x"}, {"game_name": "Good", "application_id": "1"}]}),
            encoding="utf-8",
        )
        library = Library(path=self.root / "library.json", icons_dir=self.root / "icons")
        self.assertEqual([e.game_name for e in library.entries()], ["Good"])


class TestQueue(LibraryTestCase):
    def test_set_queue_filters_unknown_slugs(self):
        self.library.add("PEAK", "1")
        self.assertEqual(self.library.set_queue(["peak", "ghost"]), ["peak"])

    def test_remove_drops_from_queue(self):
        self.library.add("PEAK", "1")
        self.library.set_queue(["peak"])
        self.library.remove("peak")
        self.assertEqual(self.library.queue, [])


class TestIcons(LibraryTestCase):
    def test_store_valid_ico(self):
        self.library.add("PEAK", "1")
        entry = self.library.set_icon("peak", ICO, "peak.ico")
        self.assertEqual(entry.icon, "peak.ico")
        path = self.library.icon_path("peak")
        self.assertTrue(path.exists())
        self.assertEqual(path.read_bytes(), ICO)

    def test_reject_empty(self):
        self.library.add("PEAK", "1")
        with self.assertRaises(LibraryError):
            self.library.set_icon("peak", b"", "peak.ico")

    def test_reject_oversized(self):
        self.library.add("PEAK", "1")
        with self.assertRaises(LibraryError):
            self.library.set_icon("peak", b"x" * (3 * 1024 * 1024), "peak.ico")

    def test_mislabelled_ico_is_rejected(self):
        self.library.add("PEAK", "1")
        with self.assertRaises(LibraryError):
            self.library.set_icon("peak", b"not an icon", "peak.ico")

    def test_png_is_kept_for_the_dashboard(self):
        self.library.add("PEAK", "1")
        entry = self.library.set_icon("peak", b"\x89PNG\r\n\x1a\nrest", "peak.png")
        self.assertEqual(entry.icon, "peak.png")

    def test_replacing_an_icon_removes_the_old_file(self):
        self.library.add("PEAK", "1")
        self.library.set_icon("peak", ICO, "peak.ico")
        self.library.set_icon("peak", b"\x89PNG\r\n\x1a\nrest", "peak.png")
        self.assertFalse((self.root / "icons" / "peak.ico").exists())
        self.assertTrue((self.root / "icons" / "peak.png").exists())

    def test_unknown_slug(self):
        with self.assertRaises(LibraryError):
            self.library.set_icon("ghost", ICO, "g.ico")


class TestCatalogArt(LibraryTestCase):
    """The window shows the same catalogue art the dashboard shows."""

    @staticmethod
    def _png(size=4):
        import struct
        import zlib

        rows = b"".join(b"\x00" + bytes([200, 100, 40, 255]) * size for _ in range(size))

        def chunk(tag, data):
            return (struct.pack(">I", len(data)) + tag + data
                    + struct.pack(">I", zlib.crc32(tag + data) & 0xFFFFFFFF))

        return (b"\x89PNG\r\n\x1a\n"
                + chunk(b"IHDR", struct.pack(">IIBBBBB", size, size, 8, 6, 0, 0, 0))
                + chunk(b"IDAT", zlib.compress(rows))
                + chunk(b"IEND", b""))

    def _fake_urlopen(self, data):
        from unittest import mock

        response = mock.MagicMock()
        response.read.return_value = data
        context = mock.MagicMock()
        context.__enter__.return_value = response
        context.__exit__.return_value = False
        return mock.patch("urllib.request.urlopen", return_value=context)

    def test_fetch_caches_png_and_ico(self):
        from worthlesstask.iconfile import is_png

        self.library.add("PEAK", "1", catalog_icon_url="https://cdn.example/i.png")
        with self._fake_urlopen(self._png()):
            ico = self.library.fetch_catalog_icon("peak")
        self.assertTrue(ico.is_file())
        self.assertTrue(is_png((self.root / "icons" / "peak.auto.png").read_bytes()))
        self.assertEqual(self.library.window_icon_path("peak"), ico)
        self.assertEqual(self.library.site_icon_path("peak"),
                         (self.root / "icons" / "peak.auto.png").resolve())

    def test_fetch_uses_cache_without_network(self):
        from unittest import mock

        self.library.add("PEAK", "1", catalog_icon_url="https://cdn.example/i.png")
        with self._fake_urlopen(self._png()):
            first = self.library.fetch_catalog_icon("peak")
        with mock.patch("urllib.request.urlopen",
                        side_effect=AssertionError("must not refetch")):
            self.assertEqual(self.library.fetch_catalog_icon("peak"), first)

    def test_fetch_rejects_non_png(self):
        self.library.add("PEAK", "1", catalog_icon_url="https://cdn.example/i.png")
        with self._fake_urlopen(b"not a png"):
            self.assertIsNone(self.library.fetch_catalog_icon("peak"))

    def test_fetch_retries_with_png_extension(self):
        """Older entries keep extensionless URLs; ``+.png`` saves them."""
        from unittest import mock

        self.library.add("PEAK", "1", catalog_icon_url="https://cdn.example/i")
        png = self._png()
        response = mock.MagicMock()
        response.read.return_value = png
        context = mock.MagicMock()
        context.__enter__.return_value = response
        context.__exit__.return_value = False

        def fake_open(request, timeout=None):
            url = request.full_url if hasattr(request, "full_url") else request
            if url.endswith(".png"):
                return context
            raise ValueError("404")

        with mock.patch("urllib.request.urlopen", side_effect=fake_open):
            ico = self.library.fetch_catalog_icon("peak")
        self.assertTrue(ico.is_file())

    def test_fetch_without_url_is_none(self):
        self.library.add("PEAK", "1")
        self.assertIsNone(self.library.fetch_catalog_icon("peak"))

    def test_upload_wins_over_catalogue_art(self):
        self.library.add("PEAK", "1", catalog_icon_url="https://cdn.example/i.png")
        with self._fake_urlopen(self._png()):
            self.library.fetch_catalog_icon("peak")
        self.library.set_icon("peak", ICO, "peak.ico")
        self.assertEqual(self.library.window_icon_path("peak"),
                         (self.root / "icons" / "peak.ico").resolve())

    def test_remove_cleans_cached_art(self):
        self.library.add("PEAK", "1", catalog_icon_url="https://cdn.example/i.png")
        with self._fake_urlopen(self._png()):
            self.library.fetch_catalog_icon("peak")
        self.library.remove("peak")
        self.assertFalse((self.root / "icons" / "peak.auto.ico").exists())
        self.assertFalse((self.root / "icons" / "peak.auto.png").exists())


class TestEntrySerialisation(unittest.TestCase):
    def test_from_dict_ignores_unknown_keys(self):
        entry = Entry.from_dict(
            {"slug": "x", "game_name": "X", "icon_url": "/api/icon/x", "bogus": 1}
        )
        self.assertEqual(entry.slug, "x")
        self.assertFalse(hasattr(entry, "bogus"))

    def test_to_dict_adds_computed_fields(self):
        data = Entry(slug="x", game_name="X", icon="x.ico").to_dict()
        self.assertEqual(data["icon_url"], "/api/icon/x")
        self.assertEqual(data["duration_minutes"], 15)


if __name__ == "__main__":
    unittest.main(verbosity=2)


class TestLibraryRecovery(unittest.TestCase):
    """One damaged file must not stop the app from starting."""

    def setUp(self):
        import tempfile

        self._tmp = tempfile.TemporaryDirectory()
        self.root = Path(self._tmp.name)
        self.path = self.root / "library.json"

    def tearDown(self):
        self._tmp.cleanup()

    def _library(self):
        return Library(path=self.path, icons_dir=self.root / "icons")

    def _seed(self):
        library = self._library()
        library.add("The Forest", "363409179668512788", executable="theforest.exe")
        library.set_queue(["the-forest"])
        return library

    def test_save_keeps_a_backup_of_the_previous_file(self):
        library = self._seed()
        library.add("PEAK", "1384276457596911676", executable="peak.exe")
        self.assertTrue(self.path.with_name("library.json.bak").exists())
        backup = json.loads(self.path.with_name("library.json.bak").read_text(encoding="utf-8"))
        self.assertEqual([g["game_name"] for g in backup["games"]], ["The Forest"])

    def test_an_empty_main_file_falls_back_to_the_backup(self):
        library = self._seed()
        library.add("PEAK", "1384276457596911676", executable="peak.exe")
        self.path.write_text("   " * 40, encoding="utf-8")
        recovered = self._library()
        self.assertEqual([e.game_name for e in recovered.entries()], ["The Forest"])

    def test_a_half_written_temp_file_is_used_when_it_is_all_there_is(self):
        self._seed()
        self.path.with_name("library.json.bak").unlink()
        self.path.write_text("not json at all", encoding="utf-8")
        self.path.with_name("library.json.writing").write_text(
            json.dumps({"games": [{"slug": "peak", "game_name": "PEAK", "application_id": "1",
                                   "executable": "peak.exe"}], "queue": []}),
            encoding="utf-8")
        recovered = self._library()
        self.assertEqual([e.game_name for e in recovered.entries()], ["PEAK"])

    def test_everything_damaged_is_still_a_clear_error(self):
        self._seed()
        for suffix in ("", ".bak", ".writing"):
            self.path.with_name("library.json" + suffix).write_text("garbage", encoding="utf-8")
        with self.assertRaises(LibraryError):
            self._library()

    def test_a_missing_file_is_an_empty_library_not_an_error(self):
        self.assertEqual(self._library().entries(), [])
