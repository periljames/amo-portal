from __future__ import annotations

import os
import subprocess
from uuid import uuid4

import sqlalchemy as sa
from sqlalchemy import create_engine, text


BASE_REVISION = "resilience_260816_commands"
TARGET_REVISION = "training_260818_rls_gap"
APP_ROLE = "amo_training_rls_probe"
TENANT_TABLES = (
    "training_configuration_revisions",
    "training_reference_resources",
    "training_controlled_form_templates",
    "training_automation_runs",
    "training_setup_versions",
    "training_change_requests",
    "training_workflow_instances",
    "training_workflow_steps",
    "training_session_invitations",
    "training_report_definitions",
    "training_report_jobs",
    "training_saved_views",
)


def _run_alembic(*arguments: str) -> None:
    subprocess.run(
        ["alembic", "-c", "amodb/alembic.ini", *arguments],
        check=True,
        env=os.environ.copy(),
    )


def _bootstrap(engine: sa.Engine) -> tuple[str, str]:
    amo_a = str(uuid4())
    amo_b = str(uuid4())
    with engine.begin() as connection:
        connection.execute(text("DROP SCHEMA public CASCADE"))
        connection.execute(text("CREATE SCHEMA public"))
        connection.execute(text("GRANT ALL ON SCHEMA public TO public"))
        for table_name in TENANT_TABLES:
            connection.execute(
                text(
                    f'CREATE TABLE "{table_name}" ('
                    "id VARCHAR(36) PRIMARY KEY, amo_id VARCHAR(36) NOT NULL)"
                )
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
    return amo_a, amo_b


def _set_tenant(connection: sa.Connection, amo_id: str) -> None:
    connection.execute(
        text("SELECT set_config('app.tenant_id', :amo_id, true)"),
        {"amo_id": amo_id},
    )


def _assert_rls_contract(connection: sa.Connection, table_name: str) -> None:
    row = connection.execute(
        text(
            """
            SELECT c.relrowsecurity
            FROM pg_class c
            JOIN pg_namespace n ON n.oid = c.relnamespace
            WHERE n.nspname = current_schema() AND c.relname = :table_name
            """
        ),
        {"table_name": table_name},
    ).one()
    assert bool(row.relrowsecurity) is True

    policy = connection.execute(
        text(
            """
            SELECT policyname, qual, with_check
            FROM pg_policies
            WHERE schemaname = current_schema() AND tablename = :table_name
            """
        ),
        {"table_name": table_name},
    ).one()
    assert policy.policyname == f"{table_name}_tenant_isolation"
    assert "app.tenant_id" in str(policy.qual)
    assert "app.tenant_id" in str(policy.with_check)


def main() -> None:
    engine = create_engine(os.environ["DATABASE_URL"])
    amo_a, amo_b = _bootstrap(engine)

    _run_alembic("stamp", BASE_REVISION)
    _run_alembic("upgrade", TARGET_REVISION)

    with engine.begin() as connection:
        assert connection.execute(text("SELECT version_num FROM alembic_version")).scalar_one() == TARGET_REVISION
        for table_name in TENANT_TABLES:
            _assert_rls_contract(connection, table_name)
            connection.execute(
                text(f'INSERT INTO "{table_name}" (id, amo_id) VALUES (:id_a, :amo_a), (:id_b, :amo_b)'),
                {
                    "id_a": f"a-{uuid4().hex[:28]}",
                    "amo_a": amo_a,
                    "id_b": f"b-{uuid4().hex[:28]}",
                    "amo_b": amo_b,
                },
            )

        connection.execute(text(f"GRANT USAGE ON SCHEMA public TO {APP_ROLE}"))
        connection.execute(text(f"GRANT SELECT, INSERT, UPDATE, DELETE ON ALL TABLES IN SCHEMA public TO {APP_ROLE}"))

    with engine.begin() as connection:
        connection.execute(text(f"SET LOCAL ROLE {APP_ROLE}"))
        _set_tenant(connection, amo_a)
        for table_name in TENANT_TABLES:
            rows = connection.execute(text(f'SELECT amo_id FROM "{table_name}"')).scalars().all()
            assert rows == [amo_a]
            cross_tenant = connection.execute(
                text(f'UPDATE "{table_name}" SET id = id WHERE amo_id = :amo_b'),
                {"amo_b": amo_b},
            )
            assert cross_tenant.rowcount == 0

    with engine.begin() as connection:
        connection.execute(text(f"SET LOCAL ROLE {APP_ROLE}"))
        _set_tenant(connection, amo_b)
        for table_name in TENANT_TABLES:
            rows = connection.execute(text(f'SELECT amo_id FROM "{table_name}"')).scalars().all()
            assert rows == [amo_b]

    print("Training PostgreSQL tenant RLS probe passed")


if __name__ == "__main__":
    main()
