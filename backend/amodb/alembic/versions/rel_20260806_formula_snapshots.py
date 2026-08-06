"""Persist governed Reliability formula definitions and calculation snapshots.

Revision ID: rel_20260806_formula_snapshots
Revises: rel_20260805_ops_exact_counts
"""

from __future__ import annotations

import hashlib
import json
from decimal import Decimal

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects.postgresql import JSONB


revision = "rel_20260806_formula_snapshots"
down_revision = "rel_20260805_ops_exact_counts"
branch_labels = None
depends_on = None


def _number(value) -> str:
    number = Decimal(str(value if value is not None else 1))
    text = format(number, "f")
    if "." in text:
        text = text.rstrip("0").rstrip(".")
    return text or "0"


def _metric_snapshot(row) -> dict:
    event_types = [str(value) for value in list(row.numerator_event_types or [])]
    event_label = ", ".join(event_types) if event_types else "configured events"
    numerator_latex = "N_{" + ("+".join(event_types) if event_types else "events") + "}"
    denominator = str(row.denominator_type or "NONE")
    multiplier = _number(row.multiplier)
    method = str(row.method or "RATE").upper()

    if method == "COUNT" or denominator == "NONE":
        latex = numerator_latex
        mathml = f'<math xmlns="http://www.w3.org/1998/Math/MathML" display="block"><mi>N({event_label})</mi></math>'
        expression = {"op": "count", "event_types": event_types}
        denominator_label = None
        unit = "count"
    elif method == "MTBUR":
        latex = rf"MTBUR=\frac{{{denominator}}}{{{numerator_latex}}}"
        mathml = f'<math xmlns="http://www.w3.org/1998/Math/MathML" display="block"><mfrac><mi>{denominator}</mi><mi>N({event_label})</mi></mfrac></math>'
        expression = {"op": "divide", "numerator": denominator, "denominator": {"op": "count", "event_types": event_types}}
        denominator_label = "Qualifying event count"
        unit = f"{denominator} / event"
    else:
        latex = rf"R=\frac{{{numerator_latex}}}{{{denominator}}}\times {multiplier}"
        mathml = f'<math xmlns="http://www.w3.org/1998/Math/MathML" display="block"><mrow><mfrac><mi>N({event_label})</mi><mi>{denominator}</mi></mfrac><mo>×</mo><mn>{multiplier}</mn></mrow></math>'
        expression = {"op": "multiply", "left": {"op": "divide", "numerator": {"op": "count", "event_types": event_types}, "denominator": denominator}, "right": float(Decimal(multiplier))}
        denominator_label = denominator
        unit = f"per {multiplier} {denominator}"

    minimum = str(row.minimum_exposure or 0)
    description = str(row.description or f"Controlled {method} metric from the Reliability programme definition.")
    return {
        "code": f"programme.{row.code}",
        "name": str(row.name),
        "version": str(row.formula_version or "1"),
        "origin": "PROGRAMME",
        "latex": latex,
        "mathml": mathml,
        "expression": expression,
        "unit": unit,
        "precision": 3,
        "rounding_mode": "HALF_UP",
        "numerator_label": event_label,
        "denominator_label": denominator_label,
        "multiplier": None if method in {"COUNT", "MTBUR"} or denominator == "NONE" else float(Decimal(multiplier)),
        "methodology": description,
        "denominator_policy": f"Minimum exposure: {minimum}. Direction: {row.direction}.",
        "source_fields": ["reliability_events.event_type", f"exposure.{denominator.lower()}"],
        "applied_to": [f"programme_metric.{row.code}"],
    }


def _hash(snapshot: dict) -> str:
    raw = json.dumps(snapshot, sort_keys=True, separators=(",", ":"), default=str).encode("utf-8")
    return hashlib.sha256(raw).hexdigest()


