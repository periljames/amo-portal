from pathlib import Path


workflow = Path(".github/workflows/pr364-final-integrity-pagination.yml").read_text(encoding="utf-8")
marker = "          python - <<'PY'\n"
start = workflow.index(marker) + len(marker)
end = workflow.index("\n          PY\n", start)
script = "\n".join(
    line[10:] if line.startswith("          ") else line
    for line in workflow[start:end].splitlines()
)

block_start = script.index("assignment_insert_anchor =")
block_end = script.index("hr = replace_once(", block_start)
replacement = '''create_start = hr.index("def create_overtime_request(")
create_end = hr.index("def decide_overtime(", create_start)
create_section = hr[create_start:create_end]
if "if payload.roster_assignment_id:" not in create_section:
    assignment_block = ''' + "'''" + '''    if payload.roster_assignment_id:
        _validated_roster_assignment(
            db,
            amo_id=amo_id,
            user_id=user_id,
            assignment_id=payload.roster_assignment_id,
            starts_at=payload.starts_at,
            ends_at=payload.ends_at,
        )
''' + "'''" + '''
    duplicate_anchor = "    duplicate = db.query(models.OvertimeRequest.id).filter("
    duplicate_position = hr.index(duplicate_anchor, create_start, create_end)
    hr = hr[:duplicate_position] + assignment_block + hr[duplicate_position:]
'''
script = script[:block_start] + replacement + script[block_end:]

pattern_block_start = script.index("old_query =", script.index("automation_path ="))
pattern_block_end = script.index("write(automation_path, automation)", pattern_block_start)
pattern_replacement = '''pattern_start = automation.index("def _pattern_assignments(")
pattern_end = automation.index("def _estimated_assignments(", pattern_start)
pattern_section = automation[pattern_start:pattern_end]
if "WorkPattern.is_active.is_(True)" not in pattern_section:
    query_anchor = "    return db.query(workforce_models.EmployeeWorkPatternAssignment).options("
    joined_query = ''' + "'''" + '''    return db.query(workforce_models.EmployeeWorkPatternAssignment).join(
        workforce_models.WorkPattern,
        workforce_models.EmployeeWorkPatternAssignment.work_pattern_id == workforce_models.WorkPattern.id,
    ).options(''' + "'''" + '''
    if query_anchor not in pattern_section:
        raise RuntimeError("Pattern readiness query start not found")
    pattern_section = pattern_section.replace(query_anchor, joined_query, 1)
    amo_anchor = "        workforce_models.EmployeeWorkPatternAssignment.amo_id == amo_id,\n"
    active_filter = ''' + "'''" + '''        workforce_models.EmployeeWorkPatternAssignment.amo_id == amo_id,
        workforce_models.WorkPattern.amo_id == amo_id,
        workforce_models.WorkPattern.is_active.is_(True),
''' + "'''" + '''
    if amo_anchor not in pattern_section:
        raise RuntimeError("Pattern readiness AMO filter not found")
    pattern_section = pattern_section.replace(amo_anchor, active_filter, 1)
    automation = automation[:pattern_start] + pattern_section + automation[pattern_end:]
'''
script = script[:pattern_block_start] + pattern_replacement + script[pattern_block_end:]
exec(compile(script, "/tmp/pr364_integrity_pagination.py", "exec"))
