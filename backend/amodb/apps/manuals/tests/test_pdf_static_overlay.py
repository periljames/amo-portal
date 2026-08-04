from __future__ import annotations

import json
from types import SimpleNamespace

import pymupdf
import pytest
from fastapi import HTTPException

from amodb.apps.manuals.pdf_static_overlay_router import (
    _parse_overlays,
    _render_static_overlays,
    static_overlay_capabilities,
)


def _user(*, control: bool):
    return SimpleNamespace(
        id="user-1",
        is_superuser=control,
        is_amo_admin=False,
        role="USER",
        department=None,
    )


def _profile(*, schema: dict | None = None):
    return SimpleNamespace(
        execution_type="DOWNLOADABLE_TEMPLATE",
        requires_signature=False,
        access_scope_json={},
        schema_json=schema or {},
    )


def _source_pdf() -> bytes:
    document = pymupdf.open()
    page = document.new_page(width=612, height=792)
    page.insert_text((72, 72), "Static controlled form")
    content = document.tobytes()
    document.close()
    return content


def test_document_control_user_can_type_on_safe_static_pdf_without_acroform() -> None:
    capabilities = static_overlay_capabilities(
        _user(control=True),
        None,
        has_javascript=False,
        is_dynamic_xfa=False,
        encrypted=False,
    )

    assert capabilities["can_overlay_fill"] is True
    assert capabilities["can_configure_overlay"] is True
    assert capabilities["overlay_download_mode"] == "COMPLETED_PAGES"


def test_scoped_executor_can_fill_only_schema_governed_fields() -> None:
    profile = _profile(schema={
        "pdf_overlay": {
            "fields": [{
                "id": "full-name",
                "name": "Full name",
                "page": 1,
                "x": 0.15,
                "y": 0.20,
                "width": 0.50,
                "height": 0.05,
                "font_size": 10,
            }],
        },
    })
    capabilities = static_overlay_capabilities(
        _user(control=False),
        profile,
        has_javascript=False,
        is_dynamic_xfa=False,
        encrypted=False,
    )
    assert capabilities["can_overlay_fill"] is True
    assert capabilities["can_configure_overlay"] is False

    overlays, completed_only = _parse_overlays(
        json.dumps({"items": [{"id": "full-name", "text": "James Muisyo"}]}),
        page_count=1,
        profile=profile,
        allow_free_position=False,
    )
    assert completed_only is True
    assert overlays[0].x == 0.15
    assert overlays[0].text == "James Muisyo"

    with pytest.raises(HTTPException) as exc:
        _parse_overlays(
            json.dumps({
                "items": [{
                    "id": "free-field",
                    "page": 1,
                    "x": 0.1,
                    "y": 0.1,
                    "width": 0.2,
                    "height": 0.05,
                    "text": "Not governed",
                }],
            }),
            page_count=1,
            profile=profile,
            allow_free_position=False,
        )
    assert exc.value.status_code == 403


def test_static_overlay_is_written_to_a_derivative_and_source_remains_unchanged() -> None:
    source = _source_pdf()
    source_before = bytes(source)
    profile = _profile()
    overlays, _ = _parse_overlays(
        json.dumps({
            "items": [{
                "id": "requester",
                "name": "Requester",
                "page": 1,
                "x": 0.15,
                "y": 0.20,
                "width": 0.5,
                "height": 0.08,
                "font_size": 10,
                "text": "James Muisyo",
            }],
        }),
        page_count=1,
        profile=profile,
        allow_free_position=True,
    )

    output, pages = _render_static_overlays(source, overlays, True)

    assert source == source_before
    assert output != source
    assert pages == [1]
    completed = pymupdf.open(stream=output, filetype="pdf")
    try:
        assert completed.page_count == 1
        assert "James Muisyo" in completed[0].get_text()
    finally:
        completed.close()


def test_static_overlay_rejects_unsafe_pdf_classes_and_signature_profiles() -> None:
    for kwargs in (
        {"has_javascript": True, "is_dynamic_xfa": False, "encrypted": False},
        {"has_javascript": False, "is_dynamic_xfa": True, "encrypted": False},
        {"has_javascript": False, "is_dynamic_xfa": False, "encrypted": True},
    ):
        capability = static_overlay_capabilities(_user(control=True), None, **kwargs)
        assert capability["can_overlay_fill"] is False

    profile = _profile()
    profile.requires_signature = True
    capability = static_overlay_capabilities(
        _user(control=True),
        profile,
        has_javascript=False,
        is_dynamic_xfa=False,
        encrypted=False,
    )
    assert capability["can_overlay_fill"] is False
    assert "signature" in str(capability["overlay_reason"]).lower()
