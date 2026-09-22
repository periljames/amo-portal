from __future__ import annotations

import os
import subprocess
from uuid import uuid4

import sqlalchemy as sa
from sqlalchemy import create_engine, text
from sqlalchemy.exc import DBAPIError

BASE_REVISION = "quality_260920_audit_ref_family"
TARGET_REVISION = "quality_260922_people_authz"
APP_ROLE = "amo_quality_people_authz_probe"

TABLES = (
    "quality_appointments",
    "quality_authorization_cases",
    "quality_authorization_case_events",
    "quality_authorization_evidence",
    "quality_authorization_reviews",
    "quality_controlled_exemptions",
)

APPEND_ONLY = (
    "quality_authorization_case_events",
    "quality_authorization_reviews",
    "quality_privilege_decisions",
)


def _run_alembic(*args: str) -> None:
    subprocess.run(["alembic", "-c", "amodb/alembic.ini", *args], check=True, env=os.environ.copy())


def _bootstrap(engine: sa.Engine) -> dict[str, str]:
    ids = {key: str(uuid4()) for key in (
        "amo_a", "amo_b", "user_a", "user_b", "rule", "privilege", "decision",
        "qm_role", "qo_role", "ae_role", "admin_role",
    )}
    with engine.begin() as connection:
        connection.execute(text("DROP SCHEMA public CASCADE"))
        connection.execute(text("CREATE SCHEMA public"))
        connection.execute(text("GRANT ALL ON SCHEMA public TO public"))
        connection.execute(text("CREATE TABLE amos (id VARCHAR(36) PRIMARY KEY)"))
        connection.execute(text("CREATE TABLE users (id VARCHAR(36) PRIMARY KEY, amo_id VARCHAR(36))"))
        connection.execute(text("""
            CREATE TABLE quality_privilege_rules (
                id VARCHAR(36) PRIMARY KEY,
                amo_id VARCHAR(36) NOT NULL REFERENCES amos(id),
                privilege_code VARCHAR(64) NOT NULL
            )
        """))
        connection.execute(text("""
            CREATE TABLE quality_privileges (
                id VARCHAR(36) PRIMARY KEY,
                amo_id VARCHAR(36) NOT NULL REFERENCES amos(id),
                rule_id VARCHAR(36) NOT NULL REFERENCES quality_privilege_rules(id),
                user_id VARCHAR(36) NOT NULL REFERENCES users(id),
                status VARCHAR(16) NOT NULL
            )
        """))
        connection.execute(text("""
            CREATE TABLE quality_privilege_decisions (
                id VARCHAR(36) PRIMARY KEY,
                amo_id VARCHAR(36) NOT NULL REFERENCES amos(id),
                privilege_id VARCHAR(36) NOT NULL,
                decision_type VARCHAR(16) NOT NULL,
                resulting_status VARCHAR(16) NOT NULL,
                rationale TEXT NOT NULL,
                eligibility_snapshot JSON NOT NULL,
                source_references JSON NOT NULL,
                effective_from DATE,
                expires_on DATE,
                decided_by_user_id VARCHAR(36) REFERENCES users(id),
                decided_at TIMESTAMPTZ NOT NULL,
                created_at TIMESTAMPTZ NOT NULL,
                CONSTRAINT ck_quality_privilege_decision_type
                    CHECK (decision_type IN ('GRANT','RENEW','SUSPEND','REINSTATE','REVOKE','EXPIRE','REJECT')),
                CONSTRAINT quality_privilege_decisions_privilege_id_fkey
                    FOREIGN KEY (privilege_id) REFERENCES quality_privileges(id) ON DELETE CASCADE
            )
        """))
        connection.execute(text("""
            CREATE TABLE auth_capability_definitions (
                id VARCHAR(64) PRIMARY KEY,
                code VARCHAR(128) NOT NULL UNIQUE,
                module VARCHAR(64) NOT NULL,
                description TEXT
            )
        """))
        connection.execute(text("""
            CREATE TABLE auth_role_definitions (
                id VARCHAR(36) PRIMARY KEY,
                base_role_key VARCHAR(64) NOT NULL
            )
        """))
        connection.execute(text("""
            CREATE TABLE auth_role_capability_bindings (
                id VARCHAR(64) PRIMARY KEY,
                role_id VARCHAR(36) NOT NULL REFERENCES auth_role_definitions(id),
                capability_id VARCHAR(64) NOT NULL REFERENCES auth_capability_definitions(id),
                constraints_json JSON NOT NULL,
                created_at TIMESTAMPTZ NOT NULL,
                UNIQUE (role_id, capability_id)
            )
        """))
        connection.execute(text("INSERT INTO amos (id) VALUES (:amo_a), (:amo_b)"), ids)
        connection.execute(text("INSERT INTO users (id, amo_id) VALUES (:user_a, :amo_a), (:user_b, :amo_b)"), ids)
        connection.execute(text("""
            INSERT INTO quality_privilege_rules (id, amo_id, privilege_code)
            VALUES (:rule, :amo_a, 'AUDITOR_INTERNAL')
        """), ids)
        connection.execute(text("""
            INSERT INTO quality_privileges (id, amo_id, rule_id, user_id, status)
            VALUES (:privilege, :amo_a, :rule, :user_a, 'ACTIVE')
        """), ids)
        connection.execute(text("""
            INSERT INTO quality_privilege_decisions
                (id, amo_id, privilege_id, decision_type, resulting_status, rationale,
                 eligibility_snapshot, source_references, decided_by_user_id, decided_at, created_at)
            VALUES
                (:decision, :amo_a, :privilege, 'GRANT', 'ACTIVE', 'Existing governed decision.',
                 CAST('{}' AS json), CAST('[]' AS json), :user_a, NOW(), NOW())
        """), ids)
        for key, role in (
            ("qm_role", "QUALITY_MANAGER"),
            ("qo_role", "QUALITY_OFFICER"),
            ("ae_role", "ACCOUNTABLE_EXECUTIVE"),
            ("admin_role", "AMO_ADMIN"),
        ):
            connection.execute(
                text("INSERT INTO auth_role_definitions (id, base_role_key) VALUES (:id, :role)"),
                {"id": ids[key], "role": role},
            )
        connection.execute(text(f"""DO $$ BEGIN
            IF NOT EXISTS (SELECT 1 FROM pg_roles WHERE rolname = '{APP_ROLE}')
            THEN CREATE ROLE {APP_ROLE} NOLOGIN; END IF;
        END $$"""))
    return ids


