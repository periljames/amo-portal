from __future__ import annotations

import os
from uuid import uuid4

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import Session

from amodb.apps.accounts import models as account_models
from amodb.apps.workforce import hr_people_directory, hr_schemas


def _id() -> str:
    return str(uuid4())


def _postgres_session() -> tuple[object, object, object, Session]:
    engine = create_engine(os.environ["DATABASE_URL"], pool_pre_ping=True)
    connection = engine.connect()
    transaction = connection.begin()
    db = Session(bind=connection, autoflush=False, expire_on_commit=False)
    return engine, connection, transaction, db


def _close_postgres_session(engine, connection, transaction, db: Session) -> None:
    db.close()
    if transaction.is_active:
        transaction.rollback()
    connection.close()
    engine.dispose()


@pytest.mark.skipif(
    not os.getenv("DATABASE_URL", "").startswith("postgresql"),
    reason="PostgreSQL integration database is not configured",
)
def test_directory_keeps_a_1500_person_tenant_bounded_and_server_paginated() -> None:
    engine, connection, transaction, db = _postgres_session()
    try:
        amo_id = _id()
        engineering_id = _id()
        quality_id = _id()
        db.add(
            account_models.AMO(
                id=amo_id,
                amo_code=f"SCALE-{amo_id[:8]}",
                name="Workforce Scale Test",
                login_slug=f"workforce-scale-{amo_id[:8]}",
                time_zone="UTC",
            )
        )
        db.add_all([
            account_models.Department(
                id=engineering_id,
                amo_id=amo_id,
                code="ENG",
                name="Engineering",
                is_active=True,
            ),
            account_models.Department(
                id=quality_id,
                amo_id=amo_id,
                code="QMS",
                name="Quality",
                is_active=True,
            ),
        ])
        db.flush()

        users = []
        for index in range(1_500):
            department_id = engineering_id if index < 1_000 else quality_id
            role = (
                account_models.AccountRole.TECHNICIAN
                if index % 2 == 0
                else account_models.AccountRole.PRODUCTION_ENGINEER
            )
            users.append(
                account_models.User(
                    id=_id(),
                    amo_id=amo_id,
                    department_id=department_id,
                    staff_code=f"SCALE-{index:04d}",
                    email=f"scale-{index:04d}@directory.invalid",
                    first_name=f"Person {index:04d}",
                    last_name="Scale",
                    full_name=f"Person {index:04d} Scale",
                    position_title=(
                        "Aircraft Technician"
                        if role == account_models.AccountRole.TECHNICIAN
                        else "Production Engineer"
                    ),
                    role=role,
                    hashed_password="not-a-real-password-hash",
                    is_active=True,
                    is_system_account=False,
                )
            )
        db.add_all(users)
        db.flush()
        db.expunge_all()

        page = hr_people_directory.list_people_page(
            db,
            amo_id=amo_id,
            page=7,
            page_size=100,
            filters=hr_schemas.HrPeopleFilterInput(
                department_id=engineering_id,
                sort_by="staff_code",
                sort_dir="asc",
            ),
        )

        assert page.total == 1_000
        assert page.pages == 10
        assert page.page == 7
        assert page.page_size == 100
        assert len(page.items) == 100
        assert page.items[0].staff_code == "SCALE-0600"
        assert page.items[-1].staff_code == "SCALE-0699"

        loaded_users = [
            value
            for value in db.identity_map.values()
            if isinstance(value, account_models.User)
        ]
        assert len(loaded_users) <= 100

        search = hr_people_directory.list_people_page(
            db,
            amo_id=amo_id,
            page=1,
            page_size=25,
            filters=hr_schemas.HrPeopleFilterInput(search="SCALE-1499"),
        )
        assert search.total == 1
        assert [item.staff_code for item in search.items] == ["SCALE-1499"]

        selected = hr_people_directory.resolve_selection_user_ids(
            db,
            amo_id=amo_id,
            selection=hr_schemas.HrPeopleSelection(
                mode="FILTERED",
                filters=hr_schemas.HrPeopleFilterInput(
                    department_id=quality_id,
                    role="TECHNICIAN",
                ),
                exclude_user_ids=[],
            ),
        )
        assert len(selected) == 250
    finally:
        _close_postgres_session(engine, connection, transaction, db)
