from __future__ import annotations

import json
from types import SimpleNamespace

from amodb.apps.accounts import models as accounts_models
from amodb.apps.training import models as training_models
from amodb.apps.training import record_presentation


class _Query:
    def __init__(self, value):
        self.value = value

    def filter(self, *args, **kwargs):
        return self

    def first(self):
        return self.value


class _FakeDB:
    def __init__(self, user):
        self.user = user

    def query(self, model):
        if model is accounts_models.User:
            return _Query(self.user)
        return _Query(None)


def _course(*, pk: str, code: str, kind, group_code: str | None = None, prerequisite: str | None = None):
    return SimpleNamespace(
        id=pk,
        course_id=code,
        course_name=code,
        kind=kind,
        status=getattr(kind, "value", str(kind)),
        group_code=group_code,
        prerequisite_course_id=prerequisite,
        frequency_months=24 if kind != training_models.TrainingKind.INITIAL else None,
    )


def test_public_payload_masks_personnel_pii_before_serialization(monkeypatch):
    amo = SimpleNamespace(name="Example Aviation", contact_email="quality@example.test", contact_phone="+254700000000")
    user = SimpleNamespace(id="user-1", amo=amo, amo_id="amo-1")
    db = _FakeDB(user)

    monkeypatch.setattr(record_presentation, "_build_requirement_rows", lambda *args, **kwargs: [])

    def original_payload(*args, **kwargs):
        return {
            "user": {
                "full_name": "James Example",
                "email": "jamesmuisyo99@gmail.com",
                "phone": "+254719199733",
                "staff_code": "ETEN01",
            },
            "records": [{"record_id": "historical-peer-row"}],
        }

    payload = record_presentation._augment_public_payload(
        original_payload,
        db,
        amo_id="amo-1",
        user_id="user-1",
    )

    serialized = json.dumps(payload)
    assert "jamesmuisyo99@gmail.com" not in serialized
    assert "+254719199733" not in serialized
    assert payload["user"]["email"] == "j***99@gmail.com"
    assert payload["user"]["phone"] == "+254 719 *** 733"
    assert "records" not in payload
    # Formal verification identifiers remain complete unless policy explicitly
    # requires masking; they are not cosmetically masked in client-side CSS.
    assert payload["user"]["staff_code"] == "ETEN01"


def test_record_scoped_public_grant_preserves_non_requirement_completion(monkeypatch):
    amo = SimpleNamespace(name="Example Aviation", contact_email="quality@example.test", contact_phone="+254700000000")
    user = SimpleNamespace(id="user-1", amo=amo, amo_id="amo-1")
    db = _FakeDB(user)

    monkeypatch.setattr(record_presentation, "_build_requirement_rows", lambda *args, **kwargs: [])

    def original_payload(*args, **kwargs):
        return {
            "user": {"full_name": "James Example", "staff_code": "ETEN01"},
            "records": [
                {
                    "record_id": "record-optional-1",
                    "course_id": "EXT-CRM",
                    "course_name": "External CRM Workshop",
                    "completion_date": "2026-08-01",
                    "valid_until": None,
                    "certificate_reference": "CRM-2026-22",
                    "verification_status": "VERIFIED",
                },
                {
                    "record_id": "peer-record",
                    "course_id": "HF-REC",
                    "course_name": "Human Factors Recurrent",
                    "completion_date": "2026-07-01",
                    "valid_until": "2028-07-01",
                    "verification_status": "VERIFIED",
                },
            ],
        }

    payload = record_presentation._augment_public_payload(
        original_payload,
        db,
        amo_id="amo-1",
        user_id="user-1",
        record_id="record-optional-1",
    )

    assert "records" not in payload
    assert len(payload["requirements"]) == 1
    requirement = payload["requirements"][0]
    assert requirement["requirement_key"] == "record:record-optional-1"
    assert requirement["course_id"] == "EXT-CRM"
    assert requirement["compliance_status"] == "Completed"
    assert [item["record_id"] for item in requirement["history"]] == ["record-optional-1"]
    assert "peer-record" not in json.dumps(payload)


def test_requirement_summary_groups_only_explicit_course_relationships():
    initial = _course(pk="a", code="HF-INIT", kind=training_models.TrainingKind.INITIAL, group_code="HF")
    recurrent = _course(pk="b", code="HF-REF", kind=training_models.TrainingKind.REFRESHER, group_code="HF")
    unrelated = _course(pk="c", code="SMS-REF", kind=training_models.TrainingKind.RECURRENT)
    course_by_id = {course.id: course for course in (initial, recurrent, unrelated)}

    items = [
        SimpleNamespace(course_id="HF-INIT", status="OK"),
        SimpleNamespace(course_id="HF-REF", status="OVERDUE"),
        SimpleNamespace(course_id="SMS-REF", status="OK"),
    ]

    grouped = record_presentation._group_pdf_status_items(items, course_by_id)
    assert len(grouped) == 2
    assert {item.course_id for item in grouped} == {"HF-REF", "SMS-REF"}


def test_suffix_similarity_does_not_inflate_or_merge_requirement_counts():
    initial = _course(pk="a", code="EWIS-INIT", kind=training_models.TrainingKind.INITIAL)
    recurrent = _course(pk="b", code="EWIS-REF", kind=training_models.TrainingKind.RECURRENT)
    course_by_id = {course.id: course for course in (initial, recurrent)}
    items = [SimpleNamespace(course_id="EWIS-INIT", status="OK"), SimpleNamespace(course_id="EWIS-REF", status="OK")]

    grouped = record_presentation._group_pdf_status_items(items, course_by_id)
    assert len(grouped) == 2
