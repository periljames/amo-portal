from pathlib import Path


def replace_once(path: str, old: str, new: str) -> None:
    target = Path(path)
    text = target.read_text(encoding="utf-8")
    if new in text:
        return
    if old not in text:
        raise RuntimeError(f"Expected text not found in {path}: {old!r}")
    target.write_text(text.replace(old, new, 1), encoding="utf-8")


replace_once(
    "backend/amodb/apps/workforce/hr_schemas.py",
    "    can_initialize_default_day_pattern: bool\n",
    "    can_initialize_default_day_pattern: bool = False\n",
)
replace_once(
    "backend/amodb/apps/workforce/hr_schemas.py",
    "    employees_without_contract_count: int\n",
    "    employees_without_contract_count: int = 0\n",
)
replace_once(
    "frontend/src/pages/rostering/components/WorkforceHrWorkspace.tsx",
    "        await updateEmploymentContract(editing.contract_id, payload);\n",
    "        await updateEmploymentContract(editing.contract_id, { ...payload, user_id: undefined });\n",
)

# Move the source-contract assertion inside the existing Vitest describe block.
test_path = Path("frontend/src/pages/rostering/rosteringSetupOverhaul.test.ts")
text = test_path.read_text(encoding="utf-8")
bad_marker = '\n\ntest("active tenant users remain visible when Workforce contracts are missing", () => {'
if bad_marker in text:
    text = text[: text.index(bad_marker)].rstrip() + "\n"
assertion = '''

  it("keeps active tenant users visible when Workforce records are incomplete", () => {
    expect(hrSource).toContain("Every active tenant user appears here");
    expect(hrSource).toContain("Create contract");
    expect(hrSource).toContain("createEmploymentContract");
    expect(hrSource).toContain("Apply default day pattern");
    const workforceHrService = readSource("../../services/workforceHr.ts");
    expect(workforceHrService).toContain("/workforce/hr/default-day-pattern");
  });
'''
if "keeps active tenant users visible when Workforce records are incomplete" not in text:
    closing = text.rfind("});")
    if closing < 0:
        raise RuntimeError("Could not find final describe closure")
    text = text[:closing] + assertion + text[closing:]
test_path.write_text(text, encoding="utf-8")

print("Applied Workforce correction follow-up hardening.")
