from __future__ import annotations

from datetime import datetime, timezone
from types import SimpleNamespace

from amodb.apps.rostering import assignments


def test_assignment_local_date_uses_roster_period_timezone():
    version = SimpleNamespace(period=SimpleNamespace(timezone_name="Pacific/Kiritimati"))
    starts_at = datetime(2026, 7, 24, 12, 30, tzinfo=timezone.utc)
    assert assignments._local_start_date(version, starts_at).isoformat() == "2026-07-25"


def test_assignment_validation_uses_effective_dated_base_before_contract_fallback():
    source = assignments._validate_assignment_payload.__code__.co_names
    assert "_resolve_assignment_base" in source


def test_clearing_duty_base_override_resolves_effective_base_before_update():
    source = assignments.update_assignment.__code__.co_names
    assert "_resolve_assignment_base" in source
