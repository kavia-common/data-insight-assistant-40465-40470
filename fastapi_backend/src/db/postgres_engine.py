"""Lightweight, lazy SQLAlchemy engine helper for Postgres using python-dotenv.

This module reads discrete credentials from .env when explicitly asked to build a URL:
  - user
  - password
  - host
  - port
  - dbname

Critical behavior:
- NO ENGINE IS CREATED AT IMPORT TIME. This prevents accidental DB initialization
  if this module is imported anywhere in the application.
- Use get_engine() to construct an Engine lazily and only when needed by scripts.
- This module is not wired into the FastAPI app; it is a standalone utility.

Usage:
  python -m src.db.postgres_engine
  -> performs a simple connectivity test (SELECT 1) and prints status.
"""

from __future__ import annotations

import os
from typing import Optional, Tuple

from sqlalchemy import create_engine, text
from sqlalchemy.engine import Engine
from dotenv import load_dotenv

# Load environment variables from .env at import time safely (no raise if absent)
load_dotenv()


def _read_env_parts() -> Tuple[Optional[str], Optional[str], Optional[str], Optional[str], Optional[str]]:
    """Return discrete credential parts from environment."""
    return (
        os.getenv("user"),
        os.getenv("password"),
        os.getenv("host"),
        os.getenv("port"),
        os.getenv("dbname"),
    )


def _build_url() -> str:
    """Compose a psycopg2 SQLAlchemy URL from discrete env vars, enforcing sslmode=require."""
    user, password, host, port, dbname = _read_env_parts()
    if not all([user, password, host, port, dbname]):
        raise ValueError(
            "Missing required environment variables in .env: user, password, host, port, dbname"
        )
    return f"postgresql+psycopg2://{user}:{password}@{host}:{port}/{dbname}?sslmode=require"


# PUBLIC_INTERFACE
def get_engine() -> Engine:
    """Return a new SQLAlchemy Engine constructed from discrete env vars (lazy)."""
    url = _build_url()
    return create_engine(url)


def _validate_env() -> None:
    """Ensure required env vars exist; used only for main-time checks."""
    user, password, host, port, dbname = _read_env_parts()
    missing = [k for k, v in {
        "user": user,
        "password": password,
        "host": host,
        "port": port,
        "dbname": dbname,
    }.items() if not v]
    if missing:
        raise ValueError(f"Missing required environment variables in .env: {', '.join(missing)}")


if __name__ == "__main__":
    # Optional connectivity test; validate env then try a simple SELECT 1.
    try:
        _validate_env()
        engine = get_engine()
        with engine.connect() as connection:
            connection.execute(text("SELECT 1"))
            print("Connection successful!")
    except Exception as e:
        print(f"Failed to connect: {e}")
