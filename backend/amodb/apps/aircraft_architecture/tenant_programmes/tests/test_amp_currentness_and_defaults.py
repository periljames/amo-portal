from __future__ import annotations

from datetime import datetime, timezone

from amodb.apps.aircraft_architecture.content_packs import models as content_models
from amodb.apps.aircraft_architecture.tenant_programmes import overlay_router, router, schemas

from .test_amp_overlay_postgresql import _controlled_fixture, _suffix, engine, sessions  # noqa: F401


def test_oem_source_change_blocks_amp_validation(sessions):
    suffix = _suffix()
    with sessions() as db:
        fixture = _controlled_fixture(db, suffix)
        draft = router.create_revision_from_oem(
            fixture["programme"].id,
            schemas.CreateFromOemRequest(
                revision_code="AMP-CURRENTNESS",
                aircraft_type_revision_id=fixture["type_revision"].id,
                base_content_pack_revision_id=fixture["content_revision"].id,
            ),
            db=db,
            user=fixture["planner"],
        )
        source = fixture["content_revision"].sources[0]
        publication_revision = db.get(content_models.AircraftOemPublicationRevision, source.publication_revision_id)
        assert publication_revision is not None

        db.add(
            content_models.AircraftOemSourceWatch(
                publication_id=publication_revision.publication_id,
                channel_type="OEM_PORTAL",
                reference=f"controlled-watch-{suffix}",
                is_active=True,
                last_checked_at=datetime.now(timezone.utc),
                last_seen_marker="revision-28",
                last_result="A newer OEM source marker was detected",
                metadata_json={
                    "last_result_code": "CHANGE_DETECTED",
                    "check_interval_hours": 24,
                    "consecutive_failures": 0,
                },
                created_by_user_id=fixture["superuser"].id,
            )
        )
        db.commit()

        result = router.validate_revision(draft.id, db=db, user=fixture["planner"])
        assert result["status"] == "BLOCKED"
        assert any(issue["code"] == "OEM_CURRENTNESS_REVIEW_REQUIRED" for issue in result["issues"])
        assert result["summary"]["oem_currentness_at_validation"] == "REVIEW_REQUIRED"


def test_aircraft_setup_defaults_prefill_exact_published_amp(sessions):
    suffix = _suffix()
    with sessions() as db:
        fixture = _controlled_fixture(db, suffix)
        draft = router.create_revision_from_oem(
            fixture["programme"].id,
            schemas.CreateFromOemRequest(
                revision_code="AMP-PREFILL",
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
                approval_reference=f"APPROVED-{suffix}",
            ),
            db=db,
            user=fixture["planner"],
        )

        defaults = overlay_router.aircraft_setup_defaults(
            fixture["type_revision"].id,
            db=db,
            user=fixture["planner"],
        )
        assert defaults["state"] == "RESOLVED"
        assert defaults["requires_series_confirmation"] is False
        assert defaults["selected_programme_revision_id"] == published.id
        assert defaults["selected_oem_baseline_revision_id"] == fixture["content_revision"].id
        assert defaults["prefill"] == {
            "type_revision_id": fixture["type_revision"].id,
            "programme_revision_id": published.id,
            "series": "200",
            "oem_baseline_revision_id": fixture["content_revision"].id,
        }
