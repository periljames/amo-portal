import uuid
from datetime import datetime, timedelta, timezone
import pytest
from fastapi import HTTPException
from pydantic import ValidationError
from amodb.apps.accounts import models as accounts
from amodb.apps.quality import models
from amodb.apps.quality.car_feedback import record_shared_feedback
from amodb.apps.quality.car_feedback_router import FeedbackCreate, append_message, timeline


def seed(db):
    tenant=accounts.AMO(amo_code="FEEDBACK",name="Feedback test",login_slug="feedback")
    db.add(tenant);db.flush()
    user=accounts.User(amo_id=tenant.id,staff_code="Q1",email="reviewer@example.invalid",first_name="Quality",last_name="Reviewer",full_name="Quality Reviewer",hashed_password="test",role=accounts.AccountRole.QUALITY_MANAGER,is_active=True)
    db.add(user);db.flush()
    car=models.CorrectiveActionRequest(amo_id=tenant.id,car_number="QA-001",title="Feedback",summary="Synthetic case",program=models.CARProgram.QUALITY,status=models.CARStatus.OPEN,priority=models.CARPriority.HIGH,requested_by_user_id=user.id,invite_token=uuid.uuid4().hex)
    db.add(car);db.commit()
    return car,user


def test_public_messages_are_shared_and_retries_are_duplicate_safe(db_session):
    car,_=seed(db_session)
    payload=FeedbackCreate(message="  Please clarify the evidence required.  ",client_message_id=uuid.uuid4(),actor_name="Respondent",visibility="INTERNAL")
    first=append_message(db_session,car,payload,public=True)
    second=append_message(db_session,car,payload,public=True)
    assert first["id"]==second["id"]
    assert first["visibility"]=="SHARED" and first["actor_kind"]=="AUDITEE"
    assert "actor_user_id" not in first
    assert db_session.query(models.CARActionLog).count()==1
    with pytest.raises(HTTPException) as error:
        append_message(db_session,car,payload.model_copy(update={"message":"different content"}),public=True)
    assert error.value.status_code==409


def test_shared_history_excludes_internal_and_other_car_and_pages_without_loss(db_session):
    car,user=seed(db_session)
    other=models.CorrectiveActionRequest(amo_id=car.amo_id,car_number="QA-OTHER",title="Other",summary="Other",program=models.CARProgram.QUALITY,requested_by_user_id=user.id,invite_token=uuid.uuid4().hex)
    db_session.add(other);db_session.flush()
    now=datetime.now(timezone.utc)
    for index in range(105):
        row=record_shared_feedback(db_session,car,f"Shared decision {index}",user=user)
        row.created_at=now+timedelta(seconds=index)
    db_session.add(models.CARActionLog(car_id=car.id,message="PRIVATE MANAGEMENT NOTE",visibility="INTERNAL",actor_user_id=user.id,created_at=now+timedelta(seconds=106)))
    record_shared_feedback(db_session,other,"Other CAR",user=user)
    db_session.commit()
    items=[];cursor=None
    while True:
        page=timeline(db_session,car,public=True,before=cursor)
        items+=page["items"];cursor=page["next_cursor"]
        if not cursor:break
        cursor=uuid.UUID(cursor)
    assert len(items)==105 and len({item["id"] for item in items})==105
    assert all(item["message"].startswith("Shared decision") for item in items)
    assert all("actor_user_id" not in item for item in items)
    assert any(item["message"]=="PRIVATE MANAGEMENT NOTE" for item in timeline(db_session,car,public=False)["items"])


def test_decision_reasons_are_retained_and_closed_car_is_read_only(db_session):
    car,user=seed(db_session)
    record_shared_feedback(db_session,car,"Root cause: REJECTED. Missing evidence.",user=user)
    record_shared_feedback(db_session,car,"Root cause: ACCEPTED. Evidence independently reviewed.",user=user)
    db_session.commit()
    assert len(timeline(db_session,car,public=True)["items"])==2
    payload=FeedbackCreate(message="Acknowledged",client_message_id=uuid.uuid4())
    sent=append_message(db_session,car,payload,public=True)
    car.status=models.CARStatus.CLOSED;db_session.commit()
    assert append_message(db_session,car,payload,public=True)["id"]==sent["id"]
    with pytest.raises(HTTPException) as error:
        append_message(db_session,car,FeedbackCreate(message="New message",client_message_id=uuid.uuid4()),public=True)
    assert error.value.status_code==409


