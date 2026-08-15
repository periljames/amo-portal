"""Controlled per-person mutations used by durable Workforce bulk operations."""
from __future__ import annotations

from datetime import date, datetime, timedelta, timezone
from typing import Any

from sqlalchemy import or_
from sqlalchemy.orm import Session

from ..accounts import models as account_models, services as account_services
from ..audit import services as audit_services
from ..foundations import models as foundation_models
from . import governance_models, hierarchy_roles, models, permissions, supervisor_governance

MUTATION_TYPES = {
    "ASSIGN_ORGANIZATION",
    "ASSIGN_POSITION",
    "ASSIGN_BASES",
    "ASSIGN_SUPERVISOR",
    "UPDATE_GROUPS",
    "UPDATE_CONTRACT_SETTINGS",
    "SCHEDULE_OFFBOARDING",
}


def _utcnow() -> datetime:
    return datetime.now(timezone.utc)


def _user(db: Session, *, amo_id: str, user_id: str, include_inactive: bool = False):
    query = db.query(account_models.User).filter(
        account_models.User.amo_id == amo_id,
        account_models.User.id == user_id,
        account_models.User.is_system_account.is_(False),
    )
    if not include_inactive:
        query = query.filter(account_models.User.is_active.is_(True))
    row = query.with_for_update().first()
    if row is None:
        raise ValueError("The selected personnel record is inactive, missing, or a system account")
    return row


def _active_org(db: Session, *, amo_id: str, org_unit_id: str):
    row = db.query(governance_models.WorkforceOrgUnit).filter(
        governance_models.WorkforceOrgUnit.amo_id == amo_id,
        governance_models.WorkforceOrgUnit.id == org_unit_id,
        governance_models.WorkforceOrgUnit.is_active.is_(True),
    ).first()
    if row is None:
        raise ValueError("The selected organisation unit is not active")
    return row


def _active_position(db: Session, *, amo_id: str, position_id: str):
    row = db.query(governance_models.WorkforcePosition).filter(
        governance_models.WorkforcePosition.amo_id == amo_id,
        governance_models.WorkforcePosition.id == position_id,
        governance_models.WorkforcePosition.is_active.is_(True),
    ).first()
    if row is None:
        raise ValueError("The selected canonical position is not active")
    return row


def _active_base(db: Session, *, amo_id: str, base_id: str | None, label: str):
    if base_id is None:
        return None
    row = db.query(foundation_models.BaseStation).filter(
        foundation_models.BaseStation.amo_id == amo_id,
        foundation_models.BaseStation.id == base_id,
        foundation_models.BaseStation.is_active.is_(True),
    ).first()
    if row is None:
        raise ValueError(f"The selected {label} base is not active")
    return row


def _supervisor(db: Session, *, amo_id: str, supervisor_user_id: str, target_user_id: str, on_date: date):
    return supervisor_governance.require_supervisor(
        db,
        amo_id=amo_id,
        supervisor_user_id=supervisor_user_id,
        target_user_id=target_user_id,
        on_date=on_date,
    )


def _contract_on(db: Session, *, amo_id: str, user_id: str, on_date: date):
    effective = db.query(models.EmploymentContract).filter(
        models.EmploymentContract.amo_id == amo_id,
        models.EmploymentContract.user_id == user_id,
        models.EmploymentContract.effective_from <= on_date,
        or_(models.EmploymentContract.effective_to.is_(None), models.EmploymentContract.effective_to >= on_date),
    ).order_by(models.EmploymentContract.effective_from.desc(), models.EmploymentContract.id.desc()).with_for_update().first()
    if effective is not None:
        return effective
    return db.query(models.EmploymentContract).filter(
        models.EmploymentContract.amo_id == amo_id,
        models.EmploymentContract.user_id == user_id,
        models.EmploymentContract.effective_from > on_date,
    ).order_by(models.EmploymentContract.effective_from.asc(), models.EmploymentContract.id.asc()).with_for_update().first()


