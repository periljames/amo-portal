from __future__ import annotations

import json
from datetime import date, timedelta
from typing import Any

from sqlalchemy.orm import Session

from amodb.apps.accounts import models as account_models
from amodb.apps.training.integration import current_training_evidence

from . import models as quality_models
from .people_models import QualityIndependenceDeclaration, QualityPrivilege, QualityPrivilegeRule
from .planner_schedule_models import QMSPlannerScheduleMetadata


_ROLE_TYPES = {
    "LEAD_AUDITOR": "LEAD_AUDITOR",
    "OBSERVER_AUDITOR": "AUDITOR",
    "ASSISTANT_AUDITOR": "AUDITOR",
}
_DEVELOPMENT_ROLES = {"OBSERVER_AUDITOR", "ASSISTANT_AUDITOR"}


def _enum_value(value: Any) -> str:
    return str(getattr(value, "value", value) or "")


def _json_list(value: Any) -> list[Any]:
    if isinstance(value, list):
        return value
    try:
        parsed = json.loads(value or "[]")
    except (TypeError, ValueError):
        return []
    return parsed if isinstance(parsed, list) else []


def _training_evidence(
    db: Session,
    *,
    amo_id: str,
    user_id: str,
    required_codes: list[str],
    as_of: date,
) -> dict[str, Any]:
    return current_training_evidence(
        db,
        amo_id=amo_id,
        user_id=user_id,
        required_codes=required_codes,
        as_of=as_of,
    )


def _capacity_evidence(
    db: Session,
    *,
    amo_id: str,
    user_id: str,
    as_of: date,
    maximum: int | None,
    exclude_schedule_id: str | None,
) -> dict[str, Any]:
    if maximum is None:
        return {"active_assignments": 0, "max_concurrent_assignments": None, "assignments": [], "passed": True}

    window_start = as_of - timedelta(days=90)
    window_end = as_of + timedelta(days=90)
    rows = (
        db.query(quality_models.QMSAuditSchedule, QMSPlannerScheduleMetadata)
        .join(QMSPlannerScheduleMetadata, QMSPlannerScheduleMetadata.schedule_id == quality_models.QMSAuditSchedule.id)
        .filter(
            quality_models.QMSAuditSchedule.amo_id == amo_id,
            quality_models.QMSAuditSchedule.is_active.is_(True),
            quality_models.QMSAuditSchedule.deleted_at.is_(None),
            quality_models.QMSAuditSchedule.next_due_date >= window_start,
            quality_models.QMSAuditSchedule.next_due_date <= window_end,
            QMSPlannerScheduleMetadata.lifecycle_status == "ACTIVE",
        )
        .limit(1000)
        .all()
    )
    assignments: list[dict[str, Any]] = []
    for schedule, metadata in rows:
        if exclude_schedule_id and str(schedule.id) == str(exclude_schedule_id):
            continue
        assigned_ids = {
            str(value)
            for value in [
                schedule.lead_auditor_user_id,
                schedule.observer_auditor_user_id,
                schedule.assistant_auditor_user_id,
                *_json_list(metadata.attendee_user_ids_json),
            ]
            if value
        }
        if user_id not in assigned_ids:
            continue
        end_date = schedule.next_due_date + timedelta(days=max(int(schedule.duration_days or 1), 1) - 1)
        if schedule.next_due_date <= as_of <= end_date:
            assignments.append(
                {
                    "schedule_id": str(schedule.id),
                    "title": schedule.title,
                    "start_date": schedule.next_due_date.isoformat(),
                    "end_date": end_date.isoformat(),
                    "source_route": f"/quality/audits/plan?schedule={schedule.id}",
                }
            )
    return {
        "active_assignments": len(assignments),
        "max_concurrent_assignments": maximum,
        "assignments": assignments,
        "passed": len(assignments) < maximum,
    }


