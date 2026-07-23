from __future__ import annotations

from types import SimpleNamespace
from unittest.mock import MagicMock

import pytest
from fastapi import HTTPException

from amodb.apps.accounts import models as account_models
from amodb.apps.platform import tenant_saas_job_router


def _admin(amo_id: str):
    return SimpleNamespace(
        id="admin-1",
        amo_id=amo_id,
        role=account_models.AccountRole.AMO_ADMIN,
        is_amo_admin=True,
        is_superuser=False,
        is_system_account=False,
    )


def _superuser():
    return SimpleNamespace(
        id="root-1",
        amo_id=None,
        role=account_models.AccountRole.SUPERUSER,
        is_amo_admin=False,
        is_superuser=True,
        is_system_account=False,
    )


def _job(tenant_id: str):
    return SimpleNamespace(
        id="job-1",
        queue_name="billing",
        job_type="STRIPE_CREATE_CHECKOUT_SESSION",
        tenant_id=tenant_id,
        status="SUCCEEDED",
        priority=1,
        attempt_count=1,
        max_attempts=5,
        available_at=None,
        locked_by=None,
        lease_expires_at=None,
        last_error=None,
        result_json={"checkout_url": "https://checkout.stripe.com/example"},
        created_at=None,
        updated_at=None,
        finished_at=None,
    )


def test_tenant_admin_can_read_own_job_result():
    db = MagicMock()
    db.get.return_value = _job("amo-1")

    result = tenant_saas_job_router.job_status(
        "job-1",
        db=db,
        user=_admin("amo-1"),
    )

    assert result["result"]["checkout_url"].startswith("https://checkout.stripe.com/")


def test_tenant_admin_cannot_read_another_tenants_job():
    db = MagicMock()
    db.get.return_value = _job("amo-2")

    with pytest.raises(HTTPException) as exc:
        tenant_saas_job_router.job_status(
            "job-1",
            db=db,
            user=_admin("amo-1"),
        )

    assert exc.value.status_code == 404


def test_scoped_superuser_cannot_read_outside_selected_tenant():
    db = MagicMock()
    db.get.return_value = _job("amo-2")

    with pytest.raises(HTTPException) as exc:
        tenant_saas_job_router.job_status(
            "job-1",
            tenant_id="amo-1",
            db=db,
            user=_superuser(),
        )

    assert exc.value.status_code == 404


def test_unscoped_superuser_can_read_job_result():
    db = MagicMock()
    db.get.return_value = _job("amo-2")

    result = tenant_saas_job_router.job_status(
        "job-1",
        db=db,
        user=_superuser(),
    )

    assert result["id"] == "job-1"
