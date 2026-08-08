from __future__ import annotations

from types import SimpleNamespace

import pytest
from alembic.config import Config
from alembic.script import ScriptDirectory
from fastapi import HTTPException
from pydantic import ValidationError

from amodb.database import Base
from amodb.apps.quality import canonical_router
from amodb.apps.quality.audit_programme_queue_router import router as audit_programme_queue_router
from amodb.apps.quality.audit_programme_router import (
    ProgrammeCreate,
    ProgrammeItemCreate,
    _TRANSITIONS,
    _assert_editable,
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


def test_audit_programme_router_exposes_governed_bounded_contract() -> None:
    methods = _route_methods(audit_programme_router)
    assert {
        ("/audit-programmes", "GET"),
        ("/audit-programmes", "POST"),
        ("/audit-programmes/{programme_id}", "GET"),
        ("/audit-programmes/{programme_id}", "PATCH"),
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
        (canonical_router.legacy_router, "/api/maintenance/{amo_code}/qms"),
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

    for router, prefix in (
        (canonical_router.router, "/api/maintenance/{amo_code}/quality"),
        (canonical_router.legacy_router, "/api/maintenance/{amo_code}/qms"),
    ):
        schedule_path = f"{prefix}/audit-programmes/{{programme_id}}/items/{{item_id}}/schedule"
        matches = _matching(router, schedule_path, "POST")
        assert len(matches) == 1
        assert matches[0].endpoint.__name__ == "schedule_programme_requirement"
        assert router.routes.index(matches[0]) < _catchall_index(router)


def test_audit_programme_routes_are_promoted_before_generic_quality_catchall() -> None:
    for router, prefix in (
        (canonical_router.router, "/api/maintenance/{amo_code}/quality"),
        (canonical_router.legacy_router, "/api/maintenance/{amo_code}/qms"),
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


def test_audit_programme_schedule_lineage_migration_extends_single_chain() -> None:
    script = ScriptDirectory.from_config(Config("amodb/alembic.ini"))
    revision = script.get_revision("quality_260808_prog_schedule")
    assert revision is not None
    assert revision.down_revision == "quality_260808_audit_programme"
    assert len(revision.revision) <= 32


def test_audit_programme_models_are_registered_in_shared_metadata() -> None:
    assert "quality_audit_programmes" in Base.metadata.tables
    assert "quality_audit_universe_items" in Base.metadata.tables
    assert "quality_audit_programme_items" in Base.metadata.tables
    assert "quality_audit_programme_events" in Base.metadata.tables
    assert Base.metadata.tables["quality_audit_programmes"].c.amo_id.nullable is False
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


def test_programme_period_and_custom_recurrence_are_validated() -> None:
    with pytest.raises(ValidationError):
        ProgrammeCreate(
            programme_year=2026,
            title="2026 audit programme",
            period_start="2026-12-31",
            period_end="2026-01-01",
        )
    with pytest.raises(ValidationError):
        ProgrammeItemCreate(
            universe_item_id="universe-1",
            audit_type="INTERNAL",
            title="Internal audit",
            scope="Quality system",
            recurrence="CUSTOM",
        )


def test_programme_recurrence_maps_only_to_supported_authoritative_planner_cadence() -> None:
    assert _RECURRENCE_TO_FREQUENCY == {
        "ONE_TIME": QMSAuditScheduleFrequency.ONE_TIME,
        "MONTHLY": QMSAuditScheduleFrequency.MONTHLY,
        "QUARTERLY": QMSAuditScheduleFrequency.QUARTERLY,
        "SEMI_ANNUAL": QMSAuditScheduleFrequency.BI_ANNUAL,
        "ANNUAL": QMSAuditScheduleFrequency.ANNUAL,
    }
    assert _expected_frequency(SimpleNamespace(recurrence="SEMI_ANNUAL")) == QMSAuditScheduleFrequency.BI_ANNUAL
    for recurrence in ("CUSTOM", "RISK_TRIGGERED"):
        with pytest.raises(HTTPException) as exc:
            _expected_frequency(SimpleNamespace(recurrence=recurrence))
        assert exc.value.status_code == 409


def test_universe_source_identity_is_a_real_relational_contract() -> None:
    table = Base.metadata.tables["quality_audit_universe_items"]
    unique_names = {constraint.name for constraint in table.constraints if constraint.name}
    assert "uq_quality_audit_universe_source" in unique_names
    item_table = Base.metadata.tables["quality_audit_programme_items"]
    fk_targets = {element.target_fullname for fk in item_table.foreign_key_constraints for element in fk.elements}
    assert "quality_audit_programmes.id" in fk_targets
    assert "quality_audit_universe_items.id" in fk_targets
