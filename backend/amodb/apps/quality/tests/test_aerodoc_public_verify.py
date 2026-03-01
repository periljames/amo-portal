from __future__ import annotations

from uuid import uuid4

from fastapi import HTTPException
from starlette.requests import Request

from amodb.apps.accounts import models as account_models
from amodb.apps.aerodoc_router import _VERIFY_RATE_LIMIT_STATE, public_verify_copy
from amodb.apps.quality import models as quality_models
from amodb.apps.audit import models as audit_models


def _ensure_tables(db_session):
    quality_models.QMSPhysicalControlledCopy.__table__.create(bind=db_session.bind, checkfirst=True)
    account_models.ModuleSubscription.__table__.create(bind=db_session.bind, checkfirst=True)


def _request(ip: str = "127.0.0.1") -> Request:
    return Request({"type": "http", "headers": [], "client": (ip, 1234)})


def _enable_module(db_session, amo_id: str):
    row = account_models.ModuleSubscription(
        amo_id=amo_id,
        module_code="aerodoc_hybrid_dms",
        status=account_models.ModuleSubscriptionStatus.ENABLED,
    )
    db_session.add(row)
    db_session.commit()


def test_public_verify_requires_module_enabled(db_session):
    _VERIFY_RATE_LIMIT_STATE.clear()
    _ensure_tables(db_session)
    amo = account_models.AMO(amo_code=f"AMO-{uuid4().hex[:6]}", name="AMO", login_slug=f"amo-{uuid4().hex[:6]}")
    db_session.add(amo)
    db_session.commit()

    try:
        public_verify_copy(serial="UNKNOWN-SERIAL", amo_id=amo.id, request=_request(), db=db_session)
        assert False, "expected module disabled"
    except HTTPException as exc:
        assert exc.status_code == 403


def test_public_verify_returns_minimal_red_for_unknown(db_session):
    _VERIFY_RATE_LIMIT_STATE.clear()
    _ensure_tables(db_session)
    amo = account_models.AMO(amo_code=f"AMO-{uuid4().hex[:6]}", name="AMO", login_slug=f"amo-{uuid4().hex[:6]}")
    db_session.add(amo)
    db_session.commit()
    _enable_module(db_session, amo.id)

    out = public_verify_copy(serial="UNKNOWN-SERIAL", amo_id=amo.id, request=_request(), db=db_session)
    assert out["status"] == "RED"
    assert "approved_version" not in out or out["approved_version"] is None


def test_public_verify_rate_limited(db_session, monkeypatch):
    _VERIFY_RATE_LIMIT_STATE.clear()
    _ensure_tables(db_session)
    amo = account_models.AMO(amo_code=f"AMO-{uuid4().hex[:6]}", name="AMO", login_slug=f"amo-{uuid4().hex[:6]}")
    db_session.add(amo)
    db_session.commit()
    _enable_module(db_session, amo.id)

    import amodb.apps.aerodoc_router as router_mod

    monkeypatch.setattr(router_mod, "_VERIFY_RATE_LIMIT_MAX_ATTEMPTS", 1)
    monkeypatch.setattr(router_mod, "_VERIFY_RATE_LIMIT_WINDOW_SEC", 60)

    public_verify_copy(serial="UNKNOWN-SERIAL", amo_id=amo.id, request=_request("10.0.0.1"), db=db_session)
    try:
        public_verify_copy(serial="UNKNOWN-SERIAL", amo_id=amo.id, request=_request("10.0.0.1"), db=db_session)
        assert False, "expected rate limit"
    except HTTPException as exc:
        assert exc.status_code == 429

    event = (
        db_session.query(audit_models.AuditEvent)
        .filter(audit_models.AuditEvent.entity_type == "qms.physical_copy.verify_public", audit_models.AuditEvent.action == "rate_limited")
        .first()
    )
    assert event is not None
