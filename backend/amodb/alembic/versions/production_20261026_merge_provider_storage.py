"""Merge external-provider oversight and Venspera tenant storage quota revisions.

Both independently developed schema branches are required for production
migration. No schema operations are needed at the join.
"""

revision = "plat_261026_merge_heads"
down_revision = ("extprov_261019_oversight", "plat_20261016_storage_bytes")
branch_labels = None
depends_on = None


def upgrade() -> None:
    pass


def downgrade() -> None:
    pass
