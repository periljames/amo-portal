from __future__ import annotations

from pathlib import Path


ROOT = Path(__file__).resolve().parents[4]
APP = ROOT / "amodb" / "apps" / "doc_control"


def _text(path: Path) -> str:
    return path.read_text(encoding="utf-8")


def test_controlled_copy_creation_gets_governed_default_due_date() -> None:
    source = _text(APP / "workspace_copy_due_router.py")
    assert 'policy_payload.get("default_due_days", 30)' in source
    assert "max(1, min(days, 3650))" in source
    assert "if not payload.due_back_at:" in source
    assert 'update={"due_back_at": utcnow() + timedelta(days=_default_due_days(tenant))}' in source


def test_explicit_copy_due_date_is_not_overwritten() -> None:
    source = _text(APP / "workspace_copy_due_router.py")
    body = source.split("def create_controlled_copy_with_due_policy", 1)[1]
    assert "if not payload.due_back_at:" in body
    assert "return _create_copy(" in body


def test_due_policy_override_precedes_compatibility_copy_router() -> None:
    router = _text(APP / "router.py")
    due_import = router.index("workspace_copy_due_router")
    compatibility_import = router.index("workspace_copy_router")
    assert due_import < compatibility_import
    due_include = router.index("workspace_copy_due_router,", router.index("router.include_router"))
    compatibility_include = router.index("workspace_copy_router,", due_include + 1)
    assert due_include < compatibility_include


def test_reminder_engine_consumes_copy_due_back_date() -> None:
    reminders = _text(APP / "reminder_service.py")
    assert "dm.DocumentControlledCopy.due_back_at.isnot(None)" in reminders
    assert "row.due_back_at" in reminders
    assert 'obligation_type="CONTROLLED_COPY_RETURN"' in reminders