def _contract_values(contract) -> dict[str, Any]:
    return {
        "contract_type": contract.contract_type,
        "employment_status": contract.employment_status,
        "effective_from": contract.effective_from,
        "effective_to": contract.effective_to,
        "standard_weekly_minutes": contract.standard_weekly_minutes,
        "standard_daily_minutes": contract.standard_daily_minutes,
        "fte_percentage": contract.fte_percentage,
        "primary_base_station_id": contract.primary_base_station_id,
        "secondary_base_station_id": contract.secondary_base_station_id,
        "supervisor_user_id": contract.supervisor_user_id,
        "cost_centre": contract.cost_centre,
        "payroll_number": contract.payroll_number,
        "overtime_eligible": contract.overtime_eligible,
        "night_shift_eligible": contract.night_shift_eligible,
        "standby_eligible": contract.standby_eligible,
    }


def _version_contract(db: Session, *, contract, effective_on: date, actor_user_id: str):
    if contract is None:
        raise ValueError("The person has no contract to update")
    if contract.effective_from == effective_on:
        return contract
    if contract.effective_from > effective_on:
        contract.effective_from = effective_on
        contract.updated_by_user_id = actor_user_id
        return contract
    original_end = contract.effective_to
    contract.effective_to = effective_on - timedelta(days=1)
    values = _contract_values(contract)
    values["effective_from"] = effective_on
    values["effective_to"] = original_end
    values["created_by_user_id"] = actor_user_id
    values["updated_by_user_id"] = actor_user_id
    replacement = models.EmploymentContract(
        amo_id=contract.amo_id,
        user_id=contract.user_id,
        **values,
    )
    db.add(replacement)
    db.flush()
    return replacement


def _placement_on(db: Session, *, amo_id: str, user_id: str, placement_type: str, on_date: date):
    return db.query(governance_models.WorkforcePersonPlacement).filter(
        governance_models.WorkforcePersonPlacement.amo_id == amo_id,
        governance_models.WorkforcePersonPlacement.user_id == user_id,
        governance_models.WorkforcePersonPlacement.placement_type == placement_type,
        governance_models.WorkforcePersonPlacement.effective_from <= on_date,
        or_(
            governance_models.WorkforcePersonPlacement.effective_to.is_(None),
            governance_models.WorkforcePersonPlacement.effective_to >= on_date,
        ),
    ).order_by(
        governance_models.WorkforcePersonPlacement.effective_from.desc(),
        governance_models.WorkforcePersonPlacement.id.desc(),
    ).with_for_update().first()


def _end_placement(row, *, effective_on: date):
    if row.effective_from >= effective_on:
        return False
    row.effective_to = effective_on - timedelta(days=1)
    return True


def _new_placement(db: Session, *, amo_id: str, user_id: str, org_unit_id: str, placement_type: str,
                   effective_on: date, actor_user_id: str, source=None, position_id: str | None = None,
                   preferred_title: str | None = None, base_station_id: str | None = None,
                   supervisor_user_id: str | None = None):
    row = governance_models.WorkforcePersonPlacement(
        amo_id=amo_id,
        user_id=user_id,
        org_unit_id=org_unit_id,
        placement_type=placement_type,
        position_id=position_id if position_id is not None else getattr(source, "position_id", None),
        preferred_title=preferred_title if preferred_title is not None else getattr(source, "preferred_title", None),
        base_station_id=base_station_id if base_station_id is not None else getattr(source, "base_station_id", None),
        supervisor_user_id=(supervisor_user_id if supervisor_user_id is not None
                            else getattr(source, "supervisor_user_id", None)),
        effective_from=effective_on,
        effective_to=getattr(source, "effective_to", None),
        created_by_user_id=actor_user_id,
        updated_by_user_id=actor_user_id,
    )
    db.add(row)
    db.flush()
    return row


