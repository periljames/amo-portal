from __future__ import annotations

from types import SimpleNamespace

from amodb.apps.manuals import revision_contract_router as override
from amodb.apps.manuals.router import router


def test_revision_serializer_handles_enum_without_duplicate_keyword_failure() -> None:
    revision = SimpleNamespace(
        id="revision-1",
        manual_id="manual-1",
        rev_number="2",
        issue_number="1",
        status_enum=SimpleNamespace(value="DRAFT"),
        effective_date=None,
        published_at=None,
        immutable_locked=False,
    )
    payload = override._revision_out(revision)
    assert payload.id == "revision-1"
    assert payload.status_enum == "DRAFT"


def test_revision_contract_routes_precede_core_routes() -> None:
    revisions_path = "/manuals/t/{tenant_slug}/{manual_id}/revisions"
    revision_routes = [
        route
        for route in router.routes
        if getattr(route, "path", None) == revisions_path
        and "GET" in (getattr(route, "methods", None) or set())
    ]
    assert revision_routes
    assert revision_routes[0].endpoint.__module__ == (
        "amodb.apps.manuals.revision_contract_router"
    )

    compare_path = "/manuals/t/{tenant_slug}/{manual_id}/rev/{rev_id}/compare"
    compare_routes = [
        route
        for route in router.routes
        if getattr(route, "path", None) == compare_path
        and "GET" in (getattr(route, "methods", None) or set())
    ]
    assert compare_routes
    assert compare_routes[0].endpoint.__module__ == (
        "amodb.apps.manuals.revision_contract_router"
    )


def test_line_comparison_preserves_add_remove_and_same_evidence() -> None:
    baseline, current = override._line_comparison(
        ["same", "old wording"],
        ["same", "new wording"],
    )
    assert baseline == [
        {"line": "same", "kind": "same"},
        {"line": "old wording", "kind": "removed"},
    ]
    assert current == [
        {"line": "same", "kind": "same"},
        {"line": "new wording", "kind": "added"},
    ]
