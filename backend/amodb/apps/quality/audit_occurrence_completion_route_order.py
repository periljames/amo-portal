from __future__ import annotations

from . import audit_occurrence_completion_models as _audit_occurrence_completion_models  # noqa: F401
from . import audit_occurrence_completion_router
from .canonical_router import legacy_router, router
from .router import public_router as quality_public_router


for api_router in (router, legacy_router):
    if not any("/governed-document-requests" in str(getattr(item, "path", "")) for item in api_router.routes):
        api_router.include_router(audit_occurrence_completion_router.router)

if not any("/quality/audit-access/collaboration" in str(getattr(item, "path", "")) for item in quality_public_router.routes):
    quality_public_router.include_router(audit_occurrence_completion_router.public_router)
