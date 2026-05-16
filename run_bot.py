from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parent
SRC = ROOT / "src"
if str(SRC) not in sys.path:
    sys.path.insert(0, str(SRC))

from laps_bot.bot import LapsBot
from laps_bot.config import load_config
from laps_bot.logger import setup_logger


def main() -> None:
    config = load_config()
    setup_logger(config.log_level)
    bot = LapsBot(config)
    bot.run_forever()


if __name__ == "__main__":
    main()
