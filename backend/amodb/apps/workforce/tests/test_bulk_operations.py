from __future__ import annotations

import os
from datetime import date, timedelta
from uuid import uuid4

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import Session, sessionmaker

from amodb.apps.accounts import models as account_models
from amodb.apps.foundations import models as foundation_models
from amodb.apps.workforce import bulk_models, bulk_patterns, bulk_schemas, bulk_service, bulk_worker, hr_schemas, models


def _id() -> str:
    return str(uuid4())


def _postgres_session() -> tuple[object, object, object, Session]:
    engine = create_engine(os.environ["DATABASE_URL"], pool_pre_ping=True)
    connection = engine.connect()
    transaction = connection.begin()
    db = Session(bind=connection, autoflush=False, expire_on_commit=False)
    return engine, connection, transaction, db


def _close_postgres_session(engine, connection, transaction, db: Session) -> None:
    db.close()
    if transaction.is_active:
        transaction.rollback()
    connection.close()
    engine.dispose()


def _seed(db: Session) -> dict[str, object]:
    amo_id = _id()
    department_id = _id()
    base_id = _id()
    db.add(
        account_models.AMO(
            id=amo_id,
            amo_code=f"BULK-{amo_id[:8]}",
            name="Workforce Bulk Test",
            login_slug=f"bulk-{amo_id[:8]}",
            time_zone="UTC",
        )
    )
    db.flush()
    db.add(
        account_models.Department(
            id=department_id,
            amo_id=amo_id,
            code="ENG",
            name="Engineering",
            is_active=True,
        )
    )
    db.add(
        foundation_models.BaseStation(
            id=base_id,
            amo_id=amo_id,
            code="NBO",
            name="Nairobi Main Base",
            base_type=foundation_models.BaseStationType.MAIN_BASE,
            is_active=True,
        )
    )
    db.flush()
    admin = account_models.User(
        id=_id(),
        amo_id=amo_id,
        department_id=department_id,
        staff_code="ADMIN-1",
        email="admin@bulk.invalid",
        first_name="Admin",
        last_name="User",
        full_name="Admin User",
        position_title="HR Manager",
        role=account_models.AccountRole.AMO_ADMIN,
        hashed_password="not-a-real-password-hash",
        is_active=True,
        is_amo_admin=True,
        is_system_account=False,
    )
    people = [
        account_models.User(
            id=_id(),
            amo_id=amo_id,
            department_id=department_id,
            staff_code=f"EMP-{index}",
            email=f"employee-{index}@bulk.invalid",
            first_name="Employee",
            last_name=str(index),
            full_name=f"Employee {index}",
            position_title="Aircraft Technician",
            role=account_models.AccountRole.TECHNICIAN,
            hashed_password="not-a-real-password-hash",
            is_active=True,
            is_system_account=False,
        )
        for index in range(1, 4)
    ]
    db.add_all([admin, *people])
    db.flush()
    return {
        "amo_id": amo_id,
        "department_id": department_id,
        "base_id": base_id,
        "admin": admin,
        "people": people,
    }


