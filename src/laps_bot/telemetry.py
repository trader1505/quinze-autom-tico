from __future__ import annotations

import json
import threading
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

    def read_events(self, limit: int | None = 200) -> list[dict[str, Any]]:
        if limit is not None and limit <= 0:
            return []
        with self._lock:
            if not self.events_path.exists():
                return []
            if limit is None:
                with self.events_path.open("r", encoding="utf-8") as f:
                    lines = list(f)
            else:
                lines = self._read_last_event_lines(limit)
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

    def read_recent_events(self, limit: int = 200) -> list[dict[str, Any]]:
        return self.read_events(limit=limit)

    def _read_last_event_lines(self, limit: int) -> list[str]:
        chunk_size = 8192
        lines: list[str] = []
        with self.events_path.open("rb") as f:
            f.seek(0, 2)
            file_size = f.tell()
            if file_size <= 0:
                return lines
            data = b""
            position = file_size
            newline_count = 0
            while position > 0 and newline_count <= limit:
                read_size = min(chunk_size, position)
                position -= read_size
                f.seek(position)
                data = f.read(read_size) + data
                newline_count = data.count(b"\n")
        raw_lines = data.splitlines()[-limit:]
        return [line.decode("utf-8", errors="ignore") for line in raw_lines]
