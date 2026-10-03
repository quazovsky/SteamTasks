"""Logs must not quietly record what the user searched for, and no route may read a
file of arbitrary size into memory.
"""

from __future__ import annotations

import unittest
from unittest import mock

from worthlesstask.web.server import redact_request


class TestRequestRedaction(unittest.TestCase):
    def test_a_search_query_is_removed(self):
        line = 'GET /api/search?q=Half%20Life%20Alyx HTTP/1.1'
        redacted = redact_request(line)
        self.assertNotIn("Half", redacted)
        self.assertNotIn("Alyx", redacted)
        self.assertIn("/api/search", redacted)
        self.assertIn("<redacted>", redacted)

    def test_other_queries_are_left_alone(self):
        """Only the paths whose query holds user input are touched."""
        line = "GET /api/state?x=1 HTTP/1.1"
        self.assertEqual(redact_request(line), line)

    def test_the_method_and_status_survive(self):
        line = 'GET /api/search?q=secret HTTP/1.1'
        self.assertTrue(redact_request(line).startswith("GET "))

    def test_a_line_without_a_query_is_untouched(self):
        line = "GET /api/state HTTP/1.1"
        self.assertEqual(redact_request(line), line)

    def test_nothing_breaks_on_an_empty_line(self):
        self.assertEqual(redact_request(""), "")


class TestLogMessageRedacts(unittest.TestCase):
    def test_the_handler_writes_the_redacted_line(self):
        from worthlesstask.web.server import Handler

        handler = object.__new__(Handler)
        handler.dashboard = mock.Mock()
        handler.log_message("GET /api/search?q=secret HTTP/1.1")
        written = handler.dashboard.log.debug.call_args[0][0]
        self.assertNotIn("secret", written)
        self.assertIn("<redacted>", written)


class TestIconSizeLimit(unittest.TestCase):
    """Uploads are capped at 2 MiB, but serving must not trust the folder."""

    def test_an_oversized_icon_is_refused(self):
        import tempfile
        from pathlib import Path

        from worthlesstask.library import MAX_ICON_BYTES, Library

        root = Path(tempfile.mkdtemp())
        library = Library(path=root / "library.json", icons_dir=root / "icons")
        library.add("The Forest", "2", executable="theforest.exe")
        icons = root / "icons"
        icons.mkdir(parents=True, exist_ok=True)
        (icons / "the-forest.ico").write_bytes(b"\x00\x00\x01\x00" + b"x" * (MAX_ICON_BYTES + 1))
        library.update("the-forest", icon="the-forest.ico")

        path = library.icon_path("the-forest")
        self.assertIsNotNone(path)
        self.assertGreater(path.stat().st_size, MAX_ICON_BYTES)

    def test_a_normal_icon_is_served(self):
        import tempfile
        from pathlib import Path

        from worthlesstask.library import Library

        root = Path(tempfile.mkdtemp())
        library = Library(path=root / "library.json", icons_dir=root / "icons")
        library.add("The Forest", "2", executable="theforest.exe")
        icons = root / "icons"
        icons.mkdir(parents=True, exist_ok=True)
        (icons / "the-forest.ico").write_bytes(b"\x00\x00\x01\x00" + b"x" * 512)
        library.update("the-forest", icon="the-forest.ico")

        path = library.icon_path("the-forest")
        self.assertIsNotNone(path)
        self.assertEqual(path.read_bytes()[:4], b"\x00\x00\x01\x00")


if __name__ == "__main__":
    unittest.main(verbosity=2)
