from __future__ import annotations

import os
from concurrent.futures import ThreadPoolExecutor
from decimal import Decimal
from uuid import uuid4

import pytest
from fastapi import HTTPException
from sqlalchemy import create_engine, text
from sqlalchemy.exc import DBAPIError
from sqlalchemy.orm import sessionmaker

from amodb.apps.accounts import models as account_models
from amodb.apps.fleet import models as fleet_models
from amodb.apps.aircraft_architecture.aircraft_induction import models as induction_models
from amodb.apps.aircraft_architecture.aircraft_induction.router import read_induction
from amodb.apps.aircraft_architecture.aircraft_induction import services as induction_services
from amodb.apps.aircraft_architecture.content_packs import models as pack_models
from amodb.apps.aircraft_architecture.content_packs import schemas as pack_schemas
from amodb.apps.aircraft_architecture.content_packs import services as pack_services
from amodb.apps.aircraft_architecture.daily_utilisation import models as daily_models
from amodb.apps.aircraft_architecture.tests.test_u5_u6_postgresql import (
    _create_account,
    _create_engineering_fixture,
    _payload,
    _suffix,
)


DATABASE_URL = os.environ.get("POSTGRES_INTEGRATION_URL")
pytestmark = pytest.mark.skipif(
    not DATABASE_URL,
    reason="POSTGRES_INTEGRATION_URL is required for U5/U6 acceptance tests",
)


@pytest.fixture(scope="module")
def engine():
    value = create_engine(DATABASE_URL, future=True, pool_pre_ping=True)
    try:
        yield value
    finally:
        value.dispose()


@pytest.fixture(scope="module")
def sessions(engine):
    return sessionmaker(bind=engine, autoflush=False, expire_on_commit=False)


def _account_for_authority(
    *,
    role: account_models.AccountRole,
    amo_id: str | None = "tenant-a",
    active: bool = True,
    system: bool = False,
    admin: bool = False,
) -> account_models.User:
    return account_models.User(
        amo_id=amo_id,
        staff_code=uuid4().hex[:12],
        email=f"{uuid4().hex}@authority.invalid",
        first_name="Authority",
        last_name="Test",
        full_name="Authority Test",
        role=role,
        hashed_password="not-used",
        is_active=active,
        is_system_account=system,
        is_superuser=False,
        is_amo_admin=admin,
    )


def _assert_sql_rejected(engine, statement: str, parameters: dict) -> None:
    with pytest.raises(DBAPIError):
        with engine.begin() as connection:
            connection.execute(text(statement), parameters)


def test_human_account_and_role_controls_cover_all_required_cases():
    administrator = _account_for_authority(
        role=account_models.AccountRole.AMO_ADMIN,
        admin=True,
    )
    planner = _account_for_authority(
        role=account_models.AccountRole.PLANNING_ENGINEER,
    )
    ordinary = _account_for_authority(role=account_models.AccountRole.TECHNICIAN)
    inactive = _account_for_authority(
        role=account_models.AccountRole.AMO_ADMIN,
        admin=True,
        active=False,
    )
    system = _account_for_authority(
        role=account_models.AccountRole.AMO_ADMIN,
        admin=True,
        system=True,
    )
    no_tenant = _account_for_authority(
        role=account_models.AccountRole.AMO_ADMIN,
        admin=True,
        amo_id=None,
    )

    assert induction_services.require_human_induction_authority(administrator) == "tenant-a"
    assert induction_services.require_human_induction_authority(planner) == "tenant-a"
    for denied_user in (ordinary, inactive, system, no_tenant):
        with pytest.raises(HTTPException) as denied:
            induction_services.require_human_induction_authority(denied_user)
        assert denied.value.status_code == 403


