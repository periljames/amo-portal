from __future__ import annotations

import math
import os
from datetime import date, datetime, timedelta, timezone
from typing import Literal, Optional

import sqlalchemy as sa
from fastapi import Depends, HTTPException, Query, status
from pydantic import BaseModel, Field
from sqlalchemy import func, or_, text
from sqlalchemy.orm import Session

from amodb.apps.audit import services as audit_services
from amodb.apps.foundations import models as foundation_models
from amodb.apps.realtime import models as realtime_models
from amodb.database import get_db
from amodb.security import require_admin

from . import models, schemas
from .router_admin import (
    _current_availability_status,
    _display_title_for_user,
    _get_personnel_profile_for_user,
    _latest_availability_map_for_users,
    _manager_roles,
    _set_profile_employment_state,
    router,
)

PRESENCE_FRESH_SECONDS = max(
    45,
    int(os.getenv("PRESENCE_HEARTBEAT_GRACE_SECONDS", "90")),
)
RECENT_ACTIVITY_MINUTES = max(
    1,
    int(os.getenv("RECENTLY_ACTIVE_WINDOW_MINUTES", "10")),
)

DirectoryAccountStatus = Literal["all", "active", "inactive"]
DirectorySortField = Literal[
    "name",
    "staff_code",
    "role",
    "department",
    "created_at",
    "last_login_at",
]
DirectorySortDirection = Literal["asc", "desc"]


class AdminUserDirectoryItemRead(schemas.AdminUserDirectoryItem):
    base_station_id: Optional[str] = None
    base_station_code: Optional[str] = None
    base_station_name: Optional[str] = None


class AdminUserDirectoryPageRead(BaseModel):
    items: list[AdminUserDirectoryItemRead] = Field(default_factory=list)
    metrics: schemas.AdminUserDirectoryMetrics = Field(
        default_factory=schemas.AdminUserDirectoryMetrics
    )
    total: int = 0
    page: int = 1
    page_size: int = 25
    pages: int = 1
    has_next: bool = False
    has_previous: bool = False
    base_station_count: int = 0
    unassigned_base_users: int = 0


class AdminDirectoryBaseRead(BaseModel):
    id: str
    code: str
    name: str
    base_type: str
    is_active: bool


class DirectoryDepartmentAssignmentRequest(BaseModel):
    user_ids: list[str] = Field(min_length=1, max_length=250)
    department_id: Optional[str] = None
    amo_id: Optional[str] = None


class DirectoryBaseAssignmentRequest(BaseModel):
    user_ids: list[str] = Field(min_length=1, max_length=250)
    base_station_id: Optional[str] = None
    amo_id: Optional[str] = None
    note: Optional[str] = None


class DirectoryPlacementResult(BaseModel):
    action: str
    processed: int
    affected_user_ids: list[str] = Field(default_factory=list)
    detail: str


def prevent_inactive_department_assignment(
    session: Session,
    _flush_context: object,
    _instances: object,
) -> None:
    """Reject a new department on an account whose final state is inactive."""
    candidates = list(session.new) + list(session.dirty)
    for candidate in candidates:
        if not isinstance(candidate, models.User):
            continue
        state = sa.inspect(candidate)
        history = state.attrs.department_id.history
        if (
            history.has_changes()
            and candidate.department_id
            and not bool(candidate.is_active)
        ):
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT,
                detail=(
                    "Inactive users cannot be assigned to a new department. "
                    "Enable the account first, then complete the department assignment."
                ),
            )


def _install_department_assignment_guard() -> None:
    if not sa.event.contains(
        Session,
        "before_flush",
        prevent_inactive_department_assignment,
    ):
        sa.event.listen(
            Session,
            "before_flush",
            prevent_inactive_department_assignment,
        )


_install_department_assignment_guard()


