import os

from argon2 import PasswordHasher
from sqlalchemy.orm import Session

from amodb.database import SessionLocal
from amodb.apps.accounts.models import AMO, User, AccountRole

EMAIL = os.getenv("AMODB_SUPERUSER_EMAIL")
PASSWORD = os.getenv("AMODB_SUPERUSER_PASSWORD")
FIRST_NAME = os.getenv("AMODB_SUPERUSER_FIRST_NAME", "Platform")
LAST_NAME = os.getenv("AMODB_SUPERUSER_LAST_NAME", "Admin")
STAFF_CODE = os.getenv("AMODB_SUPERUSER_STAFF_CODE", "SYS001")

PLATFORM_AMO_CODE = os.getenv("AMODB_PLATFORM_AMO_CODE", "PLATFORM")
PLATFORM_AMO_NAME = os.getenv("AMODB_PLATFORM_AMO_NAME", "AMOdb Platform")
PLATFORM_LOGIN_SLUG = os.getenv("AMODB_PLATFORM_LOGIN_SLUG", "root")

_pwd_hasher = PasswordHasher(
    time_cost=int(os.getenv("ARGON2_TIME_COST", "3")),
    memory_cost=int(os.getenv("ARGON2_MEMORY_COST", "65536")),
    parallelism=int(os.getenv("ARGON2_PARALLELISM", "2")),
    hash_len=int(os.getenv("ARGON2_HASH_LEN", "32")),
    salt_len=int(os.getenv("ARGON2_SALT_LEN", "16")),
)


def ensure_platform_amo(db: Session) -> AMO:
    amo = db.query(AMO).filter(AMO.amo_code == PLATFORM_AMO_CODE).first()
    if amo:
        return amo

    amo = AMO(
        amo_code=PLATFORM_AMO_CODE,
        name=PLATFORM_AMO_NAME,
        login_slug=PLATFORM_LOGIN_SLUG,
        country="",
        is_active=True,
    )
    db.add(amo)
    db.commit()
    db.refresh(amo)
    return amo


def ensure_superuser(db: Session, amo: AMO) -> User:
    existing = (
        db.query(User)
        .filter(User.amo_id == amo.id, User.email == EMAIL.lower().strip())
        .first()
    )
    if existing:
        # Ensure flags are correct
        existing.is_superuser = True
        existing.is_amo_admin = True
        existing.is_active = True
        existing.role = AccountRole.SUPERUSER
        db.add(existing)
        db.commit()
        db.refresh(existing)
        return existing

    user = User(
        amo_id=amo.id,
        department_id=None,
        staff_code=STAFF_CODE,
        email=EMAIL.lower().strip(),
        first_name=FIRST_NAME,
        last_name=LAST_NAME,
        full_name=f"{FIRST_NAME} {LAST_NAME}".strip(),
        role=AccountRole.SUPERUSER,
        is_active=True,
        is_superuser=True,
        is_amo_admin=True,
        is_system_account=False,
        hashed_password=_pwd_hasher.hash(PASSWORD),
    )
    db.add(user)
    db.commit()
    db.refresh(user)
    return user


def main() -> None:
    if not EMAIL or not PASSWORD:
        raise SystemExit(
            "Set AMODB_SUPERUSER_EMAIL and AMODB_SUPERUSER_PASSWORD before running."
        )

    db = SessionLocal()
    try:
        amo = ensure_platform_amo(db)
        user = ensure_superuser(db, amo)
        print("OK:", user.email, "superuser =", user.is_superuser, "amo_code =", amo.amo_code)
    finally:
        db.close()


if __name__ == "__main__":
    main()
