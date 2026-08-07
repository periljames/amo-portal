from __future__ import annotations

from amodb.apps.aircraft_architecture.content_packs import (
    backend_ingestion,
    backend_ingestion_hardening,
)


def _candidate(source_json):
    return backend_ingestion.NormalizedCandidateRow(
        sheet_name="Section 1",
        row_number=10,
        row_kind="TASK",
        identity_key="TASK-1",
        source_json=source_json,
        normalized_json={"task_code": "TASK-1"},
        status="VALID",
        issues=[],
    )


def test_formula_detection_is_recursive_and_fail_closed():
    assert backend_ingestion_hardening._contains_formula(
        {"interval": ["8000 FH", {"derived": "=A1+B1"}]}
    )
    assert not backend_ingestion_hardening._contains_formula(
        {"interval": ["8000 FH", {"source": "PSM 1-84-7P"}]}
    )


def test_formula_row_becomes_review_required(monkeypatch):
    preview = object()
    candidate = _candidate({"task_code": "=A1", "description": "Controlled task"})
    monkeypatch.setattr(
        backend_ingestion_hardening,
        "_ORIGINAL_NORMALIZE",
        lambda **_: (preview, [candidate]),
    )
    returned_preview, rows = backend_ingestion_hardening.normalize_oem_workbook(
        filename="source.xlsx",
        content=b"not-used-by-stub",
        source_reference="PSM 1-84-7P",
        source_revision="52",
        source_checksum_sha256="a" * 64,
    )
    assert returned_preview is preview
    assert rows[0].status == "REVIEW_REQUIRED"
    assert rows[0].issues[-1]["code"] == "FORMULA_REVIEW_REQUIRED"
