from __future__ import annotations

import os
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timezone
from decimal import Decimal
from uuid import uuid4

import pytest
from fastapi import HTTPException
from sqlalchemy import create_engine, inspect, text
from sqlalchemy.exc import DBAPIError
from sqlalchemy.orm import sessionmaker

from amodb.apps.accounts import models as account_models
from amodb.apps.fleet import models as fleet_models
from amodb.apps.aircraft_architecture.aircraft_catalogue import models as catalogue_models
from amodb.apps.aircraft_architecture.aircraft_induction import models as induction_models
from amodb.apps.aircraft_architecture.aircraft_induction import schemas as induction_schemas
from amodb.apps.aircraft_architecture.aircraft_induction import services as induction_services
from amodb.apps.aircraft_architecture.content_packs import models as pack_models
from amodb.apps.aircraft_architecture.content_packs import schemas as pack_schemas
from amodb.apps.aircraft_architecture.content_packs import services as pack_services
from amodb.apps.aircraft_architecture.daily_utilisation import models as daily_models
from amodb.apps.aircraft_architecture.tenant_programmes import models as programme_models


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


def _suffix() -> str:
    return uuid4().hex[:10]


def _create_account(
    db,
    suffix: str,
    *,
    role: account_models.AccountRole = account_models.AccountRole.AMO_ADMIN,
    superuser: bool = False,
    system: bool = False,
):
    amo = account_models.AMO(
        amo_code=f"A{suffix}"[:32],
        name=f"Acceptance AMO {suffix}",
        login_slug=f"acceptance-{suffix}"[:64],
        is_active=True,
    )
    db.add(amo)
    db.flush()
    user = account_models.User(
        amo_id=amo.id,
        staff_code=f"S{suffix}"[:32],
        email=f"{suffix}@acceptance.invalid",
        first_name="Acceptance",
        last_name="User",
        full_name="Acceptance User",
        role=role,
        hashed_password="not-used",
        is_active=True,
        is_superuser=superuser,
        is_amo_admin=role == account_models.AccountRole.AMO_ADMIN,
        is_system_account=system,
    )
    db.add(user)
    db.flush()
    return amo, user


def _create_engineering_fixture(db, suffix: str):
    amo, user = _create_account(db, suffix)
    family = catalogue_models.AircraftFamily(
        code=f"FAM-{suffix}",
        manufacturer="Acceptance OEM",
        name=f"Acceptance Family {suffix}",
        category="FIXED_WING",
        status="ACTIVE",
        created_by_user_id=user.id,
    )
    db.add(family)
    db.flush()
    template = catalogue_models.AircraftTypeTemplate(
        family_id=family.id,
        code=f"TYPE-{suffix}",
        manufacturer="Acceptance OEM",
        model=f"MODEL-{suffix}",
        category="FIXED_WING",
        status="ACTIVE",
        created_by_user_id=user.id,
    )
    db.add(template)
    db.flush()
    revision = catalogue_models.AircraftTypeTemplateRevision(
        template_id=template.id,
        revision_code="R1",
        title=f"Acceptance type revision {suffix}",
        status="PUBLISHED",
        content_hash="a" * 64,
        created_by_user_id=user.id,
        published_by_user_id=user.id,
        published_at=datetime.now(timezone.utc),
    )
    db.add(revision)
    db.flush()
    db.add_all(
        [
            catalogue_models.AircraftTypeSource(
                revision_id=revision.id,
                source_type="OEM_MANUAL",
                reference=f"AMM-{suffix}",
                source_revision="R1",
                checksum_sha256="b" * 64,
                authority="Acceptance OEM",
                created_by_user_id=user.id,
            ),
            catalogue_models.AircraftTypePosition(
                revision_id=revision.id,
                code="ENGINE_1",
                label="Engine 1",
                position_kind="POWERPLANT",
                required=True,
            ),
            catalogue_models.AircraftTypeComponentDefinition(
                revision_id=revision.id,
                definition_code="ENGINE_DEF",
                position_code="ENGINE_1",
                description="Acceptance engine",
                component_class="ENGINE",
                accepted_part_numbers_json=["PN-ENGINE-1"],
                metadata_json={"utilisation_role": "ENGINE"},
            ),
        ]
    )
    programme = programme_models.TenantMaintenanceProgramme(
        amo_id=amo.id,
        code=f"MP-{suffix}",
        title=f"Acceptance programme {suffix}",
        status="ACTIVE",
        created_by_user_id=user.id,
    )
    db.add(programme)
    db.flush()
    programme_revision = programme_models.TenantProgrammeRevision(
        programme_id=programme.id,
        revision_code="R1",
        status="PUBLISHED",
        aircraft_type_revision_id=revision.id,
        source_reference=f"MPD-{suffix}",
        source_revision="R1",
        source_checksum_sha256="c" * 64,
        content_hash="d" * 64,
        created_by_user_id=user.id,
        published_by_user_id=user.id,
        published_at=datetime.now(timezone.utc),
    )
    db.add(programme_revision)
    db.flush()
    db.add(
        programme_models.TenantProgrammeTask(
            revision_id=programme_revision.id,
            task_code="TASK-100",
            title="Acceptance inspection",
            intervals_json={"hours": 100},
            effectivity_expression_json={},
            source_reference=f"MPD-{suffix}",
        )
    )
    db.commit()
    return {
        "amo_id": amo.id,
        "user_id": user.id,
        "type_revision_id": revision.id,
        "programme_revision_id": programme_revision.id,
        "source_reference": f"AMM-{suffix}",
    }


