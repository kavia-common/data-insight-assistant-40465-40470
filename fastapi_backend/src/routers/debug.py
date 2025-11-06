from typing import Any, Dict, Optional
import os

from fastapi import APIRouter
from pydantic import BaseModel, Field

from ..core.config import get_settings
from ..core.logger import get_logger
from ..db.sqlalchemy import get_effective_db_params

logger = get_logger(__name__)
router = APIRouter(prefix="/debug", tags=["Health"])


def _detect_db_source() -> str:
    """
    Determine which source would be used for DB config based on precedence:
      1) DATABASE_URL
      2) SUPABASE_DB_CONNECTION_STRING
      3) discrete (user, password, host, port, dbname)
    """
    s = get_settings()
    if (s.DATABASE_URL or "").strip():
        return "DATABASE_URL"
    if (s.SUPABASE_DB_CONNECTION_STRING or "").strip():
        return "SUPABASE_DB_CONNECTION_STRING"
    # Check discrete set presence
    if all([(os.getenv("user") or "").strip(),
            (os.getenv("password") or "").strip(),
            (os.getenv("host") or "").strip(),
            (os.getenv("port") or "").strip(),
            (os.getenv("dbname") or "").strip()]):
        return "discrete"
    return "unconfigured"


def _redact_env_url(url: Optional[str]) -> Optional[str]:
    if not url:
        return None
    try:
        if "://" not in url:
            return url
        scheme, rest = url.split("://", 1)
        if "@" in rest:
            creds, hostpart = rest.split("@", 1)
            if ":" in creds:
                user = creds.split(":", 1)[0]
                return f"{scheme}://{user}:****@{hostpart}"
            return f"{scheme}://****@{hostpart}"
        return f"{scheme}://{rest}"
    except Exception:
        return "<redaction_error>"


class DBConfigDebug(BaseModel):
    """Effective database configuration (redacted) for diagnostics."""
    source: str = Field(..., description="Which configuration source is active (DATABASE_URL, SUPABASE_DB_CONNECTION_STRING, discrete, or unconfigured)")
    host: Optional[str] = Field(None, description="Effective database host")
    port: Optional[str] = Field(None, description="Effective database port")
    database: Optional[str] = Field(None, description="Effective database name")
    sslmode_present: bool = Field(..., description="Whether sslmode is present on the connection URL")
    driver: str = Field(..., description="Resolved SQLAlchemy driver (e.g., psycopg2)")
    redacted_url: Optional[str] = Field(None, description="Redacted connection URL suitable for logs")
    env_presence: Dict[str, Any] = Field(..., description="Presence flags of env vars (.env loading check)")
    notes: Optional[str] = Field(None, description="Additional notes or warnings about precedence or conflicts")


def _env_presence() -> Dict[str, Any]:
    s = get_settings()
    return {
        "DATABASE_URL_set": bool((s.DATABASE_URL or "").strip()),
        "SUPABASE_DB_CONNECTION_STRING_set": bool((s.SUPABASE_DB_CONNECTION_STRING or "").strip()),
        "discrete": {
            "user_set": bool((os.getenv("user") or "").strip()),
            "password_set": bool((os.getenv("password") or "").strip()),
            "host_set": bool((os.getenv("host") or "").strip()),
            "port_set": bool((os.getenv("port") or "").strip()),
            "dbname_set": bool((os.getenv("dbname") or "").strip()),
        },
    }


# PUBLIC_INTERFACE
@router.get(
    "/config",
    response_model=DBConfigDebug,
    summary="Effective DB configuration (redacted)",
    description="Returns currently effective database configuration, which source is in use, host/port, and a redacted URL. Useful for diagnosing env/.env precedence issues.",
    responses={
        200: {"description": "Effective configuration returned."}
    },
)
def debug_config() -> DBConfigDebug:
    """
    Diagnostic endpoint to reveal the active DB configuration without exposing secrets.
    This helps verify that .env is loaded and that precedence matches expectations.
    """
    # Pull effective params parsed by the same resolution logic used by engine creation
    eff = get_effective_db_params()
    presence = _env_presence()
    src = _detect_db_source()

    # Optional note if both modern and legacy URLs are set
    notes = None
    if presence["DATABASE_URL_set"] and presence["SUPABASE_DB_CONNECTION_STRING_set"]:
        notes = "Both DATABASE_URL and SUPABASE_DB_CONNECTION_STRING are set. DATABASE_URL takes precedence."

    # Also include the redacted env URLs to aid debugging when 'discrete' is selected
    s = get_settings()
    db_url_redacted = _redact_env_url(s.DATABASE_URL)
    legacy_url_redacted = _redact_env_url(s.SUPABASE_DB_CONNECTION_STRING)

    payload = DBConfigDebug(
        source=src,
        host=eff.get("host"),
        port=str(eff.get("port")) if eff.get("port") is not None else None,
        database=eff.get("database"),
        sslmode_present=bool(eff.get("sslmode_present")),
        driver=str(eff.get("driver")),
        redacted_url=str(eff.get("url_redacted") or db_url_redacted or legacy_url_redacted or ""),
        env_presence={**presence, "raw_env_urls": {"DATABASE_URL": db_url_redacted, "SUPABASE_DB_CONNECTION_STRING": legacy_url_redacted}},
        notes=notes,
    )

    logger.info("Debug config requested", extra={"db_config": payload.model_dump()})
    return payload
