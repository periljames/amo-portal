"""PostgreSQL-only schema regression for immutable calculation revisions."""
import os

from sqlalchemy import create_engine, text
from sqlalchemy.exc import DBAPIError


def main() -> None:
    engine = create_engine(os.environ["DATABASE_URL"])
    with engine.begin() as connection:
        trigger_count = connection.execute(text("""
            SELECT COUNT(*)
            FROM pg_trigger
            WHERE tgname = 'trg_reliability_calculation_runs_append_only'
              AND NOT tgisinternal
        """)).scalar_one()
        assert trigger_count == 1, trigger_count

        identity = {
            "amo_id": "00000000-0000-7000-8000-000000000001",
            "metric_id": "00000000-0000-7000-8000-000000000002",
        }
        connection.execute(text("SET LOCAL session_replication_role = replica"))
        for revision, numerator, digest in ((1, 1, "a" * 64), (2, 2, "b" * 64)):
            connection.execute(text("""
                INSERT INTO reliability_calculation_runs (
                    id, amo_id, metric_definition_id, scope_type, scope_id,
                    period_start, period_end, numerator, denominator, value,
                    sample_size, small_fleet, status, formula_version, revision,
                    source_cutoff_at, source_lineage_json, result_hash, scheduled, created_at
                ) VALUES (
                    :id, :amo_id, :metric_id, 'FLEET', 'FLEET',
                    DATE '2026-08-01', DATE '2026-08-31', :numerator, 10, :numerator,
                    :numerator, false, 'VALID', '1', :revision,
                    NOW(), CAST(:lineage AS jsonb), :digest, false, NOW()
                )
            """), {
                "id": f"00000000-0000-7000-8000-00000000000{revision + 2}",
                "amo_id": identity["amo_id"],
                "metric_id": identity["metric_id"],
                "numerator": numerator,
                "revision": revision,
                "lineage": f'{{"revision": {revision}}}',
                "digest": digest,
            })
        connection.execute(text("SET LOCAL session_replication_role = origin"))
        rows = connection.execute(text("""
            SELECT revision, numerator
            FROM reliability_calculation_runs
            WHERE amo_id = :amo_id AND metric_definition_id = :metric_id
            ORDER BY revision
        """), identity).all()
        assert [(row.revision, int(row.numerator)) for row in rows] == [(1, 1), (2, 2)]

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
    print("PostgreSQL append-only revision regression passed")


if __name__ == "__main__":
    main()
