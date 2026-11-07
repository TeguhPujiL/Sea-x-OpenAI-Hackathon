from functools import lru_cache
from pathlib import Path

from pydantic import SecretStr, UUID4
from pydantic_settings import BaseSettings, SettingsConfigDict

PROJECT_ROOT = Path(__file__).resolve().parents[3]


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=PROJECT_ROOT / ".env", env_prefix="PROCUREMIND_", extra="ignore"
    )
    database_url: str = "sqlite:///./procuremind.db"
    demo_actor_id: UUID4 | None = None
    openai_api_key: SecretStr | None = None
    openai_model: str | None = None


@lru_cache
def get_settings() -> Settings:
    return Settings()
