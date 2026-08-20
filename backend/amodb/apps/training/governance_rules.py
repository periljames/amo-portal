"""Pure governance decisions for the aviation Training Operating System.

The functions in this module intentionally accept mappings rather than ORM objects so
that the governing decision can be unit-tested without a database and every blocker
can be reproduced in browser/API acceptance tests.
"""
from __future__ import annotations

from collections import defaultdict
from datetime import date
from decimal import Decimal
from typing import Iterable, Mapping, Sequence


_ALLOWED_SEVERITIES = {"BLOCK", "APPROVAL_REQUIRED", "WARNING", "ADVISORY"}
_ACTIVE_QUESTION_STATUSES = {"ACTIVE"}
_TECHNICAL_ACTIVE_STATUSES = {"ACTIVE"}


def _as_date(value: object) -> date | None:
    if value is None or value == "":
        return None
    if isinstance(value, date):
        return value
    return date.fromisoformat(str(value))


def _upper(value: object) -> str:
    return str(value or "").strip().upper()


def _scope_matches(applicability: Mapping[str, object] | None, context: Mapping[str, object]) -> bool:
    """Match rule applicability without inventing semantics for missing fields.

    A source may scope a rule to any explicit key (course, authority, aircraft,
    delivery method, etc.).  Values may be scalar or arrays.  An absent context key
    means the rule is not proven applicable, rather than silently assuming it is.
    """

    for key, expected in dict(applicability or {}).items():
        if expected in (None, "", [], {}):
            continue
        actual = context.get(key)
        if actual is None:
            return False
        if isinstance(expected, (list, tuple, set)):
            expected_values = {_upper(item) for item in expected}
            if isinstance(actual, (list, tuple, set)):
                if not expected_values.intersection({_upper(item) for item in actual}):
                    return False
            elif _upper(actual) not in expected_values:
                return False
        elif _upper(actual) != _upper(expected):
            return False
    return True


def effective_rules(
    rules: Iterable[Mapping[str, object]],
    *,
    on_date: date,
    context: Mapping[str, object] | None = None,
) -> list[Mapping[str, object]]:
    applicable: list[Mapping[str, object]] = []
    resolved_context = context or {}
    for rule in rules:
        if _upper(rule.get("status")) != "ACTIVE":
            continue
        start = _as_date(rule.get("effective_from"))
        end = _as_date(rule.get("effective_to"))
        if start and on_date < start:
            continue
        if end and on_date > end:
            continue
        if not _scope_matches(rule.get("applicability") if isinstance(rule.get("applicability"), Mapping) else {}, resolved_context):
            continue
        severity = _upper(rule.get("severity"))
        if severity not in _ALLOWED_SEVERITIES:
            raise ValueError(f"Unsupported governance severity: {severity or '<empty>'}")
        applicable.append(rule)
    return applicable


def rule_conflicts(rules: Iterable[Mapping[str, object]]) -> list[dict[str, object]]:
    """Return unresolved same-code rule conflicts; never guess source precedence."""

    grouped: dict[str, list[Mapping[str, object]]] = defaultdict(list)
    for rule in rules:
        grouped[str(rule.get("rule_code") or "")].append(rule)

    conflicts: list[dict[str, object]] = []
    for code, rows in grouped.items():
        if not code or len(rows) < 2:
            continue
        signatures = {
            (
                repr(row.get("value_json", {})),
                repr(row.get("condition_json", {})),
                _upper(row.get("severity")),
                bool(row.get("exception_permitted", False)),
            )
            for row in rows
        }
        if len(signatures) <= 1:
            continue
        conflicts.append(
            {
                "rule_code": code,
                "rule_ids": [str(row.get("id") or "") for row in rows],
                "sources": [
                    {
                        "document_id": row.get("source_document_id"),
                        "revision_id": row.get("source_revision_id"),
                        "section": row.get("source_section"),
                        "paragraph": row.get("source_paragraph"),
                    }
                    for row in rows
                ],
                "message": f"Current controlled sources disagree for {code}; human governance resolution is required.",
            }
        )
    return conflicts


