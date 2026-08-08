"""Platform control-plane package for global and tenant SaaS operations."""

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
from .commercial_accounting import install_accounting_summary_policy
from .commercial_safety_policy import install_commercial_safety_policy
from .commercial_invoice_policy import install_invoice_accounting_policy
from .commercial_fiscal_document_policy import install_fiscal_document_policy
from .module_activation_policy import install_module_activation_policy
from .module_offer_policy import install_module_offer_policy
from .module_product_boundary_policy import install_module_product_boundary_policy
from .module_catalog_runtime_policy import install_module_catalog_runtime_policy
from .payment_data_policy import install_payment_data_policy
from .payment_transport_policy import install_payment_transport_policy
from .commercial_policy import install_commercial_control_policy
from .router import router


_saas_services.record_stripe_webhook = _saas_webhooks.record_stripe_webhook

install_tenant_provider_override_policy()
install_fiscalization_enqueue_policy()
install_saas_execution_policy()
install_tenant_admin_links()
install_provider_network_hardening()
install_resend_email_provider()
install_commercial_integrations()
install_accounting_summary_policy()
install_commercial_safety_policy()
install_payment_data_policy()
install_payment_transport_policy()
install_module_product_boundary_policy()
install_module_catalog_runtime_policy()
install_invoice_accounting_policy()
install_fiscal_document_policy()
install_module_offer_policy()
install_module_activation_policy()
install_commercial_control_policy()

from .console_router import router as console_router  # noqa: E402
from .saas_router import platform_saas_router, support_router, webhook_router  # noqa: E402
from .tenant_saas_router import router as tenant_saas_router  # noqa: E402
from . import tenant_saas_job_router as _tenant_saas_job_router  # noqa: E402
from .metrics_lifecycle import install_platform_metrics_lifecycle  # noqa: E402
from .saas_integration import integration_router  # noqa: E402
from .resend_email_router import router as resend_email_router  # noqa: E402
from .commercial_router import router as commercial_router  # noqa: E402
from .module_commerce_router import router as module_commerce_router  # noqa: E402
from .module_subscription_router import router as module_subscription_router  # noqa: E402
from .module_payment_status_router import router as module_payment_status_router  # noqa: E402
from .module_access_router import router as module_access_router  # noqa: E402
from .saas_legacy_bridge import install_legacy_command_queue  # noqa: E402
from .saas_usage import install_usage_meter_hardening  # noqa: E402

router.include_router(console_router)
router.include_router(platform_saas_router)
router.include_router(webhook_router)
router.include_router(support_router)
router.include_router(integration_router)
router.include_router(commercial_router)
router.include_router(module_commerce_router)
router.include_router(module_subscription_router)
router.include_router(module_payment_status_router)
router.include_router(module_access_router)
router.include_router(tenant_saas_router)
router.include_router(_tenant_saas_job_router.router)
router.include_router(resend_email_router)

install_legacy_command_queue()
install_usage_meter_hardening(router)
install_platform_metrics_lifecycle(router)

__all__ = ["router"]
