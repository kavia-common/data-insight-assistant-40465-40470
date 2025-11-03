"""
Application logging utilities.

Configures a root logger with a stream handler, level from settings, and a
lightweight JSON-like formatter for structured logs.
"""

import json
import logging
import sys
from typing import Any, Dict

from .config import get_settings


class _JsonLikeFormatter(logging.Formatter):
    """Simple JSON-like formatter for log records."""

    def format(self, record: logging.LogRecord) -> str:
        payload: Dict[str, Any] = {
            "ts": self.formatTime(record, datefmt="%Y-%m-%dT%H:%M:%S"),
            "level": record.levelname,
            "logger": record.name,
            "message": record.getMessage(),
        }
        # Attach extras if present
        for attr in ("pathname", "lineno", "funcName"):
            payload[attr] = getattr(record, attr, None)
        if record.exc_info:
            payload["exc_info"] = self.formatException(record.exc_info)
        return json.dumps(payload, ensure_ascii=False)


def _configure_root_logger() -> None:
    """Configure the root logger exactly once."""
    settings = get_settings()
    root = logging.getLogger()
    if getattr(root, "_configured_by_app", False):
        return

    # Clear existing handlers to avoid duplicates in reloads
    for h in list(root.handlers):
        root.removeHandler(h)

    level = getattr(logging, (settings.LOG_LEVEL or "INFO").upper(), logging.INFO)
    root.setLevel(level)

    handler = logging.StreamHandler(stream=sys.stdout)
    # Choose JSON-like formatter; can be swapped to plain if needed
    handler.setFormatter(_JsonLikeFormatter())
    root.addHandler(handler)

    # Marker to prevent reconfiguration
    setattr(root, "_configured_by_app", True)


# PUBLIC_INTERFACE
def get_logger(name: str = "app") -> logging.Logger:
    """Get a configured logger instance.

    Ensures the root logger is configured before returning the named logger.
    """
    _configure_root_logger()
    return logging.getLogger(name)
