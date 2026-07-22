from __future__ import annotations

import re
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]


def read(path: str) -> str:
    return (ROOT / path).read_text(encoding="utf-8")


def write(path: str, content: str) -> None:
    (ROOT / path).write_text(content, encoding="utf-8")


def replace_once(source: str, old: str, new: str, *, label: str) -> str:
    count = source.count(old)
    if count != 1:
        raise RuntimeError(f"{label}: expected one occurrence, found {count}")
    return source.replace(old, new, 1)


def replace_in_class(source: str, class_name: str, old: str, new: str) -> str:
    pattern = re.compile(rf"(class {re.escape(class_name)}\(Base\):.*?)(?=\nclass \w+\(Base\):|\Z)", re.S)
    match = pattern.search(source)
    if not match:
        raise RuntimeError(f"Missing class {class_name}")
    block = match.group(1)
    updated = replace_once(block, old, new, label=f"{class_name} relationship")
    return source[: match.start(1)] + updated + source[match.end(1) :]


def patch_workforce_models() -> None:
    path = "backend/amodb/apps/workforce/models.py"
    source = read(path)
    source = replace_in_class(
        source,
        "EmployeeLeaveBalance",
        '    user = relationship("User", lazy="joined")',
        '    user = relationship("User", foreign_keys=[user_id], lazy="joined")\n'
        '    updated_by = relationship("User", foreign_keys=[updated_by_user_id], lazy="joined")',
    )
    source = replace_in_class(
        source,
        "EmployeeAvailabilityEvent",
        '    user = relationship("User", lazy="joined")',
        '    user = relationship("User", foreign_keys=[user_id], lazy="joined")\n'
        '    created_by = relationship("User", foreign_keys=[created_by_user_id], lazy="joined")\n'
        '    updated_by = relationship("User", foreign_keys=[updated_by_user_id], lazy="joined")',
    )
    source = replace_in_class(
        source,
        "Timesheet",
        '    user = relationship("User", lazy="joined")',
        '    user = relationship("User", foreign_keys=[user_id], lazy="joined")\n'
        '    created_by = relationship("User", foreign_keys=[created_by_user_id], lazy="joined")\n'
        '    updated_by = relationship("User", foreign_keys=[updated_by_user_id], lazy="joined")',
    )
    source = replace_in_class(
        source,
        "OvertimeRequest",
        '    user = relationship("User", lazy="joined")',
        '    user = relationship("User", foreign_keys=[user_id], lazy="joined")\n'
        '    created_by = relationship("User", foreign_keys=[created_by_user_id], lazy="joined")',
    )
    source = replace_in_class(
        source,
        "LeaveRequestApproval",
        '    actor = relationship("User", lazy="joined")',
        '    actor = relationship("User", foreign_keys=[actor_user_id], lazy="joined")',
    )
    write(path, source)


def patch_account_schemas() -> None:
    path = "backend/amodb/apps/accounts/schemas.py"
    source = read(path)
    old = '''class AdminUserDirectoryRead(BaseModel):
    items: List[AdminUserDirectoryItem] = Field(default_factory=list)
    metrics: AdminUserDirectoryMetrics = Field(default_factory=AdminUserDirectoryMetrics)
'''
    new = '''class AdminUserDirectoryRead(BaseModel):
    items: List[AdminUserDirectoryItem] = Field(default_factory=list)
    metrics: AdminUserDirectoryMetrics = Field(default_factory=AdminUserDirectoryMetrics)
    total: int = 0
    page: int = 1
    page_size: int = 50
    pages: int = 1
    has_next: bool = False
    has_previous: bool = False
'''
    source = replace_once(source, old, new, label="directory pagination schema")
    write(path, source)


