from __future__ import annotations

import os
from functools import lru_cache
from pathlib import Path
from typing import Annotated

from dotenv import load_dotenv
from pydantic import AliasChoices, Field, field_validator
from pydantic_settings import BaseSettings, NoDecode, SettingsConfigDict


class Settings(BaseSettings):
    app_name: str = "Vossploee Task Orchestrator"
    database_path: Path = Field(default=Path("data/tasks.db"))
    poll_interval_seconds: float = Field(default=1.0, ge=0.05)
    agent_model: str | None = None
    """Comma-separated capability ids, or empty to enable every discovered capability package."""
    enabled_capabilities: Annotated[list[str], NoDecode] = Field(default_factory=list)
    api_prefix: str = "/api"
    api_key: str = Field(
        default="",
        description=(
            "If non-empty, every request must send X-API-KEY matching this value "
            "(401 if missing, 403 if wrong). The `default.env` template sets "
            "`VOSSPLOEE_API_KEY` so `cp default.env .env` enables this layer; leave empty "
            "to skip HTTP key checks (only on trusted networks)."
        ),
    )
    max_decomposed_roots: int = Field(
        default=168,
        ge=1,
        le=500,
        description="Max queue01 roots the Decomposer may emit in one POST /tasks (e.g. hourly runs).",
    )
    # Loaded from .env via OPENAI_API_KEY (or VOSSPLOEE_OPENAI_API_KEY); injected into
    # os.environ so pydantic-ai / OpenAI SDK pick it up (they do not read our .env file).
    openai_api_key: str | None = Field(
        default=None,
        validation_alias=AliasChoices("OPENAI_API_KEY", "VOSSPLOEE_OPENAI_API_KEY"),
    )

    model_config = SettingsConfigDict(
        env_prefix="VOSSPLOEE_",
        env_file=".env",
        extra="ignore",
    )

    @field_validator("enabled_capabilities", mode="before")
    @classmethod
    def parse_enabled_capabilities(cls, value: object) -> list[str]:
        if value is None or value == "":
            return []
        if isinstance(value, str):
            return [part.strip() for part in value.split(",") if part.strip()]
        if isinstance(value, list):
            return [str(item).strip() for item in value if str(item).strip()]
        raise TypeError("enabled_capabilities must be a list or comma-separated string")


@lru_cache(maxsize=1)
def get_settings() -> Settings:
    # pydantic-settings reads .env only into declared fields; merge the file into os.environ so
    # capability tools that resolve credentials via getenv(cfg.user_env) (e.g. mail) see .env values.
    load_dotenv()
    settings = Settings()
    if settings.openai_api_key:
        os.environ.setdefault("OPENAI_API_KEY", settings.openai_api_key)
    return settings