def _set_tenant(connection, amo_id: str, user_id: str) -> None:
    connection.execute(text("SELECT set_config('app.tenant_id', :value, true)"), {"value": amo_id})
    connection.execute(text("SELECT set_config('app.user_id', :value, true)"), {"value": user_id})


def _rls_state(connection, table: str) -> tuple[bool, bool]:
    row = connection.execute(text("""
        SELECT c.relrowsecurity, c.relforcerowsecurity
        FROM pg_class c
        JOIN pg_namespace n ON n.oid = c.relnamespace
        WHERE n.nspname = current_schema() AND c.relname = :table
    """), {"table": table}).one()
    return bool(row.relrowsecurity), bool(row.relforcerowsecurity)


def _assert_append_only(engine: sa.Engine, ids: dict[str, str], table: str, row_id: str) -> None:
    try:
        with engine.begin() as connection:
            connection.execute(text(f"SET LOCAL ROLE {APP_ROLE}"))
            _set_tenant(connection, ids["amo_a"], ids["user_a"])
            connection.execute(text(f"UPDATE {table} SET id=id WHERE id=:id"), {"id": row_id})
    except DBAPIError as exc:
        assert "append-only" in str(exc).lower()
        return
    raise AssertionError(f"{table} accepted mutation despite append-only governance")


