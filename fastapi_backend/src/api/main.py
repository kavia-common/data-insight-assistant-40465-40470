from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import ORJSONResponse

from ..core.config import get_settings
from ..core.logger import get_logger
from ..routers.health import router as health_router
from ..routers.data import router as data_router
from ..routers.nlq import router as nlq_router
from ..routers.supabase import router as supabase_router
from ..db.mongo import connect_client, close_client  # lifecycle hooks

settings = get_settings()
logger = get_logger(__name__)

# Initialize FastAPI application with metadata and orjson for performance
app = FastAPI(
    title=settings.APP_NAME,
    description="REST API backend for data retrieval via NLQ with MongoDB integration.",
    version="0.1.0",
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

    Connects to MongoDB when MONGO_URI is configured. Performs an optional 'ping'
    check to validate connectivity based on settings.MONGO_PING_ON_STARTUP. Startup
    continues even if ping fails to avoid hard dependency during environments without DB access.
    """
    await connect_client(ping=bool(settings.MONGO_PING_ON_STARTUP))


@app.on_event("shutdown")
async def shutdown_event():
    """FastAPI shutdown hook.

    Closes the MongoDB client gracefully if it was initialized.
    """
    await close_client()


# Root health remains available (back-compat)
@app.get("/", summary="Health Check", tags=["Health"])
def health_check_root():
    """Root-level health check maintained for backwards compatibility.

    Returns:
        A simple JSON message indicating the service is healthy.
    """
    return {"message": "Healthy"}


# Include routers (ensure all are mounted)
app.include_router(health_router)
app.include_router(data_router)
app.include_router(nlq_router)
app.include_router(supabase_router)
