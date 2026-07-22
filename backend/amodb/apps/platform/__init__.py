"""Platform control-plane package for global SaaS superadmin operations."""

# Import the durable SaaS models before FastAPI startup/Alembic mapper checks so
# SQLAlchemy registers every control-plane table in the shared metadata.
from . import saas_models as _saas_models  # noqa: F401
from .router import router
from .saas_router import platform_saas_router, support_router, webhook_router
from .saas_integration import integration_router
from .saas_legacy_bridge import install_legacy_command_queue
from .saas_usage import install_usage_meter_hardening

# ``amodb.main`` already mounts this package router at /platform. Keeping the
# expansion here avoids a second top-level router and preserves one audited
# platform permission boundary.
router.include_router(platform_saas_router)
router.include_router(webhook_router)
router.include_router(support_router)
router.include_router(integration_router)

# Existing diagnostics/maintenance endpoints keep their response contracts but
# no longer run low/medium work inside the HTTP request.
install_legacy_command_queue()

# Usage aggregation remains batched per API worker, but database increments are
# atomic across workers and batch flushing is never performed by a request.
install_usage_meter_hardening(router)

__all__ = ["router"]
