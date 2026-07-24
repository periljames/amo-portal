# backend/amodb/apps/quality/__init__.py
from __future__ import annotations

from fastapi import APIRouter

# Primary Quality API exports.
from .router import router, public_router  # noqa: F401

# Focused extensions are loaded only after the compatibility router is complete.
# Later extensions may intentionally replace narrowly scoped route operations on
# the same exported router objects. Both the full portal and the bounded Quality
# entrypoint therefore receive one authoritative implementation.
from . import audit_file_controls as _audit_file_controls  # noqa: F401,E402
from . import audit_workflow_contract as _audit_workflow_contract  # noqa: F401,E402
from . import public_invite_extensions as _public_invite_extensions  # noqa: F401,E402

# Register ORM metadata before the lifecycle router is imported. The lifecycle
# extension is deliberately loaded last so its workflow, checklist and report
# contracts replace the earlier compatibility handlers.
from . import audit_lifecycle_models as _audit_lifecycle_models  # noqa: F401,E402
from . import audit_lifecycle as _audit_lifecycle  # noqa: F401,E402


def _deduplicate_exact_routes(api_router: APIRouter) -> None:
    """Remove duplicate decorators that register the same endpoint twice.

    Quality's large compatibility router previously contained accidental exact
    duplicates. Preserve legitimately different handlers while collapsing an
    exact path/method/endpoint duplicate after every focused extension is loaded.
    """

    unique_routes = []
    seen: set[tuple[str, frozenset[str], int]] = set()
    for route_item in api_router.routes:
        path = str(getattr(route_item, "path", ""))
        methods = frozenset(getattr(route_item, "methods", None) or ())
        endpoint_marker = id(getattr(route_item, "endpoint", route_item))
        signature = (path, methods, endpoint_marker)
        if signature in seen:
            continue
        seen.add(signature)
        unique_routes.append(route_item)
    api_router.routes[:] = unique_routes


_deduplicate_exact_routes(router)
_deduplicate_exact_routes(public_router)
