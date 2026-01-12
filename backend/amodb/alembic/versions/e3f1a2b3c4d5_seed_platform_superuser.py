"""seed platform superuser

Revision ID: e3f1a2b3c4d5
Revises: d2f8c9a1b4e7
Create Date: 2025-01-05 00:00:00.000000
"""
from __future__ import annotations

import os
import uuid
from datetime import datetime, timezone
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa

from amodb.security import get_password_hash

# revision identifiers, used by Alembic.
revision: str = "e3f1a2b3c4d5"
down_revision: Union[str, Sequence[str], None] = "d2f8c9a1b4e7"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


AMO_CODE = os.getenv("AMODB_PLATFORM_AMO_CODE", "PLATFORM")
AMO_NAME = os.getenv("AMODB_PLATFORM_AMO_NAME", "AMOdb Platform")
AMO_LOGIN_SLUG = os.getenv("AMODB_PLATFORM_LOGIN_SLUG", "root")

EMAIL = os.getenv("AMODB_SUPERUSER_EMAIL")
PASSWORD = os.getenv("AMODB_SUPERUSER_PASSWORD")
FIRST_NAME = os.getenv("AMODB_SUPERUSER_FIRST_NAME", "Platform")
LAST_NAME = os.getenv("AMODB_SUPERUSER_LAST_NAME", "Admin")
STAFF_CODE = os.getenv("AMODB_SUPERUSER_STAFF_CODE", "SYS001")


def upgrade() -> None:
    if not EMAIL or not PASSWORD:
        return

    now = datetime.now(timezone.utc)
    conn = op.get_bind()

    amos = sa.table(
        "amos",
        sa.column("id", sa.String(length=36)),
        sa.column("amo_code", sa.String(length=32)),
        sa.column("name", sa.String(length=255)),
        sa.column("icao_code", sa.String(length=8)),
        sa.column("country", sa.String(length=64)),
        sa.column("login_slug", sa.String(length=64)),
        sa.column("contact_email", sa.String(length=255)),
        sa.column("contact_phone", sa.String(length=64)),
        sa.column("time_zone", sa.String(length=64)),
        sa.column("is_active", sa.Boolean()),
        sa.column("created_at", sa.DateTime(timezone=True)),
        sa.column("updated_at", sa.DateTime(timezone=True)),
    )

    users = sa.table(
        "users",
        sa.column("id", sa.String(length=36)),
        sa.column("amo_id", sa.String(length=36)),
        sa.column("department_id", sa.String(length=36)),
        sa.column("staff_code", sa.String(length=32)),
        sa.column("email", sa.String(length=255)),
        sa.column("first_name", sa.String(length=128)),
        sa.column("last_name", sa.String(length=128)),
        sa.column("full_name", sa.String(length=255)),
        sa.column("role", sa.String(length=32)),
        sa.column("is_active", sa.Boolean()),
        sa.column("is_superuser", sa.Boolean()),
        sa.column("is_amo_admin", sa.Boolean()),
        sa.column("is_system_account", sa.Boolean()),
        sa.column("position_title", sa.String(length=255)),
        sa.column("phone", sa.String(length=64)),
        sa.column("regulatory_authority", sa.String(length=32)),
        sa.column("licence_number", sa.String(length=64)),
        sa.column("licence_state_or_country", sa.String(length=64)),
        sa.column("licence_expires_on", sa.Date()),
        sa.column("approved_by_user_id", sa.String(length=36)),
        sa.column("approved_at", sa.DateTime(timezone=True)),
        sa.column("approval_notes", sa.Text()),
        sa.column("deactivated_at", sa.DateTime(timezone=True)),
        sa.column("deactivated_reason", sa.Text()),
        sa.column("hashed_password", sa.String(length=255)),
        sa.column("login_attempts", sa.Integer()),
        sa.column("locked_until", sa.DateTime(timezone=True)),
        sa.column("last_login_at", sa.DateTime(timezone=True)),
        sa.column("last_login_ip", sa.String(length=64)),
        sa.column("last_login_user_agent", sa.Text()),
        sa.column("webauthn_registered", sa.Boolean()),
        sa.column("created_at", sa.DateTime(timezone=True)),
        sa.column("updated_at", sa.DateTime(timezone=True)),
    )

    amo_id = conn.execute(
        sa.select(amos.c.id).where(amos.c.amo_code == AMO_CODE)
    ).scalar()

    if not amo_id:
        amo_id = str(uuid.uuid4())
        conn.execute(
            amos.insert().values(
                id=amo_id,
                amo_code=AMO_CODE,
                name=AMO_NAME,
                icao_code=None,
                country=None,
                login_slug=AMO_LOGIN_SLUG,
                contact_email=None,
                contact_phone=None,
                time_zone=None,
                is_active=True,
                created_at=now,
                updated_at=now,
            )
        )

    normalized_email = EMAIL.lower().strip()
    user_id = conn.execute(
        sa.select(users.c.id).where(
            users.c.amo_id == amo_id,
            users.c.email == normalized_email,
        )
    ).scalar()

    full_name = f"{FIRST_NAME} {LAST_NAME}".strip()
    hashed_password = get_password_hash(PASSWORD)

    if user_id:
        conn.execute(
            users.update()
            .where(users.c.id == user_id)
            .values(
                staff_code=STAFF_CODE,
                first_name=FIRST_NAME,
                last_name=LAST_NAME,
                full_name=full_name,
                role="SUPERUSER",
                is_active=True,
                is_superuser=True,
                is_amo_admin=True,
                is_system_account=False,
                hashed_password=hashed_password,
                updated_at=now,
            )
        )
    else:
        conn.execute(
            users.insert().values(
                id=str(uuid.uuid4()),
                amo_id=amo_id,
                department_id=None,
                staff_code=STAFF_CODE,
                email=normalized_email,
                first_name=FIRST_NAME,
                last_name=LAST_NAME,
                full_name=full_name,
                role="SUPERUSER",
                is_active=True,
                is_superuser=True,
                is_amo_admin=True,
                is_system_account=False,
                position_title=None,
                phone=None,
                regulatory_authority=None,
                licence_number=None,
                licence_state_or_country=None,
                licence_expires_on=None,
                approved_by_user_id=None,
                approved_at=None,
                approval_notes=None,
                deactivated_at=None,
                deactivated_reason=None,
                hashed_password=hashed_password,
                login_attempts=0,
                locked_until=None,
                last_login_at=None,
                last_login_ip=None,
                last_login_user_agent=None,
                webauthn_registered=False,
                created_at=now,
                updated_at=now,
            )
        )


def downgrade() -> None:
    pass