def _normalise_aware(value: Optional[datetime]) -> Optional[datetime]:
    if value is None:
        return None
    if value.tzinfo is None:
        return value.replace(tzinfo=timezone.utc)
    return value.astimezone(timezone.utc)


def resolve_directory_presence(
    *,
    raw_state: object,
    last_seen_at: Optional[datetime],
    now: datetime,
) -> schemas.UserPresenceRead:
    """Treat fresh heartbeat rows as connected, including an idle/away state."""
    last_seen = _normalise_aware(last_seen_at)
    current_time = _normalise_aware(now) or datetime.now(timezone.utc)
    state = str(getattr(raw_state, "value", raw_state) or "offline").lower()
    fresh = bool(
        last_seen
        and last_seen >= current_time - timedelta(seconds=PRESENCE_FRESH_SECONDS)
    )
    if not fresh:
        return schemas.UserPresenceRead(
            state="offline",
            is_online=False,
            last_seen_at=last_seen,
            source="realtime",
        )
    resolved_state = "away" if state == "away" else "online"
    return schemas.UserPresenceRead(
        state=resolved_state,
        is_online=True,
        last_seen_at=last_seen,
        source="realtime",
    )


def _presence_display(
    *,
    user: models.User,
    presence: schemas.UserPresenceRead,
    availability_status: Optional[str],
) -> schemas.UserPresenceDisplayRead:
    last_seen = presence.last_seen_at or user.last_login_at
    if not user.is_active:
        return schemas.UserPresenceDisplayRead(
            status_label="Inactive",
            last_seen_label="Never seen" if not last_seen else "Inactive",
            last_seen_at=last_seen,
            last_seen_at_display=last_seen.isoformat() if last_seen else None,
        )
    if availability_status == "ON_LEAVE":
        return schemas.UserPresenceDisplayRead(
            status_label="On leave",
            last_seen_label="Leave scheduled",
            last_seen_at=last_seen,
            last_seen_at_display=last_seen.isoformat() if last_seen else None,
        )
    if presence.is_online and presence.state == "away":
        return schemas.UserPresenceDisplayRead(
            status_label="Away",
            last_seen_label="Connected, idle",
            last_seen_at=last_seen,
            last_seen_at_display=last_seen.isoformat() if last_seen else None,
        )
    if presence.is_online:
        return schemas.UserPresenceDisplayRead(
            status_label="Online",
            last_seen_label="Active now",
            last_seen_at=last_seen,
            last_seen_at_display=last_seen.isoformat() if last_seen else None,
        )
    return schemas.UserPresenceDisplayRead(
        status_label="Offline",
        last_seen_label="Never seen" if not last_seen else "Last seen",
        last_seen_at=last_seen,
        last_seen_at_display=last_seen.isoformat() if last_seen else None,
    )


def _presence_map_for_page(
    db: Session,
    *,
    amo_id: str,
    users: list[models.User],
) -> dict[str, schemas.UserPresenceRead]:
    user_ids = [str(user.id) for user in users]
    if not user_ids:
        return {}
    rows = (
        db.query(realtime_models.PresenceState)
        .filter(
            realtime_models.PresenceState.amo_id == amo_id,
            realtime_models.PresenceState.user_id.in_(user_ids),
        )
        .all()
    )
    now = datetime.now(timezone.utc)
    result = {
        str(row.user_id): resolve_directory_presence(
            raw_state=row.state,
            last_seen_at=row.last_seen_at,
            now=now,
        )
        for row in rows
    }
    for user in users:
        result.setdefault(
            str(user.id),
            schemas.UserPresenceRead(
                state="offline",
                is_online=False,
                last_seen_at=user.last_login_at,
                source="login",
            ),
        )
    return result


