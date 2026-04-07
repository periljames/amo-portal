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


def test_person_id_change_reuses_existing_profile_by_email(db_session, monkeypatch):
    amo = _seed_amo(db_session)
    monkeypatch.setenv("PERSONNEL_IMPORT_DEFAULT_PASSWORD", "TempPass123!")

    existing_profile = models.PersonnelProfile(
        id="prof-1",
        amo_id=amo.id,
        person_id="OLD-001",
        first_name="Jane",
        last_name="Doe",
        full_name="Jane Doe",
        email="jane@example.com",
        status="Active",
    )
    db_session.add(existing_profile)
    db_session.commit()

    rows = [
        {
            "row_number": 2,
            "PersonID": "NEW-001",
            "FIRSTNAME": "Jane",
            "LASTNAME": "Doe",
            "Status": "Active",
            "Email": "jane@example.com",
        }
    ]
    summary = import_personnel_rows(db_session, amo_id=amo.id, rows=rows, dry_run=False)
    assert summary.created_personnel == 0
    assert summary.updated_personnel == 1
    assert db_session.query(models.PersonnelProfile).count() == 1
    updated_profile = db_session.query(models.PersonnelProfile).first()
    assert updated_profile is not None
    assert updated_profile.person_id == "NEW-001"


def test_skip_row_decision_does_not_apply_partial_profile_or_user_updates(db_session, monkeypatch):
    amo = _seed_amo(db_session)
    monkeypatch.setenv("PERSONNEL_IMPORT_DEFAULT_PASSWORD", "TempPass123!")

    existing_user = models.User(
        id="usr-skip-1",
        amo_id=amo.id,
        staff_code="P-020",
        email="old@example.com",
        first_name="Old",
        last_name="Name",
        full_name="Old Name",
        role=models.AccountRole.TECHNICIAN,
        hashed_password=services.get_password_hash("OldPass123!"),
        phone="+1-555-0000",
        is_active=True,
    )
    existing_profile = models.PersonnelProfile(
        id="prof-skip-1",
        amo_id=amo.id,
        person_id="P-020",
        user_id=existing_user.id,
        first_name="Old",
        last_name="Name",
        full_name="Old Name",
        email="old@example.com",
        phone_number="+1-555-0000",
        status="Active",
    )
    db_session.add_all([existing_user, existing_profile])
    db_session.commit()

    rows = [
        {
            "row_number": 2,
            "PersonID": "P-020",
            "FIRSTNAME": "New",
            "LASTNAME": "Name",
            "PersonName": "New Name",
            "Status": "Active",
            "PhoneNumber": "+1-555-9999",
            "Email": "new@example.com",
        }
    ]
    summary = import_personnel_rows(
        db_session,
        amo_id=amo.id,
        rows=rows,
        dry_run=False,
        decisions={2: "skip_row"},
    )

    assert summary.skipped_rows >= 1 or any("rejected" in issue.reason.lower() for issue in summary.issues)

    reloaded_profile = db_session.query(models.PersonnelProfile).filter_by(id="prof-skip-1").first()
    assert reloaded_profile is not None
    assert reloaded_profile.first_name == "Old"
    assert reloaded_profile.phone_number == "+1-555-0000"
    assert reloaded_profile.email == "old@example.com"

    reloaded_user = db_session.query(models.User).filter_by(id="usr-skip-1").first()
    assert reloaded_user is not None
    assert reloaded_user.first_name == "Old"
    assert reloaded_user.phone == "+1-555-0000"
    assert reloaded_user.email == "old@example.com"


def test_use_import_email_rejected_when_email_taken_by_different_user(db_session, monkeypatch):
    amo = _seed_amo(db_session)
    monkeypatch.setenv("PERSONNEL_IMPORT_DEFAULT_PASSWORD", "TempPass123!")

    linked_user = models.User(
        id="usr-email-1",
        amo_id=amo.id,
        staff_code="P-030",
        email="linked@example.com",
        first_name="Linked",
        last_name="User",
        full_name="Linked User",
        role=models.AccountRole.TECHNICIAN,
        hashed_password=services.get_password_hash("OldPass123!"),
        is_active=True,
    )
    taken_user = models.User(
        id="usr-email-2",
        amo_id=amo.id,
        staff_code="P-031",
        email="taken@example.com",
        first_name="Taken",
        last_name="User",
        full_name="Taken User",
        role=models.AccountRole.TECHNICIAN,
        hashed_password=services.get_password_hash("OldPass123!"),
        is_active=True,
    )
    profile = models.PersonnelProfile(
        id="prof-email-1",
        amo_id=amo.id,
        person_id="P-030",
        user_id=linked_user.id,
        first_name="Linked",
        last_name="User",
        full_name="Linked User",
        email="linked@example.com",
        status="Active",
    )
    db_session.add_all([linked_user, taken_user, profile])
    db_session.commit()

    rows = [
        {
            "row_number": 2,
            "PersonID": "P-030",
            "FIRSTNAME": "Linked",
            "LASTNAME": "User",
            "Status": "Active",
            "Email": "taken@example.com",
        }
    ]
    summary = import_personnel_rows(
        db_session,
        amo_id=amo.id,
        rows=rows,
        dry_run=False,
        decisions={2: "use_import_email"},
    )

    assert any("already used by another user account" in issue.reason.lower() for issue in summary.issues)
    assert db_session.query(models.User).filter_by(id="usr-email-1").first().email == "linked@example.com"
    assert db_session.query(models.PersonnelProfile).filter_by(id="prof-email-1").first().email == "linked@example.com"
