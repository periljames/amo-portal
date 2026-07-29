from __future__ import annotations

from pathlib import Path


def replace_once(path: str, old: str, new: str) -> None:
    target = Path(path)
    text = target.read_text(encoding="utf-8")
    if new in text:
        return
    if old not in text:
        raise RuntimeError(f"Expected block not found in {path}: {old[:220]!r}")
    target.write_text(text.replace(old, new, 1), encoding="utf-8")


service_path = "backend/amodb/apps/workforce/hr_service.py"

replace_once(
    service_path,
    """def _person_readiness_for_user(\n    user: account_models.User,\n    *,\n    contract: Optional[models.EmploymentContract],\n    pattern: Optional[models.EmployeeWorkPatternAssignment],\n    leave: Optional[models.LeaveRequest],\n) -> hr_schemas.HrPersonReadiness:\n    reasons: list[str] = []\n    status_value = _value(contract.employment_status) if contract else None\n    if contract is None:\n        reasons.append(\"No effective employment contract exists.\")\n    else:\n        if status_value != models.EmploymentStatus.ACTIVE.value:\n            reasons.append(f\"Employment status is {status_value.replace('_', ' ').lower()}.\")\n        if not contract.primary_base_station_id:\n            reasons.append(\"No primary base is assigned.\")\n""",
    """def _readiness_contracts_by_user(\n    db: Session,\n    *,\n    amo_id: str,\n    user_ids: list[str],\n    on_date: date,\n) -> dict[str, models.EmploymentContract]:\n    \"\"\"Return the effective contract or, when absent, the next future contract.\"\"\"\n    result = _current_contracts_by_user(db, amo_id=amo_id, on_date=on_date)\n    missing_user_ids = [user_id for user_id in user_ids if user_id not in result]\n    if not missing_user_ids:\n        return result\n    future_rows = db.query(models.EmploymentContract).options(\n        joinedload(models.EmploymentContract.user),\n        joinedload(models.EmploymentContract.supervisor),\n        joinedload(models.EmploymentContract.primary_base),\n    ).filter(\n        models.EmploymentContract.amo_id == amo_id,\n        models.EmploymentContract.user_id.in_(missing_user_ids),\n        models.EmploymentContract.employment_status.in_([\n            models.EmploymentStatus.ACTIVE,\n            models.EmploymentStatus.ONBOARDING,\n        ]),\n        models.EmploymentContract.effective_from > on_date,\n    ).order_by(\n        models.EmploymentContract.user_id.asc(),\n        models.EmploymentContract.effective_from.asc(),\n        models.EmploymentContract.id.asc(),\n    ).all()\n    for row in future_rows:\n        result.setdefault(str(row.user_id), row)\n    return result\n\n\ndef _person_readiness_for_user(\n    user: account_models.User,\n    *,\n    contract: Optional[models.EmploymentContract],\n    pattern: Optional[models.EmployeeWorkPatternAssignment],\n    leave: Optional[models.LeaveRequest],\n    on_date: date,\n) -> hr_schemas.HrPersonReadiness:\n    reasons: list[str] = []\n    status_value = _value(contract.employment_status) if contract else None\n    contract_is_effective = bool(\n        contract\n        and contract.effective_from <= on_date\n        and (contract.effective_to is None or contract.effective_to >= on_date)\n    )\n    if contract is None:\n        reasons.append(\"No effective or future employment contract exists.\")\n    elif not contract_is_effective:\n        reasons.append(f\"Employment contract starts on {contract.effective_from.isoformat()}.\")\n        if not contract.primary_base_station_id:\n            reasons.append(\"The future contract has no primary base assigned.\")\n    else:\n        if status_value != models.EmploymentStatus.ACTIVE.value:\n            reasons.append(f\"Employment status is {status_value.replace('_', ' ').lower()}.\")\n        if not contract.primary_base_station_id:\n            reasons.append(\"No primary base is assigned.\")\n""",
)

replace_once(
    service_path,
    """        has_effective_contract=contract is not None,\n""",
    """        has_effective_contract=contract_is_effective,\n""",
)

