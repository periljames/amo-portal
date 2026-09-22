from datetime import date

import pytest
from sqlalchemy import create_engine, event
from sqlalchemy.dialects import postgresql
from sqlalchemy.orm import Session

from amodb.database import Base
from amodb.apps.accounts import models as accounts
from amodb.apps.audit.models import AuditEvent
from amodb.apps.foundations import models as foundations
from amodb.apps.rostering import models as rostering_models  # noqa: F401
from amodb.apps.workforce import governance_mutations, models, services
from amodb.apps.training import workbook_import as importer
from amodb.apps.training.workbook_models import PersonnelLicence, TrainingWorkbookImportJob, TrainingWorkbookImportRow


@pytest.fixture
def contract_db():
    engine = create_engine("sqlite:///:memory:")
    tables = {model.__table__ for model in (
        accounts.AMO, accounts.User, accounts.PersonnelProfile,
        accounts.UserAuthorisation, accounts.AccountSecurityEvent, accounts.AMOAsset,
        foundations.BaseStation, foundations.BaseStationAlias, foundations.UserBaseAssignment,
        models.EmploymentContract, AuditEvent, PersonnelLicence,
    )}
    while True:
        dependencies = {fk.column.table for table in tables for fk in table.foreign_keys}
        if dependencies <= tables:
            break
        tables |= dependencies
    Base.metadata.create_all(engine, tables=list(tables))
    with Session(engine) as db:
        db.add(accounts.AMO(id="amo", amo_code="TEST", name="Import test", login_slug="import-test"))
        db.flush()
        db.add(accounts.User(
            id="person", amo_id="amo", staff_code="ENG01", email="test@example.invalid",
            first_name="Test", last_name="Person", full_name="Test Person",
            role=accounts.AccountRole.PRODUCTION_ENGINEER, hashed_password="unused",
        ))
        db.add(foundations.BaseStation(
            id="base", amo_id="amo", code="TEST", name="Test base",
            base_type=foundations.BaseStationType.MAIN_BASE,
        ))
        db.flush()
        db.add(models.EmploymentContract(
            id="contract", amo_id="amo", user_id="person",
            contract_type=models.ContractType.PERMANENT,
            effective_from=date(2024, 1, 1), primary_base_station_id="base",
        ))
        db.commit()
        yield db
    engine.dispose()


def capture_contract_locks(db):
    statements = []

    @event.listens_for(db, "do_orm_execute")
    def check_lock(state):
        if not state.is_select or state.statement._for_update_arg is None:
            return
        sql = str(state.statement.compile(dialect=postgresql.dialect()))
        if "FROM employment_contracts" in sql:
            # Compile the actual service query, including its eager outer joins.
            assert "LEFT OUTER JOIN" in sql
            assert sql.rstrip().endswith("FOR UPDATE OF employment_contracts")
            statements.append(sql)

    return statements


def test_people_import_updates_contract_and_is_repeatable(contract_db):
    db = contract_db
    locks = capture_contract_locks(db)
    job = TrainingWorkbookImportJob(id="job", amo_id="amo", actor_user_id="person")
    row = TrainingWorkbookImportRow(
        id="row", source_row=2, decision="LINK_EXISTING_ACCOUNT",
        payload_json={key: importer.json_value(value) for key, value in importer._person_payload({
            "PersonID": "ENG01", "FIRSTNAME": "Test", "LASTNAME": "Person",
            "PersonName": "Test Person", "Email": "test@example.invalid",
            "HireDate": date(2020, 6, 1),
        }).items()},
    )
    for _ in range(2):
        result = importer._upsert_person(db, job, row)
        db.commit()
        assert result.entity_id == "person"
    assert len(locks) == 2
    assert db.get(models.EmploymentContract, "contract").effective_from == date(2020, 6, 1)
    assert db.query(accounts.PersonnelProfile).one().hire_date == date(2020, 6, 1)
    hire_audit = db.query(AuditEvent).filter(AuditEvent.action == "HIRE_DATE_IMPORT_APPLIED").one()
    assert hire_audit.entity_id == db.query(accounts.PersonnelProfile).one().id
    assert db.query(AuditEvent).filter(AuditEvent.action == "sync_hire_date").count() == 1


@pytest.mark.parametrize("hire_date", [None, date(2024, 1, 1), date(2025, 1, 1)])
def test_contract_sync_preserves_missing_unchanged_and_invalid_dates(contract_db, hire_date):
    db = contract_db
    contract = db.get(models.EmploymentContract, "contract")
    contract.effective_to = date(2024, 12, 31)
    db.commit()
    capture_contract_locks(db)
    services.sync_contract_start_from_hire_date(
        db, amo_id="amo", user_id="person", hire_date=hire_date,
        actor_user_id="person", source="TRAINING_WORKBOOK_PEOPLE_HIREDATE",
    )
    db.commit()
    assert contract.effective_from == date(2024, 1, 1)


def test_related_contract_queries_scope_locks(contract_db):
    db = contract_db
    locks = capture_contract_locks(db)
    for on_date in (date(2023, 1, 1), date(2024, 6, 1)):
        assert governance_mutations._contract_on(
            db, amo_id="amo", user_id="person", on_date=on_date,
        ).id == "contract"
    assert services.create_reemployment_contract(
        db, amo_id="amo", user_id="missing", effective_from=date(2025, 1, 1),
        actor_user_id="person", reason="Test",
    ) is None
    assert len(locks) == 4
