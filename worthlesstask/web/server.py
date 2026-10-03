"""Loopback-only dashboard with validated requests and asynchronous process control."""
from __future__ import annotations

import json
import os
import re
import threading
import urllib.parse
import urllib.request
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path

from ..core.errors import worthlesstaskError
from ..core.logging import get_logger
from ..library import MAX_ICON_BYTES, LibraryError
from ..manager import ManagerError
from ..paths import cache_dir
from ..decoy import derive_image_name, discard_decoy, validate_image_name
from .. import steamlib
from .. import __version__
from ..presence.identity import Identity, IdentityResolver
from ..presence.resolver import DetectableIndex
from .i18n import code_for
from .page import PAGE

#: Paths whose query string can hold something the user typed.
_SENSITIVE_QUERY = ("/api/search",)


def redact_request(line: str) -> str:
    """Drop query strings from a logged request line.

    Search terms are what someone was looking for — a game, or a name — and the log
    file outlives the reason for writing it. The path is kept so the log stays useful.
    """
    text = str(line)
    for prefix in _SENSITIVE_QUERY:
        if prefix in text:
            text = re.sub(re.escape(prefix) + r"\?[^\s]*", prefix + "?<redacted>", text)
    return text


DEFAULT_HOST = "127.0.0.1"
DEFAULT_PORT = 8787
APP_VERSION = __version__  # single source of truth: worthlesstask.__version__
MAX_BODY_BYTES = 4 * 1024 * 1024
SLUG_RE = re.compile(r"[a-z0-9][a-z0-9-]{0,63}")
ICON_TYPES = {".ico":"image/x-icon", ".png":"image/png", ".jpg":"image/jpeg",
              ".jpeg":"image/jpeg", ".bmp":"image/bmp", ".webp":"image/webp"}

