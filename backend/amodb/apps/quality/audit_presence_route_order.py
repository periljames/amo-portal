from __future__ import annotations

from . import audit_presence_models as _audit_presence_models  # noqa: F401
from . import audit_presence_router
from .canonical_router import router
from .router import public_router as quality_public_router


for api_router in (router,):
    if not any("/presence" in str(getattr(item, "path", "")) and "/audits/" in str(getattr(item, "path", "")) for item in api_router.routes):
        api_router.include_router(audit_presence_router.router)

if not any("/quality/audit-access/presence/heartbeat" in str(getattr(item, "path", "")) for item in quality_public_router.routes):
    quality_public_router.include_router(audit_presence_router.public_router)
