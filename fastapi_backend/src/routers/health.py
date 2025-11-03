from fastapi import APIRouter
from ..models.schemas import HealthResponse

router = APIRouter(prefix="/health", tags=["Health"])

# PUBLIC_INTERFACE
@router.get(
    "",
    response_model=HealthResponse,
    summary="Service health",
    description="Simple health check endpoint to verify the API is running.",
    responses={200: {"description": "Service is healthy"}},
)
def get_health() -> HealthResponse:
    """Return a simple health status response."""
    return HealthResponse(status="ok")
