"""Shared foundation services.

This module centralises cross-module records that must be consumed by several
operational modules. Personnel identity always resolves to ``accounts.users.id``.
Canonical base records and effective-dated personnel deployments are owned here,
not by Rostering or another operational workspace.
"""
from __future__ import annotations

import json
from datetime import date, datetime, timezone
from typing import Iterable, Optional

import sqlalchemy as sa
from sqlalchemy import or_
from sqlalchemy.orm import Session, selectinload

from ..accounts import models as account_models
from ..audit import services as audit_services
from ..quality import models as quality_models
from . import models, schemas


def canonical_user_id(value: object) -> str:
    """Resolve a user-like object or string to the canonical ``users.id`` string."""
    if isinstance(value, str) and value.strip():
        return value.strip()
    user_id = getattr(value, "id", None)
    if isinstance(user_id, str) and user_id.strip():
        return user_id.strip()
    raise ValueError("A canonical users.id value is required.")


def normalize_base_code(value: str) -> str:
    return "".join(str(value or "").strip().upper().split())


def _iso(value: Optional[datetime]) -> Optional[str]:
    if value is None:
        return None
    if value.tzinfo is None:
        value = value.replace(tzinfo=timezone.utc)
    return value.astimezone(timezone.utc).isoformat()


def _assert_expected_updated_at(row: object, expected: Optional[datetime], *, entity: str) -> None:
    if expected is None:
        return
    actual = getattr(row, "updated_at", None)
    if _iso(actual) != _iso(expected):
        raise RuntimeError(f"{entity}_REVISION_CONFLICT:{_iso(actual) or ''}")


def _audit(
    db: Session,
    *,
    amo_id: str,
    actor_user_id: Optional[str],
    entity_type: str,
    entity_id: str,
    action: str,
    before: Optional[dict] = None,
    after: Optional[dict] = None,
    reason: Optional[str] = None,
    critical: bool = False,
) -> None:
    audit_services.log_event(
        db,
        amo_id=amo_id,
        actor_user_id=actor_user_id,
        entity_type=entity_type,
        entity_id=entity_id,
        action=action,
        before=before,
        after=after,
        metadata={"module": "foundations", "reason": reason},
        critical=critical,
    )


def _base_snapshot(row: models.BaseStation) -> dict:
    return {
        "code": row.code,
        "name": row.name,
        "icao_code": row.icao_code,
        "iata_code": row.iata_code,
        "base_type": str(getattr(row.base_type, "value", row.base_type)),
        "time_zone": row.time_zone,
        "description": row.description,
        "is_active": row.is_active,
        "aliases": sorted(alias.alias for alias in (row.aliases or [])),
        "updated_at": _iso(row.updated_at),
    }


def _assignment_snapshot(row: models.UserBaseAssignment) -> dict:
    return {
        "user_id": row.user_id,
        "base_station_id": row.base_station_id,
        "assignment_kind": str(getattr(row.assignment_kind, "value", row.assignment_kind)),
        "effective_from": row.effective_from.isoformat(),
        "effective_to": row.effective_to.isoformat() if row.effective_to else None,
        "is_primary": row.is_primary,
        "note": row.note,
        "updated_at": _iso(row.updated_at),
    }


def list_base_stations(db: Session, *, amo_id: str, include_inactive: bool = False) -> list[models.BaseStation]:
    q = db.query(models.BaseStation).options(selectinload(models.BaseStation.aliases)).filter(models.BaseStation.amo_id == amo_id)
    if not include_inactive:
        q = q.filter(models.BaseStation.is_active.is_(True))
    return q.order_by(models.BaseStation.code.asc()).all()


