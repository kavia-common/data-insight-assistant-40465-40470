"""
Pydantic schemas (skeleton).

Detailed request/response models will be added in step 4.
"""

from pydantic import BaseModel, Field

# PUBLIC_INTERFACE
class HealthResponse(BaseModel):
    """Basic health response schema."""
    status: str = Field(..., description="Health status message, e.g., 'ok'")
