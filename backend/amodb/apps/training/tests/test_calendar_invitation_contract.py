from __future__ import annotations

from pathlib import Path


ROOT = Path(__file__).resolve().parents[5]


def _source(relative: str) -> str:
    return (ROOT / relative).read_text(encoding="utf-8")


def test_training_calendar_artifact_has_stable_lifecycle_contract() -> None:
    source = _source("backend/amodb/apps/training/workflow_completion.py")
    for contract in (
        '@router.get("/invitations/{invitation_id}/calendar.ics")',
        'f"UID:training-{event.id}@amo-portal"',
        'f"SEQUENCE:{sequence}"',
        'f"METHOD:{method}"',
        'f"STATUS:{ics_status}"',
        'method = "CANCEL" if cancelled else "REQUEST"',
        'ics_status = "CANCELLED" if cancelled else "CONFIRMED"',
    ):
        assert contract in source


def test_invitation_model_persists_rsvp_and_delivery_acknowledgements() -> None:
    source = _source("backend/amodb/apps/training/operating_models.py")
    for contract in (
        'class TrainingSessionInvitation(Base):',
        'delivery_status = Column(String(24), nullable=False, default="QUEUED")',
        'attempt_count = Column(Integer, nullable=False, default=0)',
        'last_error = Column(Text, nullable=True)',
        'rsvp_status = Column(String(24), nullable=False, default="PENDING")',
        'responded_at = Column(DateTime(timezone=True), nullable=True)',
        'sent_at = Column(DateTime(timezone=True), nullable=True)',
        'delivered_at = Column(DateTime(timezone=True), nullable=True)',
        'read_at = Column(DateTime(timezone=True), nullable=True)',
    ):
        assert contract in source


def test_learner_invitation_projection_and_actions_are_mounted() -> None:
    route_source = _source("backend/amodb/apps/training/learner_invitation_routes.py")
    service_source = _source("frontend/src/services/trainingWorkflowCompletion.ts")
    inbox_source = _source("frontend/src/components/training/TrainingInvitationInbox.tsx")
    task_source = _source("frontend/src/components/training/MyTrainingTaskInbox.tsx")
    assert '@router.get("/invitations/me")' in route_source
    assert "TrainingSessionInvitation.amo_id == amo_id" in route_source
    assert "TrainingSessionInvitation.user_id == str(current_user.id)" in route_source
    assert "listMyTrainingInvitations" in service_source
    assert "respondToTrainingInvitation" in service_source
    assert "downloadTrainingInvitationCalendar" in service_source
    assert "Accept" in inbox_source
    assert "Tentative" in inbox_source
    assert "Decline" in inbox_source
    assert "Add to calendar" in inbox_source
    assert "<TrainingInvitationInbox />" in task_source
