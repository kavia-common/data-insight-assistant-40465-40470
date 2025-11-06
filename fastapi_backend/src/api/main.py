from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import ORJSONResponse

from ..core.config import get_settings
from ..core.logger import get_logger
from ..routers.health import router as health_router
from ..routers.data import router as data_router
from ..routers.nlq import router as nlq_router
from ..routers.supabase import router as supabase_router
from ..routers.supabase_ping import router as supabase_ping_router
from ..routers.debug import router as debug_router

# Important: avoid creating DB connections at import time.
# We only import lightweight helpers here; actual engine/session are created lazily within routes/startup.
# Intentionally avoid importing DB accessors or ORM models here to prevent any
# accidental side effects or metadata bindings that could lead to implicit DB access.

settings = get_settings()
logger = get_logger(__name__)

# Initialize FastAPI application with metadata and orjson for performance
app = FastAPI(
    title=settings.APP_NAME,
    description="REST API backend for data retrieval via NLQ with SQLAlchemy (Supabase Postgres).",
    version="0.2.0",
    default_response_class=ORJSONResponse,
    openapi_tags=[
        {"name": "Health", "description": "Service health and diagnostics"},
        {"name": "Data", "description": "Data access and management"},
        {"name": "NLQ", "description": "Natural Language Query endpoints"},
        {"name": "Supabase", "description": "Supabase table query endpoints"},
    ],
)

# CORS configuration driven by settings
origins = settings.cors_origins_list()
app.add_middleware(
    CORSMiddleware,
    allow_origins=origins if origins != ["*"] else ["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

logger.info("FastAPI app initialized", extra={"app_name": settings.APP_NAME, "env": settings.APP_ENV})


@app.on_event("startup")
async def startup_event():
    """FastAPI startup hook.

    Strictly no-DB: Do not import or initialize the database here. This ensures that endpoints
    like /health and /debug/config never trigger lazy connections through import chains or startup hooks.
    Any schema creation and connectivity validation must be performed explicitly by /health/db or
    operational migrations outside the app.
    """
    logger.info("Startup complete (no-DB mode).")


@app.on_event("shutdown")
async def shutdown_event():
    """FastAPI shutdown hook.

    Strictly no-DB: do not import DB or dispose engine here to avoid initializing it on shutdown.
    Connection pools will be cleaned up by process termination.
    """
    logger.info("Shutdown complete (no-DB mode).")


# Root health remains available (back-compat)
@app.get("/", summary="Health Check (root)", tags=["Health"])
def health_check_root():
    """Root-level health check maintained for backwards compatibility.

    Returns:
        A simple JSON message indicating the service is healthy.
    """
    return {"message": "Healthy"}


# Include routers (ensure all are mounted). Mongo-specific routers should be guarded if added later.
app.include_router(health_router)
app.include_router(data_router)
app.include_router(nlq_router)
app.include_router(supabase_router)
app.include_router(supabase_ping_router)
app.include_router(debug_router)


if __name__ == "__main__":
    # Allow running as: python -m src.api.main
    import os
    import uvicorn  # type: ignore

    port = int(os.getenv("PORT", "3001"))
    uvicorn.run("src.api.main:app", host="0.0.0.0", port=port, log_level="info")
