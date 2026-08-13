from __future__ import annotations

from datetime import datetime, timezone
from enum import Enum
from typing import Callable

from fastapi import Depends, HTTPException, status
from sqlalchemy import text
from sqlalchemy.orm import Session

from ...database import get_db
from ...security import get_current_active_user
from ..accounts import models as account_models


class TrainingCapability(str, Enum):
    VIEW = "training.view"
    SELF_VIEW = "training.self.view"
    PEOPLE_VIEW = "training.people.view"
    PEOPLE_MANAGE = "training.people.manage"
    COURSE_VIEW = "training.course.view"
    COURSE_MANAGE = "training.course.manage"
    REQUIREMENT_VIEW = "training.requirement.view"
    REQUIREMENT_MANAGE = "training.requirement.manage"
    PLAN_VIEW = "training.plan.view"
    PLAN_MANAGE = "training.plan.manage"
    PLAN_REVIEW = "training.plan.review"
    PLAN_APPROVE = "training.plan.approve"
    BUDGET_VIEW = "training.budget.view"
    BUDGET_MANAGE = "training.budget.manage"
    BUDGET_REVIEW = "training.budget.review"
    BUDGET_APPROVE = "training.budget.approve"
    SESSION_VIEW = "training.session.view"
    SESSION_MANAGE = "training.session.manage"
    SESSION_CLOSE = "training.session.close"
    ATTENDANCE_VIEW = "training.attendance.view"
    ATTENDANCE_SIGN_SELF = "training.attendance.sign_self"
    ATTENDANCE_MANAGE = "training.attendance.manage"
    ATTENDANCE_CORRECT = "training.attendance.correct"
    ASSESSMENT_VIEW = "training.assessment.view"
    ASSESSMENT_CREATE = "training.assessment.create"
    ASSESSMENT_PERFORM = "training.assessment.perform"
    ASSESSMENT_REVIEW = "training.assessment.review"
    ASSESSMENT_APPROVE = "training.assessment.approve"
    AUTHORIZATION_VIEW = "training.authorization.view"
    AUTHORIZATION_PREPARE = "training.authorization.prepare"
    AUTHORIZATION_RECOMMEND = "training.authorization.recommend"
    AUTHORIZATION_COMMITTEE_DECIDE = "training.authorization.committee_decide"
    AUTHORIZATION_ISSUE = "training.authorization.issue"
    AUTHORIZATION_RENEW = "training.authorization.renew"
    AUTHORIZATION_RESTRICT = "training.authorization.restrict"
    AUTHORIZATION_WITHDRAW = "training.authorization.withdraw"
    CERTIFICATE_VIEW = "training.certificate.view"
    CERTIFICATE_ISSUE = "training.certificate.issue"
    CERTIFICATE_REVOKE = "training.certificate.revoke"
    CERTIFICATE_REISSUE = "training.certificate.reissue"
    REPORT_VIEW = "training.report.view"
    REPORT_EXPORT = "training.report.export"
    SETTINGS_MANAGE = "training.settings.manage"


ALL_TRAINING_CAPABILITIES = {item.value for item in TrainingCapability}

_SELF = {
    TrainingCapability.SELF_VIEW.value,
    TrainingCapability.ATTENDANCE_SIGN_SELF.value,
    TrainingCapability.CERTIFICATE_VIEW.value,
}

_READ = _SELF | {
    TrainingCapability.VIEW.value,
    TrainingCapability.PEOPLE_VIEW.value,
    TrainingCapability.COURSE_VIEW.value,
    TrainingCapability.REQUIREMENT_VIEW.value,
    TrainingCapability.PLAN_VIEW.value,
    TrainingCapability.BUDGET_VIEW.value,
    TrainingCapability.SESSION_VIEW.value,
    TrainingCapability.ATTENDANCE_VIEW.value,
    TrainingCapability.ASSESSMENT_VIEW.value,
    TrainingCapability.AUTHORIZATION_VIEW.value,
    TrainingCapability.REPORT_VIEW.value,
}

