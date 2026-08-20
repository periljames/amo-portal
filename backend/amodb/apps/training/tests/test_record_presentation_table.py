from __future__ import annotations

from datetime import date, datetime
from types import SimpleNamespace

from amodb.apps.training import models as training_models
from amodb.apps.training import router as training_router
from amodb.apps.training.record_presentation_table import (
    _decorate_lifecycle_rows,
    _due_tone,
    _training_profile_html,
)


class _Query:
    def __init__(self, rows):
        self.rows = rows

    def filter(self, *args, **kwargs):
        return self

    def order_by(self, *args, **kwargs):
        return self

    def all(self):
        return list(self.rows)


class _FakeDB:
    def __init__(self, *, records, courses):
        self.records = records
        self.courses = courses

    def query(self, *entities):
        entity = entities[0]
        if entity is training_models.TrainingRecord:
            return _Query(self.records)
        if entity is training_models.TrainingCourse:
            return _Query(self.courses)
        if entity is training_models.TrainingFile:
            return _Query([])
        return _Query([])


def _course(*, pk: str, code: str, name: str, kind, group_code: str, active: bool = True, frequency_months=None):
    return SimpleNamespace(
        id=pk,
        amo_id="amo-1",
        course_id=code,
        course_name=name,
        kind=kind,
        status=getattr(kind, "value", str(kind)),
        group_code=group_code,
        prerequisite_course_id=None,
        frequency_months=frequency_months,
        is_active=active,
    )


def _record(*, record_id: str, course_id: str, completed: date, valid_until=None):
    return SimpleNamespace(
        id=record_id,
        amo_id="amo-1",
        user_id="user-1",
        course_id=course_id,
        completion_date=completed,
        valid_until=valid_until,
        created_at=datetime(2026, 8, 4, 8, 0, 0),
        hours_completed=None,
        exam_score=None,
        certificate_reference=None,
    )


def _payload(*, course_name: str, history, next_due: str, status: str = "Current"):
    return {
        "tenant": {"name": "Safarilink Aviation Limited", "brand_accent": "#a7862d"},
        "user": {
            "user_id": "user-1",
            "full_name": "Mercy Etende",
            "position_title": "Procurement Officer",
            "staff_code": "ETEN01",
            "is_active": True,
        },
        "summary": {"current": 1, "completed": 0, "due_soon": 0, "overdue": 0, "deferred": 0},
        "requirements": [{
            "requirement_key": "group:avsec",
            "course_pk": "course-ref",
            "course_id": "AVSEC-REF",
            "course_name": course_name,
            "course_type": "Initial",
            "last_completed": history[0]["completed"],
            "next_due": next_due,
            "scheduled": None,
            "compliance_status": status,
            "history": history,
        }],
    }


def test_initial_completion_keeps_initial_label_but_uses_recurrent_due_date():
    initial = _course(
        pk="course-init",
        code="AVSEC-INIT",
        name="Aviation Security (Initial)",
        kind=training_models.TrainingKind.INITIAL,
        group_code="AVSEC",
    )
    refresher = _course(
        pk="course-ref",
        code="AVSEC-REF",
        name="Aviation Security (Refresher)",
        kind=training_models.TrainingKind.REFRESHER,
        group_code="AVSEC",
        frequency_months=24,
    )
    record = _record(record_id="record-init", course_id="course-init", completed=date(2026, 8, 4))
    payload = _payload(
        course_name="Aviation Security (Refresher)",
        history=[{"record_id": "record-init", "type": "Initial", "completed": "2026-08-04"}],
        next_due="2028-08-04",
    )

    decorated = _decorate_lifecycle_rows(
        _FakeDB(records=[record], courses=[initial, refresher]),
        amo_id="amo-1",
        user_id="user-1",
        payload=payload,
    )
    row = decorated["requirements"][0]

    assert row["course_name"] == "Aviation Security (Initial)"
    assert row["last_completed"] == "2026-08-04"
    assert row["next_due"] == "2028-08-04"
    assert row["has_recurrence"] is True
    assert row["due_tone"] == "current"


def test_table_has_only_course_completed_due_and_certificate_columns_without_codes_or_status_column():
    payload = _payload(
        course_name="Aviation Security (Initial)",
        history=[{"record_id": "record-init", "type": "Initial", "completed": "2026-08-04"}],
        next_due="2028-08-04",
    )
    row = payload["requirements"][0]
    row["has_recurrence"] = True
    row["due_tone"] = "current"
    row["viewer_record_id"] = "record-init"
    row["viewer_label"] = "View certificate"

    body = _training_profile_html(payload).body.decode("utf-8")

    assert "<table class='record-table'>" in body
    assert "<th scope='col'>Course</th>" in body
    assert "<th scope='col'>Completed</th>" in body
    assert "<th scope='col'>Next due</th>" in body
    assert "<th scope='col'>Certificate</th>" in body
    assert "<th scope='col'>Status</th>" not in body
    assert "AVSEC-INIT" not in body
    assert "AVSEC-REF" not in body
    assert "Aviation Security (Initial)" in body
    assert "04 Aug 2026" in body
    assert "04 Aug 2028" in body
    assert "due-date due-current" in body
    assert "class='certificate-icon-button'" in body
    assert "data-record-id='record-init'" in body
    assert "status-pill" not in body.split("</style>", 1)[1]


def test_non_recurrent_course_keeps_normal_due_text_colour():
    row = {"next_due": None, "compliance_status": "Completed", "scheduled": None}
    assert _due_tone(row, has_recurrence=False, discontinued=False) == "neutral"


def test_due_colour_contract_maps_overdue_scheduled_current_and_discontinued():
    assert _due_tone({"next_due": "2026-08-01", "compliance_status": "Overdue"}, has_recurrence=True, discontinued=False) == "overdue"
    assert _due_tone({"next_due": "2026-09-01", "compliance_status": "Current", "scheduled": "2026-08-25"}, has_recurrence=True, discontinued=False) == "scheduled"
    assert _due_tone({"next_due": "2028-08-04", "compliance_status": "Current"}, has_recurrence=True, discontinued=False) == "current"
    assert _due_tone({"next_due": "2028-08-04", "compliance_status": "Current"}, has_recurrence=True, discontinued=True) == "discontinued"


def test_canonical_router_uses_lifecycle_table_renderer():
    assert training_router._training_profile_html is _training_profile_html
