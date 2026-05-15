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


def test_dashboard_save_credentials(monkeypatch) -> None:
    runtime = _build_runtime(monkeypatch)
    app = create_app(runtime=runtime)
    client = app.test_client()

    response = client.post(
        "/acoes/salvar-credenciais",
        data={"api_key": "ABCDEF123456", "api_secret": "SECRET123456"},
        follow_redirects=True,
    )
    assert response.status_code == 200
    assert runtime.client.has_credentials is True
    body = response.get_data(as_text=True)
    assert "Credenciais Binance atualizadas com sucesso" in body
    assert "ABC***456" in body
    assert "SECRET123456" not in body


def test_dashboard_clear_credentials(monkeypatch) -> None:
    runtime = _build_runtime(monkeypatch)
    runtime.client.set_credentials("ABCDEF123456", "SECRET123456")
    app = create_app(runtime=runtime)
    client = app.test_client()

    response = client.post("/acoes/limpar-credenciais", follow_redirects=True)
    assert response.status_code == 200
    assert runtime.client.has_credentials is False


def test_dashboard_automation_start_and_stop(monkeypatch) -> None:
    runtime = _build_runtime(monkeypatch)
    app = create_app(runtime=runtime)
    client = app.test_client()

    start_response = client.post(
        "/acoes/iniciar-automacao",
        data={"intervalo_segundos": "10"},
        follow_redirects=True,
    )
    assert start_response.status_code == 200
    assert "Automação iniciada com intervalo de 10 segundos." in start_response.get_data(as_text=True)
    assert runtime.is_automation_running is True

    stop_response = client.post("/acoes/parar-automacao", follow_redirects=True)
    assert stop_response.status_code == 200
    assert "Automação parada com sucesso." in stop_response.get_data(as_text=True)
    assert runtime.is_automation_running is False

