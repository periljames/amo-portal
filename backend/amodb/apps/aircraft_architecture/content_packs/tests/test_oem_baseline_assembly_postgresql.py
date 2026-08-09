from __future__ import annotations

import os
from datetime import datetime, timezone
from uuid import uuid4

import pytest
from fastapi import HTTPException
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from amodb.apps.accounts import models as account_models
from amodb.apps.aircraft_architecture.content_packs import (
    backend_assembly,
    backend_models,
    models,
    schemas,
    services,
)


DATABASE_URL = os.environ.get("POSTGRES_INTEGRATION_URL")
pytestmark = pytest.mark.skipif(
    not DATABASE_URL,
    reason="POSTGRES_INTEGRATION_URL is required for OEM assembly acceptance tests",
)


@pytest.fixture(scope="module")
def sessions():
    engine = create_engine(DATABASE_URL, future=True, pool_pre_ping=True)
    try:
        yield sessionmaker(bind=engine, autoflush=False, expire_on_commit=False)
    finally:
        engine.dispose()


def _suffix() -> str:
    return uuid4().hex[:10]


def _user(db, suffix: str):
    amo = account_models.AMO(
        amo_code=f"AS{suffix}"[:32],
        name=f"Assembly Acceptance {suffix}",
        login_slug=f"assembly-{suffix}"[:64],
        is_active=True,
    )
    db.add(amo)
    db.flush()
    user = account_models.User(
        amo_id=amo.id,
        staff_code=f"SUP-{suffix}"[:32],
        email=f"assembly-{suffix}@acceptance.invalid",
        first_name="Assembly",
        last_name="Authority",
        full_name="Assembly Authority",
        role=account_models.AccountRole.SUPERUSER,
        hashed_password="not-used",
        is_active=True,
        is_superuser=True,
        is_amo_admin=True,
        is_system_account=False,
    )
    db.add(user)
    db.flush()
    return amo, user


def _make_intake(
    db,
    *,
    amo,
    user,
    publication,
    publication_revision,
    temporary_revision,
    pack,
    normalization_hash: str,
    source_checksum: str,
    interval: str,
):
    source_revision = (
        temporary_revision.temporary_revision_code
        if temporary_revision is not None
        else publication_revision.revision_code
    )
    intake = backend_models.AircraftOemSourceIntake(
        publication_id=publication.id,
        publication_revision_id=publication_revision.id,
        temporary_revision_id=(temporary_revision.id if temporary_revision else None),
        pack_id=pack.id,
        submitted_by_amo_id=amo.id,
        source_filename=(
            f"{source_revision}.xlsx"
        ),
        storage_locator=f"controlled://assembly/{source_revision}.xlsx",
        checksum_sha256=source_checksum,
        size_bytes=1024,
        detected_profile="DHC8_400_MPD_V1",
        profile_confidence="HIGH",
        workbook_kind="OOXML",
        status="STAGED",
        source_manifest_json={"profile": "DHC8_400_MPD_V1"},
        warnings_json=[],
        validation_summary_json={},
        normalization_hash=normalization_hash,
        created_by_user_id=user.id,
    )
    db.add(intake)
    db.flush()
    task = schemas.ContentTaskCreate(
        task_code="TASK-TR-CONTROL",
        title="Controlled Q400 requirement",
        intervals_json={"hours": interval},
        source_reference=publication.publication_code,
        source_revision=source_revision,
        source_checksum_sha256=source_checksum,
    )
    row = backend_models.AircraftOemSourceIntakeRow(
        intake_id=intake.id,
        sheet_name="Section 1",
        row_number=10,
        row_kind="TASK",
        identity_key=task.task_code,
        row_hash=("1" if temporary_revision is None else "2") * 64,
        source_json={"task": task.task_code, "interval": interval},
        normalized_json=task.model_dump(mode="json"),
        status="VALID",
        issues_json=[],
        review_json={},
    )
    db.add(row)
    db.flush()
    intake.status = "VALIDATED"
    intake.validated_at = datetime.now(timezone.utc)
    intake.validation_summary_json = {
        "total_rows": 1,
        "valid_rows": 1,
        "review_required_rows": 0,
        "invalid_rows": 0,
        "ignored_rows": 0,
        "task_rows": 1,
        "resource_rows": 0,
    }
    db.flush()
    intake.status = "APPROVED"
    intake.approved_by_user_id = user.id
    intake.approved_at = datetime.now(timezone.utc)
    db.flush()
    return intake