def directory_endpoint() -> str:
    return '''@router.get(
    "/user-directory",
    response_model=schemas.AdminUserDirectoryRead,
    summary="Paginated user directory with lightweight presence",
)
def get_user_directory_admin(
    amo_id: Optional[str] = None,
    page: int = Query(1, ge=1),
    page_size: int = Query(50, ge=10, le=100),
    skip: Optional[int] = Query(None, ge=0),
    limit: Optional[int] = Query(None, ge=1, le=250),
    search: Optional[str] = None,
    role: Optional[models.AccountRole] = None,
    account_status: str = Query("all", pattern="^(all|active|inactive)$"),
    department_id: Optional[str] = None,
    sort_by: str = Query(
        "name",
        pattern="^(name|staff_code|role|department|created_at|last_login_at)$",
    ),
    sort_direction: str = Query("asc", pattern="^(asc|desc)$"),
    db: Session = Depends(get_db),
    current_user: models.User = Depends(require_admin),
):
    target_amo_id = amo_id if current_user.is_superuser and amo_id else current_user.amo_id
    if not target_amo_id:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="AMO context is required.")

    # Keep skip/limit compatible for older clients while page/page_size is the
    # canonical contract used by the scalable directory.
    effective_page_size = min(max(limit or page_size, 1), 250)
    effective_page = page
    if skip is not None:
        effective_page = (skip // effective_page_size) + 1
    offset = (effective_page - 1) * effective_page_size

    scoped = db.query(models.User).filter(models.User.amo_id == target_amo_id)
    filtered = scoped
    if search and search.strip():
        term = f"%{search.strip()}%"
        filtered = filtered.filter(
            or_(
                models.User.full_name.ilike(term),
                models.User.email.ilike(term),
                models.User.staff_code.ilike(term),
                models.User.position_title.ilike(term),
            )
        )
    if role is not None:
        filtered = filtered.filter(models.User.role == role)
    if account_status == "active":
        filtered = filtered.filter(models.User.is_active.is_(True))
    elif account_status == "inactive":
        filtered = filtered.filter(models.User.is_active.is_(False))
    if department_id == "unassigned":
        filtered = filtered.filter(models.User.department_id.is_(None))
    elif department_id:
        filtered = filtered.filter(models.User.department_id == department_id)

    total = int(filtered.order_by(None).count())
    pages = max(1, (total + effective_page_size - 1) // effective_page_size)
    if effective_page > pages:
        effective_page = pages
        offset = (effective_page - 1) * effective_page_size

    sort_columns = {
        "name": models.User.full_name,
        "staff_code": models.User.staff_code,
        "role": models.User.role,
        "department": models.User.department_id,
        "created_at": models.User.created_at,
        "last_login_at": models.User.last_login_at,
    }
    sort_column = sort_columns[sort_by]
    order = sort_column.desc().nullslast() if sort_direction == "desc" else sort_column.asc().nullsfirst()
    users = (
        filtered.order_by(order, models.User.id.asc())
        .offset(offset)
        .limit(effective_page_size)
        .all()
    )

    page_user_ids = [str(user.id) for user in users]
    department_ids = sorted({str(user.department_id) for user in users if user.department_id})
    departments = {
        str(department.id): department.name
        for department in (
            db.query(models.Department).filter(models.Department.id.in_(department_ids)).all()
            if department_ids
            else []
        )
    }
    presence_map = _presence_map_for_users(
        db,
        amo_id=target_amo_id,
        user_ids=page_user_ids,
    )
    availability_map = _latest_availability_map_for_users(
        db,
        amo_id=target_amo_id,
        user_ids=page_user_ids,
    )

    items: list[schemas.AdminUserDirectoryItem] = []
    for user in users:
        presence = _resolve_presence_for_user(user=user, presence_map=presence_map)
        availability_status = _current_availability_status(availability_map.get(str(user.id)))
        items.append(
            schemas.AdminUserDirectoryItem(
                id=str(user.id),
                amo_id=str(user.amo_id),
                department_id=user.department_id,
                department_name=departments.get(str(user.department_id)) if user.department_id else None,
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
                presence_display=_presence_display_for_user(
                    user=user,
                    presence=presence,
                    availability_status=availability_status,
                ),
            )
        )

    manager_roles = list(_manager_roles())
    aggregate = (
        db.query(
            func.count(models.User.id).label("total"),
            func.coalesce(func.sum(sa.case((models.User.is_active.is_(True), 1), else_=0)), 0).label("active"),
            func.coalesce(func.sum(sa.case((models.User.is_active.is_(False), 1), else_=0)), 0).label("inactive"),
            func.coalesce(func.sum(sa.case((models.User.department_id.is_(None), 1), else_=0)), 0).label("departmentless"),
            func.coalesce(func.sum(sa.case((models.User.role.in_(manager_roles), 1), else_=0)), 0).label("managers"),
        )
        .filter(models.User.amo_id == target_amo_id)
        .one()
    )

    online_users = 0
    away_users = 0
    recently_active_users = 0
    now = datetime.now(timezone.utc)
    try:
        from amodb.apps.realtime import models as realtime_models

        fresh_cutoff = now - timedelta(seconds=PRESENCE_HEARTBEAT_GRACE_SECONDS)
        recent_cutoff = now - timedelta(minutes=RECENTLY_ACTIVE_WINDOW_MINUTES)
        fresh_rows = (
            db.query(realtime_models.PresenceState.state, func.count(realtime_models.PresenceState.id))
            .join(models.User, models.User.id == realtime_models.PresenceState.user_id)
            .filter(
                realtime_models.PresenceState.amo_id == target_amo_id,
                realtime_models.PresenceState.last_seen_at >= fresh_cutoff,
                models.User.is_active.is_(True),
            )
            .group_by(realtime_models.PresenceState.state)
            .all()
        )
        for raw_state, count in fresh_rows:
            state_value = str(getattr(raw_state, "value", raw_state) or "offline").lower()
            if state_value in {"online", "away"}:
                online_users += int(count or 0)
            if state_value == "away":
                away_users += int(count or 0)
        recently_active_users = int(
            db.query(func.count(func.distinct(realtime_models.PresenceState.user_id)))
            .filter(
                realtime_models.PresenceState.amo_id == target_amo_id,
                realtime_models.PresenceState.last_seen_at >= recent_cutoff,
            )
            .scalar()
            or 0
        )
    except Exception:
        pass

    on_leave_users = 0
    try:
        from amodb.apps.quality import models as quality_models

        on_leave_users = int(
            db.query(func.count(func.distinct(quality_models.UserAvailability.user_id)))
            .filter(
                quality_models.UserAvailability.amo_id == target_amo_id,
                quality_models.UserAvailability.status == quality_models.UserAvailabilityStatus.ON_LEAVE,
                quality_models.UserAvailability.effective_from <= now,
                or_(
                    quality_models.UserAvailability.effective_to.is_(None),
                    quality_models.UserAvailability.effective_to >= now,
                ),
            )
            .scalar()
            or 0
        )
    except Exception:
        pass

    metrics = schemas.AdminUserDirectoryMetrics(
        total_users=int(aggregate.total or 0),
        active_users=int(aggregate.active or 0),
        inactive_users=int(aggregate.inactive or 0),
        online_users=online_users,
        away_users=away_users,
        on_leave_users=on_leave_users,
        recently_active_users=recently_active_users,
        departmentless_users=int(aggregate.departmentless or 0),
        managers=int(aggregate.managers or 0),
    )
    return schemas.AdminUserDirectoryRead(
        items=items,
        metrics=metrics,
        total=total,
        page=effective_page,
        page_size=effective_page_size,
        pages=pages,
        has_next=effective_page < pages,
        has_previous=effective_page > 1,
    )
'''


def patch_router_admin() -> None:
    path = "backend/amodb/apps/accounts/router_admin.py"
    source = read(path)
    source = replace_once(
        source,
        "from fastapi import APIRouter, Depends, File, HTTPException, UploadFile, status",
        "from fastapi import APIRouter, Depends, File, HTTPException, Query, UploadFile, status",
        label="Query import",
    )
    source = replace_once(
        source,
        'PRESENCE_HEARTBEAT_GRACE_SECONDS = 20',
        'PRESENCE_HEARTBEAT_GRACE_SECONDS = max(45, int(os.getenv("PRESENCE_HEARTBEAT_GRACE_SECONDS", "90")))',
        label="presence grace",
    )
    old_resolver = '''def _resolve_presence_state(*, raw_state: str, last_seen_at: Optional[datetime], now: datetime) -> tuple[str, bool]:
    normalized_state = str(raw_state or "offline").lower()
    freshness_cutoff = now - timedelta(seconds=PRESENCE_HEARTBEAT_GRACE_SECONDS)
    is_fresh = bool(last_seen_at and last_seen_at >= freshness_cutoff)
    if not is_fresh:
        return "offline", False
    if normalized_state == "away":
        return "away", False
    return "online", normalized_state == "online"
'''
    new_resolver = '''def _resolve_presence_state(*, raw_state: str, last_seen_at: Optional[datetime], now: datetime) -> tuple[str, bool]:
    """Resolve connection freshness without treating a brief idle state as offline."""
    normalized_state = str(raw_state or "offline").lower()
    freshness_cutoff = now - timedelta(seconds=PRESENCE_HEARTBEAT_GRACE_SECONDS)
    is_fresh = bool(last_seen_at and last_seen_at >= freshness_cutoff)
    if not is_fresh:
        return "offline", False
    if normalized_state == "away":
        return "away", True
    return "online", True
'''
    source = replace_once(source, old_resolver, new_resolver, label="presence resolver")
    source = source.replace('            last_seen_label="Away now",', '            last_seen_label="Away",', 1)

    pattern = re.compile(
        r'@router\.get\(\n    "/user-directory",.*?(?=\n@router\.get\(\n    "/users/\{user_id\}/workspace")',
        re.S,
    )
    match = pattern.search(source)
    if not match:
        raise RuntimeError("User directory endpoint block not found")
    source = source[: match.start()] + directory_endpoint() + "\n\n" + source[match.end() :]
    write(path, source)


