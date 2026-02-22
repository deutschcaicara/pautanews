"""JSON structured logging configuration."""
from __future__ import annotations

import logging
import sys

from pythonjsonlogger.json import JsonFormatter

from app.config import settings


def setup_logging() -> None:
    """Configure root logger with JSON output for production observability."""
    handler = logging.StreamHandler(sys.stdout)

    formatter = JsonFormatter(
        fmt="%(asctime)s %(levelname)s %(name)s %(message)s",
        rename_fields={
            "asctime": "timestamp",
            "levelname": "level",
            "name": "logger",
        },
    )
    handler.setFormatter(formatter)

    root = logging.getLogger()
    root.handlers.clear()
    root.addHandler(handler)
    root.setLevel(settings.APP_LOG_LEVEL)

    # Quieten noisy libraries
    logging.getLogger("uvicorn.access").setLevel(logging.WARNING)
    logging.getLogger("celery").setLevel(logging.INFO)
    logging.getLogger("sqlalchemy.engine").setLevel(
        logging.INFO if settings.APP_ENV == "development" else logging.WARNING
    )
