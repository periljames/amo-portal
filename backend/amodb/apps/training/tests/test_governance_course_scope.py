from __future__ import annotations

from datetime import date
from types import SimpleNamespace

from amodb.apps.training import governance_course_scope


class _Query:
    def __init__(self, row):
        self.row = row

    def filter(self, *args, **kwargs):
        return self

    def first(self):
        return self.row


class _DB:
    def __init__(self, row):
        self.row = row

    def query(self, *args, **kwargs):
        return _Query(self.row)


def test_revision_id_is_normalised_to_canonical_course_id(monkeypatch):
    captured = {}

    def fake_base(db, **kwargs):
        captured.update(kwargs)
        return {"eligible": True, "authorisation_id": "auth-1", "reasons": []}

    monkeypatch.setattr(governance_course_scope, "_base_readiness", fake_base)
    result = governance_course_scope.technical_authorisation_readiness(
        _DB(SimpleNamespace(course_id="course-1")),
        amo_id="tenant-1",
        user_id="assessor-1",
        privilege_type="ASSESSOR",
        on_date=date(2026, 8, 18),
        course_id="revision-1",
        require_practical=True,
    )

    assert result["eligible"] is True
    assert captured["course_id"] == "course-1"


def test_existing_canonical_course_id_is_preserved(monkeypatch):
    captured = {}

    def fake_base(db, **kwargs):
        captured.update(kwargs)
        return {"eligible": True, "authorisation_id": "auth-1", "reasons": []}

    monkeypatch.setattr(governance_course_scope, "_base_readiness", fake_base)
    governance_course_scope.technical_authorisation_readiness(
        _DB(None),
        amo_id="tenant-1",
        user_id="instructor-1",
        privilege_type="INSTRUCTOR",
        on_date=date(2026, 8, 18),
        course_id="course-1",
    )

    assert captured["course_id"] == "course-1"
