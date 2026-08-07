"""PostgreSQL-only schema regression for immutable calculation revisions."""
import hashlib
import json
import os

from sqlalchemy import create_engine, text
from sqlalchemy.exc import DBAPIError


def main() -> None:
    engine = create_engine(os.environ["DATABASE_URL"])
    with engine.begin() as connection:
        trigger = connection.execute(text("""
            SELECT COUNT(*) AS count, bool_and(tgenabled = 'O') AS enabled
            FROM pg_trigger
            WHERE tgname = 'trg_reliability_calculation_runs_append_only'
              AND NOT tgisinternal
        """)).one()
        assert trigger.count == 1, trigger.count
        assert trigger.enabled is True, trigger.enabled

        identity = {
            "amo_id": "00000000-0000-7000-8000-000000000001",
            "metric_id": "00000000-0000-7000-8000-000000000002",
        }
        formula_snapshot = {
            "code": "programme.TEST_RATE",
            "name": "Test rate",
            "version": "1",
            "origin": "PROGRAMME",
            "latex": r"R=\frac{N}{FH}\times100",
            "mathml": '<math xmlns="http://www.w3.org/1998/Math/MathML"><mrow><mfrac><mi>N</mi><mi>FH</mi></mfrac><mo>×</mo><mn>100</mn></mrow></math>',
            "expression": {"op": "multiply", "left": {"op": "divide", "numerator": "N", "denominator": "FH"}, "right": 100},
            "unit": "events / 100 FH",
            "precision": 3,
            "rounding_mode": "HALF_UP",
            "numerator_label": "Qualifying events",
            "denominator_label": "Recorded flight hours",
            "multiplier": 100,
            "methodology": "Regression fixture.",
            "denominator_policy": "Withhold when flight hours are absent.",
            "source_fields": ["reliability_events.id", "aircraft_utilization_daily.flight_hours"],
            "applied_to": ["test"],
        }
        snapshot_text = json.dumps(formula_snapshot, sort_keys=True, separators=(",", ":"))
        snapshot_hash = hashlib.sha256(snapshot_text.encode("utf-8")).hexdigest()

        connection.execute(text("SET LOCAL session_replication_role = replica"))
        for revision, numerator, digest in ((1, 1, "a" * 64), (2, 2, "b" * 64)):
            connection.execute(text("""
                INSERT INTO reliability_calculation_runs (
                    id, amo_id, metric_definition_id, scope_type, scope_id,
                    period_start, period_end, numerator, denominator, value,
                    sample_size, small_fleet, status, formula_version, revision,
                    source_cutoff_at, source_lineage_json, result_hash, scheduled, created_at,
                    formula_snapshot_json, formula_snapshot_hash
                ) VALUES (
                    :id, :amo_id, :metric_id, 'FLEET', 'FLEET',
                    DATE '2026-08-01', DATE '2026-08-31', :numerator, 10, :numerator,
                    :numerator, false, 'VALID', '1', :revision,
                    NOW(), CAST(:lineage AS jsonb), :digest, false, NOW(),
                    CAST(:snapshot AS jsonb), :snapshot_hash
                )
            """), {
                "id": f"00000000-0000-7000-8000-00000000000{revision + 2}",
                "amo_id": identity["amo_id"],
                "metric_id": identity["metric_id"],
                "numerator": numerator,
                "revision": revision,
                "lineage": json.dumps({"revision": revision, "formula_snapshot_hash": snapshot_hash}),
                "digest": digest,
                "snapshot": snapshot_text,
                "snapshot_hash": snapshot_hash,
            })
        connection.execute(text("SET LOCAL session_replication_role = origin"))
        rows = connection.execute(text("""
            SELECT revision, numerator, formula_snapshot_hash,
                   formula_snapshot_json ->> 'latex' AS latex
            FROM reliability_calculation_runs
            WHERE amo_id = :amo_id AND metric_definition_id = :metric_id
            ORDER BY revision
        """), identity).all()
        assert [(row.revision, int(row.numerator)) for row in rows] == [(1, 1), (2, 2)]
        assert all(row.formula_snapshot_hash == snapshot_hash for row in rows)
        assert all("\\frac" in row.latex for row in rows)

        connection.execute(text("SAVEPOINT append_only_check"))
        try:
            connection.execute(text("""
                UPDATE reliability_calculation_runs
                SET numerator = 99
                WHERE amo_id = :amo_id AND metric_definition_id = :metric_id AND revision = 1
            """), identity)
        except DBAPIError:
            connection.execute(text("ROLLBACK TO SAVEPOINT append_only_check"))
        else:
            raise AssertionError("append-only trigger permitted a calculation-run update")

        original = connection.execute(text("""
            SELECT numerator
            FROM reliability_calculation_runs
            WHERE amo_id = :amo_id AND metric_definition_id = :metric_id AND revision = 1
        """), identity).scalar_one()
        assert int(original) == 1
    print("PostgreSQL append-only revision and formula-snapshot regression passed")


if __name__ == "__main__":
    main()
