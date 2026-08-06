from __future__ import annotations

from alembic import op
import sqlalchemy as sa


IMMUTABLE_TABLES = (
    "aircraft_inductions",
    "aircraft_configuration_snapshots",
    "aircraft_configuration_snapshot_items",
    "aircraft_applicability_snapshots",
    "aircraft_engineering_lineage",
)
EXACT_STATE_TABLES = (
    "aircraft_exact_utilisation_states",
    "component_exact_utilisation_states",
)


def upgrade_guards() -> None:
    op.add_column(
        "aircraft_daily_utilisation_entries",
        sa.Column("correction_reason", sa.Text(), nullable=True),
    )
    op.alter_column(
        "aircraft_daily_utilisation_exposures",
        "before_cycles",
        existing_type=sa.Integer(),
        type_=sa.BigInteger(),
        existing_nullable=True,
    )
    op.alter_column(
        "aircraft_daily_utilisation_exposures",
        "after_cycles",
        existing_type=sa.Integer(),
        type_=sa.BigInteger(),
        existing_nullable=True,
    )

    op.execute(
        """
        CREATE OR REPLACE FUNCTION block_aircraft_engineering_immutable_mutation()
        RETURNS trigger AS $$
        BEGIN
            RAISE EXCEPTION '% is immutable; create a new controlled revision or induction', TG_TABLE_NAME;
        END;
        $$ LANGUAGE plpgsql;
        """
    )
    for table in IMMUTABLE_TABLES:
        op.execute(
            f"""
            CREATE TRIGGER trg_{table}_immutable
            BEFORE UPDATE OR DELETE ON {table}
            FOR EACH ROW EXECUTE FUNCTION block_aircraft_engineering_immutable_mutation();
            """
        )

    op.execute(
        """
        CREATE OR REPLACE FUNCTION protect_daily_utilisation_entry()
        RETURNS trigger AS $$
        DECLARE
            correction_enabled boolean := COALESCE(
                current_setting('amo.controlled_utilisation_correction', true),
                'off'
            ) = 'on';
        BEGIN
            IF TG_OP = 'DELETE' THEN
                IF OLD.status IN ('POSTED', 'SUPERSEDED') THEN
                    RAISE EXCEPTION 'posted daily utilisation entries are immutable';
                END IF;
                RETURN OLD;
            END IF;

            IF OLD.status = 'DRAFT' THEN
                IF ROW(
                    NEW.amo_id, NEW.aircraft_serial_number, NEW.operation_date,
                    NEW.techlog_no, NEW.station, NEW.flight_hours, NEW.cycles,
                    NEW.nil_operation, NEW.source_type, NEW.source_reference,
                    NEW.revision_no, NEW.supersedes_entry_id,
                    NEW.idempotency_key, NEW.content_hash, NEW.remarks,
                    NEW.correction_reason, NEW.created_by_user_id, NEW.created_at
                ) IS DISTINCT FROM ROW(
                    OLD.amo_id, OLD.aircraft_serial_number, OLD.operation_date,
                    OLD.techlog_no, OLD.station, OLD.flight_hours, OLD.cycles,
                    OLD.nil_operation, OLD.source_type, OLD.source_reference,
                    OLD.revision_no, OLD.supersedes_entry_id,
                    OLD.idempotency_key, OLD.content_hash, OLD.remarks,
                    OLD.correction_reason, OLD.created_by_user_id, OLD.created_at
                ) THEN
                    RAISE EXCEPTION 'daily utilisation source fields are immutable after draft creation';
                END IF;
                IF NEW.status NOT IN ('DRAFT', 'POSTED', 'REJECTED') THEN
                    RAISE EXCEPTION 'invalid controlled daily utilisation status transition';
                END IF;
                RETURN NEW;
            END IF;

            IF OLD.status = 'POSTED'
               AND correction_enabled
               AND NEW.status = 'SUPERSEDED'
               AND ROW(
                    NEW.amo_id, NEW.aircraft_serial_number, NEW.operation_date,
                    NEW.techlog_no, NEW.station, NEW.flight_hours, NEW.cycles,
                    NEW.nil_operation, NEW.source_type, NEW.source_reference,
                    NEW.revision_no, NEW.supersedes_entry_id,
                    NEW.idempotency_key, NEW.content_hash, NEW.remarks,
                    NEW.correction_reason, NEW.created_by_user_id, NEW.created_at,
                    NEW.posted_by_user_id, NEW.posted_at
               ) IS NOT DISTINCT FROM ROW(
                    OLD.amo_id, OLD.aircraft_serial_number, OLD.operation_date,
                    OLD.techlog_no, OLD.station, OLD.flight_hours, OLD.cycles,
                    OLD.nil_operation, OLD.source_type, OLD.source_reference,
                    OLD.revision_no, OLD.supersedes_entry_id,
                    OLD.idempotency_key, OLD.content_hash, OLD.remarks,
                    OLD.correction_reason, OLD.created_by_user_id, OLD.created_at,
                    OLD.posted_by_user_id, OLD.posted_at
               ) THEN
                RETURN NEW;
            END IF;

            RAISE EXCEPTION 'posted daily utilisation entries are immutable';
        END;
        $$ LANGUAGE plpgsql;
        """
    )
    op.execute(
        """
        CREATE TRIGGER trg_daily_utilisation_entry_protect
        BEFORE UPDATE OR DELETE ON aircraft_daily_utilisation_entries
        FOR EACH ROW EXECUTE FUNCTION protect_daily_utilisation_entry();
        """
    )

    op.execute(
        """
        CREATE OR REPLACE FUNCTION protect_daily_utilisation_exposure()
        RETURNS trigger AS $$
        DECLARE parent_status text;
        BEGIN
            SELECT status INTO parent_status
            FROM aircraft_daily_utilisation_entries
            WHERE id = OLD.entry_id;
            IF parent_status IN ('POSTED', 'SUPERSEDED') THEN
                RAISE EXCEPTION 'posted daily utilisation exposure rows are immutable';
            END IF;
            IF TG_OP = 'DELETE' THEN RETURN OLD; END IF;
            RETURN NEW;
        END;
        $$ LANGUAGE plpgsql;
        """
    )
    op.execute(
        """
        CREATE TRIGGER trg_daily_utilisation_exposure_protect
        BEFORE UPDATE OR DELETE ON aircraft_daily_utilisation_exposures
        FOR EACH ROW EXECUTE FUNCTION protect_daily_utilisation_exposure();
        """
    )

    op.execute(
        """
        CREATE OR REPLACE FUNCTION protect_exact_utilisation_projection()
        RETURNS trigger AS $$
        BEGIN
            IF COALESCE(
                current_setting('amo.controlled_utilisation_projection', true),
                'off'
            ) <> 'on' THEN
                RAISE EXCEPTION '% may only be changed by a controlled ledger transaction', TG_TABLE_NAME;
            END IF;
            IF TG_OP = 'DELETE' THEN RETURN OLD; END IF;
            RETURN NEW;
        END;
        $$ LANGUAGE plpgsql;
        """
    )
    for table in EXACT_STATE_TABLES:
        op.execute(
            f"""
            CREATE TRIGGER trg_{table}_controlled
            BEFORE UPDATE OR DELETE ON {table}
            FOR EACH ROW EXECUTE FUNCTION protect_exact_utilisation_projection();
            """
        )


