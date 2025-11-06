"""
SQLAlchemy database initialization for Postgres (Supabase-compatible).

Creates (lazily):
- engine: SQLAlchemy engine using DATABASE_URL (preferred) or SUPABASE_DB_CONNECTION_STRING (deprecated)
- SessionLocal: session factory for per-request DB sessions
- Base: Declarative base for ORM models
- get_db: FastAPI dependency to provide a session and ensure cleanup

Design:
- Avoid creating the engine at import time to prevent uvicorn import failures
  when environment variables are not yet present. Instead, provide getters
  that initialize on first use.
"""

from typing import Generator, Optional, Dict, Any
import os

from sqlalchemy import create_engine
from sqlalchemy.engine import Engine
from sqlalchemy.orm import Session, declarative_base, sessionmaker
from sqlalchemy.pool import NullPool

from ..core.config import get_settings
from ..core.logger import get_logger

logger = get_logger(__name__)

# Global ORM base
Base = declarative_base()

# Module-level cached engine and session factory (lazy init)
_engine: Optional[Engine] = None
_SessionLocal: Optional[sessionmaker] = None


def _build_url_from_discrete_env() -> Optional[str]:
    """
    Build a Postgres SQLAlchemy URL from discrete env vars expected by some deployments:
      user, password, host, port, dbname
    Enforces sslmode=require.
    Returns None if any required field is missing.
    """
    user = os.getenv("user")
    password = os.getenv("password")
    host = os.getenv("host")
    port = os.getenv("port")
    dbname = os.getenv("dbname")
    if not all([user, password, host, port, dbname]):
        return None
    return f"postgresql+psycopg2://{user}:{password}@{host}:{port}/{dbname}?sslmode=require"


def _append_sslmode_require(url: str) -> str:
    """
    Ensure sslmode=require is present in the connection string for psycopg2 URLs.
    If a query string already exists, append with &; otherwise, add ?sslmode=require.
    """
    if "postgresql+psycopg2://" not in url:
        return url
    # If any sslmode is already present, do not duplicate; prefer require if not set.
    if "sslmode=" in url:
        return url
    return url + ("&sslmode=require" if "?" in url else "?sslmode=require")


def _ensure_psycopg2_scheme(url: str) -> str:
    """
    Ensure the SQLAlchemy URL uses the psycopg2 driver explicitly.
    """
    if url.startswith("postgresql://"):
        return url.replace("postgresql://", "postgresql+psycopg2://", 1)
    return url


def _get_db_url() -> str:
    """
    Resolve database URL from environment variables.
    Priority:
      1) DATABASE_URL (append sslmode=require if missing)
      2) SUPABASE_DB_CONNECTION_STRING (deprecated; append sslmode=require if missing)
      3) Discrete vars: user/password/host/port/dbname (compose with sslmode=require)
    Raises ValueError if missing to make failures explicit at first DB access (not import).
    """
    settings = get_settings()
    url = (settings.DATABASE_URL or "").strip()
    if url:
        url = _ensure_psycopg2_scheme(url)
        return _append_sslmode_require(url)

    legacy = (settings.SUPABASE_DB_CONNECTION_STRING or "").strip()
    if legacy:
        legacy = _ensure_psycopg2_scheme(legacy)
        return _append_sslmode_require(legacy)

    # Fallback to discrete environment variables
    composed = _build_url_from_discrete_env()
    if composed:
        return composed

    raise ValueError(
        "Database configuration not found. Provide one of: "
        "DATABASE_URL, SUPABASE_DB_CONNECTION_STRING, or discrete env vars "
        "(user, password, host, port, dbname)."
    )


def _effective_db_params(url: str) -> Dict[str, Any]:
    """
    Parse and return effective DB connection params for logging without password.
    Keeps driver scheme and host:port/db details to assist diagnostics.
    """
    # Naive parse sufficient for logging purposes without new deps:
    redacted = url
    if "@" in url and "://" in url:
        scheme, rest = url.split("://", 1)
        if ":" in rest and "@" in rest:
            creds, hostpart = rest.split("@", 1)
            # Redact password if present in creds
            if ":" in creds:
                user = creds.split(":", 1)[0]
                redacted = f"{scheme}://{user}:****@{hostpart}"
            else:
                redacted = f"{scheme}://****@{hostpart}"
        else:
            redacted = f"{scheme}://<no-credentials>"
    return {
        "url_redacted": redacted,
        "driver": "psycopg2" if "psycopg2" in url else "unknown",
        "sslmode_present": ("sslmode=" in url),
    }


# PUBLIC_INTERFACE
def get_effective_db_params() -> Dict[str, Any]:
    """Return redacted effective DB parameters for diagnostics without exposing secrets."""
    try:
        url = _get_db_url()
        return _effective_db_params(url)
    except Exception as exc:
        # If URL resolution fails (e.g., not configured), return a structured hint
        return {"url_redacted": "<unconfigured>", "driver": "unknown", "sslmode_present": False, "error": str(exc)}


def _ensure_engine_initialized() -> None:
    """
    Initialize the SQLAlchemy engine and session factory if not already done.
    This function is idempotent and safe to call multiple times.
    """
    global _engine, _SessionLocal
    if _engine is not None and _SessionLocal is not None:
        return
    settings = get_settings()
    db_url = _get_db_url()

    # Allow disabling pooling in ephemeral preview environments to avoid stale connections.
    use_null_pool = bool(os.getenv("DISABLE_DB_POOL", "").lower() in ("1", "true", "yes"))
    engine_kwargs = {
        "pool_pre_ping": True,
        "future": True,
        "echo": bool(settings.DB_ECHO),
    }
    if use_null_pool:
        engine_kwargs["poolclass"] = NullPool  # type: ignore[assignment]

    _engine = create_engine(db_url, **engine_kwargs)
    _SessionLocal = sessionmaker(bind=_engine, autocommit=False, autoflush=False, class_=Session, future=True)

    eff = _effective_db_params(db_url)
    logger.info(
        "SQLAlchemy engine initialized.",
        extra={"echo": bool(settings.DB_ECHO), "pool": ("NullPool" if use_null_pool else "Default"), **eff},
    )


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
