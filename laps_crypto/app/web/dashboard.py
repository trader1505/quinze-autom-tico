"""Flask web dashboard entrypoint for LAPS Crypto."""

from __future__ import annotations

import os

from flask import Flask, flash, redirect, render_template, request, url_for

from .runtime import DashboardRuntime


def create_app(runtime: DashboardRuntime | None = None) -> Flask:
    """Create and configure Flask app."""
    app = Flask(__name__, template_folder="templates", static_folder="static")
    app.secret_key = os.getenv("LAPS_WEB_SECRET", "laps-crypto-secret-local")
    dashboard_runtime = runtime or DashboardRuntime.bootstrap()

    @app.get("/")
    def index():
        data = dashboard_runtime.dashboard_data()
        return render_template("dashboard.html", data=data)

    @app.post("/acoes/executar-ciclo")
    def execute_cycle():
        result = dashboard_runtime.run_cycle()
        flash(result.message_pt_br, "sucesso" if result.success else "erro")
        return redirect(url_for("index"))

    @app.post("/acoes/abrir-ordem")
    def open_order():
        result = dashboard_runtime.open_order(
            symbol=request.form.get("symbol", ""),
            side_raw=request.form.get("side", ""),
            quantity_raw=request.form.get("quantity", ""),
        )
        flash(result.message_pt_br, "sucesso" if result.success else "erro")
        return redirect(url_for("index"))

    @app.post("/acoes/avaliar-fechamento")
    def evaluate_close():
        result = dashboard_runtime.evaluate_close(
            symbol=request.form.get("symbol", ""),
        )
        flash(result.message_pt_br, "sucesso" if result.success else "erro")
        return redirect(url_for("index"))

    @app.post("/acoes/fechar-seguro")
    def close_safe():
        result = dashboard_runtime.close_position_safe(
            symbol=request.form.get("symbol", ""),
        )
        flash(result.message_pt_br, "sucesso" if result.success else "erro")
        return redirect(url_for("index"))

    @app.post("/acoes/ajustar-preco")
    def update_mark_price():
        result = dashboard_runtime.set_mark_price(
            symbol=request.form.get("symbol", ""),
            mark_price_raw=request.form.get("mark_price", ""),
        )
        flash(result.message_pt_br, "sucesso" if result.success else "erro")
        return redirect(url_for("index"))

    @app.post("/acoes/limpar-dust")
    def cleanup_dust():
        result = dashboard_runtime.cleanup_dust()
        flash(result.message_pt_br, "sucesso" if result.success else "erro")
        return redirect(url_for("index"))

    @app.post("/acoes/salvar-credenciais")
    def save_credentials():
        result = dashboard_runtime.save_api_credentials(
            api_key_raw=request.form.get("api_key", ""),
            api_secret_raw=request.form.get("api_secret", ""),
        )
        flash(result.message_pt_br, "sucesso" if result.success else "erro")
        return redirect(url_for("index"))

    @app.post("/acoes/limpar-credenciais")
    def clear_credentials():
        result = dashboard_runtime.clear_api_credentials()
        flash(result.message_pt_br, "sucesso" if result.success else "erro")
        return redirect(url_for("index"))

    return app


def run() -> None:
    """Run web dashboard with environment configuration."""
    host = os.getenv("LAPS_WEB_HOST", "0.0.0.0")
    port = int(os.getenv("LAPS_WEB_PORT", "8080"))
    debug = os.getenv("LAPS_WEB_DEBUG", "false").strip().lower() in {"1", "true", "on", "yes"}
    app = create_app()
    app.run(host=host, port=port, debug=debug)


if __name__ == "__main__":
    run()