def _safe_current_leave_count(db: Session, *, amo_id: str, now: datetime) -> int:
    """Count current leave without coupling the directory to the legacy ORM mapper."""
    try:
        inspector = sa.inspect(db.get_bind())
        if not inspector.has_table("user_availability"):
            return 0
        return int(
            db.execute(
                text(
                    """
                    SELECT COUNT(DISTINCT user_id)
                    FROM user_availability
                    WHERE amo_id = :amo_id
                      AND status = 'ON_LEAVE'
                      AND effective_from <= :now
                      AND (effective_to IS NULL OR effective_to >= :now)
                    """
                ),
                {"amo_id": amo_id, "now": now},
            ).scalar()
            or 0
        )
    except Exception:
        return 0


def _directory_metrics(db: Session, *, amo_id: str) -> schemas.AdminUserDirectoryMetrics:
    manager_roles = list(_manager_roles())
    aggregate = (
        db.query(
            func.count(models.User.id).label("total"),
            func.coalesce(
                func.sum(sa.case((models.User.is_active.is_(True), 1), else_=0)),
                0,
            ).label("active"),
            func.coalesce(
                func.sum(sa.case((models.User.is_active.is_(False), 1), else_=0)),
                0,
            ).label("inactive"),
            func.coalesce(
                func.sum(sa.case((models.User.department_id.is_(None), 1), else_=0)),
                0,
            ).label("departmentless"),
            func.coalesce(
                func.sum(sa.case((models.User.role.in_(manager_roles), 1), else_=0)),
                0,
            ).label("managers"),
        )
        .filter(models.User.amo_id == amo_id)
        .one()
    )

    now = datetime.now(timezone.utc)
    fresh_cutoff = now - timedelta(seconds=PRESENCE_FRESH_SECONDS)
    recent_cutoff = now - timedelta(minutes=RECENT_ACTIVITY_MINUTES)
    state_counts = (
        db.query(
            realtime_models.PresenceState.state,
            func.count(realtime_models.PresenceState.id),
        )
        .join(models.User, models.User.id == realtime_models.PresenceState.user_id)
        .filter(
            realtime_models.PresenceState.amo_id == amo_id,
            realtime_models.PresenceState.last_seen_at >= fresh_cutoff,
            models.User.is_active.is_(True),
        )
        .group_by(realtime_models.PresenceState.state)
        .all()
    )
    online_users = 0
    away_users = 0
    for raw_state, count in state_counts:
        state = str(getattr(raw_state, "value", raw_state) or "offline").lower()
        if state in {"online", "away"}:
            online_users += int(count or 0)
        if state == "away":
            away_users += int(count or 0)

    recently_active = int(
        db.query(func.count(func.distinct(realtime_models.PresenceState.user_id)))
        .filter(
            realtime_models.PresenceState.amo_id == amo_id,
            realtime_models.PresenceState.last_seen_at >= recent_cutoff,
        )
        .scalar()
        or 0
    )

    return schemas.AdminUserDirectoryMetrics(
        total_users=int(aggregate.total or 0),
        active_users=int(aggregate.active or 0),
        inactive_users=int(aggregate.inactive or 0),
        online_users=online_users,
        away_users=away_users,
        on_leave_users=_safe_current_leave_count(db, amo_id=amo_id, now=now),
        recently_active_users=recently_active,
        departmentless_users=int(aggregate.departmentless or 0),
        managers=int(aggregate.managers or 0),
    )


def _current_primary_assignment_filter(*, amo_id: str, active_on: date):
    return (
        foundation_models.UserBaseAssignment.amo_id == amo_id,
        foundation_models.UserBaseAssignment.is_primary.is_(True),
        foundation_models.UserBaseAssignment.effective_from <= active_on,
        or_(
            foundation_models.UserBaseAssignment.effective_to.is_(None),
            foundation_models.UserBaseAssignment.effective_to >= active_on,
        ),
    )


