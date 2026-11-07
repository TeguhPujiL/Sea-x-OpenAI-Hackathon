from functools import lru_cache
from pathlib import Path
from typing import Literal

from pydantic import Field, SecretStr, UUID4, model_validator
from pydantic_settings import BaseSettings, SettingsConfigDict

ROOT = Path(__file__).resolve().parents[3]


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=ROOT / ".env", env_prefix="PROCUREMIND_", extra="ignore")
    database_url: str = "sqlite:///./procuremind.db"
    document_classification_enabled: bool = False  # DC1 opt-in extension.
    p1_enabled: bool = False  # PROPOSED P1.1; requires explicit addendum approval.
    demo_mode: bool = False
    demo_actor_id: UUID4 | None = None
    demo_display_name: str = "Demo Analyst"
    demo_role: str = "ANALYST"
    demo_scopes: frozenset[str] = frozenset()
    storage_root: Path = ROOT / ".storage"
    upload_max_bytes: int = Field(default=10 * 1024 * 1024, ge=1024)
    pdf_max_pages: int = Field(default=100, ge=1)
    pdf_max_characters: int = Field(default=500_000, ge=1)
    ai_max_input_characters: int = Field(default=100_000, ge=1)
    openai_timeout_seconds: float = Field(default=60.0, gt=0)
    openai_provider: Literal["openai"] = "openai"
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