def main() -> None:
    engine = create_engine(os.environ["DATABASE_URL"])
    ids = _bootstrap(engine)
    _run_alembic("stamp", BASE_REVISION)
    _run_alembic("upgrade", TARGET_REVISION)

    with engine.begin() as connection:
        assert connection.execute(text("SELECT version_num FROM alembic_version")).scalar_one() == TARGET_REVISION
        connection.execute(text(f"GRANT USAGE ON SCHEMA public TO {APP_ROLE}"))
        connection.execute(text(f"GRANT SELECT, INSERT, UPDATE, DELETE ON ALL TABLES IN SCHEMA public TO {APP_ROLE}"))
        for table in TABLES:
            assert _rls_state(connection, table) == (True, True), table
            assert connection.execute(text("""
                SELECT COUNT(*) FROM pg_policies
                WHERE schemaname=current_schema() AND tablename=:table
            """), {"table": table}).scalar_one() == 1, table

        fk_delete_rule = connection.execute(text("""
            SELECT rc.delete_rule
            FROM information_schema.referential_constraints rc
            WHERE rc.constraint_schema=current_schema()
              AND rc.constraint_name='fk_quality_privilege_decisions_privilege_retained'
        """)).scalar_one()
        assert fk_delete_rule == "RESTRICT"

        decision_check = connection.execute(text("""
            SELECT pg_get_constraintdef(c.oid)
            FROM pg_constraint c
            JOIN pg_class t ON t.oid=c.conrelid
            WHERE t.relname='quality_privilege_decisions'
              AND c.conname='ck_quality_privilege_decision_type'
        """)).scalar_one()
        assert "CHANGE" in decision_check

        capabilities = {
            row[0]
            for row in connection.execute(text("""
                SELECT code FROM auth_capability_definitions
                WHERE code LIKE 'qms.authorization.%' OR code='qms.people.view'
            """)).all()
        }
        assert {
            "qms.people.view",
            "qms.authorization.prepare",
            "qms.authorization.approve",
            "qms.authorization.review",
            "qms.authorization.exemption.approve",
            "qms.authorization.policy.manage",
            "qms.authorization.oversight",
        }.issubset(capabilities)

        qo_caps = {
            row[0]
            for row in connection.execute(text("""
                SELECT c.code
                FROM auth_role_capability_bindings b
                JOIN auth_role_definitions r ON r.id=b.role_id
                JOIN auth_capability_definitions c ON c.id=b.capability_id
                WHERE r.base_role_key='QUALITY_OFFICER'
            """)).all()
        }
        assert "qms.authorization.prepare" in qo_caps
        assert "qms.authorization.approve" not in qo_caps

        qm_caps = {
            row[0]
            for row in connection.execute(text("""
                SELECT c.code
                FROM auth_role_capability_bindings b
                JOIN auth_role_definitions r ON r.id=b.role_id
                JOIN auth_capability_definitions c ON c.id=b.capability_id
                WHERE r.base_role_key='QUALITY_MANAGER'
            """)).all()
        }
        assert "qms.authorization.approve" in qm_caps
        assert "qms.authorization.review" in qm_caps
        assert "qms.authorization.exemption.approve" in qm_caps

    rows = {key: str(uuid4()) for key in ("appointment", "case", "case_event", "review", "exemption", "evidence")}
    with engine.begin() as connection:
        connection.execute(text(f"SET LOCAL ROLE {APP_ROLE}"))
        _set_tenant(connection, ids["amo_a"], ids["user_a"])
        connection.execute(text("""
            INSERT INTO quality_appointments
                (id,amo_id,user_id,function_code,title,status,source_references,created_by_user_id,updated_by_user_id,created_at,updated_at)
            VALUES
                (:id,:amo,:user,'AUDITOR','Internal Quality Auditor','ACTIVE',CAST('[]' AS json),:user,:user,NOW(),NOW())
        """), {"id": rows["appointment"], "amo": ids["amo_a"], "user": ids["user_a"]})
        connection.execute(text("""
            INSERT INTO quality_authorization_cases
                (id,amo_id,user_id,appointment_id,current_privilege_id,requested_rule_id,case_type,status,
                 requested_scope_key,requested_scope,nomination_date,nominated_by_user_id,person_snapshot,
                 current_authorization_snapshot,requested_authorization_snapshot,readiness_snapshot,source_references,
                 created_by_user_id,updated_by_user_id,created_at,updated_at)
            VALUES
                (:id,:amo,:user,:appointment,:privilege,:rule,'RENEWAL','READY_FOR_DECISION',
                 'GLOBAL',CAST('{}' AS json),CURRENT_DATE,:user,CAST('{"name":"Probe Person"}' AS json),
                 CAST('{}' AS json),CAST('{"authorization":"Auditor"}' AS json),CAST('{}' AS json),CAST('[]' AS json),
                 :user,:user,NOW(),NOW())
        """), {
            "id": rows["case"], "amo": ids["amo_a"], "user": ids["user_a"],
            "appointment": rows["appointment"], "privilege": ids["privilege"], "rule": ids["rule"],
        })
        connection.execute(text("""
            INSERT INTO quality_authorization_case_events
                (id,amo_id,case_id,action,previous_status,new_status,reason,before_snapshot,after_snapshot,
                 source_references,actor_user_id,occurred_at,created_at)
            VALUES
                (:id,:amo,:case,'SUBMITTED_FOR_DECISION','UNDER_REVIEW','READY_FOR_DECISION',
                 'Prepared case submitted.',CAST('{}' AS json),CAST('{}' AS json),CAST('[]' AS json),:user,NOW(),NOW())
        """), {"id": rows["case_event"], "amo": ids["amo_a"], "case": rows["case"], "user": ids["user_a"]})
        connection.execute(text("""
            INSERT INTO quality_authorization_evidence
                (id,amo_id,case_id,evidence_type,label,source_reference,status,uploaded_by_user_id,created_at)
            VALUES
                (:id,:amo,:case,'COMPETENCE_ASSESSMENT','Competence assessment',CAST('{}' AS json),'ACTIVE',:user,NOW())
        """), {"id": rows["evidence"], "amo": ids["amo_a"], "case": rows["case"], "user": ids["user_a"]})
        connection.execute(text("""
            INSERT INTO quality_authorization_reviews
                (id,amo_id,privilege_id,last_reviewed,next_review_due,review_outcome,review_reason,
                 reviewed_by_user_id,reviewed_at,review_evidence,before_snapshot,after_snapshot,created_at)
            VALUES
                (:id,:amo,:privilege,CURRENT_DATE,CURRENT_DATE + 365,'CONTINUE','Annual review complete.',
                 :user,NOW(),CAST('[]' AS json),CAST('{}' AS json),CAST('{}' AS json),NOW())
        """), {"id": rows["review"], "amo": ids["amo_a"], "privilege": ids["privilege"], "user": ids["user_a"]})
        connection.execute(text("""
            INSERT INTO quality_controlled_exemptions
                (id,amo_id,case_id,privilege_id,person_user_id,authorization_type,criterion,
                 reason_normal_compliance_impossible,equivalent_evidence,limitations,supervision_required,
                 conditions,effective_from,expires_on,source_references,status,approved_by_user_id,approved_at,created_at)
            VALUES
                (:id,:amo,:case,:privilege,:user,'Auditor','training_current_verified',
                 'Temporary evidence timing issue.',CAST('[]' AS json),CAST('[]' AS json),false,
                 CAST('["Direct Quality Manager oversight"]' AS json),CURRENT_DATE,CURRENT_DATE + 7,CAST('[]' AS json),
                 'ACTIVE',:user,NOW(),NOW())
        """), {
            "id": rows["exemption"], "amo": ids["amo_a"], "case": rows["case"],
            "privilege": ids["privilege"], "user": ids["user_a"],
        })
        for table in TABLES:
            assert connection.execute(text(f"SELECT COUNT(*) FROM {table}")).scalar_one() >= 1, table

    with engine.begin() as connection:
        connection.execute(text(f"SET LOCAL ROLE {APP_ROLE}"))
        _set_tenant(connection, ids["amo_b"], ids["user_b"])
        for table in TABLES:
            assert connection.execute(text(f"SELECT COUNT(*) FROM {table}")).scalar_one() == 0, table

    _assert_append_only(engine, ids, "quality_privilege_decisions", ids["decision"])
    _assert_append_only(engine, ids, "quality_authorization_case_events", rows["case_event"])
    _assert_append_only(engine, ids, "quality_authorization_reviews", rows["review"])

    print("Quality People authorization control migration, capabilities, RLS and retained-history probe passed")


if __name__ == "__main__":
    main()
