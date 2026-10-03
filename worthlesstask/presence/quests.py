"""Discord local client cache scanner and universal Quest/Game bypass resolver.

Reads Discord's local SimpleCache/Blockfile cache (``%APPDATA%\\discord\\Cache\\Cache_Data``)
using shared Win32 file handles so a running Discord client is never locked or
disturbed, extracts active/enrolled ``PLAY_ON_DESKTOP`` quests and cached game
records, and computes the exact process/IPC bypass needed for every application —
including unreleased or zero-executable Quest titles such as ``EA SPORTS FC™ 27``.
"""

from __future__ import annotations

import ctypes
import gzip
import json
import os
import re
import struct
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

__all__ = [
    "BypassPlan",
    "DiscordQuest",
    "discover_discord_quests",
    "discover_cached_discord_games",
    "resolve_bypass_plan",
    "sync_library_with_discord",
]


@dataclass(frozen=True)
class DiscordQuest:
    """A desktop-eligible Discord Quest extracted from the local Discord cache."""

    quest_id: str
    quest_name: str
    game_title: str
    publisher: str = ""
    primary_app_id: str = ""
    primary_app_name: str = ""
    accepted_app_ids: tuple[str, ...] = ()
    task_type: str = "PLAY_ON_DESKTOP"
    target_seconds: int = 900
    progress_seconds: int = 0
    enrolled_at: str | None = None
    completed_at: str | None = None
    claimed_at: str | None = None
    expires_at: str | None = None
    orb_reward: int = 0
    reward_name: str = ""
    icon_url: str | None = None

    @property
    def is_enrolled(self) -> bool:
        return bool(self.enrolled_at)

    @property
    def is_completed(self) -> bool:
        return bool(self.completed_at) or (
            self.target_seconds > 0 and self.progress_seconds >= self.target_seconds
        )

    @property
    def completed(self) -> bool:
        return self.is_completed

    @property
    def is_expired(self) -> bool:
        if not self.expires_at:
            return False
        try:
            exp = datetime.fromisoformat(self.expires_at.replace("Z", "+00:00"))
            return exp <= datetime.now(timezone.utc)
        except ValueError:
            return False

    @property
    def target_minutes(self) -> int:
        return max(1, round(self.target_seconds / 60)) if self.target_seconds > 0 else 15

    @property
    def progress_percent(self) -> int:
        if self.is_completed:
            return 100
        if self.target_seconds <= 0:
            return 0
        return min(99, max(0, int((self.progress_seconds * 100) / self.target_seconds)))

    def to_dict(self) -> dict[str, Any]:
        return {
            "quest_id": self.quest_id,
            "quest_name": self.quest_name,
            "game_title": self.game_title,
            "publisher": self.publisher,
            "primary_app_id": self.primary_app_id,
            "primary_app_name": self.primary_app_name,
            "accepted_app_ids": list(self.accepted_app_ids),
            "task_type": self.task_type,
            "target_seconds": self.target_seconds,
            "target_minutes": self.target_minutes,
            "progress_seconds": self.progress_seconds,
            "progress_percent": self.progress_percent,
            "enrolled_at": self.enrolled_at,
            "completed_at": self.completed_at,
            "claimed_at": self.claimed_at,
            "expires_at": self.expires_at,
            "is_enrolled": self.is_enrolled,
            "is_completed": self.is_completed,
            "completed": self.is_completed,
            "is_expired": self.is_expired,
            "orb_reward": self.orb_reward,
            "reward_name": self.reward_name,
            "icon_url": self.icon_url,
        }


@dataclass(frozen=True)
class BypassPlan:
    """Resolved process + IPC bypass parameters for a game."""

    application_id: str
    game_name: str
    executable: str  # leaf filename (e.g. "fc26.exe")
    executable_rel: str  # relative path inside workers/ (e.g. "ea sports fc 26/fc26.exe")
    executable_source: str  # "installed" | "catalogue" | "carrier" | "quest_sibling" | "derived"
    bypass_mode: str  # "native_exe" | "subdir_exe" | "carrier_ipc_sku" | "carrier_ipc" | "quest_sibling_ipc"
    carrier_app_id: str | None = None
    carrier_app_name: str | None = None
    epic_app_id: str | None = None
    steam_app_id: str | None = None
    quest_id: str | None = None
    quest_name: str | None = None
    orb_reward: int = 0
    icon_url: str | None = None
    extra_Catalog_executables: tuple[str, ...] = field(default_factory=tuple)

    @property
    def image_name(self) -> str:
        return self.executable


