from __future__ import annotations

from pathlib import Path

import pytest
from fastapi import HTTPException

from amodb.apps.doc_control.workspace_reports_export_router import (
    EXPORT_BATCH_SIZE,
    EXPORT_MAX_ROWS,
    _require_export_bound,
    _safe_csv_value,
)
from amodb.main import app


ROOT = Path(__file__).resolve().parents[5]


def _source(path: str) -> str:
    return (ROOT / path).read_text(encoding="utf-8")


def test_full_filtered_evidence_export_route_is_registered() -> None:
    paths = {getattr(route, "path", "") for route in app.routes}
    assert "/doc-control/workspace/t/{tenant_slug}/reports-export.csv" in paths


def test_direct_export_is_server_batched_and_explicitly_bounded() -> None:
    assert EXPORT_BATCH_SIZE == 100
    assert EXPORT_MAX_ROWS == 10_000
    _require_export_bound(EXPORT_MAX_ROWS)
    with pytest.raises(HTTPException) as caught:
        _require_export_bound(EXPORT_MAX_ROWS + 1)
    assert caught.value.status_code == 422
    assert caught.value.detail["code"] == "DOCUMENT_CONTROL_EXPORT_LIMIT_EXCEEDED"
    assert caught.value.detail["total"] == 10_001
    assert caught.value.detail["limit"] == 10_000


def test_server_export_neutralizes_spreadsheet_formula_prefixes() -> None:
    assert _safe_csv_value("=2+2") == "'=2+2"
    assert _safe_csv_value("  +SUM(A1:A2)") == "'  +SUM(A1:A2)"
    assert _safe_csv_value("@danger") == "'@danger"
    assert _safe_csv_value("normal") == "normal"


def test_export_reuses_authoritative_report_queries_and_rejects_mid_export_drift() -> None:
    source = _source("backend/amodb/apps/doc_control/workspace_reports_export_router.py")
    assert "get_reports_portfolio(" in source
    assert "get_reports_register(" in source
    assert "per_page=EXPORT_BATCH_SIZE" in source
    assert "while len(items) < total:" in source
    assert "if len(items) != total:" in source
    assert "DOCUMENT_CONTROL_EXPORT_CHANGED_DURING_GENERATION" in source
    assert "X-Document-Control-Export-Rows" in source
    assert "Record ID" in source
    assert "Document ID" in source
