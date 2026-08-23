"""Harden assurance event trigger context and actor resolution.

Revision ID: quality_260804_trigger_fix
Revises: quality_260804_assurance_wiring
Create Date: 2026-08-04
"""
from __future__ import annotations

from alembic import op
import sqlalchemy as sa


revision = "quality_260804_trigger_fix"
down_revision = "quality_260804_assurance_wiring"
branch_labels = None
depends_on = None

_ADDITIONAL_EVENT_SOURCES = (
    ("qms_report_exports", "REPORT"),
    ("qms_out_of_tolerance_events", "OUT_OF_TOLERANCE"),
)


def _is_postgresql() -> bool:
    return op.get_bind().dialect.name == "postgresql"


def upgrade() -> None:
    if not _is_postgresql():
        return
    op.execute(
        sa.text(
            """
            CREATE OR REPLACE FUNCTION quality_capture_assurance_event()
            RETURNS trigger
            LANGUAGE plpgsql
            AS $$
            DECLARE
                current_row jsonb;
                previous_row jsonb;
                tenant_id text;
                record_id text;
                actor_id text;
                request_actor_id text;
                previous_tenant_id text;
                previous_user_id text;
                invalid_reason text;
                changed jsonb;
            BEGIN
                current_row := CASE WHEN TG_OP = 'DELETE' THEN NULL ELSE to_jsonb(NEW) END;
                previous_row := CASE WHEN TG_OP = 'INSERT' THEN NULL ELSE to_jsonb(OLD) END;
                tenant_id := COALESCE(current_row ->> 'amo_id', previous_row ->> 'amo_id');
                record_id := COALESCE(current_row ->> 'id', previous_row ->> 'id');
                previous_tenant_id := current_setting('app.tenant_id', true);
                previous_user_id := current_setting('app.user_id', true);
                request_actor_id := NULLIF(previous_user_id, '');
                actor_id := COALESCE(
                    current_row ->> 'updated_by_user_id',
                    current_row ->> 'updated_by',
                    current_row ->> 'created_by_user_id',
                    current_row ->> 'created_by',
                    request_actor_id
                );

                IF tenant_id IS NULL OR record_id IS NULL THEN
                    RETURN CASE WHEN TG_OP = 'DELETE' THEN OLD ELSE NEW END;
                END IF;

                -- Triggered writes may originate from imports, scheduled jobs or
                -- specialist routers. Derive the transaction-local RLS tenant
                -- from the authoritative row instead of requiring every caller
                -- to initialise assurance context first.
                PERFORM set_config('app.tenant_id', tenant_id, true);

                IF actor_id IS NOT NULL AND NOT EXISTS (
                    SELECT 1 FROM users WHERE id::text = actor_id
                ) THEN
                    actor_id := request_actor_id;
                END IF;
                IF actor_id IS NOT NULL AND NOT EXISTS (
                    SELECT 1 FROM users WHERE id::text = actor_id
                ) THEN
                    actor_id := NULL;
                END IF;
                IF actor_id IS NOT NULL THEN
                    PERFORM set_config('app.user_id', actor_id, true);
                END IF;

                IF TG_OP = 'UPDATE' THEN
                    SELECT COALESCE(jsonb_agg(key ORDER BY key), '[]'::jsonb)
                    INTO changed
                    FROM jsonb_each(current_row)
                    WHERE previous_row -> key IS DISTINCT FROM current_row -> key;
                ELSE
                    changed := '[]'::jsonb;
                END IF;

                INSERT INTO quality_assurance_events (
                    id, amo_id, source_table, source_type, source_id, event_type,
                    previous_snapshot, source_snapshot, changed_fields, actor_user_id,
                    correlation_id, processing_status, occurred_at
                ) VALUES (
                    gen_random_uuid()::text,
                    tenant_id,
                    TG_TABLE_NAME,
                    TG_ARGV[0],
                    record_id,
                    TG_OP,
                    previous_row,
                    current_row,
                    changed,
                    actor_id,
                    NULLIF(current_setting('app.correlation_id', true), ''),
                    'PENDING',
                    NOW()
                );

                invalid_reason := CASE
                    WHEN TG_OP = 'DELETE' THEN 'Authoritative source record was deleted.'
                    WHEN NULLIF(current_row ->> 'deleted_at', '') IS NOT NULL THEN 'Authoritative source record was soft-deleted.'
                    WHEN UPPER(COALESCE(current_row ->> 'status', '')) IN (
                        'CANCELLED', 'OBSOLETE', 'REJECTED', 'DELETED', 'VOID', 'SUPERSEDED'
                    ) THEN 'Authoritative source record is no longer valid for assurance.'
                    ELSE NULL
                END;

                UPDATE quality_assurance_evidence_links
                SET source_table = TG_TABLE_NAME,
                    source_snapshot = current_row,
                    source_verified_at = NOW(),
                    last_synced_at = NOW(),
                    evidence_status = CASE
                        WHEN invalid_reason IS NOT NULL THEN 'REJECTED'
                        WHEN valid_until IS NOT NULL AND valid_until < CURRENT_DATE THEN 'EXPIRED'
                        ELSE evidence_status
                    END,
                    invalidated_at = CASE WHEN invalid_reason IS NOT NULL THEN NOW() ELSE NULL END,
                    invalidation_reason = invalid_reason,
                    updated_at = NOW()
                WHERE amo_id::text = tenant_id
                  AND source_type = TG_ARGV[0]
                  AND source_id = record_id;

                -- Do not leak the source row's tenant or actor into later
                -- statements executed by the caller in the same transaction.
                PERFORM set_config('app.tenant_id', COALESCE(previous_tenant_id, ''), true);
                PERFORM set_config('app.user_id', COALESCE(previous_user_id, ''), true);

                RETURN CASE WHEN TG_OP = 'DELETE' THEN OLD ELSE NEW END;
            END;
            $$
            """
        )
    )

    for table_name, source_type in _ADDITIONAL_EVENT_SOURCES:
        trigger_name = f"trg_{table_name}_assurance_event"
        op.execute(
            sa.text(
                f"""
                DO $$
                BEGIN
                    IF to_regclass('public.{table_name}') IS NOT NULL THEN
                        DROP TRIGGER IF EXISTS {trigger_name} ON {table_name};
                        CREATE TRIGGER {trigger_name}
                        AFTER INSERT OR UPDATE OR DELETE ON {table_name}
                        FOR EACH ROW EXECUTE FUNCTION quality_capture_assurance_event('{source_type}');
                    END IF;
                END
                $$;
                """
            )
        )


def downgrade() -> None:
    # The hardened function remains backward-compatible with the immediately
    # preceding assurance schema. Keeping it in place avoids reintroducing a
    # trigger that can fail source writes when request context is absent.
    return
