from __future__ import annotations

from types import SimpleNamespace

from amodb.apps.accounts import models as accounts_models
from amodb.apps.training import router as training_router
from amodb.apps.training.record_presentation_portfolio import (
    _PORTFOLIO_CSS,
    _PORTFOLIO_SCRIPT,
    _logo_priority,
    _training_profile_html,
)


def _requirements(count: int = 7):
    rows = []
    for index in range(count):
        rows.append(
            {
                "requirement_key": f"course:{index}",
                "course_pk": f"course-{index}",
                "course_name": f"Training Course {index + 1}",
                "last_completed": f"2026-0{(index % 8) + 1}-04",
                "next_due": f"2028-0{(index % 8) + 1}-04" if index < 4 else None,
                "scheduled": None,
                "compliance_status": "Current" if index < 4 else "Completed",
                "has_recurrence": index < 4,
                "due_tone": "current" if index < 4 else "neutral",
                "viewer_record_id": "record-1" if index == 0 else None,
                "history": [
                    {
                        "record_id": f"record-{index + 1}",
                        "course_name": f"Training Course {index + 1}",
                        "type": "Initial" if index >= 4 else "Recurrent",
                        "completed": f"2026-0{(index % 8) + 1}-04",
                        "viewer_available": index == 0,
                    }
                ],
            }
        )
    return rows


def _payload():
    return {
        "tenant": {
            "amo_id": "ID-Q50VN737",
            "name": "Safarilink Aviation Limited",
            "brand_accent": "#a7862d",
            "logo_url": "/public/training/brand/ID-Q50VN737/identity-logo",
        },
        "user": {
            "user_id": "ID-FL28MRNH",
            "full_name": "Mercy Etende",
            "position_title": "Procurement Officer",
            "staff_code": "ETEN01",
            "is_active": True,
        },
        "summary": {
            "current": 4,
            "completed": 5,
            "due_soon": 0,
            "overdue": 0,
            "deferred": 0,
        },
        "requirements": _requirements(),
    }


def test_portfolio_removes_staff_identifier_and_combined_completed_summary():
    body = _training_profile_html(_payload()).body.decode("utf-8")

    assert "Staff ETEN01" not in body
    assert "ETEN01" not in body
    assert "4 current · 5 completed" not in body
    assert "Compliance standing" in body
    assert ">4</b><span>Current</span>" in body
    assert ">0</b><span>Due soon</span>" in body
    assert ">0</b><span>Overdue</span>" in body


def test_portfolio_is_single_page_vertical_tab_workspace():
    body = _training_profile_html(_payload()).body.decode("utf-8")

    assert "role='tablist' aria-orientation='vertical'" in body
    assert "data-tab-button='overview'" in body
    assert "data-tab-button='training'" in body
    assert "data-tab-button='certificates'" in body
    assert "data-tab-button='history'" in body
    assert "data-tab-panel='overview'" in body
    assert "data-tab-panel='training'" in body
    assert "data-tab-panel='certificates'" in body
    assert "data-tab-panel='history'" in body
    assert "record-portfolio.js" in body
    assert "activateTab" in _PORTFOLIO_SCRIPT


def test_training_table_has_five_row_client_pagination_contract():
    body = _training_profile_html(_payload()).body.decode("utf-8")

    assert "data-paginated-table data-page-size='5'" in body
    assert body.count("data-training-row") == 7
    assert "data-page-prev" in body
    assert "data-page-next" in body
    assert "data-page-numbers" in body
    assert "data-page-summary" in body
    assert "Math.ceil(rows.length / pageSize)" in _PORTFOLIO_SCRIPT
    assert "Showing ${start + 1}" in _PORTFOLIO_SCRIPT


def test_portfolio_uses_amo_asset_logo_surface_without_broken_alt_text():
    body = _training_profile_html(_payload()).body.decode("utf-8")

    assert "src='/public/training/brand/ID-Q50VN737/identity-logo'" in body
    assert "data-amo-logo" in body
    assert "data-amo-logo-fallback" in body
    assert "alt=''" in body
    assert "width: 220px" in _PORTFOLIO_CSS
    assert "height: 100px" in _PORTFOLIO_CSS


def test_logo_asset_selection_prefers_canonical_amo_logo_then_named_other_asset():
    canonical = SimpleNamespace(
        kind=accounts_models.AMOAssetKind.CRS_LOGO,
        name="CRS logo",
        description=None,
        original_filename="company.png",
    )
    named_other = SimpleNamespace(
        kind=accounts_models.AMOAssetKind.OTHER,
        name="Brand logo",
        description=None,
        original_filename="identity.webp",
    )
    unrelated = SimpleNamespace(
        kind=accounts_models.AMOAssetKind.OTHER,
        name="Stamp",
        description=None,
        original_filename="stamp.png",
    )

    assert _logo_priority(canonical) == 0
    assert _logo_priority(named_other) == 1
    assert _logo_priority(unrelated) == 99


def test_typography_uses_professional_local_display_and_ui_stacks():
    assert '"Avenir Next"' in _PORTFOLIO_CSS
    assert '"Iowan Old Style"' in _PORTFOLIO_CSS
    assert "Baskerville" in _PORTFOLIO_CSS
    assert "font-variant-numeric: tabular-nums" in _PORTFOLIO_CSS


def test_certificate_and_history_sections_use_real_viewer_record_ids():
    body = _training_profile_html(_payload()).body.decode("utf-8")

    assert "id='panel-certificates'" in body
    assert "id='panel-history'" in body
    assert "data-record-id='record-1'" in body
    assert "id='certificate-viewer'" in body


def test_canonical_public_router_installs_portfolio_assets_and_renderer():
    paths = {route.path for route in training_router.public_router.routes}

    assert "/public/training/assets/record-portfolio.js" in paths
    assert "/public/training/brand/{amo_id}/identity-logo" in paths
    assert training_router._training_profile_html is _training_profile_html
    assert training_router._portfolio_training_record_presentation_installed is True
