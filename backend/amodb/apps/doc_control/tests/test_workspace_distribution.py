from __future__ import annotations

from types import SimpleNamespace

import pytest
from fastapi import HTTPException
from starlette.requests import Request

from amodb.apps.doc_control import domain_models as dm
from amodb.apps.doc_control import workspace_distribution_router as distribution
from amodb.apps.doc_control import workspace_schemas as schemas


def _request() -> Request:
    return Request(
        {
            "type": "http",
            "method": "POST",
            "path": "/doc-control/workspace/t/safarilink/distribution-campaigns/campaign-1/acknowledge",
            "raw_path": b"/doc-control/workspace/t/safarilink/distribution-campaigns/campaign-1/acknowledge",
            "root_path": "",
            "scheme": "https",
            "query_string": b"",
            "headers": [],
            "client": ("127.0.0.1", 1234),
            "server": ("testserver", 443),
        }
    )


class _Query:
    def __init__(self, rows):
        self.rows = list(rows)

    def filter(self, *args, **kwargs):
        return self

    def first(self):
        return self.rows[0] if self.rows else None

    def all(self):
        return list(self.rows)


class _DB:
    def __init__(self, rows_by_model):
        self.rows_by_model = rows_by_model

    def query(self, model, *args, **kwargs):
        return _Query(self.rows_by_model.get(model, []))


def _tenant():
    return SimpleNamespace(id="tenant-1", amo_id="amo-1")


def _user():
    return SimpleNamespace(
        id="user-1",
        role="TECHNICIAN",
        amo_id="amo-1",
        is_superuser=False,
        is_amo_admin=False,
    )


def _campaign(*, status="ISSUED", acknowledgement_required=True):
    return SimpleNamespace(
        id="campaign-1",
        tenant_id="amo-1",
        manual_id="manual-1",
        revision_id="revision-1",
        temporary_revision_id=None,
        status=status,
        acknowledgement_required=acknowledgement_required,
    )


def _recipient(*, status="PENDING", notified_at="2026-07-25T12:00:00Z"):
    return SimpleNamespace(
        id="recipient-1",
        tenant_id="amo-1",
        campaign_id="campaign-1",
        recipient_user_id="user-1",
        status=status,
        notified_at=notified_at,
    )


def test_profile_requirement_cannot_be_disabled_when_campaign_is_created(monkeypatch) -> None:
    captured = {}
    monkeypatch.setattr(distribution, "resolve_tenant", lambda *args, **kwargs: _tenant())
    monkeypatch.setattr(distribution, "get_manual", lambda *args, **kwargs: SimpleNamespace(id="manual-1"))
    monkeypatch.setattr(distribution, "get_revision", lambda *args, **kwargs: SimpleNamespace(id="revision-1"))
    monkeypatch.setattr(
        distribution,
        "get_profile",
        lambda *args, **kwargs: SimpleNamespace(acknowledgement_required=True),
    )
    monkeypatch.setattr(distribution, "require_control_user", lambda *args, **kwargs: None)
    monkeypatch.setattr(
        distribution,
        "resolve_distribution_users",
        lambda *args, **kwargs: [SimpleNamespace(id="user-1")],
    )

    def capture(**kwargs):
        captured["payload"] = kwargs["payload"]
        return {"status": "DRAFT"}

    monkeypatch.setattr(distribution, "_create_distribution_campaign", capture)
    payload = schemas.DistributionCampaignCreate(
        manual_id="manual-1",
        revision_id="revision-1",
        title="Issue revision",
        acknowledgement_required=False,
    )

    distribution.create_guarded_distribution_campaign(
        tenant_slug="safarilink",
        payload=payload,
        request=_request(),
        db=SimpleNamespace(),
        current_user=SimpleNamespace(),
    )

    assert captured["payload"].acknowledgement_required is True
    assert captured["payload"].recipient_user_ids == ["user-1"]


