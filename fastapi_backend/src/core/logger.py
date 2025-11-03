"""
Basic application logger.

This will be expanded later to include structured logging and per-module loggers.
"""

import logging
from .config import settings


# PUBLIC_INTERFACE
def get_logger(name: str = "app") -> logging.Logger:
    """Get a configured logger instance."""
    logger = logging.getLogger(name)

    # Set level based on settings; default to INFO
    level_name = (settings.LOG_LEVEL or "INFO").upper()
    level = getattr(logging, level_name, logging.INFO)
    logger.setLevel(level)

    # Avoid duplicate handlers
    if not any(isinstance(h, logging.StreamHandler) for h in logger.handlers):
        handler = logging.StreamHandler()
        formatter = logging.Formatter(
            fmt="%(asctime)s | %(levelname)s | %(name)s | %(message)s",
            datefmt="%Y-%m-%d %H:%M:%S",
        )
        handler.setFormatter(formatter)
        logger.addHandler(handler)

    return logger
