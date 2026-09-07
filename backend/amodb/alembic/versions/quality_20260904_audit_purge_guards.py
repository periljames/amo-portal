"""Permit tenant-scoped audit cascades through immutable audit history.

Revision ID: quality_260904_purge_guards
Revises: quality_260904_audit_ops
Create Date: 2026-09-04
"""
from __future__ import annotations

from alembic import op
import sqlalchemy as sa


revision = "quality_260904_purge_guards"
down_revision = "quality_260904_audit_ops"
branch_labels = None
depends_on = None


_SIMPLE_IMMUTABILITY_FUNCTIONS = (
    (
        "prevent_quality_audit_checklist_binding_mutation",
        "RAISE EXCEPTION 'quality_audit_checklist_bindings is immutable';",
    ),
    (
        "prevent_quality_checklist_execution_events_mutation",
        "RAISE EXCEPTION 'quality_audit_checklist_execution_events is append-only';",
    ),
    (
        "prevent_quality_audit_report_events_mutation",
        "RAISE EXCEPTION 'quality_audit_report_events is append-only';",
    ),
    (
        "prevent_quality_audit_preparation_events_mutation",
        "RAISE EXCEPTION 'quality_audit_preparation_events is append-only';",
    ),
    (
        "prevent_quality_fieldwork_receipts_mutation",
        "RAISE EXCEPTION 'quality_audit_fieldwork_mutation_receipts is append-only';",
    ),
    (
        "prevent_quality_fieldwork_contributions_mutation",
        "RAISE EXCEPTION 'quality_audit_fieldwork_participant_contributions is append-only';",
    ),
    (
        "prevent_quality_archive_governance_mutation",
        "RAISE EXCEPTION '% is append-only/immutable', TG_TABLE_NAME;",
    ),
    (
        "prevent_quality_external_finding_drafts_mutation",
        "RAISE EXCEPTION 'quality_audit_external_finding_drafts is immutable; "
        "create a superseding draft revision instead';",
    ),
    (
        "prevent_quality_external_finding_draft_events_mutation",
        "RAISE EXCEPTION 'quality_audit_external_finding_draft_events is append-only';",
    ),
    (
        "prevent_quality_audit_document_submission_mutation",
        "RAISE EXCEPTION 'Quality audit document submission history is append-only';",
    ),
    (
        "prevent_quality_closing_ack_mutation",
        "RAISE EXCEPTION '% is append-only/immutable', TG_TABLE_NAME;",
    ),
    (
        "prevent_quality_audit_closure_events_mutation",
        "RAISE EXCEPTION 'quality_audit_closure_events is append-only';",
    ),
    (
        "prevent_quality_external_access_events_mutation",
        "RAISE EXCEPTION 'Quality external access/release history is append-only';",
    ),
    (
        "prevent_quality_audit_evidence_mutation",
        "RAISE EXCEPTION '% is immutable audit evidence', TG_TABLE_NAME;",
    ),
    (
        "prevent_quality_closing_assurance_mutation",
        "RAISE EXCEPTION '% is append-only/immutable', TG_TABLE_NAME;",
    ),
    (
        "prevent_quality_audit_report_artifact_mutation",
        "RAISE EXCEPTION 'Generated audit report artifact history is append-only';",
    ),
)


def _is_postgresql() -> bool:
    return op.get_bind().dialect.name == "postgresql"


def _install_simple_functions(*, purge_aware: bool) -> None:
    guard = """
        IF TG_OP = 'DELETE' AND quality_audit_purge_authorized(to_jsonb(OLD)) THEN
            RETURN OLD;
        END IF;
    """ if purge_aware else ""
    for function_name, rejection in _SIMPLE_IMMUTABILITY_FUNCTIONS:
        op.execute(sa.text(f"""
            CREATE OR REPLACE FUNCTION {function_name}()
            RETURNS trigger AS $$
            BEGIN
                {guard}
                {rejection}
            END;
            $$ LANGUAGE plpgsql;
        """))


def _install_preparation_function(*, purge_aware: bool) -> None:
    guard = """
            IF quality_audit_purge_authorized(to_jsonb(OLD)) THEN
                RETURN OLD;
            END IF;
    """ if purge_aware else ""
    op.execute(sa.text(f"""
        CREATE OR REPLACE FUNCTION prevent_issued_audit_preparation_mutation()
        RETURNS trigger AS $$
        BEGIN
            IF TG_OP = 'DELETE' THEN
                {guard}
                RAISE EXCEPTION 'issued audit preparation revisions are immutable';
            END IF;
            IF OLD.status = 'ISSUED' THEN
                RAISE EXCEPTION 'issued audit preparation revisions are immutable';
            END IF;
            RETURN NEW;
        END;
        $$ LANGUAGE plpgsql;
    """))