def _assign_organization(db: Session, *, amo_id: str, user, payload, actor_user_id: str):
    org = _active_org(db, amo_id=amo_id, org_unit_id=payload["org_unit_id"])
    placement_type = payload.get("placement_type") or "PRIMARY"
    current = _placement_on(
        db, amo_id=amo_id, user_id=str(user.id), placement_type=placement_type,
        on_date=payload["effective_on"],
    )
    if current and str(current.org_unit_id) == str(org.id):
        return "SKIPPED", "ORGANIZATION_ALREADY_ASSIGNED", "Organisation placement already matches", {
            "org_unit_id": str(org.id), "placement_type": placement_type,
        }
    old_end = current.effective_to if current else None
    if current and not _end_placement(current, effective_on=payload["effective_on"]):
        db.delete(current)
        db.flush()
    row = _new_placement(
        db, amo_id=amo_id, user_id=str(user.id), org_unit_id=str(org.id),
        placement_type=placement_type, effective_on=payload["effective_on"], actor_user_id=actor_user_id,
        source=current,
    )
    row.effective_to = old_end
    if placement_type == "PRIMARY" and org.legacy_department_id:
        user.department_id = org.legacy_department_id
    return "SUCCEEDED", "ORGANIZATION_ASSIGNED", "Organisation placement assigned", {
        "placement_id": str(row.id), "org_unit_id": str(org.id), "placement_type": placement_type,
    }


def _assign_position(db: Session, *, amo_id: str, user, payload, actor_user_id: str):
    position = _active_position(db, amo_id=amo_id, position_id=payload["position_id"])
    current = _placement_on(
        db, amo_id=amo_id, user_id=str(user.id), placement_type="PRIMARY", on_date=payload["effective_on"]
    )
    if current is None:
        raise ValueError("Assign a primary organisation placement before assigning a canonical position")
    preferred_title = payload.get("preferred_title")
    source_contract = _contract_on(
        db,
        amo_id=amo_id,
        user_id=str(user.id),
        on_date=payload["effective_on"],
    )
    management_position = not hierarchy_roles.can_have_supervisor(position)
    supervisor_present = bool(
        current.supervisor_user_id
        or (source_contract is not None and source_contract.supervisor_user_id)
    )
    if (
        str(current.position_id or "") == str(position.id)
        and (current.preferred_title or None) == (preferred_title or None)
        and not (management_position and supervisor_present)
    ):
        return "SKIPPED", "POSITION_ALREADY_ASSIGNED", "Canonical position already matches", {
            "position_id": str(position.id),
        }
    old_end = current.effective_to
    if not _end_placement(current, effective_on=payload["effective_on"]):
        db.delete(current)
        db.flush()
    row = _new_placement(
        db, amo_id=amo_id, user_id=str(user.id), org_unit_id=str(current.org_unit_id),
        placement_type="PRIMARY", effective_on=payload["effective_on"], actor_user_id=actor_user_id,
        source=current, position_id=str(position.id), preferred_title=preferred_title,
    )
    row.effective_to = old_end
    supervisor_cleared = False
    if management_position:
        if row.supervisor_user_id:
            row.supervisor_user_id = None
            supervisor_cleared = True
        if source_contract is not None and source_contract.supervisor_user_id:
            contract = _version_contract(
                db,
                contract=source_contract,
                effective_on=payload["effective_on"],
                actor_user_id=actor_user_id,
            )
            contract.supervisor_user_id = None
            contract.updated_by_user_id = actor_user_id
            supervisor_cleared = True
    user.position_title = preferred_title or position.canonical_title
    account_role_synced = hierarchy_roles.sync_account_for_position(db, user, position)
    return "SUCCEEDED", "POSITION_ASSIGNED", "Canonical position assigned", {
        "placement_id": str(row.id),
        "position_id": str(position.id),
        "title": user.position_title,
        "supervisor_cleared": supervisor_cleared,
        "account_role_synced": account_role_synced,
    }


def _assign_bases(db: Session, *, amo_id: str, user, payload, actor_user_id: str):
    primary = _active_base(db, amo_id=amo_id, base_id=payload.get("primary_base_station_id"), label="primary")
    secondary = _active_base(db, amo_id=amo_id, base_id=payload.get("secondary_base_station_id"), label="secondary")
    if secondary and primary and str(secondary.id) == str(primary.id):
        raise ValueError("Primary and secondary base must be different")
    source_contract = _contract_on(db, amo_id=amo_id, user_id=str(user.id), on_date=payload["effective_on"])
    if source_contract is None:
        raise ValueError("The person has no contract to update")
    if (str(source_contract.primary_base_station_id or "") == str(primary.id) and
            str(source_contract.secondary_base_station_id or "") == str(secondary.id if secondary else "")):
        return "SKIPPED", "BASES_ALREADY_ASSIGNED", "Base assignments already match", {}
    contract = _version_contract(
        db, contract=source_contract, effective_on=payload["effective_on"], actor_user_id=actor_user_id,
    )
    contract.primary_base_station_id = primary.id
    contract.secondary_base_station_id = secondary.id if secondary else None
    contract.updated_by_user_id = actor_user_id
    primary_placement = _placement_on(
        db, amo_id=amo_id, user_id=str(user.id), placement_type="PRIMARY", on_date=payload["effective_on"]
    )
    if primary_placement:
        primary_placement.base_station_id = primary.id
        primary_placement.updated_by_user_id = actor_user_id
    return "SUCCEEDED", "BASES_ASSIGNED", "Primary and secondary bases assigned", {
        "primary_base_station_id": str(primary.id),
        "secondary_base_station_id": str(secondary.id) if secondary else None,
    }


