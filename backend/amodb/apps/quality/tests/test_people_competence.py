"""Unit tests for QMS competence — Training policy reuse, not parallel aliases."""
from __future__ import annotations

from datetime import date, timedelta
from types import SimpleNamespace

from amodb.apps.quality.people_competence import (
    active_controlled_authorization_exception,
    apply_auto_suspend_if_currency_lapsed,
    cap_privilege_expires_on,
    earliest_competence_valid_until,
    resolve_rule_competence,
)
from amodb.apps.quality.people_default_rules import DEFAULT_QUALITY_PRIVILEGE_RULES
from amodb.apps.training.integration import (
    QMS_ADMIN,
    QMS_INIT,
    QMS_REF,
    canonicalize_qms_competence_code,
    current_training_evidence_with_alternatives,
    qms_auditor_competence_evidence,
)


class _FakeQuery:
    def __init__(self, rows):
        self._rows = rows

    def join(self, *args, **kwargs):
        return self

    def options(self, *args, **kwargs):
        return self

    def filter(self, *args, **kwargs):
        return self

    def order_by(self, *args, **kwargs):
        return self

    def limit(self, *args, **kwargs):
        return self

    def all(self):
        return list(self._rows)

    def first(self):
        return self._rows[0] if self._rows else None


class _FakeSession:
    def __init__(self, rows=None, decisions=None):
        self.rows = rows or []
        self.decisions = decisions or []
        self.added = []

    def query(self, *models):
        if len(models) == 1 and models[0].__name__ == "QualityPrivilegeDecision":
            return _FakeQuery(self.decisions)
        return _FakeQuery(self.rows)

    def add(self, row):
        self.added.append(row)

    def flush(self):
        for row in self.added:
            if getattr(row, "id", None) is None:
                row.id = f"dec-{len(self.added)}"


def _record(code: str, *, valid_until: date | None, verification="VERIFIED"):
    course = SimpleNamespace(id=f"course-{code}", course_id=code)
    record = SimpleNamespace(
        id=f"rec-{code}",
        completion_date=date(2025, 1, 1),
        valid_until=valid_until,
        verification_status=verification,
        created_at=None,
    )
    return record, course


def test_canonicalize_uses_training_structured_identity_only() -> None:
    from amodb.apps.training import models as training_models

    assert canonicalize_qms_competence_code(SimpleNamespace(course_id="QMS-INIT", group_code=None, kind=None, course_name="")) == QMS_INIT
    assert canonicalize_qms_competence_code(SimpleNamespace(course_id="QMS_REF", group_code=None, kind=None, course_name="")) == QMS_REF
    assert canonicalize_qms_competence_code(SimpleNamespace(course_id="QMS REF", group_code=None, kind=None, course_name="")) == QMS_REF
    # Compact glued forms without separators are not punctuation normalisation — require
    # Training group_code / category / exact hyphenated course_id instead.
    assert canonicalize_qms_competence_code(SimpleNamespace(course_id="QMSINIT", group_code=None, kind=None, course_name="")) is None
    assert canonicalize_qms_competence_code(
        SimpleNamespace(course_id="AUD-01", group_code="QMS", kind=training_models.TrainingKind.INITIAL, course_name="Auditor initial")
    ) == QMS_INIT
    assert canonicalize_qms_competence_code(
        SimpleNamespace(course_id="AUD-02", group_code="QMS", kind=training_models.TrainingKind.RECURRENT, course_name="Auditor recurrent")
    ) == QMS_REF
    assert canonicalize_qms_competence_code(
        SimpleNamespace(
            course_id="QA-12",
            course_name="Quality Management System - Initial Auditor",
            group_code=None,
            category="QUALITY_SYSTEMS",
            kind="INITIAL",
            status="Initial",
        )
    ) == QMS_INIT
    # Unrelated families must not map.
    assert canonicalize_qms_competence_code(SimpleNamespace(course_id="HF-INIT", group_code="HF", kind=None, course_name="")) is None


def test_default_rules_embed_qms_competence_package() -> None:
    lead = next(row for row in DEFAULT_QUALITY_PRIVILEGE_RULES if row["privilege_code"] == "LEAD_AUDITOR_GLOBAL")
    auditor = next(row for row in DEFAULT_QUALITY_PRIVILEGE_RULES if row["privilege_code"] == "AUDITOR_GLOBAL")
    observer = next(row for row in DEFAULT_QUALITY_PRIVILEGE_RULES if row["privilege_code"] == "OBSERVER_TRAINEE_GLOBAL")
    assert lead["scope_schema"]["qms_competence"]["codes"] == [QMS_INIT, QMS_REF, QMS_ADMIN]
    assert lead["scope_schema"]["qms_competence"]["join"] == "AND"
    assert lead["scope_schema"]["qms_competence"]["expression"] == "QMS-INIT AND QMS-REF AND QMS-ADMIN"
    assert auditor["scope_schema"]["qms_competence"]["tracked_admin"] == QMS_ADMIN
    assert lead["required_training_course_codes"] == []
    assert observer["scope_schema"]["supervised_development"] is True
    assert "qms_competence" not in observer["scope_schema"]


