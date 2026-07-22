from __future__ import annotations

import math
import os
from datetime import datetime, timedelta, timezone
from typing import Literal, Optional

import sqlalchemy as sa
from fastapi import Depends, HTTPException, Query, status
from pydantic import BaseModel, Field
from sqlalchemy import func, or_, text
from sqlalchemy.orm import Session

from amodb.apps.realtime import models as realtime_models
from amodb.database import get_db
from amodb.security import require_admin

from . import models, schemas
from .router_admin import (
    _current_availability_status,
    _display_title_for_user,
    _latest_availability_map_for_users,
    _manager_roles,
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


class AdminUserDirectoryPageRead(BaseModel):
    items: list[schemas.AdminUserDirectoryItem] = Field(default_factory=list)
    metrics: schemas.AdminUserDirectoryMetrics = Field(
        default_factory=schemas.AdminUserDirectoryMetrics
    )
    total: int = 0
    page: int = 1
    page_size: int = 50
    pages: int = 1
    has_next: bool = False
    has_previous: bool = False


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
    "/user-directory",
    response_model=AdminUserDirectoryPageRead,
    summary="Paginated user directory with lightweight presence",
)
def get_user_directory_page(
    amo_id: Optional[str] = None,
    page: int = Query(default=1, ge=1),
    page_size: int = Query(default=50, ge=10, le=100),
    skip: Optional[int] = Query(default=None, ge=0),
    limit: Optional[int] = Query(default=None, ge=1, le=250),
    search: Optional[str] = None,
    role: Optional[models.AccountRole] = None,
    account_status: DirectoryAccountStatus = "all",
    department_id: Optional[str] = None,
    sort_by: DirectorySortField = "name",
    sort_direction: DirectorySortDirection = "asc",
    db: Session = Depends(get_db),
    current_user: models.User = Depends(require_admin),
) -> AdminUserDirectoryPageRead:
    target_amo_id = amo_id if current_user.is_superuser and amo_id else current_user.amo_id
    if not target_amo_id:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="AMO context is required.",
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

    items: list[schemas.AdminUserDirectoryItem] = []
    for user in users:
        presence = presence_map[str(user.id)]
        availability_status = _current_availability_status(
            availability_map.get(str(user.id))
        )
        items.append(
            schemas.AdminUserDirectoryItem(
                id=str(user.id),
                amo_id=str(user.amo_id),
                department_id=user.department_id,
                department_name=(
                    departments.get(str(user.department_id))
                    if user.department_id
                    else None
                ),
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

    return AdminUserDirectoryPageRead(
        items=items,
        metrics=_directory_metrics(db, amo_id=str(target_amo_id)),
        total=total,
        page=effective_page,
        page_size=effective_size,
        pages=pages,
        has_next=effective_page < pages,
        has_previous=effective_page > 1,
    )
