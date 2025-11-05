from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import ORJSONResponse

from ..core.config import get_settings
from ..core.logger import get_logger
from ..routers.health import router as health_router
from ..routers.data import router as data_router
from ..routers.nlq import router as nlq_router
from ..routers.supabase import router as supabase_router

# Important: avoid creating DB connections at import time.
# We only import lightweight helpers here; actual engine/session are created lazily within routes/startup.
from ..db.sqlalchemy import get_engine  # lazy accessor (no connection on import)  # noqa: F401
from ..models.sql_models import Item  # ensure model class is imported so metadata is registered  # noqa: F401

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

    Ensures database tables exist by creating them if needed. Uses lazy engine access to avoid
    import-time connections. If a Mongo-dependent router exists, guard its registration gracefully.
    """
    # Lazily create engine and create tables; connectivity will be validated by /health/db
    try:
        from ..db.sqlalchemy import Base  # local import binds metadata
        from sqlalchemy import text as _sql_text
        from ..db.sqlalchemy import get_engine as _lazy_engine

        engine = _lazy_engine()
        Base.metadata.create_all(bind=engine)
        # Optional lightweight probe without failing startup: swallow errors to allow app to boot
        try:
            with engine.connect() as conn:
                conn.execute(_sql_text("SELECT 1"))
            logger.info("Database connectivity verified on startup.")
        except Exception as ping_exc:
            logger.warning("Database ping failed on startup; service will still start.", exc_info=ping_exc)
    except Exception as exc:
        logger.error("Database initialization failed on startup; continuing without DB.", exc_info=exc)

    # Example guard for any hypothetical Mongo-only routers (none currently strictly depend on Mongo).
    # If you add Mongo routers in the future, wrap include_router in try/except here.


@app.on_event("shutdown")
async def shutdown_event():
    """FastAPI shutdown hook."""
    try:
        from ..db.sqlalchemy import get_engine as _lazy_engine

        engine = _lazy_engine()
        engine.dispose()
        logger.info("SQLAlchemy engine disposed.")
    except Exception as exc:
        # Do not fail shutdown
        logger.warning("Error disposing SQLAlchemy engine.", exc_info=exc)


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


if __name__ == "__main__":
    # Allow running as: python -m src.api.main
    import os
    import uvicorn  # type: ignore

    port = int(os.getenv("PORT", "3001"))
    uvicorn.run("src.api.main:app", host="0.0.0.0", port=port, log_level="info")
