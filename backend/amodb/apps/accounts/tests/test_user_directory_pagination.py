from __future__ import annotations

from datetime import datetime, timedelta, timezone

import pytest
from pydantic import ValidationError

from amodb.apps.accounts import models, schemas
from amodb.apps.realtime.models import PresenceState

from amodb.apps.accounts.router_user_directory import (
    PRESENCE_FRESH_SECONDS,
    resolve_directory_presence,
    get_user_directory_page,
)


def test_directory_and_account_reads_accept_imported_personnel_email(db_session):
    PresenceState.__table__.create(db_session.get_bind(), checkfirst=True)
    tenant = models.AMO(amo_code="DIRECTORY", name="Directory", login_slug="directory")
    db_session.add(tenant)
    db_session.flush()
    users = [
        models.User(
            amo_id=tenant.id, staff_code=code, email=email,
            first_name=code, last_name="Person", full_name=f"{code} Person",
            role=models.AccountRole.AMO_ADMIN if code == "ADMIN" else models.AccountRole.TECHNICIAN,
            hashed_password="unused", is_active=True, is_amo_admin=code == "ADMIN",
        )
        for code, email in [("ADMIN", "admin@example.com"), ("IMPORTED", "imported@personnel.invalid")]
    ]
    db_session.add_all(users)
    db_session.commit()

    result = get_user_directory_page(
        amo_id=tenant.id, page=1, page_size=50, skip=None, limit=None,
        db=db_session, current_user=users[0],
    )
    assert result.total == 2
    assert {item.email for item in result.items} == {user.email for user in users}
    assert result.metrics.total_users == 2
    assert schemas.UserRead.model_validate(users[1]).email == "imported@personnel.invalid"
    member = schemas.UserGroupMemberRead(
        id="member", group_id="group", user_id=users[1].id, full_name=users[1].full_name,
        email=users[1].email, staff_code=users[1].staff_code,
        member_role="member", added_at=datetime.now(timezone.utc),
    )
    assert member.email == users[1].email


@pytest.mark.parametrize("email", ["imported@personnel.invalid", "not-an-email"])
def test_new_account_input_still_rejects_invalid_email(email):
    with pytest.raises(ValidationError) as error:
        schemas.UserCreate(
            amo_id="tenant", staff_code="NEW", email=email,
            first_name="New", last_name="Person", role=models.AccountRole.TECHNICIAN,
            password="unused-password",
        )
    assert any(item["loc"] == ("email",) for item in error.value.errors())


def test_directory_treats_fresh_away_user_as_connected():
    now = datetime.now(timezone.utc)
    presence = resolve_directory_presence(
        raw_state="away",
        last_seen_at=now - timedelta(seconds=30),
        now=now,
    )
    assert presence.state == "away"
    assert presence.is_online is True


def test_directory_marks_expired_presence_offline():
    now = datetime.now(timezone.utc)
    presence = resolve_directory_presence(
        raw_state="online",
        last_seen_at=now - timedelta(seconds=PRESENCE_FRESH_SECONDS + 1),
        now=now,
    )
    assert presence.state == "offline"
    assert presence.is_online is False


def test_directory_route_is_registered_once():
    from amodb.apps.accounts.router_admin import router

    routes = [
        route
        for route in router.routes
        if getattr(route, "path", None) == "/accounts/admin/user-directory"
        and "GET" in (getattr(route, "methods", None) or set())
    ]
    assert len(routes) == 1