def create_base_station(
    db: Session,
    *,
    amo_id: str,
    actor_user_id: Optional[str],
    payload: schemas.BaseStationCreate,
) -> models.BaseStation:
    item = models.BaseStation(
        amo_id=amo_id,
        code=normalize_base_code(payload.code),
        name=payload.name.strip(),
        icao_code=normalize_base_code(payload.icao_code) if payload.icao_code else None,
        iata_code=normalize_base_code(payload.iata_code) if payload.iata_code else None,
        base_type=payload.base_type,
        time_zone=payload.time_zone,
        description=payload.description,
        is_active=payload.is_active,
        created_by_user_id=actor_user_id,
        updated_by_user_id=actor_user_id,
    )
    db.add(item)
    db.flush()
    replace_base_aliases(db, amo_id=amo_id, base_station=item, aliases=payload.aliases, source_module="foundations")
    db.flush()
    _audit(
        db,
        amo_id=amo_id,
        actor_user_id=actor_user_id,
        entity_type="BaseStation",
        entity_id=item.id,
        action="create",
        after=_base_snapshot(item),
        critical=True,
    )
    return item


def update_base_station(
    db: Session,
    *,
    amo_id: str,
    base_station: models.BaseStation,
    actor_user_id: Optional[str],
    payload: schemas.BaseStationUpdate,
) -> models.BaseStation:
    _assert_expected_updated_at(base_station, payload.expected_updated_at, entity="BASE_STATION")
    before = _base_snapshot(base_station)
    values = payload.model_dump(exclude_unset=True)
    values.pop("expected_updated_at", None)
    reason = values.pop("reason", None)
    if "code" in values and values["code"] is not None:
        base_station.code = normalize_base_code(values.pop("code"))
    if "name" in values and values["name"] is not None:
        base_station.name = str(values.pop("name")).strip()
    if "icao_code" in values:
        value = values.pop("icao_code")
        base_station.icao_code = normalize_base_code(value) if value else None
    if "iata_code" in values:
        value = values.pop("iata_code")
        base_station.iata_code = normalize_base_code(value) if value else None
    aliases = values.pop("aliases", None) if "aliases" in values else None
    for key, value in values.items():
        setattr(base_station, key, value)
    base_station.updated_by_user_id = actor_user_id
    db.add(base_station)
    db.flush()
    if aliases is not None:
        replace_base_aliases(db, amo_id=amo_id, base_station=base_station, aliases=aliases, source_module="foundations")
        db.flush()
    action = "deactivate" if before["is_active"] and not base_station.is_active else "reactivate" if not before["is_active"] and base_station.is_active else "update"
    _audit(
        db,
        amo_id=amo_id,
        actor_user_id=actor_user_id,
        entity_type="BaseStation",
        entity_id=base_station.id,
        action=action,
        before=before,
        after=_base_snapshot(base_station),
        reason=reason,
        critical=action in {"deactivate", "reactivate"},
    )
    return base_station


def replace_base_aliases(
    db: Session,
    *,
    amo_id: str,
    base_station: models.BaseStation,
    aliases: Iterable[str],
    source_module: Optional[str],
) -> None:
    existing = db.query(models.BaseStationAlias).filter(
        models.BaseStationAlias.amo_id == amo_id,
        models.BaseStationAlias.base_station_id == base_station.id,
    ).all()
    for row in existing:
        db.delete(row)
    seen: set[str] = set()
    for alias in aliases:
        normalized = normalize_base_code(alias)
        if not normalized or normalized == base_station.code or normalized in seen:
            continue
        seen.add(normalized)
        db.add(models.BaseStationAlias(amo_id=amo_id, base_station_id=base_station.id, alias=normalized, source_module=source_module))


def _safe_count(db: Session, sql: str, params: dict) -> int:
    try:
        return int(db.execute(sa.text(sql), params).scalar() or 0)
    except Exception:
        return 0


