from __future__ import annotations

from importlib import import_module
from pkgutil import iter_modules

from vossploee.capabilities.base import CapabilityModule
from vossploee.capabilities.capability_settings import load_capability_settings
from vossploee.capabilities.readme import parse_capability_readme, read_capability_readme_text
from vossploee.config import Settings
from vossploee.errors import CapabilityConfigurationError
from vossploee.models import CapabilityInfo
from vossploee.tools.registry import is_registered, registered_qualified_ids


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
    unknown = sorted(set(configured) - set(discovered))
    if unknown:
        raise CapabilityConfigurationError(
            f"Unknown capability id(s) in VOSSPLOEE_ENABLED_CAPABILITIES: {', '.join(unknown)}. "
            f"Known: {', '.join(discovered) or '<none>'}."
        )
    return configured


def bootstrap_tool_registry() -> None:
    """Import `tools_register` for every capability package so tools are defined before config validation."""
    for name in list_capability_names():
        mod = f"vossploee.capabilities.{name}.tools_register"
        try:
            import_module(mod)
        except ModuleNotFoundError as exc:
            if exc.name != mod:
                raise


def _validate_tool_allowlists(enabled_capability_ids: list[str]) -> None:
    for cap_id in enabled_capability_ids:
        cfg = load_capability_settings(cap_id)
        for tid in cfg.tools:
            if not is_registered(tid):
                known = ", ".join(sorted(registered_qualified_ids())) or "<none>"
                raise CapabilityConfigurationError(
                    f"Capability '{cap_id}' references unknown tool '{tid}' in config.toml. "
                    f"Registered tools: {known}."
                )


def load_capabilities(settings: Settings) -> dict[str, CapabilityModule]:
    bootstrap_tool_registry()
    enabled = resolve_enabled_capability_names(settings)
    if not enabled:
        raise CapabilityConfigurationError("No capability packages found under vossploee.capabilities.")
    _validate_tool_allowlists(enabled)
    return {name: load_capability(name, settings) for name in enabled}


def capability_info(capability_id: str) -> CapabilityInfo:
    raw = read_capability_readme_text(capability_id)
    parsed = parse_capability_readme(raw, capability_id)
    cfg = load_capability_settings(capability_id)
    return CapabilityInfo(
        id=capability_id,
        title=parsed.title,
        description=parsed.description,
        functionality=parsed.functionality,
        readme_markdown=parsed.raw_markdown,
        model_override=cfg.model,
        tools=list(cfg.tools),
    )


def list_capability_infos(settings: Settings) -> list[CapabilityInfo]:
    return [capability_info(name) for name in resolve_enabled_capability_names(settings)]


def decomposer_capability_catalog_text(infos: list[CapabilityInfo]) -> str:
    lines: list[str] = []
    for info in infos:
        lines.append(f"- id: `{info.id}`")
        lines.append(f"  title: {info.title}")
        if info.description:
            lines.append(f"  description: {info.description}")
        if info.functionality:
            lines.append(f"  functionality: {info.functionality}")
        lines.append("")
    return "\n".join(lines).strip()


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
