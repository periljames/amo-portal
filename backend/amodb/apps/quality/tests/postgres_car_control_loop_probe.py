from __future__ import annotations

import os
import subprocess
from uuid import uuid4

import sqlalchemy as sa
from sqlalchemy import create_engine, text


BASE_REVISION = "docctl_ai_audit_260809"
TARGET_REVISION = "quality_260811_car_loop"
TABLES = (
    "quality_car_control_profiles",
    "quality_car_milestones",
    "quality_car_dependencies",
    "quality_car_deadline_changes",
    "quality_car_control_events",
)


def _run_alembic(*arguments: str) -> None:
    subprocess.run(
        ["alembic", "-c", "amodb/alembic.ini", *arguments],
        check=True,
        env=os.environ.copy(),
    )


def _create_minimal_baseline(engine: sa.Engine) -> None:
    with engine.begin() as connection:
        connection.execute(text("CREATE TABLE IF NOT EXISTS amos (id VARCHAR(36) PRIMARY KEY)"))
        connection.execute(
            text(
                """
                CREATE TABLE IF NOT EXISTS users (
                    id VARCHAR(36) PRIMARY KEY,
                    amo_id VARCHAR(36),
                    is_active BOOLEAN DEFAULT TRUE,
                    is_system_account BOOLEAN DEFAULT FALSE
                )
                """
            )
        )
        connection.execute(
            text(
                """
                CREATE TABLE IF NOT EXISTS quality_cars (
                    id UUID PRIMARY KEY,
                    amo_id VARCHAR(36) NOT NULL
                )
                """
            )
        )


def _assert_rls(connection: sa.Connection, table_name: str) -> None:
    flags = connection.execute(
        text(
            """
            SELECT relrowsecurity, relforcerowsecurity
            FROM pg_class
            WHERE oid = CAST(:table_name AS regclass)
            """
        ),
        {"table_name": table_name},
    ).one()
    assert flags.relrowsecurity is True, (table_name, flags)
    assert flags.relforcerowsecurity is True, (table_name, flags)
    policy_count = connection.execute(
        text("SELECT COUNT(*) FROM pg_policies WHERE schemaname = current_schema() AND tablename = :table_name"),
        {"table_name": table_name},
    ).scalar_one()
    assert policy_count == 1, (table_name, policy_count)


def main() -> None:
    engine = create_engine(os.environ["DATABASE_URL"])
    _create_minimal_baseline(engine)
    _run_alembic("stamp", BASE_REVISION)
    _run_alembic("upgrade", TARGET_REVISION)

    amo_id = str(uuid4())
    user_id = str(uuid4())
    car_id = str(uuid4())
    with engine.begin() as connection:
        revision = connection.execute(text("SELECT version_num FROM alembic_version")).scalar_one()
        assert revision == TARGET_REVISION

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

        for table_name in TABLES:
            _assert_rls(connection, table_name)

        connection.execute(text("INSERT INTO amos (id) VALUES (:amo_id)"), {"amo_id": amo_id})
        connection.execute(text("INSERT INTO users (id, amo_id) VALUES (:user_id, :amo_id)"), {"user_id": user_id, "amo_id": amo_id})
        connection.execute(text("INSERT INTO quality_cars (id, amo_id) VALUES (CAST(:car_id AS uuid), :amo_id)"), {"car_id": car_id, "amo_id": amo_id})
        connection.execute(text("SELECT set_config('app.tenant_id', :amo_id, true)"), {"amo_id": amo_id})
        profile_id = str(uuid4())
        connection.execute(
            text(
                """
                INSERT INTO quality_car_control_profiles (
                    id, amo_id, car_id, accountable_owner_user_id,
                    original_due_date, current_due_date, effectiveness_required,
                    initialized_from, created_at, updated_at
                ) VALUES (
                    CAST(:profile_id AS uuid), :amo_id, CAST(:car_id AS uuid), :user_id,
                    DATE '2026-09-30', DATE '2026-09-30', TRUE,
                    'CAR', NOW(), NOW()
                )
                """
            ),
            {"profile_id": profile_id, "amo_id": amo_id, "car_id": car_id, "user_id": user_id},
        )
        milestone_id = str(uuid4())
        connection.execute(
            text(
                """
                INSERT INTO quality_car_milestones (
                    id, amo_id, profile_id, car_id, milestone_key, phase_order, title,
                    owner_user_id, original_due_date, current_due_date, status, created_at, updated_at
                ) VALUES (
                    CAST(:milestone_id AS uuid), :amo_id, CAST(:profile_id AS uuid), CAST(:car_id AS uuid),
                    'RCA_SUBMISSION', 1, 'Root cause analysis submitted', :user_id,
                    DATE '2026-08-25', DATE '2026-08-25', 'PLANNED', NOW(), NOW()
                )
                """
            ),
            {"milestone_id": milestone_id, "profile_id": profile_id, "car_id": car_id, "amo_id": amo_id, "user_id": user_id},
        )
        stored = connection.execute(
            text("SELECT milestone_key, phase_order, status FROM quality_car_milestones WHERE id = CAST(:milestone_id AS uuid)"),
            {"milestone_id": milestone_id},
        ).one()
        assert tuple(stored) == ("RCA_SUBMISSION", 1, "PLANNED")

    print("CAR control-loop migration, constraints and RLS contract verified")


if __name__ == "__main__":
    main()
