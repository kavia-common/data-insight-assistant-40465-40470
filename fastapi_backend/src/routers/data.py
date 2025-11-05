from typing import Any, Dict, List, Optional
import json
from uuid import UUID

from fastapi import APIRouter, HTTPException, Query, Depends
from fastapi.encoders import jsonable_encoder
from sqlalchemy import select, func, text
from sqlalchemy.orm import Session

from ..db.sqlalchemy import get_db
from ..models.schemas import (
    DataItemIn,
    DataItemOut,
    DataItemsPage,
    PaginationMeta,
)
from ..models.sql_models import Item

router = APIRouter(prefix="/data", tags=["Data"])


def _apply_filter(stmt, filter_obj: Optional[Dict[str, Any]]):
    """Apply simple equality filters for data.<field> keys on JSONB."""
    if not filter_obj:
        return stmt
    # Support nested fields like "data.country": "US"
    for k, v in filter_obj.items():
        if k.startswith("data."):
            path = k.split(".", 1)[1]
            # Use ->> for text extraction; cast as needed by PG
            stmt = stmt.where(
                text(
                    f"(items.data ->> :f_{path.replace('.', '_')}) = :v_{path.replace('.', '_')}"
                )
            ).params(**{f"f_{path.replace('.', '_')}": path, f"v_{path.replace('.', '_')}": str(v)})
        elif k == "id":
            try:
                _ = UUID(str(v))
                stmt = stmt.where(Item.id == UUID(str(v)))
            except Exception:
                # invalid id; ensure no results
                stmt = stmt.where(text("1=0"))
        # Additional operators ($gt, etc.) could be added if needed
    return stmt


def _apply_sort(stmt, sort_by: Optional[str], sort_dir: Optional[str]):
    if not sort_by:
        return stmt
    direction_desc = (sort_dir or "asc").lower() == "desc"
    if sort_by == "created_at":
        return stmt.order_by(Item.created_at.desc() if direction_desc else Item.created_at.asc())
    if sort_by == "updated_at":
        return stmt.order_by(Item.updated_at.desc() if direction_desc else Item.updated_at.asc())
    if sort_by.startswith("data."):
        path = sort_by.split(".", 1)[1]
        order_expr = text(
            f"(items.data ->> :s_{path.replace('.', '_')}) {'DESC' if direction_desc else 'ASC'}"
        )
        return stmt.order_by(order_expr).params(**{f"s_{path.replace('.', '_')}": path})
    # default to id
    return stmt.order_by(Item.id.desc() if direction_desc else Item.id.asc())


def _project_item(it: Item, fields: Optional[str]) -> Dict[str, Any]:
    # Respect simple projection for data.* fields
    data_payload = it.data or {}
    if fields:
        wanted = [f.strip() for f in fields.split(",") if f.strip()]
        # Keep only requested data.* keys
        selected: Dict[str, Any] = {}
        for f in wanted:
            if f.startswith("data."):
                key = f.split(".", 1)[1]
                if key in data_payload:
                    selected[key] = data_payload.get(key)
        data_payload = selected if selected else data_payload
    return {"_id": str(it.id), "data": data_payload}


# PUBLIC_INTERFACE


