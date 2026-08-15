from __future__ import annotations

import os
from datetime import date, timedelta
from types import SimpleNamespace
from uuid import uuid4

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import Session

from amodb.apps.accounts import models as account_models
from amodb.apps.foundations import models as foundation_models
from amodb.apps.workforce import (
    governance_directory,
    governance_models,
    governance_mutations,
    governance_schemas,
    hierarchy_roles,
    models,
)


def _id() -> str:
    return str(uuid4())


def _postgres_session() -> tuple[object, object, object, Session]:
    engine = create_engine(os.environ["DATABASE_URL"], pool_pre_ping=True)
    connection = engine.connect()
    transaction = connection.begin()
    db = Session(bind=connection, autoflush=False, expire_on_commit=False)
    return engine, connection, transaction, db


def _close(engine, connection, transaction, db: Session) -> None:
    db.close()
    if transaction.is_active:
        transaction.rollback()
    connection.close()
    engine.dispose()


def _user(*, amo_id: str, department_id: str, staff_code: str, name: str, role, is_admin: bool = False):
    return account_models.User(
        id=_id(), amo_id=amo_id, department_id=department_id, staff_code=staff_code,
        email=f"{staff_code.lower()}@governance.invalid", first_name=name.split()[0],
        last_name=name.split()[-1], full_name=name, position_title="Legacy title", role=role,
        hashed_password="not-a-real-password-hash", is_active=True, is_system_account=False,
        is_amo_admin=is_admin,
    )


def _operation(*, amo_id: str, actor_id: str, operation_type: str, payload: dict):
    return SimpleNamespace(
        id=_id(), amo_id=amo_id, actor_user_id=actor_id,
        operation_type=operation_type, payload_json=payload,
    )


def _item(*, user_id: str, payload: dict):
    return SimpleNamespace(user_id=user_id, input_json=payload)


def test_kcar_2025_management_catalogue_and_reporting_rule() -> None:
    assert [role["key"] for role in hierarchy_roles.KCAR_ROLES] == [
        "ACCOUNTABLE_EXECUTIVE",
        "BASE_MAINTENANCE_MANAGER",
        "LINE_MAINTENANCE_MANAGER",
        "WORKSHOP_MANAGER",
        "QUALITY_MANAGER",
        "SAFETY_MANAGER",
    ]
    assert all(
        hierarchy_roles.can_have_supervisor(
            SimpleNamespace(management_level=role["management_level"])
        ) is False
        for role in hierarchy_roles.KCAR_ROLES
    )
    assert hierarchy_roles.can_have_supervisor(SimpleNamespace(management_level="SUPERVISOR")) is True
    assert hierarchy_roles.TENANT_FUNCTION_KEYS == {
        "HUMAN_RESOURCES",
        "INFORMATION_TECHNOLOGY",
        "FINANCE",
    }


