from __future__ import annotations

import tomllib
from dataclasses import dataclass
from importlib import resources
from pathlib import Path
from typing import Any

from vossploee.errors import CapabilityConfigurationError

_CAP_FILE = "config.toml"

# When config.toml is missing, use these defaults (per capability id).
_DEFAULT_TOOLS: dict[str, tuple[str, ...]] = {
    "core": ("core.imap",),
}


@dataclass(frozen=True, slots=True)
class ImapToolConfig:
    """IMAP / outbound SMTP endpoints for the core.imap tool (SSL). Credentials are never stored here."""

    host: str
    port: int
    smtp_host: str
    smtp_port: int
    user_env: str
    password_env: str


# Defaults for `core` when [imap] is absent or partial (Zoho-hosted SSL).
_DEFAULT_CORE_IMAP = ImapToolConfig(
    host="imappro.zoho.eu",
    port=993,
    smtp_host="smtppro.zoho.eu",
    smtp_port=465,
    user_env="VOSSPLOEE_CORE_IMAP_USER",
    password_env="VOSSPLOEE_CORE_IMAP_PASSWORD",
)


@dataclass(frozen=True, slots=True)
class CapabilitySettings:
    """Per-capability configuration (model override, tool allowlist, tool-specific blocks)."""

    capability_id: str
    model: str | None
    tools: tuple[str, ...]
    architect_prompt: str | None = None
    imap: ImapToolConfig | None = None
    upwork: "UpworkToolConfig | None" = None


@dataclass(frozen=True, slots=True)
class UpworkSearchDefaults:
    """Optional default filters for upworkmanager.search_jobs."""

    query: str | None
    minutes: int
    limit: int
    min_budget: int | None
    max_budget: int | None
    min_hourly_rate: int | None
    max_hourly_rate: int | None
    client_country: str | None


@dataclass(frozen=True, slots=True)
class UpworkToolConfig:
    """Upwork API settings; credentials are resolved from env by api_key_env."""

    base_url: str
    api_key_env: str
    user_agent: str
    search_defaults: UpworkSearchDefaults


def _parse_tools_value(raw: object, capability_id: str) -> tuple[str, ...]:
    if raw is None:
        return _DEFAULT_TOOLS.get(capability_id, ())
    if not isinstance(raw, list):
        raise CapabilityConfigurationError(
            f"Capability '{capability_id}': 'tools' must be a list of strings in {_CAP_FILE}."
        )
    out: list[str] = []
    for item in raw:
        if not isinstance(item, str) or not item.strip():
            raise CapabilityConfigurationError(
                f"Capability '{capability_id}': each tool entry must be a non-empty string."
            )
        out.append(item.strip())
    return tuple(out)


def _parse_port(raw: object, field: str, capability_id: str) -> int:
    if isinstance(raw, bool) or not isinstance(raw, int):
        raise CapabilityConfigurationError(
            f"Capability '{capability_id}': imap.{field} must be an integer in {_CAP_FILE}."
        )
    if not (1 <= raw <= 65535):
        raise CapabilityConfigurationError(
            f"Capability '{capability_id}': imap.{field} must be between 1 and 65535."
        )
    return raw


def _parse_env_name(raw: object, field: str, capability_id: str) -> str:
    if not isinstance(raw, str) or not raw.strip():
        raise CapabilityConfigurationError(
            f"Capability '{capability_id}': {field} must be a non-empty env var name in {_CAP_FILE}."
        )
    return raw.strip()


