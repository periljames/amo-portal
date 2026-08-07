from __future__ import annotations

from datetime import date, datetime, timezone
from types import SimpleNamespace

from amodb.apps.reliability.formal_reporting_render import _render_html, _render_pdf


def _report():
    dashboard = {
        "summary": [
            {
                "code": "flight_hours",
                "label": "Flight hours",
                "value": 1234.5,
                "unit": "FH",
                "denominator": None,
                "formula_code": "sum_flight_hours",
            },
            {
                "code": "dispatch_reliability_pct",
                "label": "Dispatch reliability",
                "value": None,
                "unit": "%",
                "denominator": None,
                "formula_code": "dispatch_reliability_pct",
                "detail": "Scheduled-departure denominator is unavailable.",
            },
        ],
        "warnings": ["Scheduled-departure denominator is unavailable."],
    }
    return SimpleNamespace(
        id="report-1",
        amo_id="amo-1",
        report_number="REL-2026-H1",
        revision=0,
        title="Half-year Reliability Programme Review",
        period_type="HALF_YEAR",
        period_start=date(2026, 1, 1),
        period_end=date(2026, 6, 30),
        status="DATA_REVIEW",
        profile_code_snapshot="KCAA",
        profile_version_snapshot="2026-08-07.1",
        data_cutoff_at=datetime(2026, 7, 1, 8, 0, tzinfo=timezone.utc),
        effectivity_json={"aircraft_serial_numbers": ["5Y-AAA"]},
        source_population_json={
            "workbook_record_count": 10,
            "canonical_event_count": 6,
            "source_identity_sha256": "a" * 64,
        },
        formula_revisions_json=[{"code": "dispatch_reliability_pct", "version": "1"}],
        calculation_snapshots_json={"dashboard": dashboard},
        regulatory_manifest=[],
    )


def _sections():
    return [
        SimpleNamespace(
            sequence=1,
            section_code="executive_assessment",
            title="Executive Reliability assessment",
            status="READY",
            computed_data={},
            commentary=[{
                "kind": "OBSERVED_FACT",
                "text": "Flight-hour exposure is retained from the governed calculation snapshot.",
                "evidence_refs": [{"kind": "CALCULATION", "code": "sum_flight_hours"}],
            }],
            warnings=[],
        ),
        SimpleNamespace(
            sequence=2,
            section_code="dispatch_reliability",
            title="Dispatch reliability",
            status="WITHHELD",
            computed_data={"metric": {"value": None}},
            commentary=[],
            warnings=["Dispatch reliability is withheld because its denominator is unavailable."],
        ),
        SimpleNamespace(
            sequence=3,
            section_code="data_quality",
            title="Data-quality statement",
            status="READY",
            computed_data={"warnings": ["Scheduled-departure denominator is unavailable."]},
            commentary=[],
            warnings=[],
        ),
    ]


def test_html_render_keeps_missing_denominator_withheld():
    output = _render_html(_report(), _sections())
    assert "WITHHELD / not available" in output
    assert "0.000" not in output
    assert "Scheduled-departure denominator is unavailable" in output
    assert "OBSERVED_FACT" in output


def test_pdf_render_is_deterministic_for_same_frozen_snapshot():
    first = _render_pdf(_report(), _sections())
    second = _render_pdf(_report(), _sections())
    assert first.startswith(b"%PDF")
    assert first == second
