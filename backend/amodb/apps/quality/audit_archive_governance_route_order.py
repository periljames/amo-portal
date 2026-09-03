from __future__ import annotations

from . import audit_archive_governance_models as _audit_archive_governance_models  # noqa: F401
from . import audit_archive_governance_router
from . import audit_archive_package_router
from .canonical_router import router
from .route_ordering import promote_route_family


def _is_archive_governance_route(route_item) -> bool:
    path = str(getattr(route_item, "path", ""))
    return (
        "/audit-retention-policy" in path
        or ("/audits/" in path and "/archive-governance" in path)
        or ("/audits/" in path and "/archive-manifests" in path)
        or ("/audits/" in path and "/legal-holds/" in path)
    ) and ("/quality/" in path or "/qms/" in path)


router.include_router(audit_archive_governance_router.router)
router.include_router(audit_archive_package_router.router)
promote_route_family(router, predicate=_is_archive_governance_route, label="QMS audit archive governance")
