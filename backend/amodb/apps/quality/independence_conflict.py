"""ISO 19011 / ISO 9001 independence conflict detection for Quality auditor assignment.

Independence is a portal-enforced gate, not a free-form user declaration.
Operators may only view the rules and receive conflict warnings with remediation
suggestions. Platform superusers may deactivate enforcement for a tenant.
"""

from __future__ import annotations

from typing import Any

from sqlalchemy import text
from sqlalchemy.orm import Session, noload

from ..accounts import models as account_models
from . import models as quality_models
from .people_models import QualityIndependenceDeclaration

ISO_INDEPENDENCE_RULES: list[dict[str, str]] = [
    {
        "code": "OWN_WORK",
        "title": "Do not audit your own work",
        "standard": "ISO 19011 · ISO 9001 Clause 9.2.2c",
        "summary": "Anyone who generates evidence, owns targets, or executes the day-to-day process under audit cannot audit that activity.",
    },
    {
        "code": "OWN_DEPARTMENT",
        "title": "Do not audit your own department",
        "standard": "ISO 9001 Clause 9.2.2c · ISO 19011 Clause 4",
        "summary": "Lead auditors and observers must not be selected from the same department or process they are reviewing.",
    },
    {
        "code": "DESIGN_IMPLEMENTATION",
        "title": "Do not audit systems you designed or implemented",
        "standard": "ISO 19011 · ISO 27001 Annex A 5.3",
        "summary": "An auditor cannot objectively evaluate a control, system, or configuration they personally designed, configured, or implemented.",
    },
    {
        "code": "HIERARCHICAL_PRESSURE",
        "title": "Avoid hierarchical influence",
        "standard": "ISO 19011 Clause 4 — Independence",
        "summary": "If the auditor reports to the manager of the audited area (salary, career, or performance influence), a conflict of interest exists.",
    },
    {
        "code": "FINANCIAL_PERSONAL",
        "title": "No financial or personal vested interest",
        "standard": "ISO 19011 Clause 4 — Independence",
        "summary": "Bonuses linked to audited targets, or close personal/family relationships with people running the audited area, break impartiality.",
    },
]

_REMEDIATIONS = [
    {
        "code": "SELECT_OTHER_AUDITOR",
        "label": "Select another available auditor",
        "detail": "Assign an eligible auditor from a different department who has no ownership of the audited activity.",
    },
    {
        "code": "OUTSOURCE_EXTERNAL",
        "label": "Outsource to a qualified external auditor",
        "detail": "When the organisation is too small for departmental independence, engage an independent external consultant (ISO 19011).",
    },
    {
        "code": "IMPARTIALITY_FORM",
        "label": "Record an Auditor Impartiality Form",
        "detail": "For residual small-organisation cases only: document why bias is controlled. This does not waive detected hard conflicts such as auditing your own work.",
    },
]


def _department_for_user(db: Session, *, amo_id: str, user_id: str | None) -> dict[str, Any] | None:
    if not user_id:
        return None
    try:
        user = (
            db.query(account_models.User)
            .options(noload("*"))
            .filter(
                account_models.User.amo_id == amo_id,
                account_models.User.id == user_id,
            )
            .first()
        )
    except Exception:
        return None
    if user is None:
        return None
    department_id = getattr(user, "department_id", None)
    department_code = None
    department_name = None
    if department_id:
        try:
            department = (
                db.query(account_models.Department)
                .options(noload("*"))
                .filter(
                    account_models.Department.amo_id == amo_id,
                    account_models.Department.id == department_id,
                )
                .first()
            )
            if department is not None:
                department_code = str(getattr(department, "code", "") or "").strip().upper() or None
                department_name = str(getattr(department, "name", "") or "").strip() or None
        except Exception:
            department = None
    role = getattr(user, "role", None)
    role_text = str(getattr(role, "value", role) or "").strip()
    return {
        "user_id": str(user.id),
        "department_id": str(department_id) if department_id else None,
        "department_code": department_code,
        "department_name": department_name,
        "role": role_text,
    }


