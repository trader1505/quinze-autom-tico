from __future__ import annotations

from pathlib import Path

from flask import Flask, jsonify, request, send_from_directory

from laps_bot.config import BotConfig
from laps_bot.telemetry import TelemetryStore


def _float_or_zero(value: object) -> float:
    try:
        return float(value)  # type: ignore[arg-type]
    except (TypeError, ValueError):
        return 0.0


def _build_summary(state: dict, events: list[dict]) -> dict:
    tp_hits = 0
    tp_realized = 0.0
    recovery_closed = 0
    recovery_realized = 0.0
    topups = 0
    topup_transferred = 0.0
    errors = 0
    last_tp_at: str | None = None
    last_recovery_close_at: str | None = None
    last_cash_rebalance_at: str | None = None

    for event in events:
        event_type = event.get("type")
        payload = event.get("payload", {}) or {}
        if event_type == "tp_hit":
            tp_hits += 1
            tp_realized += _float_or_zero(payload.get("estimated_realized_pnl_usdt"))
            last_tp_at = event.get("ts")  # type: ignore[assignment]
        elif event_type == "reinforcement_recovered_close":
            recovery_closed += 1
            recovery_realized += _float_or_zero(payload.get("estimated_realized_pnl_usdt"))
            last_recovery_close_at = event.get("ts")  # type: ignore[assignment]
        elif event_type == "margin_topped_up":
            topups += 1
            topup_transferred += _float_or_zero(payload.get("topup_amount_usdt"))
        elif event_type == "cash_rebalance":
            last_cash_rebalance_at = event.get("ts")  # type: ignore[assignment]
        if event.get("severity") == "error":
            errors += 1

    positions = state.get("positions", []) or []
    open_long = 0
    open_short = 0
    recoveries_ongoing = 0
    for item in positions:
        side = str(item.get("side", "")).lower()
        if side == "long":
            open_long += 1
        elif side == "short":
            open_short += 1
        if bool(item.get("reinforcement_alert")) or bool(item.get("reinforcement_done")):
            recoveries_ongoing += 1

    return {
        "events_processed": len(events),
        "open_positions": len(positions),
        "open_long": open_long,
        "open_short": open_short,
        "tp_hits": tp_hits,
        "tp_realized_pnl_usdt": tp_realized,
        "recovery_closed_count": recovery_closed,
        "recovery_closed_realized_pnl_usdt": recovery_realized,
        "recoveries_ongoing_count": recoveries_ongoing,
        "closed_profit_total_usdt": tp_realized + recovery_realized,
        "topup_count": topups,
        "topup_total_usdt": topup_transferred,
        "error_count": errors,
        "last_tp_at": last_tp_at,
        "last_recovery_close_at": last_recovery_close_at,
        "last_cash_rebalance_at": last_cash_rebalance_at,
    }


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
        limit = max(1, min(limit, 10000))
        return jsonify({"events": store.read_recent_events(limit=limit)}), 200

    @app.get("/api/summary")
    def summary() -> tuple[dict, int]:
        state = store.read_state()
        events = store.read_events(limit=10000)
        return jsonify(_build_summary(state, events)), 200

    return app


def run_panel_server(config: BotConfig) -> None:
    app = create_panel_app(config.telemetry_dir)
    app.run(host=config.panel_host, port=config.panel_port, debug=False, use_reloader=False)
