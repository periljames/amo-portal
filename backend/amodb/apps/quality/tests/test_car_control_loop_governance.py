from __future__ import annotations

from types import SimpleNamespace
from unittest.mock import MagicMock, patch
from uuid import UUID

import pytest
from fastapi import HTTPException


def test_terminal_car_blocks_governed_deadline_changes() -> None:
    from amodb.apps.quality.car_control_loop_authority_guard import _require_active_control_car

    with pytest.raises(HTTPException) as exc_info:
        _require_active_control_car(SimpleNamespace(status="CLOSED"))
    assert exc_info.value.status_code == 409


def test_deadline_decision_uses_canonical_reviewer_authority() -> None:
    from amodb.apps.quality.car_control_loop_authority_guard import _require_canonical_review_authority

    db = MagicMock()
    reviewer = SimpleNamespace(id="user-1", is_active=True)
    db.query.return_value.filter.return_value.first.return_value = reviewer
    ctx = SimpleNamespace(user_id="user-1", amo_id="amo-1")
    car = SimpleNamespace(id="car-1")

    with patch("amodb.apps.quality.router._require_car_review_access") as review_gate:
        _require_canonical_review_authority(db, ctx=ctx, car=car)

    review_gate.assert_called_once_with(db, reviewer, car)


def test_attachment_delete_clears_all_matching_milestone_evidence_refs() -> None:
    from amodb.apps.quality.car_control_loop_evidence_guard import _clear_attachment_milestone_references

    attachment_id = UUID("00000000-0000-0000-0000-000000000123")
    matching = f"car-attachment:{attachment_id}:evidence.pdf"
    keep = "controlled-document:abc"
    first = SimpleNamespace(evidence_ref=f"{matching}; {keep}")
    second = SimpleNamespace(evidence_ref=matching)
    untouched = SimpleNamespace(evidence_ref="external-evidence:xyz")

    db = MagicMock()
    db.query.return_value.filter.return_value.with_for_update.return_value.all.return_value = [first, second, untouched]

    changed = _clear_attachment_milestone_references(
        db,
        amo_id="amo-1",
        car_id=UUID("00000000-0000-0000-0000-000000000001"),
        attachment_id=attachment_id,
    )

    assert changed == 2
    assert first.evidence_ref == keep
    assert second.evidence_ref is None
    assert untouched.evidence_ref == "external-evidence:xyz"


def test_control_loop_evidence_requires_manage_permission() -> None:
    from amodb.apps.quality import car_control_loop_evidence_guard as evidence

    db = MagicMock()
    ctx = SimpleNamespace(amo_id="amo-1", user_id="user-1")

    with (
        patch.object(evidence, "assert_quality_permission") as permission_gate,
        patch.object(evidence, "set_persistent_control_loop_context") as context_gate,
    ):
        evidence._assert_evidence_manage(db, ctx)

    permission_gate.assert_called_once_with(db, ctx, "qms.car.manage")
    context_gate.assert_called_once_with(db, amo_id="amo-1", user_id="user-1")


def _registered_endpoint(api_router, *, suffix: str, method: str):
    matches = [
        route_item
        for route_item in api_router.routes
        if str(getattr(route_item, "path", "")).endswith(suffix)
        and method in set(getattr(route_item, "methods", None) or ())
    ]
    assert len(matches) == 1, [
        (
            str(getattr(route_item, "path", "")),
            sorted(getattr(route_item, "methods", None) or ()),
            getattr(getattr(route_item, "endpoint", None), "__name__", None),
        )
        for route_item in matches
    ]
    return matches[0].endpoint


@pytest.mark.parametrize("router_name", ["router"])
def test_registered_control_loop_routes_use_strict_authority_and_evidence_handlers(router_name: str) -> None:
    from amodb.apps.quality import canonical_router
    from amodb.apps.quality import car_control_loop_authority_guard as authority
    from amodb.apps.quality import car_control_loop_evidence_guard as evidence

    api_router = getattr(canonical_router, router_name)

    assert _registered_endpoint(
        api_router,
        suffix="/cars/{car_id}/control-loop/milestones/{milestone_id}",
        method="PATCH",
    ) is authority.update_milestone_with_review_authority
    assert _registered_endpoint(
        api_router,
        suffix="/cars/{car_id}/control-loop/deadline-changes/{change_id}/decision",
        method="POST",
    ) is authority.decide_deadline_change_with_review_authority
    assert _registered_endpoint(
        api_router,
        suffix="/cars/{car_id}/control-loop/close",
        method="POST",
    ) is authority.close_control_loop_with_close_authority
    assert _registered_endpoint(
        api_router,
        suffix="/cars/{car_id}/control-loop/attachments",
        method="GET",
    ) is evidence.list_control_loop_attachments
    assert _registered_endpoint(
        api_router,
        suffix="/cars/{car_id}/control-loop/attachments",
        method="POST",
    ) is evidence.upload_control_loop_attachment
    assert _registered_endpoint(
        api_router,
        suffix="/cars/{car_id}/control-loop/attachments/{attachment_id}",
        method="DELETE",
    ) is evidence.delete_control_loop_attachment


def test_control_loop_routers_use_persistent_post_commit_tenant_context() -> None:
    from amodb.apps.quality import car_control_loop_guard_router, car_control_loop_router
    from amodb.apps.quality.car_control_loop_session_context import set_persistent_control_loop_context

    assert car_control_loop_router.set_postgres_tenant_context is set_persistent_control_loop_context
    assert car_control_loop_guard_router.set_postgres_tenant_context is set_persistent_control_loop_context