def test_atomic_induction_creates_complete_exact_aggregate_and_lineage(sessions):
    suffix = _suffix()
    with sessions() as db:
        fixture = _create_engineering_fixture(db, suffix)
        user = db.get(account_models.User, fixture["user_id"])
        payload = _payload(fixture, suffix)
        induction_id = induction_services.induct_aircraft(db, payload=payload, user=user).id

    with sessions() as verify:
        induction = verify.get(induction_models.AircraftInduction, induction_id)
        configuration = induction.configuration_snapshot
        applicability = induction.applicability_snapshot
        lineage = induction.lineage
        component = verify.query(fleet_models.AircraftComponent).filter_by(
            aircraft_serial_number=payload.aircraft_serial_number
        ).one()
        component_state = verify.query(daily_models.ComponentExactUtilisationState).filter_by(
            aircraft_component_id=component.id
        ).one()
        airframe_state = verify.query(daily_models.AircraftExactUtilisationState).filter_by(
            aircraft_serial_number=payload.aircraft_serial_number
        ).one()
        role = verify.query(induction_models.AircraftComponentUtilisationRole).filter_by(
            aircraft_component_id=component.id
        ).one()

        assert configuration.snapshot_hash != "pending"
        assert configuration.snapshot_json["initial_airframe_hours"] == "1250.25"
        assert configuration.snapshot_json["components"][0]["baseline_hours"] == "775.50"
        assert configuration.snapshot_json["components"][0]["position_code"] == "ENGINE_1"
        assert configuration.snapshot_json["components"][0]["component_id"] == component.id
        assert len(configuration.items) == 1
        assert airframe_state.total_hours == Decimal("1250.25")
        assert airframe_state.total_cycles == 840
        assert component_state.total_hours == Decimal("775.50")
        assert component_state.total_cycles == 510
        assert role.role == "ENGINE"
        assert role.assignment_source == "TYPE_DEFINITION"
        assert lineage.type_revision_id == fixture["type_revision_id"]
        assert lineage.programme_revision_id == fixture["programme_revision_id"]
        assert lineage.configuration_snapshot_id == configuration.id
        assert lineage.applicability_snapshot_id == applicability.id
        assert lineage.type_content_hash == "a" * 64
        assert lineage.programme_content_hash == "d" * 64


def test_deliberate_commit_failure_rolls_back_every_induction_record(sessions, monkeypatch):
    suffix = _suffix()
    with sessions() as db:
        fixture = _create_engineering_fixture(db, suffix)
        user = db.get(account_models.User, fixture["user_id"])
        payload = _payload(fixture, suffix)
        monkeypatch.setattr(
            db,
            "commit",
            lambda: (_ for _ in ()).throw(RuntimeError("deliberate atomic failure")),
        )
        with pytest.raises(RuntimeError, match="deliberate atomic failure"):
            induction_services.induct_aircraft(db, payload=payload, user=user)
        db.rollback()

    with sessions() as verify:
        assert verify.get(fleet_models.Aircraft, payload.aircraft_serial_number) is None
        assert verify.query(fleet_models.AircraftComponent).filter_by(
            aircraft_serial_number=payload.aircraft_serial_number
        ).count() == 0
        assert verify.query(induction_models.AircraftInduction).filter_by(
            idempotency_key=payload.idempotency_key
        ).count() == 0
        assert verify.query(induction_models.AircraftConfigurationSnapshot).filter_by(
            aircraft_serial_number=payload.aircraft_serial_number
        ).count() == 0
        assert verify.query(induction_models.AircraftApplicabilitySnapshot).filter_by(
            aircraft_serial_number=payload.aircraft_serial_number
        ).count() == 0
        assert verify.query(induction_models.AircraftEngineeringLineage).filter_by(
            aircraft_serial_number=payload.aircraft_serial_number
        ).count() == 0
        assert verify.query(daily_models.AircraftExactUtilisationState).filter_by(
            aircraft_serial_number=payload.aircraft_serial_number
        ).count() == 0
        assert verify.query(daily_models.ComponentExactUtilisationState).join(
            fleet_models.AircraftComponent,
            daily_models.ComponentExactUtilisationState.aircraft_component_id
            == fleet_models.AircraftComponent.id,
        ).filter(
            fleet_models.AircraftComponent.aircraft_serial_number
            == payload.aircraft_serial_number
        ).count() == 0


