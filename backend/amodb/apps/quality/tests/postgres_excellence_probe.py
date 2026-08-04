from __future__ import annotations

import os
import subprocess
from uuid import uuid4

import sqlalchemy as sa
from sqlalchemy import create_engine, text


BASE_REVISION = "accounts_20260803_auth_session"
TARGET_REVISION = "quality_260804_assurance_wiring"
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
        "document_a": str(uuid4()),
    }
    with engine.begin() as connection:
        connection.execute(text("DROP SCHEMA public CASCADE"))
        connection.execute(text("CREATE SCHEMA public"))
        connection.execute(text("GRANT ALL ON SCHEMA public TO public"))
        connection.execute(text("CREATE TABLE amos (id VARCHAR(36) PRIMARY KEY)"))
        connection.execute(text("CREATE TABLE users (id VARCHAR(36) PRIMARY KEY)"))
        connection.execute(
            text(
                """
                CREATE TABLE qms_documents (
                    id VARCHAR(36) PRIMARY KEY,
                    amo_id VARCHAR(36) NOT NULL REFERENCES amos(id) ON DELETE CASCADE,
                    doc_code VARCHAR(80),
                    title VARCHAR(255),
                    status VARCHAR(24),
                    updated_by VARCHAR(36),
                    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
                    updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
                    deleted_at TIMESTAMPTZ
                )
                """
            )
        )
        connection.execute(text("INSERT INTO amos (id) VALUES (:amo_a), (:amo_b)"), ids)
        connection.execute(text("INSERT INTO users (id) VALUES (:user_a)"), ids)
        connection.execute(
            text(
                """
                INSERT INTO qms_documents (id, amo_id, doc_code, title, status, updated_by)
                VALUES (:document_a, :amo_a, 'QPM-001', 'Quality Procedures Manual', 'ACTIVE', :user_a)
                """
            ),
            ids,
        )
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
        "quality_control_tests",
        "quality_assurance_events",
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

        trigger_count = connection.execute(
            text(
                """
                SELECT COUNT(*)
                FROM pg_trigger t
                JOIN pg_class c ON c.oid = t.tgrelid
                WHERE c.relname = 'qms_documents'
                  AND t.tgname = 'trg_qms_documents_assurance_event'
                  AND NOT t.tgisinternal
                """
            )
        ).scalar_one()
        assert trigger_count == 1

        function_count = connection.execute(
            text("SELECT COUNT(*) FROM pg_proc WHERE proname = 'quality_capture_assurance_event'")
        ).scalar_one()
        assert function_count == 1

        connection.execute(text(f"GRANT USAGE ON SCHEMA public TO {APP_ROLE}"))
        connection.execute(text(f"GRANT SELECT, INSERT, UPDATE, DELETE ON ALL TABLES IN SCHEMA public TO {APP_ROLE}"))

    control_id = str(uuid4())
    evidence_id = str(uuid4())
    test_id = str(uuid4())
    insight_id = str(uuid4())

    with engine.begin() as connection:
        connection.execute(text(f"SET LOCAL ROLE {APP_ROLE}"))
        connection.execute(text("SELECT set_config('app.tenant_id', :amo_id, true)"), {"amo_id": ids["amo_a"]})
        connection.execute(text("SELECT set_config('app.user_id', :user_id, true)"), {"user_id": ids["user_a"]})
        connection.execute(
            text(
                """
                INSERT INTO quality_assurance_controls (
                    id, amo_id, control_code, title, framework, process_area,
                    criticality, status, approval_status, version_no,
                    test_frequency_days, evidence_expectation
                ) VALUES (
                    :id, :amo_id, '145-A65-C01', 'Independent audit programme',
                    'KCAR PART 145', 'Quality assurance', 'CRITICAL', 'ACTIVE',
                    'APPROVED', 1, 365, 'Approved programme and current reports'
                )
                """
            ),
            {"id": control_id, "amo_id": ids["amo_a"]},
        )
        connection.execute(
            text(
                """
                INSERT INTO quality_assurance_evidence_links (
                    id, amo_id, control_id, source_type, source_id, source_table,
                    source_route, source_label, source_snapshot, relationship,
                    evidence_status, source_verified_at, last_synced_at
                ) VALUES (
                    :id, :amo_id, :control_id, 'DOCUMENT', :document_id,
                    'qms_documents', '/maintenance/AMO/quality/documents/library/' || :document_id,
                    'QPM-001 · Quality Procedures Manual', CAST('{}' AS json),
                    'IMPLEMENTS', 'VERIFIED', NOW(), NOW()
                )
                """
            ),
            {
                "id": evidence_id,
                "amo_id": ids["amo_a"],
                "control_id": control_id,
                "document_id": ids["document_a"],
            },
        )
        connection.execute(
            text(
                """
                INSERT INTO quality_control_tests (
                    id, amo_id, control_id, result, tested_at, tested_by_user_id,
                    method, evidence_summary
                ) VALUES (
                    :id, :amo_id, :control_id, 'PASS', NOW(), :user_id,
                    'Inspect programme and reports', CAST('{"verified": 1}' AS json)
                )
                """
            ),
            {
                "id": test_id,
                "amo_id": ids["amo_a"],
                "control_id": control_id,
                "user_id": ids["user_a"],
            },
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

        connection.execute(
            text(
                """
                UPDATE qms_documents
                SET title = 'Quality Procedures Manual — Approved',
                    updated_by = :user_id,
                    updated_at = NOW()
                WHERE id = :document_id AND amo_id = :amo_id
                """
            ),
            {
                "document_id": ids["document_a"],
                "amo_id": ids["amo_a"],
                "user_id": ids["user_a"],
            },
        )

        assert connection.execute(text("SELECT COUNT(*) FROM quality_assurance_controls")).scalar_one() == 1
        assert connection.execute(text("SELECT COUNT(*) FROM quality_assurance_evidence_links")).scalar_one() == 1
        assert connection.execute(text("SELECT COUNT(*) FROM quality_control_tests")).scalar_one() == 1
        assert connection.execute(text("SELECT COUNT(*) FROM quality_intelligence_reviews")).scalar_one() == 1
        assert connection.execute(text("SELECT COUNT(*) FROM quality_assurance_events")).scalar_one() == 1

        event = connection.execute(
            text(
                """
                SELECT source_type, source_id, event_type, processing_status
                FROM quality_assurance_events
                LIMIT 1
                """
            )
        ).mappings().one()
        assert event["source_type"] == "DOCUMENT"
        assert event["source_id"] == ids["document_a"]
        assert event["event_type"] == "UPDATE"
        assert event["processing_status"] == "PENDING"

        evidence = connection.execute(
            text(
                """
                SELECT source_snapshot, evidence_status, last_synced_at, invalidation_reason
                FROM quality_assurance_evidence_links
                WHERE id = :id
                """
            ),
            {"id": evidence_id},
        ).mappings().one()
        assert evidence["source_snapshot"]["title"] == "Quality Procedures Manual — Approved"
        assert evidence["evidence_status"] == "VERIFIED"
        assert evidence["last_synced_at"] is not None
        assert evidence["invalidation_reason"] is None

    with engine.begin() as connection:
        connection.execute(text(f"SET LOCAL ROLE {APP_ROLE}"))
        connection.execute(text("SELECT set_config('app.tenant_id', :amo_id, true)"), {"amo_id": ids["amo_b"]})
        assert connection.execute(text("SELECT COUNT(*) FROM quality_assurance_controls")).scalar_one() == 0
        assert connection.execute(text("SELECT COUNT(*) FROM quality_assurance_evidence_links")).scalar_one() == 0
        assert connection.execute(text("SELECT COUNT(*) FROM quality_control_tests")).scalar_one() == 0
        assert connection.execute(text("SELECT COUNT(*) FROM quality_assurance_events")).scalar_one() == 0
        assert connection.execute(text("SELECT COUNT(*) FROM quality_intelligence_reviews")).scalar_one() == 0

        rejected = False
        savepoint = connection.begin_nested()
        try:
            connection.execute(
                text(
                    """
                    INSERT INTO quality_assurance_controls (
                        id, amo_id, control_code, title, framework, process_area,
                        criticality, status, approval_status, version_no, test_frequency_days
                    ) VALUES (
                        :id, :amo_a, 'CROSS-TENANT', 'Cross-tenant write',
                        'TEST', 'TEST', 'LOW', 'ACTIVE', 'DRAFT', 1, 365
                    )
                    """
                ),
                {"id": str(uuid4()), "amo_a": ids["amo_a"]},
            )
        except sa.exc.DatabaseError:
            rejected = True
            savepoint.rollback()
        else:
            savepoint.rollback()
        assert rejected, "RLS unexpectedly allowed a cross-tenant assurance-control insert"


if __name__ == "__main__":
    main()
