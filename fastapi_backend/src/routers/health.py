from typing import Any, Dict
import os

from fastapi import APIRouter, HTTPException

from ..core.config import get_settings
from ..core.logger import get_logger
from ..models.schemas import HealthResponse

# IMPORTANT GUARD: These handlers must never touch DB modules.
NO_DB_MODE = True

router = APIRouter(prefix="/health", tags=["Health"])

_logger = get_logger(__name__)


def _effective_env_presence() -> Dict[str, Any]:
    """
    Return presence (non-empty) of critical env settings and discrete vars
    without revealing secrets. This validates that .env loading via BaseSettings worked.
    """
    s = get_settings()
    presence = {
        "DATABASE_URL_set": bool((s.DATABASE_URL or "").strip()),
        "SUPABASE_DB_CONNECTION_STRING_set": bool((s.SUPABASE_DB_CONNECTION_STRING or "").strip()),
        # Discrete vars presence (do not import db/sqlalchemy here)
        "discrete": {
            "user_set": bool((os.getenv("user") or "").strip()),
            "password_set": bool((os.getenv("password") or "").strip()),
            "host_set": bool((os.getenv("host") or "").strip()),
            "port_set": bool((os.getenv("port") or "").strip()),
            "dbname_set": bool((os.getenv("dbname") or "").strip()),
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
        "No database connections are attempted here."
    ),
    responses={
        200: {"description": "Service is healthy"},
    },
)
def get_health() -> HealthResponse:
    """
    Root health indicator used for liveness. Always returns 200 with {'status':'ok'}.
    Strictly non-DB: does not import or touch any DB engine/session. Safe when DB is unreachable.
    """
    settings = get_settings()

    # Only log minimal app/process/env presence. No DB queries/imports.
    _logger.info(
        "Health (no-DB) diagnostics",
        extra={
            "env": settings.APP_ENV,
            "env_presence": _effective_env_presence(),
            "no_db_mode": NO_DB_MODE,
        },
    )

    return HealthResponse(status="ok")


# PUBLIC_INTERFACE
@router.get(
    "/healthz",
    response_model=HealthResponse,
    summary="Service health (alias)",
    description="Alias health endpoint commonly used by platforms for liveness checks. Strictly non-DB.",
    responses={200: {"description": "Service is healthy"}},
)
def get_healthz() -> HealthResponse:
    """Alias of /health that returns the same response payload."""
    return get_health()


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
    This route is the only health endpoint that may touch DB.
    """
    # Localized imports to prevent any accidental DB initialization in module scope
    try:
        from sqlalchemy import text  # type: ignore
        from ..db.sqlalchemy import get_engine, get_effective_db_params  # type: ignore
    except Exception as exc:
        # If SQLAlchemy or db layer is unavailable, treat as service misconfiguration
        raise HTTPException(status_code=503, detail=f"database_unavailable: imports_failed: {exc}")

    try:
        engine = get_engine()  # lazy init, may raise if URL missing
        with engine.connect() as conn:
            conn.execute(text("SELECT 1"))
        _logger.info("DB connectivity OK via /health/db")
        return HealthResponse(status="ok")
    except Exception as exc:
        # Return detailed error to aid diagnostics
        try:
            eff = get_effective_db_params()
        except Exception:
            eff = {"url_redacted": "<unknown>"}
        raise HTTPException(
            status_code=503,
            detail=f"database_unavailable: {str(exc)} | effective={eff.get('url_redacted')}",
        )
