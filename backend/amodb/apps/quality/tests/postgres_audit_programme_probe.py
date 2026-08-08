from __future__ import annotations

import os
import subprocess
from uuid import uuid4

import sqlalchemy as sa
from sqlalchemy import create_engine, text

BASE_REVISION = "quality_260808_missions"
TARGET_REVISION = "quality_260808_audit_programme"
APP_ROLE = "amo_quality_programme_probe"


def _run_alembic(*args: str) -> None:
    subprocess.run(["alembic", "-c", "amodb/alembic.ini", *args], check=True, env=os.environ.copy())


def _bootstrap(engine: sa.Engine) -> dict[str, str]:
    ids = {key: str(uuid4()) for key in ("amo_a", "amo_b", "user_a", "user_b")}
    with engine.begin() as connection:
        connection.execute(text("DROP SCHEMA public CASCADE")); connection.execute(text("CREATE SCHEMA public"))
        connection.execute(text("GRANT ALL ON SCHEMA public TO public"))
        connection.execute(text("CREATE TABLE amos (id VARCHAR(36) PRIMARY KEY)"))
        connection.execute(text("CREATE TABLE users (id VARCHAR(36) PRIMARY KEY)"))
        connection.execute(text("INSERT INTO amos (id) VALUES (:amo_a), (:amo_b)"), ids)
        connection.execute(text("INSERT INTO users (id) VALUES (:user_a), (:user_b)"), ids)
        connection.execute(text(f"""DO $$ BEGIN IF NOT EXISTS (SELECT 1 FROM pg_roles WHERE rolname = '{APP_ROLE}')
            THEN CREATE ROLE {APP_ROLE} NOLOGIN; END IF; END $$"""))
    return ids


def _set_tenant(connection, amo_id: str, user_id: str) -> None:
    connection.execute(text("SELECT set_config('app.tenant_id', :v, true)"), {"v": amo_id})
    connection.execute(text("SELECT set_config('app.user_id', :v, true)"), {"v": user_id})


def _rls_state(connection, table: str) -> tuple[bool, bool]:
    row = connection.execute(text("""SELECT c.relrowsecurity, c.relforcerowsecurity FROM pg_class c
        JOIN pg_namespace n ON n.oid=c.relnamespace WHERE n.nspname=current_schema() AND c.relname=:table"""), {"table": table}).one()
    return bool(row.relrowsecurity), bool(row.relforcerowsecurity)


def main() -> None:
    engine = create_engine(os.environ["DATABASE_URL"]); ids = _bootstrap(engine)
    _run_alembic("stamp", BASE_REVISION); _run_alembic("upgrade", TARGET_REVISION)
    tables = ("quality_audit_programmes", "quality_audit_universe_items", "quality_audit_programme_items", "quality_audit_programme_events")
    with engine.begin() as connection:
        assert connection.execute(text("SELECT version_num FROM alembic_version")).scalar_one() == TARGET_REVISION
        for table in tables:
            assert _rls_state(connection, table) == (True, True)
            assert connection.execute(text("SELECT COUNT(*) FROM pg_policies WHERE schemaname=current_schema() AND tablename=:t"), {"t": table}).scalar_one() == 1
        connection.execute(text(f"GRANT USAGE ON SCHEMA public TO {APP_ROLE}"))
        connection.execute(text(f"GRANT SELECT, INSERT, UPDATE, DELETE ON ALL TABLES IN SCHEMA public TO {APP_ROLE}"))

    programme = str(uuid4()); universe = str(uuid4()); item = str(uuid4()); event = str(uuid4())
    with engine.begin() as connection:
        connection.execute(text(f"SET LOCAL ROLE {APP_ROLE}")); _set_tenant(connection, ids["amo_a"], ids["user_a"])
        connection.execute(text("""INSERT INTO quality_audit_programmes
            (id,amo_id,programme_ref,programme_series,programme_year,revision_no,title,objectives,regulatory_basis,status,period_start,period_end,owner_user_id,created_by_user_id,updated_by_user_id,created_at,updated_at)
            VALUES (:id,:amo,'AP-2026-PROBE-R01','AP-2026-PROBE',2026,1,'2026 Audit Programme',CAST('[]' AS json),CAST('[]' AS json),'DRAFT','2026-01-01','2026-12-31',:user,:user,:user,NOW(),NOW())"""),
            {"id": programme, "amo": ids["amo_a"], "user": ids["user_a"]})
        connection.execute(text("""INSERT INTO quality_audit_universe_items
            (id,amo_id,entity_type,display_label,source_owner_module,source_type,source_id,risk_classification,regulatory_criticality,mandatory_surveillance,active,created_by_user_id,updated_by_user_id,created_at,updated_at)
            VALUES (:id,:amo,'DEPARTMENT','Maintenance Department','workforce','DEPARTMENT','maintenance','HIGH','HIGH',true,true,:user,:user,NOW(),NOW())"""),
            {"id": universe, "amo": ids["amo_a"], "user": ids["user_a"]})
        connection.execute(text("""INSERT INTO quality_audit_programme_items
            (id,amo_id,programme_id,universe_item_id,audit_type,title,scope,criteria,mandatory_surveillance,recurrence,state,prioritization_basis,created_by_user_id,updated_by_user_id,created_at,updated_at)
            VALUES (:id,:amo,:programme,:universe,'DEPARTMENTAL','Maintenance Department Audit','Departmental quality system',CAST('[]' AS json),true,'ANNUAL','PLANNED',CAST('[]' AS json),:user,:user,NOW(),NOW())"""),
            {"id": item, "amo": ids["amo_a"], "programme": programme, "universe": universe, "user": ids["user_a"]})
        connection.execute(text("""INSERT INTO quality_audit_programme_events
            (id,amo_id,programme_id,event_type,reason,after_snapshot,actor_user_id,created_at)
            VALUES (:id,:amo,:programme,'CREATED','Programme created',CAST('{}' AS json),:user,NOW())"""),
            {"id": event, "amo": ids["amo_a"], "programme": programme, "user": ids["user_a"]})
        for table in tables:
            assert connection.execute(text(f"SELECT COUNT(*) FROM {table}")).scalar_one() == 1

    with engine.begin() as connection:
        connection.execute(text(f"SET LOCAL ROLE {APP_ROLE}")); _set_tenant(connection, ids["amo_b"], ids["user_b"])
        for table in tables:
            assert connection.execute(text(f"SELECT COUNT(*) FROM {table}")).scalar_one() == 0
        assert connection.execute(text("UPDATE quality_audit_programmes SET title='Cross tenant' WHERE id=:id"), {"id": programme}).rowcount == 0
        assert connection.execute(text("DELETE FROM quality_audit_programme_events WHERE id=:id"), {"id": event}).rowcount == 0

    print("Quality Audit Programme migration and tenant isolation probe passed")


if __name__ == "__main__":
    main()