def _payload(fixture, suffix: str, *, idempotency_key: str | None = None):
    return induction_schemas.AircraftInductionCreate(
        idempotency_key=idempotency_key or f"induction-{suffix}",
        aircraft_serial_number=f"AC-{suffix}",
        registration=f"5Y-{suffix[:5]}",
        type_revision_id=fixture["type_revision_id"],
        programme_revision_id=fixture["programme_revision_id"],
        model_code="ACCEPTANCE",
        manufacturer="Acceptance OEM",
        model="Acceptance Model",
        home_base="HKJK",
        initial_airframe_hours=Decimal("1250.25"),
        initial_airframe_cycles=840,
        components=[
            induction_schemas.ComponentInductionInput(
                definition_code="ENGINE_DEF",
                position_code="ENGINE_1",
                part_number="PN-ENGINE-1",
                serial_number=f"ENG-{suffix}",
                baseline_hours=Decimal("775.50"),
                baseline_cycles=510,
                source_reference=fixture["source_reference"],
                source_revision="R1",
                source_checksum_sha256="b" * 64,
            )
        ],
    )


def test_u5_u6_database_contract_and_guards(engine):
    inspector = inspect(engine)
    tables = set(inspector.get_table_names())
    expected = {
        "aircraft_inductions",
        "aircraft_configuration_snapshots",
        "aircraft_configuration_snapshot_items",
        "aircraft_applicability_snapshots",
        "aircraft_engineering_lineage",
        "aircraft_component_utilisation_roles",
        "aircraft_exact_utilisation_states",
        "component_exact_utilisation_states",
        "aircraft_content_packs",
        "aircraft_content_pack_revisions",
        "aircraft_content_pack_sources",
        "aircraft_content_pack_positions",
        "aircraft_content_pack_components",
        "aircraft_content_pack_tasks",
    }
    assert expected <= tables
    induction_uniques = {
        constraint["name"] for constraint in inspector.get_unique_constraints("aircraft_inductions")
    }
    assert "uq_aircraft_induction_idempotency" in induction_uniques
    assert "uq_aircraft_induction_aircraft" in induction_uniques
    columns = {column["name"]: column for column in inspector.get_columns("aircraft_exact_utilisation_states")}
    assert "NUMERIC" in str(columns["total_hours"]["type"]).upper()
    assert "BIGINT" in str(columns["total_cycles"]["type"]).upper()
    with engine.connect() as connection:
        triggers = {
            row[0]
            for row in connection.execute(
                text(
                    """
                    SELECT tgname
                    FROM pg_trigger
                    WHERE NOT tgisinternal
                      AND tgrelid IN (
                        'aircraft_inductions'::regclass,
                        'aircraft_configuration_snapshots'::regclass,
                        'aircraft_engineering_lineage'::regclass,
                        'aircraft_exact_utilisation_states'::regclass,
                        'component_exact_utilisation_states'::regclass
                      )
                    """
                )
            )
        }
    assert "trg_aircraft_inductions_immutable" in triggers
    assert "trg_aircraft_configuration_snapshots_immutable" in triggers
    assert "trg_aircraft_engineering_lineage_immutable" in triggers
    assert "trg_aircraft_exact_utilisation_states_controlled" in triggers
    assert "trg_component_exact_utilisation_states_controlled" in triggers