# --------------------------------------------------------------------------- #
# Shared Win32 file reading for Discord's live Cache_Data                     #
# --------------------------------------------------------------------------- #

def _discord_cache_dirs() -> list[Path]:
    """Return candidate Discord Cache_Data directories on the machine."""
    appdata = os.environ.get("APPDATA")
    if not appdata:
        return []
    base = Path(appdata)
    dirs: list[Path] = []
    for client in ("discord", "discordptb", "discordcanary"):
        candidate = base / client / "Cache" / "Cache_Data"
        if candidate.is_dir():
            dirs.append(candidate)
    return dirs


def _read_shared_bytes(path: Path) -> bytes:
    """Read ``path`` with ``FILE_SHARE_READ | FILE_SHARE_WRITE | FILE_SHARE_DELETE``."""
    if os.name != "nt":
        try:
            return path.read_bytes()
        except OSError:
            return b""
    try:
        return path.read_bytes()
    except OSError:
        pass
    try:
        kernel32 = ctypes.windll.kernel32
        handle = kernel32.CreateFileW(
            str(path),
            0x80000000,  # GENERIC_READ
            0x00000001 | 0x00000002 | 0x00000004,  # FILE_SHARE_ALL
            None,
            3,  # OPEN_EXISTING
            0,
            None,
        )
        if handle in (-1, 0xFFFFFFFF, 0xFFFFFFFFFFFFFFFF):
            return b""
        try:
            size = kernel32.GetFileSize(handle, None)
            if size <= 0 or size == 0xFFFFFFFF or size > 64 * 1024 * 1024:
                return b""
            buf = ctypes.create_string_buffer(size)
            read = ctypes.c_ulong(0)
            if not kernel32.ReadFile(handle, buf, size, ctypes.byref(read), None):
                return b""
            return buf.raw[: read.value]
        finally:
            kernel32.CloseHandle(handle)
    except Exception:
        return b""


def _maybe_gunzip(data: bytes) -> bytes:
    if len(data) >= 2 and data[:2] == b"\x1f\x8b":
        try:
            return gzip.decompress(data)
        except Exception:
            return data
    # Sometimes SimpleCache headers precede the gzip stream
    idx = data.find(b"\x1f\x8b", 0, min(len(data), 256))
    if idx > 0:
        try:
            return gzip.decompress(data[idx:])
        except Exception:
            pass
    return data


def _extract_json_object(raw: bytes, marker: bytes) -> Any | None:
    data = _maybe_gunzip(raw)
    if marker not in data:
        return None
    start = data.find(b"{")
    list_start = data.find(b"[")
    if list_start != -1 and (start == -1 or list_start < start):
        start = list_start
    if start == -1:
        return None
    text = data[start:].decode("utf-8", errors="replace")
    for end_char in ("}", "]"):
        end = text.rfind(end_char)
        if end != -1:
            try:
                return json.loads(text[: end + 1])
            except Exception:
                continue
    return None


def _resolve_blockfile_addr(
    cache_dir: Path, data_files: dict[int, bytes], addr: int, size: int
) -> bytes:
    if addr == 0 or size <= 0 or not ((addr >> 31) & 1):
        return b""
    file_type = (addr >> 28) & 0x7
    if file_type == 0:
        file_num = addr & 0x0FFFFFFF
        return _read_shared_bytes(cache_dir / f"f_{file_num:06x}")
    block_size = {1: 36, 2: 256, 3: 1024, 4: 4096}.get(file_type, 0)
    if block_size == 0:
        return b""
    file_num = (addr >> 16) & 0xFF
    block_num = addr & 0xFFFF
    offset = 8192 + block_num * block_size
    blob = data_files.get(file_num, b"")
    return blob[offset : offset + size]


# --------------------------------------------------------------------------- #
# Quest & Cached Game Extraction                                              #
# --------------------------------------------------------------------------- #

