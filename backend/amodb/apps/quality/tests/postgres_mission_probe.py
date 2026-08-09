from __future__ import annotations

import os
import subprocess
from uuid import uuid4

import sqlalchemy as sa
from sqlalchemy import create_engine, text


BASE_REVISION = "docgov_rel_20260807_merge"
TARGET_REVISION = "quality_260808_missions"
APP_ROLE = "amo_quality_mission_probe"


def _run_alembic(*arguments: str) -> None:
    subprocess.run(
        ["alembic", "-c", "amodb/alembic.ini", *arguments],
        check=True,
        env=os.environ.copy(),
    )


def _bootstrap(engine: sa.Engine) -> dict[str, str]:
    ids = {
        "amo_a": str(uuid4()),
        "amo_b": str(uuid4()),
        "user_a": str(uuid4()),
        "user_b": str(uuid4()),
    }
    with engine.begin() as connection:
        connection.execute(text("DROP SCHEMA public CASCADE"))
        connection.execute(text("CREATE SCHEMA public"))
        connection.execute(text("GRANT ALL ON SCHEMA public TO public"))
        connection.execute(text("CREATE TABLE amos (id VARCHAR(36) PRIMARY KEY)"))
        connection.execute(text("CREATE TABLE users (id VARCHAR(36) PRIMARY KEY)"))
        connection.execute(text("INSERT INTO amos (id) VALUES (:amo_a), (:amo_b)"), ids)
        connection.execute(text("INSERT INTO users (id) VALUES (:user_a), (:user_b)"), ids)
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
            WHERE n.nspname = current_schema() AND c.relname = :table_name
            """
        ),
        {"table_name": table_name},
    ).one()
    return bool(row.relrowsecurity), bool(row.relforcerowsecurity)


def _set_tenant(connection, amo_id: str, user_id: str) -> None:
    connection.execute(text("SELECT set_config('app.tenant_id', :amo_id, true)"), {"amo_id": amo_id})
    connection.execute(text("SELECT set_config('app.user_id', :user_id, true)"), {"user_id": user_id})


def main() -> None:
    engine = create_engine(os.environ["DATABASE_URL"])
    ids = _bootstrap(engine)
    _run_alembic("stamp", BASE_REVISION)
    _run_alembic("upgrade", TARGET_REVISION)

    tables = ("quality_missions", "quality_mission_gates", "quality_mission_decisions")
    with engine.begin() as connection:
        assert connection.execute(text("SELECT version_num FROM alembic_version")).scalar_one() == TARGET_REVISION
        existing = {
            str(row.table_name)
            for row in connection.execute(
                text("SELECT table_name FROM information_schema.tables WHERE table_schema = current_schema()")
            )
        }
        assert set(tables).issubset(existing)
        for table_name in tables:
            assert _rls_state(connection, table_name) == (True, True)
            assert connection.execute(
                text(
                    """
                    SELECT COUNT(*) FROM pg_policies
                    WHERE schemaname = current_schema() AND tablename = :table_name
                    """
                ),
                {"table_name": table_name},
            ).scalar_one() == 1

        connection.execute(text(f"GRANT USAGE ON SCHEMA public TO {APP_ROLE}"))
        connection.execute(text(f"GRANT SELECT, INSERT, UPDATE, DELETE ON ALL TABLES IN SCHEMA public TO {APP_ROLE}"))

    mission_a = str(uuid4())
    gate_a = str(uuid4())
    decision_a = str(uuid4())

    with engine.begin() as connection:
        connection.execute(text(f"SET LOCAL ROLE {APP_ROLE}"))
        _set_tenant(connection, ids["amo_a"], ids["user_a"])
        connection.execute(
            text(
                """
                INSERT INTO quality_missions (
                    id, amo_id, mission_ref, mission_type, title, scope, regulatory_basis,
                    risk_level, status, owner_user_id, requested_by_user_id,
                    requested_at, created_by_user_id, updated_by_user_id, created_at, updated_at
                ) VALUES (
                    :id, :amo_id, 'MSN-26-PROBE', 'CAPABILITY_ADDITION', 'DHC capability inclusion',
                    CAST('{}' AS json), CAST('[]' AS json), 'HIGH', 'IN_PROGRESS', :user_id, :user_id,
                    NOW(), :user_id, :user_id, NOW(), NOW()
                )
                """
            ),
            {"id": mission_a, "amo_id": ids["amo_a"], "user_id": ids["user_a"]},
        )
        connection.execute(
            text(
                """
                INSERT INTO quality_mission_gates (
                    id, amo_id, mission_id, gate_code, title, category, gate_type,
                    status, source_owner_module, source_type, source_id,
                    evidence_status, sort_order, created_at, updated_at
                ) VALUES (
                    :id, :amo_id, :mission_id, 'TOOLING', 'Tooling and test equipment', 'Tooling',
                    'HARD', 'PASS', 'tooling', 'EQUIPMENT', 'tool-set-1', 'VERIFIED', 40, NOW(), NOW()
                )
                """
            ),
            {"id": gate_a, "amo_id": ids["amo_a"], "mission_id": mission_a},
        )
        connection.execute(
            text(
                """
                INSERT INTO quality_mission_decisions (
                    id, amo_id, mission_id, decision_type, status, rationale,
                    evidence_snapshot, decided_by_user_id, decided_at, created_at
                ) VALUES (
                    :id, :amo_id, :mission_id, 'CUSTOM', 'APPROVED', 'Probe decision',
                    CAST('{}' AS json), :user_id, NOW(), NOW()
                )
                """
            ),
            {
                "id": decision_a,
                "amo_id": ids["amo_a"],
                "mission_id": mission_a,
                "user_id": ids["user_a"],
            },
        )
        assert connection.execute(text("SELECT COUNT(*) FROM quality_missions")).scalar_one() == 1
        assert connection.execute(text("SELECT COUNT(*) FROM quality_mission_gates")).scalar_one() == 1
        assert connection.execute(text("SELECT COUNT(*) FROM quality_mission_decisions")).scalar_one() == 1

    with engine.begin() as connection:
        connection.execute(text(f"SET LOCAL ROLE {APP_ROLE}"))
        _set_tenant(connection, ids["amo_b"], ids["user_b"])
        assert connection.execute(text("SELECT COUNT(*) FROM quality_missions")).scalar_one() == 0
        assert connection.execute(text("SELECT COUNT(*) FROM quality_mission_gates")).scalar_one() == 0
        assert connection.execute(text("SELECT COUNT(*) FROM quality_mission_decisions")).scalar_one() == 0
        updated = connection.execute(
            text("UPDATE quality_missions SET title = 'Cross-tenant mutation' WHERE id = :mission_id"),
            {"mission_id": mission_a},
        )
        assert updated.rowcount == 0

    print("Quality Mission migration and tenant isolation probe passed")


if __name__ == "__main__":
    main()
