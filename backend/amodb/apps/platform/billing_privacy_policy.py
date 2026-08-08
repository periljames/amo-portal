from __future__ import annotations

from fastapi import Depends, HTTPException, status
from fastapi.dependencies.utils import get_parameterless_sub_dependant
from fastapi.routing import APIRoute

from amodb.apps.accounts import models as account_models
from amodb.security import get_current_active_user


BILLING_READER_ROLES = {
    account_models.AccountRole.AMO_ADMIN,
    account_models.AccountRole.FINANCE_MANAGER,
    account_models.AccountRole.ACCOUNTS_OFFICER,
}
CONTRACT_MANAGER_ROLES = {
    account_models.AccountRole.AMO_ADMIN,
    account_models.AccountRole.FINANCE_MANAGER,
}


def require_tenant_billing_reader(current_user=Depends(get_current_active_user)):
    if getattr(current_user, "is_system_account", False):
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="System accounts cannot access tenant billing records.")
    if getattr(current_user, "is_superuser", False):
        return current_user
    if not getattr(current_user, "amo_id", None):
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Tenant billing context is required.")
    if getattr(current_user, "role", None) not in BILLING_READER_ROLES:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="AMO administrator or finance billing role is required to view commercial billing records.",
        )
    return current_user


def require_tenant_contract_manager(current_user=Depends(get_current_active_user)):
    user = require_tenant_billing_reader(current_user)
    if getattr(user, "is_superuser", False):
        return user
    if getattr(user, "role", None) not in CONTRACT_MANAGER_ROLES:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="AMO administrator or finance manager authority is required to accept or cancel recurring module contracts.",
        )
    return user


def reject_legacy_generic_payment_webhook() -> None:
    raise HTTPException(
        status_code=status.HTTP_410_GONE,
        detail=(
            "The generic billing webhook endpoint is retired. Use the provider-specific "
            "verified Stripe, Paystack or M-PESA webhook endpoint."
        ),
    )


def _attach(route: APIRoute, dependency) -> None:
    if any(item.call is dependency for item in route.dependant.dependencies):
        return
    depends = Depends(dependency)
    route.dependencies.append(depends)
    route.dependant.dependencies.insert(
        0,
        get_parameterless_sub_dependant(depends=depends, path=route.path_format),
    )


def _financial_account_route(path: str) -> bool:
    return bool(
        path.startswith("/billing/invoices")
        or path.startswith("/billing/payment-methods")
        or path in {"/billing/purchase", "/billing/trial", "/billing/cancel"}
    )


def install_billing_privacy_policy(
    *,
    module_commerce_router=None,
    module_subscription_router=None,
    module_payment_status_router=None,
) -> None:
    """Apply least-privilege access to commercial records and mutations.

    `/billing/access-status` deliberately remains readable by every authenticated
    tenant user so a locked technician can understand that the account requires
    billing action without seeing invoices, prices, payment references or contract
    terms. All commercial-detail routes require a billing role.
    """
    from amodb.apps.accounts import router_billing

    for route in router_billing.router.routes:
        if not isinstance(route, APIRoute):
            continue
        if route.path == "/billing/webhooks/{provider}":
            # This old catch-all endpoint accepted arbitrary JSON and cannot meet
            # the provider-specific signature/minimization guarantees. Retire it
            # before request-body parsing; the dedicated payment-provider routes
            # are the only supported payment ingress.
            _attach(route, reject_legacy_generic_payment_webhook)
        elif _financial_account_route(route.path):
            _attach(route, require_tenant_billing_reader)

    if module_commerce_router is not None:
        for route in module_commerce_router.routes:
            if not isinstance(route, APIRoute):
                continue
            path = route.path
            if "/commerce/self-service/subscribe" in path:
                _attach(route, require_tenant_contract_manager)
            elif "/commerce/self-service/" in path:
                _attach(route, require_tenant_billing_reader)

    if module_subscription_router is not None:
        for route in module_subscription_router.routes:
            if isinstance(route, APIRoute):
                _attach(route, require_tenant_contract_manager)

    if module_payment_status_router is not None:
        for route in module_payment_status_router.routes:
            if isinstance(route, APIRoute):
                _attach(route, require_tenant_billing_reader)