def test_tenant_scoped_idempotency_and_lookup_do_not_cross_tenants(sessions):
    suffix_a = _suffix()
    suffix_b = _suffix()
    shared_key = f"shared-{uuid4().hex}"
    with sessions() as db:
        fixture_a = _create_engineering_fixture(db, suffix_a)
        fixture_b = _create_engineering_fixture(db, suffix_b)
        user_a = db.get(account_models.User, fixture_a["user_id"])
        user_b = db.get(account_models.User, fixture_b["user_id"])
        payload_a = _payload(fixture_a, suffix_a, idempotency_key=shared_key)
        payload_b = _payload(fixture_b, suffix_b, idempotency_key=shared_key)
        induction_a = induction_services.induct_aircraft(db, payload=payload_a, user=user_a)
        induction_b = induction_services.induct_aircraft(db, payload=payload_b, user=user_b)
        assert induction_a.id != induction_b.id
        assert db.query(induction_models.AircraftInduction).filter_by(
            idempotency_key=shared_key
        ).count() == 2

        with pytest.raises(HTTPException) as hidden:
            read_induction(induction_a.id, db=db, user=user_b)
        assert hidden.value.status_code == 404

        foreign_programme = payload_a.model_copy(
            update={
                "idempotency_key": f"foreign-{uuid4().hex}",
                "aircraft_serial_number": f"AC-{uuid4().hex[:10]}",
                "registration": f"5Y-{uuid4().hex[:5]}",
            }
        )
        with pytest.raises(HTTPException) as denied:
            induction_services.induct_aircraft(db, payload=foreign_programme, user=user_b)
        assert denied.value.status_code == 404
        db.rollback()


@pytest.mark.parametrize(
    "source_update",
    [
        {"source_reference": "UNCONTROLLED-AMM"},
        {"source_revision": "R2"},
        {"source_checksum_sha256": "f" * 64},
        {"source_revision": ""},
        {"source_checksum_sha256": None},
    ],
)
def test_component_source_requires_the_complete_exact_controlled_tuple(sessions, source_update):
    suffix = _suffix()
    with sessions() as db:
        fixture = _create_engineering_fixture(db, suffix)
        user = db.get(account_models.User, fixture["user_id"])
        payload = _payload(fixture, suffix)
        component = payload.components[0].model_copy(update=source_update)
        invalid = payload.model_copy(update={"components": [component]})
        with pytest.raises(HTTPException) as rejected:
            induction_services.induct_aircraft(db, payload=invalid, user=user)
        assert rejected.value.status_code == 422
        db.rollback()


