"""JSON structured logging setup."""

from __future__ import annotations

import logging
import sys
from io import IOBase

from pythonjsonlogger.jsonlogger import JsonFormatter


def setup_logger(
    name: str,
    level: str = "INFO",
    stream: IOBase | None = None,
) -> logging.Logger:
    logger = logging.getLogger(name)
    logger.setLevel(getattr(logging, level.upper(), logging.INFO))
    logger.handlers.clear()
    logger.propagate = False

    handler = logging.StreamHandler(stream=stream or sys.stdout)
    handler.setFormatter(JsonFormatter("%(asctime)s %(levelname)s %(name)s %(message)s"))
    logger.addHandler(handler)
    return logger
