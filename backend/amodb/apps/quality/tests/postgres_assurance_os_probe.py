from __future__ import annotations

import os
import subprocess
from uuid import uuid4

import sqlalchemy as sa
from sqlalchemy import create_engine, text

BASE_REVISION = "quality_260808_prog_schedule"
TARGET_REVISION = "quality_260809_audit_notice"
APP_ROLE = "amo_quality_os_probe"

TABLES = (
    "quality_privilege_rules",
    "quality_privileges",
    "quality_privilege_decisions",
    "quality_independence_declarations",
    "quality_assurance_cases",
    "quality_investigation_entries",
    "quality_effectiveness_plans",
    "quality_assurance_case_events",
    "quality_signal_rules",
    "quality_signal_observations",
    "quality_requirement_nodes",
    "quality_requirement_links",
    "quality_audit_preparation_revisions",
    "quality_audit_preparation_events",
    "quality_audit_notice_policies",
    "quality_audit_notices",
    "quality_audit_notice_events",
)


def _run_alembic(*args: str) -> None:
    subprocess.run(["alembic", "-c", "amodb/alembic.ini", *args], check=True, env=os.environ.copy())


def _bootstrap(engine: sa.Engine) -> dict[str, str]:
    ids = {key: str(uuid4()) for key in ("amo_a", "amo_b", "user_a", "user_b", "audit_a")}
    with engine.begin() as connection:
        connection.execute(text("DROP SCHEMA public CASCADE"))
        connection.execute(text("CREATE SCHEMA public"))
        connection.execute(text("GRANT ALL ON SCHEMA public TO public"))
        connection.execute(text("CREATE TABLE amos (id VARCHAR(36) PRIMARY KEY)"))
        connection.execute(text("CREATE TABLE users (id VARCHAR(36) PRIMARY KEY)"))
        connection.execute(text("CREATE TABLE qms_audits (id UUID PRIMARY KEY)"))
        connection.execute(text("INSERT INTO amos (id) VALUES (:amo_a), (:amo_b)"), ids)
        connection.execute(text("INSERT INTO users (id) VALUES (:user_a), (:user_b)"), ids)
        connection.execute(text("INSERT INTO qms_audits (id) VALUES (:audit_a)"), ids)
        connection.execute(text(f"""DO $$ BEGIN IF NOT EXISTS (SELECT 1 FROM pg_roles WHERE rolname = '{APP_ROLE}')
            THEN CREATE ROLE {APP_ROLE} NOLOGIN; END IF; END $$"""))
    return ids


def _set_tenant(connection, amo_id: str, user_id: str) -> None:
    connection.execute(text("SELECT set_config('app.tenant_id', :v, true)"), {"v": amo_id})
    connection.execute(text("SELECT set_config('app.user_id', :v, true)"), {"v": user_id})


def _rls_state(connection, table: str) -> tuple[bool, bool]:
    row = connection.execute(text("""SELECT c.relrowsecurity, c.relforcerowsecurity FROM pg_class c
        JOIN pg_namespace n ON n.oid=c.relnamespace WHERE n.nspname=current_schema() AND c.relname=:table"""), {"table": table}).one()
    return bool(row.relrowsecurity), bool(row.relforcerowsecurity)


def _expect_blocked(engine: sa.Engine, ids: dict[str, str], statement: str, params: dict | None = None) -> None:
    try:
        with engine.begin() as connection:
            connection.execute(text(f"SET LOCAL ROLE {APP_ROLE}"))
            _set_tenant(connection, ids["amo_a"], ids["user_a"])
            connection.execute(text(statement), params or {})
    except Exception:
        return
    raise AssertionError(f"Expected immutable mutation to be blocked: {statement}")