def test_resolve_rule_competence_reads_scope_schema() -> None:
    rule = SimpleNamespace(scope_schema={"qms_competence": {"currency_any_of": [QMS_INIT, QMS_REF], "tracked_admin": QMS_ADMIN}})
    package = resolve_rule_competence(rule)  # type: ignore[arg-type]
    assert package is not None
    assert package["currency_any_of"] == [QMS_INIT, QMS_REF]
    assert package["tracked_admin"] == QMS_ADMIN
    assert package["codes"] == [QMS_INIT, QMS_REF, QMS_ADMIN]
    assert package["join"] == "OR"
    assert package["legacy_or_currency"] is True


def test_parse_training_expression_supports_and_or_words() -> None:
    from amodb.apps.quality.people_competence import evaluate_training_expression, parse_training_expression

    parsed = parse_training_expression("QMS-INIT AND QMS-REF AND QMS-ADMIN")
    assert parsed["ok"] is True
    assert parsed["join"] == "AND"
    assert parsed["codes"] == [QMS_INIT, QMS_REF, QMS_ADMIN]
    assert evaluate_training_expression("QMS-INIT OR QMS-REF", {QMS_REF}) is True
    assert evaluate_training_expression("(QMS-INIT OR QMS-REF) AND QMS-ADMIN", {QMS_REF, QMS_ADMIN}) is True
    assert evaluate_training_expression("QMS-INIT AND QMS-REF", {QMS_INIT}) is False


def test_alternatives_pass_when_either_init_or_ref_current() -> None:
    today = date(2026, 9, 18)
    rows = [_record(QMS_INIT, valid_until=today + timedelta(days=30))]
    db = _FakeSession(rows=rows)
    result = current_training_evidence_with_alternatives(
        db,  # type: ignore[arg-type]
        amo_id="amo-1",
        user_id="user-1",
        alternative_groups=[[QMS_INIT], [QMS_REF]],
        as_of=today,
    )
    assert result["passed"] is True
    assert result["satisfied_group"] == [QMS_INIT]
    assert QMS_REF not in result["satisfied"]


def test_alternatives_fail_when_only_expired_evidence() -> None:
    today = date(2026, 9, 18)
    db_empty_current = _FakeSession(rows=[])
    result = current_training_evidence_with_alternatives(
        db_empty_current,  # type: ignore[arg-type]
        amo_id="amo-1",
        user_id="user-1",
        alternative_groups=[[QMS_INIT], [QMS_REF]],
        as_of=today,
    )
    assert result["passed"] is False


def test_competence_evidence_reads_training_policy_rows(monkeypatch) -> None:
    from amodb.apps.training import integration as integration_mod

    today = date(2026, 9, 18)

    def fake_tracked(db, *, amo_id, user_id, as_of, codes):
        return {
            QMS_INIT: {
                "course_code": QMS_INIT,
                "completion_date": "2025-01-01",
                "valid_until": None,
                "days_until_expiry": None,
                "verification_status": "VERIFIED",
                "record_status": "READY",
                "training_status": "OK",
                "source_course_code": "AUD-01",
            },
            QMS_REF: {
                "course_code": QMS_REF,
                "completion_date": "2025-08-01",
                "valid_until": (today + timedelta(days=40)).isoformat(),
                "days_until_expiry": 40,
                "verification_status": "VERIFIED",
                "record_status": "READY",
                "training_status": "DUE_SOON",
                "source_course_code": "AUD-02",
            },
            QMS_ADMIN: {
                "course_code": QMS_ADMIN,
                "completion_date": "2025-06-01",
                "valid_until": (today + timedelta(days=200)).isoformat(),
                "days_until_expiry": 200,
                "verification_status": "PENDING",
                "record_status": "PENDING",
                "training_status": "NOT_DONE",
                "source_course_code": "QMS-ADMIN",
            },
        }

    monkeypatch.setattr(integration_mod, "_tracked_from_training_policy", fake_tracked)
    evidence = qms_auditor_competence_evidence(
        _FakeSession(),  # type: ignore[arg-type]
        amo_id="amo-1",
        user_id="user-1",
        as_of=today,
        track_admin=True,
    )
    assert evidence["source"].startswith("training_policy")
    assert evidence["passed"] is True
    assert QMS_REF in evidence["satisfied"]
    tracked = {str(row["course_code"]): row for row in evidence["tracked_records"]}
    assert tracked[QMS_REF]["days_until_expiry"] == 40
    assert tracked[QMS_INIT]["completion_date"] == "2025-01-01"
    assert tracked[QMS_INIT]["source_course_code"] == "AUD-01"


