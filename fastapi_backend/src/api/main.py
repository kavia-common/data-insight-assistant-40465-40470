from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import ORJSONResponse

from ..core.config import get_settings
from ..core.logger import get_logger
from ..routers.health import router as health_router
from ..routers.data import router as data_router
from ..routers.nlq import router as nlq_router

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
    ],
)

# CORS configuration from settings
origins = settings.cors_origins_list()
app.add_middleware(
    CORSMiddleware,
    allow_origins=origins if origins != ["*"] else ["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

logger.info("FastAPI app initialized", extra={"app_name": settings.APP_NAME, "env": settings.APP_ENV})

# Root health remains available (back-compat)
@app.get("/", summary="Health Check", tags=["Health"])
def health_check_root():
    """Root-level health check maintained for backwards compatibility."""
    return {"message": "Healthy"}

# Include routers
app.include_router(health_router)
app.include_router(data_router)
app.include_router(nlq_router)
