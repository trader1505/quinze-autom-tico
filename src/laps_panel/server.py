from __future__ import annotations

from pathlib import Path

from flask import Flask, jsonify, request, send_from_directory

from laps_bot.config import BotConfig
from laps_bot.telemetry import TelemetryStore


def create_panel_app(telemetry_dir: str) -> Flask:
    static_dir = Path(__file__).resolve().parent / "static"
    store = TelemetryStore(telemetry_dir)
    app = Flask(__name__, static_folder=str(static_dir), static_url_path="/static")

    @app.get("/")
    def index() -> str:
        return send_from_directory(app.static_folder, "index.html")

    @app.get("/api/health")
    def health() -> tuple[dict[str, str], int]:
        return {"status": "ok"}, 200

    @app.get("/api/state")
    def state() -> tuple[dict, int]:
        return jsonify(store.read_state()), 200

    @app.get("/api/events")
    def events() -> tuple[dict, int]:
        raw_limit = request.args.get("limit", "200")
        try:
            limit = int(raw_limit)
        except ValueError:
            limit = 200
        limit = max(1, min(limit, 2000))
        return jsonify({"events": store.read_recent_events(limit=limit)}), 200

    return app


def run_panel_server(config: BotConfig) -> None:
    app = create_panel_app(config.telemetry_dir)
    app.run(host=config.panel_host, port=config.panel_port, debug=False, use_reloader=False)
