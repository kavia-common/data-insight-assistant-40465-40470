from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import ORJSONResponse

from ..core.config import settings
from ..routers.health import router as health_router
from ..routers.data import router as data_router
from ..routers.nlq import router as nlq_router

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

# CORS - permissive for now, will be tightened in later steps
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"] if settings.CORS_ALLOWED_ORIGINS == "*" else [o.strip() for o in settings.CORS_ALLOWED_ORIGINS.split(",") if o.strip()],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Root health remains available (back-compat)
@app.get("/", summary="Health Check", tags=["Health"])
def health_check_root():
    """Root-level health check maintained for backwards compatibility."""
    return {"message": "Healthy"}

# Include routers
app.include_router(health_router)
app.include_router(data_router)
app.include_router(nlq_router)