def test_postgresql_rejects_update_and_delete_for_every_immutable_u5_record(engine, sessions):
    suffix = _suffix()
    with sessions() as db:
        fixture = _create_engineering_fixture(db, suffix)
        user = db.get(account_models.User, fixture["user_id"])
        payload = _payload(fixture, suffix)
        induction = induction_services.induct_aircraft(db, payload=payload, user=user)
        component = db.query(fleet_models.AircraftComponent).filter_by(
            aircraft_serial_number=payload.aircraft_serial_number
        ).one()
        item = induction.configuration_snapshot.items[0]
        ids = {
            "induction": induction.id,
            "configuration": induction.configuration_snapshot.id,
            "configuration_item": item.id,
            "applicability": induction.applicability_snapshot.id,
            "lineage": induction.lineage.id,
            "airframe_state": db.query(daily_models.AircraftExactUtilisationState.id).filter_by(
                aircraft_serial_number=payload.aircraft_serial_number
            ).scalar(),
            "component_state": db.query(daily_models.ComponentExactUtilisationState.id).filter_by(
                aircraft_component_id=component.id
            ).scalar(),
        }
        amo_id = fixture["amo_id"]
        user_id = fixture["user_id"]

    immutable_operations = [
        ("UPDATE aircraft_inductions SET request_hash = :value WHERE id = :id", {"value": "e" * 64, "id": ids["induction"]}),
        ("DELETE FROM aircraft_inductions WHERE id = :id", {"id": ids["induction"]}),
        ("UPDATE aircraft_configuration_snapshots SET snapshot_hash = :value WHERE id = :id", {"value": "e" * 64, "id": ids["configuration"]}),
        ("DELETE FROM aircraft_configuration_snapshots WHERE id = :id", {"id": ids["configuration"]}),
        ("UPDATE aircraft_configuration_snapshot_items SET position_code = 'CHANGED' WHERE id = :id", {"id": ids["configuration_item"]}),
        ("DELETE FROM aircraft_configuration_snapshot_items WHERE id = :id", {"id": ids["configuration_item"]}),
        ("UPDATE aircraft_applicability_snapshots SET snapshot_hash = :value WHERE id = :id", {"value": "e" * 64, "id": ids["applicability"]}),
        ("DELETE FROM aircraft_applicability_snapshots WHERE id = :id", {"id": ids["applicability"]}),
        ("UPDATE aircraft_engineering_lineage SET lineage_hash = :value WHERE id = :id", {"value": "e" * 64, "id": ids["lineage"]}),
        ("DELETE FROM aircraft_engineering_lineage WHERE id = :id", {"id": ids["lineage"]}),
        ("UPDATE aircraft_exact_utilisation_states SET total_hours = total_hours + 1 WHERE id = :id", {"id": ids["airframe_state"]}),
        ("DELETE FROM aircraft_exact_utilisation_states WHERE id = :id", {"id": ids["airframe_state"]}),
        ("UPDATE component_exact_utilisation_states SET total_hours = total_hours + 1 WHERE id = :id", {"id": ids["component_state"]}),
        ("DELETE FROM component_exact_utilisation_states WHERE id = :id", {"id": ids["component_state"]}),
    ]
    for statement, parameters in immutable_operations:
        _assert_sql_rejected(engine, statement, parameters)

    entry_id = str(uuid4())
    exposure_id = str(uuid4())
    with engine.begin() as connection:
        connection.execute(
            text(
                """
                INSERT INTO aircraft_daily_utilisation_entries (
                    id, amo_id, aircraft_serial_number, operation_date, techlog_no,
                    flight_hours, cycles, nil_operation, source_type, status,
                    revision_no, idempotency_key, content_hash,
                    created_by_user_id, posted_by_user_id, posted_at,
                    created_at
                ) VALUES (
                    :id, :amo_id, :serial, CURRENT_DATE, :techlog,
                    1.25, 1, false, 'MANUAL', 'POSTED',
                    1, :idempotency_key, :content_hash,
                    :user_id, :user_id, CURRENT_TIMESTAMP,
                    CURRENT_TIMESTAMP
                )
                """
            ),
            {
                "id": entry_id,
                "amo_id": amo_id,
                "serial": payload.aircraft_serial_number,
                "techlog": f"TL-{suffix}",
                "idempotency_key": f"ledger-{suffix}",
                "content_hash": "9" * 64,
                "user_id": user_id,
            },
        )
        connection.execute(
            text(
                """
                INSERT INTO aircraft_daily_utilisation_exposures (
                    id, entry_id, target_type, component_id, component_position,
                    component_description, derivation, hours_delta, cycles_delta,
                    before_hours, before_cycles, after_hours, after_cycles,
                    baseline_missing
                ) VALUES (
                    :id, :entry_id, 'AIRFRAME', NULL, 'AIRFRAME',
                    'Airframe', 'SHARED_DAILY', 1.25, 1,
                    1250.25, 840, 1251.50, 841, false
                )
                """
            ),
            {"id": exposure_id, "entry_id": entry_id},
        )

    for statement, parameters in [
        ("UPDATE aircraft_daily_utilisation_entries SET flight_hours = 2.00 WHERE id = :id", {"id": entry_id}),
        ("DELETE FROM aircraft_daily_utilisation_entries WHERE id = :id", {"id": entry_id}),
        ("UPDATE aircraft_daily_utilisation_exposures SET hours_delta = 2.00 WHERE id = :id", {"id": exposure_id}),
        ("DELETE FROM aircraft_daily_utilisation_exposures WHERE id = :id", {"id": exposure_id}),
    ]:
        _assert_sql_rejected(engine, statement, parameters)


