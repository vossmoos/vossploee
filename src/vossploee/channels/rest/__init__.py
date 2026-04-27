from __future__ import annotations

from .channel import RestChannel


def build_channel(settings, app_state):
    return RestChannel(settings=settings, app_state=app_state)
