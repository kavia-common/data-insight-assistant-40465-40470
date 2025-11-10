from fastapi import APIRouter, HTTPException
from pydantic import BaseModel, Field

from ..core.logger import get_logger

logger = get_logger(__name__)
router = APIRouter(prefix="/db", tags=["Health"])


# PUBLIC_INTERFACE
class DBHealthResponse(BaseModel):
    """Health response schema for direct DB connectivity check."""
    status: str = Field(..., description="Health status message, e.g., 'ok'")


# PUBLIC_INTERFACE
@router.get(
    "/health",
    response_model=DBHealthResponse,
    summary="Database connectivity (direct)",
    description=(
        "Runs a simple SELECT 1 via the SQLAlchemy engine to confirm direct DB connectivity.\n\n"
        "Returns 200 with {'status':'ok'} on success or 503 with an error detail. "
        "Keeps sslmode=require and port 5432 normalization. Prefer IPv4 when SUPABASE_DB_HOST_IPV4 is set or "
        "when IPv6 resolution fails."
    ),
    responses={
        200: {"description": "Database reachable"},
        503: {"description": "Database unavailable"},
    },
)
def db_health() -> DBHealthResponse:
    """
    Attempt a trivial SELECT 1 using the project's lazy SQLAlchemy engine to verify DB reachability.

    Returns:
        DBHealthResponse with status 'ok' on success, otherwise raises HTTP 503 with an error detail string.
    """
    try:
        from sqlalchemy import text  # type: ignore
        from ..db.sqlalchemy import get_engine, get_effective_db_params  # type: ignore
    except Exception as exc:
        raise HTTPException(status_code=503, detail=f"database_unavailable: imports_failed: {exc}")

    try:
        engine = get_engine()
        with engine.connect() as conn:
            _ = conn.execute(text("SELECT 1"))
        eff = get_effective_db_params()
        logger.info(
            "DB /db/health connectivity OK",
            extra={
                "host": eff.get("host"),
                "port": eff.get("port"),
                "driver": eff.get("driver"),
                "sslmode_present": eff.get("sslmode_present"),
            },
        )
        return DBHealthResponse(status="ok")
    except Exception as exc:
        eff = {}
        try:
            from ..db.sqlalchemy import get_effective_db_params  # type: ignore
            eff = get_effective_db_params() or {}
        except Exception:
            eff = {"url_redacted": "<unknown>"}
        logger.error(
            "DB /db/health connectivity failed",
            exc_info=exc,
            extra={"effective_url": eff.get("url_redacted")},
        )
        raise HTTPException(
            status_code=503,
            detail=f"database_unavailable: {str(exc)} | effective={eff.get('url_redacted')}",
        )
