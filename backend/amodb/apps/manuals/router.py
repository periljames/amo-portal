"""Compatibility router for the controlled Publications module.

The original Manuals API remains intact in ``router_legacy``. New reader-only
endpoints are composed here so existing integrations keep their stable
``/manuals`` API contract while the user-facing module is renamed Publications.
"""
from __future__ import annotations

from fastapi import APIRouter

# Bind hardened indexer, hierarchy, signature, and retained-record implementations
# before reader/workspace modules import stable knowledge-service callables.
from amodb.apps.doc_control import knowledge_runtime as _knowledge_runtime  # noqa: F401
from amodb.apps.doc_control.knowledge_access_router import publication_tree_router

from . import router_legacy as _legacy
from .approved_intake_router import router as _approved_intake_router
from .knowledge_reader_access_router import router as _knowledge_reader_access_router
from .knowledge_reader_router import router as _knowledge_reader_router
from .legacy_contract_override_router import router as _legacy_contract_override_router
from .pdf_reader_form_override_router import router as _pdf_reader_form_override_router
from .pdf_reader_precomputed_router import router as _pdf_reader_precomputed_router
from .pdf_reader_router import router as _pdf_reader_router
from .publications_fast_reader_router import router as _fast_reader_router
from .publications_router import router as _publications_router
from .upload_guard_router import router as _upload_guard_router


# These are narrow replacements for endpoints owned by pdf_reader_router. Preserve
# that public ownership marker for route-contract diagnostics and integrations that
# inspect the mounted endpoint module.
for _route in _pdf_reader_form_override_router.routes:
    if getattr(_route, "endpoint", None) is not None:
        _route.endpoint.__module__ = "amodb.apps.manuals.pdf_reader_router"


router = APIRouter()
# Guards, stable legacy-contract overrides and precomputed capability routes precede
# compatibility routes because Starlette resolves identical paths in declaration
# order. The legacy router remains mounted for endpoints that are not replaced.
router.include_router(_upload_guard_router)
router.include_router(_legacy_contract_override_router)
router.include_router(_pdf_reader_precomputed_router)
router.include_router(_pdf_reader_form_override_router)
router.include_router(_pdf_reader_router)
router.include_router(_fast_reader_router)
router.include_router(publication_tree_router)
router.include_router(_knowledge_reader_access_router)
router.include_router(_knowledge_reader_router)
router.include_router(_approved_intake_router)
router.include_router(_legacy.router)
router.include_router(_publications_router)


def __getattr__(name: str):
    """Preserve imports of helpers/constants from the historical router module."""
    return getattr(_legacy, name)


__all__ = ["router"]
