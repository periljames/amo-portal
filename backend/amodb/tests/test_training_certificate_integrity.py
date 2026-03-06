from datetime import date

import pytest
from sqlalchemy import create_engine
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import sessionmaker

from amodb.database import Base
from amodb.apps.accounts import models as account_models
from amodb.apps.training import models as training_models
from amodb.apps.training.router import verify_certificate_public


def _db_session():
    engine = create_engine("sqlite+pysqlite:///:memory:")
    Base.metadata.create_all(
        bind=engine,
        tables=[
            account_models.AMO.__table__,
            account_models.Department.__table__,
            account_models.User.__table__,
            training_models.TrainingCourse.__table__,
            training_models.TrainingRecord.__table__,
            training_models.TrainingCertificateIssue.__table__,
            training_models.TrainingCertificateStatusHistory.__table__,
        ],
    )
    Session = sessionmaker(bind=engine, autoflush=False, autocommit=False, expire_on_commit=False)
    return Session()


def _seed(db):
    amo = account_models.AMO(id="amo-1", amo_code="AMO1", name="AMO 1", login_slug="amo1")
    dept = account_models.Department(id="dept-1", amo_id=amo.id, code="QUALITY", name="Quality")
    user = account_models.User(
        id="user-1",
        amo_id=amo.id,
        department_id=dept.id,
        staff_code="U1",
        email="u1@example.com",
        hashed_password="x",
        first_name="U",
        last_name="One",
        full_name="User One",
        role=account_models.AccountRole.QUALITY_MANAGER,
        is_active=True,
    )
    course = training_models.TrainingCourse(id="course-1", amo_id=amo.id, course_id="HF-REF", course_name="HF Ref", frequency_months=12)
    record = training_models.TrainingRecord(id="rec-1", amo_id=amo.id, user_id=user.id, course_id=course.id, completion_date=date.today())
    db.add_all([amo, dept, user, course, record])
    db.commit()


def test_certificate_number_unique_per_tenant():
    db = _db_session()
    _seed(db)

    first = training_models.TrainingCertificateIssue(
        id="issue-1",
        amo_id="amo-1",
        record_id="rec-1",
        certificate_number="TC-AMO1-20260305-0001",
        status="VALID",
    )
    db.add(first)
    db.commit()

    dup = training_models.TrainingCertificateIssue(
        id="issue-2",
        amo_id="amo-1",
        record_id="rec-1",
        certificate_number="TC-AMO1-20260305-0001",
        status="VALID",
    )
    db.add(dup)
    with pytest.raises(IntegrityError):
        db.commit()


def test_public_verify_returns_json_response():
    db = _db_session()
    response = verify_certificate_public("bad", db)
    assert response.status_code == 400
    assert response.media_type == "application/json"
    assert response.body
