from __future__ import annotations

from .channel import TelegramChannel


def build_channel(settings, app_state):
    return TelegramChannel(settings=settings, app_state=app_state)
