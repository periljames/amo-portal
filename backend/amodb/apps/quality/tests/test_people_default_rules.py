from __future__ import annotations

from amodb.apps.quality.people_default_rules import (
    DEFAULT_QUALITY_PRIVILEGE_RULES,
    ensure_default_quality_privilege_rules,
)


def test_default_quality_privilege_rules_cover_lead_observer_trainee_and_auditor() -> None:
    codes = [row["privilege_code"] for row in DEFAULT_QUALITY_PRIVILEGE_RULES]
    titles = [row["title"] for row in DEFAULT_QUALITY_PRIVILEGE_RULES]
    types = [row["privilege_type"] for row in DEFAULT_QUALITY_PRIVILEGE_RULES]

    assert codes == ["LEAD_AUDITOR_GLOBAL", "OBSERVER_TRAINEE_GLOBAL", "AUDITOR_GLOBAL"]
    assert titles == ["Lead auditor", "Observer / Trainee", "Auditor"]
    assert types == ["LEAD_AUDITOR", "AUDITOR", "AUDITOR"]

    observer = next(row for row in DEFAULT_QUALITY_PRIVILEGE_RULES if row["privilege_code"] == "OBSERVER_TRAINEE_GLOBAL")
    assert observer["scope_schema"]["supervised_development"] is True
    assert set(observer["scope_schema"]["allowed_assignment_roles"]) == {"OBSERVER_AUDITOR", "ASSISTANT_AUDITOR"}


def test_ensure_default_quality_privilege_rules_creates_missing_rows() -> None:
    class _Query:
        def filter(self, *args, **kwargs):
            return self

        def first(self):
            return None

    class _Session:
        def __init__(self):
            self.added = []
            self.flushed = 0

        def query(self, model):
            return _Query()

        def add(self, row):
            self.added.append(row)

        def flush(self):
            self.flushed += 1

    db = _Session()
    created = ensure_default_quality_privilege_rules(db, amo_id="amo-1", actor_user_id="user-1")
    assert len(created) == 3
    assert len(db.added) == 3
    assert {row.privilege_code for row in db.added} == {
        "LEAD_AUDITOR_GLOBAL",
        "OBSERVER_TRAINEE_GLOBAL",
        "AUDITOR_GLOBAL",
    }
    assert {row.title for row in db.added} == {"Lead auditor", "Observer / Trainee", "Auditor"}
    assert db.flushed == 1
