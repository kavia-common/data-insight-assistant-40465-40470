"""
Application configuration module.

Provides strongly-typed settings using Pydantic BaseSettings. Values are loaded
from environment variables and .env (via python-dotenv automatically loaded by
Pydantic). Use get_settings() to obtain a cached Settings instance.

Supabase integration:
- Controlled by ENABLE_SUPABASE (default False).
- Requires SUPABASE_URL and SUPABASE_ANON_KEY to initialize the optional client.
- See services/supabase_client.py for the optional wrapper and health helper.
"""

from functools import lru_cache
from typing import Optional, List

from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict


# PUBLIC_INTERFACE
class Settings(BaseSettings):
    """Centralized application configuration powered by Pydantic BaseSettings."""

    # App
    APP_NAME: str = Field(default="Data Insight Assistant", description="Application name")
    APP_ENV: str = Field(default="development", description="Execution environment")
    LOG_LEVEL: str = Field(default="INFO", description="Root log level (DEBUG, INFO, WARNING, ERROR)")
    PORT: int = Field(default=3001, description="Port for the FastAPI server")
    CORS_ALLOWED_ORIGINS: str = Field(default="*", description="Comma-separated list of allowed CORS origins or '*'")

    # Database
    MONGO_URI: Optional[str] = Field(default=None, description="MongoDB connection URI")
    MONGO_DB_NAME: Optional[str] = Field(default=None, description="MongoDB database name")
    MONGO_COLLECTION: Optional[str] = Field(default=None, description="Default MongoDB collection name")
    MONGO_PING_ON_STARTUP: bool = Field(
        default=True,
        description="When true, perform a MongoDB ping during app startup to verify connectivity.",
    )

    # Feature flags
    ENABLE_SUPABASE: bool = Field(default=False, description="Enable Supabase integration")
    ENABLE_NLQ: bool = Field(default=True, description="Enable NLQ endpoints")
    ENABLE_NLQ_AI: bool = Field(default=False, description="Enable AI-augmented NLQ")

    # 3rd party keys (optional)
    SUPABASE_URL: Optional[str] = Field(default=None, description="Supabase project URL")
    SUPABASE_ANON_KEY: Optional[str] = Field(default=None, description="Supabase anon API key")
    OPENAI_API_KEY: Optional[str] = Field(default=None, description="OpenAI API key (optional)")

    model_config = SettingsConfigDict(env_file=".env", env_file_encoding="utf-8", extra="ignore")

    # Convenience helpers (non-env)
    def cors_origins_list(self) -> List[str]:
        """
        Parse CORS_ALLOWED_ORIGINS into a list. '*' returns ['*'] to indicate permissive mode.
        """
        raw = (self.CORS_ALLOWED_ORIGINS or "").strip()
        if raw == "*" or raw == "":
            return ["*"]
        return [o.strip() for o in raw.split(",") if o.strip()]


# PUBLIC_INTERFACE
@lru_cache(maxsize=1)
def get_settings() -> Settings:
    """Return a cached Settings instance."""
    return Settings()
