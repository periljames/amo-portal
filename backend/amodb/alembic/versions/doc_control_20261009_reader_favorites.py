"""Keep library favorites separate from reader bookmarks."""
from alembic import op
import sqlalchemy as sa

revision = "docctl_261009_favorites"
down_revision = "quality_261003_evidence_context"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column(
        "manual_reader_progress",
        sa.Column("is_favorite", sa.Boolean(), nullable=False, server_default=sa.false()),
    )
    op.execute(sa.text(
        "UPDATE manual_reader_progress SET is_favorite = true, bookmark_label = NULL "
        "WHERE bookmark_label = 'DMS_FAVORITE'"
    ))


def downgrade() -> None:
    op.drop_column("manual_reader_progress", "is_favorite")
