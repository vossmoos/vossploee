from __future__ import annotations

from importlib import import_module
from pkgutil import iter_modules
from pathlib import Path
import tomllib

from vossploee.capabilities.base import CapabilityModule
from vossploee.config import Settings
from vossploee.errors import CapabilityConfigurationError
from vossploee.models import CapabilityInfo

_ALIASES: dict[str, str] = {"upworkmanager": "uw"}


def list_capability_names() -> list[str]:
    import vossploee.capabilities as capabilities_pkg

    package_path = str(next(iter(capabilities_pkg.__path__)))
    return sorted(
        module.name
        for module in iter_modules([package_path])
        if module.ispkg and not module.name.startswith("_")
    )


def resolve_enabled_capability_names(settings: Settings) -> list[str]:
    configured = settings.enabled_capabilities
    discovered = list_capability_names()
    if not configured:
        return discovered
    normalized = [_ALIASES.get(cap_id, cap_id) for cap_id in configured]
    known = [cap_id for cap_id in normalized if cap_id in discovered]
    unknown = sorted(set(normalized) - set(discovered))
    if unknown and not known:
        raise CapabilityConfigurationError(
            f"Unknown capability id(s) in VOSSPLOEE_ENABLED_CAPABILITIES: {', '.join(unknown)}. "
            f"Known: {', '.join(discovered) or '<none>'}."
        )
    if unknown:
        # Keep backward compatibility with partially stale env values.
        return sorted(set(known))
    return sorted(set(known))


def bootstrap_tool_registry(capability_ids: list[str]) -> None:
    for name in capability_ids:
        mod = f"vossploee.capabilities.{name}.tools_register"
        try:
            import_module(mod)
        except ModuleNotFoundError as exc:
            if exc.name != mod:
                raise


def load_capabilities(settings: Settings) -> dict[str, CapabilityModule]:
    enabled = resolve_enabled_capability_names(settings)
    if not enabled:
        raise CapabilityConfigurationError("No capability packages found under vossploee.capabilities.")
    bootstrap_tool_registry(enabled)
    return {name: load_capability(name, settings) for name in sorted(enabled)}


def capability_info(capability_id: str) -> CapabilityInfo:
    cap = load_capability(capability_id, Settings())
    module = import_module(f"vossploee.capabilities.{capability_id}")
    cfg_path = Path(module.__file__).resolve().parent / "config.toml"
    tools: list[str] = []
    if cfg_path.exists():
        parsed_cfg = tomllib.loads(cfg_path.read_text(encoding="utf-8"))
        tools = [str(x) for x in parsed_cfg.get("tools", []) if str(x).strip()]
    role_ids = sorted(role.role_id for role in cap.roles().values())
    return CapabilityInfo(
        id=capability_id,
        description=cap.description,
        roles=role_ids,
        tools=tools,
        whoami=cap.whoami_markdown(),
    )


def list_capability_infos(settings: Settings) -> list[CapabilityInfo]:
    return [capability_info(name) for name in resolve_enabled_capability_names(settings)]


def load_capability(name: str, settings: Settings) -> CapabilityModule:
    module_name = f"vossploee.capabilities.{name}"
    try:
        module = import_module(module_name)
    except ModuleNotFoundError as exc:
        if exc.name != module_name:
            raise
        available = ", ".join(list_capability_names()) or "<none>"
        raise CapabilityConfigurationError(
            f"Unknown capability '{name}'. Available capabilities: {available}."
        ) from exc

    factory = getattr(module, "build_capability", None)
    if factory is None:
        raise CapabilityConfigurationError(
            f"Capability module '{module_name}' does not export build_capability(settings)."
        )

    capability = factory(settings)
    if not isinstance(capability, CapabilityModule):
        raise CapabilityConfigurationError(
            f"Capability '{name}' did not return a CapabilityModule instance."
        )

    return capability
