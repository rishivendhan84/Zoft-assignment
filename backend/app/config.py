from functools import lru_cache

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    """All knobs come from the environment; sane defaults for local dev."""

    database_url: str = "sqlite+aiosqlite:///./copilot.db"
    redis_url: str | None = None  # unset → in-memory event bus

    anthropic_api_key: str | None = None
    anthropic_model: str = "claude-sonnet-5"

    # Agent reliability knobs
    max_repair_attempts: int = 3
    llm_timeout_seconds: float = 30.0
    circuit_breaker_threshold: int = 3
    circuit_breaker_cooldown_seconds: float = 60.0

    cors_origins: str = "*"

    model_config = SettingsConfigDict(env_file=".env")


@lru_cache
def get_settings() -> Settings:
    return Settings()
