"""
SQLAlchemy database initialization for Supabase Postgres.

Creates (lazily):
- engine: SQLAlchemy engine using SUPABASE_DB_CONNECTION_STRING
- SessionLocal: session factory for per-request DB sessions
- Base: Declarative base for ORM models
- get_db: FastAPI dependency to provide a session and ensure cleanup

Design change:
- Avoid creating the engine at import time to prevent uvicorn import failures
  when environment variables are not yet present. Instead, provide getters
  that initialize on first use.
"""

from typing import Generator, Optional

from sqlalchemy import create_engine
from sqlalchemy.engine import Engine
from sqlalchemy.orm import Session, declarative_base, sessionmaker

from ..core.config import get_settings
from ..core.logger import get_logger

logger = get_logger(__name__)

# Global ORM base
Base = declarative_base()

# Module-level cached engine and session factory (lazy init)
_engine: Optional[Engine] = None
_SessionLocal: Optional[sessionmaker] = None


def _get_db_url() -> str:
    """
    Resolve database URL from environment variable SUPABASE_DB_CONNECTION_STRING.
    Raises ValueError if missing to make failures explicit at first DB access (not import).
    """
    settings = get_settings()
    url = getattr(settings, "SUPABASE_DB_CONNECTION_STRING", None)
    if not url:
        raise ValueError(
            "SUPABASE_DB_CONNECTION_STRING is not set. "
            "Provide a valid Postgres connection string in .env."
        )
    return url


def _ensure_engine_initialized() -> None:
    """
    Initialize the SQLAlchemy engine and session factory if not already done.
    This function is idempotent and safe to call multiple times.
    """
    global _engine, _SessionLocal
    if _engine is not None and _SessionLocal is not None:
        return
    db_url = _get_db_url()
    # For Supabase Postgres, psycopg2 is suitable; autocommit off, future engine.
    _engine = create_engine(db_url, pool_pre_ping=True, future=True)
    _SessionLocal = sessionmaker(bind=_engine, autocommit=False, autoflush=False, class_=Session, future=True)
    logger.info("SQLAlchemy engine initialized.")


# PUBLIC_INTERFACE
def get_engine() -> Engine:
    """Return the lazily-initialized SQLAlchemy Engine instance."""
    _ensure_engine_initialized()
    assert _engine is not None  # for type checkers
    return _engine


# PUBLIC_INTERFACE
def get_sessionmaker() -> sessionmaker:
    """Return the lazily-initialized SQLAlchemy sessionmaker."""
    _ensure_engine_initialized()
    assert _SessionLocal is not None  # for type checkers
    return _SessionLocal


# PUBLIC_INTERFACE
def get_db() -> Generator[Session, None, None]:
    """Yield a SQLAlchemy session and ensure it is closed after request."""
    SessionLocal = get_sessionmaker()
    db: Session = SessionLocal()
    try:
        yield db
    finally:
        try:
            db.close()
        except Exception as exc:
            logger.error("Error closing DB session", exc_info=exc)
