from __future__ import annotations

from pathlib import Path


def replace_once(path: str, old: str, new: str) -> None:
    target = Path(path)
    text = target.read_text(encoding="utf-8")
    if new in text:
        return
    if old not in text:
        raise RuntimeError(f"Expected block not found in {path}: {old[:160]!r}")
    target.write_text(text.replace(old, new, 1), encoding="utf-8")


def insert_before(path: str, marker: str, block: str, unique: str) -> None:
    target = Path(path)
    text = target.read_text(encoding="utf-8")
    if unique in text:
        return
    index = text.find(marker)
    if index < 0:
        raise RuntimeError(f"Marker not found in {path}: {marker!r}")
    target.write_text(text[:index] + block + text[index:], encoding="utf-8")


# Tenant-local effective dates.
service_path = "backend/amodb/apps/workforce/hr_service.py"
service = Path(service_path).read_text(encoding="utf-8")
for function_name in ("list_people_page_v2", "dashboard_v2"):
    marker = f"def {function_name}("
    start = service.find(marker)
    if start < 0:
        raise RuntimeError(f"{function_name} not found")
    end = service.find("\ndef ", start + len(marker))
    if end < 0:
        end = len(service)
    block = service[start:end]
    block = block.replace(
        "    today = date.today()\n",
        "    today = datetime.now(_amo_zone(db, amo_id=amo_id)).date()\n",
        1,
    )
    service = service[:start] + block + service[end:]

start = service.find("def bootstrap_default_day_pattern(")
if start < 0:
    raise RuntimeError("bootstrap_default_day_pattern not found")
end = len(service)
block = service[start:end]
block = block.replace(
    '    today = date.today()\n    timezone_name = str(amo.time_zone or "UTC")\n',
    '    timezone_name = str(amo.time_zone or "UTC")\n    today = datetime.now(_amo_zone(db, amo_id=amo_id)).date()\n',
    1,
)
service = service[:start] + block
Path(service_path).write_text(service, encoding="utf-8")

# Treat inactive current assignments as gaps in the dashboard.
replace_once(
    service_path,
    """    without_pattern = [user for user in users if str(user.id) not in patterns]\n""",
    """    without_pattern = [\n        user for user in users\n        if not (assignment := patterns.get(str(user.id)))\n        or not assignment.work_pattern\n        or not assignment.work_pattern.is_active\n    ]\n""",
)

# Normalize the reserved default shift and guarantee all seven pattern days.
replace_once(
    service_path,
    """    elif not shift.is_active:\n        shift.is_active = True\n        shift.updated_by_user_id = actor_user_id\n        db.add(shift)\n\n    pattern = db.query(models.WorkPattern).options(\n""",
    """    else:\n        shift.label = \"Default day shift\"\n        shift.kind = roster_models.ShiftTemplateKind.DAY\n        shift.default_start_time = \"08:00\"\n        shift.default_end_time = \"17:00\"\n        shift.duration_minutes = 480\n        shift.counts_as_duty = True\n        shift.is_active = True\n        shift.display_order = 10\n        shift.description = \"System baseline for active staff without an assigned work pattern; planner review remains required.\"\n        shift.icon_name = \"Sun\"\n        shift.updated_by_user_id = actor_user_id\n        db.add(shift)\n\n    pattern = db.query(models.WorkPattern).options(\n""",
)
replace_once(
    service_path,
    """        db.add(pattern)\n        db.flush()\n        for day_index in range(7):\n            duty = day_index < 5\n            db.add(models.WorkPatternDay(\n                amo_id=amo_id,\n                work_pattern_id=pattern.id,\n                cycle_day_index=day_index,\n                shift_template_id=shift.id if duty else None,\n                status=models.PatternDayStatus.DUTY if duty else models.PatternDayStatus.OFF,\n                start_time_local=\"08:00\" if duty else None,\n                end_time_local=\"17:00\" if duty else None,\n                spans_next_day=False,\n                planned_minutes=480 if duty else 0,\n            ))\n    else:\n        if not pattern.is_active:\n            pattern.is_active = True\n        pattern.updated_by_user_id = actor_user_id\n        db.add(pattern)\n\n    users = _active_tenant_users(db, amo_id=amo_id)\n""",
    """        db.add(pattern)\n        db.flush()\n    else:\n        pattern.name = \"Default day shift · Monday to Friday\"\n        pattern.description = \"Five default day duties followed by two days off. This is a visible baseline, not a published roster.\"\n        pattern.cycle_length_days = 7\n        pattern.is_active = True\n        pattern.timezone_name = timezone_name\n        pattern.updated_by_user_id = actor_user_id\n        db.add(pattern)\n        db.flush()\n\n    days_by_index = {int(row.cycle_day_index): row for row in (pattern.days or [])}\n    for day_index in range(7):\n        duty = day_index < 5\n        day = days_by_index.get(day_index)\n        if day is None:\n            day = models.WorkPatternDay(\n                amo_id=amo_id,\n                work_pattern_id=pattern.id,\n                cycle_day_index=day_index,\n            )\n        day.shift_template_id = shift.id if duty else None\n        day.status = models.PatternDayStatus.DUTY if duty else models.PatternDayStatus.OFF\n        day.start_time_local = \"08:00\" if duty else None\n        day.end_time_local = \"17:00\" if duty else None\n        day.spans_next_day = False\n        day.planned_minutes = 480 if duty else 0\n        db.add(day)\n\n    users = _active_tenant_users(db, amo_id=amo_id)\n""",
)

