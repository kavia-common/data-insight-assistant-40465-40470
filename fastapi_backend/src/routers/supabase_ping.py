from typing import Any, Dict, Optional
import sys  # used for defensive check against unintended DB imports

from fastapi import APIRouter, HTTPException, Query
from pydantic import BaseModel, Field

from ..core.config import get_settings
from ..core.logger import get_logger
from ..services.supabase_client import get_supabase_client, is_supabase_enabled

logger = get_logger(__name__)
router = APIRouter(prefix="/supabase", tags=["Supabase"])

# Defensive runtime check: ensure no DB modules were imported on this code path.
# This avoids accidental psycopg2 initializations due to side-effect imports elsewhere.
if any(m for m in sys.modules.keys() if m.startswith("src.db.sqlalchemy")):
    # Not raising at import-time of the whole app; only this router will complain on usage.
    logger.warning("DB module detected in sys.modules within supabase path; check imports to avoid DB side effects.")


# PUBLIC_INTERFACE
class SupabasePingResponse(BaseModel):
    """Response schema for Supabase ping connectivity check."""
    ok: bool = Field(..., description="True if the query executed successfully")
    table: Optional[str] = Field(None, description="Table used for the ping")
    count: Optional[int] = Field(None, description="Number of rows returned (0 or 1)")
    error: Optional[str] = Field(None, description="Error message if any")
    meta: Dict[str, Any] = Field(default_factory=dict, description="Additional metadata")


def _validate_enabled_or_404() -> None:
    """Raise 404 if Supabase integration is disabled or not fully configured."""
    settings = get_settings()
    if not is_supabase_enabled():
        # 404 to avoid exposing feature when not enabled
        raise HTTPException(
            status_code=404,
            detail="Supabase integration is disabled. Set ENABLE_SUPABASE=true and configure credentials.",
        )
    if not settings.SUPABASE_URL or not settings.SUPABASE_ANON_KEY:
        # 503 since the feature is enabled but configuration missing
        raise HTTPException(
            status_code=503,
            detail="Supabase is enabled but not configured. Provide SUPABASE_URL and SUPABASE_ANON_KEY.",
        )


# PUBLIC_INTERFACE
@router.get(
    "/ping",
    response_model=SupabasePingResponse,
    summary="Ping Supabase via HTTP client",
    description="""
Run a lightweight select limit(1) using the Supabase Python client to verify HTTP-based connectivity.

Notes:
- This endpoint never attempts a direct Postgres connection (no psycopg2/SQLAlchemy).
- Table name can be provided via ?table=... or via SUPABASE_TEST_TABLE in the environment (if query param omitted).
""",
    responses={
        200: {"description": "Ping executed successfully or with handled error details."},
        404: {"description": "Supabase not enabled."},
        503: {"description": "Supabase not configured or client unavailable."},
        500: {"description": "Unexpected error during ping."},
    },
)
async def supabase_ping(
    table: Optional[str] = Query(
        default=None,
        description="Table to query for select limit(1). If omitted, uses env SUPABASE_TEST_TABLE.",
    )
) -> SupabasePingResponse:
    """
    Perform a minimal Supabase HTTP call to confirm availability.

    Parameters:
        table: Optional table name to use. Falls back to env SUPABASE_TEST_TABLE if missing.

    Returns:
        SupabasePingResponse with ok status, count (0 or 1), and error (if any).
    """
    _validate_enabled_or_404()

    settings = get_settings()
    target_table = (table or "").strip() or (getattr(settings, "SUPABASE_TEST_TABLE", None) or "").strip()
    if not target_table:
        # Accept empty table as error but not a crash
        raise HTTPException(status_code=400, detail="Missing table. Provide ?table=... or set SUPABASE_TEST_TABLE.")

    client = get_supabase_client()
    if client is None:
        raise HTTPException(status_code=503, detail="Supabase client unavailable. Check configuration and logs.")

    try:
        # Lightweight: select * limit 1; avoid count to minimize overhead
        q = client.table(target_table).select("*").limit(1)
        resp = q.execute()
        data = getattr(resp, "data", None)
        error = getattr(resp, "error", None)

        if error:
            logger.error("Supabase ping error", extra={"error": str(error), "table": target_table})
            return SupabasePingResponse(ok=False, table=target_table, count=0, error=str(error), meta={})

        rows = data or []
        return SupabasePingResponse(ok=True, table=target_table, count=min(len(rows), 1), error=None, meta={})
    except HTTPException:
        raise
    except Exception as exc:
        logger.error("Unexpected Supabase ping error", exc_info=exc, extra={"table": target_table})
        # Hide internal details in error; return handled payload
        return SupabasePingResponse(ok=False, table=target_table, count=0, error="Unexpected Supabase error", meta={})
