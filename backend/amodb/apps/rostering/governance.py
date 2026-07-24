# backend/amodb/apps/rostering/governance.py
from __future__ import annotations

from datetime import date
from typing import Iterable, Optional

from sqlalchemy import and_, or_
from sqlalchemy.orm import Session

from ..accounts import models as account_models
from ..workforce import models as workforce_models
from ..workforce import permissions as workforce_permissions
from . import common, models, schemas


DEFAULT_RULE_SET_CODE = "KCAR2025_MOPM_1_6_2"


def _value(value) -> str:
    return str(getattr(value, "value", value))


def _today() -> date:
    return date.today()


def _scope_key(base_station_id: Optional[str], department_id: Optional[str]) -> tuple[str, str]:
    return (str(base_station_id or ""), str(department_id or ""))


def _active_window(query, model):
    today = _today()
    return query.filter(
        or_(model.effective_from.is_(None), model.effective_from <= today),
        or_(model.effective_to.is_(None), model.effective_to >= today),
    )


def seed_default_rule_set(db: Session, *, amo_id: str, actor_user_id: Optional[str] = None) -> models.RosterRuleSet:
    row = db.query(models.RosterRuleSet).filter(
        models.RosterRuleSet.amo_id == amo_id,
        models.RosterRuleSet.code == DEFAULT_RULE_SET_CODE,
    ).first()
    if row:
        return row
    row = models.RosterRuleSet(
        amo_id=amo_id,
        code=DEFAULT_RULE_SET_CODE,
        name="KCAR 2025 transition and MoPM shift-roster baseline",
        version_label="2025 operational baseline",
        regulatory_basis=(
            "KCAA 2025 regulatory transition obligations; numerical working-time controls remain "
            "configurable and are sourced from the approved MoPM and applicable Kenyan employment law."
        ),
        manual_reference="MoPM Part 1, section 1.6.2 — Shift Roster; controlled roster form SL/MCM/27",
        description=(
            "Tenant baseline for maintenance duty planning. It records the approved manual basis, "
            "hours, rest, shift length and departmental exceptions without hard-coding a single "
            "aircraft, base or department operating model."
        ),
        priority=100,
        is_active=True,
        created_by_user_id=actor_user_id,
        updated_by_user_id=actor_user_id,
    )
    db.add(row)
    db.flush()
    common.audit(
        db,
        amo_id=amo_id,
        actor_user_id=actor_user_id,
        entity_type="RosterRuleSet",
        entity_id=row.id,
        action="seed",
        after={"code": row.code, "version_label": row.version_label},
    )
    return row


def list_rule_sets(db: Session, *, amo_id: str, include_inactive: bool = False) -> list[models.RosterRuleSet]:
    seed_default_rule_set(db, amo_id=amo_id)
    query = db.query(models.RosterRuleSet).filter(models.RosterRuleSet.amo_id == amo_id)
    if not include_inactive:
        query = query.filter(models.RosterRuleSet.is_active.is_(True))
    return query.order_by(models.RosterRuleSet.priority.desc(), models.RosterRuleSet.code.asc()).all()


def create_rule_set(
    db: Session,
    *,
    amo_id: str,
    actor_user_id: str,
    payload: schemas.RosterRuleSetCreate,
) -> models.RosterRuleSet:
    row = models.RosterRuleSet(
        amo_id=amo_id,
        **common.dump(payload),
        created_by_user_id=actor_user_id,
        updated_by_user_id=actor_user_id,
    )
    row.code = row.code.strip().upper()
    row.name = row.name.strip()
    db.add(row)
    db.flush()
    common.audit(
        db,
        amo_id=amo_id,
        actor_user_id=actor_user_id,
        entity_type="RosterRuleSet",
        entity_id=row.id,
        action="create",
        after={"code": row.code, "name": row.name, "priority": row.priority},
    )
    return row


def update_rule_set(
    db: Session,
    *,
    row: models.RosterRuleSet,
    actor_user_id: str,
    payload: schemas.RosterRuleSetUpdate,
) -> models.RosterRuleSet:
    before = {
        "name": row.name,
        "version_label": row.version_label,
        "is_active": row.is_active,
        "priority": row.priority,
    }
    for key, value in common.dump(payload, exclude_unset=True).items():
        setattr(row, key, value)
    if row.effective_from and row.effective_to and row.effective_to < row.effective_from:
        raise ValueError("effective_to must be on or after effective_from")
    row.updated_by_user_id = actor_user_id
    db.add(row)
    db.flush()
    common.audit(
        db,
        amo_id=row.amo_id,
        actor_user_id=actor_user_id,
        entity_type="RosterRuleSet",
        entity_id=row.id,
        action="update",
        before=before,
        after={
            "name": row.name,
            "version_label": row.version_label,
            "is_active": row.is_active,
            "priority": row.priority,
        },
    )
    return row


