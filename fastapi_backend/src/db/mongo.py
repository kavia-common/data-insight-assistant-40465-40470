"""
MongoDB connection utilities (skeleton).

Real connection pooling and lifecycle management will be implemented in step 3.
"""

from typing import Optional
from motor.motor_asyncio import AsyncIOMotorClient  # type: ignore

from ..core.config import settings
from ..core.logger import get_logger

_logger = get_logger(__name__)

_client: Optional[AsyncIOMotorClient] = None

# PUBLIC_INTERFACE
def get_client() -> Optional[AsyncIOMotorClient]:
    """Return a shared AsyncIOMotorClient instance if configured, else None."""
    global _client
    try:
        if _client is None and settings.MONGO_URI:
            _logger.info("Initializing MongoDB client (deferred full setup).")
            _client = AsyncIOMotorClient(settings.MONGO_URI)
        return _client
    except Exception as exc:
        _logger.error(f"Failed to initialize MongoDB client: {exc}")
        return None
