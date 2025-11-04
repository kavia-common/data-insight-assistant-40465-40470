"""
SQLAlchemy database initialization for Supabase Postgres.

Creates:
- engine: SQLAlchemy engine using SUPABASE_DB_CONNECTION_STRING
- SessionLocal: session factory for per-request DB sessions
- Base: Declarative base for ORM models
- get_db: FastAPI dependency to provide a session and ensure cleanup
"""

from typing import Generator

from sqlalchemy import create_engine
from sqlalchemy.orm import Session, declarative_base, sessionmaker

from ..core.config import get_settings
from ..core.logger import get_logger

logger = get_logger(__name__)

# Global ORM base
Base = declarative_base()


def _get_db_url() -> str:
    """
    Resolve database URL from environment variable SUPABASE_DB_CONNECTION_STRING.
    Raises ValueError if missing to make failures explicit at startup.
    """
    settings = get_settings()
    url = getattr(settings, "SUPABASE_DB_CONNECTION_STRING", None)
    if not url:
        raise ValueError(
            "SUPABASE_DB_CONNECTION_STRING is not set. "
            "Provide a valid Postgres connection string in .env."
        )
    return url


# Create engine and session factory on import. This will raise early if config missing.
DB_URL = _get_db_url()
# For Supabase Postgres, psycopg2 is suitable; autocommit off, future engine.
engine = create_engine(DB_URL, pool_pre_ping=True, future=True)
SessionLocal = sessionmaker(bind=engine, autocommit=False, autoflush=False, class_=Session, future=True)


# PUBLIC_INTERFACE
def get_db() -> Generator[Session, None, None]:
    """Yield a SQLAlchemy session and ensure it is closed after request."""
    db: Session = SessionLocal()
    try:
        yield db
    finally:
        try:
            db.close()
        except Exception as exc:
            logger.error("Error closing DB session", exc_info=exc)