def upgrade() -> None:
    op.add_column("reliability_metric_definitions", sa.Column("formula_latex", sa.Text(), nullable=True))
    op.add_column("reliability_metric_definitions", sa.Column("formula_mathml", sa.Text(), nullable=True))
    op.add_column("reliability_metric_definitions", sa.Column("formula_expression_json", JSONB(), nullable=True))
    op.add_column("reliability_metric_definitions", sa.Column("formula_unit", sa.String(length=80), nullable=True))
    op.add_column("reliability_metric_definitions", sa.Column("formula_precision", sa.Integer(), nullable=True))
    op.add_column("reliability_metric_definitions", sa.Column("formula_rounding_mode", sa.String(length=24), nullable=True))
    op.add_column("reliability_metric_definitions", sa.Column("denominator_policy", sa.Text(), nullable=True))
    op.add_column("reliability_metric_definitions", sa.Column("formula_source_fields_json", JSONB(), nullable=True))
    op.add_column("reliability_calculation_runs", sa.Column("formula_snapshot_json", JSONB(), nullable=True))
    op.add_column("reliability_calculation_runs", sa.Column("formula_snapshot_hash", sa.String(length=64), nullable=True))

    bind = op.get_bind()
    metrics = bind.execute(sa.text("""
        SELECT id, code, name, description, scope_type, method, numerator_event_types,
               denominator_type, multiplier, minimum_exposure, direction, formula_version
        FROM reliability_metric_definitions
    """)).mappings().all()

    # Calculation runs are intentionally append-only. Disable only the named guard
    # inside this transactional migration while historical rows receive the exact
    # formula snapshot that governed their already-retained result. PostgreSQL rolls
    # the trigger state back with the migration if any statement fails.
    op.execute(
        "ALTER TABLE reliability_calculation_runs "
        "DISABLE TRIGGER trg_reliability_calculation_runs_append_only"
    )
    try:
        for metric in metrics:
            snapshot = _metric_snapshot(type("MetricRow", (), dict(metric))())
            bind.execute(
                sa.text("""
                    UPDATE reliability_metric_definitions
                    SET formula_latex = :latex,
                        formula_mathml = :mathml,
                        formula_expression_json = CAST(:expression AS jsonb),
                        formula_unit = :unit,
                        formula_precision = :precision,
                        formula_rounding_mode = :rounding,
                        denominator_policy = :policy,
                        formula_source_fields_json = CAST(:source_fields AS jsonb)
                    WHERE id = :metric_id
                """),
                {
                    "metric_id": metric["id"],
                    "latex": snapshot["latex"],
                    "mathml": snapshot["mathml"],
                    "expression": json.dumps(snapshot["expression"]),
                    "unit": snapshot["unit"],
                    "precision": snapshot["precision"],
                    "rounding": snapshot["rounding_mode"],
                    "policy": snapshot["denominator_policy"],
                    "source_fields": json.dumps(snapshot["source_fields"]),
                },
            )
            bind.execute(
                sa.text("""
                    UPDATE reliability_calculation_runs
                    SET formula_snapshot_json = CAST(:snapshot AS jsonb),
                        formula_snapshot_hash = :snapshot_hash
                    WHERE metric_definition_id = :metric_id
                """),
                {
                    "metric_id": metric["id"],
                    "snapshot": json.dumps(snapshot),
                    "snapshot_hash": _hash(snapshot),
                },
            )
    finally:
        op.execute(
            "ALTER TABLE reliability_calculation_runs "
            "ENABLE TRIGGER trg_reliability_calculation_runs_append_only"
        )

    op.alter_column("reliability_metric_definitions", "formula_latex", existing_type=sa.Text(), nullable=False)
    op.alter_column("reliability_metric_definitions", "formula_mathml", existing_type=sa.Text(), nullable=False)
    op.alter_column("reliability_metric_definitions", "formula_expression_json", existing_type=JSONB(), nullable=False)
    op.alter_column("reliability_metric_definitions", "formula_unit", existing_type=sa.String(length=80), nullable=False)
    op.alter_column("reliability_metric_definitions", "formula_precision", existing_type=sa.Integer(), nullable=False)
    op.alter_column("reliability_metric_definitions", "formula_rounding_mode", existing_type=sa.String(length=24), nullable=False)
    op.alter_column("reliability_metric_definitions", "denominator_policy", existing_type=sa.Text(), nullable=False)
    op.alter_column("reliability_metric_definitions", "formula_source_fields_json", existing_type=JSONB(), nullable=False)
    op.alter_column("reliability_calculation_runs", "formula_snapshot_json", existing_type=JSONB(), nullable=False)
    op.alter_column("reliability_calculation_runs", "formula_snapshot_hash", existing_type=sa.String(length=64), nullable=False)

    op.create_check_constraint(
        "ck_reliability_metric_formula_latex_present",
        "reliability_metric_definitions",
        "char_length(formula_latex) > 0",
    )
    op.create_check_constraint(
        "ck_reliability_metric_formula_mathml_present",
        "reliability_metric_definitions",
        "char_length(formula_mathml) > 0",
    )
    op.create_check_constraint(
        "ck_reliability_formula_snapshot_hash_format",
        "reliability_calculation_runs",
        "formula_snapshot_hash ~ '^[0-9a-f]{64}$'",
    )


def downgrade() -> None:
    op.drop_constraint("ck_reliability_formula_snapshot_hash_format", "reliability_calculation_runs", type_="check")
    op.drop_constraint("ck_reliability_metric_formula_mathml_present", "reliability_metric_definitions", type_="check")
    op.drop_constraint("ck_reliability_metric_formula_latex_present", "reliability_metric_definitions", type_="check")
    op.drop_column("reliability_calculation_runs", "formula_snapshot_hash")
    op.drop_column("reliability_calculation_runs", "formula_snapshot_json")
    op.drop_column("reliability_metric_definitions", "formula_source_fields_json")
    op.drop_column("reliability_metric_definitions", "denominator_policy")
    op.drop_column("reliability_metric_definitions", "formula_rounding_mode")
    op.drop_column("reliability_metric_definitions", "formula_precision")
    op.drop_column("reliability_metric_definitions", "formula_unit")
    op.drop_column("reliability_metric_definitions", "formula_expression_json")
    op.drop_column("reliability_metric_definitions", "formula_mathml")
    op.drop_column("reliability_metric_definitions", "formula_latex")
