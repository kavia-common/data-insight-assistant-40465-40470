from typing import Any, Dict

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session
from sqlalchemy import text

from ..core.config import get_settings
from ..core.logger import get_logger
from ..db.sqlalchemy import get_db, get_engine
from ..models.schemas import HealthResponse
from ..services.supabase_client import supabase_health

router = APIRouter(prefix="/health", tags=["Health"])

_logger = get_logger(__name__)


def _db_ping(db: Session) -> Dict[str, Any]:
    """Perform a lightweight DB ping using SELECT 1 (session)."""
    try:
        db.execute(text("SELECT 1"))
        return {"available": True}
    except Exception as exc:
        _logger.error("Database ping failed in /health.", exc_info=exc)
        return {"available": False, "error": str(exc)}


def _effective_env_presence() -> Dict[str, Any]:
    """
    Return presence (non-empty) of critical env settings and discrete vars
    without revealing secrets. This validates that .env loading via BaseSettings worked.
    """
    s = get_settings()
    presence = {
        "DATABASE_URL_set": bool((s.DATABASE_URL or "").strip()),
        "SUPABASE_DB_CONNECTION_STRING_set": bool((s.SUPABASE_DB_CONNECTION_STRING or "").strip()),
        # Discrete vars are read via os.environ in db/sqlalchemy.py, but we also check here:
        "discrete": {
            "user_set": bool((__import__("os").environ.get("user") or "").strip()),
            "password_set": bool((__import__("os").environ.get("password") or "").strip()),
            "host_set": bool((__import__("os").environ.get("host") or "").strip()),
            "port_set": bool((__import__("os").environ.get("port") or "").strip()),
            "dbname_set": bool((__import__("os").environ.get("dbname") or "").strip()),
        },
    }
    return presence


# PUBLIC_INTERFACE
@router.get(
    "",
    response_model=HealthResponse,
    summary="Service health",
    description=(
        "Liveness/health endpoint. Always returns 200 when the app is up. "
        "Executes a lightweight 'SELECT 1' against the database and reports Supabase availability."
    ),
    responses={
        200: {"description": "Service is healthy"},
    },
)
def get_health(db: Session = Depends(get_db)) -> HealthResponse:
    """
    Root health indicator used for liveness. Always returns 200 with {'status':'ok'}.
    Also logs DB and Supabase availability diagnostics.
    """
    settings = get_settings()

    db_status = _db_ping(db)
    sb = supabase_health()

    _logger.info(
        "Health diagnostics",
        extra={
            "env": settings.APP_ENV,
            "db": db_status,
            "supabase": sb,
            "env_presence": _effective_env_presence(),
        },
    )

    return HealthResponse(status="ok")


# PUBLIC_INTERFACE
@router.get(
    "/healthz",
    response_model=HealthResponse,
    summary="Service health (alias)",
    description="Alias health endpoint commonly used by platforms for liveness checks.",
    responses={200: {"description": "Service is healthy"}},
)
def get_healthz(db: Session = Depends(get_db)) -> HealthResponse:
    """Alias of /health that returns the same response payload."""
    return get_health(db)


# PUBLIC_INTERFACE
@router.get(
    "/db",
    response_model=HealthResponse,
    summary="Database connectivity",
    description="Runs a simple SELECT 1 via the SQLAlchemy engine to confirm DB connectivity.",
    responses={200: {"description": "Database reachable"}, 503: {"description": "Database unavailable"}},
)
def health_db() -> HealthResponse:
    """
    Check direct database connectivity via engine.connect().
    Logs effective connection parameters (redacted) and env presence.
    Returns detailed error text on failure to assist diagnostics.
    """
    try:
        engine = get_engine()  # lazy init, may raise if URL missing
        # Attempt a direct SELECT 1
        with engine.connect() as conn:
            conn.execute(text("SELECT 1"))
        _logger.info("DB connectivity OK via /health/db", extra={"env_presence": _effective_env_presence()})
        return HealthResponse(status="ok")
    except Exception as exc:
        # Provide richer diagnostics in logs and return detailed error for troubleshooting
        _logger.error(
            "Database connectivity check failed in /health/db.",
            exc_info=exc,
            extra={
                "env_presence": _effective_env_presence(),
                "note": "Ensure DATABASE_URL or discrete vars are set; psycopg2 driver and sslmode=require enforced.",
            },
        )
        # 503 to signal dependency unavailable, include error string for operator visibility
        raise HTTPException(status_code=503, detail=f"database_unavailable: {str(exc)}")
