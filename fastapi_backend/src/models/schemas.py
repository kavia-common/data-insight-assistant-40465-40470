"""
Pydantic schemas for API requests and responses, including SQL-friendly ID handling,
query parameters for filtering/pagination/sorting, data item models, and NLQ types.
"""

from typing import Any, Dict, List, Literal, Optional, Union

from pydantic import BaseModel, Field, ConfigDict


# ---------------------------------------------------------------------------
# (Removed) MongoDB ObjectId utilities
# ---------------------------------------------------------------------------

def serialize_object_id(oid):
    """Backwards-compat helper; now simply cast to string."""
    if oid is None:
        return None
    return str(oid)


# ---------------------------------------------------------------------------
# Common/Utility Schemas
# ---------------------------------------------------------------------------

# PUBLIC_INTERFACE
class HealthResponse(BaseModel):
    """Basic health response schema."""
    status: str = Field(..., description="Health status message, e.g., 'ok'")


# PUBLIC_INTERFACE
class QueryParams(BaseModel):
    """Standard query parameters for list endpoints.

    - filter: arbitrary MongoDB-like filter object (server-side validated)
    - fields: list of field names to include (projection)
    - sort_by: field to sort on
    - sort_dir: 'asc' or 'desc'
    - limit: page size
    - offset: starting index (skip)
    """
    filter: Optional[Dict[str, Any]] = Field(
        default=None, description="Filter object using MongoDB-like operators."
    )
    fields: Optional[List[str]] = Field(
        default=None, description="Field names to include in the response."
    )
    sort_by: Optional[str] = Field(
        default=None, description="Field name to sort by."
    )
    sort_dir: Optional[Literal["asc", "desc"]] = Field(
        default="asc", description="Sort direction."
    )
    limit: int = Field(default=50, ge=1, le=1000, description="Max items to return.")
    offset: int = Field(default=0, ge=0, description="Number of items to skip.")

    model_config = ConfigDict(extra="ignore")


# PUBLIC_INTERFACE
class PaginationMeta(BaseModel):
    """Metadata for paginated responses."""
    total: int = Field(..., ge=0, description="Total number of matching items.")
    limit: int = Field(..., ge=1, description="Page size used.")
    offset: int = Field(..., ge=0, description="Offset used.")


# ---------------------------------------------------------------------------
# Data Item Schemas
# ---------------------------------------------------------------------------

# PUBLIC_INTERFACE
class DataItemIn(BaseModel):
    """Schema for creating/updating data items."""
    # Use flexible typing for data payload to support diverse datasets
    data: Dict[str, Any] = Field(..., description="Arbitrary item payload.")

    model_config = ConfigDict(
        extra="allow",
        json_schema_extra={
            "example": {"data": {"name": "Alice", "age": 30, "country": "US"}}
        },
    )


# PUBLIC_INTERFACE
class DataItemOut(BaseModel):
    """Schema representing a data item as returned from the API (with id)."""
    # Expose id as string in API schema for compatibility; UUID string for Postgres.
    id: str = Field(..., alias="_id", description="Item identifier (UUID string).")
    data: Dict[str, Any] = Field(..., description="Arbitrary item payload.")

    model_config = ConfigDict(
        populate_by_name=True,
        json_schema_extra={
            "example": {
                "id": "f3b803f2-8c9e-4f5b-9b64-8cd3f1a5b7e1",
                "data": {"name": "Alice", "age": 30, "country": "US"},
            }
        },
    )


# PUBLIC_INTERFACE
class DataItemsPage(BaseModel):
    """Paginated list of data items."""
    items: List[DataItemOut] = Field(..., description="List of items in the page.")
    meta: PaginationMeta = Field(..., description="Pagination metadata.")


# ---------------------------------------------------------------------------
# NLQ Schemas
# ---------------------------------------------------------------------------

# PUBLIC_INTERFACE
class NLQRequest(BaseModel):
    """Natural Language Query request payload."""
    query: str = Field(..., description="Natural language query input.")
    collection: Optional[str] = Field(
        default=None,
        description="Target collection name; defaults to configured collection if omitted.",
    )
    params: Optional[QueryParams] = Field(
        default=None, description="Optional query parameters to refine results."
    )

    model_config = ConfigDict(
        json_schema_extra={"example": {"query": "List top 10 customers by revenue"}}
    )


# PUBLIC_INTERFACE
class NLQResponse(BaseModel):
    """Response for NLQ endpoint including derived filter and results."""
    nlq: str = Field(..., description="Original NLQ string.")
    filter: Dict[str, Any] = Field(
        default_factory=dict,
        description="Derived MongoDB filter used to fetch results.",
    )
    items: List[Dict[str, Any]] = Field(
        default_factory=list,
        description="List of result documents (projected/normalized).",
    )
    meta: PaginationMeta = Field(
        ...,
        description="Pagination metadata for the returned results.",
    )
