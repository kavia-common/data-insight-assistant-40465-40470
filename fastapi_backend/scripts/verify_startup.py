#!/usr/bin/env python3
"""
Utility script to validate FastAPI backend readiness.

- Verifies requirements are importable (uvicorn, fastapi)
- Verifies 'src.api.main:app' can be imported
- Starts a temporary uvicorn server on 0.0.0.0:3001 (or PORT env) in-process
- Probes GET /health (no-DB) and exits 0 on success, non-zero otherwise

This script is intended for local/CI diagnostics.
"""
import os
import sys
import time
import threading
import socket
import contextlib


def _port():
    with contextlib.suppress(Exception):
        return int(os.getenv("PORT", "3001"))
    return 3001


def _check_imports():
    try:
        import fastapi  # noqa: F401
        import uvicorn  # noqa: F401
    except Exception as exc:
        print(f"[verify] Import failure: {exc}", file=sys.stderr)
        sys.exit(2)
    try:
        # Ensure app import works
        from src.api.main import app  # noqa: F401
    except Exception as exc:
        print(f"[verify] Failed to import src.api.main:app -> {exc}", file=sys.stderr)
        sys.exit(3)


def _wait_port(host: str, port: int, timeout: float = 10.0) -> bool:
    deadline = time.time() + timeout
    while time.time() < deadline:
        with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
            s.settimeout(1.0)
            if s.connect_ex((host, port)) == 0:
                return True
        time.sleep(0.25)
    return False


def main():
    _check_imports()
    import uvicorn
    from src.api.main import app
    port = _port()

    server = uvicorn.Server(
        config=uvicorn.Config(
            app,
            host="0.0.0.0",
            port=port,
            log_level="info",
        )
    )

    t = threading.Thread(target=server.run, daemon=True)
    t.start()

    if not _wait_port("127.0.0.1", port, timeout=15.0):
        print(f"[verify] Server did not open port {port}", file=sys.stderr)
        sys.exit(4)

    # Probe /health
    import http.client
    conn = http.client.HTTPConnection("127.0.0.1", port, timeout=5)
    try:
        conn.request("GET", "/health")
        resp = conn.getresponse()
        body = resp.read().decode("utf-8", errors="ignore")
        if resp.status == 200 and '"ok"' in body:
            print("[verify] Health check passed.")
            sys.exit(0)
        else:
            print(f"[verify] Health check failed: {resp.status} {body}", file=sys.stderr)
            sys.exit(5)
    except Exception as exc:
        print(f"[verify] Exception during health check: {exc}", file=sys.stderr)
        sys.exit(6)
    finally:
        with contextlib.suppress(Exception):
            conn.close()
        # uvicorn server thread will exit when process exits


if __name__ == "__main__":
    main()
