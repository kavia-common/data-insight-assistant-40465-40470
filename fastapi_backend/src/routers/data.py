from typing import Any, Dict, List, Optional, Tuple

from fastapi import APIRouter, HTTPException, Query
from fastapi.encoders import jsonable_encoder
from pymongo import ASCENDING, DESCENDING
from pymongo.errors import PyMongoError

from ..db.mongo import get_collection
from ..models.schemas import (
    DataItemIn,
    DataItemOut,
    DataItemsPage,
    PaginationMeta,
    PyObjectId,
    serialize_object_id,
)

router = APIRouter(prefix="/data", tags=["Data"])


def _get_coll_or_503():
    """
    Internal helper to get default collection or raise 503.
    """
    coll = get_collection()
    if coll is None:
        raise HTTPException(status_code=503, detail="Database not configured or unavailable.")
    return coll


def _build_projection(fields: Optional[List[str]]) -> Optional[Dict[str, int]]:
    """
    Build a MongoDB projection dict from a list of field names.
    Always includes '_id' unless explicitly excluded.
    """
    if not fields:
        return None
    projection: Dict[str, int] = {f: 1 for f in fields if isinstance(f, str) and f.strip()}
    # Ensure _id remains unless explicitly excluded
    if "_id" not in projection:
        projection["_id"] = 1
    return projection


def _build_sort(sort_by: Optional[str], sort_dir: Optional[str]) -> Optional[List[Tuple[str, int]]]:
    """
    Build MongoDB sort specification.
    """
    if not sort_by:
        return None
    direction = ASCENDING if (sort_dir or "asc").lower() != "desc" else DESCENDING
    return [(sort_by, direction)]


def _normalize_filter(raw_filter: Optional[Dict[str, Any]]) -> Dict[str, Any]:
    """
    Light normalization of filter to handle id fields:
    - if filter contains id or _id with a string value that looks like an ObjectId,
      convert to proper ObjectId.
    """
    f: Dict[str, Any] = dict(raw_filter or {})
    # Normalize id aliases
    for key in ["id", "_id"]:
        if key in f and isinstance(f[key], str):
            try:
                f["_id"] = PyObjectId.validate(f[key])
                if key != "_id":
                    del f[key]
            except Exception:
                # leave as is; query will likely return empty if invalid
                pass
    return f


# PUBLIC_INTERFACE
@router.get(
    "",
    response_model=DataItemsPage,
    summary="List data items",
    description="Returns a paginated list of data items with optional filtering, projection, and sorting.",
    responses={
        200: {"description": "List of data items returned successfully."},
        503: {"description": "Database not available."},
    },
)
async def list_data(
    filter: Optional[str] = Query(
        default=None,
        description="JSON string for MongoDB-like filter. Example: {\"data.country\": \"US\"}",
    ),
    fields: Optional[str] = Query(
        default=None,
        description="Comma-separated fields to include in the response. Example: data.name,data.age",
    ),
    sort_by: Optional[str] = Query(default=None, description="Field to sort by."),
    sort_dir: Optional[str] = Query(default="asc", pattern="^(asc|desc)$", description="Sort direction."),
    limit: int = Query(default=50, ge=1, le=1000, description="Max items to return."),
    offset: int = Query(default=0, ge=0, description="Number of items to skip."),
) -> DataItemsPage:
    """
    List data items with pagination, filtering, and sorting.

    Parameters:
    - filter: JSON string representing a MongoDB filter document.
    - fields: Comma-separated list of fields to include.
    - sort_by: Field to sort.
    - sort_dir: asc or desc.
    - limit: Page size.
    - offset: Skip offset.

    Returns:
    - Paginated data items with metadata.
    """
    import json

    coll = _get_coll_or_503()

    # Parse filter JSON if provided
    parsed_filter: Optional[Dict[str, Any]] = None
    if filter:
        try:
            parsed_filter = json.loads(filter)
            if not isinstance(parsed_filter, dict):
                raise ValueError("Filter must be a JSON object.")
        except Exception:
            raise HTTPException(status_code=400, detail="Invalid filter JSON.")

    normalized_filter = _normalize_filter(parsed_filter)

    # Build projection and sort
    projection = _build_projection(fields.split(",") if fields else None)
    sort_spec = _build_sort(sort_by, sort_dir)

    try:
        total = await coll.count_documents(normalized_filter)
        cursor = coll.find(normalized_filter, projection=projection)
        if sort_spec:
            cursor = cursor.sort(sort_spec)
        cursor = cursor.skip(offset).limit(limit)
        docs = await cursor.to_list(length=limit)

        # Ensure ObjectId serialization for response
        for d in docs:
            if "_id" in d:
                d["_id"] = serialize_object_id(d["_id"])

        meta = PaginationMeta(total=total, limit=limit, offset=offset)
        # Since our response model is DataItemOut, map any documents that don't have 'data'
        # We will wrap non-conforming documents into {'data': <doc_without_id_and_data>}
        normalized_docs: List[Dict[str, Any]] = []
        for d in docs:
            # If document already follows { _id, data: {...} } use as-is
            if isinstance(d.get("data"), dict):
                normalized_docs.append(d)
                continue
            # Otherwise wrap remaining fields into data
            data_payload = {k: v for k, v in d.items() if k not in ("_id", "data")}
            normalized_docs.append({"_id": d.get("_id"), "data": data_payload})

        return DataItemsPage(items=[DataItemOut(**doc) for doc in normalized_docs], meta=meta)
    except PyMongoError as exc:
        raise HTTPException(status_code=500, detail=f"Database error: {exc}") from exc


