"""Persist governed Reliability formula definitions and calculation snapshots.

Revision ID: rel_20260806_formula_snapshots
Revises: rel_20260805_ops_exact_counts
"""

from __future__ import annotations

import hashlib
import json
from decimal import Decimal
from html import escape

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


def _event_latex(event_types: list[str], fallback: str = "events") -> str:
    if not event_types:
        return rf"N_{{\mathrm{{{fallback}}}}}"
    text = "+".join(event_types).replace("_", r"\_")
    return rf"N_{{\mathrm{{{text}}}}}"


def _event_mathml(event_types: list[str], fallback: str = "events") -> str:
    label = ", ".join(event_types) if event_types else fallback
    return f"<mi>{escape(f'N({label})')}</mi>"


def _math(body: str) -> str:
    return f'<math xmlns="http://www.w3.org/1998/Math/MathML" display="block"><mrow>{body}</mrow></math>'


def _metric_snapshot(row) -> dict:
    configured_types = [str(value) for value in list(row.numerator_event_types or [])]
    method = str(row.method or "RATE").upper()
    denominator = str(row.denominator_type or "NONE").upper()
    multiplier = Decimal(str(row.multiplier if row.multiplier is not None else 1))
    multiplier_text = _number(multiplier)
    numerator_types = configured_types
    source_fields = ["reliability_events.event_type"]

    if method == "NFF_RATE":
        numerator_types = ["NO_FAULT_FOUND"]
        numerator_latex = _event_latex(numerator_types)
        denominator_latex = _event_latex(["UNSCHEDULED_REMOVAL"])
        latex = rf"NFF\%=\frac{{{numerator_latex}}}{{{denominator_latex}}}\times {multiplier_text}"
        mathml = _math(
            f"<mfrac>{_event_mathml(numerator_types)}{_event_mathml(['UNSCHEDULED_REMOVAL'])}</mfrac>"
            f"<mo>×</mo><mn>{multiplier_text}</mn>"
        )
        expression = {
            "op": "multiply",
            "left": {
                "op": "divide",
                "numerator": {"op": "count", "event_types": numerator_types},
                "denominator": {"op": "count", "event_types": ["UNSCHEDULED_REMOVAL"]},
            },
            "right": float(multiplier),
        }
        denominator_label = "Unscheduled-removal events"
        unit = "%" if multiplier == Decimal("100") else f"ratio × {multiplier_text}"
        contract = (
            "Counts no-fault-found events and divides them by unscheduled-removal events "
            "within the same governed period and scope."
        )
        source_fields.append("reliability_events.event_type=UNSCHEDULED_REMOVAL")
    elif method == "PERCENT":
        numerator_latex = _event_latex(numerator_types)
        latex = rf"P\%=\frac{{{numerator_latex}}}{{N_{{\mathrm{{ALL\ RELIABILITY\ EVENTS}}}}}}\times {multiplier_text}"
        mathml = _math(
            f"<mfrac>{_event_mathml(numerator_types)}{_event_mathml([], 'all reliability events')}</mfrac>"
            f"<mo>×</mo><mn>{multiplier_text}</mn>"
        )
        expression = {
            "op": "multiply",
            "left": {
                "op": "divide",
                "numerator": {"op": "count", "event_types": numerator_types},
                "denominator": {"op": "count", "event_types": []},
            },
            "right": float(multiplier),
        }
        denominator_label = "All Reliability events in the same governed period and scope"
        unit = "%" if multiplier == Decimal("100") else f"ratio × {multiplier_text}"
        contract = (
            "Divides the configured event population by all Reliability events in the same "
            "period and scope."
        )
        source_fields.append("reliability_events.id")
    elif method == "COUNT" or denominator == "NONE":
        latex = _event_latex(numerator_types)
        mathml = _math(_event_mathml(numerator_types))
        expression = {"op": "count", "event_types": numerator_types}
        denominator_label = None
        unit = "count"
        contract = "Counts the configured Reliability event types in the governed period and scope."
    elif method == "MTBUR":
        numerator_latex = _event_latex(numerator_types)
        latex = rf"MTBUR=\frac{{{denominator}}}{{{numerator_latex}}}"
        mathml = _math(f"<mfrac><mi>{escape(denominator)}</mi>{_event_mathml(numerator_types)}</mfrac>")
        expression = {
            "op": "divide",
            "numerator": {"op": "exposure", "type": denominator},
            "denominator": {"op": "count", "event_types": numerator_types},
        }
        denominator_label = "Configured qualifying event count"
        unit = f"{denominator} / event"
        contract = f"Divides governed {denominator} exposure by the configured qualifying event count."
        source_fields.append(f"exposure.{denominator.lower()}")
    else:
        numerator_latex = _event_latex(numerator_types)
        latex = rf"R=\frac{{{numerator_latex}}}{{{denominator}}}\times {multiplier_text}"
        mathml = _math(
            f"<mfrac>{_event_mathml(numerator_types)}<mi>{escape(denominator)}</mi></mfrac>"
            f"<mo>×</mo><mn>{multiplier_text}</mn>"
        )
        expression = {
            "op": "multiply",
            "left": {
                "op": "divide",
                "numerator": {"op": "count", "event_types": numerator_types},
                "denominator": {"op": "exposure", "type": denominator},
            },
            "right": float(multiplier),
        }
        denominator_label = f"Governed {denominator} exposure"
        unit = f"events / {multiplier_text} {denominator}"
        contract = (
            f"Divides the configured qualifying event count by governed {denominator} "
            f"exposure and multiplies the result by {multiplier_text}."
        )
        source_fields.append(f"exposure.{denominator.lower()}")

    description = str(row.description or "").strip()
    methodology = f"{description} Calculation contract: {contract}" if description else contract
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
        "numerator_label": ", ".join(numerator_types) if numerator_types else "Configured qualifying events",
        "denominator_label": denominator_label,
        "multiplier": None if method in {"COUNT", "MTBUR"} or denominator == "NONE" else float(multiplier),
        "methodology": methodology,
        "denominator_policy": (
            f"Withhold or classify as insufficient exposure below {row.minimum_exposure}. "
            f"Configured threshold direction: {row.direction}."
        ),
        "source_fields": source_fields,
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

    # Calculation runs are append-only. Disable only the named guard inside this
    # transactional migration while historical rows receive a controlled formula
    # reconstruction from their metric definition. The trigger is always re-enabled.
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
            runs = bind.execute(
                sa.text("""
                    SELECT id, formula_version
                    FROM reliability_calculation_runs
                    WHERE metric_definition_id = :metric_id
                """),
                {"metric_id": metric["id"]},
            ).mappings().all()
            for run in runs:
                run_snapshot = dict(snapshot)
                run_snapshot["version"] = str(run["formula_version"] or snapshot["version"])
                run_snapshot["snapshot_provenance"] = {
                    "mode": "MIGRATION_BACKFILL",
                    "source": "reliability_metric_definitions",
                    "migration": revision,
                }
                snapshot_hash = _hash(run_snapshot)
                lineage_patch = {
                    "formula_snapshot_hash": snapshot_hash,
                    "formula_code": run_snapshot["code"],
                    "formula_version": run_snapshot["version"],
                    "formula_snapshot_provenance": "MIGRATION_BACKFILL",
                }
                bind.execute(
                    sa.text("""
                        UPDATE reliability_calculation_runs
                        SET formula_snapshot_json = CAST(:snapshot AS jsonb),
                            formula_snapshot_hash = :snapshot_hash,
                            source_lineage_json = COALESCE(source_lineage_json, '{}'::jsonb)
                                || CAST(:lineage_patch AS jsonb)
                        WHERE id = :run_id
                    """),
                    {
                        "run_id": run["id"],
                        "snapshot": json.dumps(run_snapshot),
                        "snapshot_hash": snapshot_hash,
                        "lineage_patch": json.dumps(lineage_patch),
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
        op.f("ck_reliability_metric_formula_latex_present"),
        "reliability_metric_definitions",
        "char_length(formula_latex) > 0",
    )
    op.create_check_constraint(
        op.f("ck_reliability_metric_formula_mathml_present"),
        "reliability_metric_definitions",
        "char_length(formula_mathml) > 0",
    )
    op.create_check_constraint(
        op.f("ck_reliability_formula_snapshot_hash_format"),
        "reliability_calculation_runs",
        "formula_snapshot_hash ~ '^[0-9a-f]{64}$'",
    )


def downgrade() -> None:
    op.drop_constraint(
        op.f("ck_reliability_formula_snapshot_hash_format"),
        "reliability_calculation_runs",
        type_="check",
    )
    op.drop_constraint(
        op.f("ck_reliability_metric_formula_mathml_present"),
        "reliability_metric_definitions",
        type_="check",
    )
    op.drop_constraint(
        op.f("ck_reliability_metric_formula_latex_present"),
        "reliability_metric_definitions",
        type_="check",
    )
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