def _authority_query(db: Session, *, amo_id: str):
    query = db.query(models.RosterApprovalAuthority).filter(
        models.RosterApprovalAuthority.amo_id == amo_id,
        models.RosterApprovalAuthority.is_active.is_(True),
    )
    return _active_window(query, models.RosterApprovalAuthority)


def list_authorities(db: Session, *, amo_id: str, include_inactive: bool = False) -> list[models.RosterApprovalAuthority]:
    query = db.query(models.RosterApprovalAuthority).filter(models.RosterApprovalAuthority.amo_id == amo_id)
    if not include_inactive:
        query = _active_window(
            query.filter(models.RosterApprovalAuthority.is_active.is_(True)),
            models.RosterApprovalAuthority,
        )
    return query.order_by(
        models.RosterApprovalAuthority.base_station_id.asc().nullsfirst(),
        models.RosterApprovalAuthority.department_id.asc().nullsfirst(),
        models.RosterApprovalAuthority.authority_level.asc(),
        models.RosterApprovalAuthority.created_at.asc(),
    ).all()


def _permission_grant(
    db: Session,
    *,
    authority: models.RosterApprovalAuthority,
    permission_code: str,
    actor_user_id: str,
) -> None:
    filters = [
        workforce_models.WorkforcePermissionGrant.amo_id == authority.amo_id,
        workforce_models.WorkforcePermissionGrant.user_id == authority.user_id,
        workforce_models.WorkforcePermissionGrant.permission_code == permission_code,
        workforce_models.WorkforcePermissionGrant.department_id.is_(None)
        if authority.department_id is None
        else workforce_models.WorkforcePermissionGrant.department_id == authority.department_id,
        workforce_models.WorkforcePermissionGrant.base_station_id.is_(None)
        if authority.base_station_id is None
        else workforce_models.WorkforcePermissionGrant.base_station_id == authority.base_station_id,
    ]
    row = db.query(workforce_models.WorkforcePermissionGrant).filter(*filters).first()
    if row:
        row.effect = workforce_models.PermissionEffect.GRANT
        row.effective_from = authority.effective_from
        row.effective_to = authority.effective_to
        row.reason = f"Roster approval authority {authority.id}"
        row.granted_by_user_id = actor_user_id
        db.add(row)
        return
    db.add(workforce_models.WorkforcePermissionGrant(
        amo_id=authority.amo_id,
        user_id=authority.user_id,
        permission_code=permission_code,
        effect=workforce_models.PermissionEffect.GRANT,
        department_id=authority.department_id,
        base_station_id=authority.base_station_id,
        effective_from=authority.effective_from,
        effective_to=authority.effective_to,
        reason=f"Roster approval authority {authority.id}",
        granted_by_user_id=actor_user_id,
    ))


