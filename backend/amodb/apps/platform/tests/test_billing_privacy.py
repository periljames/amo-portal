from __future__ import annotations

from types import SimpleNamespace

import pytest
from fastapi import HTTPException
from fastapi.routing import APIRoute

from amodb.apps.accounts import billing_auth, models as account_models, router_billing
from amodb.apps.platform.module_commerce_router import router as module_commerce_router
from amodb.apps.platform.module_subscription_router import router as module_subscription_router
from amodb.apps.platform.module_payment_status_router import router as module_payment_status_router


def _user(role: account_models.AccountRole, *, superuser: bool = False):
    return SimpleNamespace(
        id="user-1",
        amo_id="amo-1" if not superuser else None,
        role=role,
        is_superuser=superuser,
        is_system_account=False,
    )


def _dependency_calls(route: APIRoute):
    return {item.call for item in route.dependant.dependencies}


def test_access_status_remains_available_without_exposing_invoices() -> None:
    access_route = next(
        route for route in router_billing.router.routes
        if isinstance(route, APIRoute) and route.path == "/billing/access-status"
    )
    invoice_route = next(
        route for route in router_billing.router.routes
        if isinstance(route, APIRoute) and route.path == "/billing/invoices" and "GET" in (route.methods or set())
    )
    assert billing_auth.require_authenticated_user in _dependency_calls(access_route)
    assert billing_auth.require_billing_reader not in _dependency_calls(access_route)
    assert billing_auth.require_billing_reader in _dependency_calls(invoice_route)


def test_finance_roles_can_read_billing_records() -> None:
    for role in (
        account_models.AccountRole.AMO_ADMIN,
        account_models.AccountRole.FINANCE_MANAGER,
        account_models.AccountRole.ACCOUNTS_OFFICER,
    ):
        assert billing_auth.require_billing_reader(_user(role)).role == role


def test_non_finance_tenant_role_cannot_read_commercial_records() -> None:
    with pytest.raises(HTTPException) as error:
        billing_auth.require_billing_reader(_user(account_models.AccountRole.QUALITY_MANAGER))
    assert error.value.status_code == 403


def test_accounts_officer_can_settle_but_cannot_bind_recurring_contract() -> None:
    accounts = _user(account_models.AccountRole.ACCOUNTS_OFFICER)
    assert billing_auth.require_billing_reader(accounts) is accounts
    with pytest.raises(HTTPException) as error:
        billing_auth.require_contract_manager(accounts)
    assert error.value.status_code == 403


def test_contract_routes_declare_authority_directly() -> None:
    subscribe = next(
        route for route in module_commerce_router.routes
        if isinstance(route, APIRoute) and route.path.endswith("/commerce/self-service/subscribe")
    )
    cancel = next(
        route for route in module_subscription_router.routes
        if isinstance(route, APIRoute) and route.path.endswith("/commerce/self-service/modules/{module_code}/cancel")
    )
    payment_status = next(
        route for route in module_payment_status_router.routes
        if isinstance(route, APIRoute) and "/commerce/self-service/payment-jobs/" in route.path
    )
    assert billing_auth.require_contract_manager in _dependency_calls(subscribe)
    assert billing_auth.require_contract_manager in _dependency_calls(cancel)
    assert billing_auth.require_billing_reader in _dependency_calls(payment_status)


def test_obsolete_billing_mutations_and_generic_webhook_do_not_exist() -> None:
    paths = {route.path for route in router_billing.router.routes if isinstance(route, APIRoute)}
    for retired in {
        "/billing/catalog",
        "/billing/catalog/{sku_id}",
        "/billing/subscription",
        "/billing/payment-methods",
        "/billing/payment-methods/{payment_method_id}",
        "/billing/trial",
        "/billing/purchase",
        "/billing/cancel",
        "/billing/audit-events",
        "/billing/webhooks/{provider}",
    }:
        assert retired not in paths