def _primary_base_map_for_users(
    db: Session,
    *,
    amo_id: str,
    user_ids: list[str],
) -> dict[str, foundation_models.BaseStation]:
    if not user_ids:
        return {}
    today = date.today()
    rows = (
        db.query(
            foundation_models.UserBaseAssignment,
            foundation_models.BaseStation,
        )
        .join(
            foundation_models.BaseStation,
            foundation_models.BaseStation.id
            == foundation_models.UserBaseAssignment.base_station_id,
        )
        .filter(
            *_current_primary_assignment_filter(
                amo_id=amo_id,
                active_on=today,
            ),
            foundation_models.UserBaseAssignment.user_id.in_(user_ids),
        )
        .order_by(
            foundation_models.UserBaseAssignment.user_id.asc(),
            foundation_models.UserBaseAssignment.effective_from.desc(),
            foundation_models.UserBaseAssignment.created_at.desc(),
        )
        .all()
    )
    result: dict[str, foundation_models.BaseStation] = {}
    for assignment, base in rows:
        result.setdefault(str(assignment.user_id), base)
    return result


def _placement_metrics(db: Session, *, amo_id: str) -> tuple[int, int]:
    today = date.today()
    active_base_count = int(
        db.query(func.count(foundation_models.BaseStation.id))
        .filter(
            foundation_models.BaseStation.amo_id == amo_id,
            foundation_models.BaseStation.is_active.is_(True),
        )
        .scalar()
        or 0
    )
    assigned_active_users = (
        sa.select(foundation_models.UserBaseAssignment.user_id)
        .where(
            *_current_primary_assignment_filter(
                amo_id=amo_id,
                active_on=today,
            )
        )
        .distinct()
    )
    unassigned_base_users = int(
        db.query(func.count(models.User.id))
        .filter(
            models.User.amo_id == amo_id,
            models.User.is_active.is_(True),
            ~models.User.id.in_(assigned_active_users),
        )
        .scalar()
        or 0
    )
    return active_base_count, unassigned_base_users


def _resolve_target_amo_id(
    *,
    current_user: models.User,
    requested_amo_id: Optional[str],
) -> str:
    target = (
        requested_amo_id
        if current_user.is_superuser and requested_amo_id
        else current_user.amo_id
    )
    if not target:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="AMO context is required.",
        )
    return str(target)


def _managed_users_for_ids(
    db: Session,
    *,
    amo_id: str,
    user_ids: list[str],
) -> list[models.User]:
    normalized_ids = list(
        dict.fromkeys(str(user_id).strip() for user_id in user_ids if str(user_id).strip())
    )
    if not normalized_ids:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Select at least one user.",
        )
    users = (
        db.query(models.User)
        .filter(
            models.User.amo_id == amo_id,
            models.User.id.in_(normalized_ids),
        )
        .order_by(models.User.full_name.asc())
        .all()
    )
    if len(users) != len(normalized_ids):
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=(
                "One or more selected users no longer exist in the active AMO. "
                "Refresh the directory and try again."
            ),
        )
    return users


def _remove_legacy_route() -> None:
    router.routes[:] = [
        route
        for route in router.routes
        if not (
            getattr(route, "path", None) == "/accounts/admin/user-directory"
            and "GET" in (getattr(route, "methods", None) or set())
        )
    ]


_remove_legacy_route()


@router.get(
    "/user-directory/base-stations",
    response_model=list[AdminDirectoryBaseRead],
    summary="List active operating bases for user placement",
)
def list_directory_base_stations(
    amo_id: Optional[str] = None,
    db: Session = Depends(get_db),
    current_user: models.User = Depends(require_admin),
) -> list[AdminDirectoryBaseRead]:
    target_amo_id = _resolve_target_amo_id(
        current_user=current_user,
        requested_amo_id=amo_id,
    )
    rows = (
        db.query(foundation_models.BaseStation)
        .filter(
            foundation_models.BaseStation.amo_id == target_amo_id,
            foundation_models.BaseStation.is_active.is_(True),
        )
        .order_by(
            foundation_models.BaseStation.name.asc(),
            foundation_models.BaseStation.code.asc(),
        )
        .all()
    )
    return [
        AdminDirectoryBaseRead(
            id=str(row.id),
            code=row.code,
            name=row.name,
            base_type=str(getattr(row.base_type, "value", row.base_type)),
            is_active=bool(row.is_active),
        )
        for row in rows
    ]


