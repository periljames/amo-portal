from __future__ import annotations

from datetime import datetime, timedelta, timezone
from types import SimpleNamespace

import pytest
from fastapi import HTTPException

from amodb.apps.aircraft_architecture.content_packs import (
    backend_ingestion,
    governance,
    schemas,
)


CHECKSUM = "a" * 64


def source(reference: str = "PSM 1-84-7P") -> schemas.ContentSourceCreate:
    return schemas.ContentSourceCreate(
        source_type="OEM_MPD",
        reference=reference,
        source_revision="52",
        checksum_sha256=CHECKSUM,
        authority="De Havilland Canada",
    )


def test_q400_effectivity_normalizer_preserves_msn_and_service_bulletin_conditions():
    expression, issues = backend_ingestion.parse_effectivity_text(
        "MSN 4138 TO 4278 AND PRE SB84-32-69"
    )
    assert issues == []
    assert expression["operator"] == "ALL"
    assert expression["conditions"][0] == {
        "path": "aircraft.serial_number",
        "op": "between",
        "value": [4138, 4278],
        "label": "MSN",
    }
    assert expression["conditions"][1]["value"] == "PRE"
    assert expression["conditions"][1]["path"] == "configuration.sb_84_32_69"


def test_q400_effectivity_normalizer_is_fail_closed_for_unmapped_wording():
    expression, issues = backend_ingestion.parse_effectivity_text(
        "MSN 4138 TO 4278 AND (PRE SB84-32-69 OR OPTION 123)"
    )
    assert expression == {}
    assert issues[0]["code"] == "EFFECTIVITY_REVIEW_REQUIRED"


def test_position_and_component_source_binding_is_canonical_and_exact():
    controlled_source = source()
    payload = schemas.ContentRevisionCreate(
        revision_code="52",
        sources=[controlled_source],
        positions=[
            schemas.ContentPositionCreate(
                code="ENGINE_1",
                label="Engine 1",
                position_kind="POWERPLANT",
                source_reference=controlled_source.reference,
            )
        ],
        components=[
            schemas.ContentComponentCreate(
                definition_code="ENGINE_DEF",
                position_code="ENGINE_1",
                description="Engine",
                component_class="ENGINE",
                source_reference=controlled_source.reference,
            )
        ],
    )
    canonical = governance.canonicalize_entity_source_bindings(payload)
    for row in [canonical.positions[0], canonical.components[0]]:
        assert row.metadata_json["source_revision"] == "52"
        assert row.metadata_json["source_checksum_sha256"] == CHECKSUM
        assert row.metadata_json["source_binding"] == "CONTROLLED_SOURCE_TUPLE"
    governance.validate_source_backing(canonical)


def test_ambiguous_position_source_reference_requires_explicit_revision_binding():
    first = source()
    second = first.model_copy(update={"source_revision": "53", "checksum_sha256": "b" * 64})
    payload = schemas.ContentRevisionCreate(
        revision_code="53",
        sources=[first, second],
        positions=[
            schemas.ContentPositionCreate(
                code="ENGINE_1",
                label="Engine 1",
                position_kind="POWERPLANT",
                source_reference=first.reference,
            )
        ],
    )
    with pytest.raises(HTTPException, match="requires source_revision"):
        governance.canonicalize_entity_source_bindings(payload)


def test_non_universal_raw_effectivity_cannot_publish_as_empty_applicability():
    controlled_source = source()
    task = schemas.ContentTaskCreate(
        task_code="TASK-1",
        title="Controlled task",
        intervals_json={"hours": 100},
        raw_effectivity_text="PRE SB84-32-69",
        effectivity_expression_json={},
        source_reference=controlled_source.reference,
        source_revision=controlled_source.source_revision,
        source_checksum_sha256=controlled_source.checksum_sha256,
    )
    with pytest.raises(HTTPException, match="machine-readable effectivity"):
        governance._validate_effectivity(task)


def test_source_watch_metadata_marks_never_checked_and_stale_watches_overdue():
    now = datetime.now(timezone.utc)
    never = SimpleNamespace(
        id="watch-1",
        publication_id="pub-1",
        channel_type="OEM_PORTAL",
        reference="controlled-portal",
        is_active=True,
        last_checked_at=None,
        last_seen_marker=None,
        last_result=None,
        created_at=now,
        metadata_json={"check_interval_hours": 24},
    )
    never_read = governance.governed_watch_read(never, now=now)
    assert never_read.overdue is True
    assert never_read.check_interval_hours == 24

    stale = SimpleNamespace(
        **{
            **never.__dict__,
            "id": "watch-2",
            "last_checked_at": now - timedelta(hours=25),
            "metadata_json": {
                "check_interval_hours": 24,
                "last_result_code": "OK",
                "last_success_at": (now - timedelta(hours=25)).isoformat(),
                "consecutive_failures": 0,
            },
        }
    )
    stale_read = governance.governed_watch_read(stale, now=now)
    assert stale_read.overdue is True
    assert stale_read.last_result_code == "OK"
