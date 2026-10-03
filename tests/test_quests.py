from __future__ import annotations

import json
import tempfile
import unittest
from pathlib import Path
from unittest import mock

from worthlesstask.library import Library
from worthlesstask.presence.quests import (
    DiscordQuest,
    resolve_bypass_plan,
    sync_library_with_discord,
)


class TestQuestsAndBypass(unittest.TestCase):
    def setUp(self) -> None:
        self.sample_entries = [
            {
                "id": "1531874756096295054",
                "name": "EA SPORTS FC™ 27",
                "aliases": [],
                "executables": [],
                "overlay": True,
                "third_party_skus": [{"distributor": "epic", "id": "E7F4AC33FF3D4CE4B243075F0B5DBA84"}],
            },
            {
                "id": "1405609815337996408",
                "name": "EA SPORTS FC 26",
                "aliases": ["FC 26"],
                "executables": [
                    {"name": "ea sports fc 26/fc26.exe", "os": "win32", "is_launcher": False},
                    {"name": "fc26_trial.exe", "os": "win32", "is_launcher": False},
                ],
                "overlay": True,
            },
            {
                "id": "1124351860376096858",
                "name": "Example Launcher Game",
                "aliases": [],
                "executables": [
                    {"name": "launcher.exe", "os": "win32", "is_launcher": True},
                    {"name": "binaries/win64/game-win64-shipping.exe", "os": "win32", "is_launcher": False},
                ],
            },
        ]
        self.sample_quest = DiscordQuest(
            quest_id="1551969525602451497",
            quest_name="EA SPORTS FC 27 Quest",
            game_title="EA SPORTS FC™ 27",
            primary_app_id="1531874756096295054",
            primary_app_name="EA SPORTS FC™ 27",
            accepted_app_ids=("1531874756096295054",),
            task_type="PLAY_ON_DESKTOP",
            target_seconds=900,
            progress_seconds=120,
            enrolled_at="2026-03-31T18:45:17+00:00",
            completed_at=None,
            expires_at="2099-04-06T17:00:00+00:00",
            reward_name="700 Orbs",
            orb_reward=700,
        )

    def test_resolve_bypass_plan_for_empty_executable_ea_fc27_uses_franchise_carrier(self) -> None:
        plan = resolve_bypass_plan(
            "EA SPORTS FC™ 27",
            "1531874756096295054",
            self.sample_entries,
            quests=[self.sample_quest],
        )
        self.assertEqual(plan.application_id, "1531874756096295054")
        self.assertEqual(plan.carrier_app_id, "1405609815337996408")
        self.assertEqual(plan.executable, "fc26.exe")
        self.assertEqual(plan.executable_rel, "ea sports fc 26/fc26.exe")
        self.assertEqual(plan.epic_app_id, "E7F4AC33FF3D4CE4B243075F0B5DBA84")
        self.assertEqual(plan.bypass_mode, "carrier_ipc_sku")
        self.assertEqual(plan.quest_id, "1551969525602451497")

    def test_resolve_bypass_plan_skips_launcher_and_preserves_subfolder_path(self) -> None:
        plan = resolve_bypass_plan(
            "Example Launcher Game",
            "1124351860376096858",
            self.sample_entries,
            quests=[],
        )
        self.assertEqual(plan.executable, "game-win64-shipping.exe")
        self.assertEqual(plan.executable_rel, "binaries/win64/game-win64-shipping.exe")
        self.assertEqual(plan.bypass_mode, "subdir_exe")

    def test_sync_library_heals_broken_ea_fc27_and_adds_enrolled_quests(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            lib_path = Path(tmp) / "library.json"
            broken_payload = {
                "games": [
                    {
                        "slug": "ea-sports-fc-27",
                        "game_name": "EA SPORTS FC™ 27",
                        "executable": "ea_sports_fc_27.exe",
                        "executable_source": "derived",
                        "application_id": "1531874756096295054",
                    }
                ],
                "queue": [],
            }
            lib_path.write_text(json.dumps(broken_payload), encoding="utf-8")
            store = Library(lib_path, icons_dir=Path(tmp) / "icons")

            fake_index = mock.Mock()
            fake_index.entries.return_value = self.sample_entries

            with mock.patch(
                "worthlesstask.presence.quests.discover_cached_discord_games",
                return_value=[],
            ), mock.patch(
                "worthlesstask.presence.quests.discover_discord_quests",
                return_value=[self.sample_quest],
            ):
                report = sync_library_with_discord(
                    store,
                    fake_index,
                    auto_add_enrolled_quests=True,
                    stage_decoys=False,
                )

            self.assertEqual(report["updated_slugs"], ["ea-sports-fc-27"])
            healed = store.get("ea-sports-fc-27")
            self.assertEqual(healed.executable, "fc26.exe")
            self.assertEqual(healed.executable_rel, "ea sports fc 26/fc26.exe")
            self.assertEqual(healed.executable_source, "catalogue")
            self.assertEqual(healed.carrier_app_id, "1405609815337996408")
            self.assertEqual(healed.bypass_mode, "carrier_ipc_sku")
            self.assertEqual(healed.epic_app_id, "E7F4AC33FF3D4CE4B243075F0B5DBA84")
            self.assertTrue(healed.can_start)


if __name__ == "__main__":
    unittest.main()