def main() -> None:
    engine = create_engine(os.environ["DATABASE_URL"])
    ids = _bootstrap(engine)
    _run_alembic("stamp", BASE_REVISION)
    _run_alembic("upgrade", TARGET_REVISION)

    with engine.begin() as connection:
        assert connection.execute(text("SELECT version_num FROM alembic_version")).scalar_one() == TARGET_REVISION
        for table in TABLES:
            assert _rls_state(connection, table) == (True, True)
            assert connection.execute(text("SELECT COUNT(*) FROM pg_policies WHERE schemaname=current_schema() AND tablename=:t"), {"t": table}).scalar_one() == 1
        connection.execute(text(f"GRANT USAGE ON SCHEMA public TO {APP_ROLE}"))
        connection.execute(text(f"GRANT SELECT, INSERT, UPDATE, DELETE ON ALL TABLES IN SCHEMA public TO {APP_ROLE}"))

    ids.update({key: str(uuid4()) for key in (
        "rule", "privilege", "decision", "independence", "case", "entry", "plan", "case_event",
        "signal_rule", "observation", "node_a", "node_b", "link", "prep", "prep_event",
        "notice_policy", "notice", "notice_event",
    )})

    with engine.begin() as connection:
        connection.execute(text(f"SET LOCAL ROLE {APP_ROLE}"))
        _set_tenant(connection, ids["amo_a"], ids["user_a"])
        connection.execute(text("""INSERT INTO quality_privilege_rules
            (id,amo_id,privilege_code,title,privilege_type,required_training_course_codes,independence_required,scope_schema,is_active,created_by_user_id,updated_by_user_id,created_at,updated_at)
            VALUES (:id,:amo,'LEAD_AUDITOR','Lead auditor','LEAD_AUDITOR',CAST('[]' AS json),true,CAST('{}' AS json),true,:user,:user,NOW(),NOW())"""),
            {"id": ids["rule"], "amo": ids["amo_a"], "user": ids["user_a"]})
        connection.execute(text("""INSERT INTO quality_privileges
            (id,amo_id,rule_id,user_id,privilege_code,scope_key,scope,limitations,status,effective_from,created_by_user_id,updated_by_user_id,created_at,updated_at)
            VALUES (:id,:amo,:rule,:user,'LEAD_AUDITOR','GLOBAL',CAST('{}' AS json),CAST('[]' AS json),'ACTIVE','2026-01-01',:user,:user,NOW(),NOW())"""),
            {"id": ids["privilege"], "amo": ids["amo_a"], "rule": ids["rule"], "user": ids["user_a"]})
        connection.execute(text("""INSERT INTO quality_privilege_decisions
            (id,amo_id,privilege_id,decision_type,resulting_status,rationale,eligibility_snapshot,source_references,effective_from,decided_by_user_id,decided_at,created_at)
            VALUES (:id,:amo,:privilege,'GRANT','ACTIVE','Verified eligibility',CAST('{}' AS json),CAST('[]' AS json),'2026-01-01',:user,NOW(),NOW())"""),
            {"id": ids["decision"], "amo": ids["amo_a"], "privilege": ids["privilege"], "user": ids["user_a"]})
        connection.execute(text("UPDATE quality_privileges SET latest_decision_id=:decision WHERE id=:privilege"), {"decision": ids["decision"], "privilege": ids["privilege"]})
        connection.execute(text("""INSERT INTO quality_independence_declarations
            (id,amo_id,user_id,context_type,context_id,declaration,rationale,source_references,declared_by_user_id,declared_at,created_at)
            VALUES (:id,:amo,:user,'AUDIT',:audit,'INDEPENDENT','No involvement in audited activity',CAST('[]' AS json),:user,NOW(),NOW())"""),
            {"id": ids["independence"], "amo": ids["amo_a"], "user": ids["user_a"], "audit": ids["audit_a"]})

        connection.execute(text("""INSERT INTO quality_assurance_cases
            (id,amo_id,case_ref,case_type,title,severity,status,source_references,regulatory_basis,owner_user_id,opened_at,created_by_user_id,updated_by_user_id,created_at,updated_at)
            VALUES (:id,:amo,'ASC-PROBE','INVESTIGATION','Probe case','HIGH','INVESTIGATING',CAST('[]' AS json),CAST('[]' AS json),:user,NOW(),:user,:user,NOW(),NOW())"""),
            {"id": ids["case"], "amo": ids["amo_a"], "user": ids["user_a"]})
        connection.execute(text("""INSERT INTO quality_investigation_entries
            (id,amo_id,case_id,method,entry_type,sequence_no,statement,evidence_references,created_by_user_id,created_at)
            VALUES (:id,:amo,:case,'FIVE_WHYS','FACT',1,'Verified source fact',CAST('[{\"source\":\"probe\"}]' AS json),:user,NOW())"""),
            {"id": ids["entry"], "amo": ids["amo_a"], "case": ids["case"], "user": ids["user_a"]})
        connection.execute(text("""INSERT INTO quality_effectiveness_plans
            (id,amo_id,case_id,expected_outcome,effectiveness_measure,verification_method,source_indicators,responsible_reviewer_user_id,planned_review_date,status,conclusion_evidence,created_by_user_id,created_at,updated_at)
            VALUES (:id,:amo,:case,'No repeat finding during observation','Zero recurrence in targeted sample','Review follow-up audit evidence',CAST('[]' AS json),:user,'2026-12-31','PLANNED',CAST('[]' AS json),:user,NOW(),NOW())"""),
            {"id": ids["plan"], "amo": ids["amo_a"], "case": ids["case"], "user": ids["user_a"]})
        connection.execute(text("""INSERT INTO quality_assurance_case_events
            (id,amo_id,case_id,event_type,reason,after_snapshot,actor_user_id,created_at)
            VALUES (:id,:amo,:case,'CREATED','Case opened for probe',CAST('{}' AS json),:user,NOW())"""),
            {"id": ids["case_event"], "amo": ids["amo_a"], "case": ids["case"], "user": ids["user_a"]})

        connection.execute(text("""INSERT INTO quality_signal_rules
            (id,amo_id,rule_code,title,metric,operator,threshold,severity,explanation,source_contract,is_active,created_by_user_id,updated_by_user_id,created_at,updated_at)
            VALUES (:id,:amo,'OPEN_CASES','Open cases','OPEN_ASSURANCE_CASES','GT',0,'WATCH','Surface open assurance cases',CAST('{}' AS json),true,:user,:user,NOW(),NOW())"""),
            {"id": ids["signal_rule"], "amo": ids["amo_a"], "user": ids["user_a"]})
        connection.execute(text("""INSERT INTO quality_signal_observations
            (id,amo_id,rule_id,metric,observed_value,threshold,operator,triggered,severity,explanation,source_snapshot,source_references,as_of,state,observed_by_user_id,observed_at)
            VALUES (:id,:amo,:rule,'OPEN_ASSURANCE_CASES',1,0,'GT',true,'WATCH','One open case',CAST('{}' AS json),CAST('[]' AS json),NOW(),'OPEN',:user,NOW())"""),
            {"id": ids["observation"], "amo": ids["amo_a"], "rule": ids["signal_rule"], "user": ids["user_a"]})
        for node_id, node_type, title, source_id, state in (
            (ids["node_a"], "REQUIREMENT", "Requirement A", "REQ-A", "SUPPORTED"),
            (ids["node_b"], "PROCEDURE", "Procedure B", "PROC-B", "STALE"),
        ):
            connection.execute(text("""INSERT INTO quality_requirement_nodes
                (id,amo_id,node_type,title,source_owner_module,source_type,source_id,support_state,state_reason,created_by_user_id,updated_by_user_id,created_at,updated_at)
                VALUES (:id,:amo,:node_type,:title,'DMS','CONTROLLED_DOCUMENT',:source_id,:state,'Probe evidence state',:user,:user,NOW(),NOW())"""),
                {"id": node_id, "amo": ids["amo_a"], "node_type": node_type, "title": title, "source_id": source_id, "state": state, "user": ids["user_a"]})
        connection.execute(text("""INSERT INTO quality_requirement_links
            (id,amo_id,from_node_id,to_node_id,relationship,rationale,evidence_references,created_by_user_id,created_at)
            VALUES (:id,:amo,:from_id,:to_id,'IMPLEMENTS','Procedure implements requirement',CAST('[]' AS json),:user,NOW())"""),
            {"id": ids["link"], "amo": ids["amo_a"], "from_id": ids["node_a"], "to_id": ids["node_b"], "user": ids["user_a"]})

        connection.execute(text("""INSERT INTO quality_audit_preparation_revisions
            (id,amo_id,audit_id,revision_no,status,audit_snapshot,checklist_snapshot,document_request_snapshot,source_references,source_fingerprint,change_reason,created_by_user_id,created_at)
            VALUES (:id,:amo,:audit,1,'DRAFT',CAST('{}' AS json),CAST('[]' AS json),CAST('[]' AS json),CAST('[]' AS json),:fingerprint,'Initial controlled snapshot',:user,NOW())"""),
            {"id": ids["prep"], "amo": ids["amo_a"], "audit": ids["audit_a"], "fingerprint": "a" * 64, "user": ids["user_a"]})
        connection.execute(text("""INSERT INTO quality_audit_preparation_events
            (id,amo_id,audit_id,revision_id,event_type,reason,actor_user_id,created_at)
            VALUES (:id,:amo,:audit,:revision,'CREATED','Preparation snapshot created',:user,NOW())"""),
            {"id": ids["prep_event"], "amo": ids["amo_a"], "audit": ids["audit_a"], "revision": ids["prep"], "user": ids["user_a"]})

        connection.execute(text("""INSERT INTO quality_audit_notice_policies
            (id,amo_id,policy_code,title,minimum_notice_days,review_required,acknowledgement_required,emergency_exception_allowed,unannounced_exception_allowed,is_active,created_by_user_id,updated_by_user_id,created_at,updated_at)
            VALUES (:id,:amo,'STANDARD_14_DAY','Standard audit notice',14,true,true,true,true,true,:user,:user,NOW(),NOW())"""),
            {"id": ids["notice_policy"], "amo": ids["amo_a"], "user": ids["user_a"]})
        connection.execute(text("""INSERT INTO quality_audit_notices
            (id,amo_id,audit_id,policy_id,revision_no,status,required_notice_days,notice_date,subject,body,audit_snapshot,recipient_snapshot,delivery_channel,delivery_reference,acknowledged_by_user_id,acknowledged_at,created_by_user_id,created_at,updated_at)
            VALUES (:id,:amo,:audit,:policy,1,'ACKNOWLEDGED',14,'2026-08-01','Probe notice','Controlled notice',CAST('{}' AS json),CAST('[]' AS json),'EMAIL','probe-message-id',:user,NOW(),:user,NOW(),NOW())"""),
            {"id": ids["notice"], "amo": ids["amo_a"], "audit": ids["audit_a"], "policy": ids["notice_policy"], "user": ids["user_a"]})
        connection.execute(text("""INSERT INTO quality_audit_notice_events
            (id,amo_id,audit_id,notice_id,event_type,reason,after_snapshot,actor_user_id,created_at)
            VALUES (:id,:amo,:audit,:notice,'ACKNOWLEDGED','Recipient acknowledgement recorded',CAST('{}' AS json),:user,NOW())"""),
            {"id": ids["notice_event"], "amo": ids["amo_a"], "audit": ids["audit_a"], "notice": ids["notice"], "user": ids["user_a"]})

        for table in TABLES:
            assert connection.execute(text(f"SELECT COUNT(*) FROM {table}")).scalar_one() >= 1

        connection.execute(text("UPDATE quality_audit_preparation_revisions SET status='ISSUED',issued_by_user_id=:user,issued_at=NOW() WHERE id=:id"), {"user": ids["user_a"], "id": ids["prep"]})

    with engine.begin() as connection:
        connection.execute(text(f"SET LOCAL ROLE {APP_ROLE}"))
        _set_tenant(connection, ids["amo_b"], ids["user_b"])
        for table in TABLES:
            assert connection.execute(text(f"SELECT COUNT(*) FROM {table}")).scalar_one() == 0
        assert connection.execute(text("UPDATE quality_assurance_cases SET severity='LOW' WHERE id=:id"), {"id": ids["case"]}).rowcount == 0
        assert connection.execute(text("DELETE FROM quality_requirement_links WHERE id=:id"), {"id": ids["link"]}).rowcount == 0

    _expect_blocked(engine, ids, "UPDATE quality_privilege_decisions SET rationale='mutated' WHERE id=:id", {"id": ids["decision"]})
    _expect_blocked(engine, ids, "DELETE FROM quality_independence_declarations WHERE id=:id", {"id": ids["independence"]})
    _expect_blocked(engine, ids, "UPDATE quality_investigation_entries SET statement='mutated' WHERE id=:id", {"id": ids["entry"]})
    _expect_blocked(engine, ids, "DELETE FROM quality_assurance_case_events WHERE id=:id", {"id": ids["case_event"]})
    _expect_blocked(engine, ids, "UPDATE quality_signal_observations SET explanation='mutated' WHERE id=:id", {"id": ids["observation"]})
    _expect_blocked(engine, ids, "DELETE FROM quality_requirement_links WHERE id=:id", {"id": ids["link"]})
    _expect_blocked(engine, ids, "UPDATE quality_audit_preparation_revisions SET change_reason='mutated' WHERE id=:id", {"id": ids["prep"]})
    _expect_blocked(engine, ids, "DELETE FROM quality_audit_preparation_events WHERE id=:id", {"id": ids["prep_event"]})
    _expect_blocked(engine, ids, "UPDATE quality_audit_notices SET subject='mutated' WHERE id=:id", {"id": ids["notice"]})
    _expect_blocked(engine, ids, "DELETE FROM quality_audit_notice_events WHERE id=:id", {"id": ids["notice_event"]})

    print("Quality assurance operating system, audit preparation and notice RLS/immutability probe passed")


if __name__ == "__main__":
    main()