@pytest.mark.skipif(
    not os.getenv("DATABASE_URL", "").startswith("postgresql"),
    reason="PostgreSQL integration database is not configured",
)
def test_governed_directory_and_all_controlled_mutations() -> None:
    engine, connection, transaction, db = _postgres_session()
    try:
        today = date.today()
        amo_id = _id()
        engineering_id = _id()
        quality_id = _id()
        db.add(account_models.AMO(
            id=amo_id, amo_code=f"GOV-{amo_id[:8]}", name="Workforce Governance Test",
            login_slug=f"workforce-governance-{amo_id[:8]}", time_zone="UTC",
        ))
        db.add_all([
            account_models.Department(id=engineering_id, amo_id=amo_id, code="ENG", name="Engineering", is_active=True),
            account_models.Department(id=quality_id, amo_id=amo_id, code="QMS", name="Quality", is_active=True),
        ])
        db.flush()

        admin = _user(
            amo_id=amo_id, department_id=engineering_id, staff_code="ADMIN-001",
            name="Governance Admin", role=account_models.AccountRole.AMO_ADMIN, is_admin=True,
        )
        supervisor = _user(
            amo_id=amo_id, department_id=engineering_id, staff_code="SUP-001",
            name="Governance Supervisor", role=account_models.AccountRole.PRODUCTION_ENGINEER,
        )
        target = _user(
            amo_id=amo_id, department_id=engineering_id, staff_code="TECH-001",
            name="Governance Technician", role=account_models.AccountRole.TECHNICIAN,
        )
        quality_person = _user(
            amo_id=amo_id, department_id=quality_id, staff_code="QMS-001",
            name="Quality Inspector", role=account_models.AccountRole.QUALITY_INSPECTOR,
        )
        db.add_all([admin, supervisor, target, quality_person])
        db.flush()

        nbo = foundation_models.BaseStation(
            id=_id(), amo_id=amo_id, code="NBO", name="Nairobi", time_zone="UTC", is_active=True,
        )
        mba = foundation_models.BaseStation(
            id=_id(), amo_id=amo_id, code="MBA", name="Mombasa", time_zone="UTC", is_active=True,
        )
        db.add_all([nbo, mba])

        engineering = governance_models.WorkforceOrgUnit(
            id=_id(), amo_id=amo_id, legacy_department_id=engineering_id, code="ENG", name="Engineering",
            unit_type="DEPARTMENT", sort_order=10, is_active=True,
        )
        line = governance_models.WorkforceOrgUnit(
            id=_id(), amo_id=amo_id, parent_id=engineering.id, code="LINE", name="Line Maintenance",
            unit_type="SECTION", sort_order=20, is_active=True,
        )
        quality = governance_models.WorkforceOrgUnit(
            id=_id(), amo_id=amo_id, legacy_department_id=quality_id, code="QMS", name="Quality",
            unit_type="DEPARTMENT", sort_order=30, is_active=True,
        )
        family = governance_models.WorkforceJobFamily(
            id=_id(), amo_id=amo_id, code="MAINT", name="Aircraft Maintenance", is_active=True,
        )
        grade = governance_models.WorkforceGrade(
            id=_id(), amo_id=amo_id, code="G3", name="Grade 3", rank_order=30, is_active=True,
        )
        technician_position = governance_models.WorkforcePosition(
            id=_id(), amo_id=amo_id, code="TECH", canonical_title="Aircraft Technician",
            job_family_id=family.id, grade_id=grade.id, is_supervisory=False, is_active=True,
        )
        supervisor_position = governance_models.WorkforcePosition(
            id=_id(), amo_id=amo_id, code="SUP", canonical_title="Maintenance Supervisor",
            job_family_id=family.id, grade_id=grade.id, is_supervisory=True, is_active=True,
        )
        db.add_all([engineering, line, quality, family, grade, technician_position, supervisor_position])
        db.flush()

        db.add_all([
            models.EmploymentContract(
                id=_id(), amo_id=amo_id, user_id=admin.id, contract_type=models.ContractType.PERMANENT,
                employment_status=models.EmploymentStatus.ACTIVE, effective_from=today - timedelta(days=365),
                primary_base_station_id=nbo.id,
            ),
            models.EmploymentContract(
                id=_id(), amo_id=amo_id, user_id=supervisor.id, contract_type=models.ContractType.PERMANENT,
                employment_status=models.EmploymentStatus.ACTIVE, effective_from=today - timedelta(days=365),
                primary_base_station_id=nbo.id,
            ),
            models.EmploymentContract(
                id=_id(), amo_id=amo_id, user_id=target.id, contract_type=models.ContractType.PERMANENT,
                employment_status=models.EmploymentStatus.ACTIVE, effective_from=today - timedelta(days=30),
                primary_base_station_id=nbo.id, secondary_base_station_id=mba.id,
            ),
            models.EmploymentContract(
                id=_id(), amo_id=amo_id, user_id=quality_person.id, contract_type=models.ContractType.PERMANENT,
                employment_status=models.EmploymentStatus.ACTIVE, effective_from=today - timedelta(days=30),
                primary_base_station_id=nbo.id,
            ),
        ])
        db.add_all([
            governance_models.WorkforcePersonPlacement(
                id=_id(), amo_id=amo_id, user_id=admin.id, org_unit_id=engineering.id,
                position_id=supervisor_position.id, placement_type="PRIMARY", base_station_id=nbo.id,
                effective_from=today - timedelta(days=365),
            ),
            governance_models.WorkforcePersonPlacement(
                id=_id(), amo_id=amo_id, user_id=supervisor.id, org_unit_id=line.id,
                position_id=supervisor_position.id, placement_type="PRIMARY", base_station_id=nbo.id,
                effective_from=today - timedelta(days=365),
            ),
            governance_models.WorkforcePersonPlacement(
                id=_id(), amo_id=amo_id, user_id=target.id, org_unit_id=line.id,
                position_id=technician_position.id, placement_type="PRIMARY", base_station_id=nbo.id,
                effective_from=today - timedelta(days=30),
            ),
            governance_models.WorkforcePersonPlacement(
                id=_id(), amo_id=amo_id, user_id=target.id, org_unit_id=quality.id,
                placement_type="MATRIX", base_station_id=mba.id,
                effective_from=today - timedelta(days=10),
            ),
            governance_models.WorkforcePersonPlacement(
                id=_id(), amo_id=amo_id, user_id=quality_person.id, org_unit_id=quality.id,
                position_id=technician_position.id, placement_type="PRIMARY", base_station_id=nbo.id,
                effective_from=today - timedelta(days=30),
            ),
        ])
        group = account_models.UserGroup(
            id=_id(), amo_id=amo_id, code="RELIEF", name="Relief Team",
            group_type=account_models.UserGroupType.CUSTOM, is_active=True,
        )
        db.add(group)
        db.flush()

        page = governance_directory.list_people_page(
            db, amo_id=amo_id, page=1, page_size=25,
            filters=governance_schemas.GovernedPeopleFilterInput(
                org_unit_id=engineering.id, include_descendants=True,
                job_family_id=family.id, grade_id=grade.id,
                secondary_base_station_id=mba.id,
                contract_effective_from_on_or_after=today - timedelta(days=60),
                lifecycle_state="ACTIVE", sort_by="position", sort_dir="asc",
            ),
        )
        assert page.total == 1
        assert [row.user_id for row in page.items] == [target.id]
        assert page.items[0].primary_org_path == ["Engineering", "Line Maintenance"]
        assert [row.org_unit_name for row in page.items[0].matrix_org_units] == ["Quality"]
        assert page.items[0].secondary_base_code == "MBA"
        assert page.items[0].job_family_name == "Aircraft Maintenance"
        assert page.items[0].grade_name == "Grade 3"

        supervisors = governance_directory.list_supervisors(
            db, amo_id=amo_id, page=1, page_size=25, search="Supervisor", exclude_user_id=target.id,
        )
        assert [row.user_id for row in supervisors.items] == [supervisor.id]
        assert supervisors.items[0].is_supervisory_position is True

        with pytest.raises(ValueError, match="cycle"):
            governance_directory.upsert_org_unit(
                db, amo_id=amo_id, actor_user_id=admin.id,
                payload=governance_schemas.OrgUnitWrite(
                    parent_id=line.id, code="ENG", name="Engineering", unit_type="DEPARTMENT",
                    legacy_department_id=engineering_id, sort_order=10, is_active=True,
                ),
                org_unit_id=engineering.id,
            )

        mutations = [
            ("ASSIGN_ORGANIZATION", {"effective_on": today.isoformat(), "org_unit_id": quality.id, "placement_type": "SECONDARY"}),
            ("ASSIGN_POSITION", {"effective_on": today.isoformat(), "position_id": supervisor_position.id, "preferred_title": "Acting Maintenance Lead"}),
            ("ASSIGN_BASES", {"effective_on": today.isoformat(), "primary_base_station_id": mba.id, "secondary_base_station_id": nbo.id}),
            ("ASSIGN_SUPERVISOR", {"effective_on": today.isoformat(), "supervisor_user_id": supervisor.id}),
            ("UPDATE_GROUPS", {"effective_on": today.isoformat(), "group_ids": [group.id], "group_mode": "ADD"}),
            ("UPDATE_CONTRACT_SETTINGS", {"effective_on": today.isoformat(), "contract_settings": {"cost_centre": "ENG-LINE", "fte_percentage": 90.0}}),
            ("SCHEDULE_OFFBOARDING", {"effective_on": today.isoformat(), "offboarding_reason": "End of controlled test assignment", "revoke_access": True, "end_contracts": True, "remove_groups": True}),
        ]
        for operation_type, payload in mutations:
            outcome = governance_mutations.process_personnel_mutation_item(
                db,
                operation=_operation(amo_id=amo_id, actor_id=admin.id, operation_type=operation_type, payload=payload),
                item=_item(user_id=target.id, payload=payload),
                actor=admin,
            )
            assert outcome[0] == "SUCCEEDED", (operation_type, outcome)
            db.flush()

        refreshed = db.query(account_models.User).filter(account_models.User.id == target.id).one()
        assert refreshed.is_active is False
        assert refreshed.position_title == "Acting Maintenance Lead"
        assert db.query(account_models.UserGroupMember).filter(
            account_models.UserGroupMember.user_id == target.id
        ).count() == 0
        assert db.query(governance_models.WorkforceOffboardingPlan).filter(
            governance_models.WorkforceOffboardingPlan.user_id == target.id,
            governance_models.WorkforceOffboardingPlan.status == "COMPLETED",
        ).count() == 1
        latest_contract = db.query(models.EmploymentContract).filter(
            models.EmploymentContract.user_id == target.id
        ).order_by(models.EmploymentContract.effective_from.desc()).first()
        assert latest_contract.primary_base_station_id == mba.id
        assert latest_contract.secondary_base_station_id == nbo.id
        assert latest_contract.supervisor_user_id == supervisor.id
        assert latest_contract.cost_centre == "ENG-LINE"
        assert latest_contract.fte_percentage == 90.0
        assert latest_contract.employment_status == models.EmploymentStatus.TERMINATED
    finally:
        _close(engine, connection, transaction, db)
