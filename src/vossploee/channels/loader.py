from __future__ import annotations

from importlib import import_module
from pkgutil import iter_modules

from vossploee.channels.base import Channel
from vossploee.config import Settings


def list_channel_ids() -> list[str]:
    import vossploee.channels as channels_pkg

    package_path = str(next(iter(channels_pkg.__path__)))
    return sorted(module.name for module in iter_modules([package_path]) if module.ispkg and not module.name.startswith("_"))


def load_channels(settings: Settings, *, app_state: object) -> dict[str, Channel]:
    discovered = list_channel_ids()
    enabled = settings.enabled_channels or discovered
    out: dict[str, Channel] = {}
    for channel_id in enabled:
        module = import_module(f"vossploee.channels.{channel_id}")
        builder = getattr(module, "build_channel")
        channel = builder(settings, app_state)
        out[channel.id] = channel
    return out
