"""Compatibility router for the controlled Publications module.

The original Manuals API remains intact in ``router_legacy``. New reader-only
endpoints are composed here so existing integrations keep their stable
``/manuals`` API contract while the user-facing module is renamed Publications.
"""
from __future__ import annotations

from fastapi import APIRouter

# Bind the exact page-native indexer before reader/workspace modules import the
# stable knowledge-service callables.
from amodb.apps.doc_control import knowledge_runtime as _knowledge_runtime  # noqa: F401

from . import router_legacy as _legacy
from .approved_intake_router import router as _approved_intake_router
from .knowledge_reader_router import router as _knowledge_reader_router
from .publications_fast_reader_router import router as _fast_reader_router
from .publications_router import router as _publications_router
from .upload_guard_router import router as _upload_guard_router


router = APIRouter()
# Guards, progressive delivery, and version-aware reference routes must precede
# compatibility routes because Starlette resolves identical paths in declaration
# order. Reader knowledge routes expose only tenant-scoped, access-checked targets.
router.include_router(_upload_guard_router)
router.include_router(_fast_reader_router)
router.include_router(_knowledge_reader_router)
router.include_router(_approved_intake_router)
router.include_router(_legacy.router)
router.include_router(_publications_router)


def __getattr__(name: str):
    """Preserve imports of helpers/constants from the historical router module."""
    return getattr(_legacy, name)


__all__ = ["router"]