def _parse_quest(raw: dict[str, Any]) -> DiscordQuest | None:
    if not isinstance(raw, dict):
        return None
    qid = str(raw.get("id") or "").strip()
    cfg = raw.get("config")
    if not qid or not isinstance(cfg, dict):
        return None

    tc = cfg.get("task_config_v2") or cfg.get("task_config") or {}
    tasks = tc.get("tasks") if isinstance(tc, dict) else {}
    if not isinstance(tasks, dict):
        return None

    task_type = ""
    task_obj: dict[str, Any] | None = None
    for candidate_type in ("PLAY_ON_DESKTOP", "STREAM_ON_DESKTOP", "PLAY_ACTIVITY"):
        if isinstance(tasks.get(candidate_type), dict):
            task_type = candidate_type
            task_obj = tasks[candidate_type]
            break
    if task_obj is None:
        return None

    app = cfg.get("application") if isinstance(cfg.get("application"), dict) else {}
    primary_app_id = str(app.get("id") or "").strip()
    primary_app_name = str(app.get("name") or "").strip()

    accepted_ids: list[str] = []
    for item in task_obj.get("applications") or ():
        if isinstance(item, dict) and item.get("id"):
            aid = str(item["id"]).strip()
            if aid and aid not in accepted_ids:
                accepted_ids.append(aid)
    if primary_app_id and primary_app_id not in accepted_ids:
        accepted_ids.insert(0, primary_app_id)
    if not primary_app_id and accepted_ids:
        primary_app_id = accepted_ids[0]

    msgs = cfg.get("messages") if isinstance(cfg.get("messages"), dict) else {}
    quest_name = str(msgs.get("quest_name") or primary_app_name or qid).strip()
    game_title = str(msgs.get("game_title") or primary_app_name or quest_name).strip()
    publisher = str(msgs.get("game_publisher") or "").strip()

    target_seconds = int(task_obj.get("target") or 900)
    ustatus = raw.get("user_status") if isinstance(raw.get("user_status"), dict) else {}
    enrolled_at = ustatus.get("enrolled_at") if isinstance(ustatus.get("enrolled_at"), str) else None
    completed_at = ustatus.get("completed_at") if isinstance(ustatus.get("completed_at"), str) else None
    claimed_at = ustatus.get("claimed_at") if isinstance(ustatus.get("claimed_at"), str) else None
    expires_at = cfg.get("expires_at") if isinstance(cfg.get("expires_at"), str) else None

    progress_seconds = 0
    prog_map = ustatus.get("progress")
    if isinstance(prog_map, dict):
        p_entry = prog_map.get(task_type) or prog_map.get("PLAY_ON_DESKTOP")
        if isinstance(p_entry, dict) and isinstance(p_entry.get("value"), (int, float)):
            progress_seconds = int(p_entry["value"])
            if not completed_at and isinstance(p_entry.get("completed_at"), str):
                completed_at = p_entry["completed_at"]

    orb_reward = 0
    reward_name = ""
    rewards_cfg = cfg.get("rewards_config") if isinstance(cfg.get("rewards_config"), dict) else {}
    for r_item in rewards_cfg.get("rewards") or ():
        if not isinstance(r_item, dict):
            continue
        if isinstance(r_item.get("orb_quantity"), int):
            orb_reward = max(orb_reward, r_item["orb_quantity"])
        r_msgs = r_item.get("messages") if isinstance(r_item.get("messages"), dict) else {}
        if not reward_name and isinstance(r_msgs.get("name"), str):
            reward_name = r_msgs["name"].strip()

    return DiscordQuest(
        quest_id=qid,
        quest_name=quest_name,
        game_title=game_title,
        publisher=publisher,
        primary_app_id=primary_app_id,
        primary_app_name=primary_app_name,
        accepted_app_ids=tuple(accepted_ids),
        task_type=task_type,
        target_seconds=target_seconds,
        progress_seconds=progress_seconds,
        enrolled_at=enrolled_at,
        completed_at=completed_at,
        claimed_at=claimed_at,
        expires_at=expires_at,
        orb_reward=orb_reward,
        reward_name=reward_name,
    )


def discover_discord_quests(
    cache_dirs: list[Path] | None = None, *, logger: Any = None
) -> list[DiscordQuest]:
    """Scan Discord's local HTTP cache for ``/quests/@me`` payloads and return desktop quests."""
    _ = logger
    dirs = cache_dirs if cache_dirs is not None else _discord_cache_dirs()
    by_id: dict[str, DiscordQuest] = {}

    for cache_dir in dirs:
        if not cache_dir.is_dir():
            continue
        # Scan standalone f_* files sorted by mtime (newest last so newer overwrites older)
        try:
            f_files = sorted(cache_dir.glob("f_*"), key=lambda p: p.stat().st_mtime_ns)
        except OSError:
            f_files = []
        for fp in f_files:
            raw = _read_shared_bytes(fp)
            if not raw:
                continue
            payload = _extract_json_object(raw, b'"quests"')
            if not isinstance(payload, dict) or not isinstance(payload.get("quests"), list):
                continue
            for q_raw in payload["quests"]:
                parsed = _parse_quest(q_raw)
                if parsed is not None:
                    by_id[parsed.quest_id] = parsed

    # Sort: enrolled & incomplete first, then incomplete & not expired, then by quest_id desc
    def _rank(q: DiscordQuest) -> tuple[int, int, int, str]:
        active_enrolled = 1 if (q.is_enrolled and not q.is_completed and not q.is_expired) else 0
        available = 1 if (not q.is_completed and not q.is_expired) else 0
        return (active_enrolled, available, q.orb_reward, q.quest_id)

    return sorted(by_id.values(), key=_rank, reverse=True)