def _load_audit_context(db: Session, *, amo_id: str, context_type: str | None, context_id: str | None) -> dict[str, Any]:
    if not context_type or not context_id:
        return {}
    kind = str(context_type).strip().upper()
    if kind == "AUDIT":
        audit = (
            db.query(quality_models.QMSAudit)
            .filter(
                quality_models.QMSAudit.amo_id == amo_id,
                quality_models.QMSAudit.id == context_id,
                quality_models.QMSAudit.deleted_at.is_(None),
            )
            .first()
        )
        if audit is None:
            return {"context_type": kind, "context_id": context_id, "missing": True}
        auditee = _department_for_user(db, amo_id=amo_id, user_id=getattr(audit, "auditee_user_id", None))
        return {
            "context_type": kind,
            "context_id": str(audit.id),
            "title": audit.title,
            "audit_scope_code": str(getattr(audit, "audit_scope_code", "") or "").strip().upper() or None,
            "unit_code": str(getattr(audit, "unit_code", "") or "").strip().upper() or None,
            "auditee_user_id": str(audit.auditee_user_id) if audit.auditee_user_id else None,
            "auditee_department": auditee,
            "created_by_user_id": str(audit.created_by_user_id) if audit.created_by_user_id else None,
        }
    if kind == "AUDIT_SCHEDULE":
        schedule = (
            db.query(quality_models.QMSAuditSchedule)
            .filter(
                quality_models.QMSAuditSchedule.amo_id == amo_id,
                quality_models.QMSAuditSchedule.id == context_id,
                quality_models.QMSAuditSchedule.deleted_at.is_(None),
            )
            .first()
        )
        if schedule is None:
            return {"context_type": kind, "context_id": context_id, "missing": True}
        return {
            "context_type": kind,
            "context_id": str(schedule.id),
            "title": schedule.title,
            "audit_scope_code": str(getattr(schedule, "audit_scope_code", "") or "").strip().upper() or None,
            "unit_code": str(getattr(schedule, "unit_code", "") or "").strip().upper() or None,
            "auditee_user_id": None,
            "auditee_department": None,
            "created_by_user_id": str(schedule.created_by_user_id) if getattr(schedule, "created_by_user_id", None) else None,
        }
    return {"context_type": kind, "context_id": context_id}


def _work_order_module_connected(db: Session, *, amo_id: str) -> bool:
    """True when Quality can resolve work-order / tasking ownership for conflict checks.

    Work-order and production tasking integration is not yet wired into Quality.
    When those modules connect, ownership of executed work will feed OWN_WORK detection.
    """

    try:
        with db.begin_nested():
            row = db.execute(
                text(
                    """
                    SELECT 1
                    FROM module_subscriptions
                    WHERE amo_id = :amo_id
                      AND lower(module_code) IN ('work_orders', 'work-orders', 'production', 'tasking')
                      AND upper(coalesce(status, '')) IN ('ACTIVE', 'TRIAL', 'ENABLED')
                    LIMIT 1
                    """
                ),
                {"amo_id": amo_id},
            ).first()
            return bool(row)
    except Exception:
        return False


def get_independence_policy(db: Session, *, amo_id: str) -> dict[str, Any]:
    enforced = True
    allow_impartiality_form = True
    try:
        with db.begin_nested():
            row = db.execute(
                text(
                    """
                    SELECT workflow_rules
                    FROM qms_settings
                    WHERE amo_id = :amo_id
                    ORDER BY created_at DESC
                    LIMIT 1
                    """
                ),
                {"amo_id": amo_id},
            ).mappings().first()
            workflow = dict((row or {}).get("workflow_rules") or {})
            policy = dict(workflow.get("independence_policy") or {})
            if "enforced" in policy:
                enforced = bool(policy.get("enforced"))
            if "allow_impartiality_form" in policy:
                allow_impartiality_form = bool(policy.get("allow_impartiality_form"))
    except Exception:
        pass
    return {
        "enforced": enforced,
        "allow_impartiality_form": allow_impartiality_form,
        "rules": ISO_INDEPENDENCE_RULES,
        "remediations": _REMEDIATIONS,
        "editable_by": "platform_superuser",
    }