def test_induction_authority_rejects_system_and_unapproved_roles():
    technician = account_models.User(
        amo_id="tenant-a",
        staff_code="TECH-1",
        email="tech@acceptance.invalid",
        first_name="Tech",
        last_name="User",
        full_name="Tech User",
        role=account_models.AccountRole.TECHNICIAN,
        hashed_password="not-used",
        is_active=True,
        is_system_account=False,
        is_superuser=False,
        is_amo_admin=False,
    )
    with pytest.raises(HTTPException) as denied:
        induction_services.require_human_induction_authority(technician)
    assert denied.value.status_code == 403
    technician.role = account_models.AccountRole.AMO_ADMIN
    technician.is_amo_admin = True
    technician.is_system_account = True
    with pytest.raises(HTTPException) as system_denied:
        induction_services.require_human_induction_authority(technician)
    assert system_denied.value.status_code == 403


def test_atomic_induction_idempotency_lineage_and_immutability(sessions, engine):
    suffix = _suffix()
    with sessions() as db:
        fixture = _create_engineering_fixture(db, suffix)
        user = db.get(account_models.User, fixture["user_id"])
        payload = _payload(fixture, suffix)
        induction = induction_services.induct_aircraft(db, payload=payload, user=user)
        induction_id = induction.id
        replay = induction_services.induct_aircraft(db, payload=payload, user=user)
        assert replay.id == induction_id
        changed = payload.model_copy(update={"company_name": "Changed operator"})
        with pytest.raises(HTTPException) as duplicate:
            induction_services.induct_aircraft(db, payload=changed, user=user)
        assert duplicate.value.status_code == 409

    with sessions() as verify:
        aircraft = verify.get(fleet_models.Aircraft, payload.aircraft_serial_number)
        assert aircraft is not None
        assert aircraft.amo_id == fixture["amo_id"]
        assert aircraft.total_hours == pytest.approx(1250.25)
        component = verify.query(fleet_models.AircraftComponent).filter_by(
            aircraft_serial_number=payload.aircraft_serial_number
        ).one()
        role = verify.query(induction_models.AircraftComponentUtilisationRole).filter_by(
            aircraft_component_id=component.id
        ).one()
        assert role.role == "ENGINE"
        assert role.assignment_source == "TYPE_DEFINITION"
        exact_aircraft = verify.query(daily_models.AircraftExactUtilisationState).filter_by(
            aircraft_serial_number=payload.aircraft_serial_number
        ).one()
        exact_component = verify.query(daily_models.ComponentExactUtilisationState).filter_by(
            aircraft_component_id=component.id
        ).one()
        assert exact_aircraft.total_hours == Decimal("1250.25")
        assert exact_aircraft.total_cycles == 840
        assert exact_component.total_hours == Decimal("775.50")
        row = verify.get(induction_models.AircraftInduction, induction_id)
        assert row.configuration_snapshot.snapshot_json["components"][0]["utilisation_role"] == "ENGINE"
        assert row.applicability_snapshot.task_results_json[0]["result"]["applicable"] is True
        assert row.lineage.type_content_hash == "a" * 64
        assert row.lineage.programme_content_hash == "d" * 64

    with pytest.raises(DBAPIError):
        with engine.begin() as connection:
            connection.execute(
                text("UPDATE aircraft_inductions SET request_hash = :value WHERE id = :id"),
                {"value": "e" * 64, "id": induction_id},
            )
    with pytest.raises(DBAPIError):
        with engine.begin() as connection:
            connection.execute(
                text("DELETE FROM aircraft_inductions WHERE id = :id"),
                {"id": induction_id},
            )
    with pytest.raises(DBAPIError):
        with engine.begin() as connection:
            connection.execute(
                text(
                    "UPDATE aircraft_exact_utilisation_states "
                    "SET total_hours = total_hours + 1 WHERE aircraft_serial_number = :serial"
                ),
                {"serial": payload.aircraft_serial_number},
            )
    with pytest.raises(DBAPIError):
        with engine.begin() as connection:
            connection.execute(
                text(
                    "DELETE FROM aircraft_exact_utilisation_states "
                    "WHERE aircraft_serial_number = :serial"
                ),
                {"serial": payload.aircraft_serial_number},
            )


