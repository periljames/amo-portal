"""Immutable OCTM source-scan classification and tenant/page binding controls."""
from types import SimpleNamespace
from unittest.mock import MagicMock

import pytest
from fastapi import HTTPException

from amodb.apps.reliability.octm_source_assets import (
    PREFIX,
    _checked_asset,
    _source_type,
    validate_source_reference,
)


@pytest.mark.parametrize(
    ("binary", "expected"),
    [
        (b"%PDF-1.7\n1 0 obj\n", ("application/pdf", ".pdf")),
        (b"\x89PNG\r\n\x1a\n", ("image/png", ".png")),
        (b"\xff\xd8\xff\xe0\x00\x10", ("image/jpeg", ".jpg")),
    ],
)
def test_original_scan_supported_only_for_signed_pdf_or_images(binary, expected):
    assert _source_type(binary) == expected


@pytest.mark.parametrize("binary", [b"<html>unsafe</html>", b"MZ\x90\x00", b"", b"GIF89a"])
def test_source_scan_rejects_unrecognized_or_active_file_formats(binary):
    with pytest.raises(HTTPException) as exc:
        _source_type(binary)
    assert exc.value.status_code == 422


def test_legacy_reference_remains_descriptive_and_nonblocking():
    db = MagicMock()
    validate_source_reference(db, "tenant-a", "5Y-SLC", "SL-MCM1-012", "TECH-RECORDS-012")
    db.query.assert_not_called()


def test_retained_reference_requires_exact_tenant_aircraft_and_page():
    doc_id = "7a55e6a2-81b4-4555-8a94-3cc8b0828f20"
    db = MagicMock()
    db.query.return_value.filter.return_value.first.return_value = SimpleNamespace(
        amo_id="tenant-a", id=doc_id, aircraft_serial_number="5Y-SLC",
        techsheet_ref="SL-MCM1-012",
    )
    validate_source_reference(db, "tenant-a", "5Y-SLC", "SL-MCM1-012", PREFIX + doc_id)
    for aircraft, page in [
        ("5Y-SLA", "SL-MCM1-012"),
        ("5Y-SLC", "SL-MCM1-013"),
    ]:
        with pytest.raises(HTTPException) as exc:
            validate_source_reference(db, "tenant-a", aircraft, page, PREFIX + doc_id)
        assert exc.value.status_code == 422
    db.query.return_value.filter.return_value.first.return_value = None
    with pytest.raises(HTTPException) as exc:
        validate_source_reference(db, "tenant-b", "5Y-SLC", "SL-MCM1-012", PREFIX + doc_id)
    assert exc.value.status_code == 404


def test_malformed_source_asset_ref_cannot_access_file():
    with pytest.raises(HTTPException) as exc:
        _checked_asset(MagicMock(), "tenant-a", "not-a-uuid")
    assert exc.value.status_code == 404
