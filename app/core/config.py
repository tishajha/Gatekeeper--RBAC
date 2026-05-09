"""Application configuration loaded from environment variables.

Uses pydantic-settings so config is type-checked and validated at startup
rather than failing at runtime when a value is missing or malformed.
"""
from functools import lru_cache

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    """Application settings.

    Values are loaded from environment variables, with a `.env` file as
    fallback for local development. Defaults are safe for development only.
    """

    # JWT
    SECRET_KEY: str = "change-me-to-a-long-random-string-in-production"
    ALGORITHM: str = "HS256"
    ACCESS_TOKEN_EXPIRE_MINUTES: int = 30

    # Database
    DATABASE_URL: str = "sqlite:///./gatekeeper.db"

    # Seed defaults
    DEFAULT_ADMIN_USERNAME: str = "admin"
    DEFAULT_ADMIN_PASSWORD: str = "admin123"

    # API metadata
    PROJECT_NAME: str = "GateKeeper RBAC Execution Platform"
    API_V1_PREFIX: str = ""

    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        case_sensitive=True,
        extra="ignore",
    )


@lru_cache
def get_settings() -> Settings:
    """Return a cached Settings instance.

    `lru_cache` ensures we instantiate Settings exactly once per process,
    which means env vars are read once and the object is shared everywhere
    it's injected as a dependency.
    """
    return Settings()


settings = get_settings()
