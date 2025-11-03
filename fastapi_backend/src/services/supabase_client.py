"""
Feature-flagged Supabase client wrapper.

This module provides a safe, optional integration with Supabase. The client is
initialized only when:
- ENABLE_SUPABASE is True, and
- SUPABASE_URL and SUPABASE_ANON_KEY are configured.

Design notes:
- This module intentionally lives outside of core paths to avoid hard dependencies.
- It exposes tiny helpers so other parts of the app can optionally leverage Supabase
  without causing import-time failures when disabled or missing configuration.
"""

from typing import Optional, Any

from ..core.config import get_settings
from ..core.logger import get_logger

_logger = get_logger(__name__)

_client: Optional[Any] = None  # avoid hard import when package absent


def _settings():
    # Avoid caching settings at import time
    return get_settings()


def _is_configured() -> bool:
    s = _settings()
    return bool(
        s.ENABLE_SUPABASE
        and (s.SUPABASE_URL or "").strip()
        and (s.SUPABASE_ANON_KEY or "").strip()
    )


# PUBLIC_INTERFACE
def is_supabase_enabled() -> bool:
    """Return True if Supabase feature flag is on and credentials are provided."""
    return _is_configured()


# PUBLIC_INTERFACE
def get_supabase_client() -> Optional[Any]:
    """
    Return a cached Supabase client if configuration and feature flag allow it, else None.

    This function never raises due to missing configuration; it logs a concise message and returns None.
    """
    global _client
    if _client is not None:
        return _client

    if not _is_configured():
        _logger.info(
            "Supabase not enabled or missing configuration; client not initialized.",
            extra={"enabled": _settings().ENABLE_SUPABASE},
        )
        return None

    try:
        from supabase import create_client  # type: ignore
        s = _settings()
        # create_client validates URL/key formats internally and can raise.
        _client = create_client(s.SUPABASE_URL, s.SUPABASE_ANON_KEY)  # type: ignore[arg-type]
        _logger.info("Supabase client initialized.")
        return _client
    except Exception as exc:
        _logger.error("Failed to initialize Supabase client.", exc_info=exc)
        _client = None
        return None


# PUBLIC_INTERFACE
def supabase_health() -> dict:
    """
    Return a minimal health indicator for Supabase.

    Returns a dict like:
      { "enabled": bool, "configured": bool, "available": bool }
    where:
      - enabled: Feature flag value
      - configured: Whether URL and key are present (in addition to flag)
      - available: True if client could be obtained successfully (best-effort)
    """
    s = _settings()
    enabled = bool(s.ENABLE_SUPABASE)
    configured = _is_configured()
    available = get_supabase_client() is not None if configured else False
    return {"enabled": enabled, "configured": configured, "available": available}