@router.post(
    "/user-directory/department-assignment",
    response_model=DirectoryPlacementResult,
    summary="Assign or clear a department for selected users",
)
def assign_directory_departments(
    payload: DirectoryDepartmentAssignmentRequest,
    db: Session = Depends(get_db),
    current_user: models.User = Depends(require_admin),
) -> DirectoryPlacementResult:
    target_amo_id = _resolve_target_amo_id(
        current_user=current_user,
        requested_amo_id=payload.amo_id,
    )
    users = _managed_users_for_ids(
        db,
        amo_id=target_amo_id,
        user_ids=payload.user_ids,
    )
    department = None
    if payload.department_id:
        department = (
            db.query(models.Department)
            .filter(
                models.Department.id == payload.department_id,
                models.Department.amo_id == target_amo_id,
                models.Department.is_active.is_(True),
            )
            .first()
        )
        if not department:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="The selected active department was not found in this AMO.",
            )
        inactive = [user for user in users if not user.is_active]
        if inactive:
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT,
                detail=(
                    f"{len(inactive)} selected inactive account(s) cannot receive "
                    "a new department. Enable them first or remove them from the selection."
                ),
            )

    department_name = department.name if department else ""
    for user in users:
        before_department_id = user.department_id
        user.department_id = department.id if department else None
        profile = _get_personnel_profile_for_user(db, user=user)
        _set_profile_employment_state(
            profile,
            department_name=department_name,
        )
        db.add(user)
        if profile is not None:
            db.add(profile)
        audit_services.log_event(
            db,
            amo_id=user.amo_id,
            actor_user_id=str(current_user.id),
            entity_type="accounts.user",
            entity_id=str(user.id),
            action="DEPARTMENT_ASSIGNED" if department else "DEPARTMENT_CLEARED",
            before={"department_id": before_department_id},
            after={"department_id": user.department_id},
            metadata={"module": "accounts", "source": "user_directory"},
        )
    db.commit()
    affected_ids = [str(user.id) for user in users]
    return DirectoryPlacementResult(
        action="assign_department" if department else "clear_department",
        processed=len(affected_ids),
        affected_user_ids=affected_ids,
        detail=(
            f"{len(affected_ids)} user(s) assigned to {department.name}."
            if department
            else f"Department cleared for {len(affected_ids)} user(s)."
        ),
    )


