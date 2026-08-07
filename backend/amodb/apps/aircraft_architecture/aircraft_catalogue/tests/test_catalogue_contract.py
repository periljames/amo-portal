from types import SimpleNamespace

import pytest
from fastapi import HTTPException

from amodb.apps.aircraft_architecture.aircraft_catalogue import services


def _revision(positions, components, sources):
    return SimpleNamespace(
        template=SimpleNamespace(
            code="DHC8-315",
            manufacturer="De Havilland Canada",
            model="DHC-8-315",
            variant="315",
            series="300",
        ),
        revision_code="REV-1",
        effective_date="2026-08-05",
        configuration_schema_json={"engines": 2},
        applicability_defaults_json={"authority": "KCAA"},
        positions=positions,
        component_definitions=components,
        sources=sources,
    )


def test_revision_hash_is_order_independent():
    p1 = SimpleNamespace(code="LH-ENG", label="Left engine", position_kind="ENGINE", parent_code=None, sequence_no="1", required=True, metadata_json={}, effectivity_json={})
    p2 = SimpleNamespace(code="RH-ENG", label="Right engine", position_kind="ENGINE", parent_code=None, sequence_no="2", required=True, metadata_json={}, effectivity_json={})
    source = SimpleNamespace(source_type="MPD", reference="DHC8-MPD", source_revision="76", effective_date=None, checksum_sha256=None, authority=None, provenance_json={})
    a = services.compute_revision_hash(_revision([p1, p2], [], [source]))
    b = services.compute_revision_hash(_revision([p2, p1], [], [source]))
    assert a == b
    assert len(a) == 64


def test_revision_hash_changes_when_controlled_series_changes():
    base = _revision([], [], [])
    first = services.compute_revision_hash(base)
    base.template.series = "200"
    second = services.compute_revision_hash(base)
    assert first != second


def test_published_revision_is_immutable():
    with pytest.raises(HTTPException) as exc:
        services.require_draft(SimpleNamespace(status="PUBLISHED"))
    assert exc.value.status_code == 409


def test_catalogue_write_requires_platform_superuser():
    with pytest.raises(HTTPException) as exc:
        services.require_catalogue_writer(SimpleNamespace(is_superuser=False))
    assert exc.value.status_code == 403
