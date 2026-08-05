from fastapi.routing import APIRoute

from amodb.apps.accounts import router_admin, router_public


def _contracts(router) -> set[tuple[str, str]]:
    return {
        (route.path, method)
        for route in router.routes
        if isinstance(route, APIRoute)
        for method in (route.methods or set())
    }


def test_reporting_public_route_contract_is_registered() -> None:
    contracts = _contracts(router_public.router)
    expected = {
        ("/auth/organization/reporting/workspace", "GET"),
        ("/auth/organization/reporting/manager/chains", "POST"),
        ("/auth/organization/reporting/manager/assignments", "POST"),
        ("/auth/organization/reporting/manager/assignments/{assignment_id}", "PATCH"),
        ("/auth/organization/reporting/manager/assignments/{assignment_id}/end", "POST"),
        ("/auth/organization/reporting/manager/assignments/{assignment_id}/transfer", "POST"),
        ("/auth/organization/reporting/manager/title-preferences/{preference_id}/decision", "POST"),
        ("/auth/organization/reporting/my-title", "GET"),
        ("/auth/organization/reporting/my-title", "PUT"),
        ("/auth/organization/reporting/my-title/clear", "POST"),
    }
    assert expected <= contracts


def test_reporting_admin_route_contract_is_registered() -> None:
    contracts = _contracts(router_admin.router)
    expected = {
        ("/accounts/admin/organization/reporting/chains", "POST"),
        ("/accounts/admin/organization/reporting/assignments", "POST"),
        ("/accounts/admin/organization/reporting/assignments/{assignment_id}", "PATCH"),
        ("/accounts/admin/organization/reporting/assignments/{assignment_id}/end", "POST"),
        ("/accounts/admin/organization/reporting/assignments/{assignment_id}/transfer", "POST"),
        ("/accounts/admin/organization/reporting/title-preferences/{preference_id}/decision", "POST"),
    }
    assert expected <= contracts