def _assign_supervisor(db: Session, *, amo_id: str, user, payload, actor_user_id: str):
    hierarchy_roles.require_person_can_have_supervisor(
        db,
        amo_id=amo_id,
        user_id=str(user.id),
        on_date=payload["effective_on"],
    )
    supervisor = _supervisor(
        db, amo_id=amo_id, supervisor_user_id=payload["supervisor_user_id"],
        target_user_id=str(user.id), on_date=payload["effective_on"],
    )
    hierarchy_roles.require_no_reporting_cycle(
        db,
        amo_id=amo_id,
        user_id=str(user.id),
        supervisor_user_id=str(supervisor.id),
        on_date=payload["effective_on"],
    )
    source_contract = _contract_on(db, amo_id=amo_id, user_id=str(user.id), on_date=payload["effective_on"])
    if source_contract is None:
        raise ValueError("The person has no contract to update")
    if str(source_contract.supervisor_user_id or "") == str(supervisor.id):
        return "SKIPPED", "SUPERVISOR_ALREADY_ASSIGNED", "Supervisor already matches", {
            "supervisor_user_id": str(supervisor.id),
        }
    contract = _version_contract(
        db, contract=source_contract, effective_on=payload["effective_on"], actor_user_id=actor_user_id,
    )
    contract.supervisor_user_id = supervisor.id
    contract.updated_by_user_id = actor_user_id
    primary_placement = _placement_on(
        db, amo_id=amo_id, user_id=str(user.id), placement_type="PRIMARY", on_date=payload["effective_on"]
    )
    if primary_placement:
        primary_placement.supervisor_user_id = supervisor.id
        primary_placement.updated_by_user_id = actor_user_id
    return "SUCCEEDED", "SUPERVISOR_ASSIGNED", "Governed supervisor assigned", {
        "supervisor_user_id": str(supervisor.id), "supervisor_name": supervisor.full_name,
    }


def _update_groups(db: Session, *, amo_id: str, user, payload, actor_user_id: str):
    group_ids = sorted(set(payload.get("group_ids") or []))
    groups = db.query(account_models.UserGroup).filter(
        account_models.UserGroup.amo_id == amo_id,
        account_models.UserGroup.id.in_(group_ids or ["__none__"]),
        account_models.UserGroup.is_active.is_(True),
    ).all()
    if len(groups) != len(group_ids):
        raise ValueError("One or more selected groups are missing or inactive")
    existing = db.query(account_models.UserGroupMember).join(
        account_models.UserGroup, account_models.UserGroup.id == account_models.UserGroupMember.group_id
    ).filter(
        account_models.UserGroup.amo_id == amo_id,
        account_models.UserGroupMember.user_id == user.id,
    ).with_for_update().all()
    by_group = {str(row.group_id): row for row in existing}
    mode = payload["group_mode"]
    changed = 0
    if mode in {"REMOVE", "REPLACE"}:
        remove_ids = group_ids if mode == "REMOVE" else [gid for gid in by_group if gid not in group_ids]
        for group_id in remove_ids:
            row = by_group.get(group_id)
            if row:
                db.delete(row)
                changed += 1
    if mode in {"ADD", "REPLACE"}:
        for group_id in group_ids:
            if group_id not in by_group:
                db.add(account_models.UserGroupMember(
                    group_id=group_id, user_id=user.id, added_by_user_id=actor_user_id,
                ))
                changed += 1
    if changed == 0:
        return "SKIPPED", "GROUPS_ALREADY_MATCH", "Group memberships already match", {"group_ids": group_ids}
    return "SUCCEEDED", "GROUPS_UPDATED", "Group memberships updated", {
        "group_ids": group_ids, "mode": mode, "changes": changed,
    }


