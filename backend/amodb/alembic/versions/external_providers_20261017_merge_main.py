"""Merge upstream governed reliability lineage with the Phase 7 external-provider lineage.

Both histories branch from quality_261003_evidence_context; this empty Alembic
merge prevents a second database head after synchronizing PR #560 with main.
No unrelated schema objects are created or dropped.
"""
revision = "extprov_261017_main_merge"
down_revision = ("extprov_261016_work", "rel_261015_octm_governed")
branch_labels = None
depends_on = None


def upgrade():
    pass


def downgrade():
    pass
