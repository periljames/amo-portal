from types import SimpleNamespace

import pytest
from fastapi import HTTPException

from amodb.apps.aircraft_architecture.content_packs import backend_hardening, schemas


def _source(*, linked: bool):
    return schemas.ContentSourceCreate(
        source_type="OEM_MPD",
        reference="PSM 1-84-7P",
        source_revision="52",
        checksum_sha256="a" * 64,
        authority="De Havilland Canada",
        publication_revision_id="publication-revision-52" if linked else None,
    )


def test_series_specific_oem_source_must_have_publication_revision_lineage():
    payload = schemas.ContentRevisionCreate(revision_code="52", sources=[_source(linked=False)])
    pack = SimpleNamespace(series="400")
    with pytest.raises(HTTPException, match="first-class publication-revision lineage"):
        backend_hardening._series_pack_source_controls(
            payload,
            pack=pack,
            for_publication=False,
        )


def test_non_series_scaffold_can_still_stage_unbound_legacy_source():
    payload = schemas.ContentRevisionCreate(revision_code="R1", sources=[_source(linked=False)])
    pack = SimpleNamespace(series=None)
    backend_hardening._series_pack_source_controls(
        payload,
        pack=pack,
        for_publication=False,
    )


def test_series_specific_publish_accepts_governed_publication_lineage():
    payload = schemas.ContentRevisionCreate(revision_code="52", sources=[_source(linked=True)])
    pack = SimpleNamespace(series="400")
    backend_hardening._series_pack_source_controls(
        payload,
        pack=pack,
        for_publication=True,
    )
