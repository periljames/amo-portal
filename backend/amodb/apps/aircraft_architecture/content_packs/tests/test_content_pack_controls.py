from types import SimpleNamespace

import pytest
from pydantic import ValidationError

from amodb.apps.aircraft_architecture.content_packs import schemas, services


def source(reference: str, checksum: str) -> schemas.ContentSourceCreate:
    return schemas.ContentSourceCreate(
        source_type="OEM_MANUAL",
        reference=reference,
        source_revision="R1",
        checksum_sha256=checksum,
        authority="Controlled OEM",
        provenance_json={
            "document_control_record": f"DCR-{reference}",
            "verified_by": "engineering-records",
        },
    )


def task(code: str, source_row: schemas.ContentSourceCreate) -> schemas.ContentTaskCreate:
    return schemas.ContentTaskCreate(
        task_code=code,
        title=f"Controlled inspection {code}",
        intervals_json={"threshold": {"hours": "1250.25"}, "repeat": {"cycles": 500}},
        source_reference=source_row.reference,
        source_revision=source_row.source_revision,
        source_checksum_sha256=source_row.checksum_sha256,
    )


def test_omitted_provenance_is_canonicalized_from_the_complete_controlled_tuple():
    row = schemas.ContentSourceCreate(
        source_type="OEM_MANUAL",
        reference="AMM-208",
        source_revision="R12",
        checksum_sha256="a" * 64,
        authority="Controlled OEM",
    )
    assert row.provenance_json == {
        "authority": "Controlled OEM",
        "source_reference": "AMM-208",
        "source_revision": "R12",
        "checksum_sha256": "a" * 64,
        "provenance_basis": "CONTROLLED_SOURCE_TUPLE",
    }


def test_explicitly_empty_provenance_is_rejected():
    with pytest.raises(ValidationError, match="provenance"):
        schemas.ContentSourceCreate(
            source_type="OEM_MANUAL",
            reference="AMM-208",
            source_revision="R12",
            checksum_sha256="a" * 64,
            authority="Controlled OEM",
            provenance_json={},
        )


@pytest.mark.parametrize(
    "intervals",
    [
        {},
        {"unsupported": 10},
        {"hours": 1250.25},
        {"cycles": 500.0},
        {"threshold": {}},
        {"repeat": {"hours": 100.5}},
        {"repeat": {"unsupported": 1}},
        {"days": 0},
    ],
)
def test_unsupported_empty_or_inexact_intervals_are_rejected(intervals):
    controlled_source = source("AMM-208", "b" * 64)
    with pytest.raises(ValidationError):
        schemas.ContentTaskCreate(
            task_code="TASK-100",
            title="Controlled inspection",
            intervals_json=intervals,
            source_reference=controlled_source.reference,
            source_revision=controlled_source.source_revision,
            source_checksum_sha256=controlled_source.checksum_sha256,
        )


def test_exact_decimal_strings_and_integer_cycles_are_preserved():
    controlled_source = source("AMM-208", "c" * 64)
    row = task("TASK-EXACT", controlled_source)
    assert row.intervals_json["threshold"]["hours"] == "1250.25"
    assert row.intervals_json["repeat"]["cycles"] == 500


def test_inexact_life_limit_values_are_rejected():
    with pytest.raises(ValidationError, match="IEEE-754"):
        schemas.ContentComponentCreate(
            definition_code="ENGINE_DEF",
            position_code="ENGINE_1",
            description="Controlled engine definition",
            component_class="ENGINE",
            life_limit_json={"hours": 1000.5},
            source_reference="AMM-208",
        )


@pytest.mark.parametrize("task_code,title", [("TBD", "Inspection"), ("TASK-1", "Placeholder task")])
def test_fabricated_placeholder_tasks_are_rejected(task_code, title):
    controlled_source = source("AMM-208", "d" * 64)
    with pytest.raises(ValidationError, match="placeholder"):
        schemas.ContentTaskCreate(
            task_code=task_code,
            title=title,
            intervals_json={"hours": 100},
            source_reference=controlled_source.reference,
            source_revision=controlled_source.source_revision,
            source_checksum_sha256=controlled_source.checksum_sha256,
        )


def test_duplicate_controlled_identities_are_rejected_before_persistence():
    controlled_source = source("AMM-208", "e" * 64)
    with pytest.raises(ValidationError, match="Duplicate controlled task identity"):
        schemas.ContentRevisionCreate(
            revision_code="R1",
            sources=[controlled_source],
            tasks=[task("TASK-1", controlled_source), task("TASK-1", controlled_source)],
        )


def test_revision_hash_is_independent_of_input_collection_order():
    source_a = source("AMM-A", "1" * 64)
    source_b = source("AMM-B", "2" * 64)
    position_a = schemas.ContentPositionCreate(
        code="ENGINE_1",
        label="Engine 1",
        position_kind="POWERPLANT",
        source_reference=source_a.reference,
    )
    position_b = schemas.ContentPositionCreate(
        code="PROP_1",
        label="Propeller 1",
        position_kind="PROPELLER",
        source_reference=source_b.reference,
    )
    component_a = schemas.ContentComponentCreate(
        definition_code="ENGINE_DEF",
        position_code=position_a.code,
        description="Controlled engine",
        component_class="ENGINE",
        source_reference=source_a.reference,
    )
    component_b = schemas.ContentComponentCreate(
        definition_code="PROP_DEF",
        position_code=position_b.code,
        description="Controlled propeller",
        component_class="PROPELLER",
        source_reference=source_b.reference,
    )
    task_a = task("TASK-A", source_a)
    task_b = task("TASK-B", source_b)
    first = schemas.ContentRevisionCreate(
        revision_code="R1",
        sources=[source_a, source_b],
        positions=[position_a, position_b],
        components=[component_a, component_b],
        tasks=[task_a, task_b],
    )
    second = schemas.ContentRevisionCreate(
        revision_code="R1",
        sources=[source_b, source_a],
        positions=[position_b, position_a],
        components=[component_b, component_a],
        tasks=[task_b, task_a],
    )
    pack = SimpleNamespace(code="CONTROLLED_PACK")
    assert services.revision_hash(pack, first) == services.revision_hash(pack, second)
