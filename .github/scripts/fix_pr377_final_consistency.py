from __future__ import annotations

from pathlib import Path


def replace_once(path: str, old: str, new: str) -> None:
    target = Path(path)
    text = target.read_text(encoding="utf-8")
    if new in text:
        return
    if old not in text:
        raise RuntimeError(f"Expected block not found in {path}: {old[:240]!r}")
    target.write_text(text.replace(old, new, 1), encoding="utf-8")


service_path = "backend/amodb/apps/workforce/hr_service.py"

replace_once(
    service_path,
    """    without_contract = [user for user in users if str(user.id) not in contracts]\n    without_pattern = [\n""",
    """    without_effective_contract = [\n        user for user in users if str(user.id) not in current_contracts\n    ]\n    without_any_contract = [\n        user for user in users if str(user.id) not in contracts\n    ]\n    future_contract_users = [\n        user for user in without_effective_contract\n        if str(user.id) in contracts\n    ]\n    without_pattern = [\n""",
)
replace_once(
    service_path,
    """    response.employees_without_contract_count = len(without_contract)\n""",
    """    response.employees_without_contract_count = len(without_effective_contract)\n""",
)
replace_once(
    service_path,
    """        value=len(without_contract),\n        detail=\"Active users without an effective contract\",\n        tone=\"danger\" if without_contract else \"good\",\n""",
    """        value=len(without_effective_contract),\n        detail=\"Active users without a currently effective contract\",\n        tone=\"danger\" if without_effective_contract else \"good\",\n""",
)
replace_once(
    service_path,
    """        for user in without_contract[:50]\n    ]\n    response.action_queue = (missing_contract_actions + list(response.action_queue))[:100]\n""",
    """        for user in without_any_contract[:50]\n    ]\n    future_contract_actions = [\n        hr_schemas.HrActionItem(\n            id=f\"contract-future:{user.id}\",\n            category=\"CONTRACT\",\n            severity=\"WARNING\",\n            title=\"Employment contract not yet effective\",\n            detail=(\n                \"This active tenant user remains in the effective-contract gap until \"\n                f\"{contracts[str(user.id)].effective_from.isoformat()}.\"\n            ),\n            user_id=str(user.id),\n            user_name=_display_name(user),\n            action_label=\"Edit future contract\",\n            action_path=f\"people/{user.id}?section=contract\",\n        )\n        for user in future_contract_users[:50]\n    ]\n    response.action_queue = (\n        missing_contract_actions\n        + future_contract_actions\n        + list(response.action_queue)\n    )[:100]\n""",
)

replace_once(
    service_path,
    """        current = occupied.get(str(user.id))\n        if current is not None and current.work_pattern and current.work_pattern.is_active:\n            already_assigned += 1\n            continue\n\n        future = db.query(models.EmployeeWorkPatternAssignment).filter(\n""",
    """        current = occupied.get(str(user.id))\n        current_has_active_pattern = bool(\n            current and current.work_pattern and current.work_pattern.is_active\n        )\n        current_is_reserved_default = bool(\n            current_has_active_pattern\n            and current.work_pattern.code == \"DEFAULT-DAY-5X2\"\n        )\n        current_default_anchor_is_monday = bool(\n            current_is_reserved_default\n            and current.cycle_anchor_date\n            and current.cycle_anchor_date.weekday() == 0\n        )\n        if current_has_active_pattern and (\n            not current_is_reserved_default or current_default_anchor_is_monday\n        ):\n            already_assigned += 1\n            continue\n\n        future = db.query(models.EmployeeWorkPatternAssignment).filter(\n""",
)

replace_once(
    "backend/amodb/apps/workforce/tests/test_hr_review_flags.py",
    """def test_active_user_readiness_uses_tenant_local_date():\n    assert \"datetime.now(_amo_zone\" in inspect.getsource(hr_service.list_people_page_v2)\n    assert \"datetime.now(_amo_zone\" in inspect.getsource(hr_service.dashboard_v2)\n""",
    """def test_active_user_readiness_uses_tenant_local_date():\n    assert \"datetime.now(_amo_zone\" in inspect.getsource(hr_service.list_people_page_v2)\n    assert \"datetime.now(_amo_zone\" in inspect.getsource(hr_service.dashboard_v2)\n\n\ndef test_effective_contract_gap_retains_future_starters():\n    source = inspect.getsource(hr_service.dashboard_v2)\n    assert \"without_effective_contract\" in source\n    assert \"not in current_contracts\" in source\n    assert \"future_contract_users\" in source\n    assert \"Edit future contract\" in source\n    assert \"len(without_effective_contract)\" in source\n\n\ndef test_default_day_bootstrap_repairs_non_monday_reserved_anchor():\n    source = inspect.getsource(hr_service.bootstrap_default_day_pattern)\n    assert 'current.work_pattern.code == \"DEFAULT-DAY-5X2\"' in source\n    assert \"current.cycle_anchor_date.weekday() == 0\" in source\n    assert \"not current_is_reserved_default or current_default_anchor_is_monday\" in source\n    assert \"cycle_anchor_date=week_monday\" in source\n""",
)

# Update the permanent implementation record.
doc_path = "backend/docs/rostering/WORKFORCE_ACTIVE_USER_READINESS_20260729.md"
doc = Path(doc_path).read_text(encoding="utf-8")
doc = doc.replace(
    "The blocker reviews identified and corrected three effective-dating defects:\n",
    "The blocker reviews identified and corrected five readiness and effective-dating defects:\n",
)
doc = doc.replace(
    "- future contracts are surfaced and edited instead of misclassified as missing contracts that invite an overlapping creation.\n",
    "- future contracts are surfaced and edited instead of misclassified as missing contracts that invite an overlapping creation;\n"
    "- future starters remain included in the currently effective-contract gap metric and receive an edit-future-contract action; and\n"
    "- existing reserved default-day assignments with non-Monday anchors are safely re-effective-dated to the canonical Monday anchor.\n",
)
Path(doc_path).write_text(doc, encoding="utf-8")

print("Applied final PR377 metric and reserved-anchor consistency corrections.")
