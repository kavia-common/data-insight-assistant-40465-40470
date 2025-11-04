from typing import Any, Dict

from fastapi import APIRouter
from ..core.config import get_settings
from ..core.logger import get_logger
from ..db.mongo import get_client
from ..models.schemas import HealthResponse
from ..services.supabase_client import supabase_health

router = APIRouter(prefix="/health", tags=["Health"])

_logger = get_logger(__name__)


async def _mongo_ping() -> Dict[str, Any]:
    """
    Attempt to ping MongoDB if a client exists.
    Returns a dict with available flag and optional error.
    """
    client = get_client()
    if client is None:
        return {"configured": False, "available": False}
    try:
        await client.admin.command("ping")
        return {"configured": True, "available": True}
    except Exception as exc:
        _logger.error("MongoDB ping failed in /health.", exc_info=exc)
        return {"configured": True, "available": False, "error": str(exc)}


# PUBLIC_INTERFACE
@router.get(
    "",
    response_model=HealthResponse,
    summary="Service health",
    description=(
        "Liveness/health endpoint. Always returns 200 when the app is up. "
        "Performs a best-effort MongoDB ping if configured and logs results; "
        "also reports Supabase availability if enabled. "
        "This endpoint is intended for liveness checks; it does not fail the request when dependencies are down."
    ),
    responses={
        200: {"description": "Service is healthy"},
        503: {"description": "Service degraded or dependencies unavailable"},
    },
)
async def get_health() -> HealthResponse:
    """
    Root health indicator used for liveness. Always returns 200 with {"status":"ok"}.

    Diagnostics:
      - MongoDB: If configured, performs ping and logs availability.
      - Supabase: Logs enabled/configured/available summary.

    For strict readiness, use application logs or create a dedicated readiness endpoint
    in future that returns 503 when dependencies are unavailable.
    """
    settings = get_settings()

    # MongoDB best-effort ping
    mongo = await _mongo_ping()

    # Supabase health indicator (non-async)
    sb = supabase_health()

    # Log structured diagnostics for observability
    _logger.info(
        "Health diagnostics",
        extra={
            "env": settings.APP_ENV,
            "mongo": mongo,
            "supabase": sb,
        },
    )

    # Always 200 for liveness
    return HealthResponse(status="ok")


# PUBLIC_INTERFACE
@router.get(
    "/healthz",
    response_model=HealthResponse,
    summary="Service health (alias)",
    description="Alias health endpoint commonly used by platforms for liveness checks.",
    responses={200: {"description": "Service is healthy"}},
)
async def get_healthz() -> HealthResponse:
    """Alias of /health that returns the same response payload."""
    return await get_health()