def test_complete_baseline_assembly_requires_active_tr_and_publishes_selected_content(sessions):
    suffix = _suffix()
    with sessions() as db:
        amo, user = _user(db, suffix)
        publication = models.AircraftOemPublication(
            code=f"DHC8-400-ASSEMBLY-{suffix}",
            manufacturer="De Havilland Canada",
            family="DHC-8",
            series="400",
            publication_code=f"PSM-ASSEMBLY-{suffix}",
            title="Q400 Maintenance Planning Document",
            publication_kind="MPD",
            status="ACTIVE",
            created_by_user_id=user.id,
        )
        db.add(publication)
        db.flush()
        revision = models.AircraftOemPublicationRevision(
            publication_id=publication.id,
            revision_code="52",
            status="CURRENT",
            checksum_sha256="a" * 64,
            source_filename="base.xlsx",
            storage_locator="controlled://assembly/base.xlsx",
            submitted_by_user_id=user.id,
            submitted_by_amo_id=amo.id,
            verified_by_user_id=user.id,
            verified_at=datetime.now(timezone.utc),
        )
        db.add(revision)
        db.flush()
        temporary = models.AircraftOemTemporaryRevision(
            publication_revision_id=revision.id,
            temporary_revision_code="TR-01",
            status="ACTIVE",
            checksum_sha256="b" * 64,
            source_filename="tr-01.xlsx",
            storage_locator="controlled://assembly/tr-01.xlsx",
            submitted_by_user_id=user.id,
            submitted_by_amo_id=amo.id,
            verified_by_user_id=user.id,
            verified_at=datetime.now(timezone.utc),
        )
        db.add(temporary)
        pack = models.AircraftContentPack(
            code=f"DHC8_400_ASSEMBLY_{suffix}",
            manufacturer="De Havilland Canada",
            family="DHC-8",
            series="400",
            description="Q400 controlled assembly acceptance pack",
            status="SOURCE_INTAKE",
            created_by_user_id=user.id,
        )
        db.add(pack)
        db.flush()
        base_intake = _make_intake(
            db,
            amo=amo,
            user=user,
            publication=publication,
            publication_revision=revision,
            temporary_revision=None,
            pack=pack,
            normalization_hash="c" * 64,
            source_checksum="a" * 64,
            interval="8000",
        )
        tr_intake = _make_intake(
            db,
            amo=amo,
            user=user,
            publication=publication,
            publication_revision=revision,
            temporary_revision=temporary,
            pack=pack,
            normalization_hash="d" * 64,
            source_checksum="b" * 64,
            interval="6000",
        )
        db.commit()

        base_only = backend_assembly.OemBaselineAssemblyCreate(
            revision_code="52-BASE-ONLY",
            intake_hashes={base_intake.id: base_intake.normalization_hash},
        )
        with pytest.raises(HTTPException, match="missing active Temporary Revision intakes"):
            backend_assembly.preview_assembly(db, pack=pack, payload=base_only)

        complete_unresolved = backend_assembly.OemBaselineAssemblyCreate(
            revision_code="52-COMPLETE",
            intake_hashes={
                base_intake.id: base_intake.normalization_hash,
                tr_intake.id: tr_intake.normalization_hash,
            },
        )
        preview, _, _, _, _ = backend_assembly.preview_assembly(
            db,
            pack=pack,
            payload=complete_unresolved,
        )
        assert preview.ready is False
        assert preview.conflict_count == 1

        resolved = complete_unresolved.model_copy(
            update={
                "conflict_resolutions": [
                    backend_assembly.OemBaselineConflictResolution(
                        row_kind="TASK",
                        identity_key="TASK-TR-CONTROL",
                        selected_intake_id=tr_intake.id,
                        rationale="Active Temporary Revision supersedes the base interval for this requirement",
                    )
                ]
            }
        )
        draft = backend_assembly.create_assembled_revision(
            db,
            pack=pack,
            payload=resolved,
            user=user,
        )
        assert draft.status == "DRAFT"
        assert len(draft.sources) == 2
        assert {source.temporary_revision_id for source in draft.sources} == {None, temporary.id}
        assert len(draft.tasks) == 1
        assert draft.tasks[0].intervals_json["hours"] == "6000"
        assert draft.tasks[0].source_revision == temporary.temporary_revision_code

        published = services.publish_revision(
            db,
            revision=draft,
            expected_content_hash=draft.content_hash,
            user=user,
        )
        assert published.status == "PUBLISHED"
        assert published.pack.status == "ACTIVE"
