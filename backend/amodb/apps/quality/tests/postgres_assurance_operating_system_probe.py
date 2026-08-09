from __future__ import annotations

import os
import subprocess
from uuid import uuid4

import sqlalchemy as sa
from sqlalchemy import create_engine, text
from sqlalchemy.exc import DBAPIError

BASE_REVISION = "quality_260808_prog_schedule"
TARGET_REVISION = "quality_260808_intel_graph"
APP_ROLE = "amo_quality_assurance_os_probe"

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
)

APPEND_ONLY_TABLES = (
    "quality_privilege_decisions",
    "quality_independence_declarations",
    "quality_investigation_entries",
    "quality_assurance_case_events",
    "quality_signal_observations",
    "quality_requirement_links",
)


def _run_alembic(*args: str) -> None:
    subprocess.run(["alembic", "-c", "amodb/alembic.ini", *args], check=True, env=os.environ.copy())


def _bootstrap(engine: sa.Engine) -> dict[str, str]:
    ids = {key: str(uuid4()) for key in ("amo_a", "amo_b", "user_a", "user_b")}
    with engine.begin() as connection:
        connection.execute(text("DROP SCHEMA public CASCADE"))
        connection.execute(text("CREATE SCHEMA public"))
        connection.execute(text("GRANT ALL ON SCHEMA public TO public"))
        connection.execute(text("CREATE TABLE amos (id VARCHAR(36) PRIMARY KEY)"))
        connection.execute(text("CREATE TABLE users (id VARCHAR(36) PRIMARY KEY)"))
        connection.execute(text("INSERT INTO amos (id) VALUES (:amo_a), (:amo_b)"), ids)
        connection.execute(text("INSERT INTO users (id) VALUES (:user_a), (:user_b)"), ids)
        connection.execute(text(f"""DO $$ BEGIN IF NOT EXISTS (SELECT 1 FROM pg_roles WHERE rolname = '{APP_ROLE}')
            THEN CREATE ROLE {APP_ROLE} NOLOGIN; END IF; END $$"""))
    return ids


def _set_tenant(connection, amo_id: str, user_id: str) -> None:
    connection.execute(text("SELECT set_config('app.tenant_id', :v, true)"), {"v": amo_id})
    connection.execute(text("SELECT set_config('app.user_id', :v, true)"), {"v": user_id})


def _rls_state(connection, table_name: str) -> tuple[bool, bool]:
    row = connection.execute(text("""
        SELECT c.relrowsecurity, c.relforcerowsecurity
        FROM pg_class c JOIN pg_namespace n ON n.oid=c.relnamespace
        WHERE n.nspname=current_schema() AND c.relname=:table
    """), {"table": table_name}).one()
    return bool(row.relrowsecurity), bool(row.relforcerowsecurity)


def _assert_append_only(engine: sa.Engine, ids: dict[str, str], table_name: str, row_id: str) -> None:
    try:
        with engine.begin() as connection:
            connection.execute(text(f"SET LOCAL ROLE {APP_ROLE}"))
            _set_tenant(connection, ids["amo_a"], ids["user_a"])
            connection.execute(text(f"UPDATE {table_name} SET id=id WHERE id=:id"), {"id": row_id})
    except DBAPIError as exc:
        assert "append-only" in str(exc).lower()
    else:
        raise AssertionError(f"{table_name} accepted an UPDATE despite append-only governance")


