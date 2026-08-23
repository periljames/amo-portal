from __future__ import annotations

from pathlib import Path
from types import SimpleNamespace

from amodb.apps.workforce import attendance_warning_policy


ROSTERING_ROOT = Path(__file__).resolve().parents[1]
WORKFORCE_ROOT = ROSTERING_ROOT.parent / "workforce"


def test_assignment_read_uses_one_authoritative_assignment_query():
    source = (ROSTERING_ROOT / "generation_read_router.py").read_text(encoding="utf-8")
    aggregate = (ROSTERING_ROOT / "application_router.py").read_text(encoding="utf-8")

    assert "db.query(models.RosterVersion.id)" in source
    assert "services.list_assignments(" in source
    assert "services.get_version(" not in source
    assert '"GET" in (getattr(route, "methods", set()) or set())' in aggregate
    assert "router.include_router(generation_read_router)" in aggregate


def test_attendance_warning_policy_deduplicates_display_reasons_without_events():
    class FakeService:
        @staticmethod
        def attendance_summary(*_args, **_kwargs):
            return SimpleNamespace(
                warnings=["same reason", "same reason", "another reason", "same reason"],
                events=["event-a", "event-b", "event-c"],
                requires_review_count=3,
            )

    # Test a fresh policy install without relying on application import order.
    original_installed = attendance_warning_policy._INSTALLED
    try:
        attendance_warning_policy._INSTALLED = False
        attendance_warning_policy.install(FakeService)
        summary = FakeService.attendance_summary()
        assert summary.warnings == ["same reason", "another reason"]
        assert summary.events == ["event-a", "event-b", "event-c"]
        assert summary.requires_review_count == 3
    finally:
        attendance_warning_policy._INSTALLED = original_installed


def test_attendance_warning_policy_is_installed_on_canonical_workforce_services():
    aggregate = (ROSTERING_ROOT / "application_router.py").read_text(encoding="utf-8")
    source = (WORKFORCE_ROOT / "attendance_warning_policy.py").read_text(encoding="utf-8")

    assert "attendance_warning_policy.install(workforce_services)" in aggregate
    assert "dict.fromkeys" in source
