from __future__ import annotations

from datetime import date, timedelta
from types import SimpleNamespace

import pytest
from fastapi import HTTPException

from amodb.apps.doc_control import workspace_external_router as external
from amodb.apps.doc_control import workspace_schemas as schemas


def _source(status: str = "ACTIVE"):
    return SimpleNamespace(status=status)


def _receipt(**values):
    base = {
        "revision_label": "Revision 12",
        "currency_status": "UNVERIFIED",
        "applicability_status": "PENDING",
        "evidence": [],
    }
    base.update(values)
    return schemas.ExternalRevisionReceiptCreate(**base)


def test_inactive_external_source_rejects_new_receipt() -> None:
    with pytest.raises(HTTPException) as caught:
        external.validate_external_receipt(_source("INACTIVE"), _receipt())
    assert caught.value.status_code == 409


def test_future_publication_date_is_rejected() -> None:
    with pytest.raises(HTTPException) as caught:
        external.validate_external_receipt(
            _source(),
            _receipt(publication_date=date.today() + timedelta(days=1)),
        )
    assert caught.value.status_code == 422


def test_current_currency_requires_checksum_or_evidence() -> None:
    with pytest.raises(HTTPException) as caught:
        external.validate_external_receipt(
            _source(),
            _receipt(currency_status="CURRENT"),
        )
    assert caught.value.status_code == 422
    assert caught.value.detail["code"] == "EXTERNAL_CURRENCY_EVIDENCE_REQUIRED"


def test_current_currency_accepts_checksum() -> None:
    external.validate_external_receipt(
        _source(),
        _receipt(
            currency_status="CURRENT",
            checksum_sha256="a" * 64,
        ),
    )


def test_concluded_applicability_requires_evidence() -> None:
    with pytest.raises(HTTPException) as caught:
        external.validate_external_receipt(
            _source(),
            _receipt(applicability_status="APPLICABLE"),
        )
    assert caught.value.status_code == 422
    assert caught.value.detail["code"] == "EXTERNAL_APPLICABILITY_EVIDENCE_REQUIRED"


def test_unknown_currency_requires_note() -> None:
    with pytest.raises(HTTPException) as caught:
        external.validate_external_receipt(
            _source(),
            _receipt(currency_status="UNKNOWN"),
        )
    assert caught.value.status_code == 422


def test_evidenced_current_applicable_revision_is_allowed() -> None:
    external.validate_external_receipt(
        _source(),
        _receipt(
            currency_status="CURRENT",
            applicability_status="APPLICABLE",
            evidence=[{"asset_id": "oem-revision-notice"}],
        ),
    )
