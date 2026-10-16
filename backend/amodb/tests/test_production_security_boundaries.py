"""Focused source-boundary regression tests for production hardening.

Full PostgreSQL/RLS, two-browser and external-provider acceptance is separate.
"""
from __future__ import annotations

from types import SimpleNamespace

import pytest
from fastapi import HTTPException
from sqlalchemy import create_engine
from sqlalchemy.orm import Session, sessionmaker
from starlette.requests import Request

from amodb.database import Base
from amodb.apps.accounts import models as accounts, session_service, services
from amodb.apps.manuals import models as manuals
from amodb.apps.manuals.core_router import transition_revision, transition_revision_lifecycle
from amodb.apps.manuals.tenant_route_guard import (
    require_manuals_tenant_access,
    require_manuals_record_access,
    require_manuals_export_access,
)
from amodb.security import get_current_active_user


@pytest.fixture()
def security_db():
    engine = create_engine("sqlite+pysqlite:///:memory:")
    Base.metadata.create_all(bind=engine, tables=[
        accounts.AMO.__table__,
        accounts.Department.__table__,
        accounts.User.__table__,
        accounts.PortalAuthSession.__table__,
        accounts.RefreshSessionToken.__table__,
        accounts.PortalRefreshSession.__table__,
        accounts.UserActiveContext.__table__,
        accounts.AccountSecurityEvent.__table__,
        accounts.PasswordResetToken.__table__,
        manuals.Tenant.__table__,
        manuals.Manual.__table__,
        manuals.ManualRevision.__table__,
        manuals.PrintExport.__table__,
    ])
    db = sessionmaker(bind=engine, expire_on_commit=False)()
    try:
        yield db
    finally:
        db.close()
        engine.dispose()


def _amo(db: Session, key: str):
    row = accounts.AMO(
        amo_code=key.upper(), login_slug=key.lower(), name=f"{key} tenant", is_active=True,
    )
    db.add(row)
    db.flush()
    db.add(manuals.Tenant(amo_id=row.id, slug=key.lower(), name=row.name, settings_json={}))
    db.commit()
    return row


def _user(db: Session, amo: accounts.AMO, key: str, *, root: bool = False):
    user = accounts.User(
        amo_id=amo.id, email=f"{key}@example.com", staff_code=key.upper(),
        first_name="Test", last_name="User", full_name="Test User",
        hashed_password="unused", role=accounts.AccountRole.SUPERUSER if root else accounts.AccountRole.TECHNICIAN,
        is_superuser=root, is_active=True, must_change_password=False,
    )
    db.add(user)
    db.commit()
    return user


def _request(slug: str, *, path: str | None = None):
    path = path or f"/manuals/t/{slug}"
    return Request({
        "type": "http", "method": "GET", "path": path,
        "scheme": "http", "server": ("testserver", 80),
        "headers": [], "query_string": b"", "path_params": {"tenant_slug": slug},
    })


def test_manuals_legacy_routes_require_exact_active_tenant(security_db):
    a = _amo(security_db, "alpha")
    b = _amo(security_db, "bravo")
    alice = _user(security_db, a, "alice")
    require_manuals_tenant_access(_request("alpha"), db=security_db, user=alice)
    with pytest.raises(HTTPException) as denied:
        require_manuals_tenant_access(_request("bravo"), db=security_db, user=alice)
    assert denied.value.status_code == 404

    a.is_active = False
    security_db.commit()
    with pytest.raises(HTTPException) as inactive:
        require_manuals_tenant_access(_request("alpha"), db=security_db, user=alice)
    assert inactive.value.status_code == 404


def test_platform_manuals_access_requires_explicit_support_selection(security_db):
    root_amo = _amo(security_db, "root")
    target = _amo(security_db, "target")
    root = _user(security_db, root_amo, "owner", root=True)
    with pytest.raises(HTTPException):
        require_manuals_tenant_access(_request("target"), db=security_db, user=root)
    root.active_amo_id = target.id
    require_manuals_tenant_access(_request("target"), db=security_db, user=root)


