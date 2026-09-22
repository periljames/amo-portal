from __future__ import annotations

import inspect
import importlib
from pathlib import Path
import re
from types import SimpleNamespace

import pytest
import sqlalchemy as sa
from alembic.config import Config
from alembic.migration import MigrationContext
from alembic.operations import Operations
from alembic.script import ScriptDirectory
from fastapi import HTTPException
from pydantic import ValidationError

from amodb.apps.quality import audit_programme_schedule_router
from amodb.apps.quality import audit_programme_occurrence_router
from amodb.apps.quality import audit_archive_governance_router
from amodb.apps.quality import audit_deferral_router
from amodb.apps.quality import audit_external_access_router
from amodb.apps.quality import audit_programme_queue_router
from amodb.apps.quality import audit_report_governance_router
from amodb.apps.quality import audit_risk_planning_router
from amodb.apps.quality import audit_source_handoff_router
from amodb.apps.quality import mission_router
from amodb.apps.quality import models as quality_models
from amodb.apps.quality import people_router
from amodb.apps.quality import people_authorization_router
from amodb.apps.quality import audit_assignment_guard
from amodb.apps.quality import planner_schedule_router
from amodb.apps.quality import tenant_security
from amodb.apps.quality.schemas import QualityWorkflowSettingsUpdate

quality_router = importlib.import_module("amodb.apps.quality.router")


QUALITY_DIR = Path(__file__).resolve().parents[1]


def test_runtime_quality_code_never_repairs_the_database_schema() -> None:
    runtime_sources = [
        (QUALITY_DIR / "router.py").read_text(encoding="utf-8"),
        (QUALITY_DIR / "service.py").read_text(encoding="utf-8"),
    ]
    forbidden = (
        "ensure_qms_audit_reference_schema",
        "ensure_qms_audit_scope_schema",
        "_ensure_qms_runtime_schema_compat",
        "CREATE TABLE IF NOT EXISTS",
        "ALTER TABLE qms_",
        "__table__.create(",
    )
    for source in runtime_sources:
        assert not any(token in source for token in forbidden)
    assert not (QUALITY_DIR / "schema_compat.py").exists()


def test_proven_dead_route_order_placeholder_is_removed() -> None:
    assert not (QUALITY_DIR / "effectiveness_response_route_order.py").exists()
    assert not (QUALITY_DIR / "audit_external_session_guard_router.py").exists()
    assert not (QUALITY_DIR / "audit_external_fieldwork_draft_enable_router.py").exists()
    scripts_dir = QUALITY_DIR.parents[1] / "scripts"
    assert not (scripts_dir / "seed_safarilink_audit_privileges.py").exists()
    assert not (scripts_dir / "workflow_iso_people_lifecycle.py").exists()


def test_deployed_quality_routes_have_unique_match_shapes() -> None:
    from amodb.main import app

    seen: set[tuple[str, str]] = set()
    duplicates: list[tuple[str, str]] = []
    for route in app.routes:
        path = str(getattr(route, "path", ""))
        if "/quality" not in path:
            continue
        shape = re.sub(r"\{[^{}]+\}", "{}", path)
        for method in getattr(route, "methods", None) or ():
            if method in {"HEAD", "OPTIONS"}:
                continue
            signature = shape, method
            if signature in seen:
                duplicates.append(signature)
            seen.add(signature)
    assert duplicates == []

    programme_paths = [
        str(route.path)
        for route in app.routes
        if "/quality/audit-programmes" in str(getattr(route, "path", ""))
        and "GET" in (getattr(route, "methods", None) or ())
    ]
    prefix = "/api/maintenance/{amo_code}/quality/audit-programmes"
    assert programme_paths.index(f"{prefix}/risk-context") < programme_paths.index(
        f"{prefix}/{{programme_id}}"
    )


def test_superseded_base_mutation_routes_are_removed() -> None:
    mission_methods = {
        method
        for route in mission_router.router.routes
        for method in (getattr(route, "methods", None) or set())
    }
    assert mission_methods <= {"GET", "HEAD", "OPTIONS"}
    planner_routes = {
        (str(route.path), method)
        for route in planner_schedule_router.planner_schedule_router.routes
        for method in (getattr(route, "methods", None) or set())
    }
    assert ("/integrations/calendar/audit-schedules", "POST") not in planner_routes
    assert ("/integrations/calendar/audit-schedules/{schedule_id}/resume", "POST") not in planner_routes
    programme_routes = {
        (str(route.path), method)
        for route in audit_programme_schedule_router.router.routes
        for method in (getattr(route, "methods", None) or set())
    }
    assert ("/{programme_id}/items/{item_id}/schedule", "POST") not in programme_routes

    superseded_routes = (
        (audit_external_access_router.router, {
            ("/audits/{audit_id}/findings/{finding_id}/release", "POST"),
        }),
        (audit_report_governance_router.router, {
            ("/audits/{audit_id}/report-revisions/{revision_id}/transitions", "POST"),
        }),
        (audit_archive_governance_router.router, {
            ("/audits/{audit_id}/archive-governance", "GET"),
            ("/audits/{audit_id}/archive-manifests/generate", "POST"),
            ("/audits/{audit_id}/archive-manifests/{manifest_id}/dispose", "POST"),
        }),
    )
    for base_router, removed in superseded_routes:
        registered = {
            (str(route.path), method)
            for route in base_router.routes
            for method in (getattr(route, "methods", None) or set())
        }
        assert removed.isdisjoint(registered)


