from pathlib import Path

import pytest
from fastapi import HTTPException

from amodb.apps.quality.audit_guest_document_storage import _validate_signature, safe_filename


def test_safe_filename_strips_path_components_and_unsafe_characters():
    assert safe_filename("../../../../evidence/<script>.pdf") == "_script_.pdf"
    assert "/" not in safe_filename("folder\\nested\\record.xlsx")
    assert "\\" not in safe_filename("folder\\nested\\record.xlsx")


def test_pdf_signature_must_match_extension():
    _validate_signature("report.pdf", b"%PDF-1.7\n")
    with pytest.raises(HTTPException) as exc:
        _validate_signature("report.pdf", b"not-a-pdf")
    assert exc.value.status_code == 415


def test_office_and_image_signatures_are_validated():
    _validate_signature("record.xlsx", b"PK\x03\x04payload")
    _validate_signature("photo.png", b"\x89PNG\r\n\x1a\npayload")
    _validate_signature("photo.jpg", b"\xff\xd8\xffpayload")

    with pytest.raises(HTTPException):
        _validate_signature("record.xlsx", b"plain text")
    with pytest.raises(HTTPException):
        _validate_signature("photo.png", b"plain text")


def test_unsupported_extension_fails_closed():
    with pytest.raises(HTTPException) as exc:
        _validate_signature("payload.exe", b"MZ")
    assert exc.value.status_code == 415
