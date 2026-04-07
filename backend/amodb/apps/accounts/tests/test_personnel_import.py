from __future__ import annotations

from datetime import date

from amodb.apps.accounts import models, services
from amodb.apps.accounts.personnel_import import import_personnel_rows


def _seed_amo(db):
    amo = models.AMO(
        id="amo-test-1",
        amo_code="AMO-TEST",
        name="Test AMO",
        login_slug="amo-test",
        is_active=True,
    )
    db.add(amo)
    db.commit()
    return amo


def test_personnel_import_dry_run_and_idempotent(db_session, monkeypatch):
    amo = _seed_amo(db_session)
    monkeypatch.setenv("PERSONNEL_IMPORT_DEFAULT_PASSWORD", "TempPass123!")

    rows = [
        {
            "row_number": 2,
            "PersonID": "P-001",
            "FIRSTNAME": "Jane",
            "LASTNAME": "Doe",
            "PersonName": "Jane Doe",
            "nid": "N-1",
            "AMEL NO:": "A-1",
            "Internal Certification Stamp No:": "ABC-123",
            "initial_auth": "2024-01-02",
            "Department": "Quality",
            "Position": "Inspector",
            "PhoneNumber": "+1-555-111",
            "Email": "jane@example.com",
            "HireDate": "2023-03-04",
            "Employment_Status": "Permanent",
            "Status": "Active",
            "DOB": "1990-02-03",
            "birthplace": "Austin",
        }
    ]

    dry = import_personnel_rows(db_session, amo_id=amo.id, rows=rows, dry_run=True)
    assert dry.dry_run is True
    assert dry.created_personnel == 1
    assert dry.created_accounts == 1
    assert db_session.query(models.PersonnelProfile).count() == 0

    first = import_personnel_rows(db_session, amo_id=amo.id, rows=rows, dry_run=False)
    assert first.created_personnel == 1
    assert first.created_accounts == 1
    assert db_session.query(models.PersonnelProfile).count() == 1
    assert db_session.query(models.User).count() == 1

    second = import_personnel_rows(db_session, amo_id=amo.id, rows=rows, dry_run=False)
    assert second.updated_personnel == 1
    assert second.created_personnel == 0
    assert second.created_accounts == 0
    assert second.updated_accounts == 1


def test_personnel_import_skips_account_when_email_missing_and_dormant(db_session, monkeypatch):
    amo = _seed_amo(db_session)
    monkeypatch.setenv("PERSONNEL_IMPORT_DEFAULT_PASSWORD", "TempPass123!")

    rows = [
        {
            "row_number": 2,
            "PersonID": "P-002",
            "FIRSTNAME": "Dorm",
            "LASTNAME": "User",
            "Status": "Dormant",
            "Email": "",
        },
        {
            "row_number": 3,
            "PersonID": "P-003",
            "FIRSTNAME": "Active",
            "LASTNAME": "User",
            "Status": "Dormant",
            "Email": "dormant@example.com",
        },
    ]

    summary = import_personnel_rows(db_session, amo_id=amo.id, rows=rows, dry_run=False)
    assert summary.created_personnel == 2
    assert summary.skipped_accounts == 1
    assert summary.created_accounts == 1

    profile = db_session.query(models.PersonnelProfile).filter_by(person_id="P-002").first()
    assert profile is not None
    assert profile.status == "Dormant"

    dormant_user = db_session.query(models.User).filter_by(email="dormant@example.com").first()
    assert dormant_user is not None
    assert dormant_user.is_active is False
    assert dormant_user.must_change_password is True


def test_password_change_sets_password_changed_at(db_session, monkeypatch):
    amo = _seed_amo(db_session)
    user = models.User(
        id="usr-1",
        amo_id=amo.id,
        staff_code="P-005",
        email="pw@example.com",
        first_name="Pw",
        last_name="User",
        full_name="Pw User",
        role=models.AccountRole.TECHNICIAN,
        hashed_password=services.get_password_hash("OldPass123!"),
        must_change_password=True,
    )
    db_session.add(user)
    db_session.commit()

    updated = services.change_password(
        db_session,
        user=user,
        current_password="OldPass123!",
        new_password="NewPass1234!",
        ip=None,
        user_agent=None,
    )
    assert updated.must_change_password is False
    assert updated.password_changed_at is not None
    assert updated.password_changed_at.date() >= date(2020, 1, 1)
