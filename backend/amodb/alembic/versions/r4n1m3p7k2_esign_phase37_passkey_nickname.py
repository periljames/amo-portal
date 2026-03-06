"""esign phase37 passkey nickname fields

Revision ID: r4n1m3p7k2
Revises: q3a2c0m1p4
Create Date: 2026-03-05
"""

from alembic import op
import sqlalchemy as sa


revision = "r4n1m3p7k2"
down_revision = "q3a2c0m1p4"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column("esign_webauthn_credentials", sa.Column("nickname", sa.String(length=50), nullable=True))
    op.add_column("esign_webauthn_credentials", sa.Column("updated_at", sa.DateTime(timezone=True), nullable=True))
    op.execute("UPDATE esign_webauthn_credentials SET updated_at = created_at WHERE updated_at IS NULL")


def downgrade() -> None:
    op.drop_column("esign_webauthn_credentials", "updated_at")
    op.drop_column("esign_webauthn_credentials", "nickname")
