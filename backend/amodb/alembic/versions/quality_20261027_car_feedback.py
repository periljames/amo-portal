"""Retained shared CAR feedback on the existing activity log."""
from alembic import op
import sqlalchemy as sa

revision = "quality_car_feedback_261027"
down_revision = "quality_car_rca_261022"
branch_labels = None
depends_on = None


def upgrade():
    op.add_column("quality_car_actions", sa.Column("visibility", sa.String(16), nullable=False, server_default="INTERNAL"))
    op.add_column("quality_car_actions", sa.Column("actor_kind", sa.String(16), nullable=False, server_default="STAFF"))
    op.add_column("quality_car_actions", sa.Column("actor_name", sa.String(255), nullable=True))
    op.add_column("quality_car_actions", sa.Column("client_message_id", sa.String(80), nullable=True))
    op.create_unique_constraint("uq_car_activity_client_message", "quality_car_actions", ["car_id", "client_message_id"])


def downgrade():
    if op.get_bind().execute(sa.text("SELECT 1 FROM quality_car_actions WHERE visibility='SHARED' LIMIT 1")).first():
        raise RuntimeError("Shared CAR feedback must be retained; destructive downgrade refused.")
    op.drop_constraint("uq_car_activity_client_message", "quality_car_actions", type_="unique")
    for name in ("client_message_id", "actor_name", "actor_kind", "visibility"):
        op.drop_column("quality_car_actions", name)
