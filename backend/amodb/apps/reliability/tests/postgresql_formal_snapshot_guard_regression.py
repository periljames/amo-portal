"""PostgreSQL regression for the formal-report cutoff snapshot concurrency guard."""
from __future__ import annotations

import os

from sqlalchemy import create_engine, text
from sqlalchemy.exc import DBAPIError
from sqlalchemy.orm import Session

from amodb.apps.reliability.formal_reporting_snapshot_guard import lock_snapshot_sources


ESSENTIAL_LOCKED_TABLES = {
    "reliability_events",
    "reliability_workbook_records",
    "reliability_metric_definitions",
    "aircraft_utilization_daily",
    "aircraft",
}


def main() -> None:
    engine = create_engine(os.environ["DATABASE_URL"])

    with engine.connect() as freezer:
        transaction = freezer.begin()
        session = Session(bind=freezer)
        locked = set(lock_snapshot_sources(session))
        missing = ESSENTIAL_LOCKED_TABLES - locked
        assert not missing, f"formal snapshot guard did not include authoritative tables: {sorted(missing)}"

        held = {
            row.relname
            for row in freezer.execute(text("""
                SELECT c.relname
                FROM pg_locks l
                JOIN pg_class c ON c.oid = l.relation
                JOIN pg_namespace n ON n.oid = c.relnamespace
                WHERE l.pid = pg_backend_pid()
                  AND n.nspname = current_schema()
                  AND l.mode = 'ShareLock'
                  AND l.granted
            """))
        }
        missing_held = ESSENTIAL_LOCKED_TABLES - held
        assert not missing_held, f"expected PostgreSQL ShareLock not held: {sorted(missing_held)}"

        # A source writer requires ROW EXCLUSIVE and must be unable to overtake the
        # frozen-cutoff transaction while SHARE locks are held.
        with engine.connect() as writer:
            writer_transaction = writer.begin()
            writer.execute(text("SET LOCAL lock_timeout = '250ms'"))
            try:
                writer.execute(text("LOCK TABLE reliability_events IN ROW EXCLUSIVE MODE"))
            except DBAPIError:
                writer_transaction.rollback()
            else:
                writer_transaction.rollback()
                raise AssertionError("authoritative source writer was not blocked by formal snapshot guard")

        transaction.rollback()

    print("PostgreSQL formal Reliability snapshot concurrency regression passed")


if __name__ == "__main__":
    main()
