# backend/amodb/apps/foundations/services.py
"""Shared Phase 0 foundation services.

This module deliberately centralises cross-module reads/writes that several
future modules, especially Duty Rostering, must share. The canonical personnel
identifier is always ``accounts.users.id``.
"""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Iterable, Optional

from sqlalchemy.orm import Session, selectinload

from ..accounts import models as account_models
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
    return item


def update_base_station(
    db: Session,
    *,
    amo_id: str,
    base_station: models.BaseStation,
    actor_user_id: Optional[str],
    payload: schemas.BaseStationUpdate,
) -> models.BaseStation:
    if payload.code is not None:
        base_station.code = normalize_base_code(payload.code)
    if payload.name is not None:
        base_station.name = payload.name.strip()
    if payload.icao_code is not None:
        base_station.icao_code = normalize_base_code(payload.icao_code) if payload.icao_code else None
    if payload.iata_code is not None:
        base_station.iata_code = normalize_base_code(payload.iata_code) if payload.iata_code else None
    if payload.base_type is not None:
        base_station.base_type = payload.base_type
    if payload.time_zone is not None:
        base_station.time_zone = payload.time_zone
    if payload.description is not None:
        base_station.description = payload.description
    if payload.is_active is not None:
        base_station.is_active = payload.is_active
    base_station.updated_by_user_id = actor_user_id
    db.add(base_station)
    db.flush()
    if payload.aliases is not None:
        replace_base_aliases(db, amo_id=amo_id, base_station=base_station, aliases=payload.aliases, source_module="foundations")
    return base_station


def replace_base_aliases(
    db: Session,
    *,
    amo_id: str,
    base_station: models.BaseStation,
    aliases: Iterable[str],
    source_module: Optional[str],
) -> None:
    existing = db.query(models.BaseStationAlias).filter(models.BaseStationAlias.base_station_id == base_station.id).all()
    for row in existing:
        db.delete(row)
    seen: set[str] = set()
    for alias in aliases:
        normalized = normalize_base_code(alias)
        if not normalized or normalized == base_station.code or normalized in seen:
            continue
        seen.add(normalized)
        db.add(models.BaseStationAlias(amo_id=amo_id, base_station_id=base_station.id, alias=normalized, source_module=source_module))


def create_user_base_assignment(
    db: Session,
    *,
    amo_id: str,
    actor_user_id: Optional[str],
    payload: schemas.UserBaseAssignmentCreate,
) -> models.UserBaseAssignment:
    user = db.query(account_models.User).filter(account_models.User.id == payload.user_id, account_models.User.amo_id == amo_id).first()
    if not user:
        raise ValueError("User not found in tenant scope.")
    base = db.query(models.BaseStation).filter(models.BaseStation.id == payload.base_station_id, models.BaseStation.amo_id == amo_id).first()
    if not base:
        raise ValueError("Base station not found in tenant scope.")
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
    return item


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
    user = db.query(account_models.User).filter(account_models.User.id == payload.user_id, account_models.User.amo_id == amo_id).first()
    if not user:
        raise ValueError("User not found in tenant scope.")
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
            "availability_windows": "shared availability service, backed by user_availability during Phase 0",
            "work_orders_task_cards_assignments": "work module",
            "aircraft_master": "fleet module",
            "future_roster_assignments": "rostering module",
            "future_attendance_punches": "attendance integration under rostering/foundations contract",
        },
        service_contracts={
            "identity_health": "GET /foundations/personnel/identity-health",
            "base_stations": "GET/POST /foundations/base-stations; PUT /foundations/base-stations/{base_station_id}",
            "user_base_assignments": "POST /foundations/user-base-assignments",
            "availability": "GET/POST /foundations/availability",
        },
        canonical_frontend_routes={
            "admin_user_detail": "/maintenance/:amoCode/admin/users/:userId",
            "qms_training_person": "/maintenance/:amoCode/qms/training-competence/people/:userId",
            "planning_work_packages": "/maintenance/:amoCode/planning/work-packages",
            "planning_work_orders": "/maintenance/:amoCode/planning/work-orders",
            "production_control_board": "/maintenance/:amoCode/production/control-board",
            "maintenance_work_order_detail": "/maintenance/:amoCode/maintenance/work-orders/:woId",
            "technical_records_packs": "/maintenance/:amoCode/production/records/packs",
            "future_rostering_root": "/maintenance/:amoCode/rostering",
        },
    )