def test_manual_revision_and_export_identifiers_cannot_escape_tenant(security_db):
    own = _amo(security_db, "alpha")
    foreign = _amo(security_db, "bravo")
    alice = _user(security_db, own, "alice")
    foreign_tenant = (
        security_db.query(manuals.Tenant).filter_by(amo_id=foreign.id).one()
    )
    manual = manuals.Manual(
        tenant_id=foreign_tenant.id, code="MPM", title="Foreign MPM",
        manual_type="MPM", owner_role="DOCUMENT_CONTROL_OFFICER",
    )
    security_db.add(manual)
    security_db.flush()
    rev = manuals.ManualRevision(manual_id=manual.id, rev_number="1")
    security_db.add(rev)
    security_db.flush()
    export = manuals.PrintExport(
        revision_id=rev.id, storage_uri="private", sha256="a" * 64,
    )
    security_db.add(export)
    security_db.commit()

    record_req = _request("alpha", path=f"/manuals/t/alpha/{manual.id}/rev/{rev.id}/read")
    record_req.scope["path_params"].update({"manual_id": manual.id, "rev_id": rev.id})
    with pytest.raises(HTTPException) as wrong_record:
        require_manuals_record_access(record_req, db=security_db, user=alice)
    assert wrong_record.value.status_code == 404

    export_req = _request("alpha", path=f"/manuals/exports/{export.id}/print-log")
    export_req.scope["path_params"] = {"export_id": export.id}
    with pytest.raises(HTTPException) as wrong_export:
        require_manuals_export_access(export_req, db=security_db, user=alice)
    assert wrong_export.value.status_code == 404


def test_refresh_cannot_survive_revocation_or_tenant_suspension(security_db):
    amo = _amo(security_db, "alpha")
    user = _user(security_db, amo, "person")
    issued = session_service.create_session(
        security_db, user=user, ip_address=None, user_agent="test",
    )
    session_service.revoke_user_sessions(security_db, user=user, reason="password_changed")
    security_db.commit()
    with pytest.raises(session_service.RefreshRejected):
        session_service.rotate_session(security_db, raw_token=issued.refresh_token)

    second = session_service.create_session(
        security_db, user=user, ip_address=None, user_agent="test",
    )
    amo.is_active = False
    security_db.commit()
    with pytest.raises(session_service.RefreshRejected):
        session_service.rotate_session(security_db, raw_token=second.refresh_token)


def test_password_reset_token_is_indexed_single_use_and_revokes_session(security_db):
    amo = _amo(security_db, "alpha")
    user = _user(security_db, amo, "person")
    issued = session_service.create_session(
        security_db, user=user, ip_address=None, user_agent="test",
    )
    raw = services.create_password_reset_token(security_db, user=user)
    row = services._find_matching_reset_token(security_db, raw)
    assert row is not None
    assert row.token_hash.startswith("hmac-sha256:")
    assert raw not in row.token_hash

    changed = services.redeem_password_reset_token(
        security_db, raw_token=raw, new_password="StrongNewPassword2026!",
    )
    assert changed is not None
    assert services._find_matching_reset_token(security_db, raw) is None
    with pytest.raises(session_service.RefreshRejected):
        session_service.rotate_session(security_db, raw_token=issued.refresh_token)


def test_must_change_password_rejects_direct_business_api(security_db):
    amo = _amo(security_db, "alpha")
    user = _user(security_db, amo, "person")
    user.must_change_password = True
    security_db.commit()
    with pytest.raises(HTTPException) as exc:
        get_current_active_user(user, security_db, _request("alpha"))
    assert exc.value.status_code == 403


@pytest.mark.parametrize("handler", [transition_revision, transition_revision_lifecycle])
def test_legacy_publication_workflow_cannot_change_status(handler):
    with pytest.raises(HTTPException) as exc:
        handler(
            tenant_slug="alpha", manual_id="m", rev_id="r",
            payload=SimpleNamespace(action="publish"),
            request=None, db=None,
            **({"current_user": None} if handler is transition_revision_lifecycle else {}),
        )
    assert exc.value.status_code == 410
