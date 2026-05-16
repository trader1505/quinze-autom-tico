from __future__ import annotations

import json
import threading
from collections import deque
from datetime import datetime, timezone
from pathlib import Path
from typing import Any


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


class TelemetryStore:
    def __init__(self, directory: str) -> None:
        self.base_dir = Path(directory)
        self.base_dir.mkdir(parents=True, exist_ok=True)
        self.events_path = self.base_dir / "events.jsonl"
        self.state_path = self.base_dir / "state.json"
        self._lock = threading.Lock()
        if not self.state_path.exists():
            self._write_state({"status": "booting", "updated_at": _now_iso()})

    def emit(
        self,
        event_type: str,
        message: str,
        payload: dict[str, Any] | None = None,
        severity: str = "info",
    ) -> dict[str, Any]:
        event: dict[str, Any] = {
            "ts": _now_iso(),
            "type": event_type,
            "message": message,
            "severity": severity,
            "payload": payload or {},
        }
        with self._lock:
            with self.events_path.open("a", encoding="utf-8") as f:
                f.write(json.dumps(event, ensure_ascii=True) + "\n")
        return event

    def _read_state(self) -> dict[str, Any]:
        if not self.state_path.exists():
            return {"status": "unknown", "updated_at": _now_iso()}
        with self.state_path.open("r", encoding="utf-8") as f:
            return json.load(f)

    def _write_state(self, state: dict[str, Any]) -> None:
        with self.state_path.open("w", encoding="utf-8") as f:
            json.dump(state, f, ensure_ascii=True, indent=2)

    def update_state(self, **patch: Any) -> dict[str, Any]:
        with self._lock:
            state = self._read_state()
            state.update(patch)
            state["updated_at"] = _now_iso()
            self._write_state(state)
            return state

    def read_state(self) -> dict[str, Any]:
        with self._lock:
            return self._read_state()

    def read_recent_events(self, limit: int = 200) -> list[dict[str, Any]]:
        if limit <= 0:
            return []
        with self._lock:
            if not self.events_path.exists():
                return []
            with self.events_path.open("r", encoding="utf-8") as f:
                lines = deque(f, maxlen=limit)
        events: list[dict[str, Any]] = []
        for line in lines:
            raw = line.strip()
            if not raw:
                continue
            try:
                events.append(json.loads(raw))
            except json.JSONDecodeError:
                # Skip malformed lines to keep panel resilient.
                continue
        return events