@router.get(
    "",
    response_model=DataItemsPage,
    summary="List data items",
    description="Returns a paginated list of data items with optional filtering, projection, and sorting.",
    responses={
        200: {"description": "List of data items returned successfully."},
    },
)
def list_data(
    filter: Optional[str] = Query(
        default=None,
        description='JSON string filter on data.* keys. Example: {"data.country":"US"}',
    ),
    fields: Optional[str] = Query(
        default=None,
        description="Comma-separated fields to include (data.*). Example: data.name,data.age",
    ),
    sort_by: Optional[str] = Query(default=None, description="Field to sort by (created_at, updated_at, or data.*)."),
    sort_dir: Optional[str] = Query(default="asc", pattern="^(asc|desc)$", description="Sort direction."),
    limit: int = Query(default=50, ge=1, le=1000, description="Max items to return."),
    offset: int = Query(default=0, ge=0, description="Number of items to skip."),
    db: Session = Depends(get_db),
) -> DataItemsPage:
    try:
        parsed_filter: Optional[Dict[str, Any]] = None
        if filter:
            parsed_filter = json.loads(filter)
            if not isinstance(parsed_filter, dict):
                raise HTTPException(status_code=400, detail="Filter must be a JSON object.")

        # Count
        count_stmt = select(func.count(Item.id))
        count_stmt = _apply_filter(count_stmt, parsed_filter)
        total = db.execute(count_stmt).scalar_one()

        # Query
        stmt = select(Item)
        stmt = _apply_filter(stmt, parsed_filter)
        stmt = _apply_sort(stmt, sort_by, sort_dir)
        stmt = stmt.offset(offset).limit(limit)
        rows = db.execute(stmt).scalars().all()

        items = [_project_item(it, fields) for it in rows]
        meta = PaginationMeta(total=int(total), limit=limit, offset=offset)
        return DataItemsPage(items=[DataItemOut(**doc) for doc in items], meta=meta)
    except HTTPException:
        raise
    except Exception as exc:
        raise HTTPException(status_code=500, detail=f"Database error: {exc}")


# PUBLIC_INTERFACE


@router.get(
    "/{item_id}",
    response_model=DataItemOut,
    summary="Get data item by id",
    description="Retrieve a single data item by its UUID.",
)
def get_data_item(item_id: str, db: Session = Depends(get_db)) -> DataItemOut:
    try:
        uid = UUID(item_id)
    except Exception:
        raise HTTPException(status_code=400, detail="Invalid id.")
    try:
        it = db.get(Item, uid)
        if not it:
            raise HTTPException(status_code=404, detail="Item not found.")
        doc = _project_item(it, None)
        return DataItemOut(**doc)
    except HTTPException:
        raise
    except Exception as exc:
        raise HTTPException(status_code=500, detail=f"Database error: {exc}")


# PUBLIC_INTERFACE


@router.post(
    "",
    response_model=DataItemOut,
    status_code=201,
    summary="Create data item",
    description="Create a new data item. Payload is stored under 'data' field.",
)
def create_data_item(payload: DataItemIn, db: Session = Depends(get_db)) -> DataItemOut:
    try:
        it = Item(data=jsonable_encoder(payload.data))
        db.add(it)
        db.commit()
        db.refresh(it)
        doc = _project_item(it, None)
        return DataItemOut(**doc)
    except Exception as exc:
        db.rollback()
        raise HTTPException(status_code=500, detail=f"Database error: {exc}")


# PUBLIC_INTERFACE


@router.put(
    "/{item_id}",
    response_model=DataItemOut,
    summary="Update data item",
    description="Replace the 'data' content of a data item.",
)
def update_data_item(item_id: str, payload: DataItemIn, db: Session = Depends(get_db)) -> DataItemOut:
    try:
        uid = UUID(item_id)
    except Exception:
        raise HTTPException(status_code=400, detail="Invalid id.")
    try:
        it = db.get(Item, uid)
        if not it:
            raise HTTPException(status_code=404, detail="Item not found.")
        it.data = jsonable_encoder(payload.data)
        db.add(it)
        db.commit()
        db.refresh(it)
        return DataItemOut(**_project_item(it, None))
    except HTTPException:
        raise
    except Exception as exc:
        db.rollback()
        raise HTTPException(status_code=500, detail=f"Database error: {exc}")


# PUBLIC_INTERFACE


@router.delete(
    "/{item_id}",
    status_code=204,
    summary="Delete data item",
    description="Delete a data item by its id.",
)
def delete_data_item(item_id: str, db: Session = Depends(get_db)) -> None:
    try:
        uid = UUID(item_id)
    except Exception:
        raise HTTPException(status_code=400, detail="Invalid id.")
    try:
        it = db.get(Item, uid)
        if not it:
            raise HTTPException(status_code=404, detail="Item not found.")
        db.delete(it)
        db.commit()
        return None
    except HTTPException:
        raise
    except Exception as exc:
        db.rollback()
        raise HTTPException(status_code=500, detail=f"Database error: {exc}")
