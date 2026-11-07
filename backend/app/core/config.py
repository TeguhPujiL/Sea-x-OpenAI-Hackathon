from functools import lru_cache
from pathlib import Path

from pydantic import SecretStr, UUID4, model_validator
from pydantic_settings import BaseSettings, SettingsConfigDict

ROOT = Path(__file__).resolve().parents[3]


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=ROOT / ".env", env_prefix="PROCUREMIND_", extra="ignore")
    database_url: str = "sqlite:///./procuremind.db"
    demo_mode: bool = False
    demo_actor_id: UUID4 | None = None
    demo_display_name: str = "Demo Analyst"
    demo_role: str = "ANALYST"
    demo_scopes: frozenset[str] = frozenset()
    openai_api_key: SecretStr | None = None
    openai_model: str = "gpt-6.1-sol"

    @model_validator(mode="after")
    def validate_demo(self):
        if self.demo_mode and self.demo_actor_id is None:
            raise ValueError("Demo mode requires a backend-configured UUID v4 actor")
        if self.demo_role not in {"ANALYST", "REVIEWER", "ADMIN", "AUDITOR"}:
            raise ValueError("Unknown demo role")
        return self


@lru_cache
def get_settings() -> Settings:
    return Settings()
