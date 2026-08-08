from __future__ import annotations

from datetime import datetime, timezone
from types import SimpleNamespace

import pytest
from fastapi import HTTPException

from amodb.database import Base
from amodb.apps.quality import canonical_router
from amodb.apps.quality.mission_lifecycle_guard_router import assert_mission_actor_allowed
from amodb.apps.quality.mission_router import (
    CAPABILITY_ADDITION_GATE_TEMPLATE,
    MissionDecisionCreate,
    assert_mission_decision_allowed,
    mission_readiness,
    router as mission_router,
)


def _route_methods(router):
    return {
        (str(route.path), method)
        for route in router.routes
        for method in (getattr(route, "methods", None) or set())
    }


def _matching_routes(router, path: str, method: str):
    return [
        route
        for route in router.routes
        if str(route.path) == path and method in (getattr(route, "methods", None) or set())
    ]


def _catchall_index(router) -> int:
    return next(
        index
        for index, route in enumerate(router.routes)
        if str(route.path).endswith("/{module_path:path}")
    )


def _gate(code: str, *, status: str = "PENDING", gate_type: str = "HARD", evidence_status: str = "UNLINKED"):
    return SimpleNamespace(
        id=code.lower(),
        gate_code=code,
        title=code.replace("_", " ").title(),
        status=status,
        gate_type=gate_type,
        evidence_status=evidence_status,
        blocking_reason=None,
    )


def _decision(decision_type: str, status: str):
    now = datetime.now(timezone.utc)
    return SimpleNamespace(
        decision_type=decision_type,
        status=status,
        decided_at=now,
        created_at=now,
    )


def _mission(*, gates=None, decisions=None, owner_user_id="quality-owner", sponsor_user_id="accountable-executive"):
    return SimpleNamespace(
        gates=list(gates or []),
        decisions=list(decisions or []),
        owner_user_id=owner_user_id,
        sponsor_user_id=sponsor_user_id,
    )


def test_mission_router_exposes_bounded_governed_contract() -> None:
    methods = _route_methods(mission_router)
    assert {
        ("/missions/templates", "GET"),
        ("/missions", "GET"),
        ("/missions", "POST"),
        ("/missions/{mission_id}", "GET"),
        ("/missions/{mission_id}/gates/{gate_id}", "PATCH"),
        ("/missions/{mission_id}/decisions", "POST"),
    }.issubset(methods)


def test_mission_routes_are_promoted_before_generic_quality_catchall() -> None:
    cases = (
        (canonical_router.router, "/api/maintenance/{amo_code}/quality"),
        (canonical_router.legacy_router, "/api/maintenance/{amo_code}/qms"),
    )
    for router, prefix in cases:
        list_path = f"{prefix}/missions"
        list_matches = _matching_routes(router, list_path, "GET")
        assert len(list_matches) == 1
        assert list_matches[0].endpoint.__name__ == "list_missions"
        assert router.routes.index(list_matches[0]) < _catchall_index(router)

        decision_path = f"{prefix}/missions/{{mission_id}}/decisions"
        decision_matches = _matching_routes(router, decision_path, "POST")
        assert len(decision_matches) == 1
        assert decision_matches[0].endpoint.__name__ == "record_governed_mission_decision"
        assert router.routes.index(decision_matches[0]) < _catchall_index(router)


def test_mission_models_are_registered_in_shared_metadata() -> None:
    assert "quality_missions" in Base.metadata.tables
    assert "quality_mission_gates" in Base.metadata.tables
    assert "quality_mission_decisions" in Base.metadata.tables


def test_capability_addition_template_is_complete_and_has_unique_hard_gates() -> None:
    codes = [item["gate_code"] for item in CAPABILITY_ADDITION_GATE_TEMPLATE]
    assert len(codes) == len(set(codes))
    assert codes == [
        "APPROVAL_RATING",
        "FACILITIES",
        "TECHNICAL_DATA",
        "TOOLING",
        "MATERIALS",
        "PERSONNEL",
        "TRAINING",
        "PROCEDURES",
        "CONTRACTED_FUNCTIONS",
        "MANPOWER",
        "SAFETY_CHANGE_ASSESSMENT",
    ]
    assert all(item["source_owner_module"] for item in CAPABILITY_ADDITION_GATE_TEMPLATE)
    assert all(item["source_type"] for item in CAPABILITY_ADDITION_GATE_TEMPLATE)


def test_readiness_never_averages_away_failed_hard_gate() -> None:
    gates = [
        _gate("FACILITIES", status="PASS", evidence_status="VERIFIED"),
        _gate("TOOLING", status="FAIL", evidence_status="VERIFIED"),
        _gate("DOCUMENTATION", status="PASS", gate_type="SOFT", evidence_status="VERIFIED"),
    ]
    result = mission_readiness(gates)
    assert result["hard_gates"] == {"passed": 1, "total": 2}
    assert result["soft_gates"] == {"passed": 1, "total": 1}
    assert result["ready_for_quality_self_evaluation"] is False
    assert [item["gate_code"] for item in result["blocking_gates"]] == ["TOOLING"]


