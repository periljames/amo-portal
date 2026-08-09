from __future__ import annotations

import os
import subprocess
from uuid import uuid4

import sqlalchemy as sa
from sqlalchemy import create_engine, text

BASE_REVISION = "quality_260808_intel_graph"
TARGET_REVISION = "quality_260809_audit_sources"
APP_ROLE = "amo_quality_audit_governance_probe"

TABLES = (
    "quality_audit_preparation_revisions",
    "quality_audit_preparation_events",
    "quality_audit_notice_policies",
    "quality_audit_notices",
    "quality_audit_notice_events",
    "quality_audit_checklist_templates",
    "quality_audit_checklist_template_revisions",
    "quality_audit_checklist_bindings",
    "quality_audit_report_revisions",
    "quality_audit_report_events",
    "quality_audit_closure_states",
    "quality_audit_closure_events",
    "quality_audit_deferrals",
    "quality_audit_deferral_events",
    "quality_audit_source_links",
)


def _run_alembic(*args: str) -> None:
    subprocess.run(["alembic", "-c", "amodb/alembic.ini", *args], check=True, env=os.environ.copy())


def _bootstrap(engine: sa.Engine) -> dict[str, str]:
    ids = {key: str(uuid4()) for key in (
        "amo_a", "amo_b", "user_a", "user_b", "audit_a", "schedule_a", "programme_a", "item_a"
    )}
    with engine.begin() as connection:
        connection.execute(text("DROP SCHEMA public CASCADE"))
        connection.execute(text("CREATE SCHEMA public"))
        connection.execute(text("GRANT ALL ON SCHEMA public TO public"))
        connection.execute(text("CREATE TABLE amos (id VARCHAR(36) PRIMARY KEY)"))
        connection.execute(text("CREATE TABLE users (id VARCHAR(36) PRIMARY KEY)"))
        connection.execute(text("CREATE TABLE qms_audits (id UUID PRIMARY KEY)"))
        connection.execute(text("CREATE TABLE qms_audit_schedules (id UUID PRIMARY KEY)"))
        connection.execute(text("CREATE TABLE quality_audit_programmes (id VARCHAR(36) PRIMARY KEY)"))
        connection.execute(text("CREATE TABLE quality_audit_programme_items (id VARCHAR(36) PRIMARY KEY)"))
        connection.execute(text("INSERT INTO amos (id) VALUES (:amo_a), (:amo_b)"), ids)
        connection.execute(text("INSERT INTO users (id) VALUES (:user_a), (:user_b)"), ids)
        connection.execute(text("INSERT INTO qms_audits (id) VALUES (:audit_a)"), ids)
        connection.execute(text("INSERT INTO qms_audit_schedules (id) VALUES (:schedule_a)"), ids)
        connection.execute(text("INSERT INTO quality_audit_programmes (id) VALUES (:programme_a)"), ids)
        connection.execute(text("INSERT INTO quality_audit_programme_items (id) VALUES (:item_a)"), ids)
        connection.execute(text(f"""DO $$ BEGIN IF NOT EXISTS (SELECT 1 FROM pg_roles WHERE rolname = '{APP_ROLE}')
            THEN CREATE ROLE {APP_ROLE} NOLOGIN; END IF; END $$"""))
    return ids


def _set_tenant(connection, amo_id: str, user_id: str) -> None:
    connection.execute(text("SELECT set_config('app.tenant_id', :v, true)"), {"v": amo_id})
    connection.execute(text("SELECT set_config('app.user_id', :v, true)"), {"v": user_id})


def _rls_state(connection, table: str) -> tuple[bool, bool]:
    row = connection.execute(text("""
        SELECT c.relrowsecurity, c.relforcerowsecurity
        FROM pg_class c JOIN pg_namespace n ON n.oid=c.relnamespace
        WHERE n.nspname=current_schema() AND c.relname=:table
    """), {"table": table}).one()
    return bool(row.relrowsecurity), bool(row.relforcerowsecurity)


def _blocked(engine: sa.Engine, ids: dict[str, str], sql: str, params: dict[str, str]) -> None:
    try:
        with engine.begin() as connection:
            connection.execute(text(f"SET LOCAL ROLE {APP_ROLE}"))
            _set_tenant(connection, ids["amo_a"], ids["user_a"])
            connection.execute(text(sql), params)
    except Exception:
        return
    raise AssertionError(f"Expected governed mutation to be blocked: {sql}")