def discover_cached_discord_games(
    cache_dirs: list[Path] | None = None, *, logger: Any = None
) -> list[dict[str, Any]]:
    """Extract cached ``/api/v9/games`` and ``/api/v9/applications/public`` records from Discord."""
    _ = logger
    dirs = cache_dirs if cache_dirs is not None else _discord_cache_dirs()
    by_id: dict[str, dict[str, Any]] = {}

    for cache_dir in dirs:
        if not cache_dir.is_dir():
            continue
        data_files = {i: _read_shared_bytes(cache_dir / f"data_{i}") for i in range(4)}
        b1 = data_files.get(1, b"")
        if len(b1) <= 8192:
            continue
        for block_idx in range((len(b1) - 8192) // 256):
            off = 8192 + block_idx * 256
            rec = b1[off : off + 256]
            if len(rec) < 96:
                continue
            key_len, long_key = struct.unpack_from("<2i", rec, 32)
            if key_len <= 0 or key_len > 65536:
                continue
            if long_key != 0:
                key_bytes = _resolve_blockfile_addr(cache_dir, data_files, long_key & 0xFFFFFFFF, key_len)
            else:
                key_bytes = rec[96 : 96 + min(160, key_len)]
            if not (b"api/v9/games" in key_bytes or b"applications/public" in key_bytes):
                continue
            if b"announcements" in key_bytes or b"similar-games" in key_bytes:
                continue
            data_sizes = struct.unpack_from("<4i", rec, 40)
            data_addrs = struct.unpack_from("<4I", rec, 56)
            body = _resolve_blockfile_addr(cache_dir, data_files, data_addrs[1], data_sizes[1])
            if not body:
                continue
            parsed = _extract_json_object(body, b'"id"')
            if not isinstance(parsed, list):
                continue
            for item in parsed:
                if not isinstance(item, dict):
                    continue
                aid = str(item.get("id") or "").strip()
                name = str(item.get("name") or "").strip()
                if not aid.isdigit() or not name:
                    continue
                existing = by_id.get(aid, {})
                icon_hash = item.get("icon_hash") or item.get("icon") or existing.get("icon_hash")
                exes = item.get("executables") if isinstance(item.get("executables"), list) else existing.get("executables", [])
                skus = item.get("third_party_skus") if isinstance(item.get("third_party_skus"), list) else existing.get("third_party_skus", [])
                aliases = item.get("aliases") if isinstance(item.get("aliases"), list) else existing.get("aliases", [])
                by_id[aid] = {
                    "id": aid,
                    "name": name,
                    "aliases": aliases,
                    "icon_hash": icon_hash if isinstance(icon_hash, str) else None,
                    "hook": bool(item.get("hook", existing.get("hook", True))),
                    "executables": exes,
                    "third_party_skus": skus,
                }
    return list(by_id.values())


# --------------------------------------------------------------------------- #
# Universal Bypass Resolution                                                 #
# --------------------------------------------------------------------------- #

_EDITION_TAIL_RE = re.compile(
    r"(?:\s*[:\-–—]?\s*(?:20\d{2}|\d{1,2}|[ivx]+|remastered|remake|definitive|edition|trial|demo|beta|playtest|requiem))+$",
    re.IGNORECASE,
)

# Clean, verified non-launcher win32 executables present in Discord's games-v1.json
# used as fallback carrier hosts when a new Quest game has executables=[] and no franchise sibling.
FALLBACK_CARRIERS: tuple[tuple[str, str, str], ...] = (
    ("1421154726023532544", "EA Sports FC 26", "ea sports fc 26/fc26.exe"),
    ("1448369915462549616", "PRAGMATA", "pragmata_sketchbook.exe"),
    ("1468082130474111047", "Aniimo", "aniimo.exe"),
    ("1470616226995765409", "NTE: Neverness to Everness", "htgame.exe"),
    ("1461154307171811401", "ARKNIGHTS: ENDFIELD", "endfield.exe"),
)


def _extract_skus(entry: dict[str, Any] | None) -> tuple[str | None, str | None]:
    """Return ``(epic_app_id, steam_app_id)`` from a catalogue entry's ``third_party_skus``."""
    if not isinstance(entry, dict):
        return None, None
    epic_id: str | None = None
    steam_id: str | None = None
    for sku in entry.get("third_party_skus") or ():
        if not isinstance(sku, dict):
            continue
        dist = str(sku.get("distributor") or "").lower()
        val = str(sku.get("id") or sku.get("sku") or "").strip()
        if not val:
            continue
        if dist == "epic" and not epic_id:
            epic_id = val
        elif dist == "steam" and val.isdigit() and not steam_id:
            steam_id = val
    return epic_id, steam_id


def _win32_non_launcher_exes(entry: dict[str, Any] | None) -> list[str]:
    if not isinstance(entry, dict):
        return []
    raw_exes = entry.get("executables") or ()
    out: list[str] = []
    fallback_launchers: list[str] = []
    for item in raw_exes:
        if isinstance(item, str):
            cleaned = item.strip().lstrip(">").replace("\\", "/").lstrip("/")
            if cleaned.lower().endswith(".exe"):
                out.append(cleaned)
            continue
        if not isinstance(item, dict):
            continue
        os_name = str(item.get("os") or "win32").lower()
        if os_name not in ("win32", ""):
            continue
        name = str(item.get("name") or "").strip().lstrip(">").replace("\\", "/").lstrip("/")
        if not name or not name.lower().endswith(".exe"):
            continue
        if item.get("is_launcher"):
            fallback_launchers.append(name)
        else:
            out.append(name)
    return out or fallback_launchers


def _find_franchise_carrier(
    game_name: str,
    application_id: str,
    entries_by_id: dict[str, dict[str, Any]],
) -> tuple[str, str, str] | None:
    """Find a sibling game in the same franchise that has a non-launcher win32 executable."""
    clean_title = re.sub(r"[™®©]", "", game_name).strip()
    stem = _EDITION_TAIL_RE.sub("", clean_title).strip().lower()
    if len(stem) < 3:
        stem = clean_title.lower()
    if not stem:
        return None

    best_match: tuple[int, str, str, str] | None = None
    for cid, row in entries_by_id.items():
        if cid == application_id:
            continue
        rname = re.sub(r"[™®©]", "", str(row.get("name") or "")).strip()
        rl = rname.lower()
        if len(rl) < 4:
            continue
        if not (rl.startswith(stem) or stem.startswith(rl) or (len(rl) >= 8 and rl in stem)):
            continue
        exes = _win32_non_launcher_exes(row)
        if not exes:
            continue
        # Prefer the newest sibling (highest snowflake ID) and main non-trial/non-showcase executable
        chosen_exe = exes[0]
        for ex in exes:
            leaf = ex.rsplit("/", 1)[-1].lower()
            if not any(bad in leaf for bad in ("trial", "demo", "showcase", "launcher", "setup", "test", "crash")):
                chosen_exe = ex
                break
        score = int(cid) if cid.isdigit() else 0
        if best_match is None or score > best_match[0]:
            best_match = (score, cid, str(row.get("name") or ""), chosen_exe)

    if best_match is not None:
        return best_match[1], best_match[2], best_match[3]
    return None


def resolve_bypass_plan(
    game_name: str,
    application_id: str,
    entries: list[dict[str, Any]] | None = None,
    quests: list[DiscordQuest] | None = None,
    *,
    index: Any = None,
    logger: Any = None,
) -> BypassPlan:
    """Compute the optimal Discord detection & Quest heartbeat bypass for a game."""
    from worthlesstask import steamlib

    _ = logger
    # Support callers passing (application_id, game_name) instead of (game_name, application_id)
    if str(game_name).isdigit() and not str(application_id).isdigit():
        game_name, application_id = str(application_id), str(game_name)
    else:
        game_name, application_id = str(game_name), str(application_id)

    if entries is None:
        raw_entries: Any = ()
        if index is not None and hasattr(index, "entries"):
            try:
                raw_entries = index.entries()
            except Exception:
                raw_entries = ()
        entries = list(raw_entries) if isinstance(raw_entries, (list, tuple)) else []
        # Also enrich from local Discord cache when a real DetectableIndex is used
        if entries:
            try:
                by_existing = {str(r.get("id")) for r in entries if isinstance(r, dict)}
                for cg in discover_cached_discord_games():
                    cid = str(cg.get("id") or "")
                    if cid and cid not in by_existing:
                        entries.append(cg)
            except Exception:
                pass

    entries_by_id = {str(r.get("id")): r for r in entries if isinstance(r, dict) and r.get("id")}
    target_row = entries_by_id.get(str(application_id))
    epic_id, steam_id = _extract_skus(target_row)
    icon_hash = target_row.get("icon_hash") if isinstance(target_row, dict) else None
    icon_url = (
        f"https://cdn.discordapp.com/app-icons/{application_id}/{icon_hash}.png"
        if isinstance(icon_hash, str) and icon_hash
        else None
    )

    # Match active/enrolled quest if any
    matched_quest: DiscordQuest | None = None
    if quests:
        for q in quests:
            if application_id in q.accepted_app_ids or q.primary_app_id == application_id:
                matched_quest = q
                break
            if q.game_title and re.sub(r"\W+", "", q.game_title.lower()) == re.sub(r"\W+", "", game_name.lower()):
                matched_quest = q
                break

    # 1. Check if the target application itself has win32 non-launcher executables
    direct_exes = _win32_non_launcher_exes(target_row)
    if direct_exes:
        chosen_leaf, source = steamlib.resolve_image_name(game_name, application_id, direct_exes)
        leaf_cf = (chosen_leaf or "").casefold()
        chosen_rel = chosen_leaf or direct_exes[0].rsplit("/", 1)[-1]
        # Prefer a bare matching entry if one exists, otherwise keep the directory prefix
        bare_match = next((ex for ex in direct_exes if "/" not in ex and ex.casefold() == leaf_cf), None)
        if bare_match:
            chosen_rel = bare_match
        else:
            prefixed_match = next(
                (ex for ex in direct_exes if ex.rsplit("/", 1)[-1].casefold() == leaf_cf),
                direct_exes[0],
            )
            chosen_rel = prefixed_match
        chosen_leaf = chosen_rel.rsplit("/", 1)[-1]
        bypass_mode = "subdir_exe" if "/" in chosen_rel else "native_exe"
        return BypassPlan(
            application_id=application_id,
            game_name=game_name,
            executable=chosen_leaf,
            executable_rel=chosen_rel,
            executable_source=source,
            bypass_mode=bypass_mode,
            epic_app_id=epic_id,
            steam_app_id=steam_id,
            quest_id=matched_quest.quest_id if matched_quest else None,
            quest_name=matched_quest.quest_name if matched_quest else None,
            orb_reward=matched_quest.orb_reward if matched_quest else 0,
            icon_url=icon_url,
            extra_Catalog_executables=tuple(direct_exes),
        )

    # 2. Target has executables=[]: check if an active Quest lists sibling accepted_app_ids with win32 exes
    if matched_quest is not None:
        for sibling_id in matched_quest.accepted_app_ids:
            if sibling_id == application_id:
                continue
            sib_row = entries_by_id.get(sibling_id)
            sib_exes = _win32_non_launcher_exes(sib_row)
            if sib_exes:
                sib_name = str(sib_row.get("name") or sibling_id)
                chosen_leaf, _ = steamlib.resolve_image_name(sib_name, sibling_id, sib_exes)
                leaf_cf = (chosen_leaf or "").casefold()
                chosen_rel = next(
                    (ex for ex in sib_exes if ex.rsplit("/", 1)[-1].casefold() == leaf_cf),
                    sib_exes[0],
                )
                chosen_leaf = chosen_rel.rsplit("/", 1)[-1]
                return BypassPlan(
                    application_id=application_id,
                    game_name=game_name,
                    executable=chosen_leaf,
                    executable_rel=chosen_rel,
                    executable_source="catalogue",
                    bypass_mode="quest_sibling_ipc",
                    carrier_app_id=sibling_id,
                    carrier_app_name=sib_name,
                    epic_app_id=epic_id,
                    steam_app_id=steam_id,
                    quest_id=matched_quest.quest_id,
                    quest_name=matched_quest.quest_name,
                    orb_reward=matched_quest.orb_reward,
                    icon_url=icon_url,
                    extra_Catalog_executables=(chosen_rel,),
                )

    # 3. Target has executables=[]: find a franchise sibling carrier (e.g. EA Sports FC 26 -> ea sports fc 26/fc26.exe)
    franchise = _find_franchise_carrier(game_name, application_id, entries_by_id)
    if franchise is not None:
        carrier_id, carrier_name, carrier_rel = franchise
        carrier_leaf = carrier_rel.rsplit("/", 1)[-1]
        return BypassPlan(
            application_id=application_id,
            game_name=game_name,
            executable=carrier_leaf,
            executable_rel=carrier_rel,
            executable_source="catalogue",
            bypass_mode="carrier_ipc_sku" if (epic_id or steam_id) else "carrier_ipc",
            carrier_app_id=carrier_id,
            carrier_app_name=carrier_name,
            epic_app_id=epic_id,
            steam_app_id=steam_id,
            quest_id=matched_quest.quest_id if matched_quest else None,
            quest_name=matched_quest.quest_name if matched_quest else None,
            orb_reward=matched_quest.orb_reward if matched_quest else 0,
            icon_url=icon_url,
            extra_Catalog_executables=(carrier_rel,),
        )

    # 4. When no catalogue entries or quests exist (e.g. offline/mocked without catalogue), derive name
    if not entries_by_id and matched_quest is None:
        from worthlesstask.decoy import derive_image_name

        derived_leaf = derive_image_name(game_name)
        return BypassPlan(
            application_id=application_id,
            game_name=game_name,
            executable=derived_leaf,
            executable_rel=derived_leaf,
            executable_source="derived",
            bypass_mode="derived",
            epic_app_id=epic_id,
            steam_app_id=steam_id,
            icon_url=icon_url,
        )

    # 5. Universal fallback carrier from detectable catalogue so RunningGameStore + R.XM IPC PID binding works
    carrier_id, carrier_name, carrier_rel = FALLBACK_CARRIERS[0]
    for cid, cname, crel in FALLBACK_CARRIERS:
        if cid in entries_by_id or not entries_by_id:
            carrier_id, carrier_name, carrier_rel = cid, cname, crel
            break
    carrier_leaf = carrier_rel.rsplit("/", 1)[-1]
    return BypassPlan(
        application_id=application_id,
        game_name=game_name,
        executable=carrier_leaf,
        executable_rel=carrier_rel,
        executable_source="catalogue",
        bypass_mode="carrier_ipc_sku" if (epic_id or steam_id) else "carrier_ipc",
        carrier_app_id=carrier_id,
        carrier_app_name=carrier_name,
        epic_app_id=epic_id,
        steam_app_id=steam_id,
        quest_id=matched_quest.quest_id if matched_quest else None,
        quest_name=matched_quest.quest_name if matched_quest else None,
        orb_reward=matched_quest.orb_reward if matched_quest else 0,
        icon_url=icon_url,
        extra_Catalog_executables=(carrier_rel,),
    )


def sync_library_with_discord(
    library: Any,
    index: Any = None,
    *,
    auto_add_enrolled_quests: bool = True,
    auto_add_quests: bool | None = None,
    stage_decoys: bool = True,
    logger: Any = None,
) -> dict[str, Any]:
    """Scan Discord's catalogue and local Quest cache, heal all library entries, and stage decoys."""
    from worthlesstask.decoy import ensure_decoy

    _ = logger
    if auto_add_quests is not None:
        auto_add_enrolled_quests = bool(auto_add_quests)

    quests = discover_discord_quests()
    cached_games = discover_cached_discord_games()

    try:
        raw_cat = index.entries() if index is not None and hasattr(index, "entries") else ()
        cat_entries = list(raw_cat) if isinstance(raw_cat, (list, tuple)) else []
    except Exception:
        cat_entries = []

    # Merge cached games from Discord's local cache into catalogue entries in memory
    by_id: dict[str, dict[str, Any]] = {
        str(e.get("id")): dict(e) for e in cat_entries if isinstance(e, dict) and e.get("id")
    }
    for cg in cached_games:
        cid = str(cg.get("id") or "")
        if not cid:
            continue
        if cid not in by_id:
            by_id[cid] = cg
            cat_entries.append(cg)
        else:
            if not by_id[cid].get("third_party_skus") and cg.get("third_party_skus"):
                by_id[cid]["third_party_skus"] = cg["third_party_skus"]
            if not by_id[cid].get("icon_hash") and cg.get("icon_hash"):
                by_id[cid]["icon_hash"] = cg["icon_hash"]
            if not by_id[cid].get("executables") and cg.get("executables"):
                by_id[cid]["executables"] = cg["executables"]

    # Auto-add enrolled & incomplete desktop quests that are not in the library yet
    added_quests: list[str] = []
    if auto_add_enrolled_quests:
        existing_app_ids = {e.application_id for e in library.entries() if e.application_id}
        for q in quests:
            if not q.is_enrolled or q.is_completed or q.is_expired or not q.primary_app_id:
                continue
            if q.primary_app_id in existing_app_ids:
                continue
            if any(aid in existing_app_ids for aid in q.accepted_app_ids):
                continue
            row = by_id.get(q.primary_app_id)
            title = q.game_title or (str(row.get("name")) if row else q.quest_name)
            icon_hash = row.get("icon_hash") if isinstance(row, dict) else None
            icon_url = (
                f"https://cdn.discordapp.com/app-icons/{q.primary_app_id}/{icon_hash}.png"
                if icon_hash
                else None
            )
            plan = resolve_bypass_plan(title, q.primary_app_id, cat_entries, quests)
            entry = library.add(
                title,
                q.primary_app_id,
                minutes=q.target_minutes,
                executable=plan.executable,
                executable_source=plan.executable_source,
                catalog_icon_url=icon_url,
                executable_rel=plan.executable_rel,
                bypass_mode=plan.bypass_mode,
                epic_app_id=plan.epic_app_id,
                steam_app_id=plan.steam_app_id,
                carrier_app_id=plan.carrier_app_id,
            )
            existing_app_ids.add(q.primary_app_id)
            added_quests.append(entry.slug)
            try:
                library.fetch_catalog_icon(entry.slug)
            except Exception:
                pass

    # Heal all existing entries in the library
    updated_slugs: list[str] = []
    staged_slugs: list[str] = []
    for entry in list(library.entries()):
        app_id = entry.application_id
        row = by_id.get(app_id) if app_id else None
        if row is None and entry.game_name and index is not None and hasattr(index, "best"):
            try:
                cand = index.best(entry.game_name)
                if cand is not None and getattr(cand, "id", None):
                    app_id = str(cand.id)
                    row = by_id.get(app_id)
            except Exception:
                pass
        if not app_id:
            continue

        plan = resolve_bypass_plan(entry.game_name, app_id, cat_entries, quests)
        changes: dict[str, Any] = {}
        if entry.application_id != app_id:
            changes["application_id"] = app_id
        # Always heal derived executables, launcher executables, or missing bypass metadata
        is_bad_exe = (
            not entry.executable
            or entry.executable_source == "derived"
            or "launcher" in (entry.executable or "").lower()
            or (entry.executable_source != "manual" and entry.executable != plan.executable)
        )
        if is_bad_exe:
            changes["executable"] = plan.executable
            changes["executable_source"] = plan.executable_source
        if getattr(entry, "executable_rel", None) != plan.executable_rel:
            changes["executable_rel"] = plan.executable_rel
        if getattr(entry, "bypass_mode", None) != plan.bypass_mode:
            changes["bypass_mode"] = plan.bypass_mode
        if getattr(entry, "epic_app_id", None) != plan.epic_app_id:
            changes["epic_app_id"] = plan.epic_app_id
        if getattr(entry, "steam_app_id", None) != plan.steam_app_id:
            changes["steam_app_id"] = plan.steam_app_id
        if getattr(entry, "carrier_app_id", None) != plan.carrier_app_id:
            changes["carrier_app_id"] = plan.carrier_app_id

        if not entry.catalog_icon_url and isinstance(row, dict) and row.get("icon_hash"):
            changes["catalog_icon_url"] = (
                f"https://cdn.discordapp.com/app-icons/{app_id}/{row['icon_hash']}.png"
            )

        if changes:
            library.update(entry.slug, **changes)
            updated_slugs.append(entry.slug)

        if (changes.get("catalog_icon_url") or entry.catalog_icon_url) and not library.site_icon_path(entry.slug):
            try:
                library.fetch_catalog_icon(entry.slug)
            except Exception:
                pass

        if stage_decoys:
            refreshed = library.get(entry.slug)
            if refreshed and refreshed.executable:
                try:
                    decoy_path = ensure_decoy(
                        refreshed.executable,
                        client_id=refreshed.application_id,
                        subdir_override=getattr(refreshed, "executable_rel", None),
                    )
                    if decoy_path is not None:
                        library.update(
                            refreshed.slug,
                            worker_ready=True,
                            worker_error=None,
                            worker_path=str(decoy_path),
                        )
                    staged_slugs.append(refreshed.slug)
                except Exception:
                    pass

    return {
        "quests": [q.to_dict() for q in quests],
        "added_quests": added_quests,
        "updated_slugs": updated_slugs,
        "staged_slugs": staged_slugs,
    }