def create_authority(
    db: Session,
    *,
    amo_id: str,
    actor_user_id: str,
    payload: schemas.RosterApprovalAuthorityCreate,
) -> models.RosterApprovalAuthority:
    common.require_user(db, amo_id=amo_id, user_id=payload.user_id, active_only=True)
    common.require_department(db, amo_id=amo_id, department_id=payload.department_id)
    common.require_base(db, amo_id=amo_id, base_station_id=payload.base_station_id)
    if payload.authority_level == models.RosterApprovalAuthorityLevel.DEPARTMENT_HEAD and not payload.department_id:
        raise ValueError("Department-head authority requires a department")
    if payload.authority_level == models.RosterApprovalAuthorityLevel.BASE_MANAGER and not payload.base_station_id:
        raise ValueError("Base-manager authority requires a base")
    existing = db.query(models.RosterApprovalAuthority).filter(
        models.RosterApprovalAuthority.amo_id == amo_id,
        models.RosterApprovalAuthority.user_id == payload.user_id,
        models.RosterApprovalAuthority.authority_level == payload.authority_level,
        models.RosterApprovalAuthority.department_id.is_(None)
        if payload.department_id is None
        else models.RosterApprovalAuthority.department_id == payload.department_id,
        models.RosterApprovalAuthority.base_station_id.is_(None)
        if payload.base_station_id is None
        else models.RosterApprovalAuthority.base_station_id == payload.base_station_id,
    ).first()
    if existing:
        for key, value in common.dump(payload).items():
            setattr(existing, key, value)
        existing.is_active = True
        existing.updated_by_user_id = actor_user_id
        row = existing
    else:
        row = models.RosterApprovalAuthority(
            amo_id=amo_id,
            **common.dump(payload),
            created_by_user_id=actor_user_id,
            updated_by_user_id=actor_user_id,
        )
        db.add(row)
    db.flush()
    if row.can_approve:
        _permission_grant(
            db,
            authority=row,
            permission_code=workforce_permissions.PermissionCode.ROSTER_APPROVE.value,
            actor_user_id=actor_user_id,
        )
    if row.can_publish:
        _permission_grant(
            db,
            authority=row,
            permission_code=workforce_permissions.PermissionCode.ROSTER_PUBLISH.value,
            actor_user_id=actor_user_id,
        )
    db.flush()
    common.audit(
        db,
        amo_id=amo_id,
        actor_user_id=actor_user_id,
        entity_type="RosterApprovalAuthority",
        entity_id=row.id,
        action="assign",
        after={
            "user_id": row.user_id,
            "authority_level": _value(row.authority_level),
            "department_id": row.department_id,
            "base_station_id": row.base_station_id,
            "can_approve": row.can_approve,
            "can_publish": row.can_publish,
        },
        critical=True,
    )
    return row


def update_authority(
    db: Session,
    *,
    row: models.RosterApprovalAuthority,
    actor_user_id: str,
    payload: schemas.RosterApprovalAuthorityUpdate,
) -> models.RosterApprovalAuthority:
    before = {
        "can_approve": row.can_approve,
        "can_publish": row.can_publish,
        "is_active": row.is_active,
        "effective_to": row.effective_to.isoformat() if row.effective_to else None,
    }
    for key, value in common.dump(payload, exclude_unset=True).items():
        setattr(row, key, value)
    if row.effective_from and row.effective_to and row.effective_to < row.effective_from:
        raise ValueError("effective_to must be on or after effective_from")
    row.updated_by_user_id = actor_user_id
    db.add(row)
    if row.can_approve and row.is_active:
        _permission_grant(
            db,
            authority=row,
            permission_code=workforce_permissions.PermissionCode.ROSTER_APPROVE.value,
            actor_user_id=actor_user_id,
        )
    if row.can_publish and row.is_active:
        _permission_grant(
            db,
            authority=row,
            permission_code=workforce_permissions.PermissionCode.ROSTER_PUBLISH.value,
            actor_user_id=actor_user_id,
        )
    db.flush()
    common.audit(
        db,
        amo_id=row.amo_id,
        actor_user_id=actor_user_id,
        entity_type="RosterApprovalAuthority",
        entity_id=row.id,
        action="update",
        before=before,
        after={
            "can_approve": row.can_approve,
            "can_publish": row.can_publish,
            "is_active": row.is_active,
            "effective_to": row.effective_to.isoformat() if row.effective_to else None,
        },
        critical=True,
    )
    return row


def _title(user: account_models.User) -> str:
    return str(getattr(user, "position_title", "") or "").strip().lower()


def _is_admin(user: account_models.User) -> bool:
    return bool(getattr(user, "is_superuser", False) or getattr(user, "is_amo_admin", False))


def _active_contracts_for_user(db: Session, *, amo_id: str, user_id: str) -> list[workforce_models.EmploymentContract]:
    today = _today()
    return db.query(workforce_models.EmploymentContract).filter(
        workforce_models.EmploymentContract.amo_id == amo_id,
        workforce_models.EmploymentContract.user_id == user_id,
        workforce_models.EmploymentContract.employment_status == workforce_models.EmploymentStatus.ACTIVE,
        workforce_models.EmploymentContract.effective_from <= today,
        or_(
            workforce_models.EmploymentContract.effective_to.is_(None),
            workforce_models.EmploymentContract.effective_to >= today,
        ),
    ).all()


def _is_inferred_base_manager(
    db: Session,
    *,
    user: account_models.User,
    base_station_id: Optional[str],
) -> bool:
    if "base manager" not in _title(user):
        return False
    if not base_station_id:
        return True
    return any(
        base_station_id in {row.primary_base_station_id, row.secondary_base_station_id}
        for row in _active_contracts_for_user(db, amo_id=common.effective_amo_id(user), user_id=user.id)
    )


