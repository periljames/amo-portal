from datetime import timedelta
from types import SimpleNamespace
from unittest.mock import MagicMock
import pytest
from fastapi import HTTPException
from amodb.apps.procurement import external_auth_core as core
from amodb.apps.procurement import external_auth_router as router
from amodb.apps.notifications.providers import _fallback_content


def record(**changes):
    return dict(id="token",amo_id="ID-TENANT",identity_id="person",grant_id="grant",tenant_active=True,
                used_at=None,revoked_at=None,expires_at=core.now()+timedelta(minutes=10),**changes)


def test_new_code_is_six_digits_hashed_scoped_and_expires_in_ten_minutes(monkeypatch):
    captured=[]
    monkeypatch.setattr(core.secrets,"randbelow",lambda n:123)
    monkeypatch.setattr(core,"one",lambda sql,db,**kw: {"id":"person"} if "external_identities" in sql else None)
    monkeypatch.setattr(core,"run",lambda sql,db,**kw:captured.append((sql,kw)))
    before=core.now()
    code=core.token(MagicMock(),tenant_id="ID-TENANT",identity_id="person",grant_id="grant",kind="INVITE")
    assert code=="000123"
    insert=captured[-1][1]
    assert insert["hash"]==core.email_code_hash("ID-TENANT","person","INVITE",code)
    assert insert["hash"]!=core.digest(code)
    assert before+timedelta(minutes=10)<=insert["expires"]<=core.now()+timedelta(minutes=10)
    assert "revoked_at" in captured[0][0]
    assert code not in str(captured)


def test_code_hash_is_bound_to_tenant_identity_and_purpose():
    original=core.email_code_hash("tenant","person","INVITE","000123")
    assert all(original!=core.email_code_hash(*scope,"000123") for scope in [
        ("other","person","INVITE"),("tenant","other","INVITE"),("tenant","person","RESET")])


@pytest.mark.parametrize("state",["valid","expired","used","revoked"])
def test_short_code_checks_scope_and_single_use(monkeypatch,state):
    row=record()
    if state=="expired":row["expires_at"]=core.now()-timedelta(seconds=1)
    elif state=="used":row["used_at"]=core.now()
    elif state=="revoked":row["revoked_at"]=core.now()
    monkeypatch.setattr(core,"tenant",lambda db,slug:"ID-TENANT")
    monkeypatch.setattr(core,"context",lambda *args:None)
    def one(sql,db,**kw):
        if "external_identities" in sql:
            assert kw["email"]=="person@example.test"
            return {"id":"person"}
        assert kw["amo"]=="ID-TENANT"
        assert kw["hash"]==core.email_code_hash("ID-TENANT","person","INVITE","000123")
        assert "FOR UPDATE" in sql
        return row
    monkeypatch.setattr(core,"one",one)
    consume=MagicMock();monkeypatch.setattr(core,"run",consume)
    if state=="valid":
        assert core.redeem_token(MagicMock(),"000123","INVITE",amo_slug="tenant",email="Person@example.test")==row
        consume.assert_called_once()
    else:
        with pytest.raises(HTTPException):core.redeem_token(MagicMock(),"000123","INVITE",amo_slug="tenant",email="person@example.test")
        consume.assert_not_called()


def test_legacy_code_accepts_non_uuid_tenant_id(monkeypatch):
    monkeypatch.setattr(core,"context",lambda *args:None)
    monkeypatch.setattr(core,"one",lambda sql,db,**kw:record())
    monkeypatch.setattr(core,"run",lambda *args,**kw:None)
    assert core.redeem_token(MagicMock(),"ID-TENANT."+"x"*40,"INVITE")["amo_id"]=="ID-TENANT"


