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
            connection.execute(text("CREATE TEMP TABLE document_evidence_assets (id text,tenant_id text,filename text,sha256 text,size_bytes bigint,category text,created_at timestamptz) ON COMMIT DROP"))
            connection.execute(text("CREATE TEMP TABLE document_retention_dispositions (tenant_id text,source_type text,source_id text,status text) ON COMMIT DROP"))
            connection.execute(text("INSERT INTO document_evidence_assets VALUES ('proof','probe-amo','Reviewed change.pdf',:hash,20,'AUTHORITY',now())"), {"hash": "a" * 64})
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


def _queue(db, ctx, view):
    from amodb.apps.quality.mission_router import list_missions
    return list_missions(mission_type=None,status_filter=None,owner_user_id=None,limit=25,offset=0,view=view,ctx=ctx,db=db)["items"]


def _ready_change(db, ctx, *, authority=True, notification=True, address=False):
    from amodb.apps.quality.mission_management_guard_router import create_governed_mission, update_governed_mission_gate
    from amodb.apps.quality.mission_router import MissionCreate, GatePatch
    change = create_governed_mission(MissionCreate(mission_type="PROCEDURE_CHANGE",title="Isolated approval lifecycle",description="Change the governed maintenance procedure.",sponsor_user_id=ctx.user_id,
        scope={"affected_scope":"MOPM procedure", "authority_policy":{"approval_required":authority,"notification_required":notification,"physical_address_change":address,"justification":"Applicability assessed against MOPM section 1.9."}}),ctx,db)
    for gate in change["gates"]:
        change = update_governed_mission_gate(change["id"],gate["id"],GatePatch(status="PASS",evidence_status="VERIFIED",source_type="DOCUMENT_EVIDENCE",source_id="proof",source_snapshot={"review_note":"Reviewed current evidence against this readiness requirement."}),ctx,db)
    return change


def _decide(db, ctx, change, stage, outcome="APPROVED", **extra):
    from amodb.apps.quality.mission_lifecycle_guard_router import record_governed_mission_decision
    from amodb.apps.quality.mission_router import MissionDecisionCreate
    return record_governed_mission_decision(change["id"],MissionDecisionCreate(decision_type=stage,status=outcome,rationale="Documented review and decision rationale.",evidence_asset_id="proof",**extra),ctx,db)


@pytest.mark.parametrize("authority,notification", [(True,True),(False,True),(False,False)])
def test_full_approval_implementation_and_closure_in_postgres(isolated_changes, authority, notification):
    from datetime import datetime, timezone
    from amodb.apps.quality.mission_lifecycle_guard_router import MissionImplementation, record_mission_implementation, record_mission_effectiveness
    db, ctx = isolated_changes
    change = _ready_change(db,ctx,authority=authority,notification=notification)
    assert len(_queue(db,ctx,"pending-approval")) == 1
    change = _decide(db,ctx,change,"QUALITY_SELF_EVALUATION")
    change = _decide(db,ctx,change,"ACCOUNTABLE_EXECUTIVE")
    if notification:
        change = _decide(db,ctx,change,"AUTHORITY_SUBMISSION",notified_on=datetime.now(timezone.utc).date())
    if authority:
        change = _decide(db,ctx,change,"AUTHORITY_ACCEPTANCE")
    assert change["next_action"] == "IMPLEMENTATION"
    assert change["status"] != "COMPLETE"
    assert not _queue(db,ctx,"pending-approval")
    assert not _queue(db,ctx,"implemented")
    payload = MissionImplementation(rationale="Implementation completed within the recorded conditions.",evidence_asset_id="proof",effective_date=datetime.now(timezone.utc).date(),conditions_satisfied=True)
    with pytest.raises(HTTPException) as error:
        record_mission_effectiveness(change["id"],payload,ctx,db)
    assert error.value.status_code == 409
    change = record_mission_implementation(change["id"],payload,ctx,db)
    assert change["next_action"] == "EFFECTIVENESS_REVIEW" and change["status"] != "COMPLETE"
    assert len(_queue(db,ctx,"implemented")) == 1
    with pytest.raises(HTTPException) as error:
        record_mission_implementation(change["id"],payload,ctx,db)
    assert error.value.status_code == 409
    change = record_mission_effectiveness(change["id"],payload,ctx,db)
    assert change["status"] == "COMPLETE" and change["next_action"] is None
    assert len(change["decisions"]) == 4 + int(notification) + int(authority)


def test_return_requires_fresh_readiness_and_reapproval_in_postgres(isolated_changes):
    from amodb.apps.quality.mission_router import GatePatch
    from amodb.apps.quality.mission_management_guard_router import update_governed_mission_gate
    db, ctx = isolated_changes
    change = _ready_change(db,ctx)
    change = _decide(db,ctx,change,"QUALITY_SELF_EVALUATION")
    change = _decide(db,ctx,change,"ACCOUNTABLE_EXECUTIVE","RETURNED")
    assert len(_queue(db,ctx,"rejected")) == 1
    assert change["status"] == "IN_PROGRESS" and all(g["status"] == "PENDING" for g in change["gates"])
    with pytest.raises(HTTPException):
        _decide(db,ctx,change,"ACCOUNTABLE_EXECUTIVE")
    for gate in change["gates"]:
        change = update_governed_mission_gate(change["id"],gate["id"],GatePatch(status="PASS",evidence_status="VERIFIED"),ctx,db)
    change = _decide(db,ctx,change,"QUALITY_SELF_EVALUATION")
    assert not _queue(db,ctx,"rejected")
    assert change["next_action"] == "ACCOUNTABLE_EXECUTIVE"


def test_disposed_evidence_blocks_approval_in_postgres(isolated_changes):
    db, ctx = isolated_changes
    change = _ready_change(db,ctx)
    db.execute(text("INSERT INTO document_retention_dispositions VALUES ('probe-amo','EVIDENCE_ASSET','proof','DISPOSED')"))
    with pytest.raises(HTTPException) as error:
        _decide(db,ctx,change,"QUALITY_SELF_EVALUATION")
    assert error.value.status_code == 422


def test_stale_writes_and_unassigned_approvers_are_rejected(isolated_changes):
    from dataclasses import replace
    from datetime import datetime, timezone, timedelta
    from amodb.apps.quality.mission_management_guard_router import update_mission_metadata, MissionPatch
    db, ctx = isolated_changes
    change = _ready_change(db,ctx)
    with pytest.raises(HTTPException) as error:
        update_mission_metadata(change["id"],MissionPatch(title="Stale overwrite attempt",expected_updated_at=datetime.now(timezone.utc)-timedelta(days=1)),ctx,db)
    assert error.value.status_code == 409
    change = _decide(db,ctx,change,"QUALITY_SELF_EVALUATION")
    wrong_actor = replace(ctx,user_id="not-the-executive")
    with pytest.raises(HTTPException) as error:
        _decide(db,wrong_actor,change,"ACCOUNTABLE_EXECUTIVE")
    assert error.value.status_code == 403