def _is_inferred_department_head(user: account_models.User, department_id: Optional[str]) -> bool:
    if not department_id or str(getattr(user, "department_id", "") or "") != str(department_id):
        return False
    title = _title(user)
    return "department head" in title or title.startswith("head of ") or title.endswith(" manager") or "department manager" in title


def _matching_authorities(
    db: Session,
    *,
    amo_id: str,
    user_id: str,
    department_id: Optional[str],
    base_station_id: Optional[str],
) -> list[models.RosterApprovalAuthority]:
    rows = _authority_query(db, amo_id=amo_id).filter(
        models.RosterApprovalAuthority.user_id == user_id,
    ).all()
    return [
        row
        for row in rows
        if (row.department_id is None or row.department_id == department_id)
        and (row.base_station_id is None or row.base_station_id == base_station_id)
    ]


def can_approve_scope(
    db: Session,
    *,
    user: account_models.User,
    department_id: Optional[str],
    base_station_id: Optional[str],
) -> bool:
    if _is_admin(user):
        return True
    amo_id = common.effective_amo_id(user)
    if any(row.can_approve for row in _matching_authorities(
        db,
        amo_id=amo_id,
        user_id=user.id,
        department_id=department_id,
        base_station_id=base_station_id,
    )):
        return True
    if _is_inferred_department_head(user, department_id) or _is_inferred_base_manager(
        db,
        user=user,
        base_station_id=base_station_id,
    ):
        return True
    return workforce_permissions.has_permission(
        db,
        user=user,
        permission=workforce_permissions.PermissionCode.ROSTER_APPROVE,
        department_id=department_id,
        base_station_id=base_station_id,
    )


def can_publish_scope(
    db: Session,
    *,
    user: account_models.User,
    department_id: Optional[str],
    base_station_id: Optional[str],
) -> bool:
    if _is_admin(user):
        return True
    amo_id = common.effective_amo_id(user)
    if any(row.can_publish for row in _matching_authorities(
        db,
        amo_id=amo_id,
        user_id=user.id,
        department_id=department_id,
        base_station_id=base_station_id,
    )):
        return True
    if _is_inferred_base_manager(db, user=user, base_station_id=base_station_id):
        return True
    return False


def _preferred_approver(
    db: Session,
    *,
    amo_id: str,
    department_id: Optional[str],
    base_station_id: Optional[str],
) -> Optional[str]:
    rows = _authority_query(db, amo_id=amo_id).filter(
        models.RosterApprovalAuthority.can_approve.is_(True),
    ).all()
    candidates = [
        row
        for row in rows
        if (row.department_id is None or row.department_id == department_id)
        and (row.base_station_id is None or row.base_station_id == base_station_id)
    ]
    rank = {
        models.RosterApprovalAuthorityLevel.DEPARTMENT_HEAD: 3,
        models.RosterApprovalAuthorityLevel.DELEGATE: 2,
        models.RosterApprovalAuthorityLevel.BASE_MANAGER: 1,
    }
    if candidates:
        candidates.sort(key=lambda row: (rank.get(row.authority_level, 0), row.created_at), reverse=True)
        return candidates[0].user_id

    if department_id:
        department_heads = db.query(account_models.User).filter(
            account_models.User.amo_id == amo_id,
            account_models.User.department_id == department_id,
            account_models.User.is_active.is_(True),
            account_models.User.is_system_account.is_(False),
        ).order_by(account_models.User.full_name.asc()).all()
        for user in department_heads:
            if _is_inferred_department_head(user, department_id):
                return user.id

    if base_station_id:
        base_users = db.query(account_models.User).join(
            workforce_models.EmploymentContract,
            and_(
                workforce_models.EmploymentContract.amo_id == amo_id,
                workforce_models.EmploymentContract.user_id == account_models.User.id,
            ),
        ).filter(
            account_models.User.amo_id == amo_id,
            account_models.User.is_active.is_(True),
            account_models.User.is_system_account.is_(False),
            workforce_models.EmploymentContract.employment_status == workforce_models.EmploymentStatus.ACTIVE,
            or_(
                workforce_models.EmploymentContract.primary_base_station_id == base_station_id,
                workforce_models.EmploymentContract.secondary_base_station_id == base_station_id,
            ),
        ).order_by(account_models.User.full_name.asc()).all()
        for user in base_users:
            if "base manager" in _title(user):
                return user.id
    return None


