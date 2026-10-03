"""Open the presence window straight from source (no PyInstaller round trip).

Used while iterating on the design: it paints the real window, so a screenshot of
it is the real thing rather than a mock.
"""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from worthlesstask.config.schema import AppConfig
from worthlesstask.ui.window import run_with_window


def main() -> int:
    game = sys.argv[1] if len(sys.argv) > 1 else "ARKNIGHTS: ENDFIELD"
    icon = sys.argv[2] if len(sys.argv) > 2 and sys.argv[2] else None
    config = AppConfig(client_id="1461154307171811401", game_name=game, log_file=None)
    config.validate()
    return run_with_window(config, icon_path=icon)


if __name__ == "__main__":
    raise SystemExit(main())
