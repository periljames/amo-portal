"""Merge formal Reliability Programme reporting with current Document Control head."""
from __future__ import annotations

from alembic import op

revision = "rel_20260807_formal_docgov_merge"
down_revision = ("rel_20260807_formal_reporting", "docgov_rel_20260807_merge")
branch_labels = None
depends_on = None


_REPORT_GUARD = r"""
CREATE OR REPLACE FUNCTION rel_formal_report_guard() RETURNS trigger AS $$
BEGIN
  IF TG_OP = 'DELETE' AND OLD.published_at IS NOT NULL THEN
    RAISE EXCEPTION 'published Reliability formal reports are immutable';
  END IF;
  IF TG_OP = 'UPDATE' AND OLD.published_at IS NOT NULL THEN
    IF NEW.amo_id IS DISTINCT FROM OLD.amo_id
      OR NEW.profile_id IS DISTINCT FROM OLD.profile_id
      OR NEW.programme_id IS DISTINCT FROM OLD.programme_id
      OR NEW.report_number IS DISTINCT FROM OLD.report_number
      OR NEW.revision IS DISTINCT FROM OLD.revision
      OR NEW.title IS DISTINCT FROM OLD.title
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
      OR NEW.supersedes_report_id IS DISTINCT FROM OLD.supersedes_report_id
    THEN
      RAISE EXCEPTION 'published Reliability formal report content is immutable';
    END IF;
  END IF;
  RETURN COALESCE(NEW, OLD);
END;
$$ LANGUAGE plpgsql;
"""


_CHILD_GUARD = r"""
CREATE OR REPLACE FUNCTION rel_formal_child_guard() RETURNS trigger AS $$
DECLARE
  parent_report_id text;
  parent_published timestamptz;
BEGIN
  parent_report_id := CASE WHEN TG_OP = 'DELETE' THEN OLD.report_id ELSE NEW.report_id END;
  SELECT published_at INTO parent_published
    FROM reliability_formal_reports
    WHERE id = parent_report_id;
  IF parent_published IS NOT NULL THEN
    RAISE EXCEPTION 'published Reliability formal report child evidence is immutable';
  END IF;
  RETURN CASE WHEN TG_OP = 'DELETE' THEN OLD ELSE NEW END;
END;
$$ LANGUAGE plpgsql;
"""


_CHILD_TRIGGERS = (
    ("reliability_formal_report_sections", "trg_rel_formal_section_guard"),
    ("reliability_formal_requirement_assessments", "trg_rel_formal_req_guard"),
    ("reliability_formal_report_sources", "trg_rel_formal_source_guard"),
    ("reliability_formal_completeness_overrides", "trg_rel_formal_override_guard"),
)


def upgrade() -> None:
    # The join is schema-neutral except for tightening formal publication
    # immutability discovered by executable PostgreSQL regressions/review.
    # Lifecycle-only state metadata (SUPERSEDED/WITHDRAWN and timestamps) remains
    # mutable so controlled supersession/withdrawal can be recorded without
    # rewriting the retained report identity/content.
    op.execute(_REPORT_GUARD)
    op.execute(_CHILD_GUARD)
    for table, trigger in _CHILD_TRIGGERS:
        op.execute(f"DROP TRIGGER IF EXISTS {trigger} ON {table}")
        op.execute(
            f"CREATE TRIGGER {trigger} BEFORE INSERT OR UPDATE OR DELETE ON {table} "
            "FOR EACH ROW EXECUTE FUNCTION rel_formal_child_guard();"
        )


def downgrade() -> None:
    # Downgrading the merge marker does not remove the underlying formal-report
    # schema. Its parent revision owns the original guard definitions.
    pass
