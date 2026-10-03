#!/usr/bin/env python3
"""Sequential per-game detection bypass check.

For every game in the local library:
  1. POST /api/prepare/<slug>
  2. POST /api/play {"slug": slug}
  3. wait (up to PLAY_TIMEOUT) for all acceptance evidence:
       - state says the game is "running"
       - worker log contains "presence window created"
       - worker log contains "presence set"
       - a NEW discord renderer_js.log line "visibleGame=<game_name>"
  4. POST /api/stop {} and wait until nothing is running

Prints a PASS/FAIL table and writes JSON results to %TEMP%.
"""
import json
import os
import time
import urllib.error
import urllib.parse
import urllib.request
from pathlib import Path

BASE = "http://127.0.0.1:8787"
LOCAL = Path(os.environ["LOCALAPPDATA"]) / "worthlesstask"
RENDERER = Path(os.environ["APPDATA"]) / "discord" / "logs" / "renderer_js.log"
OUT = Path(os.environ.get("TEMP", ".")) / "per_game_bypass_results.json"
PLAY_TIMEOUT = 90.0
STOP_TIMEOUT = 60.0


def request(method, path, payload=None):
    data = None
    headers = {}
    if payload is not None:
        data = json.dumps(payload).encode("utf-8")
        headers["Content-Type"] = "application/json"
    req = urllib.request.Request(BASE + path, data=data, headers=headers, method=method)
    try:
        with urllib.request.urlopen(req, timeout=20) as resp:
            return resp.status, resp.read().decode("utf-8", "replace")
    except urllib.error.HTTPError as exc:
        return exc.code, exc.read().decode("utf-8", "replace")


def state():
    with urllib.request.urlopen(BASE + "/api/state", timeout=15) as resp:
        return json.loads(resp.read().decode("utf-8"))


def file_size(path):
    try:
        return path.stat().st_size
    except OSError:
        return 0


def read_since(path, offset):
    """Read new bytes from offset; handles truncation (log recreated)."""
    try:
        size = path.stat().st_size
    except OSError:
        return "", offset
    if size < offset:
        offset = 0
    try:
        with open(path, "rb") as handle:
            handle.seek(offset)
            chunk = handle.read()
        return chunk.decode("utf-8", "replace"), offset + len(chunk)
    except OSError:
        return "", offset


def find_game(st, slug):
    for game in st.get("games", ()):
        if game.get("slug") == slug or game.get("application_id") == slug:
            return game
    return None


def _psutil_processes():
    """Cheap process listing without a dependency: tasklist output is enough."""
    try:
        import subprocess

        out = subprocess.run(
            ["tasklist", "/fo", "csv", "/nh"],
            capture_output=True, text=True, timeout=30,
        ).stdout
    except Exception:  # noqa: BLE001
        return ()
    rows = []
    for line in out.splitlines():
        parts = [part.strip('" ') for part in line.split('","')]
        if parts:
            rows.append(type("Proc", (), {"name": parts[0]})())
    return rows


def worker_alive(game: dict | None) -> bool:
    """The dashboard reports ``worker_ready`` (not ``state``) for a live session."""
    if not game:
        return False
    if game.get("state") == "running":
        return True
    return bool(game.get("worker_ready")) and not game.get("worker_error")


def visible_match(line, name):
    hay = line.lower()
    candidates = [name.lower()]
    if ":" in name:
        candidates.append(name.split(":")[0].strip().lower())
    if name:
        candidates.append(name.split()[0].lower())
    return any(c and c in hay for c in candidates)


def main():
    if not any(
        proc.name.lower().startswith("discord") for proc in _psutil_processes()
    ):
        print(
            "WARNING: the Discord desktop client is not running. The app side will "
            "be exercised, but `presence set` and the `visibleGame=` line need a live "
            "Discord (its renderer log is not even being written).",
            flush=True,
        )
    st = state()
    games = list(st.get("games", ()))
    games.sort(key=lambda g: (g.get("slug") or g.get("application_id") or ""))
    print(f"library games: {len(games)}", flush=True)
    results = []

    for game in games:
        slug = game.get("slug") or game.get("application_id")
        name = game.get("game_name") or slug
        print(f"\n=== {slug} ({name}) ===", flush=True)
        record = {
            "slug": slug,
            "game_name": name,
            "pass": False,
            "notes": [],
            "visible_lines": [],
        }

        status, body = request("POST", "/api/prepare/" + urllib.parse.quote(slug))
        record["prepare"] = status
        if status >= 400:
            record["notes"].append(f"prepare failed: {status} {body[:200]}")
            print(f"  prepare FAILED: {status}", flush=True)
            results.append(record)
            continue
        print(f"  prepare ok ({status})", flush=True)

        worker_log = LOCAL / "logs" / f"{slug}.log"
        w_off = file_size(worker_log)
        r_off = file_size(RENDERER)
        seen_visible = []

        status, body = request("POST", "/api/play", {"slug": slug})
        record["play"] = status
        if status >= 400:
            record["notes"].append(f"play failed: {status} {body[:200]}")
            print(f"  play FAILED: {status}", flush=True)
            results.append(record)
            continue
        print(f"  play accepted ({status})", flush=True)

        deadline = time.time() + PLAY_TIMEOUT
        running = created = pset = visible = False
        while time.time() < deadline:
            try:
                st_now = state()
            except Exception:
                st_now = {}
            cur = find_game(st_now, slug)
            if worker_alive(cur):
                running = True
            wtext, w_off = read_since(worker_log, w_off)
            if "presence window created" in wtext:
                created = True
            if "presence set" in wtext:
                pset = True
            rtext, r_off = read_since(RENDERER, r_off)
            for line in rtext.splitlines():
                if "visibleGame=" in line:
                    if line not in seen_visible:
                        seen_visible.append(line[-400:])
                    if visible_match(line, name):
                        visible = True
            if running and created and pset and visible:
                break
            time.sleep(2)

        record.update(
            running=running,
            created=created,
            presence_set=pset,
            visible=visible,
            visible_lines=seen_visible[-5:],
        )
        record["pass"] = bool(running and created and pset and visible)
        missing = [
            what
            for what, ok in (
                ("state=running", running),
                ("presence window created", created),
                ("presence set", pset),
                ("visibleGame", visible),
            )
            if not ok
        ]
        if missing:
            record["notes"].append("missing: " + ", ".join(missing))
        print(
            "  " + ("PASS" if record["pass"] else "FAIL")
            + ("" if record["pass"] else " (" + "; ".join(missing) + ")"),
            flush=True,
        )
        results.append(record)

        request("POST", "/api/stop", {})
        stop_deadline = time.time() + STOP_TIMEOUT
        while time.time() < stop_deadline:
            try:
                st_now = state()
            except Exception:
                time.sleep(2)
                continue
            if not any(worker_alive(g) for g in st_now.get("games", ())):
                break
            time.sleep(2)
        time.sleep(3)  # let presence clear before the next game

    passed = sum(1 for r in results if r["pass"])
    print("\n==== RESULTS ====", flush=True)
    for r in results:
        status = "PASS" if r["pass"] else "FAIL"
        note = "" if r["pass"] else "  " + "; ".join(r["notes"])
        print(f"{status:4}  {r['slug']}{note}", flush=True)
    print(f"total: {passed}/{len(results)} passed", flush=True)
    OUT.write_text(json.dumps(results, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"json: {OUT}", flush=True)


if __name__ == "__main__":
    main()