def technical_authorisation_reasons(
    authorisation: Mapping[str, object] | None,
    *,
    on_date: date,
    privilege_type: str,
    course_id: str | None = None,
    aircraft: str | None = None,
    require_theory: bool = False,
    require_practical: bool = False,
    require_ojt: bool = False,
    dependencies_satisfied: bool = True,
) -> list[str]:
    if not authorisation:
        return [f"No controlled {privilege_type.lower()} authorisation exists for this person."]
    reasons: list[str] = []
    if _upper(authorisation.get("privilege_type")) != _upper(privilege_type):
        reasons.append(f"Authorisation does not grant {privilege_type.upper()} privilege.")
    if _upper(authorisation.get("status")) not in _TECHNICAL_ACTIVE_STATUSES:
        reasons.append(f"Technical authorisation is {_upper(authorisation.get('status')) or 'not active'}.")
    issue = _as_date(authorisation.get("issue_date"))
    expiry = _as_date(authorisation.get("expiry_date"))
    if issue and on_date < issue:
        reasons.append("Technical authorisation is not yet effective.")
    if expiry and on_date > expiry:
        reasons.append(f"Technical authorisation expired on {expiry.isoformat()}.")
    course_ids = {str(value) for value in authorisation.get("course_ids", []) or []}
    if course_id and course_ids and course_id not in course_ids:
        reasons.append("Technical authorisation is outside this course scope.")
    scoped_aircraft = str(authorisation.get("aircraft") or "").strip()
    if aircraft and scoped_aircraft and _upper(scoped_aircraft) != _upper(aircraft):
        reasons.append("Technical authorisation is outside this aircraft/type scope.")
    if require_theory and not bool(authorisation.get("theoretical_privilege")):
        reasons.append("Theoretical teaching privilege is not granted.")
    if require_practical and not bool(authorisation.get("practical_privilege")):
        reasons.append("Practical teaching/assessment privilege is not granted.")
    if require_ojt and not bool(authorisation.get("ojt_privilege")):
        reasons.append("OJT privilege is not granted.")
    if not dependencies_satisfied:
        reasons.append("Licence/training/observation/recurrent dependencies are not current.")
    return reasons


def approval_reasons(
    approval: Mapping[str, object] | None,
    *,
    on_date: date,
    expected_type: str | None = None,
) -> list[str]:
    if not approval:
        return ["No controlled approval covers this activity."]
    reasons: list[str] = []
    if _upper(approval.get("status")) != "ACTIVE":
        reasons.append(f"Approval is {_upper(approval.get('status')) or 'not active'}.")
    if expected_type and _upper(approval.get("approval_type")) != _upper(expected_type):
        reasons.append(f"Approval type does not cover {expected_type}.")
    start = _as_date(approval.get("effective_date"))
    expiry = _as_date(approval.get("expiry_date"))
    if start and on_date < start:
        reasons.append("Approval is not yet effective.")
    if expiry and on_date > expiry:
        reasons.append(f"Approval expired on {expiry.isoformat()}.")
    return reasons


def facility_reasons(
    facility: Mapping[str, object] | None,
    *,
    on_date: date,
    learners: int,
    practical_learners: int = 0,
    approval_required: bool = True,
) -> list[str]:
    if not facility:
        return ["No controlled training facility is assigned."]
    reasons: list[str] = []
    if _upper(facility.get("status")) != "ACTIVE":
        reasons.append(f"Training facility is {_upper(facility.get('status')) or 'not active'}.")
    expiry = _as_date(facility.get("expiry_date"))
    if expiry and on_date > expiry:
        reasons.append(f"Training facility approval expired on {expiry.isoformat()}.")
    if approval_required and not facility.get("approval_id"):
        reasons.append("This course requires an approved facility, but no facility approval is linked.")
    classroom_capacity = facility.get("classroom_capacity")
    if classroom_capacity is not None and learners > int(classroom_capacity):
        reasons.append(f"Class size {learners} exceeds controlled classroom capacity {classroom_capacity}.")
    practical_capacity = facility.get("practical_capacity")
    if practical_capacity is not None and practical_learners > int(practical_capacity):
        reasons.append(f"Practical group {practical_learners} exceeds controlled practical capacity {practical_capacity}.")
    return reasons


def provider_credit_reasons(
    provider: Mapping[str, object] | None,
    *,
    training_date: date,
    course_id: str | None,
    authority_id: str | None = None,
) -> list[str]:
    if not provider:
        return ["External provider is not in the governed provider register."]
    reasons: list[str] = []
    if _upper(provider.get("status")) != "ACTIVE":
        reasons.append(f"External provider is {_upper(provider.get('status')) or 'not active'}.")
    if _upper(provider.get("recognition_status")) not in {"RECOGNISED", "RECOGNIZED", "ACCEPTED"}:
        reasons.append("External provider has not been recognised for training credit by this tenant.")
    start = _as_date(provider.get("effective_date"))
    expiry = _as_date(provider.get("expiry_date"))
    if start and training_date < start:
        reasons.append("Provider approval was not yet effective on the training date.")
    if expiry and training_date > expiry:
        reasons.append("Provider approval was expired on the training date.")
    approved_courses = {str(value) for value in provider.get("approved_course_ids", []) or []}
    if course_id and approved_courses and course_id not in approved_courses:
        reasons.append("External provider approval scope does not cover this course.")
    if authority_id and provider.get("authority_id") and str(provider.get("authority_id")) != authority_id:
        reasons.append("External provider authority does not match the required recognition authority.")
    return reasons


