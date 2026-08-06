"""Harden workbook-derived Reliability analysis and evidence immutability.

Revision ID: rel_20260806_reference_integrity
Revises: rel_20260806_workbook_imports
Create Date: 2026-08-06
"""
from __future__ import annotations

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = "rel_20260806_reference_integrity"
down_revision: Union[str, Sequence[str], None] = "rel_20260806_workbook_imports"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # Replace the remaining binary floating-point persistence in the legacy
    # Reliability trend/KPI paths with fixed-point numeric storage.
    op.alter_column(
        "reliability_defect_trends",
        "utilisation_hours",
        existing_type=sa.Float(),
        type_=sa.Numeric(20, 6),
        existing_nullable=False,
        postgresql_using="ROUND(utilisation_hours::numeric, 6)",
    )
    op.alter_column(
        "reliability_defect_trends",
        "utilisation_cycles",
        existing_type=sa.Float(),
        type_=sa.Numeric(20, 6),
        existing_nullable=False,
        postgresql_using="ROUND(utilisation_cycles::numeric, 6)",
    )
    op.alter_column(
        "reliability_defect_trends",
        "defect_rate_per_100_fh",
        existing_type=sa.Float(),
        type_=sa.Numeric(20, 9),
        existing_nullable=True,
        postgresql_using="ROUND(defect_rate_per_100_fh::numeric, 9)",
    )
    op.alter_column(
        "reliability_kpis",
        "value",
        existing_type=sa.Float(),
        type_=sa.Numeric(24, 9),
        existing_nullable=False,
        postgresql_using="ROUND(value::numeric, 9)",
    )
    op.alter_column(
        "reliability_kpis",
        "numerator",
        existing_type=sa.Float(),
        type_=sa.Numeric(24, 9),
        existing_nullable=True,
        postgresql_using="ROUND(numerator::numeric, 9)",
    )
    op.alter_column(
        "reliability_kpis",
        "denominator",
        existing_type=sa.Float(),
        type_=sa.Numeric(24, 9),
        existing_nullable=True,
        postgresql_using="ROUND(denominator::numeric, 9)",
    )

    op.execute(
        """
        CREATE OR REPLACE FUNCTION prevent_reliability_reference_evidence_mutation()
        RETURNS trigger
        LANGUAGE plpgsql
        AS $$
        BEGIN
            RAISE EXCEPTION 'Reliability reference evidence table % is append-only', TG_TABLE_NAME
                USING ERRCODE = '55000';
        END;
        $$;
        """
    )
    for table_name, trigger_name in (
        (
            "reliability_statistical_alert_results",
            "trg_rel_statistical_alert_results_append_only",
        ),
        (
            "reliability_workbook_report_snapshots",
            "trg_rel_workbook_report_snapshots_append_only",
        ),
    ):
        op.execute(
            f"""
            DROP TRIGGER IF EXISTS {trigger_name} ON {table_name};
            CREATE TRIGGER {trigger_name}
            BEFORE UPDATE OR DELETE ON {table_name}
            FOR EACH ROW
            EXECUTE FUNCTION prevent_reliability_reference_evidence_mutation();
            """
        )

    op.execute(
        """
        CREATE OR REPLACE FUNCTION protect_approved_reliability_workbook_record()
        RETURNS trigger
        LANGUAGE plpgsql
        AS $$
        BEGIN
            IF TG_OP = 'DELETE' AND OLD.status IN ('APPROVED', 'CLOSED') THEN
                RAISE EXCEPTION 'Approved or closed Reliability workbook records are immutable'
                    USING ERRCODE = '55000';
            END IF;
            IF TG_OP = 'UPDATE' AND OLD.status IN ('APPROVED', 'CLOSED') THEN
                IF OLD.status = 'APPROVED'
                   AND NEW.status = 'CLOSED'
                   AND (
                       to_jsonb(NEW) - ARRAY['status','closed_at','closed_by_user_id','updated_at']
                   ) = (
                       to_jsonb(OLD) - ARRAY['status','closed_at','closed_by_user_id','updated_at']
                   )
                THEN
                    RETURN NEW;
                END IF;
                RAISE EXCEPTION 'Approved or closed Reliability workbook records are immutable; create a superseding revision'
                    USING ERRCODE = '55000';
            END IF;
            IF TG_OP = 'DELETE' THEN
                RETURN OLD;
            END IF;
            RETURN NEW;
        END;
        $$;

        DROP TRIGGER IF EXISTS trg_rel_workbook_record_approved_immutable
            ON reliability_workbook_records;
        CREATE TRIGGER trg_rel_workbook_record_approved_immutable
        BEFORE UPDATE OR DELETE ON reliability_workbook_records
        FOR EACH ROW
        EXECUTE FUNCTION protect_approved_reliability_workbook_record();
        """
    )

    op.execute(
        """
        CREATE OR REPLACE FUNCTION protect_completed_reliability_import_evidence()
        RETURNS trigger
        LANGUAGE plpgsql
        AS $$
        DECLARE
            parent_status text;
        BEGIN
            SELECT status INTO parent_status
            FROM reliability_workbook_import_batches
            WHERE id = OLD.batch_id;
            IF parent_status = 'COMPLETED' THEN
                RAISE EXCEPTION 'Completed Reliability workbook import evidence is immutable'
                    USING ERRCODE = '55000';
            END IF;
            IF TG_OP = 'DELETE' THEN
                RETURN OLD;
            END IF;
            RETURN NEW;
        END;
        $$;

        DROP TRIGGER IF EXISTS trg_rel_completed_import_evidence_immutable
            ON reliability_workbook_import_row_results;
        CREATE TRIGGER trg_rel_completed_import_evidence_immutable
        BEFORE UPDATE OR DELETE ON reliability_workbook_import_row_results
        FOR EACH ROW
        EXECUTE FUNCTION protect_completed_reliability_import_evidence();
        """
    )

    op.execute(
        """
        CREATE OR REPLACE FUNCTION protect_completed_reliability_import_batch()
        RETURNS trigger
        LANGUAGE plpgsql
        AS $$
        BEGIN
            IF OLD.status = 'COMPLETED' THEN
                RAISE EXCEPTION 'Completed Reliability workbook import batches are immutable'
                    USING ERRCODE = '55000';
            END IF;
            IF TG_OP = 'DELETE' THEN
                RETURN OLD;
            END IF;
            RETURN NEW;
        END;
        $$;

        DROP TRIGGER IF EXISTS trg_rel_completed_import_batch_immutable
            ON reliability_workbook_import_batches;
        CREATE TRIGGER trg_rel_completed_import_batch_immutable
        BEFORE UPDATE OR DELETE ON reliability_workbook_import_batches
        FOR EACH ROW
        EXECUTE FUNCTION protect_completed_reliability_import_batch();
        """
    )