def patch_realtime_provider() -> None:
    path = "frontend/src/components/realtime/RealtimeProvider.tsx"
    source = read(path)
    source = replace_once(
        source,
        "const MAX_ACTIVITY = 1500;",
        "const MAX_ACTIVITY = 1500;\nconst PRESENCE_HEARTBEAT_INTERVAL_MS = 15_000;\nconst PRESENCE_AWAY_AFTER_MS = 5 * 60_000;",
        label="presence constants",
    )

    heartbeat_pattern = re.compile(
        r'  const sendPresenceHeartbeat = useCallback\(async \(state: "online" \| "away" = "online", reason = "heartbeat", keepalive = false\) => \{.*?\n  \}, \[isPlatformUser\]\);',
        re.S,
    )
    heartbeat_match = heartbeat_pattern.search(source)
    if not heartbeat_match:
        raise RuntimeError("Heartbeat callback not found")
    heartbeat = '''  const sendPresenceHeartbeat = useCallback(async (state: "online" | "away" = "online", reason = "heartbeat", keepalive = false) => {
    if (isPlatformUser || isLoginSurface()) return;
    const token = getToken();
    if (!token || !isRealtimeEnabled()) return;
    const previousState = presenceStateRef.current;
    try {
      const response = await fetch(`${getApiBaseUrl()}/api/realtime/presence`, {
        method: "POST",
        credentials: "include",
        keepalive,
        headers: {
          Accept: "application/json",
          Authorization: `Bearer ${token}`,
          "Content-Type": "application/json",
        },
        body: JSON.stringify({ state, reason }),
      });
      if (!response.ok) return;
      presenceStateRef.current = state;
      if (previousState !== state) {
        queryClient.invalidateQueries({ queryKey: ["admin-user-directory"] });
      }
    } catch {
      // Presence is deliberately best-effort; the server freshness window
      // tolerates transient browser throttling and short network interruptions.
    }
  }, [isPlatformUser, queryClient]);'''
    source = source[: heartbeat_match.start()] + heartbeat + source[heartbeat_match.end() :]

    effect_pattern = re.compile(
        r'  useEffect\(\(\) => \{\n    if \(isPlatformUser \|\| isLoginSurface\(\) \|\| !getToken\(\) \|\| !isRealtimeEnabled\(\)\) return;.*?\n  \}, \[isPlatformUser, sendPresenceHeartbeat\]\);',
        re.S,
    )
    effect_match = effect_pattern.search(source)
    if not effect_match:
        raise RuntimeError("Presence effect not found")
    effect = '''  useEffect(() => {
    if (isPlatformUser || isLoginSurface() || !getToken() || !isRealtimeEnabled()) return;

    const resolvePresenceState = (): "online" | "away" =>
      Date.now() - lastPortalActivityRef.current >= PRESENCE_AWAY_AFTER_MS ? "away" : "online";

    const pushPresence = (reason = "heartbeat", keepalive = false) => {
      void sendPresenceHeartbeat(resolvePresenceState(), reason, keepalive);
    };
    const markActive = (reason: string) => {
      lastPortalActivityRef.current = Date.now();
      void sendPresenceHeartbeat("online", reason);
    };

    void sendPresenceHeartbeat("online", "start");
    const timer = window.setInterval(() => pushPresence("heartbeat"), PRESENCE_HEARTBEAT_INTERVAL_MS);
    const handleVisibility = () => {
      if (!document.hidden) markActive("visible");
      else pushPresence("hidden");
    };
    const handleFocus = () => markActive("focus");
    const handlePageHide = () => {
      void sendPresenceHeartbeat("away", "pagehide", true);
    };
    document.addEventListener("visibilitychange", handleVisibility);
    window.addEventListener("focus", handleFocus);
    window.addEventListener("pagehide", handlePageHide);
    window.addEventListener("beforeunload", handlePageHide);
    return () => {
      window.clearInterval(timer);
      document.removeEventListener("visibilitychange", handleVisibility);
      window.removeEventListener("focus", handleFocus);
      window.removeEventListener("pagehide", handlePageHide);
      window.removeEventListener("beforeunload", handlePageHide);
    };
  }, [isPlatformUser, sendPresenceHeartbeat]);'''
    source = source[: effect_match.start()] + effect + source[effect_match.end() :]
    write(path, source)


def patch_presence_tests() -> None:
    path = "backend/amodb/apps/accounts/tests/test_presence_resolution.py"
    source = read(path)
    source = source.replace(
        "def test_presence_resolution_marks_fresh_away_as_active():",
        "def test_presence_resolution_marks_fresh_away_as_connected():",
        1,
    )
    source = replace_once(
        source,
        '    assert display.last_seen_label == "Away"',
        '    assert display.last_seen_label == "Away"',
        label="presence display assertion",
    )
    write(path, source)


def replace_legacy_page() -> None:
    write(
        "frontend/src/pages/AdminDashboardPage.tsx",
        'export { default } from "./admin-users/AdminUserManagementPage";\n',
    )


def main() -> None:
    patch_workforce_models()
    patch_account_schemas()
    patch_router_admin()
    patch_realtime_provider()
    patch_presence_tests()
    replace_legacy_page()


if __name__ == "__main__":
    main()
