from __future__ import annotations

from pathlib import Path


MIGRATION = (
    Path(__file__).resolve().parents[3]
    / "alembic"
    / "versions"
    / "quality_260804_trigger_fix.py"
)


def test_trigger_fix_preserves_event_provenance_and_caller_context() -> None:
    source = MIGRATION.read_text(encoding="utf-8")
    assert "current_row := CASE WHEN TG_OP = 'DELETE' THEN NULL ELSE to_jsonb(NEW) END" in source
    assert "set_config('app.tenant_id', tenant_id, true)" in source
    assert "set_config('app.tenant_id', COALESCE(previous_tenant_id, ''), true)" in source
    assert "set_config('app.user_id', COALESCE(previous_user_id, ''), true)" in source
    assert "SELECT 1 FROM users WHERE id::text = actor_id" in source


def test_report_and_out_of_tolerance_sources_emit_assurance_events() -> None:
    source = MIGRATION.read_text(encoding="utf-8")
    assert '("qms_report_exports", "REPORT")' in source
    assert '("qms_out_of_tolerance_events", "OUT_OF_TOLERANCE")' in source
    assert "FOR EACH ROW EXECUTE FUNCTION quality_capture_assurance_event('{source_type}')" in source
