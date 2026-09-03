"""Default Quality privilege rules provisioned for every tenant.

These three active rules are the minimum competence catalog for governed audit
assignment:

- Lead auditor → LEAD_AUDITOR assignments
- Observer / Trainee → OBSERVER_AUDITOR / ASSISTANT_AUDITOR (supervised development)
- Auditor → full AUDITOR competence (observer/assistant without developmental waiver)
"""

from __future__ import annotations

from typing import Any

from sqlalchemy.orm import Session

from .people_models import QualityPrivilegeRule

DEFAULT_QUALITY_PRIVILEGE_RULES: tuple[dict[str, Any], ...] = (
    {
        "privilege_code": "LEAD_AUDITOR_GLOBAL",
        "title": "Lead auditor",
        "privilege_type": "LEAD_AUDITOR",
        "description": "Default lead auditor competence for governed audit assignment.",
        "required_training_course_codes": [],
        "independence_required": True,
        "max_concurrent_assignments": None,
        "scope_schema": {},
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
        "scope_schema": {},
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
    return ensured
