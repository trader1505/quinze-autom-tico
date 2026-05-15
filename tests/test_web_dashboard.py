"""Tests for Flask dashboard endpoints."""

from decimal import Decimal

from laps_crypto.app.main import LapsCryptoSystem
from laps_crypto.app.web.dashboard import create_app
from laps_crypto.app.web.runtime import DashboardRuntime


def _build_runtime(monkeypatch) -> DashboardRuntime:
    monkeypatch.setenv("LAPS_EXECUTION_MODE", "paper")
    monkeypatch.setenv("LAPS_DEFAULT_SYMBOL", "BTCUSDT")
    system = LapsCryptoSystem.bootstrap()
    system.client.set_mark_price("BTCUSDT", Decimal("50000"))
    return DashboardRuntime(system=system)


def test_dashboard_index_renders(monkeypatch) -> None:
    runtime = _build_runtime(monkeypatch)
    app = create_app(runtime=runtime)
    client = app.test_client()

    response = client.get("/")
    assert response.status_code == 200
    body = response.get_data(as_text=True)
    assert "Painel LAPS Crypto" in body
    assert "Fechamento seguro" in body


def test_dashboard_open_order_flow(monkeypatch) -> None:
    runtime = _build_runtime(monkeypatch)
    app = create_app(runtime=runtime)
    client = app.test_client()

    response = client.post(
        "/acoes/abrir-ordem",
        data={"symbol": "BTCUSDT", "side": "LONG", "quantity": "0.010"},
        follow_redirects=True,
    )
    assert response.status_code == 200
    position = runtime.client.get_position("BTCUSDT")
    assert position is not None
    assert position.quantity == Decimal("0.010")

