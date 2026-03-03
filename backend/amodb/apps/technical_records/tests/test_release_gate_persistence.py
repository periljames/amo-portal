from __future__ import annotations

from datetime import UTC, datetime

from amodb.apps.accounts import models as account_models
from amodb.apps.technical_records import models as tr_models
from amodb.apps.work import models as work_models


def test_release_gate_and_evidence_persistence(db_session):
    # ensure required tables exist for sqlite test db
    tr_models.ProductionExecutionEvidence.__table__.create(bind=db_session.get_bind(), checkfirst=True)
    tr_models.ProductionReleaseGate.__table__.create(bind=db_session.get_bind(), checkfirst=True)

    amo = account_models.AMO(
        id="amo-rel",
        amo_code="REL",
        name="Release AMO",
        login_slug="relamo",
        is_active=True,
    )
    dept = account_models.Department(id="dept-rel", amo_id=amo.id, code="production", name="Production")
    user = account_models.User(
        id="user-rel",
        amo_id=amo.id,
        department_id=dept.id,
        staff_code="REL-1",
        email="rel@example.com",
        hashed_password="x",
        first_name="Rel",
        last_name="User",
        full_name="Rel User",
        role=account_models.AccountRole.PRODUCTION_ENGINEER,
        is_active=True,
        must_change_password=False,
    )
    db_session.add_all([amo, dept, user])
    db_session.flush()

    from amodb.apps.fleet.models import Aircraft

    ac = Aircraft(
        amo_id=amo.id,
        serial_number="REL-AC-1",
        registration="REL001",
        template="B737",
        make="Boeing",
        model="737",
    )
    db_session.add(ac)
    db_session.flush()

    wo = work_models.WorkOrder(
        amo_id=amo.id,
        wo_number="WO-REL-001",
        aircraft_serial_number=ac.serial_number,
        wo_type=work_models.WorkOrderTypeEnum.PERIODIC,
        status=work_models.WorkOrderStatusEnum.IN_PROGRESS,
        open_date=datetime.now(UTC).date(),
        created_by_user_id=user.id,
    )
    db_session.add(wo)
    db_session.flush()

    evidence = tr_models.ProductionExecutionEvidence(
        amo_id=amo.id,
        work_order_id=wo.id,
        task_card_id=None,
        file_name="proof.txt",
        storage_path="/tmp/proof.txt",
        content_type="text/plain",
        notes="demo",
        created_by_user_id=user.id,
    )
    db_session.add(evidence)
    db_session.flush()

    gate = tr_models.ProductionReleaseGate(
        amo_id=amo.id,
        work_order_id=wo.id,
        status="Ready",
        blockers_json=[],
        evidence_count=1,
        signed_off_by_user_id=user.id,
        handed_to_records=True,
        handed_to_records_at=datetime.now(UTC),
    )
    db_session.add(gate)
    db_session.commit()

    loaded_gate = db_session.query(tr_models.ProductionReleaseGate).filter_by(amo_id=amo.id, work_order_id=wo.id).first()
    assert loaded_gate is not None
    assert loaded_gate.status == "Ready"
    assert loaded_gate.evidence_count == 1
    assert loaded_gate.handed_to_records is True

    loaded_evidence = db_session.query(tr_models.ProductionExecutionEvidence).filter_by(amo_id=amo.id, work_order_id=wo.id).all()
    assert len(loaded_evidence) == 1
    assert loaded_evidence[0].file_name == "proof.txt"
