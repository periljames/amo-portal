from fastapi import HTTPException
from fastapi.security import HTTPAuthorizationCredentials

from amodb.apps.accounts import models as account_models
from amodb.apps.realtime.router import get_current_active_realtime_user
from amodb.security import create_access_token


def test_realtime_user_dependency_returns_helpful_error_without_bearer(db_session):
    try:
        get_current_active_realtime_user(credentials=None, db=db_session)
        assert False, "Expected HTTPException"
    except HTTPException as exc:
        assert exc.status_code == 401
        assert exc.detail == "Missing Bearer token. Send header: Authorization: Bearer <JWT>"


def test_realtime_user_dependency_accepts_valid_bearer_token(db_session):
    amo = account_models.AMO(amo_code="AMO1", name="AMO One", login_slug="amo-one")
    db_session.add(amo)
    db_session.flush()

    user = account_models.User(
        amo_id=amo.id,
        staff_code="S001",
        email="test@example.com",
        first_name="Test",
        last_name="User",
        full_name="Test User",
        role=account_models.AccountRole.TECHNICIAN,
        hashed_password="x",
        is_active=True,
    )
    db_session.add(user)
    db_session.commit()

    jwt_token = create_access_token(data={"sub": user.id, "amo_id": amo.id})
    credentials = HTTPAuthorizationCredentials(scheme="Bearer", credentials=jwt_token)

    authed_user = get_current_active_realtime_user(credentials=credentials, db=db_session)
    assert authed_user.id == user.id
