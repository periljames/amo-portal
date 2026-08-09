from __future__ import annotations

import os
import subprocess
from uuid import uuid4

import sqlalchemy as sa
from sqlalchemy import create_engine, text

BASE_REVISION = "merge_260809_qms_reliability"
TARGET_REVISION = "quality_260809_programme_occ"
APP_ROLE = "amo_quality_occurrence_probe"
TABLE = "quality_audit_programme_occurrence_links"


def _run_alembic(*args: str) -> None:
    subprocess.run(["alembic", "-c", "amodb/alembic.ini", *args], check=True, env=os.environ.copy())


def _set_tenant(connection, amo_id: str, user_id: str) -> None:
    connection.execute(text("SELECT set_config('app.tenant_id', :v, true)"), {"v": amo_id})
    connection.execute(text("SELECT set_config('app.user_id', :v, true)"), {"v": user_id})


def main() -> None:
    engine = create_engine(os.environ["DATABASE_URL"])
    ids = {key: str(uuid4()) for key in ("amo_a", "amo_b", "user_a", "user_b", "programme", "item", "schedule", "signal", "link")}
    with engine.begin() as connection:
        connection.execute(text("DROP SCHEMA public CASCADE"))
        connection.execute(text("CREATE SCHEMA public"))
        connection.execute(text("GRANT ALL ON SCHEMA public TO public"))
        connection.execute(text("CREATE TABLE amos (id VARCHAR(36) PRIMARY KEY)"))
        connection.execute(text("CREATE TABLE users (id VARCHAR(36) PRIMARY KEY)"))
        connection.execute(text("CREATE TABLE quality_audit_programmes (id VARCHAR(36) PRIMARY KEY)"))
        connection.execute(text("CREATE TABLE quality_audit_programme_items (id VARCHAR(36) PRIMARY KEY)"))
        connection.execute(text("CREATE TABLE qms_audit_schedules (id UUID PRIMARY KEY)"))
        connection.execute(text("CREATE TABLE quality_signal_observations (id VARCHAR(36) PRIMARY KEY)"))
        connection.execute(text("INSERT INTO amos (id) VALUES (:amo_a), (:amo_b)"), ids)
        connection.execute(text("INSERT INTO users (id) VALUES (:user_a), (:user_b)"), ids)
        connection.execute(text("INSERT INTO quality_audit_programmes (id) VALUES (:programme)"), ids)
        connection.execute(text("INSERT INTO quality_audit_programme_items (id) VALUES (:item)"), ids)
        connection.execute(text("INSERT INTO qms_audit_schedules (id) VALUES (:schedule)"), ids)
        connection.execute(text("INSERT INTO quality_signal_observations (id) VALUES (:signal)"), ids)
        connection.execute(text(f"""DO $$ BEGIN IF NOT EXISTS (SELECT 1 FROM pg_roles WHERE rolname = '{APP_ROLE}')
            THEN CREATE ROLE {APP_ROLE} NOLOGIN; END IF; END $$"""))

    _run_alembic("stamp", BASE_REVISION)
    _run_alembic("upgrade", TARGET_REVISION)

    with engine.begin() as connection:
        assert connection.execute(text("SELECT version_num FROM alembic_version")).scalar_one() == TARGET_REVISION
        state = connection.execute(text("""
            SELECT c.relrowsecurity, c.relforcerowsecurity
            FROM pg_class c JOIN pg_namespace n ON n.oid=c.relnamespace
            WHERE n.nspname=current_schema() AND c.relname=:table
        """), {"table": TABLE}).one()
        assert (bool(state.relrowsecurity), bool(state.relforcerowsecurity)) == (True, True)
        assert connection.execute(text("SELECT COUNT(*) FROM pg_policies WHERE schemaname=current_schema() AND tablename=:table"), {"table": TABLE}).scalar_one() == 1
        connection.execute(text(f"GRANT USAGE ON SCHEMA public TO {APP_ROLE}"))
        connection.execute(text(f"GRANT SELECT, INSERT, UPDATE, DELETE ON {TABLE} TO {APP_ROLE}"))

    with engine.begin() as connection:
        connection.execute(text(f"SET LOCAL ROLE {APP_ROLE}"))
        _set_tenant(connection, ids["amo_a"], ids["user_a"])
        connection.execute(text("""INSERT INTO quality_audit_programme_occurrence_links
            (id,amo_id,programme_id,programme_item_id,schedule_id,occurrence_type,occurrence_key,source_signal_id,rationale,source_snapshot,created_by_user_id,created_at)
            VALUES (:id,:amo,:programme,:item,:schedule,'RISK_TRIGGERED','signal-occurrence-1',:signal,'Triggered by governed signal',CAST('{}' AS json),:user,NOW())"""),
            {"id": ids["link"], "amo": ids["amo_a"], "programme": ids["programme"], "item": ids["item"], "schedule": ids["schedule"], "signal": ids["signal"], "user": ids["user_a"]})
        assert connection.execute(text(f"SELECT COUNT(*) FROM {TABLE}")).scalar_one() == 1

    with engine.begin() as connection:
        connection.execute(text(f"SET LOCAL ROLE {APP_ROLE}"))
        _set_tenant(connection, ids["amo_b"], ids["user_b"])
        assert connection.execute(text(f"SELECT COUNT(*) FROM {TABLE}")).scalar_one() == 0

    try:
        with engine.begin() as connection:
            connection.execute(text(f"SET LOCAL ROLE {APP_ROLE}"))
            _set_tenant(connection, ids["amo_a"], ids["user_a"])
            connection.execute(text(f"UPDATE {TABLE} SET rationale='mutated' WHERE id=:id"), {"id": ids["link"]})
    except Exception as exc:
        assert "immutable" in str(exc).lower()
    else:
        raise AssertionError("programme occurrence lineage accepted a mutation")

    print("Quality custom/risk-triggered programme occurrence RLS and immutability probe passed")


if __name__ == "__main__":
    main()