class Dashboard:
    def __init__(self, library, manager, logger=None, resolver=None):
        self.library, self.manager = library, manager
        self.log = logger or get_logger()
        self.resolver = resolver or IdentityResolver(index=DetectableIndex(
            cache_path=cache_dir() / "detectable.json", logger=self.log))
        self._scheduler_stop = threading.Event()
        self._scheduler = None
        self._scheduler_lock = threading.Lock()
        self._catalog_lock = threading.Lock()
        self._mutation_lock = threading.RLock()
        self._quests_cache: list[dict] = []
        self._quests_ts: float = 0.0

    def _active_quests(self, force: bool = False) -> list[dict]:
        import time as _time
        now = _time.monotonic()
        if not force and self._quests_ts and (now - self._quests_ts) < 15.0:
            return self._quests_cache
        try:
            from ..presence.quests import discover_discord_quests
            quests = discover_discord_quests(logger=self.log)
            self._quests_cache = [
                q.to_dict() for q in quests if not q.completed and not q.is_expired
            ]
        except Exception:  # noqa: BLE001
            pass
        self._quests_ts = now
        return self._quests_cache

    def sync_quests(self, auto_add: bool = True) -> dict:
        from ..presence.quests import sync_library_with_discord
        with self._catalog_lock:
            index = self.resolver.index
        with self._mutation_lock:
            report = sync_library_with_discord(
                self.library, index=index, logger=self.log, auto_add_quests=auto_add, stage_decoys=True
            )
        self._active_quests(force=True)
        return {"sync": report, "state": self.status()}

    def start_scheduler(self):
        with self._scheduler_lock:
            if self._scheduler and self._scheduler.is_alive():
                return False
            queue = self.library.queue
            if not queue:
                return False
            for slug in queue:
                self.manager.validate_entry(slug)
            self.manager.request_play(queue[0])
            self._scheduler_stop = threading.Event()
            self._scheduler = threading.Thread(target=self.manager.run_scheduler,
                args=(self._scheduler_stop,), name="queue-scheduler", daemon=True)
            self._scheduler.start()
            return True

    def stop_scheduler(self):
        with self._scheduler_lock:
            self._scheduler_stop.set()

    def status(self):
        result = self.manager.status()
        result["queue_running"] = bool(self._scheduler and self._scheduler.is_alive()
                                        and not self._scheduler_stop.is_set())
        if not result["queue_running"]:
            result["next_switch_in_s"] = None
        # Stored failures are plain prose in the language they were written in.
        # Attach the stable code so the page can render them in its own language.
        if result.get("last_error"):
            result["last_error_code"] = code_for(result["last_error"])
        for game in result.get("games", ()):
            if game.get("worker_error"):
                game["worker_error_code"] = code_for(game["worker_error"])
        result["quests"] = self._active_quests()
        return result

    def search(self, query, limit=8):
        if not isinstance(query, str) or len(query) > 256:
            raise LibraryError("Поисковый запрос должен быть не длиннее 256 символов")
        if not query.strip():
            return []
        with self._catalog_lock:
            return [c.to_dict() for c in self.resolver.index.search(query.strip(), limit=limit)]

    def add_game(self, game_name, application_id=None, autostart=False):
        if not isinstance(game_name, str) or not game_name.strip() or len(game_name) > 256:
            raise LibraryError("Укажите название игры до 256 символов")
        name = game_name.strip()
        with self._catalog_lock:
            if application_id is not None:
                if not isinstance(application_id, str) or not re.fullmatch(r"[0-9]{17,20}", application_id):
                    raise LibraryError("Некорректный Application ID")
                candidate = self.resolver.index.by_id(application_id)
                if candidate is None or candidate.name != name:
                    raise LibraryError("Выбранная карточка устарела. Повторите поиск.")
                identity = Identity(candidate.id, candidate.name, "selection", candidate)
            else:
                identity = self.resolver.resolve_by_name(name)
        candidate = identity.candidate
        catalogue_exes = list(candidate.executables) if candidate else []
        raw_app_id = getattr(candidate, "steam_app_id", None) if candidate else None
        app_id = raw_app_id if isinstance(raw_app_id, str) else None
        raw_icon = getattr(candidate, "icon_url", None) if candidate else None
        cand_icon_url = raw_icon if isinstance(raw_icon, str) else None
        installed = steamlib.installed_executables(app_id) if app_id else set()
        exe, source = steamlib.pick_executable(catalogue_exes, installed)
        from ..presence.quests import resolve_bypass_plan
        plan = resolve_bypass_plan(
            identity.application_id,
            name,
            index=self.resolver.index,
            logger=self.log,
        )
        if exe is None:
            if plan.bypass_mode != "derived" and plan.image_name:
                exe, source = plan.image_name, plan.executable_source
            else:
                # The catalogue publishes no executable for this game. Derive one so the
                # game is still startable, and let the user correct the name later.
                exe, source = derive_image_name(name), "derived"
        with self._mutation_lock:
            if self.manager.status().get("operation"):
                raise ManagerError("Дождитесь завершения запуска или остановки")
            entry = self.library.add(
                name,
                identity.application_id,
                executable=exe,
                executable_source=source,
                catalog_icon_url=cand_icon_url or plan.icon_url,
                executable_rel=plan.executable_rel,
                bypass_mode=plan.bypass_mode,
                epic_app_id=plan.epic_app_id,
                steam_app_id=plan.steam_app_id or app_id,
                carrier_app_id=plan.carrier_app_id,
            )
        # Build the worker executable now, so pressing Запустить only starts a process.
        if entry.can_start:
            try:
                self.manager.prepare(entry.slug)
            except (ManagerError, LibraryError) as exc:
                self.log.warning("game added but the executable was not prepared",
                                 extra={"slug": entry.slug, "error": str(exc)})
        # Cache the catalogue art now, while the dashboard is online: the worker
        # shows this exact picture in the title bar and on the taskbar.
        try:
            self.library.fetch_catalog_icon(entry.slug)
        except LibraryError as exc:
            self.log.warning("catalogue art not cached",
                             extra={"slug": entry.slug, "error": str(exc)})
        if autostart and entry.can_start:
            self.manager.request_play(entry.slug)
        return self.library.get(entry.slug).to_dict()

    def set_executable(self, slug, image_name):
        if not isinstance(image_name, str):
            raise LibraryError("Имя файла должно быть строкой")
        name = image_name.strip()
        try:
            validate_image_name(name)
        except ValueError as exc:
            raise LibraryError(str(exc)) from exc
        entry = self.library.get(slug)
        if entry is None:
            raise LibraryError("Игра не найдена")
        # A hand-typed name is not automatically a guess: if Discord lists it, the game
        # will be matched normally and the user should not be warned about it.
        source = "manual"
        with self._catalog_lock:
            candidate = self.resolver.index.by_id(entry.application_id)
        if candidate:
            known = {str(e).replace("\\", "/").rsplit("/", 1)[-1].casefold()
                     for e in candidate.executables}
            if name.casefold() in known:
                source = "catalogue"
        self.library.update(slug, executable=name, executable_source=source,
                            bypass_mode="catalogue_exe" if source == "catalogue" else "manual",
                            worker_ready=False, worker_error=None, worker_path=None)
        try:
            self.manager.prepare(slug)
        except ManagerError as exc:
            self.log.warning("manual executable not prepared",
                             extra={"slug": slug, "error": str(exc)})
        return self.library.get(slug).to_dict()

    def prepare(self, slug):
        self.manager.prepare(slug)
        return self.library.get(slug).to_dict()

