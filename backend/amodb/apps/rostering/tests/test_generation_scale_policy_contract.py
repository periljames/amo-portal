from __future__ import annotations

from pathlib import Path
from types import SimpleNamespace

import pytest

from amodb.apps.rostering import generation_scale_policy, generation_setup_router


ROOT = Path(__file__).resolve().parents[1]


def test_generation_scale_policy_is_installed_before_validation_wrappers():
    source = (ROOT / "application_router.py").read_text(encoding="utf-8")
    scale_install = "generation_scale_policy.install(rostering_route_module.services)"
    compliance_install = "compliance_policy.install_validation_policy()"
    shift_install = "shift_scheduling_policy.install_service_policy(rostering_route_module.services)"

    assert scale_install in source
    assert source.index(scale_install) < source.index(compliance_install)
    assert source.index(scale_install) < source.index(shift_install)


def test_scale_policy_never_reloads_the_complete_roster_to_return_one_batch():
    source = (ROOT / "generation_scale_policy.py").read_text(encoding="utf-8")
    assert "list_assignments(" not in source
    assert "models.RosterAssignment.id.in_(assignment_ids)" in source
    assert "models.RosterAssignment.version_id == version_id" in source
    assert "models.RosterAssignment.amo_id == amo_id" in source
    assert ".with_for_update(of=models.RosterVersion)" in source


def test_locked_version_lookup_explicitly_defers_large_selectin_collections():
    source = (ROOT / "generation_scale_policy.py").read_text(encoding="utf-8")
    assert "lazyload(models.RosterVersion.assignments)" in source
    assert "lazyload(models.RosterVersion.validation_findings)" in source
    assert "lazyload(models.RosterVersion.exceptions)" in source
    assert "selectinload(models.RosterVersion.period)" in source


def test_generation_receipt_is_checked_before_canonical_revision_validation():
    source = (ROOT / "generation_scale_policy.py").read_text(encoding="utf-8")
    wrapper_start = source.index("def generate_from_patterns(db, *, version, actor_user_id: str, payload):")
    wrapper = source[wrapper_start:]
    assert wrapper.index("common.command_receipt(") < wrapper.index("return original_generate_from_patterns(")
    assert 'operation="GENERATE_PATTERN"' in wrapper
    assert "_result_from_receipt" in wrapper


def test_receipt_replay_rejects_a_different_roster_version_before_loading_rows(monkeypatch):
    receipt = SimpleNamespace(
        response_json={
            "version_id": "VERSION-A",
            "assignment_ids": ["ASSIGNMENT-A"],
            "skipped": [],
            "conflicts": [],
        }
    )
    loaded = False

    def _unexpected_loader(*args, **kwargs):
        nonlocal loaded
        loaded = True
        return {}

    monkeypatch.setattr(generation_scale_policy, "_load_assignments_by_id", _unexpected_loader)

    with pytest.raises(ValueError, match="different roster version"):
        generation_scale_policy._result_from_receipt(
            object(),
            amo_id="AMO-A",
            version_id="VERSION-B",
            receipt=receipt,
        )

    assert loaded is False


def test_batch_cycle_start_requires_the_complete_rotation_to_match():
    pattern_a = SimpleNamespace(
        cycle_length_days=2,
        timezone_name="Africa/Nairobi",
        days=[
            SimpleNamespace(
                cycle_day_index=0,
                shift_template_id="SHIFT-A",
                status="DUTY",
                start_time_local="06:00",
                end_time_local="15:00",
                spans_next_day=False,
                planned_minutes=540,
            ),
            SimpleNamespace(
                cycle_day_index=1,
                shift_template_id="SHIFT-B",
                status="DUTY",
                start_time_local="12:00",
                end_time_local="21:00",
                spans_next_day=False,
                planned_minutes=540,
            ),
        ],
    )
    pattern_b = SimpleNamespace(
        cycle_length_days=2,
        timezone_name="Africa/Nairobi",
        days=list(pattern_a.days),
    )
    pattern_c = SimpleNamespace(
        cycle_length_days=2,
        timezone_name="Africa/Nairobi",
        days=[*pattern_a.days[:-1], SimpleNamespace(
            cycle_day_index=1,
            shift_template_id="SHIFT-C",
            status="DUTY",
            start_time_local="12:00",
            end_time_local="21:00",
            spans_next_day=False,
            planned_minutes=540,
        )],
    )

    assert generation_setup_router._rotation_signature(pattern_a) == generation_setup_router._rotation_signature(pattern_b)
    assert generation_setup_router._rotation_signature(pattern_a) != generation_setup_router._rotation_signature(pattern_c)


def test_batch_cycle_start_route_is_tenant_scoped_and_audited():
    source = (ROOT / "generation_setup_router.py").read_text(encoding="utf-8")
    assert '"/work-pattern-assignments/cycle-starts/batch"' in source
    assert "workforce_services.effective_amo_id(user)" in source
    assert "EmployeeWorkPatternAssignment.amo_id == amo_id" in source
    assert "WORKFORCE_ASSIGN_PATTERNS" in source
    assert "WORK_PATTERN_CYCLE_START_ROTATION_MISMATCH" in source
    assert 'action="batch_cycle_start_update"' in source
