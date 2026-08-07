"""PostgreSQL schema regression for operational Reliability source integrity."""
from __future__ import annotations

import os
from datetime import date, datetime, timezone

from sqlalchemy import create_engine, text
from sqlalchemy.exc import DBAPIError
from sqlalchemy.orm import Session


EXPECTED_TABLES = {
    "reliability_flight_operations",
    "reliability_mel_cdl_deferrals",
    "reliability_component_shop_findings",
    "reliability_sms_occurrences",
    "reliability_workbook_imports",
    "reliability_workbook_rows",
    "reliability_source_revision_events",
}

REQUIRED_HOUR_COLUMNS = {
    ("aircraft", "total_hours"),
    ("aircraft_usage", "block_hours"),
    ("aircraft_components", "current_hours"),
}
REQUIRED_COUNT_COLUMNS = {
    ("aircraft", "total_cycles"),
    ("aircraft_usage", "cycles"),
    ("aircraft_components", "current_cycles"),
}
OPTIONAL_HOUR_COLUMNS = {
    ("technical_aircraft_utilisation", "hours"),
}
OPTIONAL_COUNT_COLUMNS = {
    ("technical_aircraft_utilisation", "cycles"),
}


def main() -> None:
    engine = create_engine(os.environ["DATABASE_URL"])
    with engine.begin() as connection:
        tables = {
            row[0]
            for row in connection.execute(text("""
                SELECT table_name
                FROM information_schema.tables
                WHERE table_schema = 'public'
            """))
        }
        missing = EXPECTED_TABLES - tables
        assert not missing, sorted(missing)

        trigger_count = connection.execute(text("""
            SELECT COUNT(*)
            FROM pg_trigger
            WHERE tgname = 'trg_rel_source_revision_append_only'
              AND NOT tgisinternal
        """)).scalar_one()
        assert trigger_count == 1, trigger_count

        target_columns = REQUIRED_HOUR_COLUMNS | REQUIRED_COUNT_COLUMNS | OPTIONAL_HOUR_COLUMNS | OPTIONAL_COUNT_COLUMNS
        columns = {
            (row.table_name, row.column_name): (row.data_type, row.numeric_precision, row.numeric_scale)
            for row in connection.execute(text("""
                SELECT table_name, column_name, data_type, numeric_precision, numeric_scale
                FROM information_schema.columns
                WHERE (table_name, column_name) IN (
                    ('aircraft', 'total_hours'),
                    ('aircraft', 'total_cycles'),
                    ('aircraft_usage', 'block_hours'),
                    ('aircraft_usage', 'cycles'),
                    ('aircraft_components', 'current_hours'),
                    ('aircraft_components', 'current_cycles'),
                    ('technical_aircraft_utilisation', 'hours'),
                    ('technical_aircraft_utilisation', 'cycles')
                )
            """))
        }
        assert REQUIRED_HOUR_COLUMNS <= columns.keys(), sorted(REQUIRED_HOUR_COLUMNS - columns.keys())
        assert REQUIRED_COUNT_COLUMNS <= columns.keys(), sorted(REQUIRED_COUNT_COLUMNS - columns.keys())
        assert set(columns) <= target_columns, sorted(set(columns) - target_columns)

        for key in REQUIRED_HOUR_COLUMNS | (OPTIONAL_HOUR_COLUMNS & columns.keys()):
            assert columns[key][0] == "numeric", (key, columns[key])
            assert columns[key][2] == 3, (key, columns[key])
        for key in REQUIRED_COUNT_COLUMNS | (OPTIONAL_COUNT_COLUMNS & columns.keys()):
            assert columns[key][0] == "bigint", (key, columns[key])

        revision_id = "00000000-0000-7000-8000-000000000091"
        connection.execute(text("SET LOCAL session_replication_role = replica"))
        connection.execute(text("""
            INSERT INTO reliability_source_revision_events (
                id, amo_id, source_type, source_id, revision, action,
                payload_json, actor_user_id, created_at
            ) VALUES (
                :id, '00000000-0000-7000-8000-000000000001',
                'FLIGHT_OPERATION', '00000000-0000-7000-8000-000000000092',
                1, 'CREATED', CAST('{}' AS jsonb), NULL, NOW()
            )
        """), {"id": revision_id})
        connection.execute(text("SET LOCAL session_replication_role = origin"))

        connection.execute(text("SAVEPOINT source_append_only_check"))
        try:
            connection.execute(text("""
                UPDATE reliability_source_revision_events
                SET action = 'ALTERED'
                WHERE id = :id
            """), {"id": revision_id})
        except DBAPIError:
            connection.execute(text("ROLLBACK TO SAVEPOINT source_append_only_check"))
        else:
            raise AssertionError("source-revision append-only trigger permitted an update")

        action = connection.execute(text("""
            SELECT action FROM reliability_source_revision_events WHERE id = :id
        """), {"id": revision_id}).scalar_one()
        assert action == "CREATED", action

        # Execute the formal long-term aggregation SQL against the real PostgreSQL
        # schema with an empty tenant population. This catches PostgreSQL-only SQL,
        # JSONB, date-truncation and expanding-parameter regressions that SQLite
        # unit tests cannot exercise.
        from amodb.apps.reliability.formal_reporting_history import (
            _domain_rows,
            _event_rows,
            _utilisation_rows,
        )

        session = Session(bind=connection)
        params = {
            "amo_id": "00000000-0000-7000-8000-000000000099",
            "start_date": date(2024, 1, 1),
            "end_date": date(2026, 12, 31),
            "cutoff": datetime(2026, 12, 31, 23, 59, tzinfo=timezone.utc),
            "aircraft": [],
            "use_aircraft": False,
        }
        assert _utilisation_rows(session, params) == []
        assert _event_rows(session, params) == []
        assert _domain_rows(session, params) == []
        params["aircraft"] = ["5Y-TEST"]
        params["use_aircraft"] = True
        assert _utilisation_rows(session, params) == []
        assert _event_rows(session, params) == []
        assert _domain_rows(session, params) == []

    print("PostgreSQL operational-source integrity regression passed")


if __name__ == "__main__":
    main()