def _update_contract_settings(db: Session, *, amo_id: str, user, payload, actor_user_id: str):
    source_contract = _contract_on(db, amo_id=amo_id, user_id=str(user.id), on_date=payload["effective_on"])
    if source_contract is None:
        raise ValueError("The person has no contract to update")
    settings = payload.get("contract_settings") or {}
    normalized: dict[str, Any] = {}
    for field, value in settings.items():
        if value is None:
            continue
        if field == "contract_type":
            value = models.ContractType(value)
        elif field == "employment_status":
            value = models.EmploymentStatus(value)
        normalized[field] = value
    changed = {
        field: str(value.value if hasattr(value, "value") else value)
        for field, value in normalized.items()
        if getattr(source_contract, field) != value
    }
    if not changed:
        return "SKIPPED", "CONTRACT_SETTINGS_ALREADY_MATCH", "Contract settings already match", {}
    contract = _version_contract(
        db, contract=source_contract, effective_on=payload["effective_on"], actor_user_id=actor_user_id,
    )
    for field, value in normalized.items():
        setattr(contract, field, value)
    if contract.effective_to and contract.effective_to < contract.effective_from:
        raise ValueError("Contract end date cannot precede the effective date")
    contract.updated_by_user_id = actor_user_id
    return "SUCCEEDED", "CONTRACT_SETTINGS_UPDATED", "Contract settings updated", changed


def _execute_offboarding(db: Session, *, plan, actor_user_id: str | None = None):
    user = db.query(account_models.User).filter(
        account_models.User.amo_id == plan.amo_id,
        account_models.User.id == plan.user_id,
    ).with_for_update().first()
    if user is None:
        plan.status = "FAILED"
        return False
    now = _utcnow()
    if plan.revoke_access:
        user.is_active = False
        user.deactivated_at = now
        user.deactivated_reason = plan.reason
        user.token_revoked_at = now
        account_services.sync_regulated_postholder_assignment(db, user)
    if plan.end_contracts:
        contracts = db.query(models.EmploymentContract).filter(
            models.EmploymentContract.amo_id == plan.amo_id,
            models.EmploymentContract.user_id == plan.user_id,
            or_(models.EmploymentContract.effective_to.is_(None),
                models.EmploymentContract.effective_to >= plan.effective_on),
        ).with_for_update().all()
        for contract in contracts:
            contract.employment_status = models.EmploymentStatus.TERMINATED
            contract.effective_to = max(contract.effective_from, plan.effective_on)
            contract.updated_by_user_id = actor_user_id or plan.requested_by_user_id
    placements = db.query(governance_models.WorkforcePersonPlacement).filter(
        governance_models.WorkforcePersonPlacement.amo_id == plan.amo_id,
        governance_models.WorkforcePersonPlacement.user_id == plan.user_id,
        or_(governance_models.WorkforcePersonPlacement.effective_to.is_(None),
            governance_models.WorkforcePersonPlacement.effective_to >= plan.effective_on),
    ).with_for_update().all()
    for placement in placements:
        placement.effective_to = max(placement.effective_from, plan.effective_on)
        placement.updated_by_user_id = actor_user_id or plan.requested_by_user_id
    if plan.remove_groups:
        db.query(account_models.UserGroupMember).filter(
            account_models.UserGroupMember.user_id == plan.user_id
        ).delete(synchronize_session=False)
    plan.status = "COMPLETED"
    plan.completed_at = now
    return True


