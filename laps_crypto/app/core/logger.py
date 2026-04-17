"""Structured logger with Portuguese user-facing messages."""

from __future__ import annotations

import logging
import sys
from typing import Optional


def build_logger(name: str = "laps_crypto", level: int = logging.INFO) -> logging.Logger:
    """Build and return a deterministic logger instance."""
    logger = logging.getLogger(name)
    logger.setLevel(level)

    if logger.handlers:
        return logger

    handler = logging.StreamHandler(sys.stdout)
    formatter = logging.Formatter(
        "%(asctime)s | %(levelname)s | %(name)s | %(message)s",
        datefmt="%Y-%m-%d %H:%M:%S",
    )
    handler.setFormatter(formatter)
    logger.addHandler(handler)
    logger.propagate = False
    return logger


def log_event(logger: logging.Logger, message_pt_br: str, extra: Optional[dict] = None) -> None:
    """Log operational event in Portuguese."""
    if extra:
        logger.info("%s | contexto=%s", message_pt_br, extra)
        return
    logger.info("%s", message_pt_br)
