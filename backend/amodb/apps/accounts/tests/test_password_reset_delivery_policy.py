from types import SimpleNamespace
from unittest.mock import MagicMock
import pytest
from fastapi import BackgroundTasks, HTTPException
from starlette.requests import Request
from amodb.apps.accounts import router_public as r, schemas
from amodb.apps.notifications import providers
from amodb.apps.platform import resend_adapter


def provider(mode='SANDBOX'):
 return providers.ResendProvider(secret={'api_key':'re_test_key'},config={'sending_mode':mode,'from_email':'security@example.com','sandbox_recipient':'sandbox@example.com','template_map_json':{'password-reset':'old-hosted-template'}},credential_status='HEALTHY')

def test_recovery_never_redirects_to_sandbox(monkeypatch):
 monkeypatch.delenv('PORTAL_ACCOUNT_RECOVERY_LIVE_DELIVERY',raising=False)
 with pytest.raises(providers.EmailDeliveryBlocked,match='cannot be redirected'):
  provider().send(template_key='password-reset',recipient='owner@example.com',subject='Reset',context={'action_url':'https://portal.example/reset-password?token=private'},correlation_id='reset-test')

def test_opted_in_recovery_goes_only_to_owner_with_expiry(monkeypatch):
 monkeypatch.setenv('PORTAL_ACCOUNT_RECOVERY_LIVE_DELIVERY','true');sent={}
 monkeypatch.setattr(resend_adapter,'send_email',lambda **kw:sent.update(kw) or {'message_id':'provider-id','provider':'resend'})
 result=provider().send(template_key='password-reset',recipient='owner@example.com',subject='Reset',context={'action_url':'https://portal.example/reset-password?token=private','expires_minutes':1440,'_cc':['other@example.com']},correlation_id='reset-test')
 assert sent['to_email']=='owner@example.com' and sent['cc'] is None and sent['template_id'] is None
 assert '24 hours' in sent['text'] and 'Reset password' in sent['html']
 assert result['mode']=='ACCOUNT_RECOVERY' and result['original_recipient']=='owner@example.com'

def test_routine_mail_stays_in_sandbox(monkeypatch):
 monkeypatch.setenv('PORTAL_ACCOUNT_RECOVERY_LIVE_DELIVERY','true');sent={}
 monkeypatch.setattr(resend_adapter,'send_email',lambda **kw:sent.update(kw) or {'message_id':'provider-id','provider':'resend'})
 provider().send(template_key='routine-update',recipient='owner@example.com',subject='Update',context={},correlation_id='routine')
 assert sent['to_email']=='sandbox@example.com'

def request():return Request({'type':'http','method':'POST','path':'/auth/password-reset/request','headers':[], 'client':('127.0.0.1',1234)})

def test_unconfigured_whatsapp_is_rejected_before_account_lookup(monkeypatch):
 monkeypatch.setattr(r,'_enforce_auth_rate_limit',lambda *a:None)
 monkeypatch.setattr(r,'_reset_delivery_channels',lambda db:{'email':True,'whatsapp':False})
 db=MagicMock()
 with pytest.raises(HTTPException) as error:r.request_password_reset(schemas.PasswordResetRequest(amo_slug='AMO',email='owner@example.com',delivery_method='whatsapp'),request(),BackgroundTasks(),db)
 assert error.value.status_code==503;db.query.assert_not_called()

def test_reset_resolves_amo_code_and_never_returns_the_token(monkeypatch):
 monkeypatch.setattr(r,'_enforce_auth_rate_limit',lambda *a:None)
 monkeypatch.setattr(r,'_reset_delivery_channels',lambda db:{'email':True,'whatsapp':False})
 resolver=MagicMock(return_value=SimpleNamespace(id='amo-id',login_slug='canonical-slug'))
 monkeypatch.setattr(r.services,'resolve_amo_by_slug_or_code',resolver)
 monkeypatch.setattr(r.services,'get_active_user_by_email',lambda **kw:SimpleNamespace(id='user-id',email='owner@example.com',phone=None))
 monkeypatch.setattr(r.services,'create_password_reset_token',lambda **kw:'private-token')
 monkeypatch.setattr(r,'RESET_LINK_BASE_URL','https://portal.example')
 send=MagicMock();monkeypatch.setattr(r,'_maybe_send_email',send)
 result=r.request_password_reset(schemas.PasswordResetRequest(amo_slug='LEGACY-CODE',email='owner@example.com'),request(),BackgroundTasks(),MagicMock())
 resolver.assert_called_once();assert resolver.call_args.args[1]=='LEGACY-CODE'
 assert 'amo=canonical-slug' in send.call_args.kwargs['action_url'];assert 'private-token' not in str(result)
 assert result.keys()=={'message'}
