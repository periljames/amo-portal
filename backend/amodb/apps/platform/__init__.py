"""Platform control-plane package for global and tenant SaaS operations."""

# Import the durable SaaS models before FastAPI startup/Alembic mapper checks so
# SQLAlchemy registers every control-plane table in the shared metadata.
from . import saas_models as _saas_models  # noqa: F401
from . import saas_services as _saas_services
from . import saas_webhooks as _saas_webhooks
from .saas_admin_links import install_tenant_admin_links
from .saas_admin_policy import install_tenant_provider_override_policy
from .saas_execution_policy import install_saas_execution_policy
from .saas_fiscalization_policy import install_fiscalization_enqueue_policy
from .saas_provider_network import install_provider_network_hardening
from .resend_email_policy import install_resend_email_provider
from .commercial_integrations import install_commercial_integrations
from .commercial_policy import install_commercial_control_policy
from .router import router

# Replace the legacy platform-only Stripe verifier before the webhook route is
# imported. The scoped implementation validates tenant endpoint secrets and
# retains the platform credential only when no tenant-specific credential exists.
_saas_services.record_stripe_webhook = _saas_webhooks.record_stripe_webhook

# Enforce credential inheritance, terminal fiscalization, provider execution,
# frontend-link and outbound network rules before superuser or tenant routes
# capture the shared service functions.
install_tenant_provider_override_policy()
install_fiscalization_enqueue_policy()
install_saas_execution_policy()
install_tenant_admin_links()
install_provider_network_hardening()
install_resend_email_provider()
# Commercial adapters are installed after network/provider hardening so Paystack,
# Daraja and QuickBooks inherit the same SSRF and secret-handling boundaries.
install_commercial_integrations()
# Separate administrative tenant state from commercial billing connectivity and
# replace placeholder commercial metrics with auditable subledger-derived values.
install_commercial_control_policy()

from .console_router import router as console_router  # noqa: E402
from .saas_router import platform_saas_router, support_router, webhook_router  # noqa: E402
from .tenant_saas_router import router as tenant_saas_router  # noqa: E402
from . import tenant_saas_job_router as _tenant_saas_job_router  # noqa: E402
from .metrics_lifecycle import install_platform_metrics_lifecycle  # noqa: E402
from .saas_integration import integration_router  # noqa: E402
from .resend_email_router import router as resend_email_router  # noqa: E402
from .commercial_router import router as commercial_router  # noqa: E402
from .saas_legacy_bridge import install_legacy_command_queue  # noqa: E402
from .saas_usage import install_usage_meter_hardening  # noqa: E402

# ``amodb.main`` already mounts this package router at /platform. Keeping the
# expansion here preserves one audited top-level control-plane namespace while
# each tenant route applies its own AMO-admin/superuser permission boundary.
router.include_router(console_router)
router.include_router(platform_saas_router)
router.include_router(webhook_router)
router.include_router(support_router)
router.include_router(integration_router)
router.include_router(commercial_router)
router.include_router(tenant_saas_router)
router.include_router(_tenant_saas_job_router.router)
router.include_router(resend_email_router)

# Existing diagnostics/maintenance endpoints keep their response contracts but
# no longer run low/medium work inside the HTTP request.
install_legacy_command_queue()

# Usage aggregation remains batched per API worker, but database increments are
# atomic across workers and failed batches are restored before the next flush.
install_usage_meter_hardening(router)

# Route latency and request distributions are process-local while requests are
# active. Persist each worker's current bucket on a real lifecycle timer so the
# dashboard combines every worker and the final bucket survives idle periods or
# a graceful restart.
install_platform_metrics_lifecycle(router)

__all__ = ["router"]
