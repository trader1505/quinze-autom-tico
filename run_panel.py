from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parent
SRC = ROOT / "src"
if str(SRC) not in sys.path:
    sys.path.insert(0, str(SRC))

from laps_bot.config import load_config
from laps_bot.logger import setup_logger
from laps_panel.server import run_panel_server


def main() -> None:
    config = load_config()
    setup_logger(config.log_level)
    run_panel_server(config)


if __name__ == "__main__":
    main()
