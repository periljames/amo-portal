from sqlalchemy.orm import Session

from amodb.database import SessionLocal
from amodb.security import get_password_hash
from amodb.apps.accounts.models import AMO, User, AccountRole

EMAIL = "jamesmuisyo99@outlook.com"
PASSWORD = "Q1w2e3r4t5y6!"  # don't commit this to git
FIRST_NAME = "James"
LAST_NAME = "Muisyo"
STAFF_CODE = "SYS001"

PLATFORM_AMO_CODE = "PLATFORM"
PLATFORM_AMO_NAME = "AMOdb Platform"
PLATFORM_LOGIN_SLUG = "root"


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
        hashed_password=get_password_hash(PASSWORD),
    )
    db.add(user)
    db.commit()
    db.refresh(user)
    return user


def main() -> None:
    db = SessionLocal()
    try:
        amo = ensure_platform_amo(db)
        user = ensure_superuser(db, amo)
        print("OK:", user.email, "superuser =", user.is_superuser, "amo_code =", amo.amo_code)
    finally:
        db.close()


if __name__ == "__main__":
    main()
