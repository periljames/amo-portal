from __future__ import annotations

from datetime import date

from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from amodb.database import Base
from amodb.apps.accounts import models as account_models
from amodb.apps.training import models as training_models
from amodb.apps.training import operating_models
from amodb.apps.training import operating_service
from amodb.apps.training import workbook_models


def _session():
    engine = create_engine("sqlite+pysqlite:///:memory:")
    core = [
        account_models.AMO.__table__,
        account_models.Department.__table__,
        account_models.User.__table__,
        account_models.PersonnelProfile.__table__,
        account_models.AuthorisationType.__table__,
        account_models.UserAuthorisation.__table__,
        account_models.AccountSecurityEvent.__table__,
    ]
    tables = core + [table for table in Base.metadata.tables.values() if table.name.startswith("training_")]
    unique_tables = list(dict.fromkeys(tables))
    Base.metadata.create_all(engine, tables=unique_tables)
    return sessionmaker(bind=engine, autoflush=False, expire_on_commit=False)()


def test_uploaded_personnel_records_become_traceable_person_month_obligations(monkeypatch):
    db = _session()
    plan_year = date.today().year + 1
    amo = account_models.AMO(id="amo-plan", amo_code="PLAN", name="Plan AMO", login_slug="plan")
    department = account_models.Department(id="dept-plan", amo_id=amo.id, code="MAINT", name="Maintenance")
    person = account_models.User(
        id="user-plan",
        amo_id=amo.id,
        department_id=department.id,
        staff_code="P001",
        email="person@example.com",
        hashed_password="x",
        first_name="Pat",
        last_name="Engineer",
        full_name="Pat Engineer",
        role=account_models.AccountRole.TECHNICIAN,
        is_active=True,
        is_system_account=False,
    )
    march = training_models.TrainingCourse(
        id="course-march", amo_id=amo.id, course_id="REC-MAR", course_name="March recurrent",
        frequency_months=12, status="Recurrent", is_active=True,
    )
    november = training_models.TrainingCourse(
        id="course-nov", amo_id=amo.id, course_id="REC-NOV", course_name="November recurrent",
        frequency_months=12, status="Recurrent", is_active=True,
    )
    overdue = training_models.TrainingCourse(
        id="course-overdue", amo_id=amo.id, course_id="REC-OLD", course_name="Overdue recurrent",
        frequency_months=12, status="Recurrent", is_active=True,
    )
    never = training_models.TrainingCourse(
        id="course-never", amo_id=amo.id, course_id="ROLE-REQ", course_name="Role requirement",
        frequency_months=24, status="Recurrent", is_mandatory=False, is_active=True,
    )
    one_off = training_models.TrainingCourse(
        id="course-one", amo_id=amo.id, course_id="ONE-OFF", course_name="Completed one-off",
        frequency_months=None, status="One_Off", is_active=True,
    )
    after_year = training_models.TrainingCourse(
        id="course-future", amo_id=amo.id, course_id="REC-FUT", course_name="Later recurrent",
        frequency_months=12, status="Recurrent", is_active=True,
    )
    group = workbook_models.TrainingRoleGroup(id="group-all", amo_id=amo.id, code="ALL", is_active=True)
    role_rule = workbook_models.TrainingCourseRoleRule(
        id="rule-never", amo_id=amo.id, course_id=never.id, role_group_id=group.id,
        is_required=True, requirement_type="GENERAL", is_active=True,
    )
    verified = training_models.TrainingRecordVerificationStatus.VERIFIED
    records = [
        training_models.TrainingRecord(
            id="record-march", amo_id=amo.id, user_id=person.id, course_id=march.id,
            completion_date=date(plan_year - 1, 3, 18), valid_until=date(plan_year, 3, 18),
            legacy_record_id="TRN-003", certificate_reference="CERT-MAR", record_status="ACTIVE",
            verification_status=verified,
        ),
        training_models.TrainingRecord(
            id="record-nov", amo_id=amo.id, user_id=person.id, course_id=november.id,
            completion_date=date(plan_year - 1, 11, 4), valid_until=date(plan_year, 11, 4),
            legacy_record_id="TRN-011", record_status="ACTIVE", verification_status=verified,
        ),
        training_models.TrainingRecord(
            id="record-old", amo_id=amo.id, user_id=person.id, course_id=overdue.id,
            completion_date=date(plan_year - 2, 6, 1), valid_until=date(plan_year - 1, 6, 1),
            legacy_record_id="TRN-OLD", record_status="ACTIVE", verification_status=verified,
        ),
        training_models.TrainingRecord(
            id="record-one", amo_id=amo.id, user_id=person.id, course_id=one_off.id,
            completion_date=date(plan_year - 1, 1, 9), valid_until=None,
            legacy_record_id="TRN-ONE", record_status="ACTIVE", verification_status=verified,
        ),
        training_models.TrainingRecord(
            id="record-future", amo_id=amo.id, user_id=person.id, course_id=after_year.id,
            completion_date=date(plan_year, 7, 1), valid_until=date(plan_year + 1, 7, 1),
            legacy_record_id="TRN-FUT", record_status="ACTIVE", verification_status=verified,
        ),
    ]
    db.add_all([amo, department, person, march, november, overdue, never, one_off, after_year, group, role_rule, *records])
    db.commit()

    items = operating_service._demand_items(db, amo_id=amo.id, year=plan_year)
    obligations = {
        (item.course_id, item.planned_month): participant
        for item in items
        for participant in item.participant_obligations
    }

    assert (march.id, 3) in obligations
    assert (november.id, 11) in obligations
    assert (overdue.id, 1) in obligations
    assert (never.id, 1) in obligations
    assert all(course_id not in {one_off.id, after_year.id} for course_id, _month in obligations)

    march_obligation = obligations[(march.id, 3)]
    assert march_obligation.person_name == "Pat Engineer"
    assert march_obligation.staff_code == "P001"
    assert march_obligation.expiry_date == date(plan_year, 3, 18)
    assert march_obligation.source_record_id == "record-march"
    assert march_obligation.source_reference == "Workbook RecordID TRN-003 · Certificate CERT-MAR"

    never_obligation = obligations[(never.id, 1)]
    assert never_obligation.obligation_status == "NOT_DONE"
    assert never_obligation.source_reference == "No completion record · requirements matrix"

    monkeypatch.setattr(operating_service, "_audit", lambda *_args, **_kwargs: None)
    first_sync = operating_service.sync_current_plan_from_records(db, actor=person, plan_year=plan_year)
    db.flush()
    persisted_plans = db.query(operating_models.TrainingPlan).all()
    assert first_sync["plan_id"] in {str(plan.id) for plan in persisted_plans}
    first_plan = next(plan for plan in persisted_plans if str(plan.id) == first_sync["plan_id"])
    assert first_sync["action"] == "CREATED"
    assert first_plan.status == "DRAFT"
    assert sum(item.participant_count for item in first_plan.items) == len(obligations)

    # Approved evidence is never rewritten after a later upload; a new draft
    # revision is created and repopulated instead.
    first_plan.status = "APPROVED"
    second_sync = operating_service.sync_current_plan_from_records(db, actor=person, plan_year=plan_year)
    db.flush()
    second_plan = db.query(operating_models.TrainingPlan).filter_by(id=second_sync["plan_id"]).one()
    assert second_sync["action"] == "REVISED_AND_RECALCULATED"
    assert second_plan.revision_no == 2
    assert second_plan.status == "DRAFT"
    assert second_plan.supersedes_plan_id == first_plan.id
    assert first_plan.status == "APPROVED"
    db.close()