def test_all_eligible_audience_is_resolved_server_side(monkeypatch) -> None:
    captured = {}
    monkeypatch.setattr(distribution, "resolve_tenant", lambda *args, **kwargs: _tenant())
    monkeypatch.setattr(distribution, "get_manual", lambda *args, **kwargs: SimpleNamespace(id="manual-1"))
    monkeypatch.setattr(distribution, "get_revision", lambda *args, **kwargs: SimpleNamespace(id="revision-1"))
    monkeypatch.setattr(distribution, "get_profile", lambda *args, **kwargs: SimpleNamespace(acknowledgement_required=False))
    monkeypatch.setattr(distribution, "require_control_user", lambda *args, **kwargs: None)

    def resolve(*args, **kwargs):
        captured["mode"] = kwargs["audience_mode"]
        return [SimpleNamespace(id="user-1"), SimpleNamespace(id="user-2")]

    monkeypatch.setattr(distribution, "resolve_distribution_users", resolve)
    monkeypatch.setattr(distribution, "_create_distribution_campaign", lambda **kwargs: captured.setdefault("payload", kwargs["payload"]) or {"status": "DRAFT"})
    payload = schemas.DistributionCampaignCreate(
        manual_id="manual-1",
        revision_id="revision-1",
        title="All staff issue",
        audience={"mode": "ALL_ELIGIBLE_USERS"},
    )

    distribution.create_guarded_distribution_campaign(
        tenant_slug="safarilink",
        payload=payload,
        request=_request(),
        db=SimpleNamespace(),
        current_user=SimpleNamespace(),
    )

    assert captured["mode"] == "ALL_ELIGIBLE_USERS"
    assert captured["payload"].recipient_user_ids == ["user-1", "user-2"]
    assert captured["payload"].audience["resolved_count"] == 2


def test_draft_campaign_cannot_be_acknowledged(monkeypatch) -> None:
    monkeypatch.setattr(distribution, "resolve_tenant", lambda *args, **kwargs: _tenant())
    db = _DB({dm.DocumentDistributionCampaign: [_campaign(status="DRAFT")]})

    with pytest.raises(HTTPException) as caught:
        distribution.acknowledge_issued_distribution_campaign(
            tenant_slug="safarilink",
            campaign_id="campaign-1",
            payload=schemas.DistributionAcknowledgeRequest(),
            request=_request(),
            db=db,
            current_user=_user(),
        )

    assert caught.value.status_code == 409


def test_delivery_only_campaign_cannot_be_acknowledged(monkeypatch) -> None:
    monkeypatch.setattr(distribution, "resolve_tenant", lambda *args, **kwargs: _tenant())
    db = _DB(
        {
            dm.DocumentDistributionCampaign: [
                _campaign(status="ISSUED", acknowledgement_required=False)
            ]
        }
    )

    with pytest.raises(HTTPException) as caught:
        distribution.acknowledge_issued_distribution_campaign(
            tenant_slug="safarilink",
            campaign_id="campaign-1",
            payload=schemas.DistributionAcknowledgeRequest(),
            request=_request(),
            db=db,
            current_user=_user(),
        )

    assert caught.value.status_code == 409


def test_unissued_recipient_cannot_acknowledge(monkeypatch) -> None:
    monkeypatch.setattr(distribution, "resolve_tenant", lambda *args, **kwargs: _tenant())
    db = _DB(
        {
            dm.DocumentDistributionCampaign: [_campaign()],
            dm.DocumentDistributionRecipient: [_recipient(notified_at=None)],
        }
    )

    with pytest.raises(HTTPException) as caught:
        distribution.acknowledge_issued_distribution_campaign(
            tenant_slug="safarilink",
            campaign_id="campaign-1",
            payload=schemas.DistributionAcknowledgeRequest(),
            request=_request(),
            db=db,
            current_user=_user(),
        )

    assert caught.value.status_code == 409
    assert "not been issued" in str(caught.value.detail)


def test_non_pending_recipient_state_cannot_be_acknowledged(monkeypatch) -> None:
    monkeypatch.setattr(distribution, "resolve_tenant", lambda *args, **kwargs: _tenant())
    db = _DB(
        {
            dm.DocumentDistributionCampaign: [_campaign()],
            dm.DocumentDistributionRecipient: [_recipient(status="DELIVERED")],
        }
    )

    with pytest.raises(HTTPException) as caught:
        distribution.acknowledge_issued_distribution_campaign(
            tenant_slug="safarilink",
            campaign_id="campaign-1",
            payload=schemas.DistributionAcknowledgeRequest(),
            request=_request(),
            db=db,
            current_user=_user(),
        )

    assert caught.value.status_code == 409
