#!/usr/bin/env python3
import argparse
from typing import Iterable

from amodb.database import SessionLocal
from amodb.security import get_password_hash
from amodb.apps.accounts import models


def _is_known_hash(value: str | None) -> bool:
    if not value:
        return False
    return value.startswith("$argon2") or value.startswith(("$2a$", "$2b$", "$2y$"))


def _iter_target_users(
    session,
    *,
    amo_id: str | None,
    email: str | None,
) -> Iterable[models.User]:
    query = session.query(models.User)
    if amo_id:
        query = query.filter(models.User.amo_id == amo_id)
    if email:
        query = query.filter(models.User.email == email)
    return query.all()


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Re-hash user passwords that were manually inserted into the database."
    )
    parser.add_argument(
        "--password",
        required=True,
        help="The plaintext password to apply before forcing a change on next login.",
    )
    parser.add_argument("--amo-id", help="Restrict to a specific AMO id.")
    parser.add_argument("--email", help="Restrict to a single user email.")
    parser.add_argument(
        "--force",
        action="store_true",
        help="Re-hash even if the stored hash already looks valid.",
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Show which users would be updated without writing changes.",
    )
    args = parser.parse_args()

    session = SessionLocal()
    try:
        users = list(
            _iter_target_users(session, amo_id=args.amo_id, email=args.email)
        )

        if not users:
            print("No users matched the supplied filters.")
            return

        updated = []
        skipped = []

        for user in users:
            if not args.force and _is_known_hash(user.hashed_password):
                skipped.append(user)
                continue
            user.hashed_password = get_password_hash(args.password)
            user.must_change_password = True
            updated.append(user)

        if args.dry_run:
            print("Dry run complete.")
            print(f"Would update {len(updated)} user(s).")
            for user in updated:
                print(f"- {user.email} ({user.id})")
            print(f"Skipped {len(skipped)} user(s) with valid hashes.")
            return

        session.commit()
        print(f"Updated {len(updated)} user(s).")
        if skipped:
            print(f"Skipped {len(skipped)} user(s) with valid hashes.")
    finally:
        session.close()


if __name__ == "__main__":
    main()