class Handler(BaseHTTPRequestHandler):
    server_version = f"worthlesstask/{APP_VERSION}"
    protocol_version = "HTTP/1.1"

    def log_message(self, fmt, *args):
        # The request line carries query strings — /api/search?q=<what you play>.
        # Journal files are readable by anything running as this user, so the query
        # is dropped before the line is written.
        self.dashboard.log.debug("http " + redact_request(fmt % args))

    def _send(self, status, body, content_type):
        self.send_response(status)
        self.send_header("Content-Type", content_type)
        self.send_header("Content-Length", str(len(body)))
        self.send_header("Cache-Control", "no-store")
        self.send_header("X-Content-Type-Options", "nosniff")
        self.send_header("X-Frame-Options", "DENY")
        self.send_header("Referrer-Policy", "no-referrer")
        self.end_headers()
        if self.command != "HEAD":
            try:
                self.wfile.write(body)
            except (BrokenPipeError, ConnectionResetError):
                self.close_connection = True

    def _json(self, payload, status=200):
        self._send(status, json.dumps(payload, ensure_ascii=False).encode("utf-8"), "application/json; charset=utf-8")

    def _error(self, status, message):
        self.close_connection = True
        payload = {"error": message}
        # A known failure also carries a stable code so the page can render it in
        # the language it is showing instead of echoing server prose.
        code = code_for(message)
        if code:
            payload["code"] = code
        self._json(payload, status)

    def _local_request(self):
        allowed = {f"127.0.0.1:{self.server.server_port}", f"localhost:{self.server.server_port}"}
        origin = self.headers.get("Origin")
        if (self.headers.get("Host", "") not in allowed
            or origin and origin not in {f"http://{h}" for h in allowed}
            or self.headers.get("Sec-Fetch-Site") == "cross-site"):
            self._error(403, "Разрешены только запросы из локальной панели")
            return False
        return True

    def _read_body(self):
        self.connection.settimeout(10)
        if self.headers.get("Transfer-Encoding"):
            raise ValueError("Потоковая передача запроса не поддерживается")
        length = int(self.headers.get("Content-Length") or 0)
        if not 0 <= length <= MAX_BODY_BYTES:
            raise ValueError("Некорректный размер запроса (максимум 4 МиБ)")
        raw = self.rfile.read(length)
        if len(raw) != length:
            raise ValueError("Запрос получен не полностью")
        return raw

    def _read_json(self):
        raw = self._read_body()
        if not raw:
            return {}
        try:
            data = json.loads(raw.decode("utf-8"))
        except (ValueError, UnicodeDecodeError) as exc:
            raise ValueError("Некорректный JSON запроса") from exc
        if not isinstance(data, dict):
            raise ValueError("Тело запроса должно быть JSON-объектом")
        return data

    def _valid_slug(self, slug):
        return isinstance(slug, str) and bool(SLUG_RE.fullmatch(slug))

    def _route(self):
        if not self._local_request():
            return
        parsed = urllib.parse.urlsplit(self.path)
        path = parsed.path
        if self.command in ("GET", "HEAD"):
            if path in ("/", "/index.html"):
                return self._send(200, PAGE.encode("utf-8"), "text/html; charset=utf-8")
            if path == "/api/state":
                return self._json(self.dashboard.status())
            if path == "/api/health":
                return self._json({"ok": True, "application": "worthlesstask", "version": APP_VERSION,
                                   "pid": os.getpid(), "library": str(self.dashboard.library.path)})
            if path == "/api/search":
                query = urllib.parse.parse_qs(parsed.query).get("q", [""])[0]
                return self._json({"results": self.dashboard.search(query)})
            if path.startswith("/api/icon/"):
                slug = path.removeprefix("/api/icon/")
                if not self._valid_slug(slug):
                    raise ValueError("Некорректный идентификатор игры")
                icon = self.dashboard.library.icon_path(slug)
                if icon is None or not icon.is_file():
                    # The same catalogue art the window caches: serve it locally
                    # so the site shows it even when the CDN is unreachable.
                    icon = self.dashboard.library.site_icon_path(slug)
                if icon is None or not icon.is_file():
                    return self._error(404, "Иконка не загружена")
                # Uploads are capped, but this reads whatever is in the folder — an
                # imported or hand-placed file can be far larger. Check before reading
                # so a huge file cannot pull the whole thing into memory.
                size = icon.stat().st_size
                if size > MAX_ICON_BYTES:
                    return self._error(413, "Иконка слишком большая")
                return self._send(200, icon.read_bytes(), ICON_TYPES.get(icon.suffix.lower(), "application/octet-stream"))
        elif self.command == "DELETE" and path.startswith("/api/games/"):
            slug = path.removeprefix("/api/games/")
            if not self._valid_slug(slug):
                raise ValueError("Некорректный идентификатор игры")
            with self.dashboard._mutation_lock:
                status = self.dashboard.manager.status()
                if status.get("operation") or (status.get("active") or {}).get("slug") == slug:
                    return self._error(409, "Сначала остановите активную сессию")
                entry = self.dashboard.library.get(slug)
                removed = self.dashboard.library.remove(slug)
                if removed and entry and entry.executable:
                    # Do not leave the game's 9 MB worker behind.
                    discard_decoy(entry.executable, logger=self.dashboard.log,
                                  client_id=entry.application_id)
                return self._json({"removed": removed}, 200 if removed else 404)
        elif self.command == "POST":
            if path.startswith("/api/icon/"):
                slug = path.removeprefix("/api/icon/")
                if not self._valid_slug(slug):
                    raise ValueError("Некорректный идентификатор игры")
                filename = urllib.parse.unquote(self.headers.get("X-Filename", "icon.ico"))
                return self._json(self.dashboard.library.set_icon(slug, self._read_body(), filename).to_dict())
            payload = self._read_json()
            if path == "/api/games":
                return self._json(self.dashboard.add_game(payload.get("game_name", ""),
                                                          payload.get("application_id"),
                                                          bool(payload.get("autostart"))))
            with self.dashboard._mutation_lock:
                if path.startswith("/api/prepare/"):
                    slug = path.removeprefix("/api/prepare/")
                    if not self._valid_slug(slug):
                        raise ValueError("Некорректный идентификатор игры")
                    return self._json(self.dashboard.prepare(slug))
                if path.startswith("/api/executable/"):
                    slug = path.removeprefix("/api/executable/")
                    if not self._valid_slug(slug):
                        raise ValueError("Некорректный идентификатор игры")
                    return self._json(self.dashboard.set_executable(slug, payload.get("executable", "")))
                if path == "/api/play":
                    self.dashboard.manager.validate_entry(payload.get("slug"))
                    self.dashboard.stop_scheduler()
                    return self._json(self.dashboard.manager.request_play(payload["slug"]), 202)
                if path == "/api/stop":
                    self.dashboard.stop_scheduler()
                    return self._json(self.dashboard.manager.request_stop(), 202)
                if path == "/api/session/reset":
                    self.dashboard.stop_scheduler()
                    return self._json(self.dashboard.manager.clear_session())
                if path == "/api/queue":
                    slugs = payload.get("slugs", [])
                    minutes = payload.get("minutes")
                    if not isinstance(slugs, list) or len(slugs) > 100:
                        raise ValueError("Очередь должна быть списком до 100 игр")
                    if minutes is not None and (type(minutes) is not int or not 1 <= minutes <= 1440):
                        raise ValueError("Укажите целое число минут от 1 до 1440")
                    for slug in slugs:
                        self.dashboard.manager.validate_entry(slug)
                    if minutes is not None:
                        # One write, not one per game: the previous loop serialised
                        # the whole library for every slug in the queue.
                        self.dashboard.library.update_many(
                            {slug: {"minutes": minutes} for slug in slugs})
                    if not slugs:
                        self.dashboard.stop_scheduler()
                    return self._json({"queue": self.dashboard.manager.set_queue(slugs)})
                if path == "/api/queue/start":
                    return self._json({"started": self.dashboard.start_scheduler(), "queue": self.dashboard.library.queue})
                if path == "/api/quests/sync":
                    auto_add = bool(payload.get("auto_add", True))
                    return self._json(self.dashboard.sync_quests(auto_add=auto_add))
        self._error(404, "Не найдено")

    def _dispatch(self):
        try:
            self._route()
        except (worthlesstaskError, ValueError, TimeoutError) as exc:
            self._error(400, str(exc))
        except (ConnectionResetError, BrokenPipeError):
            self.close_connection = True
        except Exception:
            self.dashboard.log.exception("request failed")
            self._error(500, "Внутренняя ошибка. Подробности в журнале приложения.")

    do_GET = do_HEAD = do_POST = do_DELETE = _dispatch


