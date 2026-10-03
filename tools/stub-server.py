"""Minimal stand-in for the real dashboard, used only to exercise client-side UI.

The real app server is blocked by the environment's safe-delete guard, but the modal
dialogs are pure client-side logic. This serves the real PAGE together with a small
fake /api/state so a browser can drive the dialogs for real.

    python tools/stub-server.py [port]
"""

from __future__ import annotations

import json
import sys
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

# Run as `python tools/stub-server.py`, so the script dir — not the repo root — is on
# sys.path. Put the repo root back so the package imports.
sys.path.insert(0, str(__import__("pathlib").Path(__file__).resolve().parents[1]))

from worthlesstask.web.page import PAGE  # noqa: E402

GAMES = [
    {
        "slug": "the-forest", "game_name": "The Forest", "application_id": "363409179668512788",
        "executable": "theforestvr.exe", "executable_source": "catalogue", "can_start": True,
        "worker_ready": True, "worker_path": None, "worker_error": None,
        "icon_url": None, "icon_version": "", "catalog_icon_url": None,
        "duration_minutes": 15, "availability_reason": None, "custom_icon": False,
    },
    {
        "slug": "marvel-rivals", "game_name": "Marvel Rivals", "application_id": "1",
        "executable": "marvel-win64-shipping.exe", "executable_source": "catalogue",
        "can_start": True, "worker_ready": True, "worker_path": None, "worker_error": None,
        "icon_url": None, "icon_version": "", "catalog_icon_url": None,
        "duration_minutes": 30, "availability_reason": None, "custom_icon": False,
    },
]

STATE = {
    "active": None, "operation": None, "queue": [],
    "next_switch_in_s": None, "last_error": None, "games": GAMES,
}


class Handler(BaseHTTPRequestHandler):
    def log_message(self, *args):
        pass  # keep the console quiet so the caller can parse the port line

    def _send(self, body: bytes, ctype: str, status: int = 200):
        self.send_response(status)
        self.send_header("Content-Type", ctype)
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def _json(self, payload, status: int = 200):
        self._send(json.dumps(payload).encode("utf-8"), "application/json", status)

    def do_GET(self):
        path = self.path.split("?", 1)[0]
        if path in ("/", "/index.html"):
            self._send(PAGE.encode("utf-8"), "text/html; charset=utf-8")
        elif path == "/api/state":
            self._json(STATE)
        elif path == "/api/health":
            self._json({"ok": True, "application": "worthlesstask", "version": "test", "pid": 0})
        else:
            self._json({"error": "not found", "code": "not_found"}, 404)

    def do_POST(self):
        length = int(self.headers.get("Content-Length") or 0)
        self.rfile.read(length)
        self._json({"ok": True})

    def do_DELETE(self):
        self._json({"ok": True})


def main() -> int:
    port = int(sys.argv[1]) if len(sys.argv) > 1 else 0
    server = ThreadingHTTPServer(("127.0.0.1", port), Handler)
    actual = server.server_address[1]
    print(f"STUB_PORT={actual}", flush=True)
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        pass
    return 0


if __name__ == "__main__":
    sys.exit(main())
