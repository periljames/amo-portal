"""Compatibility router for the controlled Publications module.

The original Manuals API remains intact in ``router_legacy``.  New reader-only
endpoints are composed here so existing integrations keep their stable
``/manuals`` API contract while the user-facing module is renamed Publications.
"""
from __future__ import annotations

from fastapi import APIRouter

from . import router_legacy as _legacy
from .publications_router import router as _publications_router


router = APIRouter()
router.include_router(_legacy.router)
router.include_router(_publications_router)


def __getattr__(name: str):
    """Preserve imports of helpers/constants from the historical router module."""
    return getattr(_legacy, name)


__all__ = ["router"]
