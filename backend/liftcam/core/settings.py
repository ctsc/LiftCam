from functools import lru_cache

from pydantic_settings import BaseSettings, SettingsConfigDict

# Placeholder until a real CDN/R2 default avatar exists.
DEFAULT_PROFILE_PICTURE_URL = "https://static.liftcam.app/avatars/default.png"


class Settings(BaseSettings):
    """Process configuration read from environment variables or a local .env file."""

    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

    env: str = "development"
    log_level: str = "INFO"

    # Pooled URL for the API, direct URL for the worker's SKIP LOCKED claims.
    database_url: str = "postgresql://liftcam:liftcam@localhost:5433/liftcam"
    database_direct_url: str = "postgresql://liftcam:liftcam@localhost:5433/liftcam"

    worker_poll_interval_s: float = 2.0

    # Auth (Phase 4). Override JWT_SECRET in any non-local environment.
    jwt_secret: str = "dev-only-change-me-use-32+chars!!"
    jwt_algorithm: str = "HS256"
    access_token_ttl_s: int = 900
    refresh_token_ttl_s: int = 60 * 60 * 24 * 30
    default_profile_picture_url: str = DEFAULT_PROFILE_PICTURE_URL


@lru_cache
def get_settings() -> Settings:
    return Settings()
