from __future__ import annotations

import os
from datetime import date, datetime, timezone
from uuid import uuid4

import pytest
from fastapi import HTTPException
from sqlalchemy import create_engine, text
from sqlalchemy.exc import DBAPIError
from sqlalchemy.orm import sessionmaker

from amodb.apps.accounts import models as account_models
from amodb.apps.aircraft_architecture.aircraft_catalogue import schemas as catalogue_schemas
from amodb.apps.aircraft_architecture.aircraft_catalogue import services as catalogue_services
from amodb.apps.aircraft_architecture.content_packs import models as content_models
from amodb.apps.aircraft_architecture.content_packs import schemas as content_schemas
from amodb.apps.aircraft_architecture.content_packs import services as content_services
from amodb.apps.aircraft_architecture.tenant_programmes import router, schemas


DATABASE_URL = os.environ.get("POSTGRES_INTEGRATION_URL")
pytestmark = pytest.mark.skipif(
    not DATABASE_URL,
    reason="POSTGRES_INTEGRATION_URL is required for tenant AMP PostgreSQL acceptance tests",
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
    return uuid4().hex[:8].upper()


def _interval(fh: str, months: str) -> dict:
    return {
        "schema": "MPD_INTERVAL_V1",
        "groups": [
            {
                "phase": "INTERVAL",
                "mode": "WHICHEVER_FIRST",
                "limits": [
                    {"counter": "FH", "value": fh},
                    {"counter": "MO", "value": months},
                ],
            }
        ],
    }


def _users(db, suffix: str):
    amo = account_models.AMO(
        amo_code=f"A{suffix}"[:32],
        name=f"AMP Overlay Acceptance {suffix}",
        login_slug=f"amp-overlay-{suffix.lower()}"[:64],
        is_active=True,
    )
    db.add(amo)
    db.flush()
    superuser = account_models.User(
        amo_id=amo.id,
        staff_code=f"SUP-{suffix}"[:32],
        email=f"sup-{suffix.lower()}@acceptance.invalid",
        first_name="Platform",
        last_name="Authority",
        full_name="Platform Authority",
        role=account_models.AccountRole.SUPERUSER,
        hashed_password="not-used",
        is_active=True,
        is_superuser=True,
        is_amo_admin=True,
        is_system_account=False,
    )
    planner = account_models.User(
        amo_id=amo.id,
        staff_code=f"PLN-{suffix}"[:32],
        email=f"planner-{suffix.lower()}@acceptance.invalid",
        first_name="Planning",
        last_name="Engineer",
        full_name="Planning Engineer",
        role=account_models.AccountRole.PLANNING_ENGINEER,
        hashed_password="not-used",
        is_active=True,
        is_superuser=False,
        is_amo_admin=False,
        is_system_account=False,
    )
    db.add_all([superuser, planner])
    db.commit()
    return amo, superuser, planner


def _controlled_fixture(db, suffix: str):
    amo, superuser, planner = _users(db, suffix)
    manufacturer = f"De Havilland Canada AMP {suffix}"
    family_code = f"D8A{suffix}"[:40]

    family = catalogue_services.create_family(
        db,
        catalogue_schemas.FamilyCreate(
            code=family_code,
            manufacturer=manufacturer,
            name=family_code,
            category="FIXED_WING",
            description="Acceptance Dash 8 family",
        ),
        superuser.id,
    )
    template = catalogue_services.create_template(
        db,
        catalogue_schemas.TemplateCreate(
            family_id=family.id,
            code=f"DHC8-202-{suffix}"[:50],
            manufacturer=manufacturer,
            model="DHC-8-202",
            variant="202",
            series="200",
            category="FIXED_WING",
        ),
        superuser.id,
    )
    type_revision = catalogue_services.create_revision(
        db,
        template.id,
        catalogue_schemas.RevisionCreate(
            revision_code="TYPE-1",
            title="DHC-8-202 controlled type revision",
            effective_date=date.today(),
            configuration_schema_json={"schema": "AIRCRAFT_CONFIGURATION_V1"},
            applicability_defaults_json={"series": "200"},
        ),
        superuser.id,
    )
    catalogue_services.add_position(
        db,
        type_revision.id,
        catalogue_schemas.PositionCreate(
            code="AIRFRAME",
            label="Airframe",
            position_kind="AIRFRAME",
            required=True,
        ),
    )
    catalogue_services.add_source(
        db,
        type_revision.id,
        catalogue_schemas.SourceCreate(
            source_type="TC_DATA",
            reference=f"TYPE-SOURCE-{suffix}",
            source_revision="1",
            checksum_sha256="a" * 64,
            authority="OEM",
            provenance_json={"basis": "acceptance fixture"},
        ),
        superuser.id,
    )
    type_revision = catalogue_services.publish_revision(
        db,
        type_revision.id,
        superuser.id,
        expected_hash=None,
    )

    publication = content_models.AircraftOemPublication(
        code=f"MPD-{suffix}",
        manufacturer=manufacturer,
        family=family_code,
        series="200",
        publication_code=f"PSM-{suffix}",
        title="Acceptance Series 200 MPD",
        publication_kind="MPD",
        status="ACTIVE",
        created_by_user_id=superuser.id,
    )
    db.add(publication)
    db.flush()
    publication_revision = content_models.AircraftOemPublicationRevision(
        publication_id=publication.id,
        revision_code="27",
        status="CURRENT",
        issue_date=date.today(),
        effective_date=date.today(),
        checksum_sha256="b" * 64,
        source_filename=f"mpd-{suffix}.xlsx",
        storage_locator=f"controlled://acceptance/{suffix}/mpd.xlsx",
        submitted_by_amo_id=amo.id,
        submitted_by_user_id=superuser.id,
        verified_by_user_id=superuser.id,
        verified_at=datetime.now(timezone.utc),
    )
    db.add(publication_revision)
    db.commit()

    pack = content_models.AircraftContentPack(
        code=f"AMP_TEST_{suffix}",
        manufacturer=manufacturer,
        family=family_code,
        series="200",
        description="Acceptance OEM baseline",
        status="SOURCE_INTAKE",
        created_by_user_id=superuser.id,
    )
    db.add(pack)
    db.commit()
    db.refresh(pack)

    source = content_schemas.ContentSourceCreate(
        source_type="MPD",
        reference=f"PSM-{suffix}",
        source_revision="27",
        effective_date=date.today(),
        checksum_sha256="b" * 64,
        authority="OEM",
        provenance_json={"publication": publication.publication_code, "controlled": True},
        publication_revision_id=publication_revision.id,
        document_locator=publication_revision.storage_locator,
    )
    series_200_effectivity = {"path": "aircraft.series", "op": "eq", "value": "200"}
    tasks = [
        content_schemas.ContentTaskCreate(
            task_code=f"{suffix}-A",
            title="Flight control inspection",
            ata_chapter="27",
            programme_section="SYSTEMS",
            task_type="INSP",
            intervals_json=_interval("600", "12"),
            raw_interval_text="600 FH OR 12 MO",
            effectivity_expression_json=series_200_effectivity,
            raw_effectivity_text="ALL SERIES 200",
            source_requirements_json=[{"authority": "MRB"}],
            source_reference=source.reference,
            source_revision=source.source_revision,
            source_checksum_sha256=source.checksum_sha256,
        ),
        content_schemas.ContentTaskCreate(
            task_code=f"{suffix}-B",
            title="Mandatory limitation inspection",
            ata_chapter="32",
            programme_section="ALI",
            task_type="INSP",
            intervals_json=_interval("1200", "24"),
            raw_interval_text="1200 FH OR 24 MO",
            effectivity_expression_json=series_200_effectivity,
            raw_effectivity_text="ALL SERIES 200",
            source_requirements_json=[{"authority": "ALI"}],
            source_reference=source.reference,
            source_revision=source.source_revision,
            source_checksum_sha256=source.checksum_sha256,
        ),
    ]
    content_revision = content_services.create_revision(
        db,
        pack=pack,
        payload=content_schemas.ContentRevisionCreate(
            revision_code="OEM-27",
            change_summary="Acceptance OEM baseline",
            sources=[source],
            tasks=tasks,
        ),
        user=superuser,
    )
    content_revision = content_services.publish_revision(
        db,
        revision=content_revision,
        expected_content_hash=content_revision.content_hash,
        user=superuser,
    )

    programme = router.create_programme(
        schemas.ProgrammeCreate(
            code=f"AMP-{suffix}",
            title="Acceptance Approved Maintenance Programme",
            authority="KCAA",
        ),
        db=db,
        user=planner,
    )
    return {
        "amo": amo,
        "superuser": superuser,
        "planner": planner,
        "type_revision": type_revision,
        "content_revision": content_revision,
        "programme": programme,
    }


def test_oem_backed_amp_blocks_relaxation_publishes_tightening_and_resolves_aircraft_defaults(sessions, engine):
    suffix = _suffix()
    with sessions() as db:
        fixture = _controlled_fixture(db, suffix)
        draft = router.create_revision_from_oem(
            fixture["programme"].id,
            schemas.CreateFromOemRequest(
                revision_code="AMP-01",
                aircraft_type_revision_id=fixture["type_revision"].id,
                base_content_pack_revision_id=fixture["content_revision"].id,
            ),
            db=db,
            user=fixture["planner"],
        )
        assert draft.status == "DRAFT"
        assert draft.base_content_pack_revision_id == fixture["content_revision"].id
        assert len(draft.tasks) == 2
        assert {row.decision for row in draft.tasks} == {"INHERIT"}

        editable = next(row for row in draft.tasks if row.ata_chapter == "27")
        with pytest.raises(HTTPException) as exc_info:
            router.update_task_decision(
                draft.id,
                editable.id,
                schemas.TaskDecisionUpdate(
                    decision="TIGHTEN",
                    intervals_json=_interval("500", "15"),
                    justification="Attempt to hide a relaxed calendar limit behind a tighter FH limit",
                ),
                db=db,
                user=fixture["planner"],
            )
        assert exc_info.value.status_code == 409
        assert exc_info.value.detail["code"] == "AMP_EXCEEDS_OEM_LIMIT"
        db.rollback()

        draft = router._revision(db, draft.id, fixture["planner"])
        editable = next(row for row in draft.tasks if row.ata_chapter == "27")
        router.update_task_decision(
            draft.id,
            editable.id,
            schemas.TaskDecisionUpdate(
                decision="TIGHTEN",
                intervals_json=_interval("500", "10"),
                justification="Tenant planning policy adopts a more restrictive recurring interval",
            ),
            db=db,
            user=fixture["planner"],
        )

        router.add_operator_task(
            draft.id,
            schemas.OperatorTaskCreate(
                task_code=f"AMP-{suffix}-ADD",
                title="Operator corrosion review",
                ata_chapter="53",
                intervals_json={
                    "schema": "MPD_INTERVAL_V1",
                    "groups": [{"phase": "INTERVAL", "mode": "SINGLE", "limits": [{"counter": "MO", "value": "6"}]}],
                },
                effectivity_expression_json={},
                source_reference="Tenant AMP engineering decision",
                justification="Operator-specific environmental exposure control",
            ),
            db=db,
            user=fixture["planner"],
        )

        validation = router.validate_revision(draft.id, db=db, user=fixture["planner"])
        assert validation["status"] == "PASS"
        assert validation["blocking_count"] == 0
        assert validation["summary"]["tightened_count"] == 1
        assert validation["summary"]["operator_added_count"] == 1

        current = router._revision(db, draft.id, fixture["planner"])
        published = router.publish_revision(
            current.id,
            schemas.PublishRequest(
                expected_content_hash=current.content_hash,
                approval_reference=f"KCAA-AMP-{suffix}",
            ),
            db=db,
            user=fixture["planner"],
        )
        assert published.status == "PUBLISHED"
        assert published.approval_reference == f"KCAA-AMP-{suffix}"
        assert published.source_currentness_at_approval == "CURRENT"

        defaults = router.aircraft_defaults(
            fixture["type_revision"].id,
            db=db,
            user=fixture["planner"],
        )
        assert defaults["state"] == "RESOLVED"
        assert defaults["selected_programme_revision_id"] == published.id
        assert defaults["oem"]["series"] == "200"
        assert defaults["requires_series_confirmation"] is False
        controlled_task_id = next(row.id for row in published.tasks if row.decision == "TIGHTEN")

    with pytest.raises(DBAPIError):
        with engine.begin() as connection:
            connection.execute(
                text("UPDATE tenant_maintenance_programme_tasks SET title = 'tampered' WHERE id = :id"),
                {"id": controlled_task_id},
            )


def test_published_amp_revision_cannot_be_repointed_to_another_oem_baseline(sessions, engine):
    suffix = _suffix()
    with sessions() as db:
        fixture = _controlled_fixture(db, suffix)
        draft = router.create_revision_from_oem(
            fixture["programme"].id,
            schemas.CreateFromOemRequest(
                revision_code="AMP-01",
                aircraft_type_revision_id=fixture["type_revision"].id,
                base_content_pack_revision_id=fixture["content_revision"].id,
            ),
            db=db,
            user=fixture["planner"],
        )
        validation = router.validate_revision(draft.id, db=db, user=fixture["planner"])
        assert validation["status"] == "PASS"
        draft = router._revision(db, draft.id, fixture["planner"])
        published = router.publish_revision(
            draft.id,
            schemas.PublishRequest(
                expected_content_hash=draft.content_hash,
                approval_reference=f"APPROVAL-{suffix}",
            ),
            db=db,
            user=fixture["planner"],
        )
        published_id = published.id

    with pytest.raises(DBAPIError):
        with engine.begin() as connection:
            connection.execute(
                text(
                    "UPDATE tenant_maintenance_programme_revisions "
                    "SET base_content_pack_revision_id = NULL WHERE id = :id"
                ),
                {"id": published_id},
            )