def _independence_evidence(
    db: Session,
    *,
    amo_id: str,
    user_id: str,
    required: bool,
    context_type: str | None,
    context_id: str | None,
    enforce: bool,
) -> dict[str, Any]:
    if not required:
        return {"required": False, "passed": True, "pending": False, "declaration": None}
    if not enforce:
        return {
            "required": True,
            "passed": True,
            "pending": True,
            "declaration": None,
            "message": "Independence must be declared against the created assignment before activation or execution.",
        }
    if not context_type or not context_id:
        return {"required": True, "passed": False, "pending": True, "declaration": None, "message": "Assignment context is required."}
    row = db.query(QualityIndependenceDeclaration).filter(
        QualityIndependenceDeclaration.amo_id == amo_id,
        QualityIndependenceDeclaration.user_id == user_id,
        QualityIndependenceDeclaration.context_type == context_type,
        QualityIndependenceDeclaration.context_id == context_id,
    ).first()
    if row is None:
        return {"required": True, "passed": False, "pending": True, "declaration": None, "message": "No independence declaration exists for this assignment."}
    return {
        "required": True,
        "passed": row.declaration == "INDEPENDENT",
        "pending": False,
        "declaration": row.declaration,
        "declaration_id": str(row.id),
        "rationale": row.rationale,
        "declared_at": row.declared_at.isoformat(),
    }


def _privilege_scope_matches(scope_key: str | None, assignment_scope_key: str | None) -> bool:
    value = str(scope_key or "GLOBAL").strip().upper()
    if value in {"GLOBAL", "*"}:
        return True
    if not assignment_scope_key:
        return False
    return value == str(assignment_scope_key).strip().upper()


def _development_rule(rule: QualityPrivilegeRule, role: str) -> bool:
    """Return whether this rule explicitly authorizes supervised auditor development.

    This is tenant configuration, not a portal default. Developmental privileges are
    never valid for lead-auditor assignments and do not waive active privilege,
    scope, capacity, or independence gates.
    """

    if role not in _DEVELOPMENT_ROLES:
        return False
    scope_schema = rule.scope_schema if isinstance(rule.scope_schema, dict) else {}
    if scope_schema.get("supervised_development") is not True:
        return False
    allowed_roles = {
        str(value).strip().upper()
        for value in scope_schema.get("allowed_assignment_roles", [])
        if str(value).strip()
    }
    return not allowed_roles or role in allowed_roles


