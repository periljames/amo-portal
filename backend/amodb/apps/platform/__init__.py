"""Platform control-plane package for global SaaS superadmin operations."""

# Import the durable SaaS models before FastAPI startup/Alembic mapper checks so
# SQLAlchemy registers every control-plane table in the shared metadata.
from . import saas_models as _saas_models  # noqa: F401
from .router import router
from .saas_router import platform_saas_router, support_router, webhook_router

# ``amodb.main`` already mounts this package router at /platform. Keeping the
# expansion here avoids a second top-level router and preserves one audited
# platform permission boundary.
router.include_router(platform_saas_router)
router.include_router(webhook_router)
router.include_router(support_router)

__all__ = ["router"]