def _parse_imap_section(raw: object | None, *, capability_id: str) -> ImapToolConfig | None:
    """Parse `[imap]` for the `core` capability (`core.imap` tool). Other capabilities ignore this block."""
    if capability_id != "core":
        return None
    if raw is None:
        return _DEFAULT_CORE_IMAP
    if not isinstance(raw, dict):
        raise CapabilityConfigurationError(
            f"Capability '{capability_id}': 'imap' must be a table in {_CAP_FILE}."
        )

    base = _DEFAULT_CORE_IMAP

    def _merge_str(key: str, fallback: str) -> str:
        v = raw.get(key, fallback)
        if not isinstance(v, str) or not v.strip():
            raise CapabilityConfigurationError(
                f"Capability '{capability_id}': imap.{key} must be a non-empty string in {_CAP_FILE}."
            )
        return v.strip()

    return ImapToolConfig(
        host=_merge_str("host", base.host),
        port=_parse_port(raw.get("port", base.port), "port", capability_id),
        smtp_host=_merge_str("smtp_host", base.smtp_host),
        smtp_port=_parse_port(raw.get("smtp_port", base.smtp_port), "smtp_port", capability_id),
        user_env=_parse_env_name(raw.get("user_env", base.user_env), "user_env", capability_id),
        password_env=_parse_env_name(
            raw.get("password_env", base.password_env),
            "password_env",
            capability_id,
        ),
    )


_DEFAULT_UPWORK = UpworkToolConfig(
    base_url="https://api.upwork.com/graphql",
    api_key_env="VOSSPLOEE_UPWORK_API_KEY",
    user_agent="vossploee-upworkmanager/1.0",
    search_defaults=UpworkSearchDefaults(
        query=None,
        minutes=10,
        limit=20,
        min_budget=None,
        max_budget=None,
        min_hourly_rate=None,
        max_hourly_rate=None,
        client_country=None,
    ),
)


def _parse_int_range(
    raw: object,
    *,
    field: str,
    capability_id: str,
    minimum: int,
    maximum: int,
) -> int:
    if isinstance(raw, bool) or not isinstance(raw, int):
        raise CapabilityConfigurationError(
            f"Capability '{capability_id}': {field} must be an integer in {_CAP_FILE}."
        )
    if raw < minimum or raw > maximum:
        raise CapabilityConfigurationError(
            f"Capability '{capability_id}': {field} must be between {minimum} and {maximum}."
        )
    return raw


def _parse_optional_non_negative_int(raw: object, *, field: str, capability_id: str) -> int | None:
    if raw is None:
        return None
    if isinstance(raw, bool) or not isinstance(raw, int):
        raise CapabilityConfigurationError(
            f"Capability '{capability_id}': {field} must be an integer or omitted in {_CAP_FILE}."
        )
    if raw < 0:
        raise CapabilityConfigurationError(
            f"Capability '{capability_id}': {field} must be >= 0."
        )
    return raw


def _parse_optional_trimmed_str(raw: object, *, field: str, capability_id: str) -> str | None:
    if raw is None:
        return None
    if not isinstance(raw, str):
        raise CapabilityConfigurationError(
            f"Capability '{capability_id}': {field} must be a string or omitted in {_CAP_FILE}."
        )
    text = raw.strip()
    return text or None


def _parse_upwork_search_defaults(raw: object | None, *, capability_id: str) -> UpworkSearchDefaults:
    base = _DEFAULT_UPWORK.search_defaults
    if raw is None:
        return base
    if not isinstance(raw, dict):
        raise CapabilityConfigurationError(
            f"Capability '{capability_id}': 'upwork.search_defaults' must be a table in {_CAP_FILE}."
        )
    return UpworkSearchDefaults(
        query=_parse_optional_trimmed_str(
            raw.get("query", base.query),
            field="upwork.search_defaults.query",
            capability_id=capability_id,
        ),
        minutes=_parse_int_range(
            raw.get("minutes", base.minutes),
            field="upwork.search_defaults.minutes",
            capability_id=capability_id,
            minimum=1,
            maximum=1440,
        ),
        limit=_parse_int_range(
            raw.get("limit", base.limit),
            field="upwork.search_defaults.limit",
            capability_id=capability_id,
            minimum=1,
            maximum=50,
        ),
        min_budget=_parse_optional_non_negative_int(
            raw.get("min_budget", base.min_budget),
            field="upwork.search_defaults.min_budget",
            capability_id=capability_id,
        ),
        max_budget=_parse_optional_non_negative_int(
            raw.get("max_budget", base.max_budget),
            field="upwork.search_defaults.max_budget",
            capability_id=capability_id,
        ),
        min_hourly_rate=_parse_optional_non_negative_int(
            raw.get("min_hourly_rate", base.min_hourly_rate),
            field="upwork.search_defaults.min_hourly_rate",
            capability_id=capability_id,
        ),
        max_hourly_rate=_parse_optional_non_negative_int(
            raw.get("max_hourly_rate", base.max_hourly_rate),
            field="upwork.search_defaults.max_hourly_rate",
            capability_id=capability_id,
        ),
        client_country=_parse_optional_trimmed_str(
            raw.get("client_country", base.client_country),
            field="upwork.search_defaults.client_country",
            capability_id=capability_id,
        ),
    )