def test_quality_self_evaluation_cannot_approve_with_open_hard_gate() -> None:
    mission = _mission(
        gates=[
            _gate("FACILITIES", status="PASS", evidence_status="VERIFIED"),
            _gate("TOOLING", status="PENDING"),
        ]
    )
    with pytest.raises(HTTPException) as exc:
        assert_mission_decision_allowed(
            mission,
            MissionDecisionCreate(
                decision_type="QUALITY_SELF_EVALUATION",
                status="APPROVED",
                rationale="Ready for internal approval.",
            ),
        )
    assert exc.value.status_code == 409
    assert "HARD readiness gate" in str(exc.value.detail)


def test_accountable_executive_cannot_approve_before_quality_self_evaluation() -> None:
    mission = _mission(gates=[_gate("FACILITIES", status="PASS", evidence_status="VERIFIED")])
    with pytest.raises(HTTPException) as exc:
        assert_mission_decision_allowed(
            mission,
            MissionDecisionCreate(
                decision_type="ACCOUNTABLE_EXECUTIVE",
                status="APPROVED",
                rationale="Approve capability addition.",
            ),
        )
    assert exc.value.status_code == 409
    assert "Quality self-evaluation" in str(exc.value.detail)


def test_accountable_executive_decision_requires_named_sponsor() -> None:
    payload = MissionDecisionCreate(
        decision_type="ACCOUNTABLE_EXECUTIVE",
        status="APPROVED",
        rationale="Approve capability addition.",
    )
    with pytest.raises(HTTPException) as missing:
        assert_mission_actor_allowed(_mission(sponsor_user_id=None), payload, "accountable-executive")
    assert missing.value.status_code == 409

    with pytest.raises(HTTPException) as wrong_actor:
        assert_mission_actor_allowed(_mission(), payload, "quality-owner")
    assert wrong_actor.value.status_code == 403

    assert_mission_actor_allowed(_mission(), payload, "accountable-executive")


def test_quality_and_authority_workflow_decisions_require_named_mission_owner() -> None:
    payload = MissionDecisionCreate(
        decision_type="QUALITY_SELF_EVALUATION",
        status="APPROVED",
        rationale="Quality self-evaluation approved.",
    )
    with pytest.raises(HTTPException) as wrong_actor:
        assert_mission_actor_allowed(_mission(), payload, "amo-admin")
    assert wrong_actor.value.status_code == 403
    assert_mission_actor_allowed(_mission(), payload, "quality-owner")


def test_authority_submission_requires_accountable_executive_approval() -> None:
    mission = _mission(
        gates=[_gate("FACILITIES", status="PASS", evidence_status="VERIFIED")],
        decisions=[_decision("QUALITY_SELF_EVALUATION", "APPROVED")],
    )
    with pytest.raises(HTTPException) as exc:
        assert_mission_decision_allowed(
            mission,
            MissionDecisionCreate(
                decision_type="AUTHORITY_SUBMISSION",
                status="APPROVED",
                rationale="Submit approved change to the authority.",
            ),
        )
    assert exc.value.status_code == 409
    assert "Accountable Executive approval" in str(exc.value.detail)


def test_authority_acceptance_requires_recorded_submission_decision() -> None:
    mission = _mission(
        gates=[_gate("FACILITIES", status="PASS", evidence_status="VERIFIED")],
        decisions=[
            _decision("QUALITY_SELF_EVALUATION", "APPROVED"),
            _decision("ACCOUNTABLE_EXECUTIVE", "APPROVED"),
        ],
    )
    with pytest.raises(HTTPException) as exc:
        assert_mission_decision_allowed(
            mission,
            MissionDecisionCreate(
                decision_type="AUTHORITY_ACCEPTANCE",
                status="APPROVED",
                rationale="Authority acceptance recorded.",
            ),
        )
    assert exc.value.status_code == 409
    assert "Authority submission decision" in str(exc.value.detail)


def test_full_governed_decision_chain_is_allowed_when_prerequisites_exist() -> None:
    mission = _mission(
        gates=[
            _gate("FACILITIES", status="PASS", evidence_status="VERIFIED"),
            _gate("TOOLING", status="PASS", evidence_status="VERIFIED"),
        ],
        decisions=[
            _decision("QUALITY_SELF_EVALUATION", "APPROVED"),
            _decision("ACCOUNTABLE_EXECUTIVE", "APPROVED"),
            _decision("AUTHORITY_SUBMISSION", "APPROVED"),
        ],
    )
    assert_mission_decision_allowed(
        mission,
        MissionDecisionCreate(
            decision_type="AUTHORITY_ACCEPTANCE",
            status="APPROVED",
            rationale="Authority acceptance recorded from the governed source.",
        ),
    )
