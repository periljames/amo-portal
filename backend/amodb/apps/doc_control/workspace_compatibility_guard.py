from __future__ import annotations

from fastapi import APIRouter, HTTPException, Request
from fastapi.routing import APIRoute


_LEGACY_COPY_MUTATION_PATHS = {
    "/workspace/t/{tenant_slug}/controlled-copies",
    "/workspace/t/{tenant_slug}/controlled-copies/{copy_id}/events",
}


def quarantine_legacy_copy_mutations(router: APIRouter) -> None:
    """Remove duplicate compatibility mutations superseded by guarded copy routes.

    The compatibility workspace router predates the physical-library workflow and
    still exposes the same POST paths with older request/transition semantics.
    Keeping both registrations allows route-order drift to send shelf registration
    through the legacy schema, which incorrectly requires a custodian and records
    a shelf copy as issued.  The dedicated workspace_copy_router is authoritative
    for these mutations; compatibility read routes remain untouched.
    """

    router.routes[:] = [
        route
        for route in router.routes
        if not (
            isinstance(route, APIRoute)
            and route.path in _LEGACY_COPY_MUTATION_PATHS
            and "POST" in (route.methods or set())
        )
    ]


def quarantine_legacy_core_mutations(router: APIRouter) -> None:
    """Replace the parallel legacy issuer with explicit retirement responses.

    The canonical workspace owns document registration, revision approval,
    publication, temporary revisions, distribution and acknowledgements.  The
    older root-level API persists a different model and must not remain a second
    writable source of truth.  Its GET routes stay available during migration.
    """

    retired: list[tuple[str, set[str]]] = []
    retained: list[object] = []
    prefix = str(router.prefix or "")
    for route in router.routes:
        methods = set(getattr(route, "methods", set()) or set())
        mutation_methods = methods.intersection({"POST", "PUT", "PATCH", "DELETE"})
        if isinstance(route, APIRoute) and mutation_methods:
            path = route.path[len(prefix):] if prefix and route.path.startswith(prefix) else route.path
            retired.append((path or "/", mutation_methods))
            continue
        retained.append(route)
    router.routes[:] = retained

    async def legacy_mutation_retired(request: Request):
        raise HTTPException(
            status_code=410,
            detail={
                "code": "DOCUMENT_CONTROL_LEGACY_MUTATION_RETIRED",
                "message": "This legacy Document Control write path is retired. Use the tenant-scoped Document Control workspace.",
                "method": request.method,
            },
        )

    for index, (path, methods) in enumerate(retired):
        router.add_api_route(
            path,
            legacy_mutation_retired,
            methods=sorted(methods),
            include_in_schema=False,
            name=f"retired_document_control_mutation_{index}",
        )