def test_changing_guessed_code_does_not_reset_attempt_budget(monkeypatch):
    calls=[]
    monkeypatch.setattr(core,"tenant",lambda db,slug:"canonical-tenant")
    monkeypatch.setattr(core,"auth_limit",lambda *args:None)
    monkeypatch.setattr(core.auth_rate_limit,"enforce",lambda subject,endpoint,**kw:calls.append((subject,endpoint,kw)))
    monkeypatch.setattr(core,"redeem_token",lambda *args,**kw:None)
    for code in ["000001","999999"]:
        router._redeem_code(MagicMock(),router.AccountAction(code=code,amo_slug="tenant",email="person@example.com"),SimpleNamespace(),"INVITE")
    assert calls[0]==calls[1]
    assert calls[0][2]=={"limit":5,"window_seconds":600}


def test_email_is_short_and_explicit_about_expiry():
    body,plain=_fallback_content("external-provider-invitation","Your Venspera access code",{
        "message":"Your code", "code":"000123", "expires_minutes":10,"event":"invitation",
        "action_url":"https://portal.example.test/vendor/invite?amo=tenant"})
    assert "000123" in body and "000123" in plain
    assert "10 minutes" in plain
    assert "complete your vendor invitation" in plain
    assert "can be used once" in plain
    assert "&lt;" not in plain


def test_session_supports_short_tenant_id_without_bypassing_suspension(monkeypatch):
    monkeypatch.setattr(core,"context",lambda *args:None)
    monkeypatch.setattr(core,"one",lambda sql,db,**kw:{"tenant_active":False,"amo_id":"ID-TENANT","identity_id":"person"})
    with pytest.raises(HTTPException) as failure:
        core.active_session(MagicMock(),SimpleNamespace(cookies={core.COOKIE:"ID-TENANT."+"x"*40}))
    assert failure.value.status_code==403


@pytest.mark.parametrize("available,recent",[(False,False),(True,True),(True,False)])
def test_public_resend_is_generic_scoped_and_preserves_recent_code(monkeypatch,available,recent):
    monkeypatch.setattr(core,"auth_limit",lambda *args:None)
    monkeypatch.setattr(core.auth_rate_limit,"enforce",lambda *args,**kw:None)
    monkeypatch.setattr(core,"tenant",lambda *args:"ID-TENANT")
    monkeypatch.setattr(core,"context",lambda *args:None)
    def lookup(sql,db,**kw):
        if "FROM external_tenant_grants" in sql:
            assert "g.status='PENDING'" in sql and "EXISTS" in sql
            assert "g.created_at" not in sql
            assert kw=={"amo":"ID-TENANT","email":"person@example.com"}
            return {"id":"grant","identity_id":"person"} if available else None
        if "FOR UPDATE" in sql:return {"id":"person"}
        return {"id":"recent"} if recent else None
    monkeypatch.setattr(core,"one",lookup)
    issue=MagicMock(return_value="123456");monkeypatch.setattr(core,"token",issue)
    monkeypatch.setattr(core,"event",lambda *args,**kw:None)
    send=MagicMock();monkeypatch.setattr(router,"_send",send)
    result=router.request_invitation_code(router.RecoveryRequest(amo_slug="tenant",email="person@example.com"),SimpleNamespace(),MagicMock())
    assert result=={"message":"If a pending invitation matches, a new code will be emailed. It expires in 10 minutes."}
    assert "123456" not in str(result)
    assert issue.call_count==send.call_count==int(available and not recent)


def test_code_email_cannot_be_replaced_by_a_hosted_template_missing_expiry(monkeypatch):
    from amodb.apps.notifications.providers import ResendProvider
    from amodb.apps.platform import resend_adapter
    calls=[]
    monkeypatch.setattr(resend_adapter,"send_email",lambda **kw:calls.append(kw) or {"id":"test"})
    provider=ResendProvider(secret={"api_key":"re_fake_test"},credential_status="HEALTHY",config={
        "sending_mode":"SANDBOX","sandbox_recipient":"sandbox@example.com",
        "from_email":"notifications@example.com","template_map_json":'{"external-provider-invitation":"old-template"}'})
    provider.send(template_key="external-provider-invitation",recipient="person@example.com",subject="Your access code",
                  context={"message":"Your one-time code", "code":"123456","expires_minutes":10},correlation_id="test")
    assert calls[0]["template_id"] is None
    assert "10 minutes" in calls[0]["text"]
    assert calls[0]["to_email"]=="sandbox@example.com"