def test_competence_evidence_marks_never_completed_from_training_policy(monkeypatch) -> None:
    from amodb.apps.training import integration as integration_mod

    today = date(2026, 9, 18)

    def fake_tracked(db, *, amo_id, user_id, as_of, codes):
        return {
            QMS_INIT: {
                "course_code": QMS_INIT,
                "completion_date": None,
                "valid_until": None,
                "days_until_expiry": None,
                "verification_status": "NONE",
                "record_status": "MISSING",
                "training_status": "NOT_DONE",
                "source_course_code": "QMS-INIT",
            },
        }

    monkeypatch.setattr(integration_mod, "_tracked_from_training_policy", fake_tracked)
    evidence = qms_auditor_competence_evidence(
        _FakeSession(),  # type: ignore[arg-type]
        amo_id="amo-1",
        user_id="user-1",
        as_of=today,
    )
    assert evidence["passed"] is False
    assert QMS_INIT in evidence["missing"]
    tracked = {str(row["course_code"]): row for row in evidence["tracked_records"]}
    # Never-completed policy rows have no dates — do not invent a blank/current chip payload.
    assert QMS_INIT not in tracked


def test_unverified_training_policy_row_does_not_pass_gate(monkeypatch) -> None:
    from amodb.apps.training import integration as integration_mod

    today = date(2026, 9, 18)

    def fake_tracked(db, *, amo_id, user_id, as_of, codes):
        return {
            QMS_INIT: {
                "course_code": QMS_INIT,
                "completion_date": "2025-01-01",
                "valid_until": None,
                "days_until_expiry": None,
                "verification_status": "PENDING",
                "record_status": "PENDING",
                # Training policy only emits OK after verified currency.
                "training_status": "NOT_DONE",
                "source_course_code": "QMS-INIT",
            },
        }

    monkeypatch.setattr(integration_mod, "_tracked_from_training_policy", fake_tracked)
    evidence = qms_auditor_competence_evidence(
        _FakeSession(),  # type: ignore[arg-type]
        amo_id="amo-1",
        user_id="user-1",
        as_of=today,
    )
    assert evidence["passed"] is False
    tracked = {str(row["course_code"]): row for row in evidence["tracked_records"]}
    assert QMS_INIT in tracked
    assert tracked[QMS_INIT]["completion_date"] == "2025-01-01"


def test_auto_suspend_is_idempotent_for_active_privilege() -> None:
    today = date(2026, 9, 18)
    privilege = SimpleNamespace(
        id="priv-1",
        status="ACTIVE",
        scope={},
        decisions=[],
        effective_from=today - timedelta(days=10),
        expires_on=None,
        latest_decision_id=None,
        updated_by_user_id=None,
        updated_at=None,
    )
    rule = SimpleNamespace(id="rule-1", privilege_code="AUDITOR_GLOBAL")
    competence = {
        "suspend_recommended": True,
        "expired": [QMS_REF],
        "missing": [QMS_INIT, QMS_REF],
        "admin_lapsed": False,
        "required": [QMS_INIT, QMS_REF],
    }
    db = _FakeSession(decisions=[])
    first = apply_auto_suspend_if_currency_lapsed(
        db,  # type: ignore[arg-type]
        amo_id="amo-1",
        privilege=privilege,  # type: ignore[arg-type]
        rule=rule,  # type: ignore[arg-type]
        competence=competence,
        as_of=today,
        actor_user_id="qm-1",
    )
    assert first is not None
    assert privilege.status == "SUSPENDED"
    assert len(db.added) == 1

    second = apply_auto_suspend_if_currency_lapsed(
        db,  # type: ignore[arg-type]
        amo_id="amo-1",
        privilege=privilege,  # type: ignore[arg-type]
        rule=rule,  # type: ignore[arg-type]
        competence=competence,
        as_of=today,
        actor_user_id="qm-1",
    )
    assert second is None
    assert len(db.added) == 1


def test_controlled_authorization_exception_requires_current_effectivity() -> None:
    today = date(2026, 9, 22)
    privilege = SimpleNamespace(
        scope={
            "controlled_exemption": {
                "criterion": "training_current_verified",
                "effective_from": today.isoformat(),
                "expires_on": (today + timedelta(days=7)).isoformat(),
                "approved_by_user_id": "qm-1",
                "conditions": ["Direct supervision during assigned audit work."],
                "limitations": ["Observer role only."],
                "supervision_required": True,
            }
        },
        decisions=[],
    )
    exception = active_controlled_authorization_exception(privilege, as_of=today)  # type: ignore[arg-type]
    assert exception is not None
    assert exception["valid_until"] == (today + timedelta(days=7)).isoformat()
    assert exception["criterion"] == "training_current_verified"
    assert exception["supervision_required"] is True

    privilege.scope["controlled_exemption"]["expires_on"] = (today - timedelta(days=1)).isoformat()
    assert active_controlled_authorization_exception(privilege, as_of=today) is None  # type: ignore[arg-type]


