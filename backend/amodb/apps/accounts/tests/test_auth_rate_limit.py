from concurrent.futures import ThreadPoolExecutor

import pytest
from fastapi import HTTPException

from amodb.apps.accounts import auth_rate_limit as limiter


@pytest.fixture(autouse=True)
def isolated_limiter(monkeypatch):
    limiter.STATE.clear()
    monkeypatch.setattr(limiter, "_redis_client", lambda: None)


def test_concurrent_attempts_cannot_overspend_limit():
    def attempt(_):
        try:
            limiter.enforce("same-account", "login", 10)
            return 200
        except HTTPException as exc:
            assert int(exc.headers["Retry-After"]) >= 1
            return exc.status_code

    with ThreadPoolExecutor(max_workers=32) as pool:
        statuses = list(pool.map(attempt, range(1000)))
    assert statuses.count(200) == 10
    assert statuses.count(429) == 990


def test_1000_sessions_share_network_without_sharing_session_budget():
    for index in range(1000):
        limiter.enforce("office-ip", "refresh", limiter.IP_MAX_ATTEMPTS)
        limiter.enforce(f"session-{index}", "refresh-session")
    for _ in range(limiter.MAX_ATTEMPTS - 1):
        limiter.enforce("session-0", "refresh-session")
    with pytest.raises(HTTPException) as error:
        limiter.enforce("session-0", "refresh-session")
    assert error.value.status_code == 429
    limiter.enforce("session-999", "refresh-session")


def test_expired_keys_are_removed_and_full_store_fails_closed(monkeypatch):
    monkeypatch.setattr(limiter, "MAX_KEYS", 2)
    monkeypatch.setattr(limiter.time, "monotonic", lambda: 100.0)
    limiter.enforce("one", "login")
    limiter.enforce("two", "login")
    with pytest.raises(HTTPException) as error:
        limiter.enforce("three", "login")
    assert error.value.status_code == 503
    assert len(limiter.STATE) == 2
    monkeypatch.setattr(limiter.time, "monotonic", lambda: 100.0 + limiter.WINDOW_SECONDS)
    limiter.enforce("three", "login")
    assert len(limiter.STATE) == 1


def test_redis_deadline_is_returned_without_leaking_identity(monkeypatch):
    class Redis:
        def eval(self, script, count, key, window):
            assert "private@example.com" not in key
            assert count == 1
            assert window == limiter.WINDOW_SECONDS * 1000
            return [11, 2501]

    monkeypatch.setattr(limiter, "_redis_client", lambda: Redis())
    with pytest.raises(HTTPException) as error:
        limiter.enforce("private@example.com", "login", 10)
    assert error.value.status_code == 429
    assert error.value.headers["Retry-After"] == "3"


def test_shared_limiter_outage_does_not_fall_back_to_local_counters(monkeypatch):
    def unavailable():
        raise ConnectionError("test outage")

    monkeypatch.setattr(limiter, "_redis_client", unavailable)
    with pytest.raises(HTTPException) as error:
        limiter.enforce("one", "login")
    assert error.value.status_code == 503
    assert not limiter.STATE
