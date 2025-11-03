"""
Convenience entrypoint to run the FastAPI app with uvicorn.

This allows environments that look for a top-level main.py to start the server
without custom commands. It binds to 0.0.0.0 and uses PORT env or defaults to 3001.
"""

import os
from contextlib import suppress

import uvicorn  # type: ignore


def _resolve_port() -> int:
    """Resolve the port from environment variable PORT or default to 3001."""
    with suppress(Exception):
        return int(os.getenv("PORT", "3001"))
    return 3001


# PUBLIC_INTERFACE
def main() -> None:
    """Start uvicorn for the FastAPI application on the resolved port."""
    port = _resolve_port()
    # Use module path to app to avoid import side effects here
    uvicorn.run(
        "src.api.main:app",
        host="0.0.0.0",
        port=port,
        log_level="info",
    )


if __name__ == "__main__":
    main()