def test_feedback_rejects_blank_oversized_and_missing_idempotency_keys():
    for value in (" ","x"*4001):
        with pytest.raises(ValidationError):FeedbackCreate(message=value,client_message_id=uuid.uuid4())
    with pytest.raises(ValidationError):FeedbackCreate(message="message")


def test_history_query_does_not_join_the_car_relationship_graph(db_session):
    from sqlalchemy import event
    car,user=seed(db_session)
    record_shared_feedback(db_session,car,"A retained decision",user=user)
    db_session.commit()
    assert car.id
    statements=[]
    def capture(connection,cursor,statement,parameters,context,many):
        if "FROM quality_car_actions" in statement:statements.append(statement)
    engine=db_session.get_bind();event.listen(engine,"before_cursor_execute",capture)
    try:assert timeline(db_session,car,public=True)["items"]
    finally:event.remove(engine,"before_cursor_execute",capture)
    assert statements and all("JOIN" not in statement.upper() for statement in statements)


def test_returned_individual_action_can_be_revised_without_unlocking_approved_rca():
    from types import SimpleNamespace
    from datetime import date
    from unittest.mock import MagicMock, patch
    from amodb.apps.quality import car_rca_router as rca
    car=SimpleNamespace(id=uuid.uuid4(),amo_id="tenant",status="IN_PROGRESS",root_cause_status="ACCEPTED",capa_status="ACCEPTED")
    from amodb.apps.quality.car_rca_models import QualityCarRcaAction
    row=QualityCarRcaAction(id=uuid.uuid4(),amo_id=car.amo_id,car_id=car.id,state="REJECTED",sequence_no=1)
    db=MagicMock();db.query.return_value.filter.return_value.with_for_update.return_value.first.return_value=row
    payload=rca.ActionCreate(description="Clarified implementation and evidence owner",external_owner_name="Respondent",target_date=date.today())
    with patch.object(rca,"_car_for_guest",return_value=car), patch.object(rca,"_assert_guest_editable") as narrative_gate, \
        patch.object(rca,"_assert_action_scope"),patch.object(rca,"_record_action_event"),patch.object(rca,"_action_dict",return_value={"state":"PROPOSED"}), \
        patch("amodb.apps.quality.car_feedback.record_shared_feedback"),patch("amodb.apps.quality.car_feedback.feedback_changed"):
        assert rca.revise_public_action("invite",row.id,payload,db)=={"state":"PROPOSED"}
        assert row.state=="PROPOSED"
        narrative_gate.assert_not_called()
        row.state="REJECTED";car.status="CLOSED"
        with pytest.raises(HTTPException) as error:rca.revise_public_action("invite",row.id,payload,db)
        assert error.value.status_code==409


def test_proposed_action_creation_retry_uses_retained_mutation_receipt(db_session):
    from amodb.apps.quality import car_rca_router as rca
    from amodb.apps.quality.car_rca_models import QualityCarRcaAction
    car,_=seed(db_session)
    payload=rca.ActionCreate(description="Independently verify evidence ownership",external_owner_name="Respondent",mutation_key=str(uuid.uuid4()))
    first=rca._add_action(db_session,car,payload,public=True,actor_ref="Invited responder")
    second=rca._add_action(db_session,car,payload,public=True,actor_ref="Invited responder")
    assert first["id"]==second["id"]
    assert db_session.query(QualityCarRcaAction).count()==1
    assert any("Action 01: proposed" in item["message"] for item in timeline(db_session,car,public=True)["items"])
    with pytest.raises(HTTPException) as error:
        rca._add_action(db_session,car,payload.model_copy(update={"description":"Different proposed action"}),public=True,actor_ref="Invited responder")
    assert error.value.status_code==409


def test_quality_scope_lookup_does_not_load_tenant_roster_or_assets(db_session):
    from sqlalchemy import event
    from amodb.apps.quality.tenant_security import _resolve_amo
    from amodb.apps.quality.car_control_loop_router import _load_car
    car,_=seed(db_session)
    car_id=car.id;tenant_id=car.amo_id
    db_session.expunge_all()
    statements=[]
    def capture(_connection,_cursor,statement,*_args): statements.append(statement)
    event.listen(db_session.bind,"before_cursor_execute",capture)
    try:
        tenant=_resolve_amo(db_session,"feedback")
        loaded=_load_car(db_session,amo_id=tenant_id,car_id=car_id)
        assert tenant.id==tenant_id and loaded.id==car_id
    finally:
        event.remove(db_session.bind,"before_cursor_execute",capture)
    assert len(statements)==2
    assert all(" JOIN " not in query.upper() for query in statements)
