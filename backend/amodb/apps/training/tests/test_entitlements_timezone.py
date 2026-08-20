from __future__ import annotations

from datetime import datetime, timedelta, timezone
from types import SimpleNamespace

from amodb import entitlements
from amodb.apps.accounts import models as account_models


class _Query:
    def __init__(self, subscription):
        self._subscription = subscription

    def filter(self, *_args, **_kwargs):
        return self

    def order_by(self, *_args, **_kwargs):
        return self

    def first(self):
        return self._subscription


class _DB:
    def __init__(self, subscription):
        self._subscription = subscription

    def query(self, *_args, **_kwargs):
        return _Query(self._subscription)


def _subscription(*, effective_from: datetime, effective_to: datetime):
    return SimpleNamespace(
        effective_from=effective_from,
        effective_to=effective_to,
        status=account_models.ModuleSubscriptionStatus.ENABLED,
    )


def test_module_subscription_window_accepts_postgres_aware_datetimes():
    now = datetime.now(timezone.utc)
    row = _subscription(
        effective_from=now - timedelta(minutes=5),
        effective_to=now + timedelta(minutes=5),
    )

    assert entitlements._has_module_subscription(_DB(row), "amo-1", "training") is True


def test_module_subscription_window_preserves_legacy_naive_utc_values():
    now = datetime.now(timezone.utc).replace(tzinfo=None)
    row = _subscription(
        effective_from=now - timedelta(minutes=5),
        effective_to=now + timedelta(minutes=5),
    )

    assert entitlements._has_module_subscription(_DB(row), "amo-1", "training") is True
