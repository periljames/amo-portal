"""Create or update the global platform superuser.

This account is intentionally outside the AMO tenant hierarchy:
- users.amo_id = NULL
- users.department_id = NULL
- users.is_superuser = TRUE
- users.is_amo_admin = FALSE

Tenant administrators remain AMO-scoped users. Do not seed a "platform AMO"
to host the global superuser.
"""
from __future__ import annotations

import os

from amodb.database import SessionLocal
from amodb.security import get_password_hash
from amodb.apps.accounts import models


DEFAULT_EMAIL = "root@local.test"
DEFAULT_PASSWORD = "ChangeMe123!"
DEFAULT_STAFF_CODE = "ROOT"


def _normalise_email(value: str) -> str:
    return (value or "").strip().lower()


def main() -> None:
    email = _normalise_email(os.getenv("AMO_SUPERUSER_EMAIL", DEFAULT_EMAIL))
    password = os.getenv("AMO_SUPERUSER_PASSWORD", DEFAULT_PASSWORD)
    staff_code = (os.getenv("AMO_SUPERUSER_STAFF_CODE", DEFAULT_STAFF_CODE) or DEFAULT_STAFF_CODE).strip().upper()

    db = SessionLocal()
    try:
        user = (
            db.query(models.User)
            .filter(models.User.email == email)
            .order_by(models.User.is_superuser.desc(), models.User.created_at.asc())
            .first()
        )

        if user is None:
            user = models.User(
                amo_id=None,
                department_id=None,
                staff_code=staff_code,
                email=email,
                first_name=os.getenv("AMO_SUPERUSER_FIRST_NAME", "Platform"),
                last_name=os.getenv("AMO_SUPERUSER_LAST_NAME", "Superuser"),
                full_name=os.getenv("AMO_SUPERUSER_FULL_NAME", "Platform Superuser"),
                role=models.AccountRole.SUPERUSER,
                is_active=True,
                is_superuser=True,
                is_amo_admin=False,
                is_auditor=False,
                must_change_password=True,
                hashed_password=get_password_hash(password),
            )
            db.add(user)
            action = "created"
        else:
            user.amo_id = None
            user.department_id = None
            user.role = models.AccountRole.SUPERUSER
            user.is_active = True
            user.is_superuser = True
            user.is_amo_admin = False
            user.staff_code = user.staff_code or staff_code
            if password:
                user.hashed_password = get_password_hash(password)
            db.add(user)
            action = "updated"

        db.commit()
        print(f"Platform superuser {action}: {email}")
    finally:
        db.close()


if __name__ == "__main__":
    main()