def make_server(dashboard, host=DEFAULT_HOST, port=DEFAULT_PORT):
    if host not in ("127.0.0.1", "localhost"):
        raise ManagerError("Панель допускает только локальный адрес 127.0.0.1")
    handler = type("BoundHandler", (Handler,), {"dashboard": dashboard})
    server = ThreadingHTTPServer((host, port), handler)
    server.daemon_threads = True
    return server


def serve(dashboard, host=DEFAULT_HOST, port=DEFAULT_PORT, stop_event=None, on_ready=None):
    server = make_server(dashboard, host, port)
    url = f"http://{host}:{server.server_port}"
    dashboard.log.info("dashboard listening", extra={"url": url})
    print(f"worthlesstask dashboard: {url}", flush=True)
    if on_ready:
        on_ready(url)
    try:
        if stop_event is None:
            server.serve_forever()
        else:
            server.timeout = .5
            while not stop_event.is_set():
                server.handle_request()
    except KeyboardInterrupt:
        pass
    finally:
        dashboard.stop_scheduler()
        server.server_close()
    return 0


def default_port_is_free(host=DEFAULT_HOST, port=DEFAULT_PORT):
    import socket
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as probe:
        try:
            probe.bind((host, port))
            return True
        except OSError:
            return False


def find_free_port(host=DEFAULT_HOST, start=DEFAULT_PORT, attempts=20):
    for port in range(start, min(65536, start+attempts)):
        if default_port_is_free(host, port):
            return port
    raise ManagerError("Нет свободного локального порта")


def is_dashboard_running(host=DEFAULT_HOST, port=DEFAULT_PORT, timeout=1.5, library_path=None):
    try:
        with urllib.request.urlopen(f"http://{host}:{port}/api/health", timeout=timeout) as response:
            data = json.loads(response.read(8192))
        return (data.get("application") == "worthlesstask" and data.get("version") == APP_VERSION
                and (library_path is None or Path(data.get("library", "")).resolve() == Path(library_path).resolve()))
    except (OSError, ValueError):
        return False

__all__ = ["DEFAULT_HOST", "DEFAULT_PORT", "Dashboard", "Handler", "find_free_port",
           "is_dashboard_running", "make_server", "serve"]