def evaluate_auditor_assignment(
    db: Session,
    *,
    amo_id: str,
    user_id: str,
    assignment_role: str,
    as_of: date,
    assignment_scope_key: str | None = None,
    context_type: str | None = None,
    context_id: str | None = None,
    enforce_independence: bool = True,
    exclude_schedule_id: str | None = None,
) -> dict[str, Any]:
    """Evaluate one auditor assignment against governed People hard gates.

    Auditor assignment is fail-closed. A tenant must configure an active Quality
    privilege rule for the requested auditor role before any assignment can pass.
    Observer/assistant development remains possible only when the tenant has
    explicitly marked the governing AUDITOR rule for supervised development.
    """

    role = str(assignment_role or "").strip().upper()
    privilege_type = _ROLE_TYPES.get(role)
    if privilege_type is None:
        raise ValueError(f"Unsupported auditor assignment role: {assignment_role}")

    user = db.query(account_models.User).filter(
        account_models.User.amo_id == amo_id,
        account_models.User.id == user_id,
        account_models.User.is_active.is_(True),
        account_models.User.is_system_account.is_(False),
    ).first()
    if user is None:
        return {
            "eligible": False,
            "governance_configured": True,
            "mode": "GOVERNED",
            "assignment_role": role,
            "user_id": user_id,
            "reason": "The selected auditor is inactive, belongs to another tenant, or does not exist.",
            "assessments": [],
        }

    rules = db.query(QualityPrivilegeRule).filter(
        QualityPrivilegeRule.amo_id == amo_id,
        QualityPrivilegeRule.is_active.is_(True),
        QualityPrivilegeRule.privilege_type == privilege_type,
    ).order_by(QualityPrivilegeRule.privilege_code.asc()).all()
    if not rules:
        return {
            "eligible": False,
            "governance_configured": False,
            "mode": "CONFIGURATION_REQUIRED",
            "assignment_role": role,
            "user_id": user_id,
            "reason": f"No active {privilege_type} Quality privilege rule is configured for this tenant. Configure governed auditor competence before assignment.",
            "assessments": [],
            "independence_pending": False,
        }

    assessments: list[dict[str, Any]] = []
    for rule in rules:
        privileges = db.query(QualityPrivilege).filter(
            QualityPrivilege.amo_id == amo_id,
            QualityPrivilege.rule_id == rule.id,
            QualityPrivilege.user_id == user_id,
            QualityPrivilege.privilege_code == rule.privilege_code,
            QualityPrivilege.status == "ACTIVE",
        ).order_by(QualityPrivilege.updated_at.desc()).all()
        privilege = next(
            (
                row
                for row in privileges
                if _privilege_scope_matches(row.scope_key, assignment_scope_key)
                and (row.effective_from is None or row.effective_from <= as_of)
                and (row.expires_on is None or row.expires_on >= as_of)
            ),
            None,
        )
        training = _training_evidence(
            db,
            amo_id=amo_id,
            user_id=user_id,
            required_codes=list(rule.required_training_course_codes or []),
            as_of=as_of,
        )
        capacity = _capacity_evidence(
            db,
            amo_id=amo_id,
            user_id=user_id,
            as_of=as_of,
            maximum=rule.max_concurrent_assignments,
            exclude_schedule_id=exclude_schedule_id,
        )
        independence = _independence_evidence(
            db,
            amo_id=amo_id,
            user_id=user_id,
            required=bool(rule.independence_required),
            context_type=context_type,
            context_id=context_id,
            enforce=enforce_independence,
        )
        developmental = _development_rule(rule, role)
        training_passed = bool(training["passed"]) or developmental
        hard_gates = {
            "workforce_active": True,
            "active_privilege": privilege is not None,
            "scope_authorized": privilege is not None,
            "training_current_verified": training_passed,
            "capacity": bool(capacity["passed"]),
            "independence": bool(independence["passed"]),
        }
        assessment = {
            "rule_id": str(rule.id),
            "privilege_code": rule.privilege_code,
            "privilege_type": rule.privilege_type,
            "developmental_assignment": developmental,
            "supervision_required": developmental,
            "hard_gates": hard_gates,
            "active_privilege": {
                "id": str(privilege.id),
                "scope_key": privilege.scope_key,
                "effective_from": privilege.effective_from.isoformat() if privilege and privilege.effective_from else None,
                "expires_on": privilege.expires_on.isoformat() if privilege and privilege.expires_on else None,
            } if privilege else None,
            "training": {
                **training,
                "passed": training_passed,
                "developmental_exception": developmental and not bool(training["passed"]),
            },
            "capacity": capacity,
            "independence": independence,
            "eligible": all(hard_gates.values()),
        }
        assessments.append(assessment)
        if assessment["eligible"]:
            return {
                "eligible": True,
                "governance_configured": True,
                "mode": "GOVERNED_DEVELOPMENT" if developmental else "GOVERNED",
                "assignment_role": role,
                "user_id": user_id,
                "rule_id": str(rule.id),
                "privilege_code": rule.privilege_code,
                "developmental_assignment": developmental,
                "supervision_required": developmental,
                "independence_pending": bool(independence.get("pending")),
                "assessment": assessment,
                "assessments": assessments,
            }

    return {
        "eligible": False,
        "governance_configured": True,
        "mode": "GOVERNED",
        "assignment_role": role,
        "user_id": user_id,
        "reason": "No configured Quality privilege rule passes every hard eligibility gate for this assignment.",
        "assessments": assessments,
        "independence_pending": any(bool(item.get("independence", {}).get("pending")) for item in assessments),
    }


def evaluate_schedule_auditors(
    db: Session,
    *,
    schedule: quality_models.QMSAuditSchedule,
    as_of: date,
    context_type: str,
    context_id: str,
    enforce_independence: bool,
    assignment_scope_key: str | None = None,
    exclude_schedule_id: str | None = None,
) -> dict[str, Any]:
    assignments = [
        ("LEAD_AUDITOR", schedule.lead_auditor_user_id),
        ("OBSERVER_AUDITOR", schedule.observer_auditor_user_id),
        ("ASSISTANT_AUDITOR", schedule.assistant_auditor_user_id),
    ]
    results = [
        evaluate_auditor_assignment(
            db,
            amo_id=str(schedule.amo_id),
            user_id=str(user_id),
            assignment_role=role,
            as_of=as_of,
            assignment_scope_key=assignment_scope_key,
            context_type=context_type,
            context_id=context_id,
            enforce_independence=enforce_independence,
            exclude_schedule_id=exclude_schedule_id,
        )
        for role, user_id in assignments
        if user_id
    ]
    return {
        "eligible": all(item["eligible"] for item in results),
        "governed_assignments": sum(1 for item in results if item.get("governance_configured")),
        "independence_pending": any(item.get("independence_pending") for item in results),
        "assignments": results,
    }