def approval_rows(db: Session, *, version_id: str) -> list[models.RosterDepartmentApproval]:
    return db.query(models.RosterDepartmentApproval).filter(
        models.RosterDepartmentApproval.version_id == version_id,
    ).order_by(
        models.RosterDepartmentApproval.base_station_id.asc().nullsfirst(),
        models.RosterDepartmentApproval.department_id.asc().nullsfirst(),
        models.RosterDepartmentApproval.id.asc(),
    ).all()


def prepare_approval_cycle(
    db: Session,
    *,
    version: models.RosterVersion,
    actor_user_id: str,
) -> list[models.RosterDepartmentApproval]:
    assignments = [row for row in version.assignments or [] if row.deleted_at is None]
    scopes = {
        _scope_key(row.base_station_id, row.department_id): (row.base_station_id, row.department_id)
        for row in assignments
    }
    if not scopes:
        raise ValueError("A roster version must contain at least one assignment before submission")
    existing = {
        _scope_key(row.base_station_id, row.department_id): row
        for row in approval_rows(db, version_id=version.id)
    }
    for key, (base_station_id, department_id) in scopes.items():
        row = existing.get(key)
        assignee = _preferred_approver(
            db,
            amo_id=version.amo_id,
            department_id=department_id,
            base_station_id=base_station_id,
        )
        if row:
            row.status = models.RosterDepartmentApprovalStatus.PENDING
            row.assigned_approver_user_id = assignee
            row.decided_by_user_id = None
            row.decision_comment = None
            row.decided_at = None
        else:
            row = models.RosterDepartmentApproval(
                amo_id=version.amo_id,
                version_id=version.id,
                base_station_id=base_station_id,
                department_id=department_id,
                assigned_approver_user_id=assignee,
                status=models.RosterDepartmentApprovalStatus.PENDING,
            )
        db.add(row)
    for key, row in existing.items():
        if key not in scopes:
            db.delete(row)
    db.flush()
    rows = approval_rows(db, version_id=version.id)
    common.audit(
        db,
        amo_id=version.amo_id,
        actor_user_id=actor_user_id,
        entity_type="RosterVersion",
        entity_id=version.id,
        action="prepare_department_approvals",
        after={
            "required_scopes": len(rows),
            "unassigned_scopes": sum(1 for row in rows if not row.assigned_approver_user_id),
        },
        critical=True,
    )
    return rows


def _selected_rows(
    rows: Iterable[models.RosterDepartmentApproval],
    *,
    department_id: Optional[str],
    base_station_id: Optional[str],
) -> list[models.RosterDepartmentApproval]:
    return [
        row
        for row in rows
        if (department_id is None or row.department_id == department_id)
        and (base_station_id is None or row.base_station_id == base_station_id)
    ]


def approve_scopes(
    db: Session,
    *,
    version: models.RosterVersion,
    actor: account_models.User,
    payload: schemas.RosterLifecycleRequest,
) -> tuple[list[models.RosterDepartmentApproval], bool]:
    if version.status != models.RosterVersionStatus.SUBMITTED:
        raise ValueError("Only submitted roster versions can receive departmental approvals")
    common.check_version_revision(version, payload.expected_state_revision)
    if actor.id in {version.created_by_user_id, version.submitted_by_user_id}:
        raise ValueError("The roster creator or submitter cannot approve the same version")
    rows = approval_rows(db, version_id=version.id) or prepare_approval_cycle(
        db,
        version=version,
        actor_user_id=actor.id,
    )
    selected = _selected_rows(
        rows,
        department_id=payload.department_id,
        base_station_id=payload.base_station_id,
    )
    eligible = [
        row for row in selected
        if row.status != models.RosterDepartmentApprovalStatus.APPROVED
        and can_approve_scope(
            db,
            user=actor,
            department_id=row.department_id,
            base_station_id=row.base_station_id,
        )
    ]
    if not eligible:
        raise ValueError("No pending departmental roster approval is assigned or delegated to this user")
    now = common.utcnow()
    for row in eligible:
        row.status = models.RosterDepartmentApprovalStatus.APPROVED
        row.decided_by_user_id = actor.id
        row.decision_comment = payload.comment
        row.decided_at = now
        db.add(row)
        common.audit(
            db,
            amo_id=version.amo_id,
            actor_user_id=actor.id,
            entity_type="RosterDepartmentApproval",
            entity_id=row.id,
            action="approve",
            after={
                "version_id": version.id,
                "department_id": row.department_id,
                "base_station_id": row.base_station_id,
                "comment": payload.comment,
            },
            critical=True,
        )
    db.flush()
    all_rows = approval_rows(db, version_id=version.id)
    complete = bool(all_rows) and all(
        row.status == models.RosterDepartmentApprovalStatus.APPROVED for row in all_rows
    )
    return all_rows, complete