_TRAINING_OFFICER = _READ | {
    TrainingCapability.PEOPLE_MANAGE.value,
    TrainingCapability.COURSE_MANAGE.value,
    TrainingCapability.REQUIREMENT_MANAGE.value,
    TrainingCapability.PLAN_MANAGE.value,
    TrainingCapability.BUDGET_MANAGE.value,
    TrainingCapability.SESSION_MANAGE.value,
    TrainingCapability.ATTENDANCE_MANAGE.value,
    TrainingCapability.ASSESSMENT_CREATE.value,
    TrainingCapability.ASSESSMENT_PERFORM.value,
    TrainingCapability.AUTHORIZATION_PREPARE.value,
    TrainingCapability.CERTIFICATE_ISSUE.value,
    TrainingCapability.REPORT_EXPORT.value,
}

_QUALITY_REVIEW = _READ | {
    TrainingCapability.PLAN_REVIEW.value,
    TrainingCapability.BUDGET_REVIEW.value,
    TrainingCapability.SESSION_CLOSE.value,
    TrainingCapability.ATTENDANCE_MANAGE.value,
    TrainingCapability.ATTENDANCE_CORRECT.value,
    TrainingCapability.ASSESSMENT_CREATE.value,
    TrainingCapability.ASSESSMENT_PERFORM.value,
    TrainingCapability.ASSESSMENT_REVIEW.value,
    TrainingCapability.ASSESSMENT_APPROVE.value,
    TrainingCapability.AUTHORIZATION_PREPARE.value,
    TrainingCapability.AUTHORIZATION_RECOMMEND.value,
    TrainingCapability.AUTHORIZATION_COMMITTEE_DECIDE.value,
    TrainingCapability.CERTIFICATE_ISSUE.value,
    TrainingCapability.CERTIFICATE_REVOKE.value,
    TrainingCapability.CERTIFICATE_REISSUE.value,
    TrainingCapability.REPORT_EXPORT.value,
}


def _role_value(user: account_models.User) -> str:
    raw = getattr(getattr(user, "role", None), "value", getattr(user, "role", ""))
    return str(raw or "").strip().upper()


def _department_code(user: account_models.User) -> str:
    department = getattr(user, "department", None)
    code = getattr(department, "code", "") if department is not None else ""
    return str(code or "").strip().upper().replace("_", "-")


def _position_title(user: account_models.User) -> str:
    return str(getattr(user, "position_title", "") or "").strip().lower()


def tenant_id_for(user: account_models.User) -> str:
    value = getattr(user, "effective_amo_id", None) or getattr(user, "amo_id", None)
    if not value:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Select an AMO tenant before accessing Training & Competence.",
        )
    return str(value)


def default_training_capabilities(user: account_models.User) -> set[str]:
    """Compatibility defaults while database-backed Training roles are rolled out.

    These grants are deliberately Training-only. They never elevate a Training
    department user to AMO Admin or grant unrelated QMS capabilities.
    """

    if not user or getattr(user, "is_system_account", False):
        return set()
    if getattr(user, "is_amo_admin", False) or _role_value(user) == "AMO_ADMIN":
        return set(ALL_TRAINING_CAPABILITIES)

    role = _role_value(user)
    department = _department_code(user)
    position = _position_title(user)

    if role == "QUALITY_MANAGER":
        return set(ALL_TRAINING_CAPABILITIES)
    if role in {"QUALITY_INSPECTOR", "AUDITOR"}:
        return set(_QUALITY_REVIEW)
    if department in {"QUALITY", "QUALITY-ASSURANCE"}:
        return set(_QUALITY_REVIEW)
    if department in {"TRAINING", "TRAINING-AND-COMPETENCE", "TRAINING-&-COMPETENCE"}:
        manager = any(token in position for token in ("head", "manager", "lead"))
        return set(ALL_TRAINING_CAPABILITIES if manager else _TRAINING_OFFICER)
    if role in {"FINANCE_MANAGER", "ACCOUNTS_OFFICER"}:
        return _SELF | {
            TrainingCapability.VIEW.value,
            TrainingCapability.PLAN_VIEW.value,
            TrainingCapability.BUDGET_VIEW.value,
            TrainingCapability.BUDGET_REVIEW.value,
            TrainingCapability.BUDGET_APPROVE.value,
            TrainingCapability.REPORT_VIEW.value,
            TrainingCapability.REPORT_EXPORT.value,
        }
    if any(token in position for token in ("assessor", "instructor", "trainer")):
        return _SELF | {
            TrainingCapability.VIEW.value,
            TrainingCapability.PEOPLE_VIEW.value,
            TrainingCapability.SESSION_VIEW.value,
            TrainingCapability.ATTENDANCE_VIEW.value,
            TrainingCapability.ASSESSMENT_VIEW.value,
            TrainingCapability.ASSESSMENT_PERFORM.value,
        }
    return set(_SELF)


