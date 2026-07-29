from __future__ import annotations

from pathlib import Path


def replace_once(path: str, old: str, new: str) -> None:
    target = Path(path)
    text = target.read_text(encoding="utf-8")
    if new in text:
        return
    if old not in text:
        raise RuntimeError(f"Expected block not found in {path}: {old[:200]!r}")
    target.write_text(text.replace(old, new, 1), encoding="utf-8")


service_path = "backend/amodb/apps/workforce/hr_service.py"

replace_once(
    service_path,
    """    timezone_name = str(amo.time_zone or \"UTC\")\n    today = datetime.now(_amo_zone(db, amo_id=amo_id)).date()\n\n    shift = db.query(roster_models.ShiftTemplate).filter(\n""",
    """    timezone_name = str(amo.time_zone or \"UTC\")\n    today = datetime.now(_amo_zone(db, amo_id=amo_id)).date()\n    week_monday = today - timedelta(days=today.weekday())\n\n    shift = db.query(roster_models.ShiftTemplate).filter(\n""",
)

old_loop = """    assigned = 0\n    already_assigned = 0\n    skipped_conflict = 0\n    for user in eligible_users:\n        current = occupied.get(str(user.id))\n        if current is not None:\n            if current.work_pattern and current.work_pattern.is_active:\n                already_assigned += 1\n            else:\n                current.work_pattern_id = pattern.id\n                current.cycle_anchor_date = today\n                db.add(current)\n                assigned += 1\n            continue\n        future = db.query(models.EmployeeWorkPatternAssignment).filter(\n            models.EmployeeWorkPatternAssignment.amo_id == amo_id,\n            models.EmployeeWorkPatternAssignment.user_id == user.id,\n            models.EmployeeWorkPatternAssignment.effective_from > today,\n        ).order_by(models.EmployeeWorkPatternAssignment.effective_from.asc()).first()\n        effective_to = future.effective_from - timedelta(days=1) if future else None\n        if effective_to is not None and effective_to < today:\n            skipped_conflict += 1\n            continue\n        db.add(models.EmployeeWorkPatternAssignment(\n            amo_id=amo_id,\n            user_id=user.id,\n            work_pattern_id=pattern.id,\n            effective_from=today,\n            effective_to=effective_to,\n            cycle_anchor_date=today,\n            created_by_user_id=actor_user_id,\n        ))\n        assigned += 1\n"""
new_loop = """    assigned = 0\n    already_assigned = 0\n    skipped_conflict = 0\n    for user in eligible_users:\n        current = occupied.get(str(user.id))\n        if current is not None and current.work_pattern and current.work_pattern.is_active:\n            already_assigned += 1\n            continue\n\n        future = db.query(models.EmployeeWorkPatternAssignment).filter(\n            models.EmployeeWorkPatternAssignment.amo_id == amo_id,\n            models.EmployeeWorkPatternAssignment.user_id == user.id,\n            models.EmployeeWorkPatternAssignment.effective_from > today,\n        ).order_by(models.EmployeeWorkPatternAssignment.effective_from.asc()).first()\n        effective_to = future.effective_from - timedelta(days=1) if future else None\n        if effective_to is not None and effective_to < today:\n            skipped_conflict += 1\n            continue\n\n        if current is not None:\n            # Never rewrite an historical pattern assignment in place. Close the\n            # prior interval before the tenant-local work date and create a new\n            # default assignment. A same-day invalid row has no historical span,\n            # so remove it before inserting the canonical replacement.\n            if current.effective_from < today:\n                current.effective_to = today - timedelta(days=1)\n                db.add(current)\n            else:\n                db.delete(current)\n                db.flush()\n\n        db.add(models.EmployeeWorkPatternAssignment(\n            amo_id=amo_id,\n            user_id=user.id,\n            work_pattern_id=pattern.id,\n            effective_from=today,\n            effective_to=effective_to,\n            cycle_anchor_date=week_monday,\n            created_by_user_id=actor_user_id,\n        ))\n        assigned += 1\n"""
replace_once(service_path, old_loop, new_loop)

replace_once(
    "backend/amodb/apps/workforce/tests/test_hr_review_flags.py",
    """    assert \"days_by_index\" in source\n    assert \"range(7)\" in source\n    assert \"current.work_pattern_id = pattern.id\" in source\n""",
    """    assert \"days_by_index\" in source\n    assert \"range(7)\" in source\n    assert \"week_monday = today - timedelta(days=today.weekday())\" in source\n    assert \"cycle_anchor_date=week_monday\" in source\n    assert \"current.effective_to = today - timedelta(days=1)\" in source\n    assert \"db.delete(current)\" in source\n    assert \"current.work_pattern_id = pattern.id\" not in source\n""",
)

# Keep the implementation record explicit about the two corrected invariants.
doc_path = "backend/docs/rostering/WORKFORCE_ACTIVE_USER_READINESS_20260729.md"
doc = Path(doc_path).read_text(encoding="utf-8")
anchor = "8. All effective-date decisions use the tenant timezone.\n9. The default baseline creates draft roster input only."
replacement = (
    "8. All effective-date decisions use the tenant timezone.\n"
    "9. Replacing an inactive current pattern closes the historical assignment and creates a new row effective on the tenant-local current date; historical records are never rewritten.\n"
    "10. The `DEFAULT-DAY-5X2` cycle is anchored to the tenant-local week's Monday, regardless of the day the bootstrap is run.\n"
    "11. The default baseline creates draft roster input only."
)
if replacement not in doc:
    if anchor not in doc:
        raise RuntimeError("Documentation insertion point not found")
    Path(doc_path).write_text(doc.replace(anchor, replacement, 1), encoding="utf-8")

print("Applied PR377 effective-dated replacement and Monday-cycle corrections.")
