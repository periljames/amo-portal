from __future__ import annotations

from pathlib import Path


ROOT = Path(__file__).resolve().parents[5]


def _source(relative: str) -> str:
    return (ROOT / relative).read_text(encoding="utf-8")


def test_training_calendar_artifact_has_stable_lifecycle_contract() -> None:
    source = _source("backend/amodb/apps/training/workflow_completion.py")
    for contract in (
        '@router.get("/invitations/{invitation_id}/calendar.ics")',
        'UID:amo-training-{invitation.event_id}@amo-portal',
        'SEQUENCE:{int(invitation.calendar_sequence or 0)}',
        'METHOD:{method}',
        'STATUS:{event_status}',
        'PARTSTAT={partstat}',
        'method = "CANCEL"',
        'event_status = "CANCELLED"',
    ):
        assert contract in source


def test_rsvp_and_calendar_updates_share_invitation_state() -> None:
    source = _source("backend/amodb/apps/training/workflow_completion.py")
    assert 'invitation.rsvp_status = payload.response' in source
    assert 'invitation.calendar_sequence = int(invitation.calendar_sequence or 0) + 1' in source
    assert 'TrainingSessionInvitation' in source