# Explicit bootstrap should repair an inactive current pattern assignment rather than leave the user stuck.
replace_once(
    service_path,
    """        if current is not None:\n            if current.work_pattern and current.work_pattern.is_active:\n                already_assigned += 1\n            else:\n                skipped_conflict += 1\n            continue\n""",
    """        if current is not None:\n            if current.work_pattern and current.work_pattern.is_active:\n                already_assigned += 1\n            else:\n                current.work_pattern_id = pattern.id\n                current.cycle_anchor_date = today\n                db.add(current)\n                assigned += 1\n            continue\n""",
)

# Match backend enums exactly now that the page can create contracts.
replace_once(
    "frontend/src/types/workforce.ts",
    'export type ContractType = "PERMANENT" | "FIXED_TERM" | "CASUAL" | "CONTRACTOR" | "INTERN" | "SECONDMENT";\nexport type EmploymentStatus = "ONBOARDING" | "ACTIVE" | "SUSPENDED" | "TERMINATED" | "ENDED";\n',
    'export type ContractType = "PERMANENT" | "FIXED_TERM" | "TEMPORARY" | "CONTRACTOR" | "INTERN";\nexport type EmploymentStatus = "ONBOARDING" | "ACTIVE" | "SUSPENDED" | "TERMINATED";\n',
)
replace_once(
    "frontend/src/pages/rostering/components/WorkforceHrWorkspace.tsx",
    '["PERMANENT", "FIXED_TERM", "CASUAL", "CONTRACTOR", "INTERN", "SECONDMENT"]',
    '["PERMANENT", "FIXED_TERM", "TEMPORARY", "CONTRACTOR", "INTERN"]',
)
replace_once(
    "frontend/src/pages/rostering/components/WorkforceHrWorkspace.tsx",
    '["ONBOARDING", "ACTIVE", "SUSPENDED", "TERMINATED", "ENDED"]',
    '["ONBOARDING", "ACTIVE", "SUSPENDED", "TERMINATED"]',
)

# Backend source regressions for tenant-local dates and baseline repair.
replace_once(
    "backend/amodb/apps/workforce/tests/test_hr_review_flags.py",
    """def test_default_day_bootstrap_is_explicit_and_canonical():\n    source = inspect.getsource(hr_service.bootstrap_default_day_pattern)\n    assert 'code=\"DEFAULT-DAY\"' in source\n    assert 'code=\"DEFAULT-DAY-5X2\"' in source\n    assert \"EmployeeWorkPatternAssignment\" in source\n    assert \"with_for_update\" in source\n""",
    """def test_default_day_bootstrap_is_explicit_and_canonical():\n    source = inspect.getsource(hr_service.bootstrap_default_day_pattern)\n    assert 'code=\"DEFAULT-DAY\"' in source\n    assert 'code=\"DEFAULT-DAY-5X2\"' in source\n    assert \"EmployeeWorkPatternAssignment\" in source\n    assert \"with_for_update\" in source\n    assert \"datetime.now(_amo_zone\" in source\n    assert \"days_by_index\" in source\n    assert \"range(7)\" in source\n    assert \"current.work_pattern_id = pattern.id\" in source\n\n\ndef test_active_user_readiness_uses_tenant_local_date():\n    assert \"datetime.now(_amo_zone\" in inspect.getsource(hr_service.list_people_page_v2)\n    assert \"datetime.now(_amo_zone\" in inspect.getsource(hr_service.dashboard_v2)\n""",
)