def main() -> None:
    engine = create_engine(os.environ["DATABASE_URL"])
    ids = _bootstrap(engine)
    _run_alembic("stamp", BASE_REVISION)
    _run_alembic("upgrade", TARGET_REVISION)

    with engine.begin() as connection:
        assert connection.execute(text("SELECT version_num FROM alembic_version")).scalar_one() == TARGET_REVISION
        for table_name in TABLES:
            assert _rls_state(connection, table_name) == (True, True), table_name
            policy_count = connection.execute(text("""
                SELECT COUNT(*) FROM pg_policies
                WHERE schemaname=current_schema() AND tablename=:table
            """), {"table": table_name}).scalar_one()
            assert policy_count == 1, table_name
        connection.execute(text(f"GRANT USAGE ON SCHEMA public TO {APP_ROLE}"))
        connection.execute(text(f"GRANT SELECT, INSERT, UPDATE, DELETE ON ALL TABLES IN SCHEMA public TO {APP_ROLE}"))

    row_ids = {name: str(uuid4()) for name in (
        "rule", "privilege", "decision", "independence", "case", "investigation", "effectiveness",
        "case_event", "signal_rule", "observation", "node_a", "node_b", "link",
    )}

    with engine.begin() as connection:
        connection.execute(text(f"SET LOCAL ROLE {APP_ROLE}"))
        _set_tenant(connection, ids["amo_a"], ids["user_a"])
        connection.execute(text("""INSERT INTO quality_privilege_rules
            (id,amo_id,privilege_code,title,privilege_type,required_training_course_codes,independence_required,scope_schema,is_active,created_by_user_id,updated_by_user_id,created_at,updated_at)
            VALUES (:id,:amo,'AUDITOR_INTERNAL','Internal auditor','AUDITOR',CAST('[]' AS json),true,CAST('{}' AS json),true,:user,:user,NOW(),NOW())"""),
            {"id": row_ids["rule"], "amo": ids["amo_a"], "user": ids["user_a"]})
        connection.execute(text("""INSERT INTO quality_privileges
            (id,amo_id,rule_id,user_id,privilege_code,scope_key,scope,limitations,status,created_by_user_id,updated_by_user_id,created_at,updated_at)
            VALUES (:id,:amo,:rule,:user,'AUDITOR_INTERNAL','GLOBAL',CAST('{}' AS json),CAST('[]' AS json),'DRAFT',:user,:user,NOW(),NOW())"""),
            {"id": row_ids["privilege"], "amo": ids["amo_a"], "rule": row_ids["rule"], "user": ids["user_a"]})
        connection.execute(text("""INSERT INTO quality_privilege_decisions
            (id,amo_id,privilege_id,decision_type,resulting_status,rationale,eligibility_snapshot,source_references,decided_by_user_id,decided_at,created_at)
            VALUES (:id,:amo,:privilege,'GRANT','ACTIVE','Verified governed source eligibility.',CAST('{}' AS json),CAST('[]' AS json),:user,NOW(),NOW())"""),
            {"id": row_ids["decision"], "amo": ids["amo_a"], "privilege": row_ids["privilege"], "user": ids["user_a"]})
        connection.execute(text("UPDATE quality_privileges SET status='ACTIVE',latest_decision_id=:decision WHERE id=:id"), {"decision": row_ids["decision"], "id": row_ids["privilege"]})
        connection.execute(text("""INSERT INTO quality_independence_declarations
            (id,amo_id,user_id,context_type,context_id,declaration,rationale,source_references,declared_by_user_id,declared_at,created_at)
            VALUES (:id,:amo,:user,'AUDIT_SCHEDULE','schedule-probe','INDEPENDENT','No operational responsibility for audited scope.',CAST('[]' AS json),:user,NOW(),NOW())"""),
            {"id": row_ids["independence"], "amo": ids["amo_a"], "user": ids["user_a"]})

        connection.execute(text("""INSERT INTO quality_assurance_cases
            (id,amo_id,case_ref,case_type,title,severity,status,source_references,regulatory_basis,owner_user_id,opened_at,created_by_user_id,updated_by_user_id,created_at,updated_at)
            VALUES (:id,:amo,'ASC-26-PROBE','INVESTIGATION','Probe assurance case','HIGH','INVESTIGATING',CAST('[]' AS json),CAST('[]' AS json),:user,NOW(),:user,:user,NOW(),NOW())"""),
            {"id": row_ids["case"], "amo": ids["amo_a"], "user": ids["user_a"]})
        connection.execute(text("""INSERT INTO quality_investigation_entries
            (id,amo_id,case_id,method,entry_type,sequence_no,statement,evidence_references,created_by_user_id,created_at)
            VALUES (:id,:amo,:case,'FIVE_WHYS','FACT',1,'Verified source fact.',CAST('[{"source":"probe"}]' AS json),:user,NOW())"""),
            {"id": row_ids["investigation"], "amo": ids["amo_a"], "case": row_ids["case"], "user": ids["user_a"]})
        connection.execute(text("""INSERT INTO quality_effectiveness_plans
            (id,amo_id,case_id,expected_outcome,effectiveness_measure,verification_method,source_indicators,planned_review_date,status,conclusion_evidence,created_by_user_id,created_at,updated_at)
            VALUES (:id,:amo,:case,'No recurrence during observation window.','Zero repeated findings.','Review authoritative audit findings.',CAST('[]' AS json),CURRENT_DATE + 30,'PLANNED',CAST('[]' AS json),:user,NOW(),NOW())"""),
            {"id": row_ids["effectiveness"], "amo": ids["amo_a"], "case": row_ids["case"], "user": ids["user_a"]})
        connection.execute(text("""INSERT INTO quality_assurance_case_events
            (id,amo_id,case_id,event_type,reason,after_snapshot,actor_user_id,created_at)
            VALUES (:id,:amo,:case,'INVESTIGATION_ADDED','Source fact recorded.',CAST('{}' AS json),:user,NOW())"""),
            {"id": row_ids["case_event"], "amo": ids["amo_a"], "case": row_ids["case"], "user": ids["user_a"]})

        connection.execute(text("""INSERT INTO quality_signal_rules
            (id,amo_id,rule_code,title,metric,operator,threshold,severity,explanation,source_contract,is_active,created_by_user_id,updated_by_user_id,created_at,updated_at)
            VALUES (:id,:amo,'OVERDUE_CARS_PRESENT','Overdue CARs present','OVERDUE_CAR_COUNT','GT',0,'WARNING','Trigger when any open CAR is overdue.',CAST('{}' AS json),true,:user,:user,NOW(),NOW())"""),
            {"id": row_ids["signal_rule"], "amo": ids["amo_a"], "user": ids["user_a"]})
        connection.execute(text("""INSERT INTO quality_signal_observations
            (id,amo_id,rule_id,metric,observed_value,threshold,operator,triggered,severity,explanation,source_snapshot,source_references,as_of,state,observed_by_user_id,observed_at)
            VALUES (:id,:amo,:rule,'OVERDUE_CAR_COUNT',1,0,'GT',true,'WARNING','Observed 1 GT threshold 0.',CAST(:source_snapshot AS json),CAST('[]' AS json),NOW(),'OPEN',:user,NOW())"""),
            {"id": row_ids["observation"], "amo": ids["amo_a"], "rule": row_ids["signal_rule"], "user": ids["user_a"], "source_snapshot": '{"count":1}'})
        for key, node_type, title, source_type, source_id, state in (
            ("node_a", "REQUIREMENT", "KCAR requirement", "REGULATION_CLAUSE", "KCAR-PROBE", "SUPPORTED"),
            ("node_b", "MANUAL", "MPM procedure", "CONTROLLED_DOCUMENT", "MPM-PROBE", "UNRESOLVED"),
        ):
            connection.execute(text("""INSERT INTO quality_requirement_nodes
                (id,amo_id,node_type,title,source_owner_module,source_type,source_id,support_state,state_reason,created_by_user_id,updated_by_user_id,created_at,updated_at)
                VALUES (:id,:amo,:node_type,:title,'document-control',:source_type,:source_id,:state,'Probe evidence state is explicitly attributable.',:user,:user,NOW(),NOW())"""),
                {"id": row_ids[key], "amo": ids["amo_a"], "node_type": node_type, "title": title, "source_type": source_type, "source_id": source_id, "state": state, "user": ids["user_a"]})
        connection.execute(text("""INSERT INTO quality_requirement_links
            (id,amo_id,from_node_id,to_node_id,relationship,rationale,evidence_references,created_by_user_id,created_at)
            VALUES (:id,:amo,:from_node,:to_node,'IMPLEMENTS','Manual procedure implements the requirement.',CAST('[]' AS json),:user,NOW())"""),
            {"id": row_ids["link"], "amo": ids["amo_a"], "from_node": row_ids["node_a"], "to_node": row_ids["node_b"], "user": ids["user_a"]})

        for table_name in TABLES:
            assert connection.execute(text(f"SELECT COUNT(*) FROM {table_name}")).scalar_one() >= 1, table_name

    with engine.begin() as connection:
        connection.execute(text(f"SET LOCAL ROLE {APP_ROLE}"))
        _set_tenant(connection, ids["amo_b"], ids["user_b"])
        for table_name in TABLES:
            assert connection.execute(text(f"SELECT COUNT(*) FROM {table_name}")).scalar_one() == 0, table_name

    for table_name, key in (
        ("quality_privilege_decisions", "decision"),
        ("quality_independence_declarations", "independence"),
        ("quality_investigation_entries", "investigation"),
        ("quality_assurance_case_events", "case_event"),
        ("quality_signal_observations", "observation"),
        ("quality_requirement_links", "link"),
    ):
        _assert_append_only(engine, ids, table_name, row_ids[key])

    print("Quality People, Assurance Cases, Intelligence and Approval Graph migration/RLS probe passed")


if __name__ == "__main__":
    main()
