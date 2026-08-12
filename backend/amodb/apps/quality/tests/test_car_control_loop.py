from __future__ import annotations

from datetime import date, timedelta
from types import SimpleNamespace
from unittest.mock import patch

from amodb.apps.quality.car_control_loop import closure_readiness, compute_car_health


def _milestone(
    key: str,
    due: date,
    *,
    status: str = "IN_PROGRESS",
    owner: str | None = "user-1",
    evidence_ref: str | None = None,
) -> dict[str, object]:
    return {
        "milestone_key": key,
        "current_due_date": due,
        "status": status,
        "owner_user_id": owner,
        "evidence_ref": evidence_ref,
    }


def _complete_milestones(today: date) -> list[dict[str, object]]:
    return [
        _milestone("RCA_SUBMISSION", today, status="ACCEPTED"),
        _milestone("CAP_APPROVAL", today, status="ACCEPTED"),
        _milestone("IMPLEMENTATION_COMPLETE", today, status="COMPLETED"),
        _milestone("EVIDENCE_COMPLETE", today, status="COMPLETED", evidence_ref="evidence://closure"),
        _milestone("EFFECTIVENESS_REVIEW", today, status="ACCEPTED", evidence_ref="evidence://effectiveness"),
    ]


def test_health_is_deterministic_and_healthy_when_controls_are_clear() -> None:
    today = date(2026, 8, 11)
    health = compute_car_health(
        today=today,
        car_status="IN_PROGRESS",
        final_due_date=today + timedelta(days=30),
        accountable_owner_user_id="user-1",
        milestones=[
            _milestone("RCA_SUBMISSION", today + timedelta(days=15)),
            _milestone("CAP_APPROVAL", today + timedelta(days=20)),
            _milestone("IMPLEMENTATION_COMPLETE", today + timedelta(days=24)),
            _milestone("EVIDENCE_COMPLETE", today + timedelta(days=27)),
            _milestone("EFFECTIVENESS_REVIEW", today + timedelta(days=30)),
        ],
        dependencies=[],
    )

    assert health.state == "HEALTHY"
    assert health.risk_score == 0
    assert health.days_to_final_due == 30
    assert health.factors == ()


def test_health_surfaces_missing_owner_and_due_soon_milestone() -> None:
    today = date(2026, 8, 11)
    health = compute_car_health(
        today=today,
        car_status="OPEN",
        final_due_date=today + timedelta(days=12),
        accountable_owner_user_id=None,
        milestones=[_milestone("RCA_SUBMISSION", today + timedelta(days=2), owner=None)],
        dependencies=[],
    )

    assert health.state == "AT_RISK"
    assert health.risk_score >= 50
    codes = {factor["code"] for factor in health.factors}
    assert "ACCOUNTABLE_OWNER_MISSING" in codes
    assert "MILESTONE_OWNER_MISSING" in codes
    assert "MILESTONE_DUE_IMMINENT" in codes


def test_health_escalates_old_overdue_milestone_to_critical() -> None:
    today = date(2026, 8, 11)
    health = compute_car_health(
        today=today,
        car_status="ESCALATED",
        final_due_date=today - timedelta(days=9),
        accountable_owner_user_id="user-1",
        milestones=[_milestone("IMPLEMENTATION_COMPLETE", today - timedelta(days=10))],
        dependencies=[],
    )

    assert health.state == "CRITICAL"
    assert health.risk_score >= 80
    assert any(factor["code"] == "MILESTONE_OVERDUE" for factor in health.factors)


def test_critical_dependency_drives_critical_health() -> None:
    today = date(2026, 8, 11)
    health = compute_car_health(
        today=today,
        car_status="IN_PROGRESS",
        final_due_date=today + timedelta(days=30),
        accountable_owner_user_id="user-1",
        milestones=[],
        dependencies=[
            {
                "id": "dep-1",
                "title": "Regulator approval",
                "status": "OPEN",
                "risk_level": "CRITICAL",
                "blocks_closure": True,
            }
        ],
    )

    assert health.state == "CRITICAL"
    assert any(factor["code"] == "OPEN_DEPENDENCY" for factor in health.factors)


