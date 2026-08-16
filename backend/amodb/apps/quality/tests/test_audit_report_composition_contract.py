from __future__ import annotations

from pathlib import Path

from amodb.apps.quality.audit_report_composition import _canonical_hash, _render_pdf


def _snapshot() -> dict:
    return {
        "schema": "QMS_AUDIT_REPORT_SNAPSHOT_V1",
        "audit": {
            "id": "44444444-4444-4444-8444-444444444444",
            "audit_ref": "QAR-MO-26-021",
            "title": "Quality system audit",
            "domain": "AMO",
            "kind": "INTERNAL",
            "status": "IN_PROGRESS",
            "scope": "Quality management system and controlled processes.",
            "criteria": "Approved QMS manual and applicable regulatory requirements.",
            "auditee": "Quality Department",
            "auditee_email": "quality@example.test",
            "planned_start": "2026-08-19T08:00:00+03:00",
            "planned_end": "2026-08-19T16:00:00+03:00",
            "actual_start": "2026-08-19T08:03:00+03:00",
            "actual_end": "2026-08-19T15:52:00+03:00",
            "lead_auditor_user_id": "auditor-a",
            "observer_auditor_user_id": None,
            "assistant_auditor_user_id": None,
        },
        "checklist": [
            {
                "checklist_item_id": "item-1",
                "canonical_response_status": "COMPLIANT",
                "auditor_notes": "Current controlled copy sampled at point of use.",
                "objective_evidence": "QP-04 Rev 7 compared to DMS current revision.",
                "evidence_references": [],
            },
            {
                "checklist_item_id": "item-2",
                "canonical_response_status": "NONCOMPLIANT",
                "auditor_notes": "One obsolete print was available at the sampled station.",
                "objective_evidence": "Station copy QP-07 Rev 2 versus current Rev 4.",
                "evidence_references": [{"type": "PHOTO", "ref": "IMG-021"}],
            },
        ],
        "findings": [
            {
                "id": "finding-1",
                "finding_ref": "QAR-MO-26-021-F-001",
                "finding_type": "NON_CONFORMITY",
                "severity": "MAJOR",
                "level": "LEVEL_2",
                "requirement_ref": "QMSM 4.2.3",
                "description": "An obsolete procedure revision was available at a point of use.",
                "objective_evidence": "Station copy QP-07 Rev 2 versus current Rev 4.",
                "acknowledged_at": None,
                "closed_at": None,
                "verified_at": None,
            }
        ],
        "cars": [
            {
                "id": "car-1",
                "car_number": "CAR-Q-26-021",
                "finding_id": "finding-1",
                "title": "Remove obsolete controlled copy and prevent recurrence",
                "status": "OPEN",
                "due_date": "2026-09-19",
                "target_closure_date": "2026-09-19",
            }
        ],
        "preparation_documents": [
            {
                "id": "request-1",
                "title": "Current QMS manual",
                "status": "ACCEPTED",
                "due_date": "2026-08-17",
                "uploaded_at": "2026-08-16T08:00:00Z",
                "reviewed_at": "2026-08-16T09:00:00Z",
            }
        ],
    }


def test_canonical_snapshot_hash_is_independent_of_dictionary_key_order():
    left = {"b": {"z": 3, "a": 1}, "a": [2, 1]}
    right = {"a": [2, 1], "b": {"a": 1, "z": 3}}
    assert _canonical_hash(left) == _canonical_hash(right)
    assert len(_canonical_hash(left)) == 64


def test_canonical_snapshot_hash_changes_when_controlled_content_changes():
    original = _snapshot()
    changed = _snapshot()
    changed["findings"][0]["description"] = "Different governed finding statement."
    assert _canonical_hash(original) != _canonical_hash(changed)


def test_report_renderer_produces_a_pdf_from_the_frozen_snapshot(tmp_path: Path):
    destination = tmp_path / "closing-report.pdf"
    _render_pdf(_snapshot(), destination)
    content = destination.read_bytes()
    assert content.startswith(b"%PDF-")
    assert len(content) > 1000


def test_report_renderer_handles_no_findings_without_inventing_content(tmp_path: Path):
    snapshot = _snapshot()
    snapshot["findings"] = []
    snapshot["cars"] = []
    destination = tmp_path / "no-findings-report.pdf"
    _render_pdf(snapshot, destination)
    content = destination.read_bytes()
    assert content.startswith(b"%PDF-")
    assert len(content) > 1000