@pytest.mark.parametrize(
    "payload",
    [
        {"report_reminder_days": []},
        {"report_reminder_days": [-1]},
        {"report_reminder_days": [61]},
        {"car_reminder_percentages": []},
        {"car_reminder_percentages": [0]},
        {"car_reminder_percentages": [100]},
    ],
)
def test_workflow_settings_reject_invalid_reminder_configuration(payload) -> None:
    with pytest.raises(ValidationError):
        QualityWorkflowSettingsUpdate(**payload)


def test_direct_quality_routes_require_explicit_tenant_context() -> None:
    user = SimpleNamespace(amo_id=None, effective_amo_id=None)
    with pytest.raises(HTTPException) as exc:
        quality_router._current_amo_id(user)
    assert exc.value.status_code == 403


def test_unscoped_reliability_sources_are_excluded(monkeypatch) -> None:
    monkeypatch.setattr(audit_risk_planning_router, "_table_columns", lambda _db, _table: {"id", "status"})

    class NoQuerySession:
        def execute(self, *_args, **_kwargs):
            raise AssertionError("an unscoped source table must never be queried")

    values, warnings = audit_risk_planning_router._reliability_context(
        NoQuerySession(),
        SimpleNamespace(amo_id="amo-a"),
    )

    assert values == {
        "high_critical_events_90d": 0,
        "repeat_events_90d": 0,
        "recurring_findings": 0,
        "open_high_recommendations": 0,
    }
    assert len(warnings) == 3
    assert {item["type"] for item in warnings} == {"TenantIsolationUnavailable"}


def test_authorization_decision_lifecycle_is_explicit_and_case_governed() -> None:
    source = inspect.getsource(people_authorization_router.authorization_lifecycle_decision)
    assert '"SUSPEND": {"ACTIVE"}' in source
    assert '"REVOKE": {"ACTIVE", "SUSPENDED"}' in source
    assert '"REINSTATE": {"SUSPENDED"}' in source
    assert '"RENEW": {"ACTIVE", "EXPIRED"}' in source
    assert "Revoked authorizations cannot be reinstated" in source
    assert "confirmed" in source


def test_final_authorization_decision_locks_case_and_uses_governed_case_state() -> None:
    source = inspect.getsource(people_authorization_router.decide_authorization_case)
    assert "_case(db, amo_id=ctx.amo_id, case_id=case_id, lock=True)" in source
    assert 'row.status != "READY_FOR_DECISION"' in source
    assert "_activate_case_authorization(" in source
    assert "db.commit()" in source


def test_list_rules_is_side_effect_free_and_default_provisioning_is_restricted() -> None:
    source = inspect.getsource(people_router.list_rules)
    assert "ensure_default_quality_privilege_rules(" not in source
    assert "sync_default_quality_privilege_rule_competence(" not in source
    assert "db.commit()" not in source
    ensure_source = inspect.getsource(people_router.ensure_default_rules)
    assert 'require_quality_write_permission("qms.authorization.policy.manage")' in inspect.getsource(people_router)
    assert "ensure_default_quality_privilege_rules(" in ensure_source
    assert "db.commit()" in ensure_source


def test_source_handoffs_and_occurrences_use_one_transaction() -> None:
    for endpoint in (
        audit_source_handoff_router.create_mission_audit_handoff,
        audit_source_handoff_router.create_signal_audit_handoff,
        audit_programme_occurrence_router.create_programme_occurrence,
    ):
        source = inspect.getsource(endpoint)
        assert "_create_guarded_planner_audit_schedule(" in source
        assert "commit=False" in source
        assert "db.commit()" in source
        assert source.index("commit=False") < source.rindex("db.commit()")


def test_applied_deferrals_remain_visible_and_schedulable() -> None:
    apply_source = inspect.getsource(audit_deferral_router.apply_deferral)
    queue_source = inspect.getsource(audit_programme_queue_router.list_programme_scheduling_queue)
    schedule_source = inspect.getsource(audit_programme_schedule_router._validate_programme_window)
    assert 'item.state = "DEFERRED"' in apply_source
    assert '["PLANNED", "DEFERRED"]' in queue_source
    assert '{"PLANNED", "DEFERRED"}' in schedule_source