def _platform_support_session_active(db: Session, *, user: account_models.User, amo_id: str) -> bool:
    if not getattr(user, "is_superuser", False):
        return True
    if db.get_bind().dialect.name != "postgresql":
        return False
    try:
        return bool(
            db.execute(
                text(
                    """
                    SELECT 1
                    FROM platform_tenant_support_sessions
                    WHERE tenant_id = :amo_id
                      AND platform_user_id = :user_id
                      AND status = 'ACTIVE'
                      AND expires_at > NOW()
                      AND ended_at IS NULL
                    LIMIT 1
                    """
                ),
                {"amo_id": amo_id, "user_id": str(user.id)},
            ).first()
        )
    except Exception:
        return False


def _database_capabilities(db: Session, *, user: account_models.User, amo_id: str) -> set[str]:
    if db.get_bind().dialect.name != "postgresql":
        return set()
    try:
        rows = db.execute(
            text(
                """
                SELECT DISTINCT cd.code
                FROM auth_user_role_assignments ura
                JOIN auth_role_capability_bindings rcb ON rcb.role_id = ura.role_id
                JOIN auth_capability_definitions cd ON cd.id = rcb.capability_id
                WHERE ura.amo_id = :amo_id
                  AND ura.user_id = :user_id
                  AND cd.module = 'training'
                  AND (ura.valid_from IS NULL OR ura.valid_from <= NOW())
                  AND (ura.valid_to IS NULL OR ura.valid_to >= NOW())
                """
            ),
            {"amo_id": amo_id, "user_id": str(user.id)},
        ).fetchall()
    except Exception:
        return set()
    return {str(row[0]) for row in rows if row and row[0]}


def training_capabilities_for(db: Session, *, user: account_models.User) -> set[str]:
    amo_id = tenant_id_for(user)
    if getattr(user, "is_superuser", False):
        if not _platform_support_session_active(db, user=user, amo_id=amo_id):
            return set()
        return set(ALL_TRAINING_CAPABILITIES)

    if db.get_bind().dialect.name == "postgresql":
        db.execute(text("SELECT set_config('app.tenant_id', :amo_id, true)"), {"amo_id": amo_id})
        db.execute(text("SELECT set_config('app.user_id', :user_id, true)"), {"user_id": str(user.id)})
    return default_training_capabilities(user) | _database_capabilities(db, user=user, amo_id=amo_id)


def has_training_capability(
    db: Session,
    *,
    user: account_models.User,
    capability: TrainingCapability | str,
) -> bool:
    code = capability.value if isinstance(capability, TrainingCapability) else str(capability)
    return code in training_capabilities_for(db, user=user)


def require_training_capability(
    capability: TrainingCapability | str,
) -> Callable[[account_models.User, Session], account_models.User]:
    code = capability.value if isinstance(capability, TrainingCapability) else str(capability)

    def dependency(
        current_user: account_models.User = Depends(get_current_active_user),
        db: Session = Depends(get_db),
    ) -> account_models.User:
        if not has_training_capability(db, user=current_user, capability=code):
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail={
                    "code": "TRAINING_CAPABILITY_REQUIRED",
                    "message": f"This action requires the '{code}' Training capability.",
                    "capability": code,
                },
            )
        return current_user

    return dependency


def require_not_self_approval(*, actor_user_id: str, originator_user_id: str | None, action: str) -> None:
    if originator_user_id and str(originator_user_id) == str(actor_user_id):
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail={
                "code": "SEGREGATION_OF_DUTIES",
                "message": f"You cannot {action} a governed record that you originated.",
            },
        )


def utcnow() -> datetime:
    return datetime.now(timezone.utc)
