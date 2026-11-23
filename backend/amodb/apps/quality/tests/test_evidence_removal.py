from types import SimpleNamespace
from unittest.mock import MagicMock
import uuid
import pytest
from fastapi import HTTPException
from amodb.apps.quality import audit_evidence_router as r

def setup(monkeypatch,**overrides):
 artifact=SimpleNamespace(id='photo',uploaded_by_user_id='owner',checklist_item_id=uuid.uuid4(),finding_id=None,evidence_request_id=None,context_json={'location_ref':'Hangar'},**overrides)
 db=MagicMock();db.query.return_value.filter.return_value.with_for_update.return_value.first.return_value=artifact
 ctx=SimpleNamespace(amo_id='tenant',user_id='owner');audit=uuid.uuid4()
 for name in ['assert_quality_permission_any','set_postgres_tenant_context','_internal_fieldwork_actor','_assert_base_version','_publish_persisted_evidence_event']:
  monkeypatch.setattr(r,name,MagicMock())
 item=SimpleNamespace(id=artifact.checklist_item_id)
 governance=SimpleNamespace(evidence_references=[{'artifact_id':'photo'},{'artifact_id':'keep'}],canonical_response_status='COMPLIANT',auditor_notes='Retain notes',evidence_ids=[],entity_version=3)
 monkeypatch.setattr(r,'_item',lambda *a,**kw:item);monkeypatch.setattr(r,'_locked_governance',lambda *a,**kw:governance)
 apply=MagicMock(return_value=SimpleNamespace(entity_version=4));monkeypatch.setattr(r,'_apply_execution_update',apply)
 event=SimpleNamespace(action='UPLOADED');monkeypatch.setattr(r,'_evidence_audit_event',lambda **kw:event)
 return artifact,db,ctx,audit,governance,apply,event

def test_remove_detaches_only_selected_attachment_and_retains_attribution(monkeypatch):
 artifact,db,ctx,audit,g,apply,event=setup(monkeypatch)
 result=r.remove_internal_audit_evidence(audit,'photo',3,ctx,db)
 assert result=={'removed':True,'committed_version':4}
 assert apply.call_args.kwargs['payload'].evidence_references==[{'artifact_id':'keep'}]
 assert apply.call_args.kwargs['payload'].auditor_notes=='Retain notes'
 assert artifact.context_json['location_ref']=='Hangar' and artifact.context_json['_withdrawn']['by_user_id']=='owner'
 assert event.action=='REMOVED';db.commit.assert_called_once();db.delete.assert_not_called()

def test_only_uploader_can_remove(monkeypatch):
 artifact,db,ctx,audit,g,apply,event=setup(monkeypatch);ctx.user_id='other'
 with pytest.raises(HTTPException) as exc:r.remove_internal_audit_evidence(audit,'photo',3,ctx,db)
 assert exc.value.status_code==403;apply.assert_not_called();db.commit.assert_not_called()

@pytest.mark.parametrize('usage',['finding','assessment','request'])
def test_relied_upon_evidence_cannot_be_silently_removed(monkeypatch,usage):
 artifact,db,ctx,audit,g,apply,event=setup(monkeypatch)
 if usage=='finding':artifact.finding_id=uuid.uuid4()
 if usage=='request':artifact.evidence_request_id=uuid.uuid4()
 if usage=='assessment':g.evidence_ids=['photo']
 with pytest.raises(HTTPException) as exc:r.remove_internal_audit_evidence(audit,'photo',3,ctx,db)
 assert exc.value.status_code==409;apply.assert_not_called();db.commit.assert_not_called()

def test_repeated_removal_is_idempotent(monkeypatch):
 artifact,db,ctx,audit,g,apply,event=setup(monkeypatch);artifact.context_json={'_withdrawn':{'by_user_id':'owner'}}
 assert r.remove_internal_audit_evidence(audit,'photo',3,ctx,db)=={'removed':True};apply.assert_not_called()