def test_tenant_join_keys_are_present_on_assignment_capacity_queries() -> None:
    assignment_source = inspect.getsource(audit_assignment_guard._capacity_evidence)
    assert "QMSPlannerScheduleMetadata.amo_id == quality_models.QMSAuditSchedule.amo_id" in assignment_source
    assert "QMSPlannerScheduleMetadata.amo_id == amo_id" in assignment_source


def test_planner_automation_runs_in_tenant_scoped_transactions() -> None:
    tenant_cycle = inspect.getsource(planner_schedule_router._run_quality_planner_tenant)
    reminders = inspect.getsource(planner_schedule_router._run_audit_reminders)
    assert "set_postgres_tenant_context(" in tenant_cycle
    assert "QMSAuditSchedule.amo_id == amo_id" in tenant_cycle
    assert "_run_audit_reminders(db, amo_id=amo_id" in tenant_cycle
    assert "QMSAudit.amo_id == amo_id" in reminders


def test_manual_change_request_model_has_required_tenant_key() -> None:
    amo_column = quality_models.QMSManualChangeRequest.__table__.c.amo_id
    assert amo_column.nullable is False
    assert {foreign_key.target_fullname for foreign_key in amo_column.foreign_keys} == {"amos.id"}


def test_certified_backend_merge_is_the_single_alembic_head() -> None:
    config = Config(str(QUALITY_DIR.parents[1] / "alembic.ini"))
    scripts = ScriptDirectory.from_config(config)
    assert scripts.get_heads() == ["accounts_260907_access_profiles"]


def test_certified_backend_merge_repairs_orphan_times_and_removes_defaults(monkeypatch) -> None:
    migration = importlib.import_module(
        "amodb.alembic.versions.backend_20260906_certified_merge"
    )
    executed: list[str] = []
    altered: list[tuple[str, str, object]] = []
    monkeypatch.setattr(
        migration.op,
        "execute",
        lambda statement: executed.append(str(statement)),
    )
    monkeypatch.setattr(
        migration.op,
        "alter_column",
        lambda table, column, **kwargs: altered.append(
            (table, column, kwargs.get("server_default"))
        ),
    )

    migration.upgrade()

    assert any("planned_start IS NULL" in statement for statement in executed)
    assert any("planned_end IS NULL" in statement for statement in executed)
    assert altered == [
        ("qms_audits", "planned_start_time", None),
        ("qms_audits", "planned_end_time", None),
    ]


def test_qms13_migration_backfills_and_constrains_tenant(monkeypatch) -> None:
    migration = importlib.import_module(
        "amodb.alembic.versions.quality_20260902_qms13_tenant_gate"
    )
    engine = sa.create_engine("sqlite+pysqlite:///:memory:")
    with engine.begin() as connection:
        connection.exec_driver_sql("PRAGMA foreign_keys=ON")
        connection.exec_driver_sql("CREATE TABLE amos (id VARCHAR(36) PRIMARY KEY)")
        connection.exec_driver_sql(
            "CREATE TABLE users (id VARCHAR(36) PRIMARY KEY, amo_id VARCHAR(36))"
        )
        connection.exec_driver_sql(
            """
            CREATE TABLE qms_manual_change_requests (
                id VARCHAR(36) PRIMARY KEY,
                domain VARCHAR(30),
                status VARCHAR(30),
                submitted_at DATETIME,
                created_by_user_id VARCHAR(36)
            )
            """
        )
        connection.exec_driver_sql("INSERT INTO amos VALUES ('amo-a')")
        connection.exec_driver_sql("INSERT INTO users VALUES ('user-a', 'amo-a')")
        connection.exec_driver_sql(
            """
            INSERT INTO qms_manual_change_requests
                (id, domain, status, submitted_at, created_by_user_id)
            VALUES ('change-a', 'MAINTENANCE', 'SUBMITTED', CURRENT_TIMESTAMP, 'user-a')
            """
        )
        monkeypatch.setattr(
            migration,
            "op",
            Operations(MigrationContext.configure(connection)),
        )
        migration.upgrade()

        inspector = sa.inspect(connection)
        columns = {column["name"]: column for column in inspector.get_columns(migration.TABLE)}
        indexes = {index["name"] for index in inspector.get_indexes(migration.TABLE)}
        foreign_keys = {foreign_key["name"] for foreign_key in inspector.get_foreign_keys(migration.TABLE)}
        assert columns["amo_id"]["nullable"] is False
        assert connection.exec_driver_sql(
            "SELECT amo_id FROM qms_manual_change_requests WHERE id = 'change-a'"
        ).scalar_one() == "amo-a"
        assert {
            "ix_qms_manual_change_requests_amo_id",
            "ix_qms_cr_amo_domain_status",
            "ix_qms_cr_amo_submitted_at",
        } <= indexes
        assert migration.TENANT_FK in foreign_keys