def request_changes(
    db: Session,
    *,
    version: models.RosterVersion,
    actor: account_models.User,
    payload: schemas.RosterLifecycleRequest,
) -> models.RosterVersion:
    if version.status != models.RosterVersionStatus.SUBMITTED:
        raise ValueError("Only a submitted roster can be returned for changes")
    if not payload.comment or len(payload.comment.strip()) < 8:
        raise ValueError("A clear change request comment of at least 8 characters is required")
    rows = approval_rows(db, version_id=version.id)
    selected = _selected_rows(
        rows,
        department_id=payload.department_id,
        base_station_id=payload.base_station_id,
    )
    eligible = [
        row for row in selected
        if can_approve_scope(
            db,
            user=actor,
            department_id=row.department_id,
            base_station_id=row.base_station_id,
        )
    ]
    if not eligible:
        raise ValueError("This user cannot request changes for the selected roster scope")
    now = common.utcnow()
    for row in eligible:
        row.status = models.RosterDepartmentApprovalStatus.CHANGES_REQUESTED
        row.decided_by_user_id = actor.id
        row.decision_comment = payload.comment.strip()
        row.decided_at = now
        db.add(row)
    version.status = models.RosterVersionStatus.DRAFT
    version.approved_by_user_id = None
    version.approved_at = None
    common.bump_version(version)
    db.add(version)
    db.flush()
    common.audit(
        db,
        amo_id=version.amo_id,
        actor_user_id=actor.id,
        entity_type="RosterVersion",
        entity_id=version.id,
        action="request_changes",
        after={
            "status": _value(version.status),
            "department_id": payload.department_id,
            "base_station_id": payload.base_station_id,
            "comment": payload.comment,
        },
        critical=True,
    )
    return version


def require_publish_authority(
    db: Session,
    *,
    version: models.RosterVersion,
    actor: account_models.User,
) -> None:
    rows = approval_rows(db, version_id=version.id)
    if not rows or any(row.status != models.RosterDepartmentApprovalStatus.APPROVED for row in rows):
        raise ValueError("Every required base and departmental approval must be completed before publication")
    scopes = {_scope_key(row.base_station_id, row.department_id): row for row in rows}.values()
    if not all(
        can_publish_scope(
            db,
            user=actor,
            department_id=row.department_id,
            base_station_id=row.base_station_id,
        )
        for row in scopes
    ):
        raise ValueError("Publication requires the Base Manager or an explicitly delegated roster publisher for every affected base")


def approval_matrix(
    db: Session,
    *,
    amo_id: str,
    version_id: Optional[str] = None,
) -> schemas.RosterApprovalMatrixResponse:
    query = db.query(models.RosterDepartmentApproval).filter(models.RosterDepartmentApproval.amo_id == amo_id)
    if version_id:
        query = query.filter(models.RosterDepartmentApproval.version_id == version_id)
    rows = query.order_by(models.RosterDepartmentApproval.created_at.desc(), models.RosterDepartmentApproval.id.asc()).all()
    return schemas.RosterApprovalMatrixResponse(
        version_id=version_id,
        required_count=len(rows),
        approved_count=sum(row.status == models.RosterDepartmentApprovalStatus.APPROVED for row in rows),
        pending_count=sum(row.status == models.RosterDepartmentApprovalStatus.PENDING for row in rows),
        changes_requested_count=sum(row.status == models.RosterDepartmentApprovalStatus.CHANGES_REQUESTED for row in rows),
        items=[schemas.RosterDepartmentApprovalRead.model_validate(row) for row in rows],
    )


def approval_counts(db: Session, *, version_id: str) -> tuple[int, int, int]:
    rows = approval_rows(db, version_id=version_id)
    required = len(rows)
    approved = sum(row.status == models.RosterDepartmentApprovalStatus.APPROVED for row in rows)
    pending = sum(row.status != models.RosterDepartmentApprovalStatus.APPROVED for row in rows)
    return required, approved, pending
