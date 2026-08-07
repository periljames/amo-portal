from __future__ import annotations

from amodb.apps.accounts import models as account_models
from amodb.apps.quality import models as quality_models
from amodb.apps.quality import register_pagination
from amodb.apps.quality import service as quality_service


def _create_amo_and_user(db_session, *, code: str):
    amo = account_models.AMO(
        amo_code=code,
        name=f"{code} AMO",
        login_slug=code.lower(),
    )
    db_session.add(amo)
    db_session.commit()

    user = account_models.User(
        amo_id=amo.id,
        email=f"quality-{code.lower()}@example.com",
        staff_code=f"QA-{code}",
        first_name="Quality",
        last_name=code,
        full_name=f"Quality {code}",
        hashed_password="hash",
        role=account_models.AccountRole.AMO_ADMIN,
        is_active=True,
        is_amo_admin=True,
    )
    db_session.add(user)
    db_session.commit()
    return amo, user


def _create_audit(db_session, *, amo_id: str, audit_ref: str):
    audit = quality_models.QMSAudit(
        amo_id=amo_id,
        domain=quality_models.QMSDomain.AMO,
        kind=quality_models.QMSAuditKind.INTERNAL,
        audit_ref=audit_ref,
        title=f"Audit {audit_ref}",
    )
    db_session.add(audit)
    db_session.commit()
    return audit


def _create_finding(db_session, *, amo_id: str, audit_id, ref: str, description: str):
    finding = quality_models.QMSAuditFinding(
        amo_id=amo_id,
        audit_id=audit_id,
        finding_ref=ref,
        finding_type=quality_models.QMSFindingType.NON_CONFORMITY,
        severity=quality_models.QMSFindingSeverity.MINOR,
        level=quality_models.FindingLevel.LEVEL_3,
        description=description,
    )
    db_session.add(finding)
    db_session.commit()
    return finding


def test_audit_register_pagination_is_bounded_and_tenant_scoped(db_session):
    amo_a, user_a = _create_amo_and_user(db_session, code="PAGE-A")
    amo_b, _user_b = _create_amo_and_user(db_session, code="PAGE-B")

    audit_a = _create_audit(db_session, amo_id=amo_a.id, audit_ref="QAR/MO/26/101")
    audit_b = _create_audit(db_session, amo_id=amo_b.id, audit_ref="QAR/MO/26/201")

    finding_a1 = _create_finding(
        db_session,
        amo_id=amo_a.id,
        audit_id=audit_a.id,
        ref="QAR/MO/26/101-F-001",
        description="Training record not current",
    )
    _create_finding(
        db_session,
        amo_id=amo_a.id,
        audit_id=audit_a.id,
        ref="QAR/MO/26/101-F-002",
        description="Tool calibration label missing",
    )
    _create_finding(
        db_session,
        amo_id=amo_a.id,
        audit_id=audit_a.id,
        ref="QAR/MO/26/101-F-003",
        description="Procedure copy superseded",
    )
    _create_finding(
        db_session,
        amo_id=amo_b.id,
        audit_id=audit_b.id,
        ref="QAR/MO/26/201-F-001",
        description="Other tenant finding",
    )

    car = quality_service.create_car(
        db_session,
        amo_id=amo_a.id,
        program=quality_models.CARProgram.QUALITY,
        title="Restore training currency",
        summary="Update the affected training record",
        priority=quality_models.CARPriority.HIGH,
        requested_by_user_id=user_a.id,
        assigned_to_user_id=None,
        due_date=None,
        target_closure_date=None,
        finding_id=finding_a1.id,
    )
    db_session.commit()

    first_page = register_pagination.get_audit_register_paged(
        domain=quality_models.QMSDomain.AMO,
        limit=1,
        offset=0,
        db=db_session,
        current_user=user_a,
    )

    assert first_page.total == 3
    assert len(first_page.rows) == 1
    assert first_page.has_more is True
    assert first_page.car_linked_findings == 1
    assert first_page.open_car_count == 1
    assert first_page.rows[0].audit.amo_id == amo_a.id

    second_page = register_pagination.get_audit_register_paged(
        domain=quality_models.QMSDomain.AMO,
        limit=1,
        offset=1,
        db=db_session,
        current_user=user_a,
    )
    assert second_page.total == 3
    assert len(second_page.rows) == 1
    assert second_page.rows[0].finding.id != first_page.rows[0].finding.id

    car_only = register_pagination.get_audit_register_paged(
        domain=quality_models.QMSDomain.AMO,
        only_with_cars=True,
        limit=25,
        offset=0,
        db=db_session,
        current_user=user_a,
    )
    assert car_only.total == 1
    assert car_only.rows[0].finding.id == finding_a1.id
    assert car_only.rows[0].linked_cars[0].id == car.id

    searched = register_pagination.get_audit_register_paged(
        domain=quality_models.QMSDomain.AMO,
        search=car.car_number,
        limit=25,
        offset=0,
        db=db_session,
        current_user=user_a,
    )
    assert searched.total == 1
    assert searched.rows[0].finding.id == finding_a1.id
