"""Enforce final Document Control lifecycle integrity.

Revision ID: document_control_20260725_integrity
Revises: document_control_20260724_distribution_integrity
Create Date: 2026-07-25
"""
from __future__ import annotations

from alembic import op
import sqlalchemy as sa
from sqlalchemy import text


revision = "document_control_20260725_integrity"
down_revision = "document_control_20260724_distribution_integrity"
branch_labels = None
depends_on = None


def _count(sql: str) -> int:
    return int(op.get_bind().execute(text(sql)).scalar() or 0)


def upgrade() -> None:
    inspector = sa.inspect(op.get_bind())

    if inspector.has_table("document_review_plans"):
        duplicate_reviews = _count(
            """
            SELECT count(*) FROM (
                SELECT tenant_id, manual_id, revision_id
                FROM document_review_plans
                WHERE revision_id IS NOT NULL
                  AND status IN ('SCHEDULED', 'IN_PROGRESS')
                GROUP BY tenant_id, manual_id, revision_id
                HAVING count(*) > 1
            ) duplicates
            """
        )
        if duplicate_reviews:
            raise RuntimeError(
                "Duplicate open periodic reviews exist for an effective revision. "
                "Resolve them before rerunning Alembic."
            )
        op.execute(
            text(
                """
                CREATE UNIQUE INDEX IF NOT EXISTS
                    uq_document_review_open_effective_revision
                ON document_review_plans (tenant_id, manual_id, revision_id)
                WHERE revision_id IS NOT NULL
                  AND status IN ('SCHEDULED', 'IN_PROGRESS')
                """
            )
        )

    if inspector.has_table("external_revision_receipts"):
        duplicate_labels = _count(
            """
            SELECT count(*) FROM (
                SELECT source_id, lower(btrim(revision_label)) AS normalized_label
                FROM external_revision_receipts
                GROUP BY source_id, lower(btrim(revision_label))
                HAVING count(*) > 1
            ) duplicates
            """
        )
        if duplicate_labels:
            raise RuntimeError(
                "Duplicate external revision labels exist for a source. "
                "Resolve them before rerunning Alembic."
            )
        multiple_current = _count(
            """
            SELECT count(*) FROM (
                SELECT source_id
                FROM external_revision_receipts
                WHERE currency_status = 'CURRENT'
                GROUP BY source_id
                HAVING count(*) > 1
            ) duplicates
            """
        )
        if multiple_current:
            raise RuntimeError(
                "More than one external revision is marked CURRENT for a source. "
                "Resolve them before rerunning Alembic."
            )
        op.execute(
            text(
                """
                CREATE UNIQUE INDEX IF NOT EXISTS
                    uq_external_revision_source_label_ci
                ON external_revision_receipts (
                    source_id,
                    lower(btrim(revision_label))
                )
                """
            )
        )
        op.execute(
            text(
                """
                CREATE UNIQUE INDEX IF NOT EXISTS
                    uq_external_revision_current_source
                ON external_revision_receipts (source_id)
                WHERE currency_status = 'CURRENT'
                """
            )
        )

    if inspector.has_table("document_temporary_revisions"):
        invalid_temporary_revisions = _count(
            """
            SELECT count(*)
            FROM document_temporary_revisions
            WHERE revision_id IS NULL
               OR filing_instructions IS NULL
               OR length(btrim(filing_instructions)) < 3
               OR affected_sections_json = '[]'::jsonb
            """
        )
        if invalid_temporary_revisions:
            raise RuntimeError(
                "Temporary revision rows are missing source content, affected "
                "sections, or filing instructions. Resolve them before rerunning Alembic."
            )
        op.create_check_constraint(
            "ck_document_tr_source_revision_required",
            "document_temporary_revisions",
            "revision_id IS NOT NULL",
        )
        op.create_check_constraint(
            "ck_document_tr_filing_instructions_required",
            "document_temporary_revisions",
            "filing_instructions IS NOT NULL AND length(btrim(filing_instructions)) >= 3",
        )
        op.create_check_constraint(
            "ck_document_tr_affected_sections_required",
            "document_temporary_revisions",
            "affected_sections_json <> '[]'::jsonb",
        )


def downgrade() -> None:
    inspector = sa.inspect(op.get_bind())
    if inspector.has_table("document_temporary_revisions"):
        op.drop_constraint(
            "ck_document_tr_affected_sections_required",
            "document_temporary_revisions",
            type_="check",
        )
        op.drop_constraint(
            "ck_document_tr_filing_instructions_required",
            "document_temporary_revisions",
            type_="check",
        )
        op.drop_constraint(
            "ck_document_tr_source_revision_required",
            "document_temporary_revisions",
            type_="check",
        )
    op.execute(text("DROP INDEX IF EXISTS uq_external_revision_current_source"))
    op.execute(text("DROP INDEX IF EXISTS uq_external_revision_source_label_ci"))
    op.execute(text("DROP INDEX IF EXISTS uq_document_review_open_effective_revision"))