def downgrade() -> None:
    op.execute(
        """
        DROP TRIGGER IF EXISTS trg_rel_completed_import_batch_immutable
            ON reliability_workbook_import_batches;
        DROP FUNCTION IF EXISTS protect_completed_reliability_import_batch();

        DROP TRIGGER IF EXISTS trg_rel_completed_import_evidence_immutable
            ON reliability_workbook_import_row_results;
        DROP FUNCTION IF EXISTS protect_completed_reliability_import_evidence();

        DROP TRIGGER IF EXISTS trg_rel_workbook_record_approved_immutable
            ON reliability_workbook_records;
        DROP FUNCTION IF EXISTS protect_approved_reliability_workbook_record();

        DROP TRIGGER IF EXISTS trg_rel_statistical_alert_results_append_only
            ON reliability_statistical_alert_results;
        DROP TRIGGER IF EXISTS trg_rel_workbook_report_snapshots_append_only
            ON reliability_workbook_report_snapshots;
        DROP FUNCTION IF EXISTS prevent_reliability_reference_evidence_mutation();
        """
    )
    op.alter_column(
        "reliability_kpis",
        "denominator",
        existing_type=sa.Numeric(24, 9),
        type_=sa.Float(),
        existing_nullable=True,
        postgresql_using="denominator::double precision",
    )
    op.alter_column(
        "reliability_kpis",
        "numerator",
        existing_type=sa.Numeric(24, 9),
        type_=sa.Float(),
        existing_nullable=True,
        postgresql_using="numerator::double precision",
    )
    op.alter_column(
        "reliability_kpis",
        "value",
        existing_type=sa.Numeric(24, 9),
        type_=sa.Float(),
        existing_nullable=False,
        postgresql_using="value::double precision",
    )
    op.alter_column(
        "reliability_defect_trends",
        "defect_rate_per_100_fh",
        existing_type=sa.Numeric(20, 9),
        type_=sa.Float(),
        existing_nullable=True,
        postgresql_using="defect_rate_per_100_fh::double precision",
    )
    op.alter_column(
        "reliability_defect_trends",
        "utilisation_cycles",
        existing_type=sa.Numeric(20, 6),
        type_=sa.Float(),
        existing_nullable=False,
        postgresql_using="utilisation_cycles::double precision",
    )
    op.alter_column(
        "reliability_defect_trends",
        "utilisation_hours",
        existing_type=sa.Numeric(20, 6),
        type_=sa.Float(),
        existing_nullable=False,
        postgresql_using="utilisation_hours::double precision",
    )
