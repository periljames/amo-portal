"""Composed router for the controlled Publications module.

Core Manuals routes and focused reader routes are composed here under the stable
``/manuals`` API contract used by Publications.
"""
from __future__ import annotations

from fastapi import APIRouter, Depends
from fastapi.routing import APIRoute
from fastapi.dependencies.utils import get_parameterless_sub_dependant

# Bind hardened indexer, hierarchy, signature, and retained-record implementations
# before reader/workspace modules import stable knowledge-service callables.
from amodb.apps.doc_control import knowledge_runtime as _knowledge_runtime  # noqa: F401
from amodb.apps.doc_control.knowledge_access_router import publication_tree_router

from . import core_router as _core
from .tenant_route_guard import (
    require_manuals_tenant_access,
    require_manuals_record_access,
    require_manuals_export_access,
)
from amodb.apps.doc_control.workspace_service import require_control_user as _require_control_user

# Keep the legacy Manuals intake helper aligned with the canonical Document
# Control authority policy. In particular, a tenant/AMO administrator is a
# control user for document intake, but never gains approval authority merely
# through this bridge.
_core._require_manual_control_user = _require_control_user

from .approved_intake_router import router as _approved_intake_router
from .knowledge_reader_access_router import router as _knowledge_reader_access_router
from .knowledge_reader_router import router as _knowledge_reader_router
from .revision_contract_router import router as _revision_contract_router
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
# Guards, stable revision contracts and precomputed capability routes precede core
# routes because Starlette resolves identical paths in declaration order.
router.include_router(_upload_guard_router)
router.include_router(_revision_contract_router)
router.include_router(_pdf_reader_precomputed_router)
router.include_router(_pdf_reader_form_override_router)
router.include_router(_pdf_reader_router)
router.include_router(_fast_reader_router)
router.include_router(publication_tree_router)
router.include_router(_knowledge_reader_access_router)
router.include_router(_knowledge_reader_router)
router.include_router(_approved_intake_router)
router.include_router(_core.router)
router.include_router(_publications_router)

# Starlette selects the first matching route. Attach this dependency after every
# legacy/modern Manuals router has been composed, but before application mount
# copies these APIRoutes into the main app. This covers aliases and extensions.
for _route in router.routes:
    if not isinstance(_route, APIRoute):
        continue
    _path = str(_route.path)
    _guards = []
    if "{tenant_slug}" in _path:
        _guards.append(require_manuals_tenant_access)
        if "{manual_id}" in _path:
            _guards.append(require_manuals_record_access)
    elif "{export_id}" in _path and _path.startswith("/manuals/exports/"):
        _guards.append(require_manuals_export_access)
    for _guard_function in _guards:
        _guard = Depends(_guard_function)
        _route.dependencies.append(_guard)
        _route.dependant.dependencies.insert(
            0,
            get_parameterless_sub_dependant(depends=_guard, path=_route.path_format),
        )


def __getattr__(name: str):
    """Expose shared helpers/constants from the core router module."""
    return getattr(_core, name)


__all__ = ["router"]