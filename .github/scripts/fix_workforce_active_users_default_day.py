from __future__ import annotations

from pathlib import Path


def replace_once(path: str, old: str, new: str) -> None:
    file_path = Path(path)
    text = file_path.read_text(encoding="utf-8")
    if new in text:
        return
    if old not in text:
        raise RuntimeError(f"Expected block not found in {path}: {old[:120]!r}")
    file_path.write_text(text.replace(old, new, 1), encoding="utf-8")


def append_once(path: str, marker: str, block: str) -> None:
    file_path = Path(path)
    text = file_path.read_text(encoding="utf-8")
    if marker in text:
        return
    file_path.write_text(text.rstrip() + "\n\n" + block.strip() + "\n", encoding="utf-8")


# Backend response contracts.
replace_once(
    "backend/amodb/apps/workforce/hr_schemas.py",
    """class HrPersonReadiness(HrSchema):\n    user_id: str\n    contract_id: str\n    staff_code: str\n    full_name: str\n""",
    """class HrPersonReadiness(HrSchema):\n    user_id: str\n    contract_id: Optional[str] = None\n    staff_code: str\n    full_name: str\n    email: Optional[str] = None\n    has_effective_contract: bool = False\n    uses_default_day_pattern: bool = False\n""",
)
replace_once(
    "backend/amodb/apps/workforce/hr_schemas.py",
    """class HrDashboardResponse(HrSchema):\n    generated_at: datetime\n    can_manage_contracts: bool\n""",
    """class HrDashboardResponse(HrSchema):\n    generated_at: datetime\n    can_manage_contracts: bool\n    can_initialize_default_day_pattern: bool\n""",
)
replace_once(
    "backend/amodb/apps/workforce/hr_schemas.py",
    """    active_employee_count: int\n    onboarding_employee_count: int\n""",
    """    active_employee_count: int\n    employees_without_contract_count: int\n    onboarding_employee_count: int\n""",
)
append_once(
    "backend/amodb/apps/workforce/hr_schemas.py",
    "class HrDefaultDayBootstrapResponse",
    """
class HrDefaultDayBootstrapResponse(HrSchema):
    shift_template_id: str
    work_pattern_id: str
    eligible_user_count: int
    assigned_user_count: int
    already_assigned_count: int
    skipped_conflict_count: int
""",
)

# Active-account based presentation and explicit default-day bootstrap.
append_once(
    "backend/amodb/apps/workforce/hr_service.py",
    "def _active_tenant_users",
    r'''
def _active_tenant_users(db: Session, *, amo_id: str) -> list[account_models.User]:
    """Return every active human tenant account, regardless of HR completeness."""
    return db.query(account_models.User).options(
        joinedload(account_models.User.department),
    ).filter(
        account_models.User.amo_id == amo_id,
        account_models.User.is_active.is_(True),
        account_models.User.is_system_account.is_(False),
    ).order_by(
        account_models.User.full_name.asc(),
        account_models.User.staff_code.asc(),
        account_models.User.id.asc(),
    ).all()


def _current_contracts_by_user(
    db: Session,
    *,
    amo_id: str,
    on_date: date,
) -> dict[str, models.EmploymentContract]:
    result: dict[str, models.EmploymentContract] = {}
    for row in _active_contracts(db, amo_id=amo_id, on_date=on_date):
        result.setdefault(str(row.user_id), row)
    return result


def _person_readiness_for_user(
    user: account_models.User,
    *,
    contract: Optional[models.EmploymentContract],
    pattern: Optional[models.EmployeeWorkPatternAssignment],
    leave: Optional[models.LeaveRequest],
) -> hr_schemas.HrPersonReadiness:
    reasons: list[str] = []
    status_value = _value(contract.employment_status) if contract else None
    if contract is None:
        reasons.append("No effective employment contract exists.")
    else:
        if status_value != models.EmploymentStatus.ACTIVE.value:
            reasons.append(f"Employment status is {status_value.replace('_', ' ').lower()}.")
        if not contract.primary_base_station_id:
            reasons.append("No primary base is assigned.")

    work_pattern = pattern.work_pattern if pattern else None
    if not work_pattern or not work_pattern.is_active:
        reasons.append("No active work pattern is assigned.")
    if leave and _value(leave.status) == models.LeaveRequestStatus.HR_APPROVED.value:
        reasons.append("Employee is currently on approved leave.")

    if status_value == models.EmploymentStatus.SUSPENDED.value:
        state = "BLOCKED"
    elif reasons:
        state = "NEEDS_ATTENTION"
    else:
        state = "READY"

    return hr_schemas.HrPersonReadiness(
        user_id=str(user.id),
        contract_id=contract.id if contract else None,
        staff_code=str(getattr(user, "staff_code", "") or ""),
        full_name=_display_name(user) or str(user.id),
        email=getattr(user, "email", None),
        has_effective_contract=contract is not None,
        uses_default_day_pattern=bool(work_pattern and work_pattern.code == "DEFAULT-DAY-5X2"),
        position_title=getattr(user, "position_title", None),
        department_code=_department_code(user),
        employment_status=status_value,
        contract_type=_value(contract.contract_type) if contract else None,
        contract_effective_from=contract.effective_from if contract else None,
        contract_effective_to=contract.effective_to if contract else None,
        primary_base_station_id=contract.primary_base_station_id if contract else None,
        primary_base_code=getattr(contract.primary_base, "code", None) if contract else None,
        supervisor_name=_display_name(contract.supervisor) if contract else None,
        standard_weekly_minutes=contract.standard_weekly_minutes if contract else 2400,
        standard_daily_minutes=contract.standard_daily_minutes if contract else 480,
        fte_percentage=float(contract.fte_percentage) if contract else 100.0,
        cost_centre=contract.cost_centre if contract else None,
        payroll_number=contract.payroll_number if contract else None,
        overtime_eligible=contract.overtime_eligible if contract else True,
        night_shift_eligible=contract.night_shift_eligible if contract else True,
        standby_eligible=contract.standby_eligible if contract else True,
        work_pattern_code=getattr(work_pattern, "code", None),
        work_pattern_name=getattr(work_pattern, "name", None),
        work_pattern_effective_from=pattern.effective_from if pattern else None,
        active_leave_status=_value(leave.status) if leave else None,
        readiness_state=state,
        readiness_reasons=reasons,
    )


def list_people_page_v2(
    db: Session,
    *,
    amo_id: str,
    page: int = 1,
    page_size: int = 100,
    search: Optional[str] = None,
) -> hr_schemas.HrPeoplePage:
    today = date.today()
    now = _utcnow()
    users = _active_tenant_users(db, amo_id=amo_id)
    user_ids = [str(user.id) for user in users]
    contracts = _current_contracts_by_user(db, amo_id=amo_id, on_date=today)
    patterns = _effective_patterns(db, amo_id=amo_id, user_ids=user_ids, on_date=today)
    leave_by_user = _active_leave(db, amo_id=amo_id, user_ids=user_ids, now=now)
    items = [
        _person_readiness_for_user(
            user,
            contract=contracts.get(str(user.id)),
            pattern=patterns.get(str(user.id)),
            leave=leave_by_user.get(str(user.id)),
        )
        for user in users
    ]
    needle = str(search or "").strip().lower()
    if needle:
        items = [
            item for item in items
            if any(
                needle in str(value or "").lower()
                for value in (
                    item.full_name,
                    item.email,
                    item.staff_code,
                    item.position_title,
                    item.department_code,
                    item.primary_base_code,
                    item.payroll_number,
                )
            )
        ]
    items.sort(key=lambda item: (
        item.has_effective_contract,
        item.readiness_state == "READY",
        item.full_name.lower(),
        item.user_id,
    ))
    total = len(items)
    safe_page_size = max(1, min(int(page_size), 200))
    pages = (total + safe_page_size - 1) // safe_page_size if total else 0
    safe_page = max(1, int(page))
    start = (safe_page - 1) * safe_page_size
    return hr_schemas.HrPeoplePage(
        items=items[start:start + safe_page_size],
        page=safe_page,
        page_size=safe_page_size,
        total=total,
        pages=pages,
    )


def dashboard_v2(
    db: Session,
    *,
    amo_id: str,
    current_user: account_models.User,
    people_limit: int = 200,
) -> hr_schemas.HrDashboardResponse:
    response = dashboard(
        db,
        amo_id=amo_id,
        current_user=current_user,
        people_limit=people_limit,
    )
    today = date.today()
    now = _utcnow()
    users = _active_tenant_users(db, amo_id=amo_id)
    user_ids = [str(user.id) for user in users]
    contracts = _current_contracts_by_user(db, amo_id=amo_id, on_date=today)
    patterns = _effective_patterns(db, amo_id=amo_id, user_ids=user_ids, on_date=today)
    leave_by_user = _active_leave(db, amo_id=amo_id, user_ids=user_ids, now=now)
    people = [
        _person_readiness_for_user(
            user,
            contract=contracts.get(str(user.id)),
            pattern=patterns.get(str(user.id)),
            leave=leave_by_user.get(str(user.id)),
        )
        for user in users
    ]
    people.sort(key=lambda item: (
        item.has_effective_contract,
        item.readiness_state == "READY",
        item.full_name.lower(),
        item.user_id,
    ))
    without_contract = [user for user in users if str(user.id) not in contracts]
    without_pattern = [user for user in users if str(user.id) not in patterns]
    without_base = [
        user for user in users
        if (contract := contracts.get(str(user.id))) is not None and not contract.primary_base_station_id
    ]

    response.active_employee_count = len(users)
    response.employees_without_contract_count = len(without_contract)
    response.onboarding_employee_count = sum(
        1 for contract in contracts.values()
        if _value(contract.employment_status) == models.EmploymentStatus.ONBOARDING.value
    )
    response.suspended_employee_count = sum(
        1 for contract in contracts.values()
        if _value(contract.employment_status) == models.EmploymentStatus.SUSPENDED.value
    )
    response.employees_without_pattern_count = len(without_pattern)
    response.employees_without_base_count = len(without_base)
    response.people = people[:people_limit]
    response.can_initialize_default_day_pattern = all((
        permissions.has_permission(
            db,
            user=current_user,
            permission=permissions.PermissionCode.WORKFORCE_MANAGE_CONTRACTS,
        ),
        permissions.has_permission(
            db,
            user=current_user,
            permission=permissions.PermissionCode.ROSTER_MANAGE_PATTERNS,
        ),
        permissions.has_permission(
            db,
            user=current_user,
            permission=permissions.PermissionCode.ROSTER_MANAGE_SHIFT_TEMPLATES,
        ),
    ))

    metric_by_key = {metric.key: metric for metric in response.metrics}
    if "active" in metric_by_key:
        metric_by_key["active"].value = len(users)
        metric_by_key["active"].detail = "Active tenant user accounts"
    if "patterns" in metric_by_key:
        metric_by_key["patterns"].value = len(without_pattern)
        metric_by_key["patterns"].detail = "Active users without a current pattern"
        metric_by_key["patterns"].tone = "danger" if without_pattern else "good"
    response.metrics.insert(1, hr_schemas.HrMetric(
        key="contract_gaps",
        label="Contract gaps",
        value=len(without_contract),
        detail="Active users without an effective contract",
        tone="danger" if without_contract else "good",
    ))

    missing_contract_actions = [
        hr_schemas.HrActionItem(
            id=f"contract-missing:{user.id}",
            category="CONTRACT",
            severity="BLOCKER",
            title="Employment contract missing",
            detail="This active tenant user cannot be rostered until an effective Workforce contract is created.",
            user_id=str(user.id),
            user_name=_display_name(user),
            action_label="Create contract",
            action_path=f"people/{user.id}?section=contract",
        )
        for user in without_contract[:50]
    ]
    response.action_queue = (missing_contract_actions + list(response.action_queue))[:100]
    return response


def bootstrap_default_day_pattern(
    db: Session,
    *,
    amo_id: str,
    actor_user_id: str,
) -> hr_schemas.HrDefaultDayBootstrapResponse:
    """Create one controlled day-shift baseline and assign it only where safe."""
    from ..rostering import models as roster_models

    amo = db.query(account_models.AMO).filter(
        account_models.AMO.id == amo_id,
    ).with_for_update().one()
    today = date.today()
    timezone_name = str(amo.time_zone or "UTC")

    shift = db.query(roster_models.ShiftTemplate).filter(
        roster_models.ShiftTemplate.amo_id == amo_id,
        roster_models.ShiftTemplate.code == "DEFAULT-DAY",
    ).first()
    if shift is None:
        shift = roster_models.ShiftTemplate(
            amo_id=amo_id,
            code="DEFAULT-DAY",
            label="Default day shift",
            kind=roster_models.ShiftTemplateKind.DAY,
            default_start_time="08:00",
            default_end_time="17:00",
            duration_minutes=480,
            counts_as_duty=True,
            is_active=True,
            display_order=10,
            description="System baseline for active staff without an assigned work pattern; planner review remains required.",
            icon_name="Sun",
            created_by_user_id=actor_user_id,
            updated_by_user_id=actor_user_id,
        )
        db.add(shift)
        db.flush()
    elif not shift.is_active:
        shift.is_active = True
        shift.updated_by_user_id = actor_user_id
        db.add(shift)

    pattern = db.query(models.WorkPattern).options(
        joinedload(models.WorkPattern.days),
    ).filter(
        models.WorkPattern.amo_id == amo_id,
        models.WorkPattern.code == "DEFAULT-DAY-5X2",
    ).first()
    if pattern is None:
        pattern = models.WorkPattern(
            amo_id=amo_id,
            code="DEFAULT-DAY-5X2",
            name="Default day shift · Monday to Friday",
            description="Five default day duties followed by two days off. This is a visible baseline, not a published roster.",
            cycle_length_days=7,
            is_active=True,
            timezone_name=timezone_name,
            created_by_user_id=actor_user_id,
            updated_by_user_id=actor_user_id,
        )
        db.add(pattern)
        db.flush()
        for day_index in range(7):
            duty = day_index < 5
            db.add(models.WorkPatternDay(
                amo_id=amo_id,
                work_pattern_id=pattern.id,
                cycle_day_index=day_index,
                shift_template_id=shift.id if duty else None,
                status=models.PatternDayStatus.DUTY if duty else models.PatternDayStatus.OFF,
                start_time_local="08:00" if duty else None,
                end_time_local="17:00" if duty else None,
                spans_next_day=False,
                planned_minutes=480 if duty else 0,
            ))
    else:
        if not pattern.is_active:
            pattern.is_active = True
        pattern.updated_by_user_id = actor_user_id
        db.add(pattern)

    users = _active_tenant_users(db, amo_id=amo_id)
    contracts = _current_contracts_by_user(db, amo_id=amo_id, on_date=today)
    eligible_users = [
        user for user in users
        if (contract := contracts.get(str(user.id))) is not None
        and _value(contract.employment_status) in {
            models.EmploymentStatus.ACTIVE.value,
            models.EmploymentStatus.ONBOARDING.value,
        }
    ]
    current_rows = db.query(models.EmployeeWorkPatternAssignment).options(
        joinedload(models.EmployeeWorkPatternAssignment.work_pattern),
    ).filter(
        models.EmployeeWorkPatternAssignment.amo_id == amo_id,
        models.EmployeeWorkPatternAssignment.user_id.in_([str(user.id) for user in eligible_users] or ["__none__"]),
        models.EmployeeWorkPatternAssignment.effective_from <= today,
        or_(
            models.EmployeeWorkPatternAssignment.effective_to.is_(None),
            models.EmployeeWorkPatternAssignment.effective_to >= today,
        ),
    ).all()
    occupied = {str(row.user_id): row for row in current_rows}

    assigned = 0
    already_assigned = 0
    skipped_conflict = 0
    for user in eligible_users:
        current = occupied.get(str(user.id))
        if current is not None:
            if current.work_pattern and current.work_pattern.is_active:
                already_assigned += 1
            else:
                skipped_conflict += 1
            continue
        future = db.query(models.EmployeeWorkPatternAssignment).filter(
            models.EmployeeWorkPatternAssignment.amo_id == amo_id,
            models.EmployeeWorkPatternAssignment.user_id == user.id,
            models.EmployeeWorkPatternAssignment.effective_from > today,
        ).order_by(models.EmployeeWorkPatternAssignment.effective_from.asc()).first()
        effective_to = future.effective_from - timedelta(days=1) if future else None
        if effective_to is not None and effective_to < today:
            skipped_conflict += 1
            continue
        db.add(models.EmployeeWorkPatternAssignment(
            amo_id=amo_id,
            user_id=user.id,
            work_pattern_id=pattern.id,
            effective_from=today,
            effective_to=effective_to,
            cycle_anchor_date=today,
            created_by_user_id=actor_user_id,
        ))
        assigned += 1

    db.flush()
    return hr_schemas.HrDefaultDayBootstrapResponse(
        shift_template_id=shift.id,
        work_pattern_id=pattern.id,
        eligible_user_count=len(eligible_users),
        assigned_user_count=assigned,
        already_assigned_count=already_assigned,
        skipped_conflict_count=skipped_conflict,
    )
''',
)

# Route the HR surfaces through the active-user implementation and expose the controlled bootstrap.
replace_once(
    "backend/amodb/apps/workforce/hr_router.py",
    """    return hr_service.dashboard(\n        db,\n        amo_id=_amo(current_user),\n        current_user=current_user,\n        people_limit=people_limit,\n    )\n""",
    """    return hr_service.dashboard_v2(\n        db,\n        amo_id=_amo(current_user),\n        current_user=current_user,\n        people_limit=people_limit,\n    )\n""",
)
replace_once(
    "backend/amodb/apps/workforce/hr_router.py",
    """    return hr_service.list_people_page(\n        db,\n        amo_id=_amo(current_user),\n        page=page,\n        page_size=page_size,\n        search=search,\n    )\n""",
    """    return hr_service.list_people_page_v2(\n        db,\n        amo_id=_amo(current_user),\n        page=page,\n        page_size=page_size,\n        search=search,\n    )\n""",
)
replace_once(
    "backend/amodb/apps/workforce/hr_router.py",
    """@router.get(\"/work-patterns\", response_model=list[schemas.WorkPatternRead])\n""",
    """@router.post(\"/default-day-pattern\", response_model=hr_schemas.HrDefaultDayBootstrapResponse)\ndef hr_bootstrap_default_day_pattern(\n    db: Session = Depends(get_db),\n    current_user: account_models.User = Depends(get_current_active_user),\n):\n    for permission in (\n        permissions.PermissionCode.WORKFORCE_MANAGE_CONTRACTS,\n        permissions.PermissionCode.ROSTER_MANAGE_PATTERNS,\n        permissions.PermissionCode.ROSTER_MANAGE_SHIFT_TEMPLATES,\n    ):\n        permissions.require_permission(db, user=current_user, permission=permission)\n    try:\n        result = hr_service.bootstrap_default_day_pattern(\n            db, amo_id=_amo(current_user), actor_user_id=current_user.id\n        )\n        db.commit()\n        return result\n    except ValueError as exc:\n        db.rollback()\n        raise _error(str(exc), code=\"HR_DEFAULT_DAY_PATTERN_INVALID\") from exc\n\n\n@router.get(\"/work-patterns\", response_model=list[schemas.WorkPatternRead])\n""",
)

# Frontend contracts and service.
replace_once(
    "frontend/src/types/workforceHr.ts",
    """  user_id: string;\n  contract_id: string;\n  staff_code: string;\n  full_name: string;\n""",
    """  user_id: string;\n  contract_id?: string | null;\n  staff_code: string;\n  full_name: string;\n  email?: string | null;\n  has_effective_contract: boolean;\n  uses_default_day_pattern: boolean;\n""",
)
replace_once(
    "frontend/src/types/workforceHr.ts",
    """  can_manage_contracts: boolean;\n  can_manage_leave_balances: boolean;\n""",
    """  can_manage_contracts: boolean;\n  can_initialize_default_day_pattern: boolean;\n  can_manage_leave_balances: boolean;\n""",
)
replace_once(
    "frontend/src/types/workforceHr.ts",
    """  active_employee_count: number;\n  onboarding_employee_count: number;\n""",
    """  active_employee_count: number;\n  employees_without_contract_count: number;\n  onboarding_employee_count: number;\n""",
)
append_once(
    "frontend/src/types/workforceHr.ts",
    "export type HrDefaultDayBootstrap",
    """
export type HrDefaultDayBootstrap = {
  shift_template_id: string;
  work_pattern_id: string;
  eligible_user_count: number;
  assigned_user_count: number;
  already_assigned_count: number;
  skipped_conflict_count: number;
};
""",
)
replace_once(
    "frontend/src/services/workforceHr.ts",
    """import type { HrDashboard, HrOvertimeRequest, HrPeoplePage } from \"../types/workforceHr\";\n""",
    """import type { HrDashboard, HrDefaultDayBootstrap, HrOvertimeRequest, HrPeoplePage } from \"../types/workforceHr\";\n""",
)
replace_once(
    "frontend/src/services/workforceHr.ts",
    """export function listWorkforceHrPatterns(includeInactive = false): Promise<WorkPatternRead[]> {\n""",
    """export function bootstrapWorkforceHrDefaultDayPattern(): Promise<HrDefaultDayBootstrap> {\n  return apiJson(\"/workforce/hr/default-day-pattern\", { method: \"POST\" });\n}\n\nexport function listWorkforceHrPatterns(includeInactive = false): Promise<WorkPatternRead[]> {\n""",
)

# Frontend register: create missing contracts, show active users, and offer an explicit default-day baseline.
replace_once(
    "frontend/src/pages/rostering/components/WorkforceHrWorkspace.tsx",
    """  approveTimesheet,\n  downloadPayrollExport,\n""",
    """  approveTimesheet,\n  createEmploymentContract,\n  downloadPayrollExport,\n""",
)
replace_once(
    "frontend/src/pages/rostering/components/WorkforceHrWorkspace.tsx",
    """  assignWorkforceHrPattern,\n  decideWorkforceHrOvertime,\n""",
    """  assignWorkforceHrPattern,\n  bootstrapWorkforceHrDefaultDayPattern,\n  decideWorkforceHrOvertime,\n""",
)
replace_once(
    "frontend/src/pages/rostering/components/WorkforceHrWorkspace.tsx",
    """           canManage={dashboard.can_manage_contracts}\n           busy={busy}\n""",
    """           canManage={dashboard.can_manage_contracts}\n           canInitializeDefaults={dashboard.can_initialize_default_day_pattern}\n           onInitializeDefaults={() => runAction(\"default-day-pattern\", bootstrapWorkforceHrDefaultDayPattern)}\n           busy={busy}\n""",
)
replace_once(
    "frontend/src/pages/rostering/components/WorkforceHrWorkspace.tsx",
    """  people, search, onSearch, page, pages, total, loading, onPage, bases, loadingBases, canManage, busy, runAction,\n""",
    """  people, search, onSearch, page, pages, total, loading, onPage, bases, loadingBases, canManage, canInitializeDefaults, onInitializeDefaults, busy, runAction,\n""",
)
replace_once(
    "frontend/src/pages/rostering/components/WorkforceHrWorkspace.tsx",
    """  canManage: boolean;\n  busy: string | null;\n""",
    """  canManage: boolean;\n  canInitializeDefaults: boolean;\n  onInitializeDefaults: () => Promise<void>;\n  busy: string | null;\n""",
)
replace_once(
    "frontend/src/pages/rostering/components/WorkforceHrWorkspace.tsx",
    """      employment_status: (person.employment_status || \"ACTIVE\") as EmploymentStatus,\n      effective_from: person.contract_effective_from || isoDate(new Date()),\n""",
    """      employment_status: (person.has_effective_contract ? person.employment_status : \"ACTIVE\") as EmploymentStatus,\n      effective_from: person.contract_effective_from || isoDate(new Date()),\n""",
)
replace_once(
    "frontend/src/pages/rostering/components/WorkforceHrWorkspace.tsx",
    """      standard_weekly_hours: String(person.standard_weekly_minutes / 60),\n      standard_daily_hours: String(person.standard_daily_minutes / 60),\n""",
    """      standard_weekly_hours: String((person.standard_weekly_minutes || 2400) / 60),\n      standard_daily_hours: String((person.standard_daily_minutes || 480) / 60),\n""",
)
replace_once(
    "frontend/src/pages/rostering/components/WorkforceHrWorkspace.tsx",
    """    void runAction(`employment-contract:${editing.contract_id}`, async () => {\n      await updateEmploymentContract(editing.contract_id, {\n        contract_type: draft.contract_type,\n""",
    """    void runAction(`employment-contract:${editing.contract_id || editing.user_id}`, async () => {\n      const payload = {\n        user_id: editing.user_id,\n        contract_type: draft.contract_type,\n""",
)
replace_once(
    "frontend/src/pages/rostering/components/WorkforceHrWorkspace.tsx",
    """        standby_eligible: draft.standby_eligible,\n      });\n      close();\n""",
    """        standby_eligible: draft.standby_eligible,\n      };\n      if (editing.contract_id) {\n        await updateEmploymentContract(editing.contract_id, payload);\n      } else {\n        await createEmploymentContract(payload);\n      }\n      close();\n""",
)
replace_once(
    "frontend/src/pages/rostering/components/WorkforceHrWorkspace.tsx",
    """      <div className=\"wr-section-heading\"><div><span className=\"wr-eyebrow\">People and contracts</span><h2>Employee readiness register</h2><p>Managers can correct effective contract, hours and home-base data here. Other users retain a read-only operational view.</p></div><label className=\"hr-search\"><Search size={15} /><input value={search} onChange={(event) => onSearch(event.target.value)} placeholder=\"Search staff, role, base or department\" /></label></div>\n""",
    """      <div className=\"wr-section-heading\"><div><span className=\"wr-eyebrow\">People and contracts</span><h2>Employee readiness register</h2><p>Every active tenant user appears here. Missing contracts, bases and patterns remain visible as readiness blockers instead of removing the employee.</p></div><div className=\"wr-actions\">{canInitializeDefaults ? <button type=\"button\" className=\"wr-button wr-button--secondary\" disabled={Boolean(busy)} onClick={() => void onInitializeDefaults()}><CalendarDays size={15} /> Apply default day pattern</button> : null}<label className=\"hr-search\"><Search size={15} /><input value={search} onChange={(event) => onSearch(event.target.value)} placeholder=\"Search staff, email, role, base or department\" /></label></div></div>\n""",
)
replace_once(
    "frontend/src/pages/rostering/components/WorkforceHrWorkspace.tsx",
    """{person.work_pattern_name || \"Automatic rotation unavailable\"}</span></div><div><StatusPill value={person.readiness_state} />""",
    """{person.work_pattern_name || \"Automatic rotation unavailable\"}</span>{person.uses_default_day_pattern ? <small>System baseline · planner review required</small> : null}</div><div><StatusPill value={person.readiness_state} />""",
)
replace_once(
    "frontend/src/pages/rostering/components/WorkforceHrWorkspace.tsx",
    """<BriefcaseBusiness size={14} /> Edit</button>""",
    """<BriefcaseBusiness size={14} /> {person.contract_id ? \"Edit\" : \"Create contract\"}</button>""",
)
replace_once(
    "frontend/src/pages/rostering/components/WorkforceHrWorkspace.tsx",
    """    {!people.length && !loading ? <EmptyState title=\"No matching employees\" description=\"Change the search or confirm effective employment contracts exist.\" /> : null}\n""",
    """    {!people.length && !loading ? <EmptyState title=\"No active tenant users found\" description=\"Change the search, or activate/create user accounts in tenant administration. Employment-contract gaps no longer hide users from this register.\" /> : null}\n""",
)
replace_once(
    "frontend/src/pages/rostering/components/WorkforceHrWorkspace.tsx",
    """<Save size={15} /> Save contract</button>""",
    """<Save size={15} /> {editing.contract_id ? \"Save contract\" : \"Create contract\"}</button>""",
)

# Regression contracts.
append_once(
    "backend/amodb/apps/workforce/tests/test_hr_review_flags.py",
    "def test_hr_people_register_starts_from_active_tenant_users",
    r'''

def test_hr_people_register_starts_from_active_tenant_users():
    source = inspect.getsource(hr_service._active_tenant_users)
    assert "User.is_active.is_(True)" in source
    assert "User.is_system_account.is_(False)" in source
    people_source = inspect.getsource(hr_service.list_people_page_v2)
    assert "_active_tenant_users" in people_source
    assert "_current_contracts_by_user" in people_source
    assert "contract=contracts.get" in people_source


def test_default_day_bootstrap_is_explicit_and_canonical():
    source = inspect.getsource(hr_service.bootstrap_default_day_pattern)
    assert 'code="DEFAULT-DAY"' in source
    assert 'code="DEFAULT-DAY-5X2"' in source
    assert "EmployeeWorkPatternAssignment" in source
    assert "with_for_update" in source
''',
)
append_once(
    "frontend/src/pages/rostering/rosteringSetupOverhaul.test.ts",
    "active tenant users remain visible",
    r'''

test("active tenant users remain visible when Workforce contracts are missing", () => {
  const source = readFileSync(resolve(__dirname, "components/WorkforceHrWorkspace.tsx"), "utf8");
  const service = readFileSync(resolve(__dirname, "../../services/workforceHr.ts"), "utf8");
  expect(source).toContain("Every active tenant user appears here");
  expect(source).toContain("Create contract");
  expect(source).toContain("createEmploymentContract");
  expect(source).toContain("Apply default day pattern");
  expect(service).toContain("/workforce/hr/default-day-pattern");
});
''',
)

print("Applied active-user Workforce register and default-day baseline correction.")
