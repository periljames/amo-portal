from __future__ import annotations

from datetime import date
from types import SimpleNamespace

import pytest
from alembic.config import Config
from alembic.script import ScriptDirectory
from fastapi import HTTPException
from pydantic import ValidationError

from amodb.database import Base
from amodb.apps.quality import canonical_router
from amodb.apps.quality.audit_programme_optimizer import ALGORITHM_VERSION, WEIGHTS, score_surveillance
from amodb.apps.quality.audit_programme_queue_router import router as audit_programme_queue_router
from amodb.apps.quality.audit_programme_router import (
    ProgrammeCreate,
    ProgrammeItemCreate,
    _TRANSITIONS,
    _assert_editable,
    _programme_readiness,
    _recurrence_for_interval,
    _validate_item_window,
    router as audit_programme_router,
)
from amodb.apps.quality.audit_programme_schedule_router import (
    _RECURRENCE_TO_FREQUENCY,
    _expected_frequency,
    router as audit_programme_schedule_router,
)
from amodb.apps.quality.enums import QMSAuditScheduleFrequency


def _route_methods(router):
    return {(str(route.path), method) for route in router.routes for method in (getattr(route, "methods", None) or set())}


def _catchall_index(router) -> int:
    return next(index for index, route in enumerate(router.routes) if str(route.path).endswith("/{module_path:path}"))


def _matching(router, path: str, method: str):
    return [route for route in router.routes if str(route.path) == path and method in (getattr(route, "methods", None) or set())]


def _readiness_programme(regulatory_basis: list | None = None):
    item = SimpleNamespace(
        title="Maintenance Department Audit",
        target_start=date(2026, 8, 1),
        target_end=date(2026, 8, 31),
        criteria=["KCAR / MPM"],
        mandatory_surveillance=True,
        state="PLANNED",
        universe_item=SimpleNamespace(risk_classification="HIGH"),
    )
    return SimpleNamespace(
        items=[item],
        regulatory_basis=regulatory_basis or [],
        period_start=date(2026, 1, 1),
        period_end=date(2026, 12, 31),
    )


def test_audit_programme_router_exposes_governed_bounded_contract() -> None:
    methods = _route_methods(audit_programme_router)
    assert {
        ("/audit-programmes", "GET"),
        ("/audit-programmes", "POST"),
        ("/audit-programmes/{programme_id}", "GET"),
        ("/audit-programmes/{programme_id}", "PATCH"),
        ("/audit-programmes/{programme_id}/optimizer", "GET"),
        ("/audit-programmes/{programme_id}/optimizer/rebuild", "POST"),
        ("/audit-programmes/{programme_id}/transitions", "POST"),
        ("/audit-programmes/{programme_id}/amendments", "POST"),
        ("/audit-programmes/universe/items", "GET"),
        ("/audit-programmes/universe/items", "POST"),
        ("/audit-programmes/universe/items/{universe_item_id}", "PATCH"),
        ("/audit-programmes/{programme_id}/items", "POST"),
        ("/audit-programmes/{programme_id}/items/{item_id}", "PATCH"),
    }.issubset(methods)


def test_programme_queue_is_bounded_and_static_before_generic_quality_catchall() -> None:
    methods = _route_methods(audit_programme_queue_router)
    assert ("/audit-programmes/planner/queue", "GET") in methods

    for router, prefix in (
        (canonical_router.router, "/api/maintenance/{amo_code}/quality"),
    ):
        queue_path = f"{prefix}/audit-programmes/planner/queue"
        matches = _matching(router, queue_path, "GET")
        assert len(matches) == 1
        assert matches[0].endpoint.__name__ == "list_programme_scheduling_queue"
        assert router.routes.index(matches[0]) < _catchall_index(router)


def test_programme_schedule_adapter_exposes_authoritative_link_contract() -> None:
    methods = _route_methods(audit_programme_schedule_router)
    assert {
        ("/audit-programmes/{programme_id}/schedule-links", "GET"),
        ("/audit-programmes/{programme_id}/items/{item_id}/schedule", "POST"),
    }.issubset(methods)

    adapter_matches = _matching(
        audit_programme_schedule_router,
        "/audit-programmes/{programme_id}/items/{item_id}/schedule",
        "POST",
    )
    assert len(adapter_matches) == 1
    assert adapter_matches[0].endpoint.__name__ == "schedule_programme_requirement"

    for router, prefix in (
        (canonical_router.router, "/api/maintenance/{amo_code}/quality"),
    ):
        schedule_path = f"{prefix}/audit-programmes/{{programme_id}}/items/{{item_id}}/schedule"
        matches = _matching(router, schedule_path, "POST")
        assert len(matches) == 1
        assert matches[0].endpoint.__name__ == "schedule_guarded_programme_requirement"
        assert router.routes.index(matches[0]) < _catchall_index(router)


