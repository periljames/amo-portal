from __future__ import annotations

import os
import subprocess
from uuid import uuid4

import sqlalchemy as sa
from sqlalchemy import create_engine, text

BASE_REVISION = "quality_260809_programme_occ"
TARGET_REVISION = "quality_260809_effect_response"
APP_ROLE = "amo_quality_effect_response_probe"
TABLES = ("quality_effectiveness_response_actions", "quality_effectiveness_response_events")


def _run_alembic(*args: str) -> None:
    subprocess.run(["alembic", "-c", "amodb/alembic.ini", *args], check=True, env=os.environ.copy())


def _set_tenant(connection, amo_id: str, user_id: str) -> None:
    connection.execute(text("SELECT set_config('app.tenant_id', :v, true)"), {"v": amo_id})
    connection.execute(text("SELECT set_config('app.user_id', :v, true)"), {"v": user_id})


def main() -> None:
    engine = create_engine(os.environ["DATABASE_URL"])
    ids = {key: str(uuid4()) for key in ("amo_a", "amo_b", "user_a", "user_b", "case", "plan", "schedule", "action", "event")}
    with engine.begin() as connection:
        connection.execute(text("DROP SCHEMA public CASCADE"))
        connection.execute(text("CREATE SCHEMA public"))
        connection.execute(text("GRANT ALL ON SCHEMA public TO public"))
        connection.execute(text("CREATE TABLE amos (id VARCHAR(36) PRIMARY KEY)"))
        connection.execute(text("CREATE TABLE users (id VARCHAR(36) PRIMARY KEY)"))
        connection.execute(text("CREATE TABLE quality_assurance_cases (id VARCHAR(36) PRIMARY KEY)"))
        connection.execute(text("CREATE TABLE quality_effectiveness_plans (id VARCHAR(36) PRIMARY KEY)"))
        connection.execute(text("CREATE TABLE qms_audit_schedules (id UUID PRIMARY KEY)"))
        connection.execute(text("INSERT INTO amos (id) VALUES (:amo_a), (:amo_b)"), ids)
        connection.execute(text("INSERT INTO users (id) VALUES (:user_a), (:user_b)"), ids)
        connection.execute(text("INSERT INTO quality_assurance_cases (id) VALUES (:case)"), ids)
        connection.execute(text("INSERT INTO quality_effectiveness_plans (id) VALUES (:plan)"), ids)
        connection.execute(text("INSERT INTO qms_audit_schedules (id) VALUES (:schedule)"), ids)
        connection.execute(text(f"""DO $$ BEGIN IF NOT EXISTS (SELECT 1 FROM pg_roles WHERE rolname = '{APP_ROLE}')
            THEN CREATE ROLE {APP_ROLE} NOLOGIN; END IF; END $$"""))

    _run_alembic("stamp", BASE_REVISION)
    _run_alembic("upgrade", TARGET_REVISION)

    with engine.begin() as connection:
        assert connection.execute(text("SELECT version_num FROM alembic_version")).scalar_one() == TARGET_REVISION
        for table in TABLES:
            state = connection.execute(text("""
                SELECT c.relrowsecurity, c.relforcerowsecurity
                FROM pg_class c JOIN pg_namespace n ON n.oid=c.relnamespace
                WHERE n.nspname=current_schema() AND c.relname=:table
            """), {"table": table}).one()
            assert (bool(state.relrowsecurity), bool(state.relforcerowsecurity)) == (True, True), table
            assert connection.execute(text("SELECT COUNT(*) FROM pg_policies WHERE schemaname=current_schema() AND tablename=:table"), {"table": table}).scalar_one() == 1, table
        connection.execute(text(f"GRANT USAGE ON SCHEMA public TO {APP_ROLE}"))
        connection.execute(text(f"GRANT SELECT, INSERT, UPDATE, DELETE ON ALL TABLES IN SCHEMA public TO {APP_ROLE}"))

    with engine.begin() as connection:
        connection.execute(text(f"SET LOCAL ROLE {APP_ROLE}"))
        _set_tenant(connection, ids["amo_a"], ids["user_a"])
        connection.execute(text("""INSERT INTO quality_effectiveness_response_actions
            (id,amo_id,case_id,effectiveness_plan_id,action_type,status,rationale,target_source_type,target_source_id,target_route,schedule_id,due_date,owner_user_id,source_snapshot,created_by_user_id,created_at)
            VALUES (:id,:amo,:case,:plan,'FOLLOW_UP_AUDIT','OPEN','Ineffective action requires follow-up audit','AUDIT_SCHEDULE',:schedule,'/quality/calendar/week',:schedule,CURRENT_DATE + 30,:user,CAST('{}' AS json),:user,NOW())"""),
            {"id": ids["action"], "amo": ids["amo_a"], "case": ids["case"], "plan": ids["plan"], "schedule": ids["schedule"], "user": ids["user_a"]})
        connection.execute(text("""INSERT INTO quality_effectiveness_response_events
            (id,amo_id,case_id,response_action_id,event_type,reason,snapshot,actor_user_id,created_at)
            VALUES (:id,:amo,:case,:action,'OPENED','Follow-up audit obligation opened',CAST('{}' AS json),:user,NOW())"""),
            {"id": ids["event"], "amo": ids["amo_a"], "case": ids["case"], "action": ids["action"], "user": ids["user_a"]})
        for table in TABLES:
            assert connection.execute(text(f"SELECT COUNT(*) FROM {table}")).scalar_one() == 1

    with engine.begin() as connection:
        connection.execute(text(f"SET LOCAL ROLE {APP_ROLE}"))
        _set_tenant(connection, ids["amo_b"], ids["user_b"])
        for table in TABLES:
            assert connection.execute(text(f"SELECT COUNT(*) FROM {table}")).scalar_one() == 0

    try:
        with engine.begin() as connection:
            connection.execute(text(f"SET LOCAL ROLE {APP_ROLE}"))
            _set_tenant(connection, ids["amo_a"], ids["user_a"])
            connection.execute(text("UPDATE quality_effectiveness_response_events SET reason='mutated' WHERE id=:id"), {"id": ids["event"]})
    except Exception as exc:
        assert "append-only" in str(exc).lower()
    else:
        raise AssertionError("effectiveness response event accepted mutation")

    print("Quality effectiveness response RLS and immutable history probe passed")


if __name__ == "__main__":
    main()
