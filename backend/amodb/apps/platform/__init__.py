"""Platform control-plane package for global and tenant SaaS operations."""

import os

# Import durable SaaS and Platform Operations data models before FastAPI
# startup/Alembic mapper checks so SQLAlchemy registers every control-plane table
# in the shared metadata.
from . import saas_models as _saas_models  # noqa: F401
from . import ops_data_models as _ops_data_models  # noqa: F401
from . import saas_services as _saas_services
from . import saas_webhooks as _saas_webhooks
from .saas_admin_links import install_tenant_admin_links
from .saas_admin_policy import install_tenant_provider_override_policy
from .saas_execution_policy import install_saas_execution_policy
from .saas_fiscalization_policy import install_fiscalization_enqueue_policy
from .saas_provider_network import install_provider_network_hardening
from .resend_email_policy import install_resend_email_provider
from .managed_ai_provider_policy import install_managed_ai_provider_policy
from .ai_execution_policy import install_ai_execution_policy
from .router import router

_saas_services.record_stripe_webhook = _saas_webhooks.record_stripe_webhook

install_tenant_provider_override_policy()
install_fiscalization_enqueue_policy()
install_saas_execution_policy()
install_tenant_admin_links()
install_provider_network_hardening()
install_resend_email_provider()
install_managed_ai_provider_policy()
install_ai_execution_policy()

from .ops_console_router import router as console_router  # noqa: E402
from .product_analytics import router as product_analytics_router  # noqa: E402
from .saas_router import platform_saas_router, support_router, webhook_router  # noqa: E402
from .tenant_saas_router import router as tenant_saas_router  # noqa: E402
from . import tenant_saas_job_router as _tenant_saas_job_router  # noqa: E402
from .metrics_lifecycle import install_platform_metrics_lifecycle  # noqa: E402
from .saas_integration import integration_router  # noqa: E402
from .resend_email_router import router as resend_email_router  # noqa: E402
from .command_queue_install import install_command_queue  # noqa: E402
from .saas_usage import install_usage_meter_hardening  # noqa: E402
from .ai_router import router as ai_router  # noqa: E402

router.include_router(console_router)
router.include_router(product_analytics_router)
router.include_router(platform_saas_router)
router.include_router(webhook_router)
router.include_router(support_router)
router.include_router(integration_router)
router.include_router(tenant_saas_router)
router.include_router(_tenant_saas_job_router.router)
router.include_router(resend_email_router)
router.include_router(ai_router)

install_command_queue()
install_usage_meter_hardening(router)
install_platform_metrics_lifecycle(router)

# Fleet, Training and Reliability file-transfer policies belong to the tenant API
# process. The isolated Ops gateway sets this flag false before importing the
# Platform package so its failure domain and import graph remain independent.
if (os.getenv("AMO_INSTALL_SHARED_STORAGE_ROUTE_HARDENING") or "true").strip().lower() in {"1", "true", "yes", "on"}:
    from amodb import storage as _storage  # noqa: E402
    from .storage_route_hardening import install_shared_storage_route_hardening  # noqa: E402

    # Production can explicitly require replica-safe object storage. Validate at
    # tenant-API startup/import instead of discovering a missing bucket on the
    # first upload. Test/Alembic discovery imports deliberately skip this
    # filesystem side effect: dedicated storage tests exercise the same validator
    # explicitly, while CI runners must not need write access to /srv/amo merely
    # to enumerate migrations or collect unrelated tests.
    app_env = (os.getenv("APP_ENV") or "").strip().lower()
    if app_env not in {"test", "testing"}:
        _storage.validate_storage_configuration()
    install_shared_storage_route_hardening()

__all__ = ["router"]