def base_station_dependency_impact(db: Session, *, amo_id: str, base_station_id: str) -> schemas.BaseStationImpactRead:
    today = date.today()
    params = {"amo_id": amo_id, "base_station_id": base_station_id, "today": today}
    definitions = [
        (
            "ACTIVE_OR_FUTURE_DEPLOYMENTS",
            "SELECT COUNT(*) FROM user_base_assignments WHERE amo_id=:amo_id AND base_station_id=:base_station_id AND (effective_to IS NULL OR effective_to >= :today)",
            "Active or future personnel base deployments must be moved or ended.",
        ),
        (
            "ACTIVE_EMPLOYMENT_CONTRACTS",
            "SELECT COUNT(*) FROM employment_contracts WHERE amo_id=:amo_id AND (primary_base_station_id=:base_station_id OR secondary_base_station_id=:base_station_id) AND employment_status='ACTIVE' AND (effective_to IS NULL OR effective_to >= :today)",
            "Active employment contracts still reference this base.",
        ),
        (
            "CURRENT_OR_FUTURE_ROSTER_ASSIGNMENTS",
            "SELECT COUNT(*) FROM roster_assignments ra JOIN roster_versions rv ON rv.id=ra.version_id JOIN roster_periods rp ON rp.id=rv.period_id WHERE ra.amo_id=:amo_id AND ra.base_station_id=:base_station_id AND ra.deleted_at IS NULL AND rp.ends_on >= :today",
            "Draft, submitted, approved or published roster assignments still use this base.",
        ),
    ]
    dependencies: list[schemas.BaseDependencyRead] = []
    for dependency_type, sql, detail in definitions:
        count = _safe_count(db, sql, params)
        if count:
            dependencies.append(schemas.BaseDependencyRead(dependency_type=dependency_type, count=count, detail=detail, blocking=True))
    return schemas.BaseStationImpactRead(
        base_station_id=base_station_id,
        can_deactivate=not any(item.blocking and item.count > 0 for item in dependencies),
        dependencies=dependencies,
    )


def list_user_base_assignments(
    db: Session,
    *,
    amo_id: str,
    user_id: Optional[str] = None,
    active_on: Optional[date] = None,
    include_expired: bool = True,
) -> list[models.UserBaseAssignment]:
    q = (
        db.query(models.UserBaseAssignment)
        .options(selectinload(models.UserBaseAssignment.base_station))
        .filter(models.UserBaseAssignment.amo_id == amo_id)
    )
    if user_id:
        q = q.filter(models.UserBaseAssignment.user_id == user_id)
    if active_on:
        q = q.filter(
            models.UserBaseAssignment.effective_from <= active_on,
            or_(
                models.UserBaseAssignment.effective_to.is_(None),
                models.UserBaseAssignment.effective_to >= active_on,
            ),
        )
    elif not include_expired:
        today = date.today()
        q = q.filter(or_(models.UserBaseAssignment.effective_to.is_(None), models.UserBaseAssignment.effective_to >= today))
    return q.order_by(
        models.UserBaseAssignment.user_id.asc(),
        models.UserBaseAssignment.effective_from.desc(),
        models.UserBaseAssignment.created_at.desc(),
    ).all()


def _validate_assignment_window(
    db: Session,
    *,
    amo_id: str,
    user_id: str,
    assignment_kind: models.BaseAssignmentKind,
    effective_from: date,
    effective_to: Optional[date],
    is_primary: bool,
    exclude_id: Optional[str] = None,
) -> None:
    if effective_to and effective_to < effective_from:
        raise ValueError("effective_to must be on or after effective_from")
    if assignment_kind in {
        models.BaseAssignmentKind.TEMPORARY,
        models.BaseAssignmentKind.RELIEF,
        models.BaseAssignmentKind.TRAINING,
    } and effective_to is None:
        raise ValueError("Temporary, relief and training deployments require an end date")
    if not is_primary:
        return

    window_end = effective_to or date.max
    q = db.query(models.UserBaseAssignment).filter(
        models.UserBaseAssignment.amo_id == amo_id,
        models.UserBaseAssignment.user_id == user_id,
        models.UserBaseAssignment.is_primary.is_(True),
        models.UserBaseAssignment.effective_from <= window_end,
        or_(
            models.UserBaseAssignment.effective_to.is_(None),
            models.UserBaseAssignment.effective_to >= effective_from,
        ),
    )
    if exclude_id:
        q = q.filter(models.UserBaseAssignment.id != exclude_id)

    if assignment_kind == models.BaseAssignmentKind.HOME_BASE:
        q = q.filter(models.UserBaseAssignment.assignment_kind == models.BaseAssignmentKind.HOME_BASE)
        conflict_message = "A primary home-base assignment already covers part of this date range. End or amend it first."
    else:
        q = q.filter(models.UserBaseAssignment.assignment_kind != models.BaseAssignmentKind.HOME_BASE)
        conflict_message = "Another temporary, relief or training deployment already covers part of this date range."

    conflict = q.first()
    if conflict:
        raise ValueError(f"{conflict_message} Conflict {conflict.id}: {conflict.effective_from} to {conflict.effective_to or 'open ended'}.")


