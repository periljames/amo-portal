import asyncio
from datetime import datetime, timedelta, timezone
from types import SimpleNamespace
from unittest.mock import MagicMock, AsyncMock
import uuid
import pytest
from fastapi import HTTPException, UploadFile
from jose import jwt
from amodb.security import SECRET_KEY, JWT_ALGORITHM
from amodb.apps.quality import audit_evidence_router as r
from amodb.apps.quality.audit_evidence_storage import _validate_signature

def token(**overrides):
    data=dict(aud='qms-phone-evidence',purpose='checklist-photo',amo='tenant-a',code='AMO-A',actor='user-a',audit=str(uuid.uuid4()),item=str(uuid.uuid4()),jti='capture-session',exp=datetime.now(timezone.utc)+timedelta(minutes=10))
    data.update(overrides)
    return jwt.encode(data,SECRET_KEY,algorithm=JWT_ALGORITHM)

def setup(monkeypatch):
    monkeypatch.setattr(r,'set_postgres_tenant_context',lambda *a,**kw:None)
    monkeypatch.setattr(r,'assert_quality_permission_any',lambda *a,**kw:None)
    monkeypatch.setattr(r,'_internal_fieldwork_actor',lambda *a,**kw:None)
    monkeypatch.setattr(r,'_item',lambda *a,**kw:SimpleNamespace(prompt='Question',checklist_ref='1.1',finding_id=None))

@pytest.mark.parametrize('override',[{'exp':datetime.now(timezone.utc)-timedelta(seconds=1)},{'aud':'login'},{'purpose':'login'}])
def test_expiry_and_purpose_are_enforced(monkeypatch,override):
    setup(monkeypatch)
    with pytest.raises(HTTPException) as exc:r._phone_capture_grant(token(**override),MagicMock())
    assert exc.value.status_code==401

def test_scoped_actor_and_item_are_retained(monkeypatch):
    setup(monkeypatch)
    data,ctx,audit,item,_=r._phone_capture_grant(token(),MagicMock())
    assert ctx.amo_id=='tenant-a' and ctx.user_id=='user-a' and not ctx.is_superuser
    assert str(item)==data['item'] and str(audit)==data['audit']

def test_revoked_permission_stops_capture(monkeypatch):
    setup(monkeypatch)
    def deny(*a,**kw):raise HTTPException(403,'Access removed')
    monkeypatch.setattr(r,'assert_quality_permission_any',deny)
    with pytest.raises(HTTPException) as exc:r._phone_capture_grant(token(),MagicMock())
    assert exc.value.status_code==403

@pytest.mark.parametrize("version", [7, None])
def test_upload_uses_current_version_and_stable_session_mutation(monkeypatch, version):
    setup(monkeypatch)
    monkeypatch.setattr(r,'_locked_governance',lambda *a,**kw:SimpleNamespace(entity_version=version) if version is not None else None)
    upload=AsyncMock(return_value={'artifact':{'id':'photo'}});monkeypatch.setattr(r,'upload_internal_audit_evidence',upload)
    capture_id=uuid.uuid4();file=SimpleNamespace(content_type='image/jpeg',filename='original.jpg')
    asyncio.run(r.phone_capture_upload(token=token(),file=file,capture_id=capture_id,db=MagicMock()))
    kwargs=upload.call_args.kwargs
    assert kwargs['base_version']==(version or 0) and kwargs['file'] is file
    assert kwargs['client_mutation_id']==f'phone-capture-session-{capture_id}'
    assert kwargs['source_device_id']=='paired-phone'

def test_original_heic_signature_supported():
    _validate_signature('original.heic',b'\x00\x00\x00\x18ftypheic\x00\x00\x00\x00')
    with pytest.raises(HTTPException):_validate_signature('fake.heic',b'not an image')


def test_generated_link_expires_in_ten_minutes_and_is_not_a_login(monkeypatch):
    setup(monkeypatch)
    audit_id,item_id=uuid.uuid4(),uuid.uuid4()
    ctx=r.TenantContext(amo_code='AMO-A',amo_id='tenant-a',user_id='user-a',is_superuser=False)
    grant=r.create_phone_capture(audit_id,item_id,ctx,MagicMock())
    data=jwt.decode(grant['token'],SECRET_KEY,algorithms=[JWT_ALGORITHM],audience='qms-phone-evidence')
    assert 590 <= data['exp']-datetime.now(timezone.utc).timestamp() <= 600
    assert data['purpose']=='checklist-photo' and 'sub' not in data
    assert data['audit']==str(audit_id) and data['item']==str(item_id)
