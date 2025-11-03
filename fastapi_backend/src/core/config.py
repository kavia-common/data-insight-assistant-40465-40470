"""
Application configuration module.

This placeholder will be expanded in subsequent steps to load environment
variables and provide strongly-typed settings across the app.
"""

from typing import Optional
import os

# PUBLIC_INTERFACE
class Settings:
    """Minimal settings placeholder. Will be expanded with Pydantic in next steps."""
    APP_NAME: str = os.getenv("APP_NAME", "Data Insight Assistant")
    APP_ENV: str = os.getenv("APP_ENV", "development")
    LOG_LEVEL: str = os.getenv("LOG_LEVEL", "INFO")
    PORT: int = int(os.getenv("PORT", "3001"))
    CORS_ALLOWED_ORIGINS: str = os.getenv("CORS_ALLOWED_ORIGINS", "*")

    # Database
    MONGO_URI: Optional[str] = os.getenv("MONGO_URI")
    MONGO_DB_NAME: Optional[str] = os.getenv("MONGO_DB_NAME")
    MONGO_COLLECTION: Optional[str] = os.getenv("MONGO_COLLECTION")

    # Feature flags
    ENABLE_SUPABASE: str = os.getenv("ENABLE_SUPABASE", "false")
    ENABLE_NLQ: str = os.getenv("ENABLE_NLQ", "true")
    ENABLE_NLQ_AI: str = os.getenv("ENABLE_NLQ_AI", "false")

    # 3rd party keys (optional)
    SUPABASE_URL: Optional[str] = os.getenv("SUPABASE_URL")
    SUPABASE_ANON_KEY: Optional[str] = os.getenv("SUPABASE_ANON_KEY")
    OPENAI_API_KEY: Optional[str] = os.getenv("OPENAI_API_KEY")


settings = Settings()
