"""esign phase 1.1 hardening

Revision ID: f1h1a2r3d4n5
Revises: e5s1g2n3m4o5
Create Date: 2026-03-04 00:00:01.000000
"""

from __future__ import annotations

import hashlib

from alembic import op
import sqlalchemy as sa


revision = "f1h1a2r3d4n5"
down_revision = "e5s1g2n3m4o5"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column("esign_webauthn_challenges", sa.Column("challenge_hash", sa.String(length=64), nullable=True))

    bind = op.get_bind()
    rows = bind.execute(sa.text("SELECT id, challenge FROM esign_webauthn_challenges")).fetchall()
    for row in rows:
        challenge = row[1] or ""
        bind.execute(
            sa.text("UPDATE esign_webauthn_challenges SET challenge_hash=:h WHERE id=:id"),
            {"h": hashlib.sha256(challenge.encode("utf-8")).hexdigest(), "id": row[0]},
        )

    op.alter_column("esign_webauthn_challenges", "challenge_hash", nullable=False)
    op.create_index("ix_esign_webauthn_challenges_lookup", "esign_webauthn_challenges", ["tenant_id", "owner_id", "challenge_hash", "challenge_type"], unique=False)


def downgrade() -> None:
    op.drop_index("ix_esign_webauthn_challenges_lookup", table_name="esign_webauthn_challenges")
    op.drop_column("esign_webauthn_challenges", "challenge_hash")
