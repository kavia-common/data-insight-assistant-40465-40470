from typing import Any, Dict, List, Optional, Tuple

from fastapi import APIRouter, HTTPException
from pymongo.errors import PyMongoError

from ..core.config import get_settings
from ..db.mongo import get_collection
from ..models.schemas import NLQRequest, NLQResponse, PaginationMeta, serialize_object_id
from ..services.nlq_service import parse_nlq_to_query

router = APIRouter(prefix="/nlq", tags=["NLQ"])


def _get_collection_or_503(name: Optional[str]):
    """
    Internal: Get a MongoDB collection by name or the default one, else 503.

    503 is returned only when DB is not configured or cannot be reached.
    """
    coll = get_collection(name)
    if coll is None:
        raise HTTPException(
            status_code=503,
            detail=(
                "Database not configured or unavailable. "
                "Ensure MONGO_URI, MONGO_DB_NAME, and MONGO_COLLECTION are set and MongoDB is reachable."
            ),
        )
    return coll


def _coalesce_limit_offset(req: NLQRequest, parsed: Dict[str, Any]) -> Tuple[int, int]:
    """
    Merge limit/offset between parsed NLQ and explicit request params with defaults.
    """
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


def _coalesce_projection(req: NLQRequest, parsed: Dict[str, Any]) -> Optional[Dict[str, int]]:
    """
    Build projection from request params if provided; else use parsed projection.
    """
    if req.params and req.params.fields:
        projection = {f: 1 for f in req.params.fields}
        if "_id" not in projection:
            projection["_id"] = 1
        return projection
    return parsed.get("projection")


def _coalesce_sort(req: NLQRequest, parsed: Dict[str, Any]) -> Optional[List[Tuple[str, int]]]:
    """
    Compose sort spec as list of (field, direction) where direction 1 asc, -1 desc.
    """
    sort = parsed.get("sort")
    sort_spec = [(f, int(d)) for f, d in sort] if sort else None
    if req.params and req.params.sort_by:
        direction = 1 if (req.params.sort_dir or "asc").lower() != "desc" else -1
        sort_spec = [(req.params.sort_by, direction)]
    return sort_spec


# PUBLIC_INTERFACE
@router.post(
    "/query",
    response_model=NLQResponse,
    summary="Execute Natural Language Query",
    description="Parses the provided natural language query into a MongoDB filter and returns results.",
    responses={
        200: {"description": "NLQ executed successfully."},
        400: {"description": "Invalid request."},
        503: {"description": "Database unavailable."},
        500: {"description": "Database error."},
    },
)
async def execute_nlq(req: NLQRequest) -> NLQResponse:
    """
    Execute an NLQ request and return results with derived filter and pagination.

    Parameters:
    - req: NLQRequest containing the natural language query, optional collection name,
      and optional structured parameters (fields, sorting, pagination).

    Returns:
    - NLQResponse including the original NLQ, derived filter, result items, and pagination metadata.
    """
    settings = get_settings()
    if not settings.ENABLE_NLQ:
        raise HTTPException(status_code=404, detail="NLQ is disabled.")

    if not req or not req.query or not req.query.strip():
        raise HTTPException(status_code=400, detail="Query must be a non-empty string.")

    parsed = parse_nlq_to_query(req.query)
    filter_doc: Dict[str, Any] = parsed.get("filter", {})

    projection = _coalesce_projection(req, parsed)
    sort_spec = _coalesce_sort(req, parsed)
    limit, offset = _coalesce_limit_offset(req, parsed)

    coll = _get_collection_or_503(req.collection)

    try:
        total = await coll.count_documents(filter_doc)
        cursor = coll.find(filter_doc, projection=projection)
        if sort_spec:
            cursor = cursor.sort(sort_spec)
        cursor = cursor.skip(offset).limit(limit)
        docs = await cursor.to_list(length=limit)

        # Serialize ObjectIds and keep items as dictionaries
        normalized: List[Dict[str, Any]] = []
        for d in docs:
            if "_id" in d:
                d["_id"] = serialize_object_id(d["_id"])
            normalized.append(d)

        meta = PaginationMeta(total=total, limit=limit, offset=offset)
        return NLQResponse(nlq=req.query, filter=filter_doc, items=normalized, meta=meta)
    except PyMongoError as exc:
        raise HTTPException(status_code=500, detail=f"Database error: {exc}") from exc
