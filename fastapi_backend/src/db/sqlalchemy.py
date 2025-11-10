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
    Enforces sslmode=require and port=5432 (default if missing).
    Returns None if any required field is missing.
    """
    user = os.getenv("user")
    password = os.getenv("password")
    host = os.getenv("host")
    port = os.getenv("port") or "5432"
    dbname = os.getenv("dbname")
    if not all([user, password, host, dbname]):
        return None
    # Enforce port 5432 (normalize if someone set 6543 etc.)
    if port != "5432":
        port = "5432"
    return f"postgresql+psycopg2://{user}:{password}@{host}:{port}/{dbname}?sslmode=require"


def _append_sslmode_require(url: str) -> str:
    """
    Ensure sslmode=require is present in the connection string for psycopg2 URLs.
    If a query string already exists, append with &; otherwise, add ?sslmode=require.
    """
    # Apply for postgresql or postgresql+psycopg2 schemes
    if not (url.startswith("postgresql://") or url.startswith("postgresql+psycopg2://")):
        return url
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


def _ensure_port_5432(url: str) -> str:
    """
    Ensure the URL uses port 5432 explicitly. If a different port is present (e.g., 6543), it will be replaced with 5432.
    If no port is present, 5432 will be added.
    """
    try:
        if "://" not in url:
            return url
        scheme, rest = url.split("://", 1)
        creds, hostpart = (rest.split("@", 1) if "@" in rest else ("", rest))
        # Separate query
        query = ""
        if "?" in hostpart:
            host_db, query = hostpart.split("?", 1)
        else:
            host_db = hostpart
        # host_db format: host[:port]/db...
        if "/" in host_db:
            host_port, dbpath = host_db.split("/", 1)
        else:
            host_port, dbpath = host_db, ""
        # Extract host and port
        if ":" in host_port:
            host, _port = host_port.rsplit(":", 1)
            port = "5432"
        else:
            host = host_port
            port = "5432"
        new_host_port = f"{host}:{port}" if host else f":{port}"
        new_host_db = f"{new_host_port}/{dbpath}" if dbpath else new_host_port
        rebuilt = f"{scheme}://"
        if creds:
            rebuilt += f"{creds}@"
        rebuilt += new_host_db
        if query:
            rebuilt += f"?{query}"
        return rebuilt
    except Exception:
        return url


def _apply_ipv4_host_override(url: str) -> str:
    """
    If SUPABASE_DB_HOST_IPV4 is set, override the host portion of the URL with that value.
    This is a best-effort approach to prefer IPv4 without implementing a custom resolver.
    """
    ipv4 = (os.getenv("SUPABASE_DB_HOST_IPV4") or "").strip()
    if not ipv4:
        return url
    try:
        if "://" not in url:
            return url
        scheme, rest = url.split("://", 1)
        creds, hostpart = (rest.split("@", 1) if "@" in rest else ("", rest))
        query = ""
        if "?" in hostpart:
            host_db, query = hostpart.split("?", 1)
        else:
            host_db = hostpart
        if "/" in host_db:
            host_port, dbpath = host_db.split("/", 1)
        else:
            host_port, dbpath = host_db, ""
        # Extract current port (if present)
        if ":" in host_port:
            _, port = host_port.rsplit(":", 1)
        else:
            port = "5432"
        new_host_port = f"{ipv4}:{port}"
        new_host_db = f"{new_host_port}/{dbpath}" if dbpath else new_host_port
        rebuilt = f"{scheme}://"
        if creds:
            rebuilt += f"{creds}@"
        rebuilt += new_host_db
        if query:
            rebuilt += f"?{query}"
        return rebuilt
    except Exception:
        return url


def _get_db_url() -> str:
    """
    Resolve database URL from environment variables.
    Priority:
      1) SUPABASE_DB_URL (preferred)
      2) DATABASE_URL (deprecated)
      3) SUPABASE_DB_CONNECTION_STRING (legacy)
      4) Discrete vars: user/password/host/port/dbname (compose)
    Normalization:
      - Enforce psycopg2 driver
      - Enforce explicit port 5432 (replace any other port)
      - Append sslmode=require if missing
      - Apply IPv4 host override via SUPABASE_DB_HOST_IPV4 if provided
    Raises ValueError if missing to make failures explicit at first DB access (not import).
    """
    settings = get_settings()
    primary = (getattr(settings, "SUPABASE_DB_URL", None) or "").strip()
    if primary:
        url = _ensure_psycopg2_scheme(primary)
        url = _ensure_port_5432(url)
        url = _append_sslmode_require(url)
        url = _apply_ipv4_host_override(url)
        return url

    url2 = (settings.DATABASE_URL or "").strip()
    if url2:
        url2 = _ensure_psycopg2_scheme(url2)
        url2 = _ensure_port_5432(url2)
        url2 = _append_sslmode_require(url2)
        url2 = _apply_ipv4_host_override(url2)
        return url2

    legacy = (settings.SUPABASE_DB_CONNECTION_STRING or "").strip()
    if legacy:
        legacy = _ensure_psycopg2_scheme(legacy)
        legacy = _ensure_port_5432(legacy)
        legacy = _append_sslmode_require(legacy)
        legacy = _apply_ipv4_host_override(legacy)
        return legacy

    # Fallback to discrete environment variables
    composed = _build_url_from_discrete_env()
    if composed:
        composed = _apply_ipv4_host_override(_ensure_port_5432(composed))
        return composed

    raise ValueError(
        "Database configuration not found. Provide one of: "
        "SUPABASE_DB_URL (preferred), DATABASE_URL (deprecated), SUPABASE_DB_CONNECTION_STRING (legacy), "
        "or discrete env vars (user, password, host, port, dbname)."
    )


def _effective_db_params(url: str) -> Dict[str, Any]:
    """
    Parse and return effective DB connection params for logging without password.
    Returns:
        {
          "url_redacted": "...",
          "driver": "psycopg2" | "unknown",
          "sslmode_present": bool,
          "host": "<host or None>",
          "port": "<port or None>",
          "database": "<dbname or None>"
        }
    """
    # Naive parse sufficient for logging purposes without new deps:
    redacted = url
    host = None
    port = None
    database = None
    if "://" in url:
        scheme, rest = url.split("://", 1)
        # Split credentials (optional) from host/db section
        if "@" in rest:
            creds, hostpart = rest.split("@", 1)
            # Redact password if present in creds
            if ":" in creds:
                user = creds.split(":", 1)[0]
                redacted = f"{scheme}://{user}:****@{hostpart}"
            else:
                redacted = f"{scheme}://****@{hostpart}"
        else:
            hostpart = rest
            redacted = f"{scheme}://{hostpart}"
        # hostpart format: host[:port]/database[?query]
        host_db = hostpart
        # Strip query string
        if "?" in host_db:
            host_db, _ = host_db.split("?", 1)
        # Split host[:port] and path (/db)
        if "/" in host_db:
            host_port, dbpath = host_db.split("/", 1)
            database = dbpath or None
        else:
            host_port = host_db
        # Extract host and optional port
        if ":" in host_port:
            host, port = host_port.rsplit(":", 1)
        else:
            host = host_port or None
            port = "5432" if host else None
    return {
        "url_redacted": redacted,
        "driver": "psycopg2" if "psycopg2" in url else "unknown",
        "sslmode_present": ("sslmode=" in url),
        "host": host,
        "port": port,
        "database": database,
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
        extra={
            "echo": bool(settings.DB_ECHO),
            "pool": ("NullPool" if use_null_pool else "Default"),
            **eff,
        },
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
