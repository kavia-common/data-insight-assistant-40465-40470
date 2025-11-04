"""
Async MongoDB client utilities.

Provides:
- Lifecycle helpers to connect and close a shared AsyncIOMotorClient
- Convenience accessors to get database and collection
- Optional ping on startup to validate connectivity

This module is intentionally lightweight; connection string and names
are sourced from environment via Settings (see core.config).
"""

from typing import Optional

from motor.motor_asyncio import AsyncIOMotorClient  # type: ignore
from pymongo.errors import PyMongoError

from ..core.config import get_settings
from ..core.logger import get_logger

_logger = get_logger(__name__)

_client: Optional[AsyncIOMotorClient] = None


def _settings():
    # Internal helper to avoid caching Settings at import-time during tests/reloads
    return get_settings()


# PUBLIC_INTERFACE
async def connect_client(ping: bool = False) -> Optional[AsyncIOMotorClient]:
    """Create and cache a shared AsyncIOMotorClient if not present.

    Args:
        ping: When True, performs a 'ping' command against the admin DB to
              verify connectivity on startup.

    Returns:
        The shared AsyncIOMotorClient instance or None if configuration is missing.

    Notes:
        - If MONGO_URI is not configured, returns None and logs at INFO level.
        - Safe to call multiple times; subsequent calls return the existing client.
    """
    global _client
    settings = _settings()
    if _client is not None:
        return _client

    if not settings.MONGO_URI:
        _logger.info(
            "MongoDB URI not configured; skipping client initialization.",
            extra={
                "mongodb_uri_set": False,
                "mongodb_db_name_set": bool(settings.MONGO_DB_NAME),
                "mongodb_collection_set": bool(settings.MONGO_COLLECTION),
            },
        )
        return None

    try:
        _client = AsyncIOMotorClient(settings.MONGO_URI)
        _logger.info(
            "MongoDB client initialized.",
            extra={
                "mongodb_uri_set": True,
                "mongodb_db_name_set": bool(settings.MONGO_DB_NAME),
                "mongodb_collection_set": bool(settings.MONGO_COLLECTION),
            },
        )

        if ping:
            try:
                await _client.admin.command("ping")
                _logger.info("MongoDB ping succeeded.")
            except Exception as ping_exc:
                _logger.error("MongoDB ping failed.", exc_info=ping_exc)
                # Keep client alive; ping can fail transiently depending on network/policies
        return _client
    except Exception as exc:
        _logger.error("Failed to initialize MongoDB client.", exc_info=exc)
        _client = None
        return None


# PUBLIC_INTERFACE
def get_client() -> Optional[AsyncIOMotorClient]:
    """Return the shared AsyncIOMotorClient instance if initialized, else None.

    This does not create a new client; call connect_client() during app startup.
    """
    return _client


# PUBLIC_INTERFACE
def get_database():
    """Return the configured MongoDB database handle or None if unavailable."""
    client = get_client()
    settings = _settings()
    if client is None or not settings.MONGO_DB_NAME:
        return None
    return client[settings.MONGO_DB_NAME]


# PUBLIC_INTERFACE
def get_collection(name: Optional[str] = None):
    """Return a MongoDB collection handle or None if unavailable.

    Args:
        name: Optional explicit collection name. If not provided, tries
              to use MONGO_COLLECTION from settings.

    Returns:
        The collection handle or None.
    """
    db = get_database()
    if db is None:
        return None
    settings = _settings()
    coll_name = name or settings.MONGO_COLLECTION
    if not coll_name:
        return None
    return db[coll_name]


# PUBLIC_INTERFACE
async def close_client() -> None:
    """Close the shared MongoDB client if it exists."""
    global _client
    if _client is not None:
        try:
            _client.close()
            _logger.info("MongoDB client closed.")
        except PyMongoError as exc:
            _logger.error("Error while closing MongoDB client.", exc_info=exc)
        finally:
            _client = None
