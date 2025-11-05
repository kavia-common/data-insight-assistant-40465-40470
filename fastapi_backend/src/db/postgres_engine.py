"""Lightweight SQLAlchemy engine for Postgres using python-dotenv.

This module reads credentials from a .env file (loaded via python-dotenv) using
individual variables:
  - user
  - password
  - host
  - port
  - dbname

It constructs a SQLAlchemy database URL using the psycopg2 driver and exposes a
module-level engine object for optional usage in scripts.

Design:
- No import-time validation errors if environment variables are missing.
- The engine is created from the raw values; if any are None, constructing the URL
  could produce an invalid DSN. We therefore only raise validation errors when
  running as a script (__main__) and attempting the connectivity test.
- This module is not wired into the FastAPI app; it's a standalone utility and
  should not affect app startup.

Usage:
  python -m src.db.postgres_engine
  -> performs a simple connectivity test (SELECT 1) and prints status.
"""

from __future__ import annotations

import os
from sqlalchemy import create_engine
from sqlalchemy.engine import Engine
from sqlalchemy import text
from dotenv import load_dotenv

# Load environment variables from .env at import time safely (no raise if absent)
load_dotenv()

# Read discrete postgres credentials
USER = os.getenv("user")
PASSWORD = os.getenv("password")
HOST = os.getenv("host")
PORT = os.getenv("port")
DBNAME = os.getenv("dbname")

# Build the DATABASE_URL. We avoid validating here to keep imports safe.
# sslmode=require is appended as per instruction.
DATABASE_URL = (
    f"postgresql+psycopg2://{USER}:{PASSWORD}@{HOST}:{PORT}/{DBNAME}?sslmode=require"
)

# Create engine object. Note: If env vars are missing, the URL may be malformed,
# but we do not attempt to connect or validate at import time.
engine: Engine = create_engine(DATABASE_URL)


def _validate_env() -> None:
    """Ensure required env vars exist; used only for main-time checks."""
    missing = [k for k, v in {
        "user": USER,
        "password": PASSWORD,
        "host": HOST,
        "port": PORT,
        "dbname": DBNAME,
    }.items() if not v]
    if missing:
        raise ValueError(
            f"Missing required environment variables in .env: {', '.join(missing)}"
        )


if __name__ == "__main__":
    # Optional connectivity test; validate env then try a simple SELECT 1.
    try:
        _validate_env()
        with engine.connect() as connection:
            # simple ping
            connection.execute(text("SELECT 1"))
            print("Connection successful!")
    except Exception as e:
        print(f"Failed to connect: {e}")
