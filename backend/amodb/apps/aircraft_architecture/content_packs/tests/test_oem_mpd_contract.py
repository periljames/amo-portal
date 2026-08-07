from types import SimpleNamespace

import pytest
from fastapi import HTTPException
from pydantic import ValidationError

from amodb.apps.aircraft_architecture.content_packs import schemas, services
from amodb.apps.aircraft_architecture.effectivity.evaluator import evaluate_expression


CHECKSUM = "a" * 64


def controlled_source(reference: str = "PSM 1-84-7P:CH01") -> schemas.ContentSourceCreate:
    return schemas.ContentSourceCreate(
        source_type="OEM_MPD",
        reference=reference,
        source_revision="52",
        effective_date="2022-03-05",
        checksum_sha256=CHECKSUM,
        authority="De Havilland Canada",
        provenance_json={
            "publication": "PSM 1-84-7P",
            "source_file": "CH01.pdf",
            "controlled_copy": True,
        },
    )


def task_with_interval(intervals: dict) -> schemas.ContentTaskCreate:
    source = controlled_source()
    return schemas.ContentTaskCreate(
        task_code="321100-207-A-02",
        title="Restoration of the Main Landing Gear Stabilizer Brace",
        ata_chapter="32",
        programme_section="SYSTEMS_POWERPLANT",
        task_type="RST",
        intervals_json=intervals,
        raw_interval_text="25000 FC or 12 YR",
        raw_effectivity_text="Pre SB84-32-69 and Pre SB84-32-76",
        effectivity_expression_json={
            "operator": "ALL",
            "conditions": [
                {"path": "aircraft.serial_number", "op": "between", "value": [4138, 4278]},
                {"path": "configuration.sb_84_32_69", "op": "eq", "value": "PRE"},
                {"path": "configuration.sb_84_32_76", "op": "eq", "value": "PRE"},
            ],
        },
        source_requirements_json=[
            {
                "authority": "MRB",
                "task_number": "321100-207",
                "configuration": "A",
                "fec": [6, 9],
            }
        ],
        task_card_number="000-32-730-720",
        amm_reference="32-11-16-900-801",
        skill_code="Mech",
        labour_hours="1.75",
        number_of_persons=1,
        source_page_ref="1-32 Page 8",
        source_reference=source.reference,
        source_revision=source.source_revision,
        source_checksum_sha256=source.checksum_sha256,
    )


def test_q400_whichever_first_interval_is_preserved():
    row = task_with_interval(
        {
            "schema": "MPD_INTERVAL_V1",
            "groups": [
                {
                    "phase": "INTERVAL",
                    "mode": "WHICHEVER_FIRST",
                    "limits": [
                        {"counter": "FC", "value": 25000},
                        {"counter": "YR", "value": 12},
                    ],
                }
            ],
        }
    )
    assert row.intervals_json["groups"][0]["mode"] == "WHICHEVER_FIRST"
    assert row.intervals_json["groups"][0]["limits"][1] == {"counter": "YR", "value": 12}
    applicability = evaluate_expression(
        row.effectivity_expression_json,
        {
            "aircraft": {"serial_number": 4200},
            "configuration": {"sb_84_32_69": "PRE", "sb_84_32_76": "PRE"},
        },
    )
    assert applicability.applicable is True


def test_q400_structural_threshold_repeat_cut_in_and_repeat_are_first_class():
    row = task_with_interval(
        {
            "schema": "MPD_INTERVAL_V1",
            "groups": [
                {
                    "phase": "THRESHOLD",
                    "mode": "SINGLE",
                    "limits": [{"counter": "FC", "value": 40000}],
                },
                {
                    "phase": "REPEAT_CUT_IN",
                    "mode": "SINGLE",
                    "limits": [{"counter": "FC", "value": 80000}],
                },
                {
                    "phase": "REPEAT",
                    "mode": "SINGLE",
                    "limits": [{"counter": "FC", "value": 34870}],
                },
            ],
        }
    )
    assert [group["phase"] for group in row.intervals_json["groups"]] == [
        "THRESHOLD",
        "REPEAT_CUT_IN",
        "REPEAT",
    ]


def test_engine_apu_and_custom_counters_can_be_modelled_without_floats():
    source = controlled_source()
    row = schemas.ContentTaskCreate(
        task_code="POWERPLANT-CONTROL",
        title="Controlled powerplant requirement",
        intervals_json={
            "schema": "MPD_INTERVAL_V1",
            "groups": [
                {
                    "phase": "THRESHOLD",
                    "mode": "ALL_DUE",
                    "limits": [
                        {"counter": "EH", "value": 4000},
                        {"counter": "APUH", "value": "1250.25"},
                        {
                            "counter": "CUSTOM",
                            "custom_counter": "UNIT_LANDINGS",
                            "value": 10700,
                        },
                    ],
                }
            ],
        },
        source_reference=source.reference,
        source_revision=source.source_revision,
        source_checksum_sha256=source.checksum_sha256,
    )
    assert row.intervals_json["groups"][0]["limits"][1]["value"] == "1250.25"