def downgrade_guards() -> None:
    for table in EXACT_STATE_TABLES:
        op.execute(f"DROP TRIGGER IF EXISTS trg_{table}_controlled ON {table}")
    op.execute("DROP FUNCTION IF EXISTS protect_exact_utilisation_projection()")
    op.execute("DROP TRIGGER IF EXISTS trg_daily_utilisation_exposure_protect ON aircraft_daily_utilisation_exposures")
    op.execute("DROP FUNCTION IF EXISTS protect_daily_utilisation_exposure()")
    op.execute("DROP TRIGGER IF EXISTS trg_daily_utilisation_entry_protect ON aircraft_daily_utilisation_entries")
    op.execute("DROP FUNCTION IF EXISTS protect_daily_utilisation_entry()")
    for table in IMMUTABLE_TABLES:
        op.execute(f"DROP TRIGGER IF EXISTS trg_{table}_immutable ON {table}")
    op.execute("DROP FUNCTION IF EXISTS block_aircraft_engineering_immutable_mutation()")
    op.alter_column(
        "aircraft_daily_utilisation_exposures",
        "after_cycles",
        existing_type=sa.BigInteger(),
        type_=sa.Integer(),
        existing_nullable=True,
    )
    op.alter_column(
        "aircraft_daily_utilisation_exposures",
        "before_cycles",
        existing_type=sa.BigInteger(),
        type_=sa.Integer(),
        existing_nullable=True,
    )
    op.drop_column("aircraft_daily_utilisation_entries", "correction_reason")
