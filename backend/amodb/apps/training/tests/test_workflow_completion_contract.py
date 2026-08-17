from __future__ import annotations

from pathlib import Path

from amodb.apps.training import models


ROOT = Path(__file__).resolve().parents[5]


def _source(relative: str) -> str:
    return (ROOT / relative).read_text(encoding="utf-8")


def test_governed_state_values_are_first_class() -> None:
    assert models.DeferralStatus.RETURNED_FOR_INFORMATION.value == "RETURNED_FOR_INFORMATION"
    assert models.DeferralStatus.EXPIRED.value == "EXPIRED"
    assert models.TrainingFileReviewStatus.RETURNED.value == "RETURNED"
    assert models.TrainingParticipantStatus.WAITLISTED.value == "WAITLISTED"


def test_evidence_upload_never_self_approves_and_self_review_is_blocked() -> None:
    source = _source("backend/amodb/apps/training/router.py")
    assert "auto_approved = False" in source
    assert "Training evidence must be reviewed by someone other than the learner/uploader." in source
    assert "Returned evidence requires a reviewer comment" in source


def test_deferral_return_resubmit_risk_replacement_and_expiry_contracts_exist() -> None:
    source = _source("backend/amodb/apps/training/workflow_completion.py")
    for contract in (
        '"RETURNED_FOR_INFORMATION"',
        '"/deferrals/{deferral_id}/resubmit"',
        '"risk_level"',
        '"risk_summary"',
        '"operational_justification"',
        '"replacement_event_id"',
        '"expired_at"',
        '"DEFERRAL_CONTROL"',
    ):
        assert contract in source


def test_evidence_resubmission_is_immutable_and_lineaged() -> None:
    source = _source("backend/amodb/apps/training/workflow_completion.py")
    assert '"/files/{file_id}/resubmit-link"' in source
    assert '"supersedes_file_id"' in source
    assert '"replacement_file_id"' in source
    assert "Replacement evidence must be a new immutable file." in source


def test_p1_programme_routes_extend_existing_training_domain() -> None:
    source = _source("backend/amodb/apps/training/workflow_completion.py")
    for route in (
        '"/external-learning/requests"',
        '"/invitations/{invitation_id}/calendar.ics"',
        '"/assessments/{assessment_id}/attempt/start"',
        '"/assessments/{assessment_id}/attempt/autosave"',
        '"/assessments/{assessment_id}/appeal"',
        '"/ojt/logs"',
        '"/authorization-cases/{case_id}/readiness/explain"',
        '"/authorization-cases/{case_id}/renewal"',
        '"/events/{event_id}/conflicts"',
        '"/events/{event_id}/enrol"',
        '"/events/{event_id}/waitlist/promote"',
        '"/workspace/manager"',
        '"/workspace/coordinator"',
    ):
        assert route in source


def test_external_learning_returned_request_cannot_skip_resubmission() -> None:
    source = _source("backend/amodb/apps/training/workflow_completion.py")
    assert '"RESUBMIT_REQUEST"' in source
    assert 'data["return_stage"] = "COMPLETION" if prior == "COMPLETION_SUBMITTED" else "REQUEST"' in source
    assert 'prior == "RETURNED" and data.get("return_stage") == "COMPLETION"' in source


def test_notification_worker_runs_deferral_and_evidence_escalations() -> None:
    source = _source("backend/amodb/jobs/training_notification_automation.py")
    assert "run_workflow_escalations" in source
    assert 'summary[f"workflow_{key}"]' in source


def test_learner_action_centre_is_mounted_in_my_training() -> None:
    page = _source("frontend/src/pages/MyTrainingPage.tsx")
    component = _source("frontend/src/components/training/TrainingLearnerActionCentre.tsx")
    assert "TrainingLearnerActionCentre" in page
    assert "<TrainingLearnerActionCentre />" in page
    assert "Resubmit deferral" in component
    assert "Submit replacement evidence" in component
    assert "Request external learning" in component
    assert "Record OJT / supervised experience" in component
