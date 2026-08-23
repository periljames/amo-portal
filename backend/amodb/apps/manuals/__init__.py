"""Controlled Publications package.

Model imports are intentionally lightweight. The FastAPI router is loaded lazily
so Alembic and cross-domain model configuration do not import the complete web
routing graph while SQLAlchemy metadata is still initializing.
"""
from __future__ import annotations

from importlib import import_module
from typing import Any


__all__ = ["router"]


def __getattr__(name: str) -> Any:
    if name == "router":
        return import_module(f"{__name__}.router").router
    if name in {"models", "schemas", "core_router", "publications_router"}:
        return import_module(f"{__name__}.{name}")
    raise AttributeError(name)