def test_legacy_qm_bypass_is_read_only_compatibility_not_a_writer() -> None:
    today = date(2026, 9, 22)
    privilege = SimpleNamespace(
        scope={
            "qm_training_bypass": {
                "rationale": "Historic recorded exception retained for traceability.",
                "valid_until": (today + timedelta(days=1)).isoformat(),
                "approved_by_user_id": "qm-legacy",
            }
        },
        decisions=[],
    )
    legacy = active_controlled_authorization_exception(privilege, as_of=today)  # type: ignore[arg-type]
    assert legacy is not None
    assert legacy["source"] == "legacy_privilege_scope"

    from amodb.apps.quality import people_competence
    assert not hasattr(people_competence, "record_qm_training_bypass")


def test_no_parallel_alias_dictionary_remains() -> None:
    from pathlib import Path

    source = Path(__file__).resolve().parents[1].parent.joinpath("training", "integration.py").read_text(encoding="utf-8")
    assert "_QMS_CODE_ALIASES" not in source
    assert "_qms_course_match_filter" not in source
    assert "QUALITYINIT" not in source
    assert "_tracked_from_training_policy" in source
    assert "evaluate_user_training_policy" in source


def test_blank_pills_reproduce_when_training_uses_spaced_course_ids(monkeypatch) -> None:
    """Spaced/underscored catalogue ids still map via Training policy + structured identity."""
    from amodb.apps.training import integration as integration_mod

    today = date(2026, 9, 18)

    def fake_tracked(db, *, amo_id, user_id, as_of, codes):
        return {
            QMS_INIT: {
                "course_code": QMS_INIT,
                "completion_date": "2025-03-01",
                "valid_until": None,
                "days_until_expiry": None,
                "verification_status": "PENDING",
                "record_status": "PENDING",
                "training_status": "NOT_DONE",
                "source_course_code": "QMS INIT",
            },
            QMS_REF: {
                "course_code": QMS_REF,
                "completion_date": "2025-08-01",
                "valid_until": (today + timedelta(days=60)).isoformat(),
                "days_until_expiry": 60,
                "verification_status": "VERIFIED",
                "record_status": "READY",
                "training_status": "OK",
                "source_course_code": "QMS_REF",
            },
        }

    monkeypatch.setattr(integration_mod, "_tracked_from_training_policy", fake_tracked)
    evidence = qms_auditor_competence_evidence(
        _FakeSession(),  # type: ignore[arg-type]
        amo_id="amo-1",
        user_id="user-1",
        as_of=today,
        track_admin=True,
    )
    tracked = {str(item["course_code"]): item for item in evidence.get("tracked_records") or []}
    assert QMS_INIT in tracked, "People pills went blank when Training used 'QMS INIT'"
    assert QMS_REF in tracked
    assert tracked[QMS_INIT]["completion_date"] == "2025-03-01"
    assert tracked[QMS_REF]["days_until_expiry"] == 60
    assert tracked[QMS_INIT]["source_course_code"] == "QMS INIT"
    assert evidence["passed"] is True
    assert canonicalize_qms_competence_code(
        SimpleNamespace(course_id="QMS INIT", group_code="QMS", kind="INITIAL", category="QUALITY_SYSTEMS", course_name="")
    ) == QMS_INIT


def test_earliest_competence_valid_until_uses_soonest_satisfied_course():
    training = {
        "satisfied": ["QMS-INIT", "QMS-REF"],
        "records": [
            {"course_code": "QMS-INIT", "valid_until": None},
            {"course_code": "QMS-REF", "valid_until": "2030-01-15"},
            {"course_code": "QMS-ADMIN", "valid_until": "2028-06-01"},  # not satisfied — ignored
        ],
    }
    assert earliest_competence_valid_until(training, as_of=date(2026, 9, 21)) == date(2030, 1, 15)


def test_cap_privilege_expires_on_forces_course_calendar_day():
    training = {
        "satisfied": ["QMS-REF"],
        "records": [{"course_code": "QMS-REF", "valid_until": "2030-01-15"}],
    }
    assert cap_privilege_expires_on(None, training, as_of=date(2026, 9, 21)) == date(2030, 1, 15)
    assert cap_privilege_expires_on(date(2035, 1, 1), training, as_of=date(2026, 9, 21)) == date(2030, 1, 15)
    assert cap_privilege_expires_on(date(2029, 6, 1), training, as_of=date(2026, 9, 21)) == date(2029, 6, 1)
