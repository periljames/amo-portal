from __future__ import annotations

from fastapi import APIRouter

from . import audit_closing_assurance_models as _audit_closing_assurance_models  # noqa: F401
from . import audit_authority_pack_router
from . import audit_closing_assurance_router
from .canonical_router import router


def _is_core_closing_assurance_route(route_item) -> bool:
    path = str(getattr(route_item, "path", ""))
    return (
        "/audit-output-policy" in path
        or ("/audits/" in path and "/signature-evidence" in path)
        or ("/audits/" in path and "/assurance-artifacts" in path)
    ) and ("/quality/" in path or "/qms/" in path)


def _is_authority_pack_route(route_item) -> bool:
    path = str(getattr(route_item, "path", ""))
    return "/audits/" in path and (
        "/authority-attestation" in path or "/authority-pack" in path
    ) and ("/quality/" in path or "/qms/" in path)


def _is_closing_assurance_route(route_item) -> bool:
    return _is_core_closing_assurance_route(route_item) or _is_authority_pack_route(route_item)


def _is_generic_catchall(route_item) -> bool:
    path = str(getattr(route_item, "path", ""))
    methods = set(getattr(route_item, "methods", None) or ())
    return path.endswith("/{module_path:path}") and bool(methods & {"GET", "POST", "PATCH", "DELETE"})


def _register(api_router: APIRouter) -> None:
    if not any(_is_core_closing_assurance_route(item) for item in api_router.routes):
        api_router.include_router(audit_closing_assurance_router.router)
    if not any(_is_authority_pack_route(item) for item in api_router.routes):
        api_router.include_router(audit_authority_pack_router.router)


def _promote(api_router: APIRouter) -> None:
    routes = [item for item in api_router.routes if _is_closing_assurance_route(item)]
    if not routes:
        raise RuntimeError("QMS audit closing assurance routes were not registered")
    remaining = [item for item in api_router.routes if not _is_closing_assurance_route(item)]
    catchall_index = next(
        (index for index, item in enumerate(remaining) if _is_generic_catchall(item)),
        len(remaining),
    )
    api_router.routes[:] = [*remaining[:catchall_index], *routes, *remaining[catchall_index:]]


for api_router in (router,):
    _register(api_router)
    _promote(api_router)
