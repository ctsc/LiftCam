from functools import lru_cache

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    """Process configuration read from environment variables or a local .env file."""

    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

    env: str = "development"
    log_level: str = "INFO"

    # Pooled URL for the API, direct URL for the worker's SKIP LOCKED claims.
    database_url: str = "postgresql://liftcam:liftcam@localhost:5433/liftcam"
    database_direct_url: str = "postgresql://liftcam:liftcam@localhost:5433/liftcam"

    worker_poll_interval_s: float = 2.0


@lru_cache
def get_settings() -> Settings:
    return Settings()