@pytest.mark.skipif(
    not os.getenv("DATABASE_URL", "").startswith("postgresql"),
    reason="PostgreSQL integration database is not configured",
)
def test_contract_bulk_operation_is_idempotent_chunked_and_auditable(monkeypatch) -> None:
    engine, connection, transaction, db = _postgres_session()
    try:
        seeded = _seed(db)
        monkeypatch.setattr(
            bulk_worker,
            "WriteSessionLocal",
            sessionmaker(bind=connection, autoflush=False, expire_on_commit=False),
        )
        monkeypatch.setattr(bulk_service.audit_services, "log_event", lambda *args, **kwargs: None)
        monkeypatch.setattr(bulk_worker.audit_services, "log_event", lambda *args, **kwargs: None)

        selection = hr_schemas.HrPeopleSelection(
            mode="EXPLICIT",
            user_ids=[str(user.id) for user in seeded["people"]],
        )
        preview = bulk_service.preview_contract_batch(
            db,
            amo_id=str(seeded["amo_id"]),
            actor=seeded["admin"],
            payload=bulk_schemas.ContractBatchPreviewRequest(
                selection=selection,
                defaults=bulk_schemas.ContractDefaults(
                    contract_type=models.ContractType.PERMANENT,
                    employment_status=models.EmploymentStatus.ACTIVE,
                    effective_from=date.today(),
                    primary_base_station_id=str(seeded["base_id"]),
                    supervisor_user_id=str(seeded["admin"].id),
                ),
            ),
        )
        assert preview.matched_count == 3
        assert preview.eligible_count == 3
        assert preview.blocked_count == 0

        request = bulk_schemas.ContractBatchSubmitRequest(
            selection=selection,
            defaults=bulk_schemas.ContractDefaults(
                contract_type=models.ContractType.PERMANENT,
                employment_status=models.EmploymentStatus.ACTIVE,
                effective_from=date.today(),
                primary_base_station_id=str(seeded["base_id"]),
                supervisor_user_id=str(seeded["admin"].id),
            ),
            expected_match_count=preview.matched_count,
            expected_selection_token=preview.selection_token,
        )
        first, created = bulk_service.submit_contract_batch(
            db,
            amo_id=str(seeded["amo_id"]),
            actor=seeded["admin"],
            idempotency_key="contract-bulk-idempotency-1",
            payload=request,
        )
        duplicate, duplicate_created = bulk_service.submit_contract_batch(
            db,
            amo_id=str(seeded["amo_id"]),
            actor=seeded["admin"],
            idempotency_key="contract-bulk-idempotency-1",
            payload=request,
        )
        db.flush()
        assert created is True
        assert duplicate_created is False
        assert duplicate.id == first.id

        bulk_service.process_operation(first.id)
        db.expire_all()
        operation = bulk_service.read_operation(
            db,
            amo_id=str(seeded["amo_id"]),
            operation_id=first.id,
        )
        assert operation.status == "COMPLETED"
        assert operation.processed_count == 3
        assert operation.succeeded_count == 3
        assert operation.failed_count == 0
        assert db.query(models.EmploymentContract).filter(
            models.EmploymentContract.amo_id == seeded["amo_id"]
        ).count() == 3
    finally:
        _close_postgres_session(engine, connection, transaction, db)


@pytest.mark.skipif(
    not os.getenv("DATABASE_URL", "").startswith("postgresql"),
    reason="PostgreSQL integration database is not configured",
)
def test_work_pattern_batch_replaces_from_effective_date_and_preserves_history(monkeypatch) -> None:
    engine, connection, transaction, db = _postgres_session()
    try:
        seeded = _seed(db)
        monkeypatch.setattr(
            bulk_worker,
            "WriteSessionLocal",
            sessionmaker(bind=connection, autoflush=False, expire_on_commit=False),
        )
        monkeypatch.setattr(bulk_service.audit_services, "log_event", lambda *args, **kwargs: None)
        monkeypatch.setattr(bulk_worker.audit_services, "log_event", lambda *args, **kwargs: None)
        monkeypatch.setattr(bulk_patterns.audit_services, "log_event", lambda *args, **kwargs: None)

        old_pattern = models.WorkPattern(
            amo_id=seeded["amo_id"], code="OLD", name="Old rotation", cycle_length_days=7,
            timezone_name="UTC", applicability_json={}, is_active=True,
        )
        new_pattern = models.WorkPattern(
            amo_id=seeded["amo_id"], code="NEW", name="New rotation", cycle_length_days=7,
            timezone_name="UTC", applicability_json={}, is_active=True,
        )
        db.add_all([old_pattern, new_pattern])
        db.flush()
        effective_from = date.today()
        db.add(models.EmployeeWorkPatternAssignment(
            amo_id=seeded["amo_id"], user_id=seeded["people"][0].id,
            work_pattern_id=old_pattern.id, effective_from=effective_from - timedelta(days=30),
            effective_to=None, cycle_anchor_date=effective_from - timedelta(days=30),
            created_by_user_id=seeded["admin"].id,
        ))
        db.flush()

        selection = hr_schemas.HrPeopleSelection(
            mode="EXPLICIT",
            user_ids=[str(user.id) for user in seeded["people"]],
        )
        options = bulk_schemas.WorkPatternBatchOptions(
            work_pattern_id=str(new_pattern.id), effective_from=effective_from,
            cycle_anchor_date=effective_from, conflict_strategy="REPLACE_OVERLAPS",
            reason="Move department to new rotation",
        )
        preview = bulk_service.preview_work_pattern_batch(
            db,
            amo_id=str(seeded["amo_id"]),
            actor=seeded["admin"],
            payload=bulk_schemas.WorkPatternBatchPreviewRequest(selection=selection, options=options),
        )
        assert preview.matched_count == 3
        assert preview.assign_count == 2
        assert preview.replace_count == 1
        assert preview.blocked_count == 0

        operation, created = bulk_service.submit_work_pattern_batch(
            db,
            amo_id=str(seeded["amo_id"]),
            actor=seeded["admin"],
            idempotency_key="pattern-bulk-idempotency-1",
            payload=bulk_schemas.WorkPatternBatchSubmitRequest(
                selection=selection, options=options,
                expected_match_count=preview.matched_count,
                expected_selection_token=preview.selection_token,
            ),
        )
        assert created is True
        bulk_service.process_operation(operation.id)
        db.expire_all()

        completed = bulk_service.read_operation(
            db, amo_id=str(seeded["amo_id"]), operation_id=operation.id,
        )
        assert completed.status == "COMPLETED"
        assert completed.succeeded_count == 3
        old_assignment = db.query(models.EmployeeWorkPatternAssignment).filter(
            models.EmployeeWorkPatternAssignment.user_id == seeded["people"][0].id,
            models.EmployeeWorkPatternAssignment.work_pattern_id == old_pattern.id,
        ).one()
        assert old_assignment.effective_to == effective_from - timedelta(days=1)
        assert db.query(models.EmployeeWorkPatternAssignment).filter(
            models.EmployeeWorkPatternAssignment.work_pattern_id == new_pattern.id,
            models.EmployeeWorkPatternAssignment.effective_from == effective_from,
        ).count() == 3
    finally:
        _close_postgres_session(engine, connection, transaction, db)


