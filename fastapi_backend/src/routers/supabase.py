from typing import Any, Dict, List, Literal, Optional, Tuple
import sys  # used for defensive check against unintended DB imports

from fastapi import APIRouter, HTTPException, Query, Body
from pydantic import BaseModel, Field

from ..core.config import get_settings
from ..core.logger import get_logger
from ..services.supabase_client import get_supabase_client, is_supabase_enabled

logger = get_logger(__name__)
router = APIRouter(prefix="/supabase", tags=["Supabase"])

# Defensive runtime check: ensure no DB modules were imported on this code path.
if any(m for m in sys.modules.keys() if m.startswith("src.db.sqlalchemy")):
    logger.warning("DB module detected in sys.modules within supabase router; verify no unintended DB imports.")


# PUBLIC_INTERFACE
class SupabaseFilter(BaseModel):
    """Represents a single filter on a column with an operator and a value."""
    column: str = Field(..., description="Column name to filter on")
    op: Literal["eq", "neq", "lt", "lte", "gt", "gte", "ilike"] = Field(
        ..., description="Comparison operator"
    )
    value: Any = Field(..., description="Value to compare against")


# PUBLIC_INTERFACE
class SupabaseQueryResponse(BaseModel):
    """Response schema for Supabase table queries."""
    items: List[Dict[str, Any]] = Field(default_factory=list, description="Result rows")
    meta: Dict[str, Any] = Field(
        default_factory=dict,
        description="Metadata such as limit/offset/count if available",
    )


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


def _apply_filters(q: Any, filters: Optional[List[SupabaseFilter]]) -> Any:
    """Apply supported filters to a Supabase query object."""
    if not filters:
        return q
    for f in filters:
        col = f.column
        if f.op == "eq":
            q = q.eq(col, f.value)
        elif f.op == "neq":
            q = q.neq(col, f.value)
        elif f.op == "lt":
            q = q.lt(col, f.value)
        elif f.op == "lte":
            q = q.lte(col, f.value)
        elif f.op == "gt":
            q = q.gt(col, f.value)
        elif f.op == "gte":
            q = q.gte(col, f.value)
        elif f.op == "ilike":
            # Expect caller to provide %wildcards% as needed for ilike
            q = q.ilike(col, str(f.value))
        else:
            # Should not happen due to Literal typing; keep safe
            raise HTTPException(status_code=400, detail=f"Unsupported operator: {f.op}")
    return q


def _apply_order(q: Any, order_by: Optional[str], order_dir: Optional[str]) -> Any:
    if not order_by:
        return q
    # Supabase-py uses order(column=..., desc=bool)
    desc = bool((order_dir or "asc").lower() == "desc")
    return q.order(order_by, desc=desc)


def _apply_pagination(q: Any, limit: Optional[int], offset: Optional[int]) -> Tuple[Any, Dict[str, Any]]:
    meta: Dict[str, Any] = {}
    if limit is not None:
        q = q.limit(limit)
        meta["limit"] = limit
    if offset is not None:
        # In supabase-py, range(from, to) is common; however limit/offset is also supported in postgrest.
        # When using limit/offset directly, we keep it simple and rely on server-side support.
        q = q.offset(offset)
        meta["offset"] = offset
    return q, meta


# PUBLIC_INTERFACE
@router.post(
    "/query",
    response_model=SupabaseQueryResponse,
    summary="Query a Supabase table",
    description="""
Query a Supabase table using optional filters, ordering, and pagination.

Usage examples:

- Basic:
  POST /supabase/query
  body: {"table":"customers","limit":10}

- With filters (provide as JSON list in the body):
  filters: [
    {"column":"country","op":"eq","value":"US"},
    {"column":"name","op":"ilike","value":"%ann%"}
  ]

- With ordering and pagination:
  POST /supabase/query
  body: {"table":"orders","order_by":"created_at","order_dir":"desc","limit":20,"offset":0}
""",
    responses={
        200: {"description": "Query executed successfully."},
        400: {"description": "Invalid request or parameters."},
        404: {"description": "Supabase not enabled."},
        503: {"description": "Supabase not configured or unavailable."},
        500: {"description": "Supabase query failed."},
    },
)
async def supabase_query(
    table: str = Query(..., description="Target table name"),
    order_by: Optional[str] = Query(None, description="Column to order by"),
    order_dir: Optional[Literal["asc", "desc"]] = Query("asc", description="Sort direction"),
    limit: Optional[int] = Query(50, ge=1, le=1000, description="Max rows to return"),
    offset: Optional[int] = Query(0, ge=0, description="Number of rows to skip"),
    # For POST, accept filters as JSON body to support complex structures
    filters: Optional[List[SupabaseFilter]] = Body(
        default=None,
        description="Optional list of filters to apply to the table query.",
    ),
) -> SupabaseQueryResponse:
    """
    Execute a read-only Supabase query against a given table.
    Requires ENABLE_SUPABASE=true and credentials configured.

    Returns:
        items: list of rows from Supabase
        meta: includes limit/offset and possibly count if requested in future
    """
    _validate_enabled_or_404()

    client = get_supabase_client()
    if client is None:
        raise HTTPException(status_code=503, detail="Supabase client unavailable. Check configuration and logs.")

    try:
        q = client.table(table).select("*")
        q = _apply_filters(q, filters)
        q = _apply_order(q, order_by, order_dir)
        q, meta = _apply_pagination(q, limit, offset)

        # Execute
        resp = q.execute()
        # supabase-py returns an object with .data and .error
        data = getattr(resp, "data", None)
        error = getattr(resp, "error", None)

        if error:
            logger.error("Supabase query error", extra={"error": str(error), "table": table})
            raise HTTPException(status_code=500, detail=f"Supabase error: {error}")

        rows: List[Dict[str, Any]] = data or []
        return SupabaseQueryResponse(items=rows, meta=meta)
    except HTTPException:
        raise
    except Exception as exc:
        logger.error("Unexpected Supabase error", exc_info=exc, extra={"table": table})
        raise HTTPException(status_code=500, detail="Unexpected Supabase error.")
