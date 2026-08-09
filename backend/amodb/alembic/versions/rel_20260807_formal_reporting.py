"""add formal Reliability Programme reporting governance

Revision ID: rel_20260807_formal_reporting
Revises: rel_20260807_main_merge
Create Date: 2026-08-07
"""
from __future__ import annotations

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

revision = "rel_20260807_formal_reporting"
down_revision = "rel_20260807_main_merge"
branch_labels = None
depends_on = None

J = postgresql.JSONB(astext_type=sa.Text())


def _id():
    return sa.Column("id", sa.String(36), primary_key=True)


def _amo():
    return sa.Column("amo_id", sa.String(36), sa.ForeignKey("amos.id", ondelete="CASCADE"), nullable=False)


def _user(name: str, *, nullable: bool = True, ondelete: str = "SET NULL"):
    return sa.Column(name, sa.String(36), sa.ForeignKey("users.id", ondelete=ondelete), nullable=nullable)


def _created():
    return sa.Column("created_at", sa.DateTime(timezone=True), nullable=False)


def _updated():
    return sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False)


def upgrade() -> None:
    op.create_table(
        "reliability_regulatory_profiles",
        _id(), _amo(),
        sa.Column("code", sa.String(32), nullable=False),
        sa.Column("version", sa.String(40), nullable=False),
        sa.Column("name", sa.String(255), nullable=False),
        sa.Column("authority", sa.String(32), nullable=False),
        sa.Column("jurisdiction", sa.String(64), nullable=False),
        sa.Column("effective_date", sa.Date(), nullable=True),
        sa.Column("revision", sa.String(80), nullable=True),
        sa.Column("status", sa.String(24), nullable=False),
        sa.Column("derived_from_profiles", J, nullable=False),
        sa.Column("required_sections", J, nullable=False),
        sa.Column("mandatory_kpis", J, nullable=False),
        sa.Column("minimum_analysis_periods", J, nullable=False),
        sa.Column("statistical_methods", J, nullable=False),
        sa.Column("historical_windows", J, nullable=False),
        sa.Column("commentary_rules", J, nullable=False),
        sa.Column("evidence_rules", J, nullable=False),
        sa.Column("approval_workflow", J, nullable=False),
        sa.Column("publication_rules", J, nullable=False),
        sa.Column("source_manifest", J, nullable=False),
        sa.Column("is_default", sa.Boolean(), nullable=False),
        sa.Column("supersedes_profile_id", sa.String(36), sa.ForeignKey("reliability_regulatory_profiles.id", ondelete="SET NULL"), nullable=True),
        _created(), _updated(), _user("created_by_user_id"),
        sa.UniqueConstraint("amo_id", "code", "version", name="uq_rel_reg_profile_version"),
    )
    op.create_index("ix_rel_reg_profile_active", "reliability_regulatory_profiles", ["amo_id", "code", "status"])
    op.create_index("ix_rel_reg_profile_authority", "reliability_regulatory_profiles", ["authority"])

    op.create_table(
        "reliability_regulatory_requirements",
        _id(), _amo(),
        sa.Column("profile_id", sa.String(36), sa.ForeignKey("reliability_regulatory_profiles.id", ondelete="RESTRICT"), nullable=False),
        sa.Column("requirement_key", sa.String(120), nullable=False),
        sa.Column("authority", sa.String(32), nullable=False),
        sa.Column("jurisdiction", sa.String(64), nullable=False),
        sa.Column("source_kind", sa.String(32), nullable=False),
        sa.Column("source_reference", sa.String(255), nullable=False),
        sa.Column("paragraph_reference", sa.String(120), nullable=True),
        sa.Column("source_url", sa.Text(), nullable=False),
        sa.Column("effective_date", sa.Date(), nullable=True),
        sa.Column("revision", sa.String(80), nullable=False),
        sa.Column("controlled_summary", sa.Text(), nullable=False),
        sa.Column("applicability_rule", J, nullable=False),
        sa.Column("aircraft_applicability", J, nullable=False),
        sa.Column("operator_applicability", J, nullable=False),
        sa.Column("obligation_status", sa.String(20), nullable=False),
        sa.Column("report_section_code", sa.String(80), nullable=False),
        sa.Column("data_source_codes", J, nullable=False),
        sa.Column("calculation_code", sa.String(120), nullable=True),
        sa.Column("minimum_analysis_months", sa.Integer(), nullable=True),
        sa.Column("historical_comparison_months", sa.Integer(), nullable=True),
        sa.Column("evidence_rule", J, nullable=False),
        sa.Column("approval_role", sa.String(64), nullable=True),
        sa.Column("completeness_rule", J, nullable=False),
        sa.Column("reviewer_notes", sa.Text(), nullable=True),
        sa.Column("lifecycle_status", sa.String(24), nullable=False),
        sa.Column("supersedes_requirement_id", sa.String(36), sa.ForeignKey("reliability_regulatory_requirements.id", ondelete="SET NULL"), nullable=True),
        _created(), _updated(), _user("created_by_user_id"),
        sa.UniqueConstraint("profile_id", "requirement_key", "revision", name="uq_rel_reg_requirement_revision"),
    )
    op.create_index("ix_rel_reg_requirement_profile_status", "reliability_regulatory_requirements", ["profile_id", "lifecycle_status"])
    op.create_index("ix_rel_reg_requirement_authority_ref", "reliability_regulatory_requirements", ["amo_id", "authority", "source_reference"])
    op.create_index("ix_rel_reg_requirement_key", "reliability_regulatory_requirements", ["requirement_key"])

    op.create_table(
        "reliability_formal_reports",
        _id(), _amo(),
        sa.Column("programme_id", sa.String(36), sa.ForeignKey("reliability_programmes.id", ondelete="SET NULL"), nullable=True),
        sa.Column("profile_id", sa.String(36), sa.ForeignKey("reliability_regulatory_profiles.id", ondelete="RESTRICT"), nullable=False),
        sa.Column("report_number", sa.String(100), nullable=False),
        sa.Column("revision", sa.Integer(), nullable=False),
        sa.Column("title", sa.String(255), nullable=False),
        sa.Column("period_type", sa.String(32), nullable=False),
        sa.Column("period_start", sa.Date(), nullable=False),
        sa.Column("period_end", sa.Date(), nullable=False),
        sa.Column("status", sa.String(32), nullable=False),
        sa.Column("profile_code_snapshot", sa.String(32), nullable=False),
        sa.Column("profile_version_snapshot", sa.String(40), nullable=False),
        sa.Column("regulatory_manifest", J, nullable=False),
        sa.Column("data_cutoff_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("effectivity_json", J, nullable=False),
        sa.Column("effectivity_frozen_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("source_population_json", J, nullable=False),
        sa.Column("formula_revisions_json", J, nullable=False),
        sa.Column("calculation_snapshots_json", J, nullable=False),
        sa.Column("chart_data_json", J, nullable=False),
        sa.Column("narrative_json", J, nullable=False),
        sa.Column("data_quality_json", J, nullable=False),
        sa.Column("completeness_json", J, nullable=False),
        sa.Column("rendered_html", sa.Text(), nullable=True),
        sa.Column("html_sha256", sa.String(64), nullable=True),
        sa.Column("pdf_storage_ref", sa.Text(), nullable=True),
        sa.Column("pdf_sha256", sa.String(64), nullable=True),
        sa.Column("pdf_size_bytes", sa.Integer(), nullable=True),
        sa.Column("published_at", sa.DateTime(timezone=True), nullable=True),
        _user("published_by_user_id"),
        sa.Column("supersedes_report_id", sa.String(36), sa.ForeignKey("reliability_formal_reports.id", ondelete="SET NULL"), nullable=True),
        sa.Column("superseded_at", sa.DateTime(timezone=True), nullable=True),
        _user("superseded_by_user_id"),
        sa.Column("withdrawn_at", sa.DateTime(timezone=True), nullable=True),
        _user("withdrawn_by_user_id"),
        _created(), _updated(), _user("created_by_user_id"),
        sa.UniqueConstraint("amo_id", "report_number", "revision", name="uq_rel_formal_report_revision"),
        sa.CheckConstraint("period_end >= period_start", name="ck_rel_formal_report_period"),
    )
    op.create_index("ix_rel_formal_report_status_period", "reliability_formal_reports", ["amo_id", "status", "period_start", "period_end"])
    op.create_index("ix_rel_formal_report_profile", "reliability_formal_reports", ["profile_id", "period_end"])
    op.create_index("ix_rel_formal_report_number", "reliability_formal_reports", ["amo_id", "report_number"])
    op.create_index("ix_rel_formal_report_cutoff", "reliability_formal_reports", ["data_cutoff_at"])
    op.create_index("ix_rel_formal_report_published", "reliability_formal_reports", ["published_at"])
    op.create_index("ix_rel_formal_html_sha", "reliability_formal_reports", ["html_sha256"])
    op.create_index("ix_rel_formal_pdf_sha", "reliability_formal_reports", ["pdf_sha256"])

    op.create_table(
        "reliability_formal_report_sections",
        _id(), _amo(),
        sa.Column("report_id", sa.String(36), sa.ForeignKey("reliability_formal_reports.id", ondelete="CASCADE"), nullable=False),
        sa.Column("section_code", sa.String(80), nullable=False),
        sa.Column("sequence", sa.Integer(), nullable=False),
        sa.Column("title", sa.String(255), nullable=False),
        sa.Column("required", sa.Boolean(), nullable=False),
        sa.Column("status", sa.String(24), nullable=False),
        sa.Column("computed_data", J, nullable=False),
        sa.Column("commentary", J, nullable=False),
        sa.Column("evidence_refs", J, nullable=False),
        sa.Column("warnings", J, nullable=False),
        _updated(), _user("updated_by_user_id"),
        sa.UniqueConstraint("report_id", "section_code", name="uq_rel_formal_report_section"),
    )
    op.create_index("ix_rel_formal_section_order", "reliability_formal_report_sections", ["report_id", "sequence"])

    op.create_table(
        "reliability_formal_requirement_assessments",
        _id(), _amo(),
        sa.Column("report_id", sa.String(36), sa.ForeignKey("reliability_formal_reports.id", ondelete="CASCADE"), nullable=False),
        sa.Column("requirement_id", sa.String(36), sa.ForeignKey("reliability_regulatory_requirements.id", ondelete="RESTRICT"), nullable=False),
        sa.Column("section_code", sa.String(80), nullable=False),
        sa.Column("applicable", sa.Boolean(), nullable=False),
        sa.Column("status", sa.String(24), nullable=False),
        sa.Column("requirement_snapshot", J, nullable=False),
        sa.Column("evidence_refs", J, nullable=False),
        sa.Column("calculation_refs", J, nullable=False),
        sa.Column("source_refs", J, nullable=False),
        sa.Column("reviewer_note", sa.Text(), nullable=True),
        sa.Column("resolved_at", sa.DateTime(timezone=True), nullable=True),
        _user("resolved_by_user_id"),
        _created(), _updated(),
        sa.UniqueConstraint("report_id", "requirement_id", name="uq_rel_formal_requirement_assessment"),
    )
    op.create_index("ix_rel_formal_requirement_status", "reliability_formal_requirement_assessments", ["report_id", "status"])
    op.create_index("ix_rel_formal_requirement_section", "reliability_formal_requirement_assessments", ["section_code"])

    op.create_table(
        "reliability_formal_report_sources",
        _id(), _amo(),
        sa.Column("report_id", sa.String(36), sa.ForeignKey("reliability_formal_reports.id", ondelete="CASCADE"), nullable=False),
        sa.Column("source_kind", sa.String(40), nullable=False),
        sa.Column("source_id", sa.String(128), nullable=False),
        sa.Column("source_hash", sa.String(64), nullable=True),
        sa.Column("source_date", sa.Date(), nullable=True),
        sa.Column("dataset_code", sa.String(32), nullable=True),
        sa.Column("aircraft_serial_number", sa.String(50), nullable=True),
        sa.Column("reference_code", sa.String(128), nullable=True),
        sa.Column("captured_at", sa.DateTime(timezone=True), nullable=False),
        sa.UniqueConstraint("report_id", "source_kind", "source_id", name="uq_rel_formal_report_source"),
    )
    op.create_index("ix_rel_formal_report_source_kind", "reliability_formal_report_sources", ["report_id", "source_kind"])
    op.create_index("ix_rel_formal_report_source_date", "reliability_formal_report_sources", ["source_date"])
    op.create_index("ix_rel_formal_report_source_aircraft", "reliability_formal_report_sources", ["aircraft_serial_number"])
    op.create_index("ix_rel_formal_report_source_dataset", "reliability_formal_report_sources", ["dataset_code"])

    op.create_table(
        "reliability_formal_approvals",
        _id(), _amo(),
        sa.Column("report_id", sa.String(36), sa.ForeignKey("reliability_formal_reports.id", ondelete="CASCADE"), nullable=False),
        sa.Column("stage", sa.String(32), nullable=False),
        sa.Column("decision", sa.String(24), nullable=False),
        _user("actor_user_id"),
        sa.Column("role_snapshot", sa.String(64), nullable=False),
        sa.Column("comment", sa.Text(), nullable=True),
        sa.Column("report_revision", sa.Integer(), nullable=False),
        sa.Column("report_hash", sa.String(64), nullable=True),
        _created(),
    )
    op.create_index("ix_rel_formal_approval_chain", "reliability_formal_approvals", ["report_id", "created_at"])

    op.create_table(
        "reliability_formal_lifecycle_events",
        _id(), _amo(),
        sa.Column("report_id", sa.String(36), sa.ForeignKey("reliability_formal_reports.id", ondelete="CASCADE"), nullable=False),
        sa.Column("from_status", sa.String(32), nullable=True),
        sa.Column("to_status", sa.String(32), nullable=False),
        sa.Column("action", sa.String(32), nullable=False),
        sa.Column("rationale", sa.Text(), nullable=True),
        sa.Column("payload_json", J, nullable=False),
        sa.Column("previous_hash", sa.String(64), nullable=True),
        sa.Column("event_hash", sa.String(64), nullable=False),
        _user("actor_user_id"),
        sa.Column("role_snapshot", sa.String(64), nullable=False),
        _created(),
        sa.UniqueConstraint("event_hash", name="uq_rel_formal_lifecycle_event_hash"),
    )
    op.create_index("ix_rel_formal_lifecycle_chain", "reliability_formal_lifecycle_events", ["report_id", "created_at"])

    op.create_table(
        "reliability_formal_completeness_overrides",
        _id(), _amo(),
        sa.Column("report_id", sa.String(36), sa.ForeignKey("reliability_formal_reports.id", ondelete="CASCADE"), nullable=False),
        sa.Column("check_code", sa.String(120), nullable=False),
        sa.Column("requirement_id", sa.String(36), sa.ForeignKey("reliability_regulatory_requirements.id", ondelete="SET NULL"), nullable=True),
        sa.Column("justification", sa.Text(), nullable=False),
        sa.Column("authority_basis", sa.Text(), nullable=False),
        _user("approved_by_user_id", nullable=False, ondelete="RESTRICT"),
        sa.Column("approved_role", sa.String(64), nullable=False),
        sa.Column("report_hash", sa.String(64), nullable=True),
        _created(),
    )
    op.create_index("ix_rel_formal_override_report", "reliability_formal_completeness_overrides", ["report_id", "created_at"])

    op.create_table(
        "reliability_amp_recommendations",
        _id(), _amo(),
        sa.Column("report_id", sa.String(36), sa.ForeignKey("reliability_formal_reports.id", ondelete="SET NULL"), nullable=True),
        sa.Column("programme_id", sa.String(36), sa.ForeignKey("reliability_programmes.id", ondelete="SET NULL"), nullable=True),
        sa.Column("programme_item_id", sa.Integer(), sa.ForeignKey("amp_program_items.id", ondelete="SET NULL"), nullable=True),
        sa.Column("title", sa.String(255), nullable=False),
        sa.Column("summary", sa.Text(), nullable=False),
        sa.Column("change_type", sa.String(48), nullable=False),
        sa.Column("status", sa.String(40), nullable=False),
        sa.Column("source_evidence", J, nullable=False),
        sa.Column("current_requirement", J, nullable=False),
        sa.Column("proposed_change", J, nullable=False),
        sa.Column("technical_basis", J, nullable=False),
        sa.Column("authority_approval_required", sa.Boolean(), nullable=False),
        _user("owner_user_id"),
        sa.Column("target_date", sa.Date(), nullable=True),
        sa.Column("approved_at", sa.DateTime(timezone=True), nullable=True),
        _user("approved_by_user_id"),
        sa.Column("implemented_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("effectiveness_due_date", sa.Date(), nullable=True),
        sa.Column("closed_at", sa.DateTime(timezone=True), nullable=True),
        _created(), _updated(), _user("created_by_user_id"),
    )
    op.create_index("ix_rel_amp_rec_status", "reliability_amp_recommendations", ["amo_id", "status"])
    op.create_index("ix_rel_amp_rec_report", "reliability_amp_recommendations", ["report_id", "created_at"])

    op.create_table(
        "reliability_reporting_schedule",
        _id(), _amo(),
        sa.Column("profile_id", sa.String(36), sa.ForeignKey("reliability_regulatory_profiles.id", ondelete="SET NULL"), nullable=True),
        sa.Column("programme_id", sa.String(36), sa.ForeignKey("reliability_programmes.id", ondelete="SET NULL"), nullable=True),
        sa.Column("report_id", sa.String(36), sa.ForeignKey("reliability_formal_reports.id", ondelete="SET NULL"), nullable=True),
        sa.Column("obligation_code", sa.String(100), nullable=False),
        sa.Column("name", sa.String(255), nullable=False),
        sa.Column("period_type", sa.String(32), nullable=False),
        sa.Column("period_start", sa.Date(), nullable=False),
        sa.Column("period_end", sa.Date(), nullable=False),
        sa.Column("due_date", sa.Date(), nullable=False),
        sa.Column("cycle_config", J, nullable=False),
        sa.Column("status", sa.String(32), nullable=False),
        _user("owner_user_id"),
        sa.Column("completeness_json", J, nullable=False),
        _created(), _updated(), _user("created_by_user_id"),
        sa.UniqueConstraint("amo_id", "obligation_code", "period_start", "period_end", name="uq_rel_reporting_schedule_period"),
        sa.CheckConstraint("period_end >= period_start", name="ck_rel_reporting_schedule_period"),
    )
    op.create_index("ix_rel_reporting_schedule_due", "reliability_reporting_schedule", ["amo_id", "status", "due_date"])

    op.create_table(
        "reliability_formal_distributions",
        _id(), _amo(),
        sa.Column("report_id", sa.String(36), sa.ForeignKey("reliability_formal_reports.id", ondelete="CASCADE"), nullable=False),
        _user("recipient_user_id"),
        sa.Column("recipient_role", sa.String(64), nullable=True),
        sa.Column("external_recipient_ref", sa.String(255), nullable=True),
        sa.Column("channel", sa.String(32), nullable=False),
        sa.Column("revision_snapshot", sa.Integer(), nullable=False),
        sa.Column("report_hash", sa.String(64), nullable=False),
        sa.Column("distributed_at", sa.DateTime(timezone=True), nullable=False),
        _user("distributed_by_user_id"),
        sa.Column("acknowledged_at", sa.DateTime(timezone=True), nullable=True),
    )
    op.create_index("ix_rel_formal_distribution_report", "reliability_formal_distributions", ["report_id", "distributed_at"])

    op.execute("""
    CREATE OR REPLACE FUNCTION rel_formal_report_guard() RETURNS trigger AS $$
    BEGIN
      IF TG_OP = 'DELETE' AND OLD.published_at IS NOT NULL THEN
        RAISE EXCEPTION 'published Reliability formal reports are immutable';
      END IF;
      IF TG_OP = 'UPDATE' AND OLD.published_at IS NOT NULL THEN
        IF NEW.amo_id IS DISTINCT FROM OLD.amo_id
          OR NEW.profile_id IS DISTINCT FROM OLD.profile_id
          OR NEW.report_number IS DISTINCT FROM OLD.report_number
          OR NEW.revision IS DISTINCT FROM OLD.revision
          OR NEW.period_type IS DISTINCT FROM OLD.period_type
          OR NEW.period_start IS DISTINCT FROM OLD.period_start
          OR NEW.period_end IS DISTINCT FROM OLD.period_end
          OR NEW.profile_code_snapshot IS DISTINCT FROM OLD.profile_code_snapshot
          OR NEW.profile_version_snapshot IS DISTINCT FROM OLD.profile_version_snapshot
          OR NEW.regulatory_manifest IS DISTINCT FROM OLD.regulatory_manifest
          OR NEW.data_cutoff_at IS DISTINCT FROM OLD.data_cutoff_at
          OR NEW.effectivity_json IS DISTINCT FROM OLD.effectivity_json
          OR NEW.effectivity_frozen_at IS DISTINCT FROM OLD.effectivity_frozen_at
          OR NEW.source_population_json IS DISTINCT FROM OLD.source_population_json
          OR NEW.formula_revisions_json IS DISTINCT FROM OLD.formula_revisions_json
          OR NEW.calculation_snapshots_json IS DISTINCT FROM OLD.calculation_snapshots_json
          OR NEW.chart_data_json IS DISTINCT FROM OLD.chart_data_json
          OR NEW.narrative_json IS DISTINCT FROM OLD.narrative_json
          OR NEW.data_quality_json IS DISTINCT FROM OLD.data_quality_json
          OR NEW.completeness_json IS DISTINCT FROM OLD.completeness_json
          OR NEW.rendered_html IS DISTINCT FROM OLD.rendered_html
          OR NEW.html_sha256 IS DISTINCT FROM OLD.html_sha256
          OR NEW.pdf_storage_ref IS DISTINCT FROM OLD.pdf_storage_ref
          OR NEW.pdf_sha256 IS DISTINCT FROM OLD.pdf_sha256
          OR NEW.pdf_size_bytes IS DISTINCT FROM OLD.pdf_size_bytes
          OR NEW.published_at IS DISTINCT FROM OLD.published_at
          OR NEW.published_by_user_id IS DISTINCT FROM OLD.published_by_user_id
        THEN
          RAISE EXCEPTION 'published Reliability formal report content is immutable';
        END IF;
      END IF;
      RETURN COALESCE(NEW, OLD);
    END;
    $$ LANGUAGE plpgsql;
    CREATE TRIGGER trg_rel_formal_report_guard
      BEFORE UPDATE OR DELETE ON reliability_formal_reports
      FOR EACH ROW EXECUTE FUNCTION rel_formal_report_guard();
    """)

    op.execute("""
    CREATE OR REPLACE FUNCTION rel_formal_child_guard() RETURNS trigger AS $$
    DECLARE parent_published timestamptz;
    BEGIN
      SELECT published_at INTO parent_published
        FROM reliability_formal_reports WHERE id = OLD.report_id;
      IF parent_published IS NOT NULL THEN
        RAISE EXCEPTION 'published Reliability formal report child evidence is immutable';
      END IF;
      RETURN COALESCE(NEW, OLD);
    END;
    $$ LANGUAGE plpgsql;
    """)
    for table, trigger in (
        ("reliability_formal_report_sections", "trg_rel_formal_section_guard"),
        ("reliability_formal_requirement_assessments", "trg_rel_formal_req_guard"),
        ("reliability_formal_report_sources", "trg_rel_formal_source_guard"),
        ("reliability_formal_completeness_overrides", "trg_rel_formal_override_guard"),
    ):
        op.execute(
            f"CREATE TRIGGER {trigger} BEFORE UPDATE OR DELETE ON {table} "
            "FOR EACH ROW EXECUTE FUNCTION rel_formal_child_guard();"
        )

    op.execute("""
    CREATE OR REPLACE FUNCTION rel_formal_append_only() RETURNS trigger AS $$
    BEGIN
      RAISE EXCEPTION 'Reliability formal audit records are append-only';
    END;
    $$ LANGUAGE plpgsql;
    CREATE TRIGGER trg_rel_formal_approval_append
      BEFORE UPDATE OR DELETE ON reliability_formal_approvals
      FOR EACH ROW EXECUTE FUNCTION rel_formal_append_only();
    CREATE TRIGGER trg_rel_formal_lifecycle_append
      BEFORE UPDATE OR DELETE ON reliability_formal_lifecycle_events
      FOR EACH ROW EXECUTE FUNCTION rel_formal_append_only();
    """)


def downgrade() -> None:
    op.execute("DROP TRIGGER IF EXISTS trg_rel_formal_lifecycle_append ON reliability_formal_lifecycle_events")
    op.execute("DROP TRIGGER IF EXISTS trg_rel_formal_approval_append ON reliability_formal_approvals")
    op.execute("DROP FUNCTION IF EXISTS rel_formal_append_only()")
    for table, trigger in (
        ("reliability_formal_completeness_overrides", "trg_rel_formal_override_guard"),
        ("reliability_formal_report_sources", "trg_rel_formal_source_guard"),
        ("reliability_formal_requirement_assessments", "trg_rel_formal_req_guard"),
        ("reliability_formal_report_sections", "trg_rel_formal_section_guard"),
    ):
        op.execute(f"DROP TRIGGER IF EXISTS {trigger} ON {table}")
    op.execute("DROP FUNCTION IF EXISTS rel_formal_child_guard()")
    op.execute("DROP TRIGGER IF EXISTS trg_rel_formal_report_guard ON reliability_formal_reports")
    op.execute("DROP FUNCTION IF EXISTS rel_formal_report_guard()")

    for table in (
        "reliability_formal_distributions",
        "reliability_reporting_schedule",
        "reliability_amp_recommendations",
        "reliability_formal_completeness_overrides",
        "reliability_formal_lifecycle_events",
        "reliability_formal_approvals",
        "reliability_formal_report_sources",
        "reliability_formal_requirement_assessments",
        "reliability_formal_report_sections",
        "reliability_formal_reports",
        "reliability_regulatory_requirements",
        "reliability_regulatory_profiles",
    ):
        op.drop_table(table)