def _install_report_function(*, purge_aware: bool) -> None:
    guard = """
            IF quality_audit_purge_authorized(to_jsonb(OLD)) THEN
                RETURN OLD;
            END IF;
    """ if purge_aware else ""
    op.execute(sa.text(f"""
        CREATE OR REPLACE FUNCTION prevent_terminal_quality_audit_report_mutation()
        RETURNS trigger AS $$
        BEGIN
            IF TG_OP = 'DELETE' THEN
                {guard}
                RAISE EXCEPTION 'audit report revisions cannot be deleted';
            END IF;
            IF OLD.status IN ('SUPERSEDED','CANCELLED') THEN
                RAISE EXCEPTION 'terminal audit report revisions are immutable';
            END IF;
            IF OLD.status = 'ISSUED' AND NEW.status <> 'SUPERSEDED' THEN
                RAISE EXCEPTION 'issued audit report revisions may only transition to SUPERSEDED';
            END IF;
            RETURN NEW;
        END;
        $$ LANGUAGE plpgsql;
    """))


def _install_notice_function(*, purge_aware: bool) -> None:
    guard = """
            IF quality_audit_purge_authorized(to_jsonb(OLD)) THEN
                RETURN OLD;
            END IF;
    """ if purge_aware else """
            IF current_setting('app.qms_audit_purge_id', true) = OLD.audit_id::text THEN
                RETURN OLD;
            END IF;
    """
    op.execute(sa.text(f"""
        CREATE OR REPLACE FUNCTION prevent_terminal_quality_audit_notice_mutation()
        RETURNS trigger AS $$
        BEGIN
            IF TG_OP = 'DELETE' THEN
                {guard}
                RAISE EXCEPTION 'audit notice revisions cannot be deleted directly';
            END IF;
            IF OLD.status IN ('ACKNOWLEDGED','SUPERSEDED','CANCELLED') THEN
                RAISE EXCEPTION 'terminal audit notice revisions are immutable';
            END IF;
            RETURN NEW;
        END;
        $$ LANGUAGE plpgsql;
    """))


def _install_notice_event_function(*, purge_aware: bool) -> None:
    guard = """
        IF TG_OP = 'DELETE' AND quality_audit_purge_authorized(to_jsonb(OLD)) THEN
            RETURN OLD;
        END IF;
    """ if purge_aware else """
        IF TG_OP = 'DELETE' AND current_setting('app.qms_audit_purge_id', true) = OLD.audit_id::text THEN
            RETURN OLD;
        END IF;
    """
    op.execute(sa.text(f"""
        CREATE OR REPLACE FUNCTION prevent_quality_audit_notice_events_mutation()
        RETURNS trigger AS $$
        BEGIN
            {guard}
            RAISE EXCEPTION 'quality_audit_notice_events is append-only';
        END;
        $$ LANGUAGE plpgsql;
    """))


def upgrade() -> None:
    if not _is_postgresql():
        return

    op.execute(sa.text("""
        CREATE OR REPLACE FUNCTION quality_audit_purge_authorized(row_data jsonb)
        RETURNS boolean AS $$
        BEGIN
            RETURN
                NULLIF(current_setting('app.qms_audit_purge_id', true), '') = NULLIF(row_data ->> 'audit_id', '')
                AND NULLIF(current_setting('app.qms_audit_purge_amo_id', true), '') = NULLIF(row_data ->> 'amo_id', '')
                AND NULLIF(current_setting('app.tenant_id', true), '') = NULLIF(row_data ->> 'amo_id', '');
        END;
        $$ LANGUAGE plpgsql STABLE;
    """))
    _install_simple_functions(purge_aware=True)
    _install_preparation_function(purge_aware=True)
    _install_report_function(purge_aware=True)
    _install_notice_function(purge_aware=True)
    _install_notice_event_function(purge_aware=True)


def downgrade() -> None:
    if not _is_postgresql():
        return

    _install_simple_functions(purge_aware=False)
    _install_preparation_function(purge_aware=False)
    _install_report_function(purge_aware=False)
    _install_notice_function(purge_aware=False)
    _install_notice_event_function(purge_aware=False)
    op.execute(sa.text("DROP FUNCTION IF EXISTS quality_audit_purge_authorized(jsonb)"))
