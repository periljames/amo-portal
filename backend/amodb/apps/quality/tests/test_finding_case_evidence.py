import uuid
import importlib
from types import SimpleNamespace

import pytest
from fastapi import HTTPException
from amodb.database import Base
from amodb.apps.quality import models
from amodb.apps.quality import audit_evidence_router as evidence
from amodb.apps.quality.audit_evidence_models import QualityAuditEvidenceArtifact
from amodb.apps.quality import tenant_security


def test_finding_evidence_includes_source_question_and_preserves_tenant_audit_scope(db_session, monkeypatch):
    Base.metadata.create_all(db_session.get_bind(), tables=[models.QualityAuditChecklistItem.__table__,QualityAuditEvidenceArtifact.__table__])
    audit,other_audit,finding=uuid.uuid4(),uuid.uuid4(),uuid.uuid4()
    item=models.QualityAuditChecklistItem(amo_id="own",audit_id=audit,prompt="Source question",finding_id=finding)
    db_session.add(item);db_session.flush()
    def artifact(name,**kw):
        return QualityAuditEvidenceArtifact(amo_id=kw.pop("amo_id","own"),audit_id=kw.pop("audit_id",audit),
            source_type="INTERNAL_USER",file_ref="test-only",filename=name,size_bytes=1,sha256="a"*64,**kw)
    db_session.add_all([artifact("source.pdf",checklist_item_id=item.id),artifact("finding.pdf",finding_id=finding),
        artifact("unrelated.pdf"),artifact("foreign.pdf",amo_id="foreign",finding_id=finding),
        artifact("other-audit.pdf",audit_id=other_audit,finding_id=finding)])
    db_session.commit()
    monkeypatch.setattr(evidence,"set_postgres_tenant_context",lambda *args,**kwargs:None)
    monkeypatch.setattr(evidence,"_internal_fieldwork_viewer",lambda *args,**kwargs:None)
    result=evidence.list_audit_evidence(audit,finding_id=finding,ctx=SimpleNamespace(amo_id="own",user_id="auditor"),db=db_session)
    assert {row["filename"] for row in result["items"]} == {"source.pdf","finding.pdf"}


@pytest.mark.parametrize("allowed",[True,False])
def test_evidence_read_uses_view_permission_without_granting_write(allowed, monkeypatch):
    router=importlib.import_module("amodb.apps.quality.router")
    seen=[]
    def permission(db,ctx,key):
        seen.append(key)
        if not allowed: raise HTTPException(status_code=403,detail="Denied")
    monkeypatch.setattr(tenant_security,"assert_quality_permission",permission)
    user=SimpleNamespace(id="viewer",amo_id="own",effective_amo_id="own",is_superuser=False)
    if allowed:
        router._require_car_read_access(None,user,SimpleNamespace(amo_id="own"))
    else:
        with pytest.raises(HTTPException) as caught: router._require_car_read_access(None,user,SimpleNamespace(amo_id="own"))
        assert caught.value.status_code == 403
    assert seen == ["qms.car.view"]
    with pytest.raises(HTTPException) as caught: router._require_car_read_access(None,user,SimpleNamespace(amo_id="foreign"))
    assert caught.value.status_code == 404


@pytest.mark.parametrize("status",[models.CARStatus.CLOSED,models.CARStatus.CANCELLED,models.CARStatus.ESCALATED])
def test_locked_car_cannot_receive_new_evidence(status,monkeypatch):
    router=importlib.import_module("amodb.apps.quality.router")
    car=SimpleNamespace(status=status,amo_id="own",finding_id=None)
    monkeypatch.setattr(router,"_get_car_for_amo",lambda *args,**kwargs:car)
    monkeypatch.setattr(router,"_require_car_write_access",lambda *args,**kwargs:None)
    monkeypatch.setattr(router,"_store_car_attachment",lambda *args,**kwargs:pytest.fail("Locked evidence must not be stored"))
    user=SimpleNamespace(id="auditor",amo_id="own",effective_amo_id="own")
    with pytest.raises(HTTPException) as caught:
        router.upload_car_attachment(uuid.uuid4(),file=None,description=None,db=None,current_user=user)
    assert caught.value.status_code == 423


@pytest.mark.parametrize("has_profile",[True,False])
def test_accepting_proposed_plan_never_closes_car_without_effectiveness(has_profile,monkeypatch):
    from amodb.apps.quality import car_response_workflow
    router=importlib.import_module("amodb.apps.quality.router")
    car=SimpleNamespace(id=uuid.uuid4(),status=models.CARStatus.PENDING_VERIFICATION,
        root_cause_status="ACCEPTED",capa_status="ACCEPTED",evidence_required=True,closed_at=None)
    response=SimpleNamespace(status=None)
    monkeypatch.setattr(router,"_car_has_evidence",lambda *args:True)
    monkeypatch.setattr(router,"_latest_reviewable_car_response",lambda *args:response)
    monkeypatch.setattr(car_response_workflow,"sync_response_milestones",lambda *args,**kwargs:has_profile)
    monkeypatch.setattr(router,"_mark_audit_in_progress_or_cap_open",lambda *args:None)
    monkeypatch.setattr(router,"_close_accepted_car_workflow",lambda *args,**kwargs:pytest.fail("Plan acceptance must not close the CAR or finding"))
    state,outcome=router._sync_car_review_state(None,car,actor_user_id="auditor")
    assert state == models.CARStatus.IN_PROGRESS
    assert outcome == "accepted_pending_control_loop"
    assert car.closed_at is None
    assert response.status == models.CARResponseStatus.CAP_ACCEPTED
