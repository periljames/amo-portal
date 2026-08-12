from __future__ import annotations

from datetime import date, timedelta
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import MagicMock, patch

import pytest
from fastapi import HTTPException

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


def test_low_risk_nonblocking_dependency_becomes_overdue_when_its_due_date_passes() -> None:
    today = date(2026, 8, 11)
    health = compute_car_health(
        today=today,
        car_status="IN_PROGRESS",
        final_due_date=today + timedelta(days=30),
        accountable_owner_user_id="user-1",
        milestones=[],
        dependencies=[
            {
                "id": "dep-low",
                "title": "Purchase order response",
                "status": "OPEN",
                "risk_level": "LOW",
                "blocks_closure": False,
                "due_date": today - timedelta(days=2),
            }
        ],
    )

    assert health.state == "OVERDUE"
    overdue = next(factor for factor in health.factors if factor["code"] == "DEPENDENCY_OVERDUE")
    assert overdue["dependency_id"] == "dep-low"
    assert overdue["overdue_days"] == 2


def test_health_ignores_disabled_effectiveness_milestone() -> None:
    today = date(2026, 8, 11)
    effectiveness = SimpleNamespace(
        milestone_key="EFFECTIVENESS_REVIEW",
        current_due_date=today - timedelta(days=10),
        status="PLANNED",
        owner_user_id="user-1",
        evidence_ref=None,
        profile=SimpleNamespace(effectiveness_required=False),
    )

    health = compute_car_health(
        today=today,
        car_status="IN_PROGRESS",
        final_due_date=today + timedelta(days=30),
        accountable_owner_user_id="user-1",
        milestones=[effectiveness],
        dependencies=[],
    )

    assert health.state == "HEALTHY"
    assert not any(factor.get("milestone_key") == "EFFECTIVENESS_REVIEW" for factor in health.factors)


def test_closure_readiness_accepts_complete_control_chain() -> None:
    today = date(2026, 8, 11)
    readiness = closure_readiness(
        milestones=_complete_milestones(today),
        dependencies=[],
        effectiveness_required=True,
    )
    assert readiness == {"ready": True, "blockers": []}


def test_closure_readiness_requires_explicit_rca_and_cap_acceptance() -> None:
    today = date(2026, 8, 11)
    milestones = _complete_milestones(today)
    milestones[0]["status"] = "COMPLETED"
    milestones[1]["status"] = "WAIVED"

    readiness = closure_readiness(
        milestones=milestones,
        dependencies=[],
        effectiveness_required=True,
    )

    assert readiness["ready"] is False
    blocked_keys = {
        blocker["milestone_key"]
        for blocker in readiness["blockers"]
        if blocker["code"] == "MILESTONE_NOT_ACCEPTED"
    }
    assert blocked_keys == {"RCA_SUBMISSION", "CAP_APPROVAL"}


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


def test_public_invite_report_requires_matching_issued_revision() -> None:
    from amodb.apps.quality.public_invite_extensions import _issued_revision_matches_path

    report_path = Path("/controlled/reports/audit-report.pdf")
    draft = SimpleNamespace(status="DRAFT", file_ref=str(report_path))
    issued = SimpleNamespace(status="ISSUED", file_ref=str(report_path))
    different_issued = SimpleNamespace(status="ISSUED", file_ref="/controlled/reports/other.pdf")

    assert _issued_revision_matches_path(draft, report_path) is False
    assert _issued_revision_matches_path(issued, report_path) is True
    assert _issued_revision_matches_path(different_issued, report_path) is False


def test_public_invite_report_sets_forced_rls_tenant_context() -> None:
    from amodb.apps.quality.public_invite_extensions import _set_public_tenant_context

    db = MagicMock()
    db.get_bind.return_value.dialect.name = "postgresql"

    _set_public_tenant_context(db, amo_id="amo-tenant-1")

    db.execute.assert_called_once()
    _, params = db.execute.call_args.args
    assert params == {"amo_id": "amo-tenant-1"}


def test_sent_reminder_stage_is_archived_before_reseeding_extended_deadline() -> None:
    from amodb.apps.quality.car_control_loop_guard_router import _archive_sent_car_reminders_before_reseed

    old_due = date(2026, 8, 20)
    reminder = SimpleNamespace(
        id="12345678-reminder",
        due_date=old_due,
        milestone_key="CAR_DUE_7_DAYS",
    )
    db = MagicMock()
    db.query.return_value.filter.return_value.all.return_value = [reminder]

    _archive_sent_car_reminders_before_reseed(
        db,
        car=SimpleNamespace(id="car-1", amo_id="amo-1"),
        approved_due_date=date(2026, 9, 5),
    )

    assert reminder.milestone_key.startswith("CAR_DUE_7_DAYS@2026-08-20:12345678")
    db.flush.assert_called_once()


def test_authoritative_deadline_sync_updates_dates_and_rebuilds_pending_reminders() -> None:
    from amodb.apps.quality.car_control_loop_guard_router import _synchronize_authoritative_car_deadline

    old_due = date(2026, 8, 20)
    approved_due = date(2026, 9, 5)
    car = SimpleNamespace(
        id="car-1",
        amo_id="amo-1",
        due_date=old_due,
        target_closure_date=old_due,
    )
    historical_query = MagicMock()
    historical_query.filter.return_value.all.return_value = []
    pending_query = MagicMock()
    db = MagicMock()
    db.query.side_effect = [historical_query, pending_query]

    with patch("amodb.apps.quality.router._seed_car_reminders") as seed_reminders:
        _synchronize_authoritative_car_deadline(
            db,
            car=car,
            approved_due_date=approved_due,
        )

    assert car.due_date == approved_due
    assert car.target_closure_date == approved_due
    pending_query.filter.return_value.delete.assert_called_once_with(synchronize_session=False)
    seed_reminders.assert_called_once_with(db, car)


def test_initial_authoritative_deadline_sets_both_dates_and_reminder_plan() -> None:
    from amodb.apps.quality.car_control_loop_guard_router import _prepare_initial_authoritative_deadline

    initial_due = date(2026, 9, 5)
    car = SimpleNamespace(due_date=None, target_closure_date=None)
    db = MagicMock()

    with patch("amodb.apps.quality.router._seed_car_reminders") as seed_reminders:
        _prepare_initial_authoritative_deadline(
            db,
            car=car,
            final_due_date=initial_due,
        )

    assert car.due_date == initial_due
    assert car.target_closure_date == initial_due
    seed_reminders.assert_called_once_with(db, car)


def test_closure_evidence_reference_is_capped_at_authoritative_car_column() -> None:
    from amodb.apps.quality.car_control_loop_guard_router import _validated_closure_evidence_ref
    from amodb.apps.quality.car_control_loop_router import CloseControlLoop

    accepted = _validated_closure_evidence_ref(
        CloseControlLoop(evidence_ref="x" * 512, closure_reason="Verified complete"),
        [],
    )
    assert len(accepted) == 512

    with pytest.raises(HTTPException) as exc_info:
        _validated_closure_evidence_ref(
            CloseControlLoop(evidence_ref="x" * 513, closure_reason="Verified complete"),
            [],
        )
    assert exc_info.value.status_code == 422
