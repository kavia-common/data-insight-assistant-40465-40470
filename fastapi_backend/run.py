"""
Uvicorn launcher for the FastAPI app.

Reads port from Settings (env/.env) and starts the server on 0.0.0.0.
This ensures the backend binds to port 3001 by default and can be used
in environments that prefer `python run.py` over a shell uvicorn command.
"""

import os
from contextlib import suppress

import uvicorn  # type: ignore

from src.core.config import get_settings
from src.core.logger import get_logger

logger = get_logger(__name__)


def _get_port() -> int:
    """
    Resolve the port to bind:
    - Prefer Settings.PORT (pydantic BaseSettings reads .env/env automatically)
    - Fallback to PORT env var if somehow settings isn't loaded
    - Default to 3001
    """
    try:
        settings = get_settings()
        port = int(settings.PORT or 3001)
        return port
    except Exception:
        with suppress(Exception):
            return int(os.getenv("PORT", "3001"))
        return 3001


# PUBLIC_INTERFACE
def main() -> None:
    """Start the FastAPI application with uvicorn."""
    port = _get_port()
    logger.info("Starting uvicorn server", extra={"port": port})
    uvicorn.run(
        "src.api.main:app",
        host="0.0.0.0",
        port=port,
        reload=bool(os.getenv("UVICORN_RELOAD", "").lower() in ("1", "true", "yes")),
        log_level="info",
    )


if __name__ == "__main__":
    main()