@pytest.mark.skipif(
    not os.getenv("DATABASE_URL", "").startswith("postgresql"),
    reason="PostgreSQL integration database is not configured",
)
def test_failed_operation_resume_only_requeues_interrupted_items(monkeypatch) -> None:
    engine, connection, transaction, db = _postgres_session()
    try:
        seeded = _seed(db)
        monkeypatch.setattr(bulk_service.audit_services, "log_event", lambda *args, **kwargs: None)
        operation = bulk_models.WorkforceBulkOperation(
            amo_id=seeded["amo_id"],
            actor_user_id=seeded["admin"].id,
            operation_type="CREATE_CONTRACTS",
            status="FAILED",
            idempotency_key="resume-test",
            request_hash="a" * 64,
            selection_token="b" * 64,
            selection_snapshot={"mode": "EXPLICIT"},
            payload_json={},
            total_count=2,
            processed_count=1,
            succeeded_count=1,
            last_error="worker interrupted",
        )
        db.add(operation)
        db.flush()
        db.add_all([
            bulk_models.WorkforceBulkOperationItem(
                operation_id=operation.id,
                amo_id=seeded["amo_id"],
                user_id=seeded["people"][0].id,
                sequence=0,
                status="SUCCEEDED",
                attempt_count=1,
            ),
            bulk_models.WorkforceBulkOperationItem(
                operation_id=operation.id,
                amo_id=seeded["amo_id"],
                user_id=seeded["people"][1].id,
                sequence=1,
                status="RUNNING",
                attempt_count=1,
            ),
        ])
        db.flush()

        resumed = bulk_service.resume_operation(
            db,
            amo_id=str(seeded["amo_id"]),
            actor=seeded["admin"],
            operation_id=str(operation.id),
        )
        db.flush()
        assert resumed.status == "QUEUED"
        statuses = {
            item.sequence: item.status
            for item in db.query(bulk_models.WorkforceBulkOperationItem).filter(
                bulk_models.WorkforceBulkOperationItem.operation_id == operation.id
            ).all()
        }
        assert statuses == {0: "SUCCEEDED", 1: "PENDING"}
    finally:
        _close_postgres_session(engine, connection, transaction, db)
