from __future__ import annotations

from fastapi import APIRouter

from . import audit_checklist_execution_router
from . import router as quality_api_router
from .canonical_router import router
from .router import (
    _date_to_datetime,
    _ensure_car_for_finding,
    _next_audit_finding_ref,
    _require_audit_fieldwork_write_access,
    _serialize_finding,
    task_services,
)


def _is_execution_route(route_item) -> bool:
    path = str(getattr(route_item, "path", ""))
    return any(
        marker in path
        for marker in (
            "checklist-execution-governance",
            "/execution-governance",
            "/fieldwork-mutations",
            "/fieldwork-findings",
        )
    )


def _is_generic_catchall(route_item) -> bool:
    path = str(getattr(route_item, "path", ""))
    methods = set(getattr(route_item, "methods", None) or ())
    return path.endswith("/{module_path:path}") and bool(methods & {"GET", "POST", "PATCH", "DELETE"})


def _bind_quality_helpers() -> None:
    """Keep lazy fieldwork imports bound to the Quality module contract.

    ``amodb.apps.quality`` exports its primary APIRouter as ``router``. Python's
    ``from . import router`` therefore resolves that package export rather than
    the ``quality.router`` module inside lazy fieldwork paths. Bind the small
    helper surface those paths intentionally reuse so runtime authorization and
    finding creation cannot fail with APIRouter attribute errors.
    """

    helpers = {
        "_require_audit_fieldwork_write_access": _require_audit_fieldwork_write_access,
        "_next_audit_finding_ref": _next_audit_finding_ref,
        "_date_to_datetime": _date_to_datetime,
        "_ensure_car_for_finding": _ensure_car_for_finding,
        "_serialize_finding": _serialize_finding,
        "task_services": task_services,
    }
    for name, value in helpers.items():
        setattr(quality_api_router, name, value)


def _register(api_router: APIRouter) -> None:
    if not any(_is_execution_route(item) for item in api_router.routes):
        api_router.include_router(audit_checklist_execution_router.router)


def _promote(api_router: APIRouter) -> None:
    routes = [item for item in api_router.routes if _is_execution_route(item)]
    if not routes:
        raise RuntimeError("QMS checklist execution governance routes were not registered")
    remaining = [item for item in api_router.routes if not _is_execution_route(item)]
    catchall_index = next((index for index, item in enumerate(remaining) if _is_generic_catchall(item)), len(remaining))
    api_router.routes[:] = [*remaining[:catchall_index], *routes, *remaining[catchall_index:]]


_bind_quality_helpers()
_register(router)
_promote(router)
