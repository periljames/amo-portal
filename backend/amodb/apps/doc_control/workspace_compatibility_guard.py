from __future__ import annotations

from fastapi import APIRouter
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
