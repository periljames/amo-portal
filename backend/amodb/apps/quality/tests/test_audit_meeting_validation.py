from datetime import date, datetime, time, timezone
from types import SimpleNamespace
from zoneinfo import ZoneInfo

import pytest
from fastapi import HTTPException

from amodb.apps.quality.audit_meeting_validation import validate_meeting_timeline


def audit():
    return SimpleNamespace(planned_start=date(2026, 9, 22), planned_end=date(2026, 9, 22),
                           planned_start_time=time(9), planned_end_time=time(17))


@pytest.mark.parametrize("kind,start,end", [
    ("CLOSING", "2026-09-09T14:00", "2026-09-09T15:00"),
    ("OPENING", "2026-09-22T07:00", "2026-09-22T08:00"),
    ("OPENING", "2026-09-22T05:00", "2026-09-22T05:00"),
])
def test_invalid_chronology_is_rejected(kind, start, end):
    with pytest.raises(HTTPException) as error:
        validate_meeting_timeline(audit(), kind, datetime.fromisoformat(start).replace(tzinfo=timezone.utc),
                                  datetime.fromisoformat(end).replace(tzinfo=timezone.utc), ZoneInfo("Africa/Nairobi"))
    assert error.value.status_code == 422


@pytest.mark.parametrize("kind,start,end", [
    ("OPENING", "2026-09-22T05:00", "2026-09-22T06:00"),
    ("CLOSING", "2026-09-22T14:00", "2026-09-22T15:00"),
])
def test_valid_tenant_local_boundary(kind, start, end):
    validate_meeting_timeline(audit(), kind, datetime.fromisoformat(start).replace(tzinfo=timezone.utc),
                              datetime.fromisoformat(end).replace(tzinfo=timezone.utc), ZoneInfo("Africa/Nairobi"))


def test_saved_team_id_is_not_enough_for_setup_readiness(monkeypatch):
    from amodb.apps.quality.audit_workflow_contract import _audit_setup_ready
    from amodb.apps.quality import audit_occurrence_assignment_router as assignments
    row = audit()
    row.scope = "Saved scope"
    row.criteria = "Saved criteria"
    row.auditee = "Representative"
    row.lead_auditor_user_id = "lead"
    row.observer_auditor_user_id = None
    row.assistant_auditor_user_id = None
    row.amo_id = "tenant"
    monkeypatch.setattr(assignments, "_evaluate", lambda *args, **kwargs: {"eligible": False})
    assert _audit_setup_ready(row, object()) is False
    monkeypatch.setattr(assignments, "_evaluate", lambda *args, **kwargs: {"eligible": True})
    assert _audit_setup_ready(row, object()) is True
