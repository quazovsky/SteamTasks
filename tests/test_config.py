"""Config loading tests — no Discord required."""

from __future__ import annotations

import json
import sys
import tempfile
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from worthlesstask.config.schema import AppConfig, load_config
from worthlesstask.core.errors import ConfigError, ValidationError

VALID_ID = "357607133254254632"


def write_config(directory: Path, payload: dict) -> Path:
    path = directory / "config.json"
    path.write_text(json.dumps(payload), encoding="utf-8")
    return path


class TestValidation(unittest.TestCase):
    def test_valid_config_passes(self):
        AppConfig(client_id=VALID_ID, game_name="The Forest").validate()

    def test_client_id_must_be_numeric(self):
        with self.assertRaises(ValidationError):
            AppConfig(client_id="not-a-snowflake", game_name="G").validate()

    def test_client_id_must_be_long_enough(self):
        with self.assertRaises(ValidationError) as ctx:
            AppConfig(client_id="12345", game_name="G").validate()
        self.assertIn("17-19 digits", str(ctx.exception))

    def test_game_name_required(self):
        with self.assertRaises(ValidationError):
            AppConfig(client_id=VALID_ID, game_name="  ").validate()

    def test_refresh_interval_floor(self):
        with self.assertRaises(ValidationError):
            AppConfig(client_id=VALID_ID, game_name="G", refresh_interval=1.0).validate()

    def test_bad_activity_type(self):
        with self.assertRaises(ValidationError):
            AppConfig(client_id=VALID_ID, game_name="G", activity_type="streaming").validate()

    def test_masked_hides_middle_of_id(self):
        masked = AppConfig(client_id=VALID_ID, game_name="G").masked()
        self.assertNotIn(VALID_ID, masked["client_id"])
        self.assertTrue(masked["client_id"].startswith("357607"))


class TestLoading(unittest.TestCase):
    def test_file_values_are_loaded(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = write_config(Path(tmp), {"client_id": VALID_ID, "game_name": "PEAK"})
            config = load_config(path=path, environ={})
            self.assertEqual(config.game_name, "PEAK")
            self.assertEqual(config.client_id, VALID_ID)

    def test_defaults_apply_when_file_is_sparse(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = write_config(Path(tmp), {"client_id": VALID_ID, "game_name": "PEAK"})
            config = load_config(path=path, environ={})
            self.assertEqual(config.activity_type, "playing")
            self.assertTrue(config.show_elapsed)
            self.assertEqual(config.refresh_interval, 60.0)

    def test_environment_overrides_file(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = write_config(Path(tmp), {"client_id": VALID_ID, "game_name": "PEAK"})
            config = load_config(
                path=path, environ={"WORTHLESSTASK_GAME_NAME": "The Forest"}
            )
            self.assertEqual(config.game_name, "The Forest")

    def test_cli_overrides_environment(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = write_config(Path(tmp), {"client_id": VALID_ID, "game_name": "PEAK"})
            config = load_config(
                path=path,
                overrides={"game_name": "Dota 2"},
                environ={"WORTHLESSTASK_GAME_NAME": "The Forest"},
            )
            self.assertEqual(config.game_name, "Dota 2")

    def test_env_coercion_of_numbers_and_flags(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = write_config(Path(tmp), {"client_id": VALID_ID, "game_name": "G"})
            config = load_config(
                path=path,
                environ={
                    "WORTHLESSTASK_REFRESH_INTERVAL": "30",
                    "WORTHLESSTASK_SHOW_ELAPSED": "false",
                },
            )
            self.assertEqual(config.refresh_interval, 30.0)
            self.assertFalse(config.show_elapsed)

    def test_unknown_field_is_rejected(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = write_config(
                Path(tmp), {"client_id": VALID_ID, "game_name": "G", "typo_field": 1}
            )
            with self.assertRaises(ConfigError) as ctx:
                load_config(path=path, environ={})
            self.assertIn("typo_field", str(ctx.exception))

    def test_missing_file_raises_when_required(self):
        with tempfile.TemporaryDirectory() as tmp:
            with self.assertRaises(ConfigError):
                load_config(path=Path(tmp) / "nope.json", environ={}, require_file=True)

    def test_invalid_json_is_reported(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "config.json"
            path.write_text("{not json", encoding="utf-8")
            with self.assertRaises(ConfigError):
                load_config(path=path, environ={})

    def test_backoff_block_round_trips(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = write_config(
                Path(tmp),
                {
                    "client_id": VALID_ID,
                    "game_name": "G",
                    "backoff": {"base_delay": 2.0, "max_delay": 20.0, "jitter": 0.1},
                },
            )
            config = load_config(path=path, environ={})
            self.assertEqual(config.backoff.base_delay, 2.0)
            self.assertEqual(config.backoff.max_delay, 20.0)

    def test_buttons_are_validated_on_load(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = write_config(
                Path(tmp),
                {
                    "client_id": VALID_ID,
                    "game_name": "G",
                    "buttons": [{"label": "a", "url": "notaurl"}],
                },
            )
            with self.assertRaises(ValidationError):
                load_config(path=path, environ={})


if __name__ == "__main__":
    unittest.main(verbosity=2)