@router.post(
    "/user-directory/base-assignment",
    response_model=DirectoryPlacementResult,
    summary="Assign or clear the primary operating base for selected users",
)
def assign_directory_bases(
    payload: DirectoryBaseAssignmentRequest,
    db: Session = Depends(get_db),
    current_user: models.User = Depends(require_admin),
) -> DirectoryPlacementResult:
    target_amo_id = _resolve_target_amo_id(
        current_user=current_user,
        requested_amo_id=payload.amo_id,
    )
    users = _managed_users_for_ids(
        db,
        amo_id=target_amo_id,
        user_ids=payload.user_ids,
    )
    base = None
    if payload.base_station_id:
        base = (
            db.query(foundation_models.BaseStation)
            .filter(
                foundation_models.BaseStation.id == payload.base_station_id,
                foundation_models.BaseStation.amo_id == target_amo_id,
                foundation_models.BaseStation.is_active.is_(True),
            )
            .first()
        )
        if not base:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="The selected active base was not found in this AMO.",
            )
        inactive = [user for user in users if not user.is_active]
        if inactive:
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT,
                detail=(
                    f"{len(inactive)} selected inactive account(s) cannot receive "
                    "a new base. Enable them first or remove them from the selection."
                ),
            )

    today = date.today()
    for user in users:
        current_rows = (
            db.query(foundation_models.UserBaseAssignment)
            .filter(
                *_current_primary_assignment_filter(
                    amo_id=target_amo_id,
                    active_on=today,
                ),
                foundation_models.UserBaseAssignment.user_id == user.id,
            )
            .order_by(
                foundation_models.UserBaseAssignment.effective_from.desc(),
                foundation_models.UserBaseAssignment.created_at.desc(),
            )
            .all()
        )
        current_base_id = (
            str(current_rows[0].base_station_id)
            if current_rows
            else None
        )
        if base and current_base_id == str(base.id):
            continue
        for current in current_rows:
            current.is_primary = False
            db.add(current)
        if base:
            db.add(
                foundation_models.UserBaseAssignment(
                    amo_id=target_amo_id,
                    user_id=user.id,
                    base_station_id=base.id,
                    assignment_kind=foundation_models.BaseAssignmentKind.HOME_BASE,
                    effective_from=today,
                    effective_to=None,
                    is_primary=True,
                    note=(payload.note or "Assigned from user directory").strip(),
                    created_by_user_id=current_user.id,
                )
            )
        audit_services.log_event(
            db,
            amo_id=user.amo_id,
            actor_user_id=str(current_user.id),
            entity_type="foundations.user_base_assignment",
            entity_id=str(user.id),
            action="PRIMARY_BASE_ASSIGNED" if base else "PRIMARY_BASE_CLEARED",
            before={"base_station_id": current_base_id},
            after={"base_station_id": str(base.id) if base else None},
            metadata={"module": "foundations", "source": "user_directory"},
        )
    db.commit()
    affected_ids = [str(user.id) for user in users]
    return DirectoryPlacementResult(
        action="assign_base" if base else "clear_base",
        processed=len(affected_ids),
        affected_user_ids=affected_ids,
        detail=(
            f"{len(affected_ids)} user(s) assigned to {base.name}."
            if base
            else f"Primary base cleared for {len(affected_ids)} user(s)."
        ),
    )