def _controlled_pack_payload(suffix: str) -> pack_schemas.ContentRevisionCreate:
    source = pack_schemas.ContentSourceCreate(
        source_type="OEM_MANUAL",
        reference=f"AMM-{suffix}",
        source_revision="R1",
        checksum_sha256="7" * 64,
        authority="Controlled OEM",
        provenance_json={
            "document_control_record": f"DCR-{suffix}",
            "verified_by": "engineering-records",
        },
    )
    return pack_schemas.ContentRevisionCreate(
        revision_code=f"R-{suffix}",
        change_summary="Controlled source-backed acceptance revision",
        sources=[source],
        positions=[
            pack_schemas.ContentPositionCreate(
                code="ENGINE_1",
                label="Engine 1",
                position_kind="POWERPLANT",
                source_reference=source.reference,
            )
        ],
        components=[
            pack_schemas.ContentComponentCreate(
                definition_code="ENGINE_DEF",
                position_code="ENGINE_1",
                description="Controlled engine definition",
                component_class="ENGINE",
                life_limit_json={"hours": "10000.00", "cycles": 8000},
                source_reference=source.reference,
            )
        ],
        tasks=[
            pack_schemas.ContentTaskCreate(
                task_code="TASK-100",
                title="Controlled inspection",
                intervals_json={"hours": "1250.25", "cycles": 500},
                source_reference=source.reference,
                source_revision=source.source_revision,
                source_checksum_sha256=source.checksum_sha256,
            )
        ],
    )


def test_content_pack_publication_is_concurrency_safe_idempotent_and_immutable(engine, sessions):
    suffix = _suffix()
    with sessions() as db:
        _, superuser = _create_account(
            db,
            suffix,
            role=account_models.AccountRole.SUPERUSER,
            superuser=True,
        )
        db.commit()
        pack = pack_services.bootstrap_source_intake_packs(db, user=superuser)[0]
        revision = pack_services.create_revision(
            db,
            pack=pack,
            payload=_controlled_pack_payload(suffix),
            user=superuser,
        )
        revision_id = revision.id
        revision_hash = revision.content_hash
        user_id = superuser.id

    def publish() -> str:
        with sessions() as db:
            row = db.get(pack_models.AircraftContentPackRevision, revision_id)
            actor = db.get(account_models.User, user_id)
            return pack_services.publish_revision(
                db,
                revision=row,
                expected_content_hash=revision_hash,
                user=actor,
            ).id

    with ThreadPoolExecutor(max_workers=2) as pool:
        published_ids = list(pool.map(lambda _: publish(), range(2)))
    assert published_ids == [revision_id, revision_id]

    with sessions() as verify:
        revision = verify.get(pack_models.AircraftContentPackRevision, revision_id)
        assert revision.status == "PUBLISHED"
        assert revision.content_hash == revision_hash
        assert revision.sources[0].provenance_json["document_control_record"] == f"DCR-{suffix}"
        source_id = revision.sources[0].id
        position_id = revision.positions[0].id
        component_id = revision.components[0].id
        task_id = revision.tasks[0].id

    operations = [
        ("UPDATE aircraft_content_pack_revisions SET content_hash = :value WHERE id = :id", {"value": "8" * 64, "id": revision_id}),
        ("DELETE FROM aircraft_content_pack_revisions WHERE id = :id", {"id": revision_id}),
        ("UPDATE aircraft_content_pack_sources SET authority = 'Changed' WHERE id = :id", {"id": source_id}),
        ("DELETE FROM aircraft_content_pack_sources WHERE id = :id", {"id": source_id}),
        ("UPDATE aircraft_content_pack_positions SET label = 'Changed' WHERE id = :id", {"id": position_id}),
        ("DELETE FROM aircraft_content_pack_positions WHERE id = :id", {"id": position_id}),
        ("UPDATE aircraft_content_pack_components SET description = 'Changed' WHERE id = :id", {"id": component_id}),
        ("DELETE FROM aircraft_content_pack_components WHERE id = :id", {"id": component_id}),
        ("UPDATE aircraft_content_pack_tasks SET title = 'Changed' WHERE id = :id", {"id": task_id}),
        ("DELETE FROM aircraft_content_pack_tasks WHERE id = :id", {"id": task_id}),
    ]
    for statement, parameters in operations:
        _assert_sql_rejected(engine, statement, parameters)
