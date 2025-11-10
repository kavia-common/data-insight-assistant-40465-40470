#!/usr/bin/env python3
"""
Verify that /health and /debug/config return 200 without any database connectivity.

This script assumes the FastAPI app is running on 127.0.0.1:<PORT> (default 3001).
It does not require an actual database. It is intended to be run in environments where
the configured DB is intentionally unreachable.

Usage:
  python scripts/verify_no_db_endpoints.py
  PORT=3001 python scripts/verify_no_db_endpoints.py
"""
import os
import sys
import http.client
import json


def _port() -> int:
    try:
        return int(os.getenv("PORT", "3001"))
    except Exception:
        return 3001


def _check(path: str) -> None:
    conn = http.client.HTTPConnection("127.0.0.1", _port(), timeout=5)
    try:
        conn.request("GET", path)
        resp = conn.getresponse()
        body = resp.read().decode("utf-8", errors="ignore")
        if resp.status != 200:
            print(f"[verify] {path} -> {resp.status} {body}", file=sys.stderr)
            sys.exit(1)
        print(f"[verify] {path} OK: {resp.status}")
        # Quick sanity checks
        if path == "/health":
            try:
                data = json.loads(body)
                if data.get("status") != "ok":
                    print(f"[verify] /health payload unexpected: {body}", file=sys.stderr)
                    sys.exit(2)
            except Exception as exc:
                print(f"[verify] /health invalid JSON: {exc}", file=sys.stderr)
                sys.exit(3)
    finally:
        try:
            conn.close()
        except Exception:
            pass


def main():
    _check("/health")
    _check("/debug/config")
    print("[verify] No-DB endpoints verified successfully.")
    sys.exit(0)


if __name__ == "__main__":
    main()