def _require_assignment_entities(
    db: Session,
    *,
    amo_id: str,
    user_id: str,
    base_station_id: str,
) -> tuple[account_models.User, models.BaseStation]:
    user = db.query(account_models.User).filter(
        account_models.User.id == user_id,
        account_models.User.amo_id == amo_id,
        account_models.User.is_active.is_(True),
        account_models.User.deactivated_at.is_(None),
        account_models.User.is_system_account.is_(False),
    ).first()
    if not user:
        raise ValueError("Only an active human user in this tenant may receive a base deployment.")
    base = db.query(models.BaseStation).filter(
        models.BaseStation.id == base_station_id,
        models.BaseStation.amo_id == amo_id,
    ).first()
    if not base:
        raise ValueError("Base station not found in tenant scope.")
    if not base.is_active:
        raise ValueError("Inactive base stations cannot receive new personnel deployments.")
    return user, base


def create_user_base_assignment(
    db: Session,
    *,
    amo_id: str,
    actor_user_id: Optional[str],
    payload: schemas.UserBaseAssignmentCreate,
) -> models.UserBaseAssignment:
    user, base = _require_assignment_entities(
        db,
        amo_id=amo_id,
        user_id=payload.user_id,
        base_station_id=payload.base_station_id,
    )
    _validate_assignment_window(
        db,
        amo_id=amo_id,
        user_id=user.id,
        assignment_kind=payload.assignment_kind,
        effective_from=payload.effective_from,
        effective_to=payload.effective_to,
        is_primary=payload.is_primary,
    )
    item = models.UserBaseAssignment(
        amo_id=amo_id,
        user_id=user.id,
        base_station_id=base.id,
        assignment_kind=payload.assignment_kind,
        effective_from=payload.effective_from,
        effective_to=payload.effective_to,
        is_primary=payload.is_primary,
        note=payload.note,
        created_by_user_id=actor_user_id,
    )
    db.add(item)
    db.flush()
    _audit(
        db,
        amo_id=amo_id,
        actor_user_id=actor_user_id,
        entity_type="UserBaseAssignment",
        entity_id=item.id,
        action="create",
        after=_assignment_snapshot(item),
        reason=payload.note,
        critical=True,
    )
    return item


def update_user_base_assignment(
    db: Session,
    *,
    amo_id: str,
    assignment: models.UserBaseAssignment,
    actor_user_id: Optional[str],
    payload: schemas.UserBaseAssignmentUpdate,
) -> models.UserBaseAssignment:
    _assert_expected_updated_at(assignment, payload.expected_updated_at, entity="USER_BASE_ASSIGNMENT")
    before = _assignment_snapshot(assignment)
    values = payload.model_dump(exclude_unset=True)
    values.pop("expected_updated_at", None)
    reason = values.pop("reason", None)
    base_station_id = str(values.get("base_station_id") or assignment.base_station_id)
    if "base_station_id" in values:
        _require_assignment_entities(
            db,
            amo_id=amo_id,
            user_id=assignment.user_id,
            base_station_id=base_station_id,
        )

    assignment_kind = values.get("assignment_kind", assignment.assignment_kind)
    effective_from = values.get("effective_from", assignment.effective_from)
    effective_to = values.get("effective_to", assignment.effective_to)
    is_primary = values.get("is_primary", assignment.is_primary)
    _validate_assignment_window(
        db,
        amo_id=amo_id,
        user_id=assignment.user_id,
        assignment_kind=assignment_kind,
        effective_from=effective_from,
        effective_to=effective_to,
        is_primary=is_primary,
        exclude_id=assignment.id,
    )

    for key, value in values.items():
        setattr(assignment, key, value)
    db.add(assignment)
    db.flush()
    _audit(
        db,
        amo_id=amo_id,
        actor_user_id=actor_user_id,
        entity_type="UserBaseAssignment",
        entity_id=assignment.id,
        action="update",
        before=before,
        after=_assignment_snapshot(assignment),
        reason=reason,
        critical=True,
    )
    return assignment


