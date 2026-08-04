from pathlib import Path


def replace_once(path: str, old: str, new: str) -> None:
    file = Path(path)
    text = file.read_text(encoding="utf-8")
    count = text.count(old)
    if count != 1:
        raise SystemExit(f"{path}: expected one replacement, found {count}")
    file.write_text(text.replace(old, new, 1), encoding="utf-8")


model_path = "backend/amodb/apps/reliability/advanced_models.py"
replace_once(
    model_path,
    '''            "period_end",
            "formula_version",
            name="uq_reliability_calculation_identity",
        ),
        Index("ix_reliability_calculation_metric_period", "metric_definition_id", "period_end"),''',
    '''            "period_end",
            "formula_version",
            "revision",
            name="uq_reliability_calculation_identity",
        ),
        Index(
            "ix_reliability_calculation_identity_revision",
            "amo_id",
            "metric_definition_id",
            "scope_type",
            "scope_id",
            "period_start",
            "period_end",
            "formula_version",
            "revision",
        ),
        Index("ix_reliability_calculation_metric_period", "metric_definition_id", "period_end"),''',
)
replace_once(
    model_path,
    '''    status = Column(String(32), nullable=False, default="VALID", index=True)
    formula_version = Column(String(40), nullable=False)
    source_cutoff_at = Column(DateTime(timezone=True), nullable=False)''',
    '''    status = Column(String(32), nullable=False, default="VALID", index=True)
    formula_version = Column(String(40), nullable=False)
    revision = Column(Integer, nullable=False, default=1, server_default="1")
    source_cutoff_at = Column(DateTime(timezone=True), nullable=False)''',
)

service_path = "backend/amodb/apps/reliability/advanced_services.py"
replace_once(
    service_path,
    '''                    or parsed_delay < 0
                    or parsed_delay != parsed_delay.to_integral_value()
                ):''',
    '''                    or parsed_delay < 0
                    or parsed_delay > Decimal("2147483647")
                    or parsed_delay != parsed_delay.to_integral_value()
                ):''',
)

service = Path(service_path)
text_value = service.read_text(encoding="utf-8")
start = text_value.index("    result_hash = sha256_value(\n", text_value.index("def execute_metric("))
end_marker = '        audit_action = "CALCULATION_EXECUTED"\n'
end = text_value.index(end_marker, start) + len(end_marker)
replacement = '''    identity_payload = {
        "amo_id": amo_id,
        "metric_definition_id": metric.id,
        "scope_type": resolved_scope_type,
        "scope_id": resolved_scope_id,
        "period_start": start.isoformat(),
        "period_end": end.isoformat(),
        "formula_version": metric.formula_version,
    }
    if db.get_bind().dialect.name == "postgresql":
        db.execute(
            text("SELECT pg_advisory_xact_lock(hashtextextended(:identity_key, 0))"),
            {"identity_key": canonical_json(identity_payload)},
        )
    previous = (
        db.query(domain.ReliabilityCalculationRun)
        .filter(
            domain.ReliabilityCalculationRun.amo_id == amo_id,
            domain.ReliabilityCalculationRun.metric_definition_id == metric.id,
            domain.ReliabilityCalculationRun.scope_type == resolved_scope_type,
            domain.ReliabilityCalculationRun.scope_id == resolved_scope_id,
            domain.ReliabilityCalculationRun.period_start == start,
            domain.ReliabilityCalculationRun.period_end == end,
            domain.ReliabilityCalculationRun.formula_version == metric.formula_version,
        )
        .order_by(
            domain.ReliabilityCalculationRun.revision.desc(),
            domain.ReliabilityCalculationRun.created_at.desc(),
            domain.ReliabilityCalculationRun.id.desc(),
        )
        .first()
    )
    revision = (int(previous.revision) + 1) if previous else 1
    if previous:
        lineage["previous_run_id"] = previous.id
        lineage["previous_revision"] = int(previous.revision)
    lineage["revision"] = revision
    result_hash = sha256_value(
        {
            "metric_id": metric.id,
            "formula_version": metric.formula_version,
            "revision": revision,
            "lineage": lineage,
            "value": str(value) if value is not None else None,
            "confidence": [str(lower) if lower is not None else None, str(upper) if upper is not None else None],
            "status": result_status,
        }
    )
    run = domain.ReliabilityCalculationRun(
        amo_id=amo_id,
        metric_definition_id=metric.id,
        scope_type=resolved_scope_type,
        scope_id=resolved_scope_id,
        period_start=start,
        period_end=end,
        numerator=Decimal(events),
        denominator=exposure,
        value=value,
        confidence_lower=lower,
        confidence_upper=upper,
        sample_size=events,
        small_fleet=active_aircraft < 6,
        status=result_status,
        formula_version=metric.formula_version,
        revision=revision,
        source_cutoff_at=source_cutoff,
        source_lineage_json=lineage,
        result_hash=result_hash,
        scheduled=scheduled,
        run_by_user_id=actor_user_id,
    )
    db.add(run)
    audit_action = "CALCULATION_REFRESHED" if previous else "CALCULATION_EXECUTED"
'''
text_value = text_value[:start] + replacement + text_value[end:]
service.write_text(text_value, encoding="utf-8")
replace_once(
    service_path,
    '''            "result_hash": result_hash,
            "scheduled": scheduled,''',
    '''            "result_hash": result_hash,
            "revision": revision,
            "previous_run_id": previous.id if previous else None,
            "scheduled": scheduled,''',
)

