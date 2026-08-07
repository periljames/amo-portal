from __future__ import annotations

from datetime import date
from types import SimpleNamespace

from amodb.apps.reliability.formal_reporting_charts import (
    PublicationChartSpec,
    chart_manifest,
    drawing_for_spec,
    publication_chart_specs,
    svg_for_spec,
)


def _report():
    return SimpleNamespace(
        period_start=date(2026, 1, 1),
        period_end=date(2026, 6, 30),
        calculation_snapshots_json={
            "dashboard": {
                "time_series": [
                    {"key": "2026-01", "label": "Jan 2026", "metrics": {"event_rate_per_100_fh": 1.25}},
                    {"key": "2026-02", "label": "Feb 2026", "metrics": {"event_rate_per_100_fh": None}},
                ],
                "ata_pareto": [
                    {"key": "21", "label": "ATA 21", "metrics": {"count": 5, "cumulative_pct": 50}},
                ],
                "aircraft_performance": [],
                "station_delay": [],
                "fracas_stages": [],
                "deferral_status": [],
                "component_reliability": [],
            },
            "long_term_history": {
                "series": [
                    {"month": "2026-01-01", "exact_event_rate_per_100_fh": "1.25", "exact_flight_hours": "120.5"},
                    {"month": "2026-02-01", "exact_event_rate_per_100_fh": None, "exact_flight_hours": None},
                ]
            },
        },
    )


def test_publication_chart_specs_are_snapshot_only_and_preserve_withheld_points():
    specs = publication_chart_specs(_report())
    assert {item.code for item in specs} >= {"long_term_event_rate", "long_term_flight_hours", "period_event_rate", "ata_pareto"}
    history = next(item for item in specs if item.code == "long_term_event_rate")
    assert history.values[0] is not None
    assert history.values[1] is None
    assert history.source_path.startswith("calculation_snapshots.long_term_history")
    assert "withheld" in (history.denominator_context or "").lower()


def test_svg_has_units_source_metadata_and_zero_baseline_geometry():
    spec = PublicationChartSpec(
        code="test",
        section_code="statistical_analysis",
        title="Reliability rate",
        subtitle="2026 H1",
        unit="events / 100 FH",
        kind="LINE",
        labels=("Jan", "Feb"),
        values=(None, None),
        source_path="calculation_snapshots.test",
        denominator_context="Flight-hour exposure required.",
    )
    svg = svg_for_spec(spec)
    assert "Reliability rate" in svg
    assert "events / 100 FH" in svg
    assert "WITHHELD" in svg
    assert "source=calculation_snapshots.test" in svg


def test_pdf_drawing_and_manifest_are_deterministic():
    spec = PublicationChartSpec(
        code="bars",
        section_code="operational_interruptions",
        title="ATA events",
        subtitle="2026 H1",
        unit="events",
        kind="BAR",
        labels=("ATA 21", "ATA 32"),
        values=(None, None),
        source_path="calculation_snapshots.dashboard.ata_pareto",
    )
    drawing = drawing_for_spec(spec)
    assert drawing.width == 500
    first = chart_manifest([spec])
    second = chart_manifest([spec])
    assert first == second
    assert first[0]["values"] == [None, None]
