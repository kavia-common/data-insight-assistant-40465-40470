"""
Pydantic schemas for API requests and responses, including MongoDB ObjectId handling,
query parameters for filtering/pagination/sorting, data item models, and NLQ types.
"""

from typing import Any, Dict, List, Literal, Optional, Union

from pydantic import BaseModel, Field, ConfigDict


# ---------------------------------------------------------------------------
# MongoDB ObjectId utilities and serializer
# ---------------------------------------------------------------------------
try:
    from bson import ObjectId  # type: ignore
except Exception:  # pragma: no cover - fallback if bson not present at runtime
    class ObjectId(str):  # type: ignore
        """Fallback minimal ObjectId stub for environments without bson."""

        @classmethod
        def is_valid(cls, oid: Any) -> bool:
            # naive validation: 24 hex chars
            try:
                s = str(oid)
                return len(s) == 24 and all(c in "0123456789abcdefABCDEF" for c in s)
            except Exception:
                return False


# PUBLIC_INTERFACE
class PyObjectId(ObjectId):
    """Wrapper to allow Pydantic validation/serialization of MongoDB ObjectId."""

    @classmethod
    def __get_validators__(cls):
        yield cls.validate

    @classmethod
    def validate(cls, v: Any):
        """Validate and coerce input to a BSON ObjectId."""
        if isinstance(v, ObjectId):
            return v
        if isinstance(v, cls):
            return ObjectId(str(v))
        if isinstance(v, str) and ObjectId.is_valid(v):
            return ObjectId(v)
        raise TypeError("Invalid ObjectId")

    @classmethod
    def __get_pydantic_json_schema__(cls, core_schema, handler):
        """Represent ObjectId as string in generated schema."""
        schema = handler(core_schema)
        # ensure string representation in OpenAPI
        schema.update(type="string", example="60f7a2c7b4d1c8e5f4a9b0c1")
        return schema


def serialize_object_id(oid: Optional[Union[ObjectId, str]]) -> Optional[str]:
    """Helper to serialize ObjectId to string safely."""
    if oid is None:
        return None
    if isinstance(oid, ObjectId):
        return str(oid)
    if isinstance(oid, str):
        return oid
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
    id: PyObjectId = Field(..., alias="_id", description="MongoDB ObjectId of the item.")
    data: Dict[str, Any] = Field(..., description="Arbitrary item payload.")

    model_config = ConfigDict(
        populate_by_name=True,
        arbitrary_types_allowed=True,
        json_encoders={ObjectId: serialize_object_id, PyObjectId: serialize_object_id},
        json_schema_extra={
            "example": {
                "id": "60f7a2c7b4d1c8e5f4a9b0c1",
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