def cancel_future_user_base_assignment(
    db: Session,
    *,
    amo_id: str,
    assignment: models.UserBaseAssignment,
    actor_user_id: Optional[str],
    payload: schemas.UserBaseAssignmentCancel,
) -> None:
    _assert_expected_updated_at(assignment, payload.expected_updated_at, entity="USER_BASE_ASSIGNMENT")
    if assignment.effective_from <= date.today():
        raise ValueError("Only a future deployment can be cancelled. End an active deployment with an effective end date instead.")
    before = _assignment_snapshot(assignment)
    db.delete(assignment)
    db.flush()
    _audit(
        db,
        amo_id=amo_id,
        actor_user_id=actor_user_id,
        entity_type="UserBaseAssignment",
        entity_id=assignment.id,
        action="cancel",
        before=before,
        after=None,
        reason=payload.reason,
        critical=True,
    )


def effective_base_assignment(
    db: Session,
    *,
    amo_id: str,
    user_id: str,
    on_date: date,
) -> Optional[models.UserBaseAssignment]:
    rows = list_user_base_assignments(db, amo_id=amo_id, user_id=user_id, active_on=on_date)
    priority = {
        models.BaseAssignmentKind.TEMPORARY: 50,
        models.BaseAssignmentKind.RELIEF: 40,
        models.BaseAssignmentKind.TRAINING: 30,
        models.BaseAssignmentKind.OTHER: 20,
        models.BaseAssignmentKind.HOME_BASE: 10,
    }
    primary = [row for row in rows if row.is_primary]
    return max(primary or rows, key=lambda row: (priority.get(row.assignment_kind, 0), row.effective_from, row.created_at), default=None)


def list_availability(
    db: Session,
    *,
    amo_id: str,
    user_id: Optional[str] = None,
    active_at: Optional[datetime] = None,
) -> list[quality_models.UserAvailability]:
    q = db.query(quality_models.UserAvailability).filter(quality_models.UserAvailability.amo_id == amo_id)
    if user_id:
        q = q.filter(quality_models.UserAvailability.user_id == user_id)
    if active_at:
        q = q.filter(
            quality_models.UserAvailability.effective_from <= active_at,
            (quality_models.UserAvailability.effective_to.is_(None)) | (quality_models.UserAvailability.effective_to >= active_at),
        )
    return q.order_by(quality_models.UserAvailability.updated_at.desc()).all()


def create_availability(
    db: Session,
    *,
    amo_id: str,
    actor_user_id: Optional[str],
    payload: schemas.AvailabilityCreate,
) -> quality_models.UserAvailability:
    user = db.query(account_models.User).filter(
        account_models.User.id == payload.user_id,
        account_models.User.amo_id == amo_id,
        account_models.User.is_active.is_(True),
        account_models.User.is_system_account.is_(False),
    ).first()
    if not user:
        raise ValueError("Active user not found in tenant scope.")
    row = quality_models.UserAvailability(
        amo_id=amo_id,
        user_id=user.id,
        status=quality_models.UserAvailabilityStatus(payload.status),
        effective_from=payload.effective_from or datetime.now(timezone.utc),
        effective_to=payload.effective_to,
        note=payload.note,
        updated_by_user_id=actor_user_id,
    )
    db.add(row)
    db.flush()
    return row


