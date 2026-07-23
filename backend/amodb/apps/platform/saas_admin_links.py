from __future__ import annotations

from importlib import import_module
from typing import Any


_INSTALLED = False


def install_tenant_admin_links() -> None:
    """Keep backend-discovered setup links aligned with registered SPA routes."""

    global _INSTALLED
    if _INSTALLED:
        return
    module = import_module("amodb.apps.platform.tenant_saas_router")

    def setup_links(tenant_id: str | None, superuser: bool) -> dict[str, Any]:
        return {
            "stripe_webhook_path": "/platform/saas/webhooks/stripe",
            "tenant_admin_path": "/maintenance/{amoCode}/admin/email-settings",
            "platform_integrations_path": "/platform/integrations" if superuser else None,
            "platform_billing_path": "/platform/billing" if superuser else None,
            "scope_tenant_id": tenant_id,
        }

    module._setup_links = setup_links
    _INSTALLED = True
