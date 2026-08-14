from __future__ import annotations

from pathlib import Path

import pytest
from pydantic import ValidationError

from amodb.apps.training import operating_schemas as schemas


TRAINING_DIR = Path(__file__).parents[1]
MIGRATION = TRAINING_DIR.parents[1] / "alembic" / "versions" / "training_20260813_readiness_audit.py"


def test_control_room_supports_unknown_without_false_zero() -> None:
    queue = schemas.ActionQueueItem(
        key="people",
        label="People compliance",
        count=None,
        severity="CRITICAL",
        reason="Source unavailable. This count is Unknown, not zero.",
        action_label="Retry source",
        path="/training/competence/people",
        available=False,
    )
    assert queue.count is None
    assert queue.available is False


def test_setup_supports_all_three_frontend_starting_modes() -> None:
    for mode in ("BLANK", "TEMPLATE_PACK", "WORKBOOK"):
        payload = schemas.SetupVersionCreate(source_mode=mode, title=f"{mode} setup")
        assert payload.source_mode == mode


def test_controlled_workflow_requires_bounded_idempotency_and_known_form_family() -> None:
    payload = schemas.WorkflowInstanceCreate(
        workflow_type="QAM_51_INDUCTION",
        title="Induction for employee 100",
        idempotency_key="induction:employee-100:2026",
        steps=[schemas.WorkflowStepInput(step_key="quality_close", label="Quality completion", sequence_no=1)],
    )
    assert payload.workflow_type == "QAM_51_INDUCTION"
    with pytest.raises(ValidationError):
        schemas.WorkflowInstanceCreate(workflow_type="CUSTOM", title="x", idempotency_key="short")


def test_material_mutations_have_preview_and_independent_decision_contracts() -> None:
    preview = schemas.ChangePreviewCreate(
        object_type="REQUIREMENT",
        operation="BULK_REPLACE",
        requested_payload={"ids": ["requirement-1", "requirement-2"]},
    )
    decision = schemas.ChangeDecision(decision="ACCEPT", reason="Reviewed affected population and source revision.")
    assert preview.object_type == "REQUIREMENT"
    assert decision.decision == "ACCEPT"


def test_invitation_delivery_and_rsvp_states_are_separate() -> None:
    invitation = schemas.InvitationRead(
        id="invitation-1", event_id="event-1", user_id="user-1", channel="EMAIL",
        delivery_status="FAILED", attempt_count=2, last_error="Provider timeout", rsvp_status="PENDING",
        created_at="2026-08-13T12:00:00Z", updated_at="2026-08-13T12:05:00Z",
    )
    assert invitation.delivery_status == "FAILED"
    assert invitation.rsvp_status == "PENDING"


def test_readiness_migration_contains_every_shared_control_table() -> None:
    source = MIGRATION.read_text(encoding="utf-8")
    for table in (
        "training_setup_versions", "training_change_requests", "training_workflow_instances",
        "training_workflow_steps", "training_session_invitations", "training_report_definitions",
        "training_report_jobs", "training_saved_views",
    ):
        assert table in source


def test_operability_routes_are_tenant_scoped_and_capability_guarded() -> None:
    router_source = (TRAINING_DIR / "operating_router.py").read_text(encoding="utf-8")
    service_source = (TRAINING_DIR / "readiness_service.py").read_text(encoding="utf-8")
    assert '"/source-health"' in router_source
    assert '"/people"' in router_source
    assert '"/workflows"' in router_source
    assert '"/report-jobs"' in router_source
    assert "tenant_id_for(current_user)" in router_source
    assert "amo_id=tenant_id_for(actor)" in service_source
    assert "You may respond only to your own invitation" in service_source
    assert "Segregation of duties requires a different user" in service_source


def test_retained_exports_import_history_and_certificate_batches_are_wired() -> None:
    router_source = (TRAINING_DIR / "operating_router.py").read_text(encoding="utf-8")
    workbook_router = (TRAINING_DIR / "workbook_router.py").read_text(encoding="utf-8")
    report_worker = (TRAINING_DIR.parents[1] / "jobs" / "training_report_jobs.py").read_text(encoding="utf-8")
    assert '/report-jobs/{job_id}/download' in router_source
    assert '/certificates/eligibility' in router_source
    assert '/certificates/batch-issue' in router_source
    assert '@router.get("/template")' in workbook_router
    assert 'resolved_artifact_path' in report_worker
    assert 'artifact_checksum' in report_worker
