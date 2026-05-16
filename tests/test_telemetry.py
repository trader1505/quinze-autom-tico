from pathlib import Path
import shutil
import sys
import tempfile
import unittest

ROOT = Path(__file__).resolve().parents[1]
SRC = ROOT / "src"
if str(SRC) not in sys.path:
    sys.path.insert(0, str(SRC))

from laps_bot.telemetry import TelemetryStore


class TelemetryTests(unittest.TestCase):
    def setUp(self) -> None:
        self.tmp_dir = tempfile.mkdtemp(prefix="laps-telemetry-test-")
        self.store = TelemetryStore(self.tmp_dir)

    def tearDown(self) -> None:
        shutil.rmtree(self.tmp_dir, ignore_errors=True)

    def test_emit_and_read_events(self) -> None:
        self.store.emit("tp_hit", "Target reached", {"roi_pct": 100})
        self.store.emit("cash_rebalance", "Rebalance done", {"spot_pct": 80, "futures_pct": 20})
        events = self.store.read_recent_events(limit=10)
        self.assertEqual(len(events), 2)
        self.assertEqual(events[0]["type"], "tp_hit")
        self.assertEqual(events[1]["type"], "cash_rebalance")

    def test_update_state(self) -> None:
        state = self.store.update_state(status="running", symbol="BTC/USDT:USDT", roi_pct=5.5)
        self.assertEqual(state["status"], "running")
        self.assertEqual(state["symbol"], "BTC/USDT:USDT")
        self.assertEqual(state["roi_pct"], 5.5)


if __name__ == "__main__":
    unittest.main()
