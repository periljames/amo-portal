"""Opt-in PostgreSQL regression checks; all writes use rolled-back temp tables.

Run with MOPM_POSTGRES_PROBE=1 and MOPM_POSTGRES_DATABASE_URL configured.
No persistent tenant, user, mission or evidence records are created.
"""
import os

import pytest
from fastapi import HTTPException
from sqlalchemy import text, create_engine
from sqlalchemy.orm import Session

pytestmark = pytest.mark.skipif(os.getenv("MOPM_POSTGRES_PROBE") != "1", reason="Opt-in PostgreSQL temporary-table probe")


@pytest.fixture
def isolated_changes():
    from amodb.apps.quality.tenant_security import TenantContext
    # The shared pytest harness deliberately replaces DATABASE_URL with SQLite.
    # Keep this explicit opt-in connection separate from the shared test engine.
    engine = create_engine(os.environ["MOPM_POSTGRES_DATABASE_URL"])
    assert engine.dialect.name == "postgresql"
    with engine.connect() as connection:
        transaction = connection.begin()
        try:
            connection.execute(text("CREATE TEMP TABLE users (id text,amo_id text,is_active boolean,is_system_account boolean) ON COMMIT DROP"))
            connection.execute(text("INSERT INTO users VALUES ('probe-owner','probe-amo',true,false)"))
            for table in ("quality_missions", "quality_mission_gates", "quality_mission_decisions"):
                connection.execute(text(f"CREATE TEMP TABLE {table} (LIKE public.{table} INCLUDING DEFAULTS) ON COMMIT DROP"))
            with Session(bind=connection, join_transaction_mode="create_savepoint") as db:
                yield db, TenantContext(amo_id="probe-amo", amo_code="probe", user_id="probe-owner", is_superuser=False)
        finally:
            transaction.rollback()
    engine.dispose()


@pytest.mark.parametrize("kind,total", [("CAPABILITY_ADDITION",11),("PROCEDURE_CHANGE",5),("CAPABILITY_CHANGE",5),("LINE_STATION",5),("REGULATORY_TRANSITION",5)])
def test_create_change_and_lock_readiness_gate_in_postgres(isolated_changes, kind, total):
    from amodb.apps.quality.mission_management_guard_router import create_governed_mission, update_governed_mission_gate
    from amodb.apps.quality.mission_router import GatePatch, MissionCreate, _load_mission

    db, ctx = isolated_changes
    created = create_governed_mission(MissionCreate(mission_type=kind,title="Isolated workflow check",description="Review scoped change evidence before implementation.",scope={"affected_scope":"MOPM procedure"}),ctx,db)
    assert created["readiness"]["hard_gates"] == {"passed":0,"total":total}
    gate_id = created["gates"][0]["id"]
    # This exact route formerly raised PostgreSQL's "FOR UPDATE cannot be
    # applied to the nullable side of an outer join" before validation ran.
    with pytest.raises(HTTPException) as error:
        update_governed_mission_gate(created["id"],gate_id,GatePatch(status="PASS"),ctx,db)
    assert error.value.status_code == 422
    updated = update_governed_mission_gate(created["id"],gate_id,GatePatch(status="IN_PROGRESS"),ctx,db)
    assert next(gate for gate in updated["gates"] if gate["id"]==gate_id)["status"] == "IN_PROGRESS"
    assert not updated["readiness"]["ready_for_quality_self_evaluation"]
    with pytest.raises(HTTPException) as error:
        _load_mission(db,amo_id="other-amo",mission_id=created["id"])
    assert error.value.status_code == 404