def course_revision_reconciliation(
    *,
    revision: Mapping[str, object],
    modules: Iterable[Mapping[str, object]],
) -> dict[str, object]:
    theory = sum(Decimal(str(row.get("theory_hours") or 0)) for row in modules)
    practical = sum(Decimal(str(row.get("practical_hours") or 0)) for row in modules)
    total = theory + practical
    expected_theory = Decimal(str(revision.get("theory_hours") or 0))
    expected_practical = Decimal(str(revision.get("practical_hours") or 0))
    expected_total = Decimal(str(revision.get("total_hours") or 0))
    blockers: list[str] = []
    if theory != expected_theory:
        blockers.append(f"Module theory hours {theory} do not reconcile to controlled theory hours {expected_theory}.")
    if practical != expected_practical:
        blockers.append(f"Module practical hours {practical} do not reconcile to controlled practical hours {expected_practical}.")
    if total != expected_total:
        blockers.append(f"Module total hours {total} do not reconcile to controlled course hours {expected_total}.")
    return {"theory_hours": theory, "practical_hours": practical, "total_hours": total, "blockers": blockers}


def question_eligibility_reasons(question: Mapping[str, object], revision: Mapping[str, object], *, on_date: date) -> list[str]:
    reasons: list[str] = []
    if _upper(question.get("status")) not in _ACTIVE_QUESTION_STATUSES:
        reasons.append(f"Question is {_upper(question.get('status')) or 'not active'}.")
    if _upper(revision.get("status")) not in _ACTIVE_QUESTION_STATUSES:
        reasons.append(f"Question revision is {_upper(revision.get('status')) or 'not active'}.")
    start = _as_date(revision.get("effective_from"))
    end = _as_date(revision.get("effective_to"))
    if start and on_date < start:
        reasons.append("Question revision is not yet effective.")
    if end and on_date > end:
        reasons.append("Question revision is superseded/expired for new examinations.")
    if not revision.get("source_revision_id"):
        reasons.append("Question revision has no controlled source revision.")
    return reasons


def learner_completion_decision(
    *,
    required_module_ids: Sequence[str],
    completed_module_ids: Iterable[str],
    required_practical_task_ids: Sequence[str],
    passed_practical_task_ids: Iterable[str],
    required_assessments: Sequence[str],
    passed_assessments: Iterable[str],
    additional_blockers: Iterable[str] = (),
) -> dict[str, object]:
    modules_missing = sorted(set(required_module_ids) - set(completed_module_ids))
    practical_missing = sorted(set(required_practical_task_ids) - set(passed_practical_task_ids))
    assessments_missing = sorted(set(required_assessments) - set(passed_assessments))
    blockers = list(additional_blockers)
    blockers.extend(f"Required module incomplete: {value}" for value in modules_missing)
    blockers.extend(f"Required practical task incomplete: {value}" for value in practical_missing)
    blockers.extend(f"Required assessment incomplete: {value}" for value in assessments_missing)
    if blockers:
        if modules_missing:
            status = "MAKE_UP_REQUIRED"
        elif practical_missing:
            status = "PRACTICAL_INCOMPLETE"
        elif assessments_missing:
            status = "EXAMINATION_INCOMPLETE"
        else:
            status = "BLOCKED"
        return {"status": status, "certificate_eligible": False, "blockers": blockers}
    return {"status": "READY_FOR_CERTIFICATE", "certificate_eligible": True, "blockers": []}


def batch_certificate_decisions(decisions: Iterable[Mapping[str, object]]) -> dict[str, object]:
    ready: list[str] = []
    blocked: list[dict[str, object]] = []
    for row in decisions:
        user_id = str(row.get("user_id") or "")
        if bool(row.get("certificate_eligible")) and _upper(row.get("status")) == "READY_FOR_CERTIFICATE":
            ready.append(user_id)
        else:
            blocked.append({"user_id": user_id, "status": row.get("status"), "blockers": list(row.get("blockers") or [])})
    return {"ready_user_ids": ready, "blocked": blocked, "ready_count": len(ready), "blocked_count": len(blocked)}


def readiness_result(checks: Iterable[Mapping[str, object]]) -> dict[str, object]:
    """Collapse explainable checks into READY/WARNING/BLOCKED without losing actions."""

    normalized = [dict(row) for row in checks]
    has_block = any(_upper(row.get("severity")) in {"BLOCK", "APPROVAL_REQUIRED"} and not bool(row.get("satisfied")) for row in normalized)
    has_warning = any(_upper(row.get("severity")) == "WARNING" and not bool(row.get("satisfied")) for row in normalized)
    status = "BLOCKED" if has_block else "WARNING" if has_warning else "READY"
    return {
        "status": status,
        "checks": normalized,
        "blockers": [row for row in normalized if not bool(row.get("satisfied")) and _upper(row.get("severity")) in {"BLOCK", "APPROVAL_REQUIRED"}],
        "warnings": [row for row in normalized if not bool(row.get("satisfied")) and _upper(row.get("severity")) == "WARNING"],
    }