def main() -> None:
    engine = create_engine(os.environ["DATABASE_URL"])
    ids = _bootstrap(engine)
    _run_alembic("stamp", BASE_REVISION)
    _run_alembic("upgrade", TARGET_REVISION)

    with engine.begin() as connection:
        assert connection.execute(text("SELECT version_num FROM alembic_version")).scalar_one() == TARGET_REVISION
        for table in TABLES:
            assert _rls_state(connection, table) == (True, True), table
            assert connection.execute(text("SELECT COUNT(*) FROM pg_policies WHERE schemaname=current_schema() AND tablename=:t"), {"t": table}).scalar_one() == 1, table
        connection.execute(text(f"GRANT USAGE ON SCHEMA public TO {APP_ROLE}"))
        connection.execute(text(f"GRANT SELECT, INSERT, UPDATE, DELETE ON ALL TABLES IN SCHEMA public TO {APP_ROLE}"))

    ids.update({key: str(uuid4()) for key in (
        "prep", "prep_event", "notice_policy", "notice", "notice_event", "template", "template_rev",
        "binding", "report", "report_event", "closure", "closure_event", "deferral", "deferral_event", "source_link"
    )})

    with engine.begin() as connection:
        connection.execute(text(f"SET LOCAL ROLE {APP_ROLE}"))
        _set_tenant(connection, ids["amo_a"], ids["user_a"])

        connection.execute(text("""INSERT INTO quality_audit_preparation_revisions
            (id,amo_id,audit_id,revision_no,status,audit_snapshot,checklist_snapshot,document_request_snapshot,source_references,source_fingerprint,change_reason,created_by_user_id,created_at,issued_by_user_id,issued_at)
            VALUES (:id,:amo,:audit,1,'ISSUED',CAST('{}' AS json),CAST('[]' AS json),CAST('[]' AS json),CAST('[]' AS json),:fingerprint,'Controlled snapshot',:user,NOW(),:user,NOW())"""),
            {"id": ids["prep"], "amo": ids["amo_a"], "audit": ids["audit_a"], "fingerprint": "a" * 64, "user": ids["user_a"]})
        connection.execute(text("""INSERT INTO quality_audit_preparation_events
            (id,amo_id,audit_id,revision_id,event_type,reason,actor_user_id,created_at)
            VALUES (:id,:amo,:audit,:revision,'ISSUED','Issued controlled snapshot',:user,NOW())"""),
            {"id": ids["prep_event"], "amo": ids["amo_a"], "audit": ids["audit_a"], "revision": ids["prep"], "user": ids["user_a"]})

        connection.execute(text("""INSERT INTO quality_audit_notice_policies
            (id,amo_id,policy_code,title,minimum_notice_days,review_required,acknowledgement_required,emergency_exception_allowed,unannounced_exception_allowed,is_active,created_by_user_id,updated_by_user_id,created_at,updated_at)
            VALUES (:id,:amo,'STANDARD_14_DAY','Standard notice',14,true,true,true,true,true,:user,:user,NOW(),NOW())"""),
            {"id": ids["notice_policy"], "amo": ids["amo_a"], "user": ids["user_a"]})
        connection.execute(text("""INSERT INTO quality_audit_notices
            (id,amo_id,audit_id,policy_id,revision_no,status,required_notice_days,notice_date,subject,body,audit_snapshot,recipient_snapshot,delivery_channel,delivery_reference,acknowledged_by_user_id,acknowledged_at,created_by_user_id,created_at,updated_at)
            VALUES (:id,:amo,:audit,:policy,1,'ACKNOWLEDGED',14,'2026-08-01','Probe notice','Controlled notice',CAST('{}' AS json),CAST('[]' AS json),'EMAIL','message-1',:user,NOW(),:user,NOW(),NOW())"""),
            {"id": ids["notice"], "amo": ids["amo_a"], "audit": ids["audit_a"], "policy": ids["notice_policy"], "user": ids["user_a"]})
        connection.execute(text("""INSERT INTO quality_audit_notice_events
            (id,amo_id,audit_id,notice_id,event_type,reason,after_snapshot,actor_user_id,created_at)
            VALUES (:id,:amo,:audit,:notice,'ACKNOWLEDGED','Acknowledged delivery',CAST('{}' AS json),:user,NOW())"""),
            {"id": ids["notice_event"], "amo": ids["amo_a"], "audit": ids["audit_a"], "notice": ids["notice"], "user": ids["user_a"]})

        connection.execute(text("""INSERT INTO quality_audit_checklist_templates
            (id,amo_id,template_code,title,status,created_by_user_id,updated_by_user_id,created_at,updated_at)
            VALUES (:id,:amo,'INT-AUDIT','Internal audit','ACTIVE',:user,:user,NOW(),NOW())"""),
            {"id": ids["template"], "amo": ids["amo_a"], "user": ids["user_a"]})
        connection.execute(text("""INSERT INTO quality_audit_checklist_template_revisions
            (id,amo_id,template_id,revision_no,status,items,source_references,content_sha256,change_reason,issued_by_user_id,issued_at,created_by_user_id,created_at)
            VALUES (:id,:amo,:template,1,'ISSUED',CAST('[{\"prompt\":\"Verify control\"}]' AS json),CAST('[]' AS json),:digest,'Initial issue',:user,NOW(),:user,NOW())"""),
            {"id": ids["template_rev"], "amo": ids["amo_a"], "template": ids["template"], "digest": "b" * 64, "user": ids["user_a"]})
        connection.execute(text("""INSERT INTO quality_audit_checklist_bindings
            (id,amo_id,audit_id,template_id,template_revision_id,template_code,revision_no,content_sha256,item_snapshot,source_references,instantiated_item_ids,application_reason,applied_by_user_id,applied_at)
            VALUES (:id,:amo,:audit,:template,:revision,'INT-AUDIT',1,:digest,CAST('[]' AS json),CAST('[]' AS json),CAST('[]' AS json),'Apply controlled template',:user,NOW())"""),
            {"id": ids["binding"], "amo": ids["amo_a"], "audit": ids["audit_a"], "template": ids["template"], "revision": ids["template_rev"], "digest": "b" * 64, "user": ids["user_a"]})

        connection.execute(text("""INSERT INTO quality_audit_report_revisions
            (id,amo_id,audit_id,revision_no,status,file_ref,filename,size_bytes,sha256,report_snapshot,change_reason,issued_by_user_id,issued_at,created_by_user_id,created_at,updated_at)
            VALUES (:id,:amo,:audit,1,'ISSUED','/controlled/report.pdf','report.pdf',100,:digest,CAST('{}' AS json),'Approved report',:user,NOW(),:user,NOW(),NOW())"""),
            {"id": ids["report"], "amo": ids["amo_a"], "audit": ids["audit_a"], "digest": "c" * 64, "user": ids["user_a"]})
        connection.execute(text("""INSERT INTO quality_audit_report_events
            (id,amo_id,audit_id,revision_id,event_type,reason,after_snapshot,actor_user_id,created_at)
            VALUES (:id,:amo,:audit,:revision,'ISSUED','Formal report issued',CAST('{}' AS json),:user,NOW())"""),
            {"id": ids["report_event"], "amo": ids["amo_a"], "audit": ids["audit_a"], "revision": ids["report"], "user": ids["user_a"]})

        connection.execute(text("""INSERT INTO quality_audit_closure_states
            (id,amo_id,audit_id,execution_status,execution_closed_by_user_id,execution_closed_at,execution_close_reason,execution_evidence_snapshot,follow_up_status,follow_up_evidence_snapshot,created_by_user_id,created_at,updated_at)
            VALUES (:id,:amo,:audit,'CLOSED',:user,NOW(),'Execution closed',CAST('{}' AS json),'OPEN',CAST('{}' AS json),:user,NOW(),NOW())"""),
            {"id": ids["closure"], "amo": ids["amo_a"], "audit": ids["audit_a"], "user": ids["user_a"]})
        connection.execute(text("""INSERT INTO quality_audit_closure_events
            (id,amo_id,audit_id,closure_state_id,event_type,reason,evidence_snapshot,actor_user_id,created_at)
            VALUES (:id,:amo,:audit,:state,'EXECUTION_CLOSED','Execution closure recorded',CAST('{}' AS json),:user,NOW())"""),
            {"id": ids["closure_event"], "amo": ids["amo_a"], "audit": ids["audit_a"], "state": ids["closure"], "user": ids["user_a"]})

        connection.execute(text("""INSERT INTO quality_audit_deferrals
            (id,amo_id,programme_id,programme_item_id,original_target_start,revised_target_start,reason,risk_rating,risk_assessment,mitigations,approval_required,repeated_deferral_count,status,requested_by_user_id,requested_at)
            VALUES (:id,:amo,:programme,:item,'2026-08-01','2026-08-15','Operational conflict','HIGH','Risk assessed and mitigated',CAST('[]' AS json),true,1,'REQUESTED',:user,NOW())"""),
            {"id": ids["deferral"], "amo": ids["amo_a"], "programme": ids["programme_a"], "item": ids["item_a"], "user": ids["user_a"]})
        connection.execute(text("""INSERT INTO quality_audit_deferral_events
            (id,amo_id,programme_item_id,deferral_id,event_type,reason,snapshot,actor_user_id,created_at)
            VALUES (:id,:amo,:item,:deferral,'REQUESTED','Governed deferral requested',CAST('{}' AS json),:user,NOW())"""),
            {"id": ids["deferral_event"], "amo": ids["amo_a"], "item": ids["item_a"], "deferral": ids["deferral"], "user": ids["user_a"]})

        connection.execute(text("""INSERT INTO quality_audit_source_links
            (id,amo_id,schedule_id,source_type,source_id,source_route,rationale,source_snapshot,created_by_user_id,created_at)
            VALUES (:id,:amo,:schedule,'MISSION','mission-probe','/quality?workspace=missions','Readiness surveillance',CAST('{}' AS json),:user,NOW())"""),
            {"id": ids["source_link"], "amo": ids["amo_a"], "schedule": ids["schedule_a"], "user": ids["user_a"]})

        for table in TABLES:
            assert connection.execute(text(f"SELECT COUNT(*) FROM {table}")).scalar_one() >= 1, table

    with engine.begin() as connection:
        connection.execute(text(f"SET LOCAL ROLE {APP_ROLE}"))
        _set_tenant(connection, ids["amo_b"], ids["user_b"])
        for table in TABLES:
            assert connection.execute(text(f"SELECT COUNT(*) FROM {table}")).scalar_one() == 0, table

    _blocked(engine, ids, "UPDATE quality_audit_preparation_revisions SET change_reason='mutated' WHERE id=:id", {"id": ids["prep"]})
    _blocked(engine, ids, "DELETE FROM quality_audit_preparation_events WHERE id=:id", {"id": ids["prep_event"]})
    _blocked(engine, ids, "UPDATE quality_audit_notices SET subject='mutated' WHERE id=:id", {"id": ids["notice"]})
    _blocked(engine, ids, "DELETE FROM quality_audit_notice_events WHERE id=:id", {"id": ids["notice_event"]})
    _blocked(engine, ids, "UPDATE quality_audit_checklist_template_revisions SET change_reason='mutated' WHERE id=:id", {"id": ids["template_rev"]})
    _blocked(engine, ids, "DELETE FROM quality_audit_checklist_bindings WHERE id=:id", {"id": ids["binding"]})
    _blocked(engine, ids, "UPDATE quality_audit_report_revisions SET filename='mutated.pdf' WHERE id=:id", {"id": ids["report"]})
    _blocked(engine, ids, "DELETE FROM quality_audit_report_events WHERE id=:id", {"id": ids["report_event"]})
    _blocked(engine, ids, "DELETE FROM quality_audit_closure_events WHERE id=:id", {"id": ids["closure_event"]})
    _blocked(engine, ids, "UPDATE quality_audit_deferral_events SET reason='mutated' WHERE id=:id", {"id": ids["deferral_event"]})
    _blocked(engine, ids, "UPDATE quality_audit_source_links SET rationale='mutated' WHERE id=:id", {"id": ids["source_link"]})

    print("Quality audit governance migrations, tenant RLS and immutable history probe passed")


if __name__ == "__main__":
    main()
