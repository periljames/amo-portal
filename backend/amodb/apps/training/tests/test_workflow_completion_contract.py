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


def test_notification_delivery_is_durable_and_provider_state_is_separate() -> None:
    dispatch = _source("backend/amodb/apps/training/notification_dispatch.py")
    worker = _source("backend/amodb/jobs/training_notification_automation.py")
    for state in ("QUEUED", "SENDING", "SENT", "RETRY_SCHEDULED", "FAILED"):
        assert state in dispatch
    assert "provider_message_id" in dispatch
    assert "attempt_count" in dispatch
    assert "next_attempt_at" in dispatch
    assert "sync_notifications_to_outbox" in worker
    assert "process_outbox" in worker


def test_learner_self_service_routes_are_tenant_and_subject_scoped() -> None:
    source = _source("backend/amodb/apps/training/learner_workflow_routes.py")
    assert '@router.get("/assessments/me")' in source
    assert "TrainingAssessmentInstance.amo_id == amo_id" in source
    assert "TrainingAssessmentInstance.candidate_user_id == str(current_user.id)" in source
    assert '@router.get("/authorization-cases/me")' in source
    assert "TrainingAuthorizationCase.candidate_user_id == str(current_user.id)" in source
    assert '@router.post("/invitations/{invitation_id}/rsvp")' in source
    assert "TrainingSessionInvitation.user_id == str(current_user.id)" in source
    assert "TrainingParticipantStatus.CONFIRMED" in source
    assert "TrainingParticipantStatus.CANCELLED" in source
    assert "TrainingParticipantStatus.INVITED" in source


def test_learner_assessment_projection_never_exposes_answer_keys() -> None:
    source = _source("backend/amodb/apps/training/learner_workflow_routes.py")
    assert "_safe_assessment_payload" in source
    assert '"question_text"' in source
    assert '"answer_options"' in source
    assert '"answer_key"' not in source


def test_manager_workspace_is_role_guarded_and_coordinator_is_editor_guarded() -> None:
    source = _source("backend/amodb/apps/training/workflow_completion.py")
    assert "Management permission is required for Team Training." in source
    assert "if coordinator:\n            _training_editor(router_module, current_user)" in source


def test_learner_and_reviewer_workflow_surfaces_are_reachable() -> None:
    page = _source("frontend/src/pages/MyTrainingPage.tsx")
    action_centre = _source("frontend/src/components/training/TrainingLearnerActionCentre.tsx")
    task_inbox = _source("frontend/src/components/training/MyTrainingTaskInbox.tsx")
    invitation_inbox = _source("frontend/src/components/training/TrainingInvitationInbox.tsx")
    session_self_service = _source("frontend/src/components/training/TrainingSessionSelfService.tsx")
    reviewer = _source("frontend/src/components/training/TrainingExternalLearningReview.tsx")
    workflow_workspace = _source("frontend/src/components/training/TrainingWorkflowWorkspace.tsx")
    service = _source("frontend/src/services/trainingWorkflowCompletion.ts")
    assert "TrainingLearnerActionCentre" in page
    assert "<TrainingLearnerActionCentre />" in page
    for label in (
        "Resubmit deferral",
        "Submit replacement evidence",
        "Request external learning",
        "Record OJT / supervised experience",
        "Assessments & examinations",
        "Authorization readiness & renewal posture",
    ):
        assert label in action_centre
    assert "TrainingInvitationInbox" in task_inbox
    assert "TrainingSessionSelfService" in task_inbox
    assert "TrainingRoleWorkspacePanel" in task_inbox
    assert "Add to calendar" in invitation_inbox
    assert "Check & enrol" in session_self_service
    assert "governed waitlist" in session_self_service
    assert "External learning approvals" in reviewer
    assert "VERIFY_COMPLETION" in reviewer
    assert "TrainingExternalLearningReview" in workflow_workspace
    assert "/training/assessments/me" in service
    assert "/training/authorization-cases/me" in service
    assert "/training/invitations/${encodeURIComponent(invitationId)}/rsvp" in service