def _schedule_offboarding(db: Session, *, amo_id: str, user, payload, actor_user_id: str):
    plan = db.query(governance_models.WorkforceOffboardingPlan).filter(
        governance_models.WorkforceOffboardingPlan.amo_id == amo_id,
        governance_models.WorkforceOffboardingPlan.user_id == user.id,
        governance_models.WorkforceOffboardingPlan.effective_on == payload["effective_on"],
    ).with_for_update().first()
    created = plan is None
    if plan is None:
        plan = governance_models.WorkforceOffboardingPlan(
            amo_id=amo_id, user_id=user.id, effective_on=payload["effective_on"],
            requested_by_user_id=actor_user_id,
        )
        db.add(plan)
    plan.reason = payload["offboarding_reason"].strip()
    plan.revoke_access = bool(payload.get("revoke_access", True))
    plan.end_contracts = bool(payload.get("end_contracts", True))
    plan.remove_groups = bool(payload.get("remove_groups", True))
    plan.status = "SCHEDULED"
    plan.completed_at = None
    db.flush()
    if plan.effective_on <= date.today():
        _execute_offboarding(db, plan=plan, actor_user_id=actor_user_id)
    return ("SUCCEEDED", "OFFBOARDING_SCHEDULED" if plan.status == "SCHEDULED" else "OFFBOARDING_COMPLETED",
            "Offboarding plan created" if created else "Offboarding plan updated",
            {"offboarding_plan_id": str(plan.id), "effective_on": str(plan.effective_on), "status": plan.status})


def process_personnel_mutation_item(db: Session, *, operation, item, actor):
    permissions.require_permission(
        db, user=actor, permission=permissions.PermissionCode.WORKFORCE_MANAGE_CONTRACTS
    )
    payload = dict(item.input_json or operation.payload_json or {})
    mutation_type = operation.operation_type
    if mutation_type not in MUTATION_TYPES:
        raise ValueError(f"Unsupported personnel mutation: {mutation_type}")
    if isinstance(payload.get("effective_on"), str):
        payload["effective_on"] = date.fromisoformat(payload["effective_on"])
    settings = payload.get("contract_settings")
    user = _user(
        db, amo_id=str(operation.amo_id), user_id=str(item.user_id),
        include_inactive=mutation_type == "SCHEDULE_OFFBOARDING",
    )
    before = {
        "department_id": str(user.department_id) if user.department_id else None,
        "position_title": user.position_title,
        "is_active": bool(user.is_active),
    }
    handlers = {
        "ASSIGN_ORGANIZATION": _assign_organization,
        "ASSIGN_POSITION": _assign_position,
        "ASSIGN_BASES": _assign_bases,
        "ASSIGN_SUPERVISOR": _assign_supervisor,
        "UPDATE_GROUPS": _update_groups,
        "UPDATE_CONTRACT_SETTINGS": _update_contract_settings,
        "SCHEDULE_OFFBOARDING": _schedule_offboarding,
    }
    outcome = handlers[mutation_type](
        db, amo_id=str(operation.amo_id), user=user, payload={**payload, "contract_settings": settings},
        actor_user_id=str(actor.id),
    )
    audit_services.log_event(
        db, amo_id=str(operation.amo_id), actor_user_id=str(actor.id),
        entity_type="User", entity_id=str(user.id), action=mutation_type.lower(),
        correlation_id=str(operation.id), before=before,
        after={"outcome_code": outcome[1], "result": outcome[3]},
        metadata={"module": "workforce", "bulk_operation_id": str(operation.id)},
    )
    return outcome


def apply_due_offboarding(db: Session, *, limit: int = 100) -> int:
    today = date.today()
    plans = db.query(governance_models.WorkforceOffboardingPlan).filter(
        governance_models.WorkforceOffboardingPlan.status == "SCHEDULED",
        governance_models.WorkforceOffboardingPlan.effective_on <= today,
    ).order_by(
        governance_models.WorkforceOffboardingPlan.effective_on.asc(),
        governance_models.WorkforceOffboardingPlan.id.asc(),
    ).limit(max(1, min(limit, 1000))).with_for_update(skip_locked=True).all()
    completed = 0
    for plan in plans:
        if _execute_offboarding(db, plan=plan):
            completed += 1
            audit_services.log_event(
                db, amo_id=str(plan.amo_id), actor_user_id=plan.requested_by_user_id,
                entity_type="WorkforceOffboardingPlan", entity_id=str(plan.id),
                action="complete", after={"user_id": str(plan.user_id), "effective_on": str(plan.effective_on)},
                metadata={"module": "workforce", "automated": True},
            )
    return completed