def test_audit_programme_routes_are_promoted_before_generic_quality_catchall() -> None:
    for router, prefix in (
        (canonical_router.router, "/api/maintenance/{amo_code}/quality"),
    ):
        path = f"{prefix}/audit-programmes"
        matches = _matching(router, path, "GET")
        assert len(matches) == 1
        assert matches[0].endpoint.__name__ == "list_programmes"
        assert router.routes.index(matches[0]) < _catchall_index(router)
        universe_path = f"{prefix}/audit-programmes/universe/items"
        universe = _matching(router, universe_path, "GET")
        assert len(universe) == 1
        assert universe[0].endpoint.__name__ == "list_universe"
        assert router.routes.index(universe[0]) < _catchall_index(router)
        optimizer_path = f"{prefix}/audit-programmes/{{programme_id}}/optimizer"
        optimizer = _matching(router, optimizer_path, "GET")
        assert len(optimizer) == 1
        assert optimizer[0].endpoint.__name__ == "get_programme_optimizer"
        assert router.routes.index(optimizer[0]) < _catchall_index(router)


def test_audit_programme_schedule_lineage_migration_extends_single_chain() -> None:
    script = ScriptDirectory.from_config(Config("amodb/alembic.ini"))
    revision = script.get_revision("quality_260808_prog_schedule")
    assert revision is not None
    assert revision.down_revision == "quality_260808_audit_programme"
    assert len(revision.revision) <= 32


def test_hybrid_programme_migration_extends_current_quality_chain_without_methodology_backfill() -> None:
    script = ScriptDirectory.from_config(Config("amodb/alembic.ini"))
    revision = script.get_revision("quality_260823_hybrid_programme")
    assert revision is not None
    assert revision.down_revision == "quality_260820_provider_gov"
    assert len(revision.revision) <= 32


def test_audit_programme_models_are_registered_in_shared_metadata() -> None:
    assert "quality_audit_programmes" in Base.metadata.tables
    assert "quality_audit_universe_items" in Base.metadata.tables
    assert "quality_audit_programme_items" in Base.metadata.tables
    assert "quality_audit_programme_events" in Base.metadata.tables
    programme_table = Base.metadata.tables["quality_audit_programmes"]
    assert programme_table.c.amo_id.nullable is False
    assert programme_table.c.continuous_monitoring_enabled.nullable is False
    assert programme_table.c.optimizer_version.nullable is False
    assert "programme_methodology" not in programme_table.c
    assert "methodology_rationale" not in programme_table.c
    assert Base.metadata.tables["quality_audit_universe_items"].c.amo_id.nullable is False

    item_table = Base.metadata.tables["quality_audit_programme_items"]
    assert item_table.c.schedule_id.nullable is True
    assert item_table.c.scheduled_by_user_id.nullable is True
    assert item_table.c.scheduled_at.nullable is True
    unique_names = {constraint.name for constraint in item_table.constraints if constraint.name}
    assert "uq_quality_audit_programme_item_schedule" in unique_names
    fk_targets = {element.target_fullname for fk in item_table.foreign_key_constraints for element in fk.elements}
    assert "qms_audit_schedules.id" in fk_targets
    assert "users.id" in fk_targets


def test_programme_lifecycle_is_explicit_and_terminal_history_is_immutable() -> None:
    assert _TRANSITIONS == {
        "DRAFT": {"UNDER_REVIEW"},
        "UNDER_REVIEW": {"DRAFT", "APPROVED"},
        "APPROVED": {"ACTIVE", "SUPERSEDED"},
        "ACTIVE": {"SUPERSEDED", "CLOSED"},
        "SUPERSEDED": set(),
        "CLOSED": set(),
    }
    for state in ("APPROVED", "ACTIVE", "SUPERSEDED", "CLOSED"):
        with pytest.raises(HTTPException) as exc:
            _assert_editable(SimpleNamespace(status=state))
        assert exc.value.status_code == 409
    _assert_editable(SimpleNamespace(status="DRAFT"))
    _assert_editable(SimpleNamespace(status="UNDER_REVIEW"))