replace_once(
    service_path,
    """    contracts = _current_contracts_by_user(db, amo_id=amo_id, on_date=today)\n    patterns = _effective_patterns(db, amo_id=amo_id, user_ids=user_ids, on_date=today)\n""",
    """    contracts = _readiness_contracts_by_user(\n        db, amo_id=amo_id, user_ids=user_ids, on_date=today\n    )\n    patterns = _effective_patterns(db, amo_id=amo_id, user_ids=user_ids, on_date=today)\n""",
)

# Both readiness call sites need the tenant-local work date.
service = Path(service_path).read_text(encoding="utf-8")
old_call = """            pattern=patterns.get(str(user.id)),\n            leave=leave_by_user.get(str(user.id)),\n        )\n"""
new_call = """            pattern=patterns.get(str(user.id)),\n            leave=leave_by_user.get(str(user.id)),\n            on_date=today,\n        )\n"""
count = service.count(old_call)
if count != 2:
    raise RuntimeError(f"Expected two readiness call sites, found {count}")
service = service.replace(old_call, new_call)
Path(service_path).write_text(service, encoding="utf-8")

# Dashboard separates current contracts (for current-status metrics) from the
# readiness contract view that may include the next future contract.
replace_once(
    service_path,
    """    contracts = _current_contracts_by_user(db, amo_id=amo_id, on_date=today)\n    patterns = _effective_patterns(db, amo_id=amo_id, user_ids=user_ids, on_date=today)\n    leave_by_user = _active_leave(db, amo_id=amo_id, user_ids=user_ids, now=now)\n    people = [\n""",
    """    current_contracts = _current_contracts_by_user(db, amo_id=amo_id, on_date=today)\n    contracts = _readiness_contracts_by_user(\n        db, amo_id=amo_id, user_ids=user_ids, on_date=today\n    )\n    patterns = _effective_patterns(db, amo_id=amo_id, user_ids=user_ids, on_date=today)\n    leave_by_user = _active_leave(db, amo_id=amo_id, user_ids=user_ids, now=now)\n    people = [\n""",
)
replace_once(
    service_path,
    """    response.onboarding_employee_count = sum(\n        1 for contract in contracts.values()\n        if _value(contract.employment_status) == models.EmploymentStatus.ONBOARDING.value\n    )\n    response.suspended_employee_count = sum(\n        1 for contract in contracts.values()\n        if _value(contract.employment_status) == models.EmploymentStatus.SUSPENDED.value\n    )\n""",
    """    response.onboarding_employee_count = sum(\n        1 for contract in current_contracts.values()\n        if _value(contract.employment_status) == models.EmploymentStatus.ONBOARDING.value\n    )\n    response.suspended_employee_count = sum(\n        1 for contract in current_contracts.values()\n        if _value(contract.employment_status) == models.EmploymentStatus.SUSPENDED.value\n    )\n""",
)

# The editor should preserve a surfaced future contract's configured status.
replace_once(
    "frontend/src/pages/rostering/components/WorkforceHrWorkspace.tsx",
    """      employment_status: (person.has_effective_contract ? person.employment_status : \"ACTIVE\") as EmploymentStatus,\n""",
    """      employment_status: (person.contract_id ? person.employment_status : \"ACTIVE\") as EmploymentStatus,\n""",
)

# Backend source contracts cover future lookup and non-creation behavior.
replace_once(
    "backend/amodb/apps/workforce/tests/test_hr_review_flags.py",
    """    assert \"_current_contracts_by_user\" in people_source\n    assert \"contract=contracts.get\" in people_source\n""",
    """    assert \"_readiness_contracts_by_user\" in people_source\n    assert \"contract=contracts.get\" in people_source\n\n\ndef test_hr_readiness_surfaces_the_next_future_contract():\n    lookup_source = inspect.getsource(hr_service._readiness_contracts_by_user)\n    readiness_source = inspect.getsource(hr_service._person_readiness_for_user)\n    assert \"effective_from > on_date\" in lookup_source\n    assert \"effective_from.asc()\" in lookup_source\n    assert \"result.setdefault\" in lookup_source\n    assert \"Employment contract starts on\" in readiness_source\n    assert \"has_effective_contract=contract_is_effective\" in readiness_source\n""",
)

