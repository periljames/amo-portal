from __future__ import annotations

import os
import subprocess

import sqlalchemy as sa
from sqlalchemy import create_engine, text


TARGET_REVISION = "quality_260816_fieldwork_sync"
TABLES = (
    "quality_external_identities",
    "quality_audit_participants",
    "quality_audit_access_grants",
    "quality_audit_access_events",
    "quality_audit_finding_release_events",
    "quality_audit_document_submissions",
    "quality_audit_report_artifacts",
    "quality_audit_fieldwork_mutation_receipts",
)
APPEND_ONLY_TABLES = (
    "quality_audit_access_events",
    "quality_audit_finding_release_events",
    "quality_audit_document_submissions",
    "quality_audit_report_artifacts",
    "quality_audit_fieldwork_mutation_receipts",
)


def _run_alembic(*arguments: str) -> None:
    subprocess.run(
        ["alembic", "-c", "amodb/alembic.ini", *arguments],
        check=True,
        env=os.environ.copy(),
    )


def _assert_rls(connection: sa.Connection, table_name: str) -> None:
    row = connection.execute(
        text(
            """
            SELECT relrowsecurity, relforcerowsecurity
            FROM pg_class
            WHERE oid = CAST(:table_name AS regclass)
            """
        ),
        {"table_name": table_name},
    ).one()
    assert row.relrowsecurity is True, (table_name, row)
    assert row.relforcerowsecurity is True, (table_name, row)
    policies = connection.execute(
        text(
            """
            SELECT policyname, qual, with_check
            FROM pg_policies
            WHERE schemaname = current_schema()
              AND tablename = :table_name
            """
        ),
        {"table_name": table_name},
    ).all()
    assert len(policies) == 1, (table_name, policies)
    policy_text = f"{policies[0].qual} {policies[0].with_check}"
    assert "app.tenant_id" in policy_text, (table_name, policy_text)


def main() -> None:
    engine = create_engine(os.environ["DATABASE_URL"])
    _run_alembic("upgrade", "heads")

    with engine.begin() as connection:
        versions = {str(row[0]) for row in connection.execute(text("SELECT version_num FROM alembic_version")).all()}
        assert TARGET_REVISION in versions, versions

        existing = {
            str(row[0])
            for row in connection.execute(
                text(
                    """
                    SELECT table_name
                    FROM information_schema.tables
                    WHERE table_schema = current_schema()
                      AND table_name = ANY(:tables)
                    """
                ),
                {"tables": list(TABLES)},
            ).all()
        }
        assert existing == set(TABLES), existing

        columns = {
            str(row[0])
            for row in connection.execute(
                text(
                    """
                    SELECT column_name
                    FROM information_schema.columns
                    WHERE table_schema = current_schema()
                      AND table_name = 'quality_audit_checklist_execution_governance'
                    """
                )
            ).all()
        }
        assert "entity_version" in columns, columns

        for table_name in TABLES:
            _assert_rls(connection, table_name)

        triggers = {
            (str(row.table_name), str(row.trigger_name))
            for row in connection.execute(
                text(
                    """
                    SELECT event_object_table AS table_name, trigger_name
                    FROM information_schema.triggers
                    WHERE trigger_schema = current_schema()
                      AND event_object_table = ANY(:tables)
                    """
                ),
                {"tables": list(APPEND_ONLY_TABLES)},
            ).mappings()
        }
        for table_name in APPEND_ONLY_TABLES:
            assert any(table == table_name and "append_only" in trigger for table, trigger in triggers), (table_name, triggers)

    print("Live audit migrations, RLS, versioning and append-only history verified")


if __name__ == "__main__":
    main()
