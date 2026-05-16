"""Application entrypoint."""

from __future__ import annotations

import uvicorn

from .api import create_app
from .config import BotSettings


def run() -> None:
    settings = BotSettings.from_env()
    app = create_app(settings)
    uvicorn.run(app, host=settings.api_host, port=settings.api_port)


if __name__ == "__main__":
    run()
