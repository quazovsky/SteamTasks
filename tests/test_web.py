"""The dashboard HTTP surface, exercised over a real loopback socket."""

from __future__ import annotations

import json
import sys
import tempfile
import threading
import unittest
import urllib.error
import urllib.request
from pathlib import Path
from unittest import mock

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from worthlesstask.library import Library
from worthlesstask.manager import PresenceManager
from worthlesstask.web.server import Dashboard, is_dashboard_running, make_server

ICO = b"\x00\x00\x01\x00" + b"\x00" * 60
HOST = "127.0.0.1"


class FakeProcess:
    def __init__(self, pid=4242):
        self.pid = pid
        self.exit_code = None

    def poll(self):
        return self.exit_code

    def terminate(self):
        self.exit_code = 0

    def kill(self):
        self.exit_code = 0

    def wait(self, timeout=None):
        self.exit_code = 0
        return 0


class DashboardTestCase(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls._tmp = tempfile.TemporaryDirectory()
        cls.root = Path(cls._tmp.name)
        cls.library = Library(path=cls.root / "library.json", icons_dir=cls.root / "icons")
        cls.library.add("ARKNIGHTS: ENDFIELD", "1461154307171811401", executable="endfield.exe")
        cls.library.add("The Forest", "363409179668512788", executable="theforestvr.exe")

        cls.spawned: list[list[str]] = []

        def spawn(argv, env, cwd):
            cls.spawned.append(list(argv))
            return FakeProcess()

        for name in ("endfield.exe", "theforestvr.exe"):
            (cls.root / name).write_bytes(b"MZ" + b"\0" * 64)
        cls._decoy_patch = mock.patch(
            "worthlesstask.manager.ensure_decoy", side_effect=lambda name, logger=None, client_id=None: cls.root / name
        )
        cls._decoy_patch.start()

        cls.manager = PresenceManager(
            cls.library, package_root=cls.root, spawn=spawn, runtime_path=cls.root / "runtime.json"
        )
        cls.dashboard = Dashboard(cls.library, cls.manager)

        # A resolver that never touches the network.
        cls.dashboard.resolver = mock.Mock()
        cls.dashboard.resolver.index = mock.Mock()
        cls.dashboard.resolver.index.search.return_value = []

        cls.server = make_server(cls.dashboard, HOST, 0)
        cls.port = cls.server.server_address[1]
        cls.thread = threading.Thread(target=cls.server.serve_forever, daemon=True)
        cls.thread.start()

    @classmethod
    def tearDownClass(cls):
        cls.server.shutdown()
        cls.server.server_close()
        cls._decoy_patch.stop()
        cls._tmp.cleanup()

    # -- helpers -------------------------------------------------------- #
    def url(self, path: str) -> str:
        return f"http://{HOST}:{self.port}{path}"

    def get(self, path: str):
        with urllib.request.urlopen(self.url(path), timeout=10) as response:
            return response.status, response.read(), response.headers

    def get_json(self, path: str):
        status, body, _ = self.get(path)
        return status, json.loads(body.decode("utf-8"))

    def post_json(self, path: str, payload: dict | None = None):
        data = json.dumps(payload or {}).encode("utf-8")
        request = urllib.request.Request(
            self.url(path), data=data, method="POST",
            headers={"Content-Type": "application/json"},
        )
        with urllib.request.urlopen(request, timeout=10) as response:
            return response.status, json.loads(response.read().decode("utf-8"))


class TestStaticAndState(DashboardTestCase):
    def test_page_is_served(self):
        status, body, headers = self.get("/")
        self.assertEqual(status, 200)
        self.assertIn(b"worthlesstask", body)
        self.assertIn("text/html", headers["Content-Type"])

    def test_every_js_hook_exists_in_the_markup(self):
        """A missing id freezes the panel: render() throws on text(null),
        the catch re-renders and throws again, and poll() never reschedules,
        leaving every button gray (2026-09-26: id="globalError" was lost in
        the compact redesign)."""
        import re

        from worthlesstask.web.page import PAGE

        # Markup is everything outside the script blocks (the first script
        # sits in <head>, before <body> even starts).
        html = re.sub(r"<script>.*?</script>", "", PAGE, flags=re.DOTALL)
        hooks = set()
        for body in re.findall(r"<script>(.*?)</script>", PAGE, flags=re.DOTALL):
            # $('id'), $(`id`), getElementById('id') — static names only.
            hooks.update(re.findall(r"\$\(\s*['\"`]([A-Za-z][\w-]*)['\"`]\s*\)", body))
            hooks.update(re.findall(r"getElementById\(\s*['\"`]([A-Za-z][\w-]*)['\"`]\s*\)", body))
        missing = sorted(h for h in hooks if f'id="{h}"' not in html)
        self.assertEqual(missing, [])

    def test_buttons_have_no_motion_or_light_frames(self):
        """Buttons change state instantly and carry no whitish borders.

        No transition on any .btn rule, no press/hover transforms, no shine
        pseudo-element on .btn.primary, and no light border colors on buttons.
        """
        import re

        from worthlesstask.web.page import PAGE

        css = re.search(r"<style>(.*?)</style>", PAGE, re.DOTALL).group(1)
        for match in re.finditer(r"([^{}]*\.btn[^{}]*)\{([^{}]*)\}", css):
            selector, body = match.group(1), match.group(2)
            self.assertNotIn("transition", body, selector)
            self.assertNotIn("translateY(-1px)", body, selector)
            self.assertNotIn("scale(.985)", body, selector)
            for token in re.findall(r"border-color\s*:\s*([^;]+)", body):
                self.assertNotRegex(
                    token,
                    r"rgba\(255\s*,\s*255\s*,\s*255\s*,\s*\.(3|4|5|9)",
                    f"{selector}: light frame {token}",
                )
        self.assertNotIn(".btn.primary:after", css)

    def test_health(self):
        health = self.get_json("/api/health")[1]
        self.assertTrue(health["ok"])
        self.assertEqual(health["application"], "worthlesstask")
        # Derived from the package version, so this never drifts from it.
        from worthlesstask import __version__

        self.assertEqual(health["version"], __version__)

    def test_state_lists_games(self):
        _, payload = self.get_json("/api/state")
        self.assertEqual(len(payload["games"]), 2)
        self.assertIn("queue", payload)

    def test_unknown_route_is_404(self):
        with self.assertRaises(urllib.error.HTTPError) as ctx:
            self.get("/api/nope")
        self.assertEqual(ctx.exception.code, 404)

    def test_is_dashboard_running_detects_us(self):
        self.assertTrue(is_dashboard_running(HOST, self.port))


class TestErrorCodes(DashboardTestCase):
    """A known failure must carry a code the page can render in any language."""

    def test_known_failure_carries_a_code(self):
        request = urllib.request.Request(
            self.url("/api/play"), data=json.dumps({"slug": ""}).encode("utf-8"),
            method="POST", headers={"Content-Type": "application/json"},
        )
        with self.assertRaises(urllib.error.HTTPError) as ctx:
            urllib.request.urlopen(request, timeout=10)
        payload = json.loads(ctx.exception.read().decode("utf-8"))
        self.assertIn("error", payload)
        # An unmapped message stays readable: the page falls back to this text.
        self.assertTrue(payload.get("code") is None or isinstance(payload["code"], str))

    def test_every_code_is_translated(self):
        from worthlesstask.web.i18n import EXACT_CODES, PREFIX_CODES, TRANSLATIONS

        codes = set(EXACT_CODES.values()) | set(PREFIX_CODES.values())
        for lang, table in TRANSLATIONS.items():
            self.assertEqual(set(table), codes, f"{lang} table does not match the code maps")
            for code in codes:
                self.assertTrue(table[code], f"{code} empty in {lang}")

    def test_code_lookup_is_stable(self):
        from worthlesstask.web.i18n import code_for

        # Fixed messages match exactly.
        self.assertEqual(code_for("Некорректный идентификатор игры"), "slug.invalid")
        self.assertEqual(code_for("Очередь должна быть списком игр"), "queue.not_list")
        # Interpolated messages match on their stable prefix.
        self.assertEqual(code_for("Игра 'ghost' не найдена в библиотеке"), "game.missing")
        self.assertEqual(code_for("EXE не найден: test-missing.exe"), "exe.missing")
        self.assertEqual(code_for("Проверьте параметры игры: bad id"), "game.invalid")
        # An unrecognised message keeps its own text on the client.
        self.assertIsNone(code_for("something the server has never said"))

    def test_known_error_response_carries_its_code(self):
        from worthlesstask.web.i18n import code_for

        request = urllib.request.Request(self.url("/api/prepare/@@@"), method="POST")
        with self.assertRaises(urllib.error.HTTPError) as ctx:
            urllib.request.urlopen(request, timeout=10)
        payload = json.loads(ctx.exception.read().decode("utf-8"))
        self.assertEqual(payload.get("code"), code_for(payload["error"]))
        self.assertEqual(payload["code"], "slug.invalid")


class TestGameRoutes(DashboardTestCase):
    def test_delete_unknown_game(self):
        request = urllib.request.Request(self.url("/api/games/ghost"), method="DELETE")
        with self.assertRaises(urllib.error.HTTPError) as ctx:
            urllib.request.urlopen(request, timeout=10)
        self.assertEqual(ctx.exception.code, 404)

    def test_bad_slug_is_rejected(self):
        request = urllib.request.Request(self.url("/api/games/../etc"), method="DELETE")
        with self.assertRaises(urllib.error.HTTPError) as ctx:
            urllib.request.urlopen(request, timeout=10)
        self.assertIn(ctx.exception.code, (400, 404))

    def test_add_game_uses_the_resolver(self):
        from worthlesstask.presence.resolver import Candidate

        candidate = Candidate(
            id="999", name="Test Game", score=100, matched_on="name-exact",
            executables=("testgame.exe",),
        )
        self.dashboard.resolver.resolve_by_name = mock.Mock(
            return_value=mock.Mock(application_id="999", candidate=candidate)
        )
        try:
            status, payload = self.post_json("/api/games", {"game_name": "Test Game"})
        finally:
            del self.dashboard.resolver.resolve_by_name
        self.assertEqual(status, 200)
        self.assertEqual(payload["slug"], "test-game")
        self.assertEqual(payload["executable"], "testgame.exe")
        self.library.remove("test-game")

    def test_add_without_a_name_fails(self):
        with self.assertRaises(urllib.error.HTTPError) as ctx:
            self.post_json("/api/games", {"game_name": "  "})
        self.assertEqual(ctx.exception.code, 400)


class TestControlRoutes(DashboardTestCase):
    def wait_operation(self):
        import time
        deadline = time.monotonic() + 5
        while time.monotonic() < deadline:
            _, state = self.get_json("/api/state")
            if state.get("operation") is None:
                return state
            threading.Event().wait(.01)
        self.fail("operation did not complete")

    def test_play_and_stop(self):
        code, payload = self.post_json("/api/play", {"slug": "arknights-endfield"})
        self.assertEqual(code, 202)
        payload = self.wait_operation()
        self.assertEqual(payload["active"]["slug"], "arknights-endfield")
        self.assertEqual(payload["active"]["rpc_state"], "connecting")
        code, _ = self.post_json("/api/stop")
        self.assertEqual(code, 202)
        self.assertIsNone(self.wait_operation()["active"])

    def test_play_unknown_slug(self):
        with self.assertRaises(urllib.error.HTTPError) as ctx:
            self.post_json("/api/play", {"slug": "ghost"})
        self.assertEqual(ctx.exception.code, 400)

    def test_queue_round_trip(self):
        _, payload = self.post_json("/api/queue", {"slugs": ["arknights-endfield"], "minutes": 20})
        self.assertEqual(payload["queue"], ["arknights-endfield"])
        self.assertEqual(self.library.get("arknights-endfield").minutes, 20)
        self.post_json("/api/queue", {"slugs": []})

    def test_queue_rejects_a_non_list(self):
        with self.assertRaises(urllib.error.HTTPError) as ctx:
            self.post_json("/api/queue", {"slugs": "arknights-endfield"})
        self.assertEqual(ctx.exception.code, 400)

    def test_queue_start_without_a_queue_does_not_start(self):
        self.post_json("/api/queue", {"slugs": []})
        _, payload = self.post_json("/api/queue/start")
        self.assertFalse(payload["started"])


class TestIconRoutes(DashboardTestCase):
    def test_upload_and_download(self):
        request = urllib.request.Request(
            self.url("/api/icon/the-forest"), data=ICO, method="POST",
            headers={"Content-Type": "application/octet-stream", "X-Filename": "forest.ico"},
        )
        with urllib.request.urlopen(request, timeout=10) as response:
            payload = json.loads(response.read().decode("utf-8"))
        self.assertEqual(payload["icon"], "the-forest.ico")

        status, body, headers = self.get("/api/icon/the-forest")
        self.assertEqual(status, 200)
        self.assertEqual(body, ICO)
        self.assertEqual(headers["Content-Type"], "image/x-icon")

    def test_missing_icon_is_404(self):
        with self.assertRaises(urllib.error.HTTPError) as ctx:
            self.get("/api/icon/arknights-endfield")
        self.assertEqual(ctx.exception.code, 404)

    def test_bad_icon_is_rejected(self):
        request = urllib.request.Request(
            self.url("/api/icon/the-forest"), data=b"nope", method="POST",
            headers={"X-Filename": "forest.ico"},
        )
        with self.assertRaises(urllib.error.HTTPError) as ctx:
            urllib.request.urlopen(request, timeout=10)
        self.assertEqual(ctx.exception.code, 400)

    def test_an_oversized_icon_on_disk_is_not_served(self):
        """Uploads are capped, but serving must not trust what is in the folder."""
        from worthlesstask.library import MAX_ICON_BYTES

        # Point the entry at an on-disk icon far larger than the upload cap.
        icons = self.library.icons_dir
        icons.mkdir(parents=True, exist_ok=True)
        (icons / "the-forest.ico").write_bytes(
            b"\x00\x00\x01\x00" + b"x" * (MAX_ICON_BYTES + 1))
        self.library.update("the-forest", icon="the-forest.ico")

        with self.assertRaises(urllib.error.HTTPError) as ctx:
            self.get("/api/icon/the-forest")
        self.assertEqual(ctx.exception.code, 413)


class TestSearchRoute(DashboardTestCase):
    def test_search_returns_results(self):
        from worthlesstask.presence.resolver import Candidate

        self.dashboard.resolver.index.search.return_value = [
            Candidate(id="1", name="X", score=100, matched_on="name-exact")
        ]
        _, payload = self.get_json("/api/search?q=x")
        self.assertEqual(payload["results"][0]["name"], "X")


if __name__ == "__main__":
    unittest.main(verbosity=2)
