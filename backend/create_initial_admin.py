# backend/create_initial_admin.py

from amodb.database import SessionLocal
from amodb import models
from amodb.security import get_password_hash


def main() -> None:
    db = SessionLocal()
    try:
        email = "admin@amo.local"
        password = "ChangeMe123!"

        # Check if it already exists
        existing = db.query(models.User).filter(models.User.email == email).first()
        if existing:
            print(f"[INFO] User already exists: id={existing.id}, email={existing.email}")
            return

        user = models.User(
            user_code="ADM001",
            email=email,
            full_name="AMO Admin",
            role="admin",
            is_active=True,
            hashed_password=get_password_hash(password),
        )

        db.add(user)
        db.commit()
        db.refresh(user)

        print("[OK] Created admin user:")
        print(f"  id:      {user.id}")
        print(f"  email:   {user.email}")
        print(f"  role:    {user.role}")
        print(f"  login password: {password}")
    finally:
        db.close()


if __name__ == "__main__":
    main()
