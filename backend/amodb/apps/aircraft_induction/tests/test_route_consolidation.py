from amodb.apps.fleet import router as fleet_router_module
from amodb.apps.fleet.usage_guard_router import router as aircraft_control_router


def route_paths(router):
    return {str(getattr(route, "path", "")) for route in router.routes}


def test_universal_induction_is_the_only_aircraft_onboarding_api():
    all_paths = route_paths(aircraft_control_router) | route_paths(fleet_router_module.router)

    assert any(path.startswith("/aircraft/induction") or path.startswith("/induction") for path in all_paths)
    retired_fragments = ("/import", "/ocr", "/snapshots", "/reconciliation")
    retired_paths = [
        path for path in all_paths
        if not path.startswith("/aircraft/induction")
        and any(fragment in path.lower() for fragment in retired_fragments)
    ]
    assert retired_paths == []


def test_direct_usage_mutation_remains_blocked():
    paths = route_paths(aircraft_control_router)
    assert "/aircraft/usage/{usage_id}" in paths or "/usage/{usage_id}" in paths