# Browser fixture now includes one active user with no contract.
e2e_path = "frontend/tests/e2e/rostering-role-access.spec.ts"
replace_once(
    e2e_path,
    """    can_manage_contracts: permissions.includes(\"workforce.manage_contracts\"),\n    can_manage_leave_balances: permissions.includes(\"leave.manage_balances\"),\n""",
    """    can_manage_contracts: permissions.includes(\"workforce.manage_contracts\"),\n    can_initialize_default_day_pattern: [\n      \"workforce.manage_contracts\",\n      \"roster.manage_shift_templates\",\n      \"roster.manage_patterns\",\n    ].every((permission) => permissions.includes(permission)),\n    can_manage_leave_balances: permissions.includes(\"leave.manage_balances\"),\n""",
)
replace_once(
    e2e_path,
    """    active_employee_count: 0,\n    onboarding_employee_count: 0,\n""",
    """    active_employee_count: 1,\n    employees_without_contract_count: 1,\n    onboarding_employee_count: 0,\n""",
)
insert_before(
    e2e_path,
    "async function fulfilJson",
    """const activeUserWithoutContract = {\n  user_id: \"active-user-without-contract\",\n  contract_id: null,\n  staff_code: \"TECH-001\",\n  full_name: \"Active Technician\",\n  email: \"active.technician@example.test\",\n  has_effective_contract: false,\n  uses_default_day_pattern: false,\n  position_title: \"Aircraft Technician\",\n  department_code: \"maintenance\",\n  employment_status: null,\n  contract_type: null,\n  contract_effective_from: null,\n  contract_effective_to: null,\n  primary_base_station_id: null,\n  primary_base_code: null,\n  supervisor_name: null,\n  standard_weekly_minutes: 2400,\n  standard_daily_minutes: 480,\n  fte_percentage: 100,\n  cost_centre: null,\n  payroll_number: null,\n  overtime_eligible: true,\n  night_shift_eligible: true,\n  standby_eligible: true,\n  work_pattern_code: null,\n  work_pattern_name: null,\n  work_pattern_effective_from: null,\n  active_leave_status: null,\n  readiness_state: \"NEEDS_ATTENTION\",\n  readiness_reasons: [\n    \"No effective employment contract exists.\",\n    \"No active work pattern is assigned.\",\n  ],\n};\n\n""",
    "activeUserWithoutContract",
)
replace_once(
    e2e_path,
    """    if (path.endsWith(\"/workforce/hr/dashboard\")) {\n      await fulfilJson(route, hrDashboardResponse(roleCase.permissions));\n      return;\n    }\n""",
    """    if (path.endsWith(\"/workforce/hr/dashboard\")) {\n      await fulfilJson(route, hrDashboardResponse(roleCase.permissions));\n      return;\n    }\n    if (path.endsWith(\"/workforce/hr/people\")) {\n      await fulfilJson(route, { items: [activeUserWithoutContract], page: 1, page_size: 100, total: 1, pages: 1 });\n      return;\n    }\n    if (path.endsWith(\"/foundations/base-stations\")) {\n      await fulfilJson(route, [{ id: \"base-nbo\", code: \"NBO\", name: \"Nairobi\", is_active: true }]);\n      return;\n    }\n""",
)
insert_before(
    e2e_path,
    'test("AMO Admin can open guided Setup',
    """test(\"active users without contracts remain visible and actionable in Workforce\", async ({ page }) => {\n  const admin = cases.find((item) => item.name === \"AMO Admin\")!;\n  await installAuthenticatedSession(page, admin);\n  await page.goto(`${ROSTER_ROOT}/settings?section=workforce`);\n  await page.getByRole(\"button\", { name: \"People & contracts\" }).click();\n\n  await expect(page.getByText(\"Active Technician\", { exact: true })).toBeVisible();\n  await expect(page.getByText(\"No contract\", { exact: true })).toBeVisible();\n  await expect(page.getByRole(\"button\", { name: \"Create contract\" })).toBeVisible();\n  await expect(page.getByRole(\"button\", { name: \"Apply default day pattern\" })).toBeVisible();\n});\n\n""",
    "active users without contracts remain visible and actionable",
)

# Frontend source contract checks exact backend enum values.
replace_once(
    "frontend/src/pages/rostering/rosteringSetupOverhaul.test.ts",
    """    expect(workforceHrService).toContain(\"/workforce/hr/default-day-pattern\");\n  });\n""",
    """    expect(workforceHrService).toContain(\"/workforce/hr/default-day-pattern\");\n    const workforceTypes = readSource(\"../../types/workforce.ts\");\n    expect(workforceTypes).toContain('\\\"TEMPORARY\\\"');\n    expect(workforceTypes).not.toContain('\\\"CASUAL\\\"');\n    expect(workforceTypes).not.toContain('\\\"SECONDMENT\\\"');\n    expect(workforceTypes).not.toContain('\\\"ENDED\\\"');\n  });\n""",
)

print("Applied PR377 follow-up corrections.")
