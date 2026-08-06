from __future__ import annotations

from contextlib import contextmanager
from datetime import date, datetime, timezone
from uuid import uuid4

import pytest
from fastapi.testclient import TestClient
from sqlalchemy.orm import Session

from amodb.apps.accounts import models as account_models
from amodb.apps.fleet import models as fleet_models
from amodb.apps.rostering import calendar_feed, models as roster_models
from amodb.apps.work import models as work_models
from amodb.database import engine, get_db
from amodb.main import app

pytestmark = pytest.mark.skipif(
    engine.dialect.name != "postgresql",
    reason="Calendar endpoint integration coverage requires PostgreSQL.",
)

UTC = timezone.utc


def _id() -> str:
    return str(uuid4())


@contextmanager
def _isolated_postgres_session():
    connection = engine.connect()
    transaction = connection.begin()
    db = Session(bind=connection, autoflush=False, expire_on_commit=False)
    try:
        yield db
    finally:
        db.close()
        if transaction.is_active:
            transaction.rollback()
        connection.close()


def test_personal_calendar_endpoint_renders_linked_maintenance_work() -> None:
    amo_id = _id()
    user_id = _id()
    period_id = _id()
    version_id = _id()
    roster_assignment_id = _id()
    link_id = _id()
    serial_number = f"CAL-{uuid4().hex[:10].upper()}"
    registration = f"5Y-{uuid4().hex[:4].upper()}"
    suffix = uuid4().hex[:10]

    with _isolated_postgres_session() as db:
        amo = account_models.AMO(
            id=amo_id,
            amo_code=f"CAL{suffix[:8].upper()}",
            name="Calendar Feed Integration AMO",
            login_slug=f"calendar-feed-{suffix}",
        )
        user = account_models.User(
            id=user_id,
            amo_id=amo_id,
            staff_code=f"CAL-{suffix[:8].upper()}",
            email=f"calendar-feed-{suffix}@example.test",
            first_name="Calendar",
            last_name="Engineer",
            full_name="Calendar Engineer",
            role=account_models.AccountRole.TECHNICIAN,
            hashed_password="not-used-by-public-calendar-test",
            is_active=True,
            is_system_account=False,
            must_change_password=False,
        )
        aircraft = fleet_models.Aircraft(
            serial_number=serial_number,
            amo_id=amo_id,
            registration=registration,
            aircraft_model_code="DHC8-315",
            status="OPEN",
            is_active=True,
        )
        period = roster_models.RosterPeriod(
            id=period_id,
            amo_id=amo_id,
            period_code=f"CAL-{suffix[:8].upper()}",
            name="Calendar endpoint integration period",
            starts_on=date(2026, 8, 1),
            ends_on=date(2026, 8, 31),
            timezone_name="Africa/Nairobi",
        )
        version = roster_models.RosterVersion(
            id=version_id,
            amo_id=amo_id,
            period_id=period_id,
            version_no=1,
            status=roster_models.RosterVersionStatus.PUBLISHED,
            published_at=datetime(2026, 8, 1, 6, 0, tzinfo=UTC),
        )
        assignment = roster_models.RosterAssignment(
            id=roster_assignment_id,
            amo_id=amo_id,
            version_id=version_id,
            user_id=user_id,
            status=roster_models.RosterAssignmentStatus.DUTY,
            source=roster_models.RosterAssignmentSource.MANUAL,
            starts_at=datetime(2026, 8, 12, 5, 0, tzinfo=UTC),
            ends_at=datetime(2026, 8, 12, 13, 0, tzinfo=UTC),
            planned_minutes=480,
            role_label="Aircraft Technician",
            location_label="NBO",
            task_note="Linked maintenance work must appear in the feed.",
        )

        db.add_all([amo, user, aircraft, period, version, assignment])
        db.flush()

        work_order = work_models.WorkOrder(
            amo_id=amo_id,
            wo_number=f"WO-CAL-{suffix[:6].upper()}",
            aircraft_serial_number=serial_number,
            description="Calendar feed linked work order",
            wo_type=work_models.WorkOrderTypeEnum.LINE,
            status=work_models.WorkOrderStatusEnum.RELEASED,
        )
        db.add(work_order)
        db.flush()

        task = work_models.TaskCard(
            amo_id=amo_id,
            work_order_id=work_order.id,
            aircraft_serial_number=serial_number,
            task_code=f"TASK-CAL-{suffix[:6].upper()}",
            title="Inspect calendar-linked maintenance task",
            category=work_models.TaskCategoryEnum.SCHEDULED,
            origin_type=work_models.TaskOriginTypeEnum.SCHEDULED,
            status=work_models.TaskStatusEnum.PLANNED,
        )
        db.add(task)
        db.flush()

        task_assignment = work_models.TaskAssignment(
            amo_id=amo_id,
            task_id=task.id,
            user_id=user_id,
            role_on_task=work_models.TaskRoleOnTaskEnum.LEAD,
            status=work_models.TaskAssignmentStatusEnum.ASSIGNED,
            allocated_hours=8,
        )
        db.add(task_assignment)
        db.flush()

        db.add(
            roster_models.RosterTaskAssignmentLink(
                id=link_id,
                amo_id=amo_id,
                roster_assignment_id=roster_assignment_id,
                task_assignment_id=task_assignment.id,
                allocated_start=assignment.starts_at,
                allocated_end=assignment.ends_at,
                allocated_hours=8,
            )
        )
        db.flush()

        def override_get_db():
            yield db

        app.dependency_overrides[get_db] = override_get_db
        try:
            token = calendar_feed.calendar_token(amo_id=amo_id, user_id=user_id)
            with TestClient(app) as client:
                response = client.get(
                    f"/rostering/calendar/feed/{token}.ics",
                    params={"from_date": "2026-08-01", "to_date": "2026-08-31"},
                )
        finally:
            app.dependency_overrides.pop(get_db, None)

        assert response.status_code == 200, response.text
        assert response.headers["content-type"].startswith("text/calendar")
        assert response.headers["content-disposition"] == (
            "inline; filename=amo-portal-personal-calendar.ics"
        )
        assert "BEGIN:VCALENDAR" in response.text
        assert f"UID:roster:{roster_assignment_id}@amo-portal" in response.text
        assert f"SUMMARY:DUTY · NBO · {registration}" in response.text
        assert work_order.wo_number in response.text
        assert task.task_code in response.text
        assert task.title in response.text
        assert "END:VCALENDAR" in response.text