def test_programme_payload_has_no_methodology_choice_and_validates_period_and_recurrence() -> None:
    assert "programme_methodology" not in ProgrammeCreate.model_fields
    assert "methodology_rationale" not in ProgrammeCreate.model_fields

    with pytest.raises(ValidationError):
        ProgrammeCreate(
            programme_year=2026,
            title="Invalid period",
            period_start="2026-12-31",
            period_end="2026-01-01",
        )

    with pytest.raises(ValidationError):
        ProgrammeItemCreate(
            universe_item_id="universe",
            audit_type="INTERNAL",
            title="Bad custom cadence",
            scope="Quality",
            recurrence="CUSTOM",
        )


def test_programme_readiness_always_keeps_compliance_baseline() -> None:
    without_basis = _programme_readiness(_readiness_programme())
    assert without_basis["ready_for_approval"] is False
    assert "NO_COMPLIANCE_BASIS" in {blocker["code"] for blocker in without_basis["blockers"]}

    with_basis = _programme_readiness(_readiness_programme(["KCAR / approved MPM"]))
    assert with_basis["ready_for_approval"] is True
    assert with_basis["mandatory_requirement_count"] == 1
    assert with_basis["high_risk_requirement_count"] == 1

    with_gap = _programme_readiness(_readiness_programme(["KCAR / approved MPM"]), mandatory_coverage_gaps=1)
    assert with_gap["ready_for_approval"] is False
    assert "MANDATORY_COVERAGE_GAP" in {blocker["code"] for blocker in with_gap["blockers"]}


def test_hybrid_optimizer_is_versioned_transparent_and_only_evidence_increases_mandatory_surveillance() -> None:
    assert ALGORITHM_VERSION == "HYBRID_ASSURANCE_V1"
    assert sum(WEIGHTS.values()) == pytest.approx(1.0)
    entity = SimpleNamespace(
        regulatory_criticality="LOW",
        risk_classification="LOW",
        mandatory_surveillance=True,
        surveillance_interval_days=365,
    )
    baseline = score_surveillance(universe_item=entity, signals={})
    assert baseline["priority_score"] >= 40
    assert baseline["priority_score"] < 60
    assert baseline["recommended_interval_days"] == 365
    assert baseline["mandatory_baseline"] is True
    assert baseline["recommend_in_programme"] is True
    assert {entry["factor"] for entry in baseline["drivers"]} >= {"COMPLIANCE", "RISK", "PERFORMANCE", "MANDATORY_FLOOR", "MANDATORY_INTERVAL_CAP"}

    pressured = score_surveillance(
        universe_item=entity,
        signals={"repeat_findings": 3, "open_findings": 2, "follow_up_required": 1, "adverse_trends": 2},
    )
    assert pressured["priority_score"] > baseline["priority_score"]
    assert pressured["recommended_interval_days"] < baseline["recommended_interval_days"]
    assert pressured["components"]["performance"] > baseline["components"]["performance"]


def test_hybrid_interval_maps_to_supported_planner_cadence() -> None:
    assert _recurrence_for_interval(30) == ("MONTHLY", None)
    assert _recurrence_for_interval(90) == ("QUARTERLY", None)
    assert _recurrence_for_interval(180) == ("SEMI_ANNUAL", None)
    assert _recurrence_for_interval(365) == ("ANNUAL", None)
    assert _recurrence_for_interval(730) == ("CUSTOM", 730)


def test_programme_target_window_cannot_escape_governed_period() -> None:
    programme = _readiness_programme(["KCAR / MPM"])
    _validate_item_window(programme, date(2026, 2, 1), date(2026, 2, 28))

    with pytest.raises(HTTPException) as early:
        _validate_item_window(programme, date(2025, 12, 31), date(2026, 1, 2))
    assert early.value.status_code == 422

    with pytest.raises(HTTPException) as late:
        _validate_item_window(programme, date(2026, 12, 30), date(2027, 1, 2))
    assert late.value.status_code == 422


def test_schedule_frequency_is_derived_from_governed_recurrence() -> None:
    assert _RECURRENCE_TO_FREQUENCY["ONE_TIME"] == QMSAuditScheduleFrequency.ONE_TIME
    assert _RECURRENCE_TO_FREQUENCY["QUARTERLY"] == QMSAuditScheduleFrequency.QUARTERLY
    assert _RECURRENCE_TO_FREQUENCY["SEMI_ANNUAL"] == QMSAuditScheduleFrequency.BI_ANNUAL
    assert _expected_frequency(SimpleNamespace(recurrence="ANNUAL")) == QMSAuditScheduleFrequency.ANNUAL

    with pytest.raises(HTTPException) as exc:
        _expected_frequency(SimpleNamespace(recurrence="RISK_TRIGGERED"))
    assert exc.value.status_code == 409
