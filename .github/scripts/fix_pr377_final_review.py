from __future__ import annotations

from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]


def replace_once(path: str, old: str, new: str) -> None:
    target = ROOT / path
    text = target.read_text(encoding="utf-8")
    if old not in text:
        raise RuntimeError(f"Expected patch anchor missing in {path}: {old[:180]!r}")
    target.write_text(text.replace(old, new, 1), encoding="utf-8")


service = "backend/amodb/apps/workforce/hr_service.py"
replace_once(
    service,
    "def _person_readiness_for_user(\n    user: account_models.User,\n    *,\n    contract: Optional[models.EmploymentContract],\n",
    "def _person_readiness_for_user(\n    user: account_models.User,\n    *,\n    amo_id: str,\n    contract: Optional[models.EmploymentContract],\n",
)
replace_once(
    service,
    "    else:\n        state = \"READY\"\n\n    return hr_schemas.HrPersonReadiness(\n",
    "    else:\n        state = \"READY\"\n\n    managed_default_pattern_id = _default_day_system_id(\n        amo_id=amo_id,\n        system_key=_DEFAULT_DAY_PATTERN_KEY,\n    )\n\n    return hr_schemas.HrPersonReadiness(\n",
)
replace_once(
    service,
    "        uses_default_day_pattern=bool(work_pattern and work_pattern.code == \"DEFAULT-DAY-5X2\"),\n",
    "        uses_default_day_pattern=bool(\n            pattern and str(pattern.work_pattern_id) == managed_default_pattern_id\n        ),\n",
)
# Both public assemblers are tenant-scoped and must pass that identity explicitly.
service_path = ROOT / service
text = service_path.read_text(encoding="utf-8")
call_anchor = "        _person_readiness_for_user(\n            user,\n            contract=contracts.get(str(user.id)),\n"
if text.count(call_anchor) != 2:
    raise RuntimeError(f"Expected two readiness assembler calls, found {text.count(call_anchor)}")
text = text.replace(
    call_anchor,
    "        _person_readiness_for_user(\n            user,\n            amo_id=amo_id,\n            contract=contracts.get(str(user.id)),\n",
)
service_path.write_text(text, encoding="utf-8")

replace_once(
    service,
    "        \"description\": row.description,\n        \"icon_name\": row.icon_name,\n    }\n",
    "        \"description\": row.description,\n        \"icon_name\": row.icon_name,\n        \"updated_by_user_id\": row.updated_by_user_id,\n        \"updated_at\": row.updated_at.isoformat() if row.updated_at else None,\n    }\n",
)
replace_once(
    service,
    "        \"is_active\": bool(row.is_active),\n        \"timezone_name\": row.timezone_name,\n        \"days\": [\n",
    "        \"is_active\": bool(row.is_active),\n        \"timezone_name\": row.timezone_name,\n        \"updated_by_user_id\": row.updated_by_user_id,\n        \"updated_at\": row.updated_at.isoformat() if row.updated_at else None,\n        \"days\": [\n",
)

component = "frontend/src/pages/manuals/DocumentationAssistantPanel.tsx"
replace_once(
    component,
    "    return <button type=\"button\" className=\"documentation-assistant-launcher\" onClick={() => setOpen(true)} aria-expanded=\"false\">\n      <span className=\"documentation-assistant-launcher__icon\" aria-hidden=\"true\"><Bot size={18} /><Sparkles size={11} /></span>\n      <span>Assisted search</span>\n",
    "    return <button type=\"button\" className=\"documentation-assistant-launcher\" onClick={() => setOpen(true)} aria-expanded=\"false\" aria-label=\"Open assisted search\">\n      <span className=\"documentation-assistant-launcher__icon\" aria-hidden=\"true\"><Bot size={18} /><Sparkles size={11} /></span>\n      <span className=\"documentation-assistant-launcher__label\">Assisted search</span>\n",
)

css = "frontend/src/pages/manuals/documentationAssistantPanel.css"
replace_once(
    css,
    "  .documentation-assistant-launcher span {\n    display: none;\n  }\n",
    "  .documentation-assistant-launcher__label {\n    display: none;\n  }\n",
)

backend_test = ROOT / "backend/amodb/apps/workforce/tests/test_hr_review_flags.py"
backend_text = backend_test.read_text(encoding="utf-8").rstrip()
backend_addition = r'''


def test_readiness_labels_only_the_managed_default_pattern():
    source = inspect.getsource(hr_service._person_readiness_for_user)
    assert "managed_default_pattern_id" in source
    assert "str(pattern.work_pattern_id) == managed_default_pattern_id" in source
    assert 'work_pattern.code == "DEFAULT-DAY-5X2"' not in source
    assert "amo_id=amo_id" in inspect.getsource(hr_service.list_people_page_v2)
    assert "amo_id=amo_id" in inspect.getsource(hr_service.dashboard_v2)


def test_bootstrap_definition_snapshots_include_attribution_mutations():
    shift_source = inspect.getsource(hr_service._shift_template_snapshot)
    pattern_source = inspect.getsource(hr_service._work_pattern_snapshot)
    for source in (shift_source, pattern_source):
        assert '"updated_by_user_id"' in source
        assert '"updated_at"' in source
'''
if "test_readiness_labels_only_the_managed_default_pattern" not in backend_text:
    backend_test.write_text(backend_text + backend_addition + "\n", encoding="utf-8")

frontend_test = ROOT / "frontend/src/pages/rostering/documentationAssistantUx.test.ts"
frontend_text = frontend_test.read_text(encoding="utf-8")
old = '''    expect(assistantCss).toContain("prefers-reduced-motion");
  });
'''
new = '''    expect(assistantCss).toContain("prefers-reduced-motion");
    expect(assistant).toContain('aria-label="Open assisted search"');
    expect(assistant).toContain("documentation-assistant-launcher__label");
    expect(assistantCss).toContain(".documentation-assistant-launcher__label");
    expect(assistantCss).not.toContain(".documentation-assistant-launcher span");
  });
'''
if old not in frontend_text:
    raise RuntimeError("assistant UX test anchor missing")
frontend_test.write_text(frontend_text.replace(old, new, 1), encoding="utf-8")

doc = ROOT / "backend/docs/rostering/WORKFORCE_ACTIVE_USER_READINESS_20260729.md"
doc_text = doc.read_text(encoding="utf-8")
anchor = "- Every actual bootstrap definition or assignment mutation writes an append-only AuditEvent with the actor, before/after state, and one correlation ID inside the same transaction.\n"
addition = (
    anchor
    + "- Readiness labels the system baseline only when the assignment targets the deterministic managed pattern ID; a tenant-authored record that reuses the code is never presented as portal-owned.\n"
    + "- Definition audit snapshots include `updated_by_user_id` and `updated_at`, so administrator attribution changes cannot occur without matching audit evidence.\n"
    + "- The mobile assistant launcher keeps its icon visible and exposes an explicit accessible name while only the visual text label is collapsed.\n"
)
if anchor not in doc_text:
    raise RuntimeError("documentation final-review anchor missing")
doc.write_text(doc_text.replace(anchor, addition, 1), encoding="utf-8")

print("PR377 final Codex review corrections applied")
