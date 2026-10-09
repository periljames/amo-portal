from __future__ import annotations

from fastapi import APIRouter

from . import audit_preparation_context_router
from .canonical_router import router
from .route_ordering import promote_route_family


def _is_context_route(route_item) -> bool:
    return str(getattr(route_item, "path", "")).endswith("/audits/{audit_id}/preparation-context")


def _register(api_router: APIRouter) -> None:
    if not any(_is_context_route(item) for item in api_router.routes):
        api_router.include_router(audit_preparation_context_router.router)


def _promote(api_router: APIRouter) -> None:
    promote_route_family(api_router, predicate=_is_context_route, label="QMS audit preparation context")


for api_router in (router,):
    _register(api_router)
    _promote(api_router)
