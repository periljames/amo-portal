from __future__ import annotations

from datetime import date
from typing import Any

from fastapi import HTTPException
from sqlalchemy import or_
from sqlalchemy.orm import Session, noload

from amodb.apps.accounts import models as account_models

from . import models
from . import record_lifecycle


def _enum_text(value: Any) -> str:
    return str(getattr(value, "value", value) or "").strip().upper()


def _requirements_for_source(
    db: Session,
    *,
    amo_id: str,
    source_type: str,
    source_id: str,
    as_of: date,
) -> list[models.TrainingRequirement]:
    return (
        db.query(models.TrainingRequirement)
        .options(noload("*"))
        .filter(
            models.TrainingRequirement.amo_id == amo_id,
            models.TrainingRequirement.source_type == source_type,
            models.TrainingRequirement.source_id == source_id,
            models.TrainingRequirement.blocking.is_(True),
            models.TrainingRequirement.is_active.is_(True),
            models.TrainingRequirement.is_mandatory.is_(True),
            or_(models.TrainingRequirement.effective_from.is_(None), models.TrainingRequirement.effective_from <= as_of),
            or_(models.TrainingRequirement.effective_to.is_(None), models.TrainingRequirement.effective_to >= as_of),
        )
        .all()
    )


def _target_users(
    db: Session,
    *,
    amo_id: str,
    requirements: list[models.TrainingRequirement],
) -> tuple[dict[str, account_models.User], dict[str, set[str]], list[dict[str, str]]]:
    rows = (
        db.query(account_models.User)
        .filter(
            account_models.User.amo_id == amo_id,
            account_models.User.is_active.is_(True),
            account_models.User.is_system_account.is_(False),
        )
        .all()
    )
    users = {str(row.id): row for row in rows}
    targets: dict[str, set[str]] = {}
    malformed: list[dict[str, str]] = []
    for requirement in requirements:
        scope = _enum_text(requirement.scope)
        selected: set[str] = set()
        if scope == "ALL":
            selected = set(users)
        elif scope == "USER" and requirement.user_id:
            if str(requirement.user_id) in users:
                selected.add(str(requirement.user_id))
        elif scope == "DEPARTMENT" and requirement.department_code:
            required_code = str(requirement.department_code).strip().upper()
            selected = {
                user_id
                for user_id, user in users.items()
                if str(getattr(getattr(user, "department", None), "code", "") or "").strip().upper() == required_code
            }
        elif scope == "JOB_ROLE" and requirement.job_role:
            required_role = str(requirement.job_role).strip().casefold()
            selected = {
                user_id
                for user_id, user in users.items()
                if str(getattr(user, "position_title", "") or "").strip().casefold() == required_role
            }
        if not selected:
            malformed.append({"requirement_id": str(requirement.id), "reason": "NO_ACTIVE_TARGETS"})
        targets[str(requirement.id)] = selected
    return users, targets, malformed


def unresolved_training_gate_items(
    db: Session,
    *,
    amo_id: str,
    source_type: str,
    source_id: str,
    as_of: date | None = None,
) -> list[dict[str, str]]:
    """Return missing/expired evidence for one governed QMS or DMS source."""

    as_of = as_of or date.today()
    requirements = _requirements_for_source(
        db,
        amo_id=amo_id,
        source_type=source_type,
        source_id=source_id,
        as_of=as_of,
    )
    if not requirements:
        return []

    users, targets, unresolved = _target_users(db, amo_id=amo_id, requirements=requirements)
    user_ids = sorted({user_id for values in targets.values() for user_id in values})
    course_ids = sorted({str(row.course_id) for row in requirements})
    current_pairs: set[tuple[str, str]] = set()
    if user_ids and course_ids:
        current_pairs = {
            (str(user_id), str(course_id))
            for user_id, course_id in db.query(
                models.TrainingRecord.user_id,
                models.TrainingRecord.course_id,
            ).filter(
                models.TrainingRecord.amo_id == amo_id,
                models.TrainingRecord.user_id.in_(user_ids),
                models.TrainingRecord.course_id.in_(course_ids),
                models.TrainingRecord.verification_status == models.TrainingRecordVerificationStatus.VERIFIED,
                record_lifecycle.active_records_filter(models.TrainingRecord),
                or_(models.TrainingRecord.valid_until.is_(None), models.TrainingRecord.valid_until >= as_of),
            ).distinct().all()
        }

    for requirement in requirements:
        course_id = str(requirement.course_id)
        for user_id in sorted(targets.get(str(requirement.id), set())):
            if (user_id, course_id) in current_pairs:
                continue
            user = users[user_id]
            unresolved.append(
                {
                    "requirement_id": str(requirement.id),
                    "course_id": course_id,
                    "user_id": user_id,
                    "person": str(user.full_name or user.email or user.staff_code or user_id),
                    "reason": "CURRENT_VERIFIED_EVIDENCE_REQUIRED",
                }
            )
    return unresolved


def _enforce_source_gate(db: Session, *, amo_id: str, source_type: str, source_id: str, label: str) -> None:
    unresolved = unresolved_training_gate_items(
        db,
        amo_id=amo_id,
        source_type=source_type,
        source_id=source_id,
    )
    if unresolved:
        raise HTTPException(
            status_code=409,
            detail={
                "code": "TRAINING_GATE_BLOCKED",
                "message": f"{label} is blocked until required personnel training is current and verified.",
                "unresolved_count": len(unresolved),
                "items": unresolved[:25],
            },
        )


def ensure_revision_training_gate_satisfied(db: Session, *, amo_id: str, package) -> None:
    if not bool(getattr(package, "requires_training", False)):
        return
    if str(getattr(package, "training_gate_policy", "NONE") or "NONE").upper() == "NONE":
        return
    source_id = str(getattr(package, "package_id", "") or "")
    if not source_id:
        raise HTTPException(status_code=409, detail={"code": "TRAINING_GATE_SOURCE_MISSING", "message": "Revision package identity is missing."})
    _enforce_source_gate(db, amo_id=amo_id, source_type="REVISION", source_id=source_id, label="Document publication")


def ensure_finding_training_gate_satisfied(db: Session, *, amo_id: str, finding_id: str) -> None:
    _enforce_source_gate(db, amo_id=amo_id, source_type="FINDING", source_id=str(finding_id), label="Finding closure")
