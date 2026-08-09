from __future__ import annotations

import os
import subprocess
from uuid import uuid4

from sqlalchemy import create_engine, text

BASE_REVISION = "quality_260809_effect_response"
TARGET_REVISION = "quality_260809_checklist_exec"
APP_ROLE = "amo_quality_checklist_exec_probe"
STATE_TABLE = "quality_audit_checklist_execution_governance"
EVENT_TABLE = "quality_audit_checklist_execution_events"


def _run_alembic(*args: str) -> None:
    subprocess.run(["alembic", "-c", "amodb/alembic.ini", *args], check=True, env=os.environ.copy())


def _set_tenant(connection, amo_id: str, user_id: str) -> None:
    connection.execute(text("SELECT set_config('app.tenant_id', :v, true)"), {"v": amo_id})
    connection.execute(text("SELECT set_config('app.user_id', :v, true)"), {"v": user_id})


def main() -> None:
    engine = create_engine(os.environ["DATABASE_URL"])
    ids = {key: str(uuid4()) for key in ("amo_a", "amo_b", "user_a", "user_b", "audit", "item", "state", "event")}
    with engine.begin() as connection:
        connection.execute(text("DROP SCHEMA public CASCADE"))
        connection.execute(text("CREATE SCHEMA public"))
        connection.execute(text("GRANT ALL ON SCHEMA public TO public"))
        connection.execute(text("CREATE TABLE amos (id VARCHAR(36) PRIMARY KEY)"))
        connection.execute(text("CREATE TABLE users (id VARCHAR(36) PRIMARY KEY)"))
        connection.execute(text("CREATE TABLE qms_audits (id UUID PRIMARY KEY)"))
        connection.execute(text("CREATE TABLE quality_audit_checklist_items (id UUID PRIMARY KEY)"))
        connection.execute(text("INSERT INTO amos (id) VALUES (:amo_a), (:amo_b)"), ids)
        connection.execute(text("INSERT INTO users (id) VALUES (:user_a), (:user_b)"), ids)
        connection.execute(text("INSERT INTO qms_audits (id) VALUES (:audit)"), ids)
        connection.execute(text("INSERT INTO quality_audit_checklist_items (id) VALUES (:item)"), ids)
        connection.execute(text(f"""DO $$ BEGIN IF NOT EXISTS (SELECT 1 FROM pg_roles WHERE rolname = '{APP_ROLE}')
            THEN CREATE ROLE {APP_ROLE} NOLOGIN; END IF; END $$"""))

    _run_alembic("stamp", BASE_REVISION)
    _run_alembic("upgrade", TARGET_REVISION)

    with engine.begin() as connection:
        assert connection.execute(text("SELECT version_num FROM alembic_version")).scalar_one() == TARGET_REVISION
        for table_name in (STATE_TABLE, EVENT_TABLE):
            state = connection.execute(text("""
                SELECT c.relrowsecurity, c.relforcerowsecurity
                FROM pg_class c JOIN pg_namespace n ON n.oid=c.relnamespace
                WHERE n.nspname=current_schema() AND c.relname=:table
            """), {"table": table_name}).one()
            assert (bool(state.relrowsecurity), bool(state.relforcerowsecurity)) == (True, True)
            assert connection.execute(text("SELECT COUNT(*) FROM pg_policies WHERE schemaname=current_schema() AND tablename=:table"), {"table": table_name}).scalar_one() == 1
        connection.execute(text(f"GRANT USAGE ON SCHEMA public TO {APP_ROLE}"))
        connection.execute(text(f"GRANT SELECT, INSERT, UPDATE, DELETE ON {STATE_TABLE}, {EVENT_TABLE} TO {APP_ROLE}"))

    with engine.begin() as connection:
        connection.execute(text(f"SET LOCAL ROLE {APP_ROLE}"))
        _set_tenant(connection, ids["amo_a"], ids["user_a"])
        connection.execute(text(f"""INSERT INTO {STATE_TABLE}
            (id,amo_id,audit_id,checklist_item_id,canonical_response_status,auditor_notes,evidence_references,updated_by_user_id,created_at,updated_at)
            VALUES (:state,:amo,:audit,:item,'NONCOMPLIANT','Evidence gap',CAST('[\"DMS:DOC-1@REV-2\"]' AS json),:user,NOW(),NOW())"""),
            {"state": ids["state"], "amo": ids["amo_a"], "audit": ids["audit"], "item": ids["item"], "user": ids["user_a"]})
        connection.execute(text(f"""INSERT INTO {EVENT_TABLE}
            (id,amo_id,audit_id,checklist_item_id,governance_id,event_type,reason,before_snapshot,after_snapshot,actor_user_id,created_at)
            VALUES (:event,:amo,:audit,:item,:state,'CREATED','Initial governed execution',NULL,CAST('{{\"canonical_response_status\":\"NONCOMPLIANT\"}}' AS json),:user,NOW())"""),
            {"event": ids["event"], "amo": ids["amo_a"], "audit": ids["audit"], "item": ids["item"], "state": ids["state"], "user": ids["user_a"]})
        assert connection.execute(text(f"SELECT COUNT(*) FROM {STATE_TABLE}")).scalar_one() == 1
        assert connection.execute(text(f"SELECT COUNT(*) FROM {EVENT_TABLE}")).scalar_one() == 1

    with engine.begin() as connection:
        connection.execute(text(f"SET LOCAL ROLE {APP_ROLE}"))
        _set_tenant(connection, ids["amo_b"], ids["user_b"])
        assert connection.execute(text(f"SELECT COUNT(*) FROM {STATE_TABLE}")).scalar_one() == 0
        assert connection.execute(text(f"SELECT COUNT(*) FROM {EVENT_TABLE}")).scalar_one() == 0

    try:
        with engine.begin() as connection:
            connection.execute(text(f"SET LOCAL ROLE {APP_ROLE}"))
            _set_tenant(connection, ids["amo_a"], ids["user_a"])
            connection.execute(text(f"UPDATE {EVENT_TABLE} SET reason='mutated' WHERE id=:id"), {"id": ids["event"]})
    except Exception as exc:
        assert "append-only" in str(exc).lower()
    else:
        raise AssertionError("checklist execution event history accepted a mutation")

    print("Quality checklist execution governance RLS and append-only event probe passed")


if __name__ == "__main__":
    main()
