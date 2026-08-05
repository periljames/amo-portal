from __future__ import annotations

from types import SimpleNamespace

import pytest
from fastapi import HTTPException

from amodb.apps.foundations.tenant_scope import (
    AMO_CONTEXT_HEADER,
    resolve_foundation_amo_id,
)


class _QueryStub:
    def __init__(self, result):
        self._result = result

    def filter(self, *args, **kwargs):
        return self

    def first(self):
        return self._result


class _DbStub:
    def __init__(self, result=object()):
        self._result = result

    def query(self, *args, **kwargs):
        return _QueryStub(self._result)


def _user(*, superuser: bool, amo_id: str | None, effective_amo_id: str | None = None):
    return SimpleNamespace(
        is_superuser=superuser,
        amo_id=amo_id,
        active_amo_id=effective_amo_id,
        effective_amo_id=effective_amo_id,
    )


def test_superuser_write_is_bound_to_explicit_request_amo():
    user = _user(superuser=True, amo_id=None, effective_amo_id="persisted-amo")

    resolved = resolve_foundation_amo_id(
        _DbStub(),
        user,
        "request-amo",
        require_explicit_superuser=True,
    )

    assert resolved == "request-amo"
    assert resolved != user.effective_amo_id


def test_superuser_write_fails_closed_without_request_header():
    user = _user(superuser=True, amo_id=None, effective_amo_id="persisted-amo")

    with pytest.raises(HTTPException) as exc_info:
        resolve_foundation_amo_id(
            _DbStub(),
            user,
            None,
            require_explicit_superuser=True,
        )

    assert exc_info.value.status_code == 400
    assert AMO_CONTEXT_HEADER in str(exc_info.value.detail)


def test_non_superuser_cannot_cross_tenant_with_header():
    user = _user(superuser=False, amo_id="own-amo")

    with pytest.raises(HTTPException) as exc_info:
        resolve_foundation_amo_id(_DbStub(), user, "other-amo")

    assert exc_info.value.status_code == 403


def test_non_superuser_remains_bound_to_own_amo():
    user = _user(superuser=False, amo_id="own-amo")

    assert resolve_foundation_amo_id(_DbStub(), user, None) == "own-amo"
    assert resolve_foundation_amo_id(_DbStub(), user, "own-amo") == "own-amo"


def test_unknown_or_inactive_superuser_target_is_rejected():
    user = _user(superuser=True, amo_id=None, effective_amo_id="persisted-amo")

    with pytest.raises(HTTPException) as exc_info:
        resolve_foundation_amo_id(
            _DbStub(result=None),
            user,
            "inactive-amo",
            require_explicit_superuser=True,
        )

    assert exc_info.value.status_code == 404
