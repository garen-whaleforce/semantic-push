"""Application configuration using pydantic-settings."""
from functools import lru_cache
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    """Application settings loaded from environment variables."""

    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        case_sensitive=False,
    )

    # FMP API
    fmp_api_key: str
    fmp_base_url: str = "https://financialmodelingprep.com/api/v3"

    # Database
    database_url: str

    # Application
    app_name: str = "Strategy Engine"
    debug: bool = False

    # SP500 cache TTL (hours)
    sp500_cache_ttl_hours: int = 24


@lru_cache
def get_settings() -> Settings:
    """Get cached settings instance."""
    return Settings()