def test_closure_readiness_accepts_complete_control_chain() -> None:
    today = date(2026, 8, 11)
    readiness = closure_readiness(
        milestones=_complete_milestones(today),
        dependencies=[],
        effectiveness_required=True,
    )
    assert readiness == {"ready": True, "blockers": []}


def test_closure_readiness_blocks_missing_evidence_and_open_dependency() -> None:
    today = date(2026, 8, 11)
    milestones = _complete_milestones(today)
    milestones[-1]["evidence_ref"] = None
    readiness = closure_readiness(
        milestones=milestones,
        dependencies=[
            {
                "id": "dep-1",
                "title": "Facility modification",
                "status": "MITIGATING",
                "risk_level": "HIGH",
                "blocks_closure": True,
            }
        ],
        effectiveness_required=True,
    )

    assert readiness["ready"] is False
    codes = {blocker["code"] for blocker in readiness["blockers"]}
    assert "MILESTONE_EVIDENCE_MISSING" in codes
    assert "BLOCKING_DEPENDENCY_OPEN" in codes


def test_effectiveness_milestone_can_be_optional_by_governed_profile() -> None:
    today = date(2026, 8, 11)
    milestones = _complete_milestones(today)[:-1]
    readiness = closure_readiness(
        milestones=milestones,
        dependencies=[],
        effectiveness_required=False,
    )
    assert readiness["ready"] is True


def test_nullable_owner_payloads_distinguish_omitted_from_explicit_clear() -> None:
    from amodb.apps.quality.car_control_loop_router import ControlLoopInitialize, ControlProfileUpdate, MilestoneUpdate

    assert "accountable_owner_user_id" not in ControlLoopInitialize(effectiveness_required=True).model_fields_set
    assert "accountable_owner_user_id" in ControlLoopInitialize(accountable_owner_user_id=None, effectiveness_required=True).model_fields_set
    assert "accountable_owner_user_id" not in ControlProfileUpdate().model_fields_set
    assert "accountable_owner_user_id" in ControlProfileUpdate(accountable_owner_user_id=None).model_fields_set
    assert "owner_user_id" not in MilestoneUpdate().model_fields_set
    assert "owner_user_id" in MilestoneUpdate(owner_user_id=None).model_fields_set


def test_car_invite_accepts_detailed_quality_response() -> None:
    from amodb.apps.quality.schemas import CARInviteUpdate

    detailed = "x" * 8000
    payload = CARInviteUpdate(
        containment_action=detailed,
        root_cause=detailed,
        corrective_action=detailed,
        preventive_action=detailed,
    )
    assert len(payload.root_cause or "") == 8000
    assert len(payload.corrective_action or "") == 8000


def test_public_invite_persistence_preserves_full_detailed_response() -> None:
    from amodb.apps.quality.public_invite_extensions import _persist_detailed_response_fields
    from amodb.apps.quality.schemas import CARInviteUpdate

    detailed = "x" * 8000
    payload = CARInviteUpdate(
        containment_action=detailed,
        root_cause=detailed,
        corrective_action=detailed,
        preventive_action=detailed,
    )
    car = SimpleNamespace(
        containment_action=None,
        root_cause=None,
        corrective_action=None,
        preventive_action=None,
    )

    _persist_detailed_response_fields(car, payload)

    assert len(car.containment_action) == 8000
    assert len(car.root_cause) == 8000
    assert len(car.corrective_action) == 8000
    assert len(car.preventive_action) == 8000


def test_authoritative_deadline_sync_updates_both_dates_and_reminders() -> None:
    from amodb.apps.quality.car_control_loop_guard_router import _synchronize_authoritative_car_deadline

    old_due = date(2026, 8, 20)
    approved_due = date(2026, 9, 5)
    car = SimpleNamespace(due_date=old_due, target_closure_date=old_due)
    db = object()

    with patch("amodb.apps.quality.router._seed_car_reminders") as seed_reminders:
        _synchronize_authoritative_car_deadline(
            db,
            car=car,
            approved_due_date=approved_due,
        )

    assert car.due_date == approved_due
    assert car.target_closure_date == approved_due
    seed_reminders.assert_called_once_with(db, car)
