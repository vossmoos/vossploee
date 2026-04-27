from __future__ import annotations

import os
from functools import lru_cache
from pathlib import Path
from typing import Annotated

from dotenv import load_dotenv
from pydantic import AliasChoices, Field, field_validator
from pydantic_settings import BaseSettings, NoDecode, SettingsConfigDict


class Settings(BaseSettings):
    app_name: str = "Vossploee"
    database_path: Path = Field(default=Path("data/tasks.db"))
    chroma_path: Path = Field(default=Path("data/chroma"))
    api_prefix: str = "/api"
    api_key: str = ""
    poll_interval_seconds: float = Field(default=1.0, ge=0.05)
    agent_model: str = "openai:gpt-5.4-mini"
    enabled_capabilities: Annotated[list[str], NoDecode] = Field(default_factory=lambda: ["core", "uw"])
    enabled_channels: Annotated[list[str], NoDecode] = Field(default_factory=lambda: ["email", "rest", "telegram"])
    entrypoint_decomposer: str = "core.decomposer"
    reasoning_log_enabled: bool = False
    memory_inject_top_k: int = Field(default=6, ge=1, le=15)
    channel_email_allowed_senders: Annotated[list[str], NoDecode] = Field(default_factory=list)
    channel_email_poll_seconds: int = Field(default=600, ge=30)
    channel_email_imap_host: str = "imappro.zoho.eu"
    channel_email_imap_port: int = 993
    channel_email_smtp_host: str = "smtppro.zoho.eu"
    channel_email_smtp_port: int = 465
    channel_email_user_env: str = "VOSSPLOEE_CORE_IMAP_USER"
    channel_email_password_env: str = "VOSSPLOEE_CORE_IMAP_PASSWORD"
    channel_telegram_poll_seconds: float = Field(default=10.0, ge=0.5)
    channel_telegram_bot_token_env: str = "VOSSPLOEE_TELEGRAM_BOT_TOKEN"
    channel_telegram_allowed_chat_ids: Annotated[list[str], NoDecode] = Field(default_factory=list)
    openai_api_key: str | None = Field(
        default=None,
        validation_alias=AliasChoices("OPENAI_API_KEY", "VOSSPLOEE_OPENAI_API_KEY"),
    )

    model_config = SettingsConfigDict(
        env_prefix="VOSSPLOEE_",
        env_file=".env",
        extra="ignore",
    )

    @field_validator(
        "enabled_capabilities",
        "enabled_channels",
        "channel_email_allowed_senders",
        "channel_telegram_allowed_chat_ids",
        mode="before",
    )
    @classmethod
    def parse_csv_list(cls, value: object) -> list[str]:
        if value is None or value == "":
            return []
        if isinstance(value, str):
            return [part.strip() for part in value.split(",") if part.strip()]
        if isinstance(value, list):
            return [str(item).strip() for item in value if str(item).strip()]
        raise TypeError("value must be a list or comma-separated string")


@lru_cache(maxsize=1)
def get_settings() -> Settings:
    load_dotenv()
    settings = Settings()
    if settings.openai_api_key:
        os.environ.setdefault("OPENAI_API_KEY", settings.openai_api_key)
    return settings
