"""HTTP API + dashboard for bot control."""

from __future__ import annotations

from pathlib import Path

from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse

from .config import BotSettings
from .engine import TradingEngine
from .gateway import BinanceGateway, SimulationGateway
from .models import BalanceSnapshot, Position, Side

BASE_DIR = Path(__file__).resolve().parents[2]
DASHBOARD_FILE = BASE_DIR / "static" / "dashboard.html"


def build_engine(settings: BotSettings) -> TradingEngine:
    if settings.dry_run:
        gateway = SimulationGateway(
            close_prices=[100 + i * 0.1 for i in range(80)],
            balances=BalanceSnapshot(
                spot_usdt=80.0,
                futures_wallet_usdt=20.0,
                futures_free_usdt=20.0,
                margin_ratio=0.10,
            ),
            position=Position(side=Side.FLAT, quantity=0, entry_price=0, mark_price=100),
        )
        return TradingEngine(settings, gateway)

    if not settings.binance_api_key or not settings.binance_api_secret:
        raise ValueError("BINANCE_API_KEY e BINANCE_API_SECRET são obrigatórios em modo live")
    return TradingEngine(
        settings=settings,
        gateway=BinanceGateway(settings.binance_api_key, settings.binance_api_secret),
    )


def create_app(settings: BotSettings | None = None) -> FastAPI:
    settings = settings or BotSettings.from_env()
    engine = build_engine(settings)
    app = FastAPI(title="LAPS 1505 Bot", version="1.0.0")
    app.add_middleware(
        CORSMiddleware,
        allow_origins=["*"],
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
    )

    @app.get("/")
    def dashboard() -> FileResponse:
        if not DASHBOARD_FILE.exists():
            raise HTTPException(status_code=404, detail="Dashboard não encontrado")
        return FileResponse(DASHBOARD_FILE)

    @app.get("/api/status")
    def status() -> dict:
        return engine.status()

    @app.post("/api/start")
    def start() -> dict:
        engine.start()
        return {"ok": True, "running": True}

    @app.post("/api/stop")
    def stop() -> dict:
        engine.stop()
        return {"ok": True, "running": False}

    @app.post("/api/cycle")
    def cycle() -> dict:
        engine.cycle_once()
        return {"ok": True, "status": engine.status()}

    return app