def test_induction_is_tenant_scoped_and_rolls_back_as_one_transaction(sessions, monkeypatch):
    suffix = _suffix()
    with sessions() as db:
        fixture = _create_engineering_fixture(db, suffix)
        _, other_user = _create_account(db, f"other{suffix}")
        db.commit()
        foreign_payload = _payload(fixture, f"foreign{suffix}")
        with pytest.raises(HTTPException) as denied:
            induction_services.induct_aircraft(db, payload=foreign_payload, user=other_user)
        assert denied.value.status_code == 404
        db.rollback()

    rollback_suffix = _suffix()
    with sessions() as db:
        rollback_fixture = _create_engineering_fixture(db, rollback_suffix)
        user = db.get(account_models.User, rollback_fixture["user_id"])
        rollback_payload = _payload(rollback_fixture, rollback_suffix)
        monkeypatch.setattr(db, "commit", lambda: (_ for _ in ()).throw(RuntimeError("forced commit failure")))
        with pytest.raises(RuntimeError, match="forced commit failure"):
            induction_services.induct_aircraft(db, payload=rollback_payload, user=user)
        db.rollback()
    with sessions() as verify:
        assert verify.get(fleet_models.Aircraft, rollback_payload.aircraft_serial_number) is None
        assert verify.query(induction_models.AircraftInduction).filter_by(
            idempotency_key=rollback_payload.idempotency_key
        ).count() == 0


def test_concurrent_induction_replay_returns_one_controlled_result(sessions):
    suffix = _suffix()
    with sessions() as db:
        fixture = _create_engineering_fixture(db, suffix)
    payload = _payload(fixture, suffix, idempotency_key=f"concurrent-{suffix}")

    def execute() -> str:
        with sessions() as db:
            user = db.get(account_models.User, fixture["user_id"])
            return induction_services.induct_aircraft(db, payload=payload, user=user).id

    with ThreadPoolExecutor(max_workers=2) as pool:
        ids = list(pool.map(lambda _: execute(), range(2)))
    assert ids[0] == ids[1]
    with sessions() as verify:
        assert verify.query(induction_models.AircraftInduction).filter_by(
            amo_id=fixture["amo_id"],
            idempotency_key=payload.idempotency_key,
        ).count() == 1
        assert verify.query(fleet_models.Aircraft).filter_by(
            serial_number=payload.aircraft_serial_number
        ).count() == 1


def test_component_source_must_match_the_published_type_revision(sessions):
    suffix = _suffix()
    with sessions() as db:
        fixture = _create_engineering_fixture(db, suffix)
        user = db.get(account_models.User, fixture["user_id"])
        payload = _payload(fixture, suffix)
        invalid_component = payload.components[0].model_copy(
            update={"source_checksum_sha256": "f" * 64}
        )
        invalid = payload.model_copy(update={"components": [invalid_component]})
        with pytest.raises(HTTPException) as rejected:
            induction_services.induct_aircraft(db, payload=invalid, user=user)
        assert rejected.value.status_code == 422
        db.rollback()