def test_opportunity_requirement_is_not_forced_into_a_fake_numeric_interval():
    source = controlled_source()
    row = schemas.ContentTaskCreate(
        task_code="491000-204-A-00",
        title="Opportunity maintenance requirement",
        intervals_json={
            "schema": "MPD_INTERVAL_V1",
            "groups": [
                {
                    "phase": "INTERVAL",
                    "mode": "OPPORTUNITY",
                    "reference": "MRB SYS Note 5",
                }
            ],
        },
        raw_interval_text="OPPORTUNITY - MRB SYS Note 5",
        source_reference=source.reference,
        source_revision=source.source_revision,
        source_checksum_sha256=source.checksum_sha256,
    )
    assert row.intervals_json["groups"][0]["mode"] == "OPPORTUNITY"


@pytest.mark.parametrize(
    "intervals",
    [
        {
            "schema": "MPD_INTERVAL_V1",
            "groups": [
                {
                    "phase": "INTERVAL",
                    "mode": "SINGLE",
                    "limits": [{"counter": "FH", "value": 8000.5}],
                }
            ],
        },
        {
            "schema": "MPD_INTERVAL_V1",
            "groups": [
                {
                    "phase": "INTERVAL",
                    "mode": "SINGLE",
                    "limits": [{"counter": "BOGUS", "value": 10}],
                }
            ],
        },
        {
            "schema": "MPD_INTERVAL_V1",
            "groups": [{"phase": "INTERVAL", "mode": "OPPORTUNITY"}],
        },
    ],
)
def test_invalid_mpd_intervals_are_rejected(intervals):
    with pytest.raises(ValidationError):
        task_with_interval(intervals)


def test_q400_task_metadata_keeps_source_authority_and_tbd_labour_explicit():
    source = controlled_source()
    row = schemas.ContentTaskCreate(
        task_code="212500-102-A-00",
        title="General Visual Inspection of the Avionics Cooling Duct System",
        task_type="GVI",
        intervals_json={
            "schema": "MPD_INTERVAL_V1",
            "groups": [
                {
                    "phase": "INTERVAL",
                    "mode": "SINGLE",
                    "limits": [{"counter": "FH", "value": 24545}],
                }
            ],
        },
        source_requirements_json=[
            {"authority": "CMR", "task_number": "212500-102", "classification": "*"}
        ],
        labour_hours="TBD",
        source_reference=source.reference,
        source_revision=source.source_revision,
        source_checksum_sha256=source.checksum_sha256,
    )
    assert row.labour_hours == "TBD"
    assert row.source_requirements_json[0]["authority"] == "CMR"


def test_publication_revision_requires_a_controlled_source_locator():
    with pytest.raises(ValidationError, match="controlled source"):
        schemas.OemPublicationRevisionCreate(
            revision_code="52",
            checksum_sha256=CHECKSUM,
        )


def test_amoadmin_can_submit_source_content_but_cannot_publish_global_baseline():
    admin = SimpleNamespace(
        is_active=True,
        is_system_account=False,
        is_superuser=False,
        is_amo_admin=True,
    )
    services.require_source_contributor(admin)
    with pytest.raises(HTTPException, match="superuser"):
        services.require_platform_human(admin)


def test_system_account_cannot_contribute_oem_source_data():
    system = SimpleNamespace(
        is_active=True,
        is_system_account=True,
        is_superuser=True,
        is_amo_admin=True,
    )
    with pytest.raises(HTTPException, match="human"):
        services.require_source_contributor(system)


def test_content_hash_includes_controlled_supporting_resources():
    source = controlled_source()
    pack = SimpleNamespace(code="DHC8_400_MPD_SOURCE_INTAKE")
    base = schemas.ContentRevisionCreate(revision_code="52", sources=[source])
    with_resource = schemas.ContentRevisionCreate(
        revision_code="52",
        sources=[source],
        resources=[
            schemas.ContentResourceCreate(
                resource_kind="ACCESS_PANEL",
                resource_code="111AT",
                title="Radome access panel",
                payload_json={"open_hours": "0.23", "close_hours": "0.42", "persons": 1},
                source_reference=source.reference,
                source_revision=source.source_revision,
                source_checksum_sha256=source.checksum_sha256,
                source_page_ref="Appendix A Page 2",
            )
        ],
    )
    assert services.revision_hash(pack, base) != services.revision_hash(pack, with_resource)
