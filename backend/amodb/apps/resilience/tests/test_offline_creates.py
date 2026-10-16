from importlib import import_module

import pytest
from fastapi import FastAPI, Depends, HTTPException
from fastapi.testclient import TestClient

from amodb.apps.accounts import models as accounts
from amodb.apps.tasks import models, schemas
from amodb.apps.resilience.models import ReplayCommand
from amodb.apps.resilience.offline_commands import offline_create

router = import_module("amodb.apps.tasks.router")


@pytest.fixture
def actor(db_session):
    ReplayCommand.__table__.create(db_session.get_bind(), checkfirst=True)
    amo = accounts.AMO(amo_code="OFFLINE", login_slug="offline", name="Offline test")
    db_session.add(amo)
    db_session.flush()
    user = accounts.User(amo_id=amo.id, email="offline@test.invalid", staff_code="OFFLINE-1", first_name="Offline",
        last_name="User", full_name="Offline User", hashed_password="test", role=accounts.AccountRole.USER, is_active=True)
    db_session.add(user)
    db_session.commit()
    user.effective_amo_id = amo.id
    return user


def create(db, actor, key, title="Captured offline"):
    return router.create_personal_task(schemas.PersonalTaskCreate(title=title), db, actor,
        _offline_command="1", _offline_key=key)


def test_personal_task_replay_returns_original_record_and_receipt(db_session, actor):
    first = create(db_session, actor, "device-command-123456")
    replay = create(db_session, actor, "device-command-123456")
    assert first == replay
    assert db_session.query(models.Task).count() == 1
    receipt = db_session.query(ReplayCommand).one()
    assert receipt.status == "SUCCEEDED"
    assert receipt.response_json["id"] == first["id"]
    assert receipt.route_key == "portal.create:/tasks/personal"


def test_same_key_cannot_create_changed_content(db_session, actor):
    create(db_session, actor, "device-command-123456")
    with pytest.raises(HTTPException) as failure:
        create(db_session, actor, "device-command-123456", "Different content")
    assert failure.value.status_code == 409
    assert failure.value.detail["error_code"] == "IDEMPOTENCY_CONFLICT"
    assert db_session.query(models.Task).count() == 1


def test_training_course_and_reliability_replay_real_domain_rows(db_session, actor, monkeypatch):
    training = import_module("amodb.apps.training.router")
    reliability = import_module("amodb.apps.reliability.router")
    tables = {model.__table__ for model in vars(training.training_models).values()
              if isinstance(model, type) and hasattr(model, "__table__")}
    training.training_models.Base.metadata.create_all(db_session.get_bind(), tables=list(tables))
    reliability.services.models.ReliabilityRecommendation.__table__.create(db_session.get_bind(), checkfirst=True)
    reliability.services.models.ReliabilityDefectTrend.__table__.create(db_session.get_bind(), checkfirst=True)
    reliability.services.models.ReliabilityRecurringFinding.__table__.create(db_session.get_bind(), checkfirst=True)
    # Schema installation is deployment infrastructure, not part of creating a course.
    monkeypatch.setattr(training, "_ensure_training_catalog_schema_compat", lambda db: None)
    course = training.training_schemas.TrainingCourseCreate(course_id="OFFLINE", course_name="Offline course")
    first = training.create_course(course, db_session, actor, _offline_command="1", _offline_key="offline-course-key")
    assert training.create_course(course, db_session, actor, _offline_command="1", _offline_key="offline-course-key") == first
    assert db_session.query(training.training_models.TrainingCourse).count() == 1
    assert db_session.query(training.training_models.TrainingAuditLog).count() == 1
    recommendation = reliability.schemas.ReliabilityRecommendationCreate(title="Offline recommendation")
    saved = reliability.create_recommendation(recommendation, actor, db_session,
        _offline_command="1", _offline_key="offline-recommendation-key")
    assert reliability.create_recommendation(recommendation, actor, db_session,
        _offline_command="1", _offline_key="offline-recommendation-key") == saved
    assert db_session.query(reliability.services.models.ReliabilityRecommendation).count() == 1
    assert db_session.query(ReplayCommand).count() == 2


def test_domain_flush_cannot_commit_without_its_receipt(db_session, actor):
    @offline_create("/test/create", schemas.TaskRead)
    def fail_after_commit(payload, db, current_user):
        db.add(models.Task(amo_id=current_user.amo_id, title="Must roll back"))
        db.commit()
        raise RuntimeError("Failure after handler commit")
    with pytest.raises(RuntimeError):
        fail_after_commit({}, db_session, actor, _offline_command="1", _offline_key="device-failure-key")
    assert db_session.query(models.Task).count() == 0
    assert db_session.query(ReplayCommand).count() == 0


def test_public_response_validation_rolls_back_domain_rows(db_session, actor):
    @offline_create("/test/create", schemas.TaskRead)
    def invalid_response(payload, db, current_user):
        db.add(models.Task(amo_id=current_user.amo_id, title="Must roll back"))
        db.commit()
        return {"missing": "required response fields"}
    with pytest.raises(ValueError):
        invalid_response({}, db_session, actor, _offline_command="1", _offline_key="device-invalid-key")
    assert db_session.query(models.Task).count() == 0
    assert db_session.query(ReplayCommand).count() == 0


def test_fastapi_keeps_offline_metadata_in_headers_and_enforces_permissions():
    app = FastAPI()
    def denied():
        raise HTTPException(403, "Access revoked")
    app.add_api_route("/tasks/personal", router.create_personal_task, methods=["POST"],
        response_model=schemas.TaskRead, dependencies=[Depends(denied)])
    operation = app.openapi()["paths"]["/tasks/personal"]["post"]
    headers = {parameter["name"] for parameter in operation["parameters"] if parameter["in"] == "header"}
    assert {"Idempotency-Key", "X-AMO-Offline-Command"} <= headers
    response = TestClient(app).post("/tasks/personal", json={"title": "Offline task"},
        headers={"Idempotency-Key": "same-command", "X-AMO-Offline-Command": "1"})
    assert response.status_code == 403