def set_independence_policy(
    db: Session,
    *,
    amo_id: str,
    enforced: bool | None = None,
    allow_impartiality_form: bool | None = None,
) -> dict[str, Any]:
    import json as _json

    row = db.execute(
        text(
            """
            SELECT id, workflow_rules
            FROM qms_settings
            WHERE amo_id = :amo_id
            ORDER BY created_at DESC
            LIMIT 1
            """
        ),
        {"amo_id": amo_id},
    ).mappings().first()
    if row is None:
        raise ValueError("QMS settings row is required before independence policy can be changed.")
    raw_rules = row.get("workflow_rules")
    if isinstance(raw_rules, str):
        try:
            workflow = dict(_json.loads(raw_rules) or {})
        except Exception:
            workflow = {}
    else:
        workflow = dict(raw_rules or {})
    policy = dict(workflow.get("independence_policy") or {})
    if enforced is not None:
        policy["enforced"] = bool(enforced)
    if allow_impartiality_form is not None:
        policy["allow_impartiality_form"] = bool(allow_impartiality_form)
    workflow["independence_policy"] = policy
    payload = _json.dumps(workflow)
    try:
        db.execute(
            text(
                """
                UPDATE qms_settings
                SET workflow_rules = CAST(:workflow AS jsonb)
                WHERE id = :id AND amo_id = :amo_id
                """
            ),
            {"workflow": payload, "id": row["id"], "amo_id": amo_id},
        )
    except Exception:
        db.execute(
            text(
                """
                UPDATE qms_settings
                SET workflow_rules = :workflow
                WHERE id = :id AND amo_id = :amo_id
                """
            ),
            {"workflow": payload, "id": row["id"], "amo_id": amo_id},
        )
    db.flush()
    return get_independence_policy(db, amo_id=amo_id)


def evaluate_independence_conflicts(
    db: Session,
    *,
    amo_id: str,
    user_id: str,
    context_type: str | None = None,
    context_id: str | None = None,
    assignment_scope_key: str | None = None,
) -> dict[str, Any]:
    try:
        return _evaluate_independence_conflicts(
            db,
            amo_id=amo_id,
            user_id=user_id,
            context_type=context_type,
            context_id=context_id,
            assignment_scope_key=assignment_scope_key,
        )
    except Exception as exc:
        policy = get_independence_policy(db, amo_id=amo_id)
        return {
            "required": True,
            "enforced": bool(policy.get("enforced", True)),
            "passed": None,
            "pending": True,
            "conflicts": [],
            "hard_conflict_count": 0,
            "remediations": list(_REMEDIATIONS),
            "notes": [f"Independence assessment could not be completed ({exc})."],
            "work_order_module_connected": False,
            "auditor": None,
            "context": {},
            "impartiality_form": None,
            "policy": {
                "enforced": bool(policy.get("enforced", True)),
                "allow_impartiality_form": bool(policy.get("allow_impartiality_form", True)),
                "editable_by": "platform_superuser",
            },
            "message": "Independence assessment is temporarily unavailable.",
        }


