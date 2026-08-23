from __future__ import annotations

from amodb.apps.quality import audit_report_composition as composition
from amodb.apps.quality import audit_report_composition_hardening as hardening


def test_report_hardening_patches_canonical_composition_symbols():
    assert composition.build_report_snapshot is hardening.build_report_snapshot
    assert composition._render_pdf is hardening.render_pdf


def test_report_hardening_source_snapshot_keeps_execution_version_and_question_context():
    names = set(hardening.build_report_snapshot.__code__.co_names)
    assert "entity_version" in names
    assert "objective_evidence" in names
    assert "evidence_references" in names