def test_source_intake_packs_are_idempotent_and_publication_is_source_backed(sessions):
    suffix = _suffix()
    with sessions() as db:
        _, superuser = _create_account(
            db,
            suffix,
            role=account_models.AccountRole.SUPERUSER,
            superuser=True,
        )
        db.commit()
        first = pack_services.bootstrap_source_intake_packs(db, user=superuser)
        second = pack_services.bootstrap_source_intake_packs(db, user=superuser)
        expected_codes = {
            "CESSNA_208_SOURCE_INTAKE",
            "DHC8_SOURCE_INTAKE",
            "DHC8_100_MPD_SOURCE_INTAKE",
            "DHC8_200_MPD_SOURCE_INTAKE",
            "DHC8_300_MPD_SOURCE_INTAKE",
            "DHC8_400_MPD_SOURCE_INTAKE",
        }
        assert {row.code for row in first} == expected_codes
        assert {row.id for row in first} == {row.id for row in second}
        assert db.query(pack_models.AircraftContentPack).filter(
            pack_models.AircraftContentPack.code.in_(expected_codes)
        ).count() == len(expected_codes)
        assert {
            row.series for row in first if row.code.startswith("DHC8_") and row.series
        } == {"100", "200", "300", "400"}

        ordinary = account_models.User(
            amo_id=superuser.amo_id,
            staff_code="ORDINARY",
            email=f"ordinary-{suffix}@acceptance.invalid",
            first_name="Ordinary",
            last_name="User",
            full_name="Ordinary User",
            role=account_models.AccountRole.AMO_ADMIN,
            hashed_password="not-used",
            is_active=True,
            is_superuser=False,
            is_amo_admin=True,
            is_system_account=False,
        )
        with pytest.raises(HTTPException) as denied:
            pack_services.require_platform_human(ordinary)
        assert denied.value.status_code == 403

        pack = first[0]
        invalid = pack_schemas.ContentRevisionCreate(
            revision_code=f"INVALID-{suffix}",
            positions=[
                pack_schemas.ContentPositionCreate(
                    code="ENGINE_1",
                    label="Engine 1",
                    position_kind="POWERPLANT",
                    source_reference="AMM-MISSING",
                )
            ],
        )
        with pytest.raises(HTTPException) as source_required:
            pack_services.create_revision(db, pack=pack, payload=invalid, user=superuser)
        assert source_required.value.status_code == 422

        source = pack_schemas.ContentSourceCreate(
            source_type="OEM_MANUAL",
            reference=f"AMM-{suffix}",
            source_revision="R1",
            checksum_sha256="1" * 64,
            authority="Acceptance OEM",
        )
        valid = pack_schemas.ContentRevisionCreate(
            revision_code=f"R1-{suffix}",
            change_summary="Controlled acceptance content",
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
                    description="Acceptance engine",
                    component_class="ENGINE",
                    accepted_part_numbers_json=["PN-ENGINE-1"],
                    metadata_json={"utilisation_role": "ENGINE"},
                    source_reference=source.reference,
                )
            ],
            tasks=[
                pack_schemas.ContentTaskCreate(
                    task_code="TASK-100",
                    title="Acceptance inspection",
                    intervals_json={"hours": 100},
                    source_reference=source.reference,
                    source_revision=source.source_revision,
                    source_checksum_sha256=source.checksum_sha256,
                )
            ],
        )
        revision = pack_services.create_revision(db, pack=pack, payload=valid, user=superuser)
        with pytest.raises(HTTPException) as stale_hash:
            pack_services.publish_revision(
                db,
                revision=revision,
                expected_content_hash="0" * 64,
                user=superuser,
            )
        assert stale_hash.value.status_code == 409
        published = pack_services.publish_revision(
            db,
            revision=revision,
            expected_content_hash=revision.content_hash,
            user=superuser,
        )
        assert published.status == "PUBLISHED"
        assert published.pack.status == "ACTIVE"
        assert len(published.sources) == 1
        assert len(published.positions) == 1
        assert len(published.components) == 1
        assert len(published.tasks) == 1
