from __future__ import annotations

import os
import subprocess
from uuid import uuid4

import sqlalchemy as sa
from sqlalchemy import create_engine, text


BASE_REVISION = "accounts_20260803_auth_session"
TARGET_REVISION = "quality_260804_assurance_rls"
APP_ROLE = "amo_quality_probe_app"


def _run_alembic(*arguments: str) -> None:
    subprocess.run(
        ["alembic", "-c", "amodb/alembic.ini", *arguments],
        check=True,
        env=os.environ.copy(),
    )


def _reset_and_bootstrap(engine: sa.Engine) -> dict[str, str]:
    ids = {
        "amo_a": str(uuid4()),
        "amo_b": str(uuid4()),
        "user_a": str(uuid4()),
    }
    with engine.begin() as connection:
        connection.execute(text("DROP SCHEMA public CASCADE"))
        connection.execute(text("CREATE SCHEMA public"))
        connection.execute(text("GRANT ALL ON SCHEMA public TO public"))
        connection.execute(text("CREATE TABLE amos (id VARCHAR(36) PRIMARY KEY)"))
        connection.execute(text("CREATE TABLE users (id VARCHAR(36) PRIMARY KEY)"))
        connection.execute(text("INSERT INTO amos (id) VALUES (:amo_a), (:amo_b)"), ids)
        connection.execute(text("INSERT INTO users (id) VALUES (:user_a)"), ids)
        connection.execute(
            text(
                f"""
                DO $$
                BEGIN
                    IF NOT EXISTS (SELECT 1 FROM pg_roles WHERE rolname = '{APP_ROLE}') THEN
                        CREATE ROLE {APP_ROLE} NOLOGIN;
                    END IF;
                END
                $$
                """
            )
        )
    return ids


def _rls_state(connection, table_name: str) -> tuple[bool, bool]:
    row = connection.execute(
        text(
            """
            SELECT c.relrowsecurity, c.relforcerowsecurity
            FROM pg_class c
            JOIN pg_namespace n ON n.oid = c.relnamespace
            WHERE n.nspname = current_schema()
              AND c.relname = :table_name
            """
        ),
        {"table_name": table_name},
    ).one()
    return bool(row.relrowsecurity), bool(row.relforcerowsecurity)


def main() -> None:
    engine = create_engine(os.environ["DATABASE_URL"])
    ids = _reset_and_bootstrap(engine)
    _run_alembic("stamp", BASE_REVISION)
    _run_alembic("upgrade", TARGET_REVISION)

    tables = (
        "user_portal_preferences",
        "quality_assurance_controls",
        "quality_assurance_evidence_links",
        "quality_intelligence_reviews",
    )
    rls_tables = tables[1:]

    with engine.begin() as connection:
        revision = connection.execute(text("SELECT version_num FROM alembic_version")).scalar_one()
        assert revision == TARGET_REVISION

        existing = {
            str(row.table_name)
            for row in connection.execute(
                text(
                    """
                    SELECT table_name
                    FROM information_schema.tables
                    WHERE table_schema = current_schema()
                    """
                )
            )
        }
        assert set(tables).issubset(existing)

        for table_name in rls_tables:
            assert _rls_state(connection, table_name) == (True, True)
            policy_count = connection.execute(
                text(
                    """
                    SELECT COUNT(*)
                    FROM pg_policies
                    WHERE schemaname = current_schema()
                      AND tablename = :table_name
                    """
                ),
                {"table_name": table_name},
            ).scalar_one()
            assert policy_count == 1

        connection.execute(text(f"GRANT USAGE ON SCHEMA public TO {APP_ROLE}"))
        connection.execute(text(f"GRANT SELECT, INSERT, UPDATE, DELETE ON ALL TABLES IN SCHEMA public TO {APP_ROLE}"))

    control_id = str(uuid4())
    evidence_id = str(uuid4())
    insight_id = str(uuid4())

    with engine.begin() as connection:
        connection.execute(text(f"SET LOCAL ROLE {APP_ROLE}"))
        connection.execute(text("SELECT set_config('app.tenant_id', :amo_id, true)"), {"amo_id": ids["amo_a"]})
        connection.execute(
            text(
                """
                INSERT INTO quality_assurance_controls (
                    id, amo_id, control_code, title, framework, process_area,
                    criticality, status, test_frequency_days
                ) VALUES (
                    :id, :amo_id, '145-A65-C01', 'Independent audit programme',
                    'KCAR PART 145', 'Quality assurance', 'CRITICAL', 'ACTIVE', 365
                )
                """
            ),
            {"id": control_id, "amo_id": ids["amo_a"]},
        )
        connection.execute(
            text(
                """
                INSERT INTO quality_assurance_evidence_links (
                    id, amo_id, control_id, source_type, source_id,
                    relationship, evidence_status
                ) VALUES (
                    :id, :amo_id, :control_id, 'DOCUMENT', 'doc-1',
                    'IMPLEMENTS', 'VERIFIED'
                )
                """
            ),
            {"id": evidence_id, "amo_id": ids["amo_a"], "control_id": control_id},
        )
        connection.execute(
            text(
                """
                INSERT INTO quality_intelligence_reviews (
                    id, amo_id, insight_type, title, rationale, payload,
                    source_fingerprint, risk_level, status, created_by
                ) VALUES (
                    :id, :amo_id, 'CONTROL_TEST_DUE', 'Retest control',
                    'Evidence is approaching its test date.', CAST('{}' AS json),
                    'probe:control-test-due', 'MEDIUM', 'PROPOSED', 'RULE_ENGINE'
                )
                """
            ),
            {"id": insight_id, "amo_id": ids["amo_a"]},
        )
        assert connection.execute(text("SELECT COUNT(*) FROM quality_assurance_controls")).scalar_one() == 1
        assert connection.execute(text("SELECT COUNT(*) FROM quality_assurance_evidence_links")).scalar_one() == 1
        assert connection.execute(text("SELECT COUNT(*) FROM quality_intelligence_reviews")).scalar_one() == 1

    with engine.begin() as connection:
        connection.execute(text(f"SET LOCAL ROLE {APP_ROLE}"))
        connection.execute(text("SELECT set_config('app.tenant_id', :amo_id, true)"), {"amo_id": ids["amo_b"]})
        assert connection.execute(text("SELECT COUNT(*) FROM quality_assurance_controls")).scalar_one() == 0
        assert connection.execute(text("SELECT COUNT(*) FROM quality_assurance_evidence_links")).scalar_one() == 0
        assert connection.execute(text("SELECT COUNT(*) FROM quality_intelligence_reviews")).scalar_one() == 0

        rejected = False
        try:
            connection.execute(
                text(
                    """
                    INSERT INTO quality_assurance_controls (
                        id, amo_id, control_code, title, framework, process_area,
                        criticality, status, test_frequency_days
                    ) VALUES (
                        :id, :amo_a, 'CROSS-TENANT', 'Cross-tenant write',
                        'TEST', 'TEST', 'LOW', 'ACTIVE', 365
                    )
                    """
                ),
                {"id": str(uuid4()), "amo_a": ids["amo_a"]},
            )
        except sa.exc.DatabaseError:
            rejected = True
        assert rejected, "RLS unexpectedly allowed a cross-tenant assurance-control insert"


if __name__ == "__main__":
    main()
