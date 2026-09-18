from datetime import datetime, timedelta, timezone
from types import SimpleNamespace
from unittest.mock import Mock

import pytest
from fastapi import HTTPException

from amodb.apps.accounts import session_service


def test_session_budget_runs_before_rotation_and_uses_verified_session_id():
    future = datetime.now(timezone.utc) + timedelta(hours=1)
    token = SimpleNamespace(session_id="verified-session", revoked_at=None, expires_at=future)
    session = SimpleNamespace(id="verified-session", revoked_at=None, expires_at=future)
    token_query = Mock()
    token_query.filter.return_value.with_for_update.return_value.first.return_value = token
    session_query = Mock()
    session_query.filter.return_value.with_for_update.return_value.first.return_value = session
    db = Mock()
    db.query.side_effect = [token_query, session_query]
    budget = Mock(side_effect=HTTPException(429, "limited", headers={"Retry-After": "60"}))

    with pytest.raises(HTTPException) as error:
        session_service.rotate_session(db, raw_token="untrusted-cookie", before_rotation=budget)

    assert error.value.status_code == 429
    budget.assert_called_once_with("verified-session")
    db.add.assert_not_called()
    db.flush.assert_not_called()
    db.commit.assert_not_called()


def test_invalid_cookie_never_selects_a_session_budget():
    db = Mock()
    db.query.return_value.filter.return_value.with_for_update.return_value.first.return_value = None
    budget = Mock()
    with pytest.raises(session_service.RefreshRejected):
        session_service.rotate_session(db, raw_token="forged-cookie", before_rotation=budget)
    budget.assert_not_called()
