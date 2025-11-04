from typing import Any, Dict, List, Optional, Tuple

from fastapi import APIRouter, HTTPException, Depends
from sqlalchemy import select, func, text
from sqlalchemy.orm import Session

from ..core.config import get_settings
from ..db.sqlalchemy import get_db
from ..models.schemas import NLQRequest, NLQResponse, PaginationMeta
from ..services.nlq_service import parse_nlq_to_query
from ..models.sql_models import Item

router = APIRouter(prefix="/nlq", tags=["NLQ"])


def _coalesce_limit_offset(req: NLQRequest, parsed: Dict[str, Any]) -> Tuple[int, int]:
    default_limit = 50
    default_offset = 0
    limit = parsed.get("limit")
    offset = parsed.get("offset")
    if req.params:
        if req.params.limit is not None:
            limit = req.params.limit
        if req.params.offset is not None:
            offset = req.params.offset
    return int(limit or default_limit), int(offset or default_offset)


def _apply_filter(stmt, f: Dict[str, Any]):
    # Very basic mapping: support equality on data.* keys
    for k, v in (f or {}).items():
        if k.startswith("data."):
            path = k.split(".", 1)[1]
            stmt = stmt.where(
                text(f"(items.data ->> :f_{path.replace('.', '_')}) = :v_{path.replace('.', '_')}")
            ).params(**{f"f_{path.replace('.', '_')}": path, f"v_{path.replace('.', '_')}": str(v)})
    return stmt


def _apply_sort(stmt, sort_spec: Optional[List[List[Any]]], req: NLQRequest):
    # sort_spec like [["field", 1]]
    field = None
    direction_desc = False
    if sort_spec:
        field = sort_spec[0][0]
        direction_desc = int(sort_spec[0][1]) < 0
    if req.params and req.params.sort_by:
        field = req.params.sort_by
        direction_desc = (req.params.sort_dir or "asc").lower() == "desc"

    if not field:
        return stmt
    if field == "created_at":
        return stmt.order_by(Item.created_at.desc() if direction_desc else Item.created_at.asc())
    if field == "updated_at":
        return stmt.order_by(Item.updated_at.desc() if direction_desc else Item.updated_at.asc())
    if field.startswith("data."):
        path = field.split(".", 1)[1]
        return stmt.order_by(
            text(f"(items.data ->> :s_{path.replace('.', '_')}) {'DESC' if direction_desc else 'ASC'}")
        ).params(**{f"s_{path.replace('.', '_')}": path})
    return stmt


# PUBLIC_INTERFACE
@router.post(
    "/query",
    response_model=NLQResponse,
    summary="Execute Natural Language Query",
    description="Parses the provided natural language query into filters and returns results from SQL items.",
    responses={
        200: {"description": "NLQ executed successfully."},
        400: {"description": "Invalid request."},
        500: {"description": "Database error."},
    },
)
def execute_nlq(req: NLQRequest, db: Session = Depends(get_db)) -> NLQResponse:
    settings = get_settings()
    if not settings.ENABLE_NLQ:
        raise HTTPException(status_code=404, detail="NLQ is disabled.")

    if not req or not req.query or not req.query.strip():
        raise HTTPException(status_code=400, detail="Query must be a non-empty string.")

    parsed = parse_nlq_to_query(req.query)
    filter_doc: Dict[str, Any] = parsed.get("filter", {})

    limit, offset = _coalesce_limit_offset(req, parsed)
    try:
        # Count
        count_stmt = select(func.count(Item.id))
        count_stmt = _apply_filter(count_stmt, filter_doc)
        total = db.execute(count_stmt).scalar_one()

        # Query items
        stmt = select(Item)
        stmt = _apply_filter(stmt, filter_doc)
        stmt = _apply_sort(stmt, parsed.get("sort"), req)
        stmt = stmt.offset(offset).limit(limit)
        rows = db.execute(stmt).scalars().all()

        items: List[Dict[str, Any]] = [
            {"_id": str(r.id), **({"data": r.data} if isinstance(r.data, dict) else {"data": {}})} for r in rows
        ]
        meta = PaginationMeta(total=int(total), limit=limit, offset=offset)
        return NLQResponse(nlq=req.query, filter=filter_doc, items=items, meta=meta)
    except HTTPException:
        raise
    except Exception as exc:
        raise HTTPException(status_code=500, detail=f"Database error: {exc}")