tests_path = "backend/amodb/apps/reliability/tests/test_review_regressions.py"
replace_once(
    tests_path,
    '''def test_existing_period_result_is_refreshed_instead_of_returned_early():
    source = getsource(advanced_services.execute_metric)
    assert "run.source_cutoff_at = source_cutoff" in source
    assert 'audit_action = "CALCULATION_REFRESHED"' in source
    assert "if existing:\n        return existing" not in source
''',
    '''def test_existing_period_result_creates_an_immutable_revision():
    source = getsource(advanced_services.execute_metric)
    assert "pg_advisory_xact_lock" in source
    assert "ReliabilityCalculationRun.revision.desc()" in source
    assert "revision=revision" in source
    assert 'audit_action = "CALCULATION_REFRESHED" if previous else "CALCULATION_EXECUTED"' in source
    assert "run = existing" not in source
    assert "run.source_cutoff_at = source_cutoff" not in source


def test_delay_integer_boundaries_are_validated_before_insertion():
    accepted = {
        "event_type": "TECHNICAL_DELAY",
        "occurred_at": "2026-08-04T00:00:00Z",
        "flight_number": "KQ100",
        "delay_minutes": "2147483647",
    }
    errors, _ = advanced_services._validate_ingestion_record(accepted)
    assert not errors
    assert accepted["delay_minutes"] == 2147483647

    rejected = {
        "event_type": "TECHNICAL_DELAY",
        "occurred_at": "2026-08-04T00:00:00Z",
        "flight_number": "KQ101",
        "delay_minutes": "2147483648",
    }
    errors, _ = advanced_services._validate_ingestion_record(rejected)
    assert "delay_minutes must be a nonnegative whole number" in errors
    assert rejected["delay_minutes"] == "2147483648"
''',
)

Path("backend/amodb/alembic/versions/rel_20260804_calculation_run_revisions.py").write_text(
    '''"""Add immutable revisions to Reliability calculation runs.

Revision ID: rel_20260804_calc_revisions
Revises: rel_quality_20260804_merge
Create Date: 2026-08-04
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa

revision: str = "rel_20260804_calc_revisions"
down_revision: Union[str, Sequence[str], None] = "rel_quality_20260804_merge"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

IDENTITY_COLUMNS = [
    "amo_id",
    "metric_definition_id",
    "scope_type",
    "scope_id",
    "period_start",
    "period_end",
    "formula_version",
]


def upgrade() -> None:
    op.add_column(
        "reliability_calculation_runs",
        sa.Column("revision", sa.Integer(), nullable=True, server_default=sa.text("1")),
    )
    op.execute("UPDATE reliability_calculation_runs SET revision = 1 WHERE revision IS NULL")
    op.alter_column(
        "reliability_calculation_runs",
        "revision",
        existing_type=sa.Integer(),
        nullable=False,
        server_default=sa.text("1"),
    )
    op.drop_constraint(
        "uq_reliability_calculation_identity",
        "reliability_calculation_runs",
        type_="unique",
    )
    op.create_unique_constraint(
        "uq_reliability_calculation_identity",
        "reliability_calculation_runs",
        [*IDENTITY_COLUMNS, "revision"],
    )
    op.create_index(
        "ix_reliability_calculation_identity_revision",
        "reliability_calculation_runs",
        [*IDENTITY_COLUMNS, "revision"],
        unique=False,
    )


def downgrade() -> None:
    bind = op.get_bind()
    later_revisions = bind.execute(
        sa.text("SELECT COUNT(*) FROM reliability_calculation_runs WHERE revision > 1")
    ).scalar_one()
    if later_revisions:
        raise RuntimeError(
            "Cannot downgrade calculation-run revisions while immutable revisions greater than 1 exist."
        )
    op.drop_index(
        "ix_reliability_calculation_identity_revision",
        table_name="reliability_calculation_runs",
    )
    op.drop_constraint(
        "uq_reliability_calculation_identity",
        "reliability_calculation_runs",
        type_="unique",
    )
    op.create_unique_constraint(
        "uq_reliability_calculation_identity",
        "reliability_calculation_runs",
        IDENTITY_COLUMNS,
    )
    op.drop_column("reliability_calculation_runs", "revision")
''',
    encoding="utf-8",
)

Path("backend/amodb/apps/reliability/tests/postgresql_append_only_regression.py").write_text(
    '''"""PostgreSQL-only schema regression for immutable calculation revisions."""
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
''',
    encoding="utf-8",
)

workflow_path = ".github/workflows/reliability-module-ci.yml"
replace_once(
    workflow_path,
    "          grep -q 'rel_quality_20260804_merge' /tmp/alembic-heads.txt\n",
    "          grep -q 'rel_20260804_calc_revisions' /tmp/alembic-heads.txt\n",
)
replace_once(
    workflow_path,
    "          assert version == 'rel_quality_20260804_merge', version\n",
    "          assert version == 'rel_20260804_calc_revisions', version\n",
)
replace_once(
    workflow_path,
    '''      - name: Run Reliability tests
        run: pytest -q backend/amodb/apps/reliability/tests
''',
    '''      - name: Run PostgreSQL append-only revision regression
        run: python backend/amodb/apps/reliability/tests/postgresql_append_only_regression.py

      - name: Run Reliability tests
        run: pytest -q backend/amodb/apps/reliability/tests
''',
)
