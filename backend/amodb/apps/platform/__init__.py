"""Platform control-plane package for global and tenant SaaS operations."""

# Import the durable SaaS models before FastAPI startup/Alembic mapper checks so
# SQLAlchemy registers every control-plane table in the shared metadata.
from . import saas_models as _saas_models  # noqa: F401
from . import saas_services as _saas_services
from . import saas_webhooks as _saas_webhooks
from .router import router

# Replace the legacy platform-only Stripe verifier before the webhook route is
# imported. The scoped implementation validates tenant endpoint secrets and
# retains the platform credential only as an explicit fallback.
_saas_services.record_stripe_webhook = _saas_webhooks.record_stripe_webhook

from .saas_router import platform_saas_router, support_router, webhook_router  # noqa: E402
from .tenant_saas_router import router as tenant_saas_router  # noqa: E402
from .saas_integration import integration_router  # noqa: E402
from .saas_legacy_bridge import install_legacy_command_queue  # noqa: E402
from .saas_usage import install_usage_meter_hardening  # noqa: E402

# ``amodb.main`` already mounts this package router at /platform. Keeping the
# expansion here preserves one audited top-level control-plane namespace while
# each tenant route applies its own AMO-admin/superuser permission boundary.
router.include_router(platform_saas_router)
router.include_router(webhook_router)
router.include_router(support_router)
router.include_router(integration_router)
router.include_router(tenant_saas_router)

# Existing diagnostics/maintenance endpoints keep their response contracts but
# no longer run low/medium work inside the HTTP request.
install_legacy_command_queue()

# Usage aggregation remains batched per API worker, but database increments are
# atomic across workers and failed batches are restored before the next flush.
install_usage_meter_hardening(router)

__all__ = ["router"]