def _parse_upwork_section(raw: object | None, *, capability_id: str) -> UpworkToolConfig | None:
    """Parse `[upwork]` config for the upworkmanager capability."""
    if capability_id != "upworkmanager":
        return None
    if raw is None:
        return _DEFAULT_UPWORK
    if not isinstance(raw, dict):
        raise CapabilityConfigurationError(
            f"Capability '{capability_id}': 'upwork' must be a table in {_CAP_FILE}."
        )

    base = _DEFAULT_UPWORK

    def _merge_str(key: str, fallback: str) -> str:
        v = raw.get(key, fallback)
        if not isinstance(v, str) or not v.strip():
            raise CapabilityConfigurationError(
                f"Capability '{capability_id}': upwork.{key} must be a non-empty string in {_CAP_FILE}."
            )
        return v.strip()

    return UpworkToolConfig(
        base_url=_merge_str("base_url", base.base_url),
        api_key_env=_parse_env_name(raw.get("api_key_env", base.api_key_env), "api_key_env", capability_id),
        user_agent=_merge_str("user_agent", base.user_agent),
        search_defaults=_parse_upwork_search_defaults(
            raw.get("search_defaults"),
            capability_id=capability_id,
        ),
    )


def _read_toml_from_package(capability_id: str) -> dict[str, Any] | None:
    try:
        pkg = f"vossploee.capabilities.{capability_id}"
        files = resources.files(pkg)
        path = files.joinpath(_CAP_FILE)
        if not path.is_file():
            return None
        data = path.read_bytes()
    except (ModuleNotFoundError, FileNotFoundError, OSError):
        return None
    return tomllib.loads(data.decode("utf-8"))


def _read_toml_from_filesystem(capability_id: str) -> dict[str, Any] | None:
    base = Path(__file__).resolve().parent / capability_id / _CAP_FILE
    if not base.is_file():
        return None
    return tomllib.loads(base.read_text(encoding="utf-8"))


def load_capability_settings(capability_id: str) -> CapabilitySettings:
    """Load `{capability}/config.toml` from the installed package, with sensible defaults."""
    parsed = _read_toml_from_package(capability_id)
    if parsed is None:
        parsed = _read_toml_from_filesystem(capability_id)

    if parsed is None:
        tools = _DEFAULT_TOOLS.get(capability_id, ())
        architect_prompt = None
        imap = _parse_imap_section(None, capability_id=capability_id)
        upwork = _parse_upwork_section(None, capability_id=capability_id)
        return CapabilitySettings(
            capability_id=capability_id,
            model=None,
            tools=tools,
            architect_prompt=architect_prompt,
            imap=imap,
            upwork=upwork,
        )

    model_raw = parsed.get("model")
    model: str | None
    if model_raw is None or model_raw == "":
        model = None
    elif isinstance(model_raw, str):
        model = model_raw.strip() or None
    else:
        raise CapabilityConfigurationError(
            f"Capability '{capability_id}': 'model' must be a string or omitted in {_CAP_FILE}."
        )

    tools = _parse_tools_value(parsed.get("tools"), capability_id)
    architect_prompt = _parse_optional_trimmed_str(
        parsed.get("architect_prompt"),
        field="architect_prompt",
        capability_id=capability_id,
    )
    imap = _parse_imap_section(parsed.get("imap"), capability_id=capability_id)
    upwork = _parse_upwork_section(parsed.get("upwork"), capability_id=capability_id)
    return CapabilitySettings(
        capability_id=capability_id,
        model=model,
        tools=tools,
        architect_prompt=architect_prompt,
        imap=imap,
        upwork=upwork,
    )
