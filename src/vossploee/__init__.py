from __future__ import annotations

from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    from fastapi import FastAPI

    from vossploee.config import Settings


def create_app(settings: "Settings | None" = None) -> "FastAPI":
    from vossploee.main import create_app as _create_app

    return _create_app(settings)


def main() -> None:
    from vossploee.main import main as _main

    _main()


def __getattr__(name: str) -> Any:
    if name == "app":
        from vossploee.main import app as _app

        return _app
    raise AttributeError(f"module {__name__!r} has no attribute {name!r}")


__all__ = ["app", "create_app", "main"]