@router.get(
    "/user-directory",
    response_model=AdminUserDirectoryPageRead,
    summary="Paginated user directory with lightweight presence and placement",
)
def get_user_directory_page(
    amo_id: Optional[str] = None,
    page: int = Query(default=1, ge=1),
    page_size: int = Query(default=25, ge=10, le=100),
    skip: Optional[int] = Query(default=None, ge=0),
    limit: Optional[int] = Query(default=None, ge=1, le=250),
    search: Optional[str] = None,
    role: Optional[models.AccountRole] = None,
    account_status: DirectoryAccountStatus = "all",
    department_id: Optional[str] = None,
    base_station_id: Optional[str] = None,
    sort_by: DirectorySortField = "name",
    sort_direction: DirectorySortDirection = "asc",
    db: Session = Depends(get_db),
    current_user: models.User = Depends(require_admin),
) -> AdminUserDirectoryPageRead:
    target_amo_id = _resolve_target_amo_id(
        current_user=current_user,
        requested_amo_id=amo_id,
    )

    effective_size = min(max(limit or page_size, 1), 250)
    effective_page = ((skip or 0) // effective_size) + 1 if skip is not None else page

    query = db.query(models.User).filter(models.User.amo_id == target_amo_id)
    if search and search.strip():
        term = f"%{search.strip()}%"
        query = query.filter(
            or_(
                models.User.full_name.ilike(term),
                models.User.email.ilike(term),
                models.User.staff_code.ilike(term),
                models.User.position_title.ilike(term),
            )
        )
    if role is not None:
        query = query.filter(models.User.role == role)
    if account_status == "active":
        query = query.filter(models.User.is_active.is_(True))
    elif account_status == "inactive":
        query = query.filter(models.User.is_active.is_(False))
    if department_id == "unassigned":
        query = query.filter(models.User.department_id.is_(None))
    elif department_id:
        query = query.filter(models.User.department_id == department_id)

    today = date.today()
    current_base_users = (
        sa.select(foundation_models.UserBaseAssignment.user_id)
        .where(
            *_current_primary_assignment_filter(
                amo_id=target_amo_id,
                active_on=today,
            )
        )
    )
    if base_station_id == "unassigned":
        query = query.filter(~models.User.id.in_(current_base_users))
    elif base_station_id:
        selected_base_users = current_base_users.where(
            foundation_models.UserBaseAssignment.base_station_id
            == base_station_id
        )
        query = query.filter(models.User.id.in_(selected_base_users))

    total = int(query.order_by(None).count())
    pages = max(1, math.ceil(total / effective_size))
    effective_page = min(effective_page, pages)
    offset = (effective_page - 1) * effective_size

    sort_columns = {
        "name": models.User.full_name,
        "staff_code": models.User.staff_code,
        "role": models.User.role,
        "department": models.User.department_id,
        "created_at": models.User.created_at,
        "last_login_at": models.User.last_login_at,
    }
    sort_column = sort_columns[sort_by]
    ordering = (
        sort_column.desc().nullslast()
        if sort_direction == "desc"
        else sort_column.asc().nullsfirst()
    )
    users = (
        query.order_by(ordering, models.User.id.asc())
        .offset(offset)
        .limit(effective_size)
        .all()
    )

    department_ids = sorted(
        {str(user.department_id) for user in users if user.department_id}
    )
    departments = {
        str(department.id): department.name
        for department in (
            db.query(models.Department)
            .filter(models.Department.id.in_(department_ids))
            .all()
            if department_ids
            else []
        )
    }
    presence_map = _presence_map_for_page(
        db,
        amo_id=str(target_amo_id),
        users=users,
    )
    availability_map = _latest_availability_map_for_users(
        db,
        amo_id=str(target_amo_id),
        user_ids=[str(user.id) for user in users],
    )
    base_map = _primary_base_map_for_users(
        db,
        amo_id=str(target_amo_id),
        user_ids=[str(user.id) for user in users],
    )

    items: list[AdminUserDirectoryItemRead] = []
    for user in users:
        presence = presence_map[str(user.id)]
        availability_status = _current_availability_status(
            availability_map.get(str(user.id))
        )
        base = base_map.get(str(user.id))
        items.append(
            AdminUserDirectoryItemRead(
                id=str(user.id),
                amo_id=str(user.amo_id),
                department_id=user.department_id,
                department_name=(
                    departments.get(str(user.department_id))
                    if user.department_id
                    else None
                ),
                base_station_id=str(base.id) if base else None,
                base_station_code=base.code if base else None,
                base_station_name=base.name if base else None,
                staff_code=user.staff_code,
                email=user.email,
                first_name=user.first_name,
                last_name=user.last_name,
                full_name=user.full_name,
                role=user.role,
                position_title=user.position_title,
                is_active=user.is_active,
                is_superuser=user.is_superuser,
                is_amo_admin=user.is_amo_admin,
                display_title=_display_title_for_user(user),
                availability_status=availability_status,
                last_login_at=user.last_login_at,
                created_at=user.created_at,
                updated_at=user.updated_at,
                presence=presence,
                presence_display=_presence_display(
                    user=user,
                    presence=presence,
                    availability_status=availability_status,
                ),
            )
        )

    base_station_count, unassigned_base_users = _placement_metrics(
        db,
        amo_id=str(target_amo_id),
    )
    return AdminUserDirectoryPageRead(
        items=items,
        metrics=_directory_metrics(db, amo_id=str(target_amo_id)),
        total=total,
        page=effective_page,
        page_size=effective_size,
        pages=pages,
        has_next=effective_page < pages,
        has_previous=effective_page > 1,
        base_station_count=base_station_count,
        unassigned_base_users=unassigned_base_users,
    )
