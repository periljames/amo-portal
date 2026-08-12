from __future__ import annotations

from fastapi.routing import APIRoute

from amodb.apps.doc_control.router import router


REGISTER_PATH = "/doc-control/workspace/t/{tenant_slug}/controlled-copies"
EVENT_PATH = "/doc-control/workspace/t/{tenant_slug}/controlled-copies/{copy_id}/events"


def _post_routes(path: str) -> list[APIRoute]:
    return [
        route
        for route in router.routes
        if isinstance(route, APIRoute)
        and route.path == path
        and "POST" in (route.methods or set())
    ]


def test_guarded_controlled_copy_mutations_are_authoritative() -> None:
    register_routes = _post_routes(REGISTER_PATH)
    event_routes = _post_routes(EVENT_PATH)

    assert len(register_routes) == 1, [route.endpoint.__name__ for route in register_routes]
    assert register_routes[0].endpoint.__name__ == "register_controlled_copy"

    assert len(event_routes) == 1, [route.endpoint.__name__ for route in event_routes]
    assert event_routes[0].endpoint.__name__ == "create_guarded_copy_event"
