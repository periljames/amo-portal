"""Link CAR evidence to its response section without changing existing files."""
from alembic import op
import sqlalchemy as sa
revision = "quality_car_evidence_261121"
down_revision = "quality_car_feedback_261027"
branch_labels = None
depends_on = None

def upgrade():
    columns = {column["name"] for column in sa.inspect(op.get_bind()).get_columns("quality_car_attachments")}
    if "response_section" not in columns:
        op.add_column("quality_car_attachments", sa.Column("response_section", sa.String(32), nullable=True))

def downgrade():
    op.drop_column("quality_car_attachments", "response_section")