# Render one future-contract employee beside the genuinely contractless user.
e2e_path = "frontend/tests/e2e/rostering-role-access.spec.ts"
replace_once(
    e2e_path,
    """const activeUserWithoutContract = {\n""",
    """const activeUserWithFutureContract = {\n  user_id: \"active-user-future-contract\",\n  contract_id: \"future-contract-001\",\n  staff_code: \"TECH-002\",\n  full_name: \"Future Starter\",\n  email: \"future.starter@example.test\",\n  has_effective_contract: false,\n  uses_default_day_pattern: false,\n  position_title: \"Aircraft Technician\",\n  department_code: \"maintenance\",\n  employment_status: \"ONBOARDING\",\n  contract_type: \"FIXED_TERM\",\n  contract_effective_from: \"2026-08-15\",\n  contract_effective_to: \"2027-08-14\",\n  primary_base_station_id: \"base-nbo\",\n  primary_base_code: \"NBO\",\n  supervisor_name: null,\n  standard_weekly_minutes: 2400,\n  standard_daily_minutes: 480,\n  fte_percentage: 100,\n  cost_centre: null,\n  payroll_number: null,\n  overtime_eligible: true,\n  night_shift_eligible: true,\n  standby_eligible: true,\n  work_pattern_code: null,\n  work_pattern_name: null,\n  work_pattern_effective_from: null,\n  active_leave_status: null,\n  readiness_state: \"NEEDS_ATTENTION\",\n  readiness_reasons: [\n    \"Employment contract starts on 2026-08-15.\",\n    \"No active work pattern is assigned.\",\n  ],\n};\n\nconst activeUserWithoutContract = {\n""",
)
replace_once(
    e2e_path,
    """      await fulfilJson(route, { items: [activeUserWithoutContract], page: 1, page_size: 100, total: 1, pages: 1 });\n""",
    """      await fulfilJson(route, {\n        items: [activeUserWithoutContract, activeUserWithFutureContract],\n        page: 1,\n        page_size: 100,\n        total: 2,\n        pages: 1,\n      });\n""",
)
replace_once(
    e2e_path,
    """  await expect(page.getByRole(\"button\", { name: \"Apply default day pattern\" })).toBeVisible();\n});\n""",
    """  await expect(page.getByRole(\"button\", { name: \"Apply default day pattern\" })).toBeVisible();\n\n  const futureEmployee = page.getByText(\"Future Starter\", { exact: true }).locator(\"xpath=ancestor::article\");\n  await expect(futureEmployee).toContainText(\"ONBOARDING\");\n  await expect(futureEmployee).toContainText(\"starts on 2026-08-15\");\n  await expect(futureEmployee.getByRole(\"button\", { name: \"Edit\" })).toBeVisible();\n  await expect(futureEmployee.getByRole(\"button\", { name: \"Create contract\" })).toHaveCount(0);\n});\n""",
)

# Permanent implementation record.
doc_path = "backend/docs/rostering/WORKFORCE_ACTIVE_USER_READINESS_20260729.md"
doc = Path(doc_path).read_text(encoding="utf-8")
anchor = "3. Missing Workforce records remain visible as actionable readiness blockers; they never remove the user from the register.\n"
addition = (
    anchor
    + "4. When no contract is currently effective, the next future ACTIVE or ONBOARDING contract is surfaced for editing rather than offering an overlapping contract creation.\n"
)
if addition not in doc:
    if anchor not in doc:
        raise RuntimeError("Documentation anchor not found")
    doc = doc.replace(anchor, addition, 1)
    # Renumber the remaining canonical behavior items.
    for old, new in reversed([(str(i), str(i + 1)) for i in range(4, 12)]):
        doc = doc.replace(f"{old}. ", f"{new}. ", 1)
    Path(doc_path).write_text(doc, encoding="utf-8")

print("Applied PR377 future-contract readiness correction.")