def personnel_identity_health(db: Session, *, amo_id: str) -> schemas.PersonnelIdentityHealth:
    users = (
        db.query(account_models.User)
        .filter(account_models.User.amo_id == amo_id, account_models.User.is_active.is_(True), account_models.User.is_system_account.is_(False))
        .all()
    )
    profiles = (
        db.query(account_models.PersonnelProfile)
        .filter(account_models.PersonnelProfile.amo_id == amo_id, account_models.PersonnelProfile.status == "Active")
        .all()
    )
    profiles_by_user = {p.user_id: p for p in profiles if p.user_id}
    linked_user_ids = set(profiles_by_user)
    issues: list[schemas.PersonnelIdentityIssue] = []

    for user in users:
        if user.id not in linked_user_ids:
            issues.append(
                schemas.PersonnelIdentityIssue(
                    issue_type="ACTIVE_USER_WITHOUT_PERSONNEL_PROFILE",
                    user_id=user.id,
                    staff_code=getattr(user, "staff_code", None),
                    full_name=getattr(user, "full_name", None),
                    email=getattr(user, "email", None),
                    detail="Active human user is rosterable only after it is linked to a PersonnelProfile record.",
                )
            )
    for profile in profiles:
        if not profile.user_id:
            issues.append(
                schemas.PersonnelIdentityIssue(
                    issue_type="ACTIVE_PERSONNEL_PROFILE_WITHOUT_USER",
                    personnel_profile_id=profile.id,
                    person_id=profile.person_id,
                    full_name=profile.full_name,
                    email=profile.email,
                    detail="Active personnel profile cannot be used in rostering, training, work allocation, or attendance until linked to users.id.",
                )
            )

    return schemas.PersonnelIdentityHealth(
        amo_id=amo_id,
        active_users=len(users),
        active_personnel_profiles=len(profiles),
        linked_active_profiles=len(linked_user_ids),
        active_users_without_profile=sum(1 for issue in issues if issue.issue_type == "ACTIVE_USER_WITHOUT_PERSONNEL_PROFILE"),
        active_profiles_without_user=sum(1 for issue in issues if issue.issue_type == "ACTIVE_PERSONNEL_PROFILE_WITHOUT_USER"),
        issues=issues,
    )


def foundation_contracts() -> schemas.FoundationContracts:
    return schemas.FoundationContracts(
        canonical_personnel_key="users.id",
        ownership={
            "personnel_identity": "accounts.users.id; extended HR metadata in accounts.personnel_profiles",
            "licences_authorisations": "accounts.user_authorisations and accounts.authorisation_types",
            "training_due_and_currency": "training requirements, records, events, participants, and deferrals",
            "base_station_master": "foundations.base_stations",
            "personnel_base_deployments": "foundations.user_base_assignments",
            "availability_windows": "shared availability service, backed by user_availability during Phase 0",
            "work_orders_task_cards_assignments": "work module",
            "aircraft_master": "fleet module",
            "roster_assignments": "rostering module",
            "attendance_punches": "workforce attendance integration",
        },
        service_contracts={
            "identity_health": "GET /foundations/personnel/identity-health",
            "base_stations": "GET/POST /foundations/base-stations; GET /foundations/base-stations/{id}/impact; PUT /foundations/base-stations/{id}",
            "user_base_assignments": "GET/POST /foundations/user-base-assignments; PUT/DELETE /foundations/user-base-assignments/{id}",
            "availability": "GET/POST /foundations/availability",
        },
        canonical_frontend_routes={
            "admin_operating_structure": "/maintenance/:amoCode/admin/operating-structure",
            "admin_user_detail": "/maintenance/:amoCode/admin/users/:userId",
            "qms_training_person": "/maintenance/:amoCode/qms/training-competence/people/:userId",
            "planning_work_packages": "/maintenance/:amoCode/planning/work-packages",
            "planning_work_orders": "/maintenance/:amoCode/planning/work-orders",
            "production_control_board": "/maintenance/:amoCode/production/control-board",
            "maintenance_work_order_detail": "/maintenance/:amoCode/maintenance/work-orders/:woId",
            "technical_records_packs": "/maintenance/:amoCode/production/records/packs",
            "rostering_root": "/maintenance/:amoCode/rostering",
        },
    )