# PUBLIC_INTERFACE
@router.get(
    "/{item_id}",
    response_model=DataItemOut,
    summary="Get data item by id",
    description="Retrieve a single data item by its MongoDB ObjectId.",
    responses={
        200: {"description": "Item found."},
        404: {"description": "Item not found."},
        400: {"description": "Invalid item id."},
        503: {"description": "Database not available."},
    },
)
async def get_data_item(item_id: str) -> DataItemOut:
    """
    Get a single data item by its id.
    """
    coll = _get_coll_or_503()
    try:
        oid = PyObjectId.validate(item_id)
    except Exception:
        raise HTTPException(status_code=400, detail="Invalid ObjectId.")

    try:
        doc = await coll.find_one({"_id": oid})
        if not doc:
            raise HTTPException(status_code=404, detail="Item not found.")
        # ensure serialization
        doc["_id"] = serialize_object_id(doc["_id"])
        if not isinstance(doc.get("data"), dict):
            data_payload = {k: v for k, v in doc.items() if k not in ("_id", "data")}
            doc = {"_id": doc.get("_id"), "data": data_payload}
        return DataItemOut(**doc)
    except PyMongoError as exc:
        raise HTTPException(status_code=500, detail=f"Database error: {exc}") from exc


# PUBLIC_INTERFACE
@router.post(
    "",
    response_model=DataItemOut,
    status_code=201,
    summary="Create data item",
    description="Create a new data item. Payload is stored under 'data' field.",
    responses={
        201: {"description": "Item created."},
        400: {"description": "Invalid payload."},
        503: {"description": "Database not available."},
    },
)
async def create_data_item(payload: DataItemIn) -> DataItemOut:
    """
    Create a new data item; server stores it as { data: <payload.data> }.
    """
    coll = _get_coll_or_503()
    try:
        doc: Dict[str, Any] = {"data": jsonable_encoder(payload.data)}
        result = await coll.insert_one(doc)
        inserted_id = serialize_object_id(result.inserted_id)
        doc["_id"] = inserted_id
        return DataItemOut(**doc)
    except PyMongoError as exc:
        raise HTTPException(status_code=500, detail=f"Database error: {exc}") from exc


# PUBLIC_INTERFACE
@router.put(
    "/{item_id}",
    response_model=DataItemOut,
    summary="Update data item",
    description="Replace the 'data' content of a data item.",
    responses={
        200: {"description": "Item updated."},
        404: {"description": "Item not found."},
        400: {"description": "Invalid item id or payload."},
        503: {"description": "Database not available."},
    },
)
async def update_data_item(item_id: str, payload: DataItemIn) -> DataItemOut:
    """
    Update the 'data' field of an item, returning the updated document.
    """
    coll = _get_coll_or_503()
    try:
        oid = PyObjectId.validate(item_id)
    except Exception:
        raise HTTPException(status_code=400, detail="Invalid ObjectId.")

    try:
        update_doc = {"$set": {"data": jsonable_encoder(payload.data)}}
        result = await coll.find_one_and_update({"_id": oid}, update_doc, return_document=True)
        # Motor's find_one_and_update with return_document=True requires ReturnDocument import in pymongo,
        # but Motor accepts True as ReturnDocument.AFTER in recent versions. If None, fetch explicitly.
        if result is None:
            # fetch explicitly after update to ensure compatibility
            result = await coll.find_one({"_id": oid})
        if not result:
            raise HTTPException(status_code=404, detail="Item not found.")
        result["_id"] = serialize_object_id(result["_id"])
        if not isinstance(result.get("data"), dict):
            data_payload = {k: v for k, v in result.items() if k not in ("_id", "data")}
            result = {"_id": result.get("_id"), "data": data_payload}
        return DataItemOut(**result)
    except PyMongoError as exc:
        raise HTTPException(status_code=500, detail=f"Database error: {exc}") from exc


# PUBLIC_INTERFACE
@router.delete(
    "/{item_id}",
    status_code=204,
    summary="Delete data item",
    description="Delete a data item by its id.",
    responses={
        204: {"description": "Item deleted."},
        404: {"description": "Item not found."},
        400: {"description": "Invalid item id."},
        503: {"description": "Database not available."},
    },
)
async def delete_data_item(item_id: str) -> None:
    """
    Delete a data item by id. Returns 204 No Content on success.
    """
    coll = _get_coll_or_503()
    try:
        oid = PyObjectId.validate(item_id)
    except Exception:
        raise HTTPException(status_code=400, detail="Invalid ObjectId.")
    try:
        result = await coll.delete_one({"_id": oid})
        if result.deleted_count == 0:
            raise HTTPException(status_code=404, detail="Item not found.")
        return None
    except PyMongoError as exc:
        raise HTTPException(status_code=500, detail=f"Database error: {exc}") from exc
