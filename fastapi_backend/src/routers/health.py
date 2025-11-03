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
        "Health endpoint that reports app status, MongoDB connectivity (best-effort ping), "
        "and Supabase availability if enabled."
    ),
    responses={
        200: {"description": "Service is healthy"},
        503: {"description": "Service degraded or dependencies unavailable"},
    },
)
async def get_health() -> HealthResponse:
    """
    Return a simple health status response. Extended diagnostics are included in headers/logs.

    The response 'status' is 'ok' when the application is running. MongoDB and Supabase
    status are logged and can be inspected in application logs.
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

    # We keep HTTP 200 even if deps are down to allow liveness probes to pass by default.
    # If strict readiness is desired, this endpoint could return 503 when required deps fail.
    return HealthResponse(status="ok")
