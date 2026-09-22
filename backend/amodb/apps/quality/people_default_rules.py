"""Default Quality privilege rules provisioned for every tenant.

These three active rules are the minimum competence catalog for governed audit
assignment:

- Lead auditor → LEAD_AUDITOR assignments
- Observer / Trainee → OBSERVER_AUDITOR / ASSISTANT_AUDITOR (supervised development)
- Auditor → full AUDITOR competence (observer/assistant without developmental waiver)

Auditor / Lead training defaults to AND of QMS-INIT, QMS-REF, and QMS-ADMIN.
Tenants can override with an Advanced OR / mixed expression in scope_schema.
"""

from __future__ import annotations

from typing import Any

from sqlalchemy.orm import Session

from amodb.apps.training.integration import QMS_ADMIN, QMS_INIT, QMS_REF

from .people_models import QualityPrivilegeRule

_QMS_COMPETENCE_CODES = [QMS_INIT, QMS_REF, QMS_ADMIN]
_QMS_COMPETENCE_PACKAGE: dict[str, Any] = {
    "codes": list(_QMS_COMPETENCE_CODES),
    "join": "AND",
    "expression": "QMS-INIT AND QMS-REF AND QMS-ADMIN",
    # Legacy mirrors kept for older readers during rollout.
    "currency_any_of": [QMS_INIT, QMS_REF],
    "tracked_admin": QMS_ADMIN,
}

DEFAULT_QUALITY_PRIVILEGE_RULES: tuple[dict[str, Any], ...] = (
    {
        "privilege_code": "LEAD_AUDITOR_GLOBAL",
        "title": "Lead auditor",
        "privilege_type": "LEAD_AUDITOR",
        "description": "Default lead auditor competence for governed audit assignment.",
        "required_training_course_codes": [],
        "independence_required": True,
        "max_concurrent_assignments": None,
        "scope_schema": {"qms_competence": dict(_QMS_COMPETENCE_PACKAGE)},
    },
    {
        "privilege_code": "OBSERVER_TRAINEE_GLOBAL",
        "title": "Observer / Trainee",
        "privilege_type": "AUDITOR",
        "description": "Default supervised observer/trainee competence for developmental audit roles.",
        "required_training_course_codes": [],
        "independence_required": False,
        "max_concurrent_assignments": None,
        "scope_schema": {
            "supervised_development": True,
            "allowed_assignment_roles": ["OBSERVER_AUDITOR", "ASSISTANT_AUDITOR"],
        },
    },
    {
        "privilege_code": "AUDITOR_GLOBAL",
        "title": "Auditor",
        "privilege_type": "AUDITOR",
        "description": "Default auditor competence for observer/assistant assignment.",
        "required_training_course_codes": [],
        "independence_required": True,
        "max_concurrent_assignments": None,
        "scope_schema": {"qms_competence": dict(_QMS_COMPETENCE_PACKAGE)},
    },
)


def ensure_default_quality_privilege_rules(
    db: Session,
    *,
    amo_id: str,
    actor_user_id: str | None = None,
) -> list[QualityPrivilegeRule]:
    """Create missing default privilege rules for one tenant (idempotent).

    Existing rows with the same privilege_code are left unchanged so tenants can
    deactivate or retitle defaults without the portal forcing them back on.
    """

    ensured: list[QualityPrivilegeRule] = []
    for spec in DEFAULT_QUALITY_PRIVILEGE_RULES:
        code = str(spec["privilege_code"])
        row = (
            db.query(QualityPrivilegeRule)
            .filter(
                QualityPrivilegeRule.amo_id == amo_id,
                QualityPrivilegeRule.privilege_code == code,
            )
            .first()
        )
        if row is not None:
            ensured.append(row)
            continue
        row = QualityPrivilegeRule(
            amo_id=amo_id,
            privilege_code=code,
            title=str(spec["title"]),
            privilege_type=str(spec["privilege_type"]),
            description=spec.get("description"),
            required_training_course_codes=list(spec.get("required_training_course_codes") or []),
            independence_required=bool(spec.get("independence_required", True)),
            max_concurrent_assignments=spec.get("max_concurrent_assignments"),
            scope_schema=dict(spec.get("scope_schema") or {}),
            is_active=True,
            created_by_user_id=actor_user_id,
            updated_by_user_id=actor_user_id,
        )
        db.add(row)
        ensured.append(row)
    db.flush()
    sync_default_quality_privilege_rule_competence(db, amo_id=amo_id, actor_user_id=actor_user_id)
    return ensured


def sync_default_quality_privilege_rule_competence(
    db: Session,
    *,
    amo_id: str,
    actor_user_id: str | None = None,
) -> list[QualityPrivilegeRule]:
    """Backfill qms_competence onto default Auditor/Lead rules when missing.

    Does not overwrite tenant customizations of title, description, capacity, or
    an already-present qms_competence package. Observer/trainee stays
    supervised_development without a hard competence package.
    """

    updated: list[QualityPrivilegeRule] = []
    for code in ("LEAD_AUDITOR_GLOBAL", "AUDITOR_GLOBAL"):
        row = (
            db.query(QualityPrivilegeRule)
            .filter(
                QualityPrivilegeRule.amo_id == amo_id,
                QualityPrivilegeRule.privilege_code == code,
            )
            .first()
        )
        if row is None:
            continue
        scope = dict(row.scope_schema or {}) if isinstance(row.scope_schema, dict) else {}
        existing = scope.get("qms_competence")
        if isinstance(existing, dict) and (
            existing.get("codes")
            or existing.get("expression")
            or existing.get("currency_any_of")
            or existing.get("tracked_admin")
        ):
            continue
        scope["qms_competence"] = dict(_QMS_COMPETENCE_PACKAGE)
        row.scope_schema = scope
        if row.required_training_course_codes:
            normalized = {str(c).strip().upper() for c in (row.required_training_course_codes or [])}
            if normalized and normalized.issubset({QMS_INIT, QMS_REF, QMS_ADMIN}):
                row.required_training_course_codes = []
        row.updated_by_user_id = actor_user_id or row.updated_by_user_id
        updated.append(row)
    if updated:
        db.flush()
    return updated