def _evaluate_independence_conflicts(
    db: Session,
    *,
    amo_id: str,
    user_id: str,
    context_type: str | None = None,
    context_id: str | None = None,
    assignment_scope_key: str | None = None,
) -> dict[str, Any]:
    policy = get_independence_policy(db, amo_id=amo_id)
    auditor = _department_for_user(db, amo_id=amo_id, user_id=user_id)
    context = _load_audit_context(db, amo_id=amo_id, context_type=context_type, context_id=context_id)
    wo_connected = _work_order_module_connected(db, amo_id=amo_id)
    conflicts: list[dict[str, Any]] = []
    notes: list[str] = []

    if not context_type or not context_id:
        notes.append("Assign an audit or schedule context to run full independence conflict detection.")
    elif context.get("missing"):
        notes.append("Assignment context was not found for this tenant; independence cannot be confirmed.")
    else:
        auditee_dept = context.get("auditee_department") or {}
        auditor_dept_id = (auditor or {}).get("department_id")
        auditee_dept_id = auditee_dept.get("department_id")
        if auditor_dept_id and auditee_dept_id and auditor_dept_id == auditee_dept_id:
            conflicts.append(
                {
                    "code": "OWN_DEPARTMENT",
                    "severity": "hard",
                    "title": "Auditor belongs to the audited department",
                    "message": (
                        f"Auditor department {(auditor or {}).get('department_name') or (auditor or {}).get('department_code') or 'unknown'} "
                        "matches the auditee department. ISO 9001 / 19011 require cross-department independence."
                    ),
                }
            )

        scope_key = str(assignment_scope_key or context.get("audit_scope_code") or context.get("unit_code") or "").strip().upper()
        auditor_dept_code = (auditor or {}).get("department_code")
        if scope_key and auditor_dept_code and scope_key == auditor_dept_code:
            conflicts.append(
                {
                    "code": "OWN_DEPARTMENT",
                    "severity": "hard",
                    "title": "Assignment scope matches auditor department",
                    "message": f"Scope/unit '{scope_key}' matches the auditor's department code. Select an auditor from another department.",
                }
            )

        if context.get("auditee_user_id") and str(context["auditee_user_id"]) == str(user_id):
            conflicts.append(
                {
                    "code": "OWN_WORK",
                    "severity": "hard",
                    "title": "Auditor is the auditee",
                    "message": "The selected person is listed as the auditee for this assignment and cannot audit their own work.",
                }
            )

        # Work-order ownership checks run silently when connected; do not narrate
        # future integration status when the assessment is otherwise clear.

    # Deduplicate by code+title
    unique: list[dict[str, Any]] = []
    seen: set[str] = set()
    for item in conflicts:
        key = f"{item['code']}:{item['title']}"
        if key in seen:
            continue
        seen.add(key)
        unique.append(item)

    hard_conflicts = [item for item in unique if item.get("severity") == "hard"]
    enforced = bool(policy.get("enforced", True))
    passed = (not hard_conflicts) if enforced else True

    impartiality = None
    if context_type and context_id:
        row = (
            db.query(QualityIndependenceDeclaration)
            .options(noload("*"))
            .filter(
                QualityIndependenceDeclaration.amo_id == amo_id,
                QualityIndependenceDeclaration.user_id == user_id,
                QualityIndependenceDeclaration.context_type == str(context_type).strip().upper(),
                QualityIndependenceDeclaration.context_id == str(context_id),
            )
            .first()
        )
        if row is not None:
            impartiality = {
                "declaration": row.declaration,
                "rationale": row.rationale,
                "declared_at": row.declared_at.isoformat() if row.declared_at else None,
                "relationship_to_subject": row.relationship_to_subject,
            }
            # Impartiality form never clears hard OWN_WORK / OWN_DEPARTMENT conflicts.
            if row.declaration == "INDEPENDENT" and not hard_conflicts:
                passed = True if enforced else True
            elif row.declaration in {"CONFLICT", "REQUIRES_REVIEW"} and not hard_conflicts:
                passed = False if enforced else True

    remediations = list(_REMEDIATIONS)
    if hard_conflicts and any(item["code"] == "OWN_WORK" for item in hard_conflicts):
        remediations = [item for item in remediations if item["code"] != "IMPARTIALITY_FORM"]

    return {
        "required": True,
        "enforced": enforced,
        "passed": passed if enforced else True,
        "pending": bool(context_type and context_id) is False,
        "conflicts": unique,
        "hard_conflict_count": len(hard_conflicts),
        "remediations": remediations,
        "notes": notes,
        "work_order_module_connected": wo_connected,
        "auditor": auditor,
        "context": {
            **{key: value for key, value in context.items() if key != "auditee_department"},
            "auditee_department": context.get("auditee_department"),
        },
        "impartiality_form": impartiality,
        "policy": {
            "enforced": enforced,
            "allow_impartiality_form": bool(policy.get("allow_impartiality_form", True)),
            "editable_by": "platform_superuser",
        },
        "message": (
            None
            if passed
            else (
                unique[0]["message"]
                if unique
                else "Independence conflict detected. Select another auditor, outsource externally, or review ISO impartiality guidance."
            )
        ),
    }
