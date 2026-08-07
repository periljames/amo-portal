from __future__ import annotations

import os

from sqlalchemy import create_engine, text
from sqlalchemy.exc import DBAPIError


engine = create_engine(os.environ["DATABASE_URL"])
with engine.begin() as connection:
    numeric = {
        (row.table_name, row.column_name): (row.data_type, row.numeric_precision, row.numeric_scale)
        for row in connection.execute(text("""
            SELECT table_name, column_name, data_type, numeric_precision, numeric_scale
            FROM information_schema.columns
            WHERE (table_name = 'reliability_defect_trends' AND column_name IN ('utilisation_hours','utilisation_cycles','defect_rate_per_100_fh'))
               OR (table_name = 'reliability_kpis' AND column_name IN ('value','numerator','denominator'))
        """)).mappings()
    }
    assert all(value[0] == "numeric" for value in numeric.values()), numeric
    expected_triggers = {
        "trg_rel_statistical_alert_results_append_only",
        "trg_rel_workbook_report_snapshots_append_only",
        "trg_rel_workbook_record_approved_immutable",
        "trg_rel_completed_import_evidence_immutable",
        "trg_rel_completed_import_batch_immutable",
    }
    triggers = set(connection.execute(text("""
        SELECT tgname FROM pg_trigger
        WHERE NOT tgisinternal AND tgname LIKE 'trg_rel_%'
    """)).scalars())
    assert expected_triggers <= triggers, sorted(expected_triggers - triggers)

    connection.execute(text("CREATE TEMP TABLE reference_evidence_probe (id integer primary key, value integer not null)"))
    connection.execute(text("""
        CREATE TRIGGER reference_evidence_probe_immutable
        BEFORE UPDATE OR DELETE ON reference_evidence_probe
        FOR EACH ROW EXECUTE FUNCTION prevent_reliability_reference_evidence_mutation()
    """))
    connection.execute(text("INSERT INTO reference_evidence_probe (id, value) VALUES (1, 1)"))
    savepoint = connection.begin_nested()
    try:
        connection.execute(text("UPDATE reference_evidence_probe SET value = 2 WHERE id = 1"))
    except DBAPIError as exc:
        savepoint.rollback()
        assert "append-only" in str(exc.orig)
    else:
        raise AssertionError("Reference-evidence append-only trigger allowed an UPDATE")

print("PostgreSQL workbook-reference exactness and immutability regression passed")
