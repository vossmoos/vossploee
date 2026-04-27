from __future__ import annotations

from .channel import EmailChannel


def build_channel(settings, app_state):
    return EmailChannel(settings=settings, app_state=app_state)
