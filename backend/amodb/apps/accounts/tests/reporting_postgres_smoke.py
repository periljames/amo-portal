"""PostgreSQL smoke test for reporting-line integrity.

Executed directly by CI after a clean Alembic upgrade. It deliberately bypasses
the SQLite unit-test fixture so row locking, foreign keys and the shared
assignment flush guard are exercised against the production database dialect.
"""
from __future__ import annotations

import os
from datetime import date
from uuid import uuid4

from fastapi import HTTPException
from sqlalchemy import create_engine, text
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import sessionmaker

from amodb.apps.accounts import corporate_structure_models as org_models
from amodb.apps.accounts import models
from amodb.apps.foundations import models as foundation_models


def _id() -> str:
    return str(uuid4())


def _expect_conflict(Session, assignment: org_models.PositionAssignment, expected: str) -> None:
    session = Session()
    try:
        session.add(assignment)
        try:
            session.commit()
        except HTTPException as exc:
            session.rollback()
            assert exc.status_code == 409
            assert expected in str(exc.detail)
        else:
            raise AssertionError("Expected assignment integrity conflict was not raised")
    finally:
        session.close()


def main() -> None:
    database_url = os.environ["DATABASE_URL"]
    if not database_url.startswith("postgresql"):
        raise RuntimeError("reporting_postgres_smoke must run against PostgreSQL")

    engine = create_engine(database_url, pool_pre_ping=True)
    Session = sessionmaker(bind=engine, autoflush=False, expire_on_commit=False)

    amo_id = _id()
    department_id = _id()
    base_id = _id()
    unit_id = _id()
    first_position_id = _id()
    second_position_id = _id()
    first_user_id = _id()
    second_user_id = _id()

    session = Session()
    try:
        session.add(
            models.AMO(
                id=amo_id,
                amo_code=f"CI-{amo_id[:8]}",
                name="Reporting Integrity CI",
                login_slug=f"reporting-{amo_id[:8]}",
            )
        )
        session.add(
            models.Department(
                id=department_id,
                amo_id=amo_id,
                code="ENGINEERING",
                name="Engineering",
            )
        )
        session.add_all(
            [
                models.User(
                    id=first_user_id,
                    amo_id=amo_id,
                    department_id=department_id,
                    staff_code=f"CI-{first_user_id[:8]}",
                    email=f"{first_user_id[:8]}@ci.invalid",
                    first_name="First",
                    last_name="Engineer",
                    full_name="First Engineer",
                    role=models.AccountRole.TECHNICIAN,
                    hashed_password="not-a-real-password-hash",
                ),
                models.User(
                    id=second_user_id,
                    amo_id=amo_id,
                    department_id=department_id,
                    staff_code=f"CI-{second_user_id[:8]}",
                    email=f"{second_user_id[:8]}@ci.invalid",
                    first_name="Second",
                    last_name="Engineer",
                    full_name="Second Engineer",
                    role=models.AccountRole.TECHNICIAN,
                    hashed_password="not-a-real-password-hash",
                ),
            ]
        )
        session.add(
            foundation_models.BaseStation(
                id=base_id,
                amo_id=amo_id,
                code="CI-BASE",
                name="CI Base",
                base_type=foundation_models.BaseStationType.MAIN_BASE,
            )
        )
        session.add(
            org_models.OrganizationUnit(
                id=unit_id,
                amo_id=amo_id,
                department_id=department_id,
                base_station_id=base_id,
                code="CI-ENG",
                name="CI Engineering",
                unit_type="DEPARTMENT",
            )
        )
        session.add_all(
            [
                org_models.OrganizationPosition(
                    id=first_position_id,
                    amo_id=amo_id,
                    unit_id=unit_id,
                    code="CI-ENGINEER-1",
                    title="Engineer I",
                    headcount_limit=1,
                ),
                org_models.OrganizationPosition(
                    id=second_position_id,
                    amo_id=amo_id,
                    unit_id=unit_id,
                    code="CI-ENGINEER-2",
                    title="Engineer II",
                    headcount_limit=1,
                ),
            ]
        )
        session.commit()
    finally:
        session.close()

    session = Session()
    try:
        session.add(
            org_models.PositionAssignment(
                id=_id(),
                amo_id=amo_id,
                user_id=first_user_id,
                position_id=first_position_id,
                assignment_type="SUBSTANTIVE",
                status="ACTIVE",
                is_primary=True,
                matrix_reporting=False,
                fte_percent=100,
                effective_from=date(2026, 1, 1),
                effective_to=date(2026, 12, 31),
            )
        )
        session.commit()
    finally:
        session.close()

    _expect_conflict(
        Session,
        org_models.PositionAssignment(
            id=_id(),
            amo_id=amo_id,
            user_id=first_user_id,
            position_id=second_position_id,
            assignment_type="SUBSTANTIVE",
            status="ACTIVE",
            is_primary=True,
            matrix_reporting=False,
            fte_percent=100,
            effective_from=date(2026, 6, 1),
            effective_to=None,
        ),
        "already has a primary position assignment",
    )

    _expect_conflict(
        Session,
        org_models.PositionAssignment(
            id=_id(),
            amo_id=amo_id,
            user_id=second_user_id,
            position_id=first_position_id,
            assignment_type="SUBSTANTIVE",
            status="ACTIVE",
            is_primary=True,
            matrix_reporting=False,
            fte_percent=100,
            effective_from=date(2026, 4, 1),
            effective_to=date(2026, 5, 1),
        ),
        "approved headcount",
    )

    session = Session()
    try:
        session.add(
            org_models.PositionAssignment(
                id=_id(),
                amo_id=amo_id,
                user_id=first_user_id,
                position_id=second_position_id,
                assignment_type="SUBSTANTIVE",
                status="ACTIVE",
                is_primary=True,
                matrix_reporting=False,
                fte_percent=100,
                effective_from=date(2027, 1, 1),
                effective_to=None,
            )
        )
        session.commit()
    finally:
        session.close()

    session = Session()
    try:
        session.add(
            org_models.OrganizationUnit(
                id=_id(),
                amo_id=amo_id,
                base_station_id=_id(),
                code="CI-BAD-BASE",
                name="Invalid Base Reference",
                unit_type="DEPARTMENT",
            )
        )
        try:
            session.commit()
        except IntegrityError:
            session.rollback()
        else:
            raise AssertionError("organization_units.base_station_id foreign key was not enforced")
    finally:
        session.close()

    with engine.begin() as connection:
        connection.execute(text("DELETE FROM amos WHERE id = :amo_id"), {"amo_id": amo_id})

    print("PostgreSQL reporting integrity smoke test passed")


if __name__ == "__main__":
    main()
