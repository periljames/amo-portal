from __future__ import annotations

from dataclasses import dataclass
from decimal import Decimal, InvalidOperation
from typing import Any, Iterable
from xml.sax.saxutils import escape

from reportlab.graphics.charts.barcharts import VerticalBarChart
from reportlab.graphics.charts.lineplots import LinePlot
from reportlab.graphics.shapes import Drawing, String
from reportlab.graphics.widgets.markers import makeMarker
from reportlab.lib import colors


@dataclass(frozen=True)
class PublicationChartSpec:
    code: str
    section_code: str
    title: str
    subtitle: str
    unit: str
    kind: str
    labels: tuple[str, ...]
    values: tuple[Decimal | None, ...]
    source_path: str
    denominator_context: str | None = None


def _decimal(value: Any) -> Decimal | None:
    if value is None or isinstance(value, bool):
        return None
    try:
        result = Decimal(str(value))
    except (InvalidOperation, ValueError, TypeError):
        return None
    if not result.is_finite():
        return None
    return result


def _points(
    rows: Iterable[dict[str, Any]],
    *,
    metric: str,
    limit: int | None = None,
) -> tuple[tuple[str, ...], tuple[Decimal | None, ...]]:
    labels: list[str] = []
    values: list[Decimal | None] = []
    for row in list(rows)[:limit]:
        labels.append(str(row.get("label") or row.get("key") or ""))
        values.append(_decimal((row.get("metrics") or {}).get(metric)))
    return tuple(labels), tuple(values)


def _history_points(rows: Iterable[dict[str, Any]], field: str) -> tuple[tuple[str, ...], tuple[Decimal | None, ...]]:
    labels: list[str] = []
    values: list[Decimal | None] = []
    for row in rows:
        month = str(row.get("month") or "")
        labels.append(month[:7])
        values.append(_decimal(row.get(field)))
    return tuple(labels), tuple(values)


def publication_chart_specs(report) -> list[PublicationChartSpec]:
    calculations = report.calculation_snapshots_json or {}
    dashboard = calculations.get("dashboard") or {}
    history = calculations.get("long_term_history") or {}
    period = f"{report.period_start} — {report.period_end}"
    specs: list[PublicationChartSpec] = []

    history_rows = history.get("series") or []
    if history_rows:
        labels, values = _history_points(history_rows, "exact_event_rate_per_100_fh")
        specs.append(PublicationChartSpec(
            code="long_term_event_rate",
            section_code="statistical_analysis",
            title="Long-term Reliability event rate",
            subtitle=f"Monthly controlled history through {report.period_end}",
            unit="events / 100 FH",
            kind="LINE",
            labels=labels,
            values=values,
            source_path="calculation_snapshots.long_term_history.series.exact_event_rate_per_100_fh",
            denominator_context="Approved flight-hour exposure; points are withheld where exposure is unavailable or zero.",
        ))
        labels, values = _history_points(history_rows, "exact_flight_hours")
        specs.append(PublicationChartSpec(
            code="long_term_flight_hours",
            section_code="utilisation",
            title="Long-term fleet utilisation",
            subtitle=f"Monthly approved flight-hour exposure through {report.period_end}",
            unit="FH",
            kind="LINE",
            labels=labels,
            values=values,
            source_path="calculation_snapshots.long_term_history.series.exact_flight_hours",
        ))

    time_series = dashboard.get("time_series") or []
    if time_series:
        labels, values = _points(time_series, metric="event_rate_per_100_fh")
        specs.append(PublicationChartSpec(
            code="period_event_rate",
            section_code="operational_interruptions",
            title="Current-period Reliability event rate",
            subtitle=period,
            unit="events / 100 FH",
            kind="LINE",
            labels=labels,
            values=values,
            source_path="calculation_snapshots.dashboard.time_series.metrics.event_rate_per_100_fh",
            denominator_context="Flight-hour exposure from the governed dashboard snapshot.",
        ))

    for code, section, title, field, metric, unit, limit in (
        ("ata_pareto", "operational_interruptions", "ATA event Pareto", "ata_pareto", "count", "events", 15),
        ("aircraft_event_rate", "operational_interruptions", "Aircraft Reliability comparison", "aircraft_performance", "event_rate_per_100_fh", "events / 100 FH", 15),
        ("station_delay", "operational_interruptions", "Technical delay concentration by station", "station_delay", "delay_minutes", "minutes", 15),
        ("fracas_stage", "fracas", "FRACAS case status", "fracas_stages", "count", "cases", 12),
        ("deferral_status", "deferred_defects", "Deferred-defect status", "deferral_status", "count", "items", 12),
        ("component_reliability", "component_reliability", "Component Reliability concentration", "component_reliability", "unscheduled_removals", "unscheduled removals", 12),
    ):
        rows = dashboard.get(field) or []
        if not rows:
            continue
        labels, values = _points(rows, metric=metric, limit=limit)
        if not any(value is not None for value in values):
            continue
        specs.append(PublicationChartSpec(
            code=code,
            section_code=section,
            title=title,
            subtitle=period,
            unit=unit,
            kind="BAR",
            labels=labels,
            values=values,
            source_path=f"calculation_snapshots.dashboard.{field}.metrics.{metric}",
            denominator_context=("Flight-hour exposure from the governed dashboard snapshot." if "rate" in metric else None),
        ))

    return specs


def chart_manifest(specs: Iterable[PublicationChartSpec]) -> list[dict[str, Any]]:
    return [{
        "code": spec.code,
        "section_code": spec.section_code,
        "title": spec.title,
        "subtitle": spec.subtitle,
        "unit": spec.unit,
        "kind": spec.kind,
        "labels": list(spec.labels),
        "values": [format(value, "f") if value is not None else None for value in spec.values],
        "source_path": spec.source_path,
        "denominator_context": spec.denominator_context,
    } for spec in specs]


def _nice_max(values: list[float]) -> float:
    maximum = max(values, default=0.0)
    if maximum <= 0:
        return 1.0
    return maximum * 1.12


def drawing_for_spec(spec: PublicationChartSpec, *, width: int = 500, height: int = 245) -> Drawing:
    drawing = Drawing(width, height)
    drawing.add(String(8, height - 17, spec.title, fontName="Helvetica-Bold", fontSize=10, fillColor=colors.HexColor("#1f2933")))
    drawing.add(String(8, height - 31, spec.subtitle, fontName="Helvetica", fontSize=7, fillColor=colors.HexColor("#536170")))
    drawing.add(String(8, 5, spec.unit, fontName="Helvetica-Bold", fontSize=6.5, fillColor=colors.HexColor("#536170")))
    if spec.denominator_context:
        drawing.add(String(88, 5, spec.denominator_context[:98], fontName="Helvetica", fontSize=5.7, fillColor=colors.HexColor("#667587")))

    valid = [(idx, value) for idx, value in enumerate(spec.values) if value is not None]
    if not valid:
        drawing.add(String(8, height / 2, "WITHHELD — no plottable governed value for this period", fontName="Helvetica-Bold", fontSize=8, fillColor=colors.HexColor("#6b7280")))
        return drawing

    chart_x = 48
    chart_y = 32
    chart_width = width - 62
    chart_height = height - 78
    numeric = [float(value) for _, value in valid]

    if spec.kind == "BAR":
        chart = VerticalBarChart()
        chart.x = chart_x
        chart.y = chart_y
        chart.width = chart_width
        chart.height = chart_height
        chart.data = [[float(value or 0) for value in spec.values]]
        chart.categoryAxis.categoryNames = [label[:18] for label in spec.labels]
        chart.categoryAxis.labels.fontName = "Helvetica"
        chart.categoryAxis.labels.fontSize = 5.5
        chart.categoryAxis.labels.angle = 35 if len(spec.labels) > 7 else 0
        chart.categoryAxis.labels.dy = -8
        chart.valueAxis.valueMin = 0
        chart.valueAxis.valueMax = _nice_max(numeric)
        chart.valueAxis.valueStep = None
        chart.valueAxis.labels.fontName = "Helvetica"
        chart.valueAxis.labels.fontSize = 6
        chart.bars[0].fillColor = colors.HexColor("#56616d")
        chart.bars[0].strokeColor = colors.HexColor("#303840")
        chart.barSpacing = 1.3
        drawing.add(chart)
        return drawing

    chart = LinePlot()
    chart.x = chart_x
    chart.y = chart_y
    chart.width = chart_width
    chart.height = chart_height
    chart.data = [[(float(idx), float(value)) for idx, value in valid]]
    chart.xValueAxis.valueMin = 0
    chart.xValueAxis.valueMax = max(len(spec.labels) - 1, 1)
    chart.xValueAxis.valueStep = max(1, len(spec.labels) // 8)
    chart.xValueAxis.labels.fontSize = 5.5
    chart.xValueAxis.labels.fontName = "Helvetica"
    chart.xValueAxis.labelTextFormat = lambda value: spec.labels[min(max(int(round(value)), 0), len(spec.labels) - 1)][:10]
    chart.yValueAxis.valueMin = 0
    chart.yValueAxis.valueMax = _nice_max(numeric)
    chart.yValueAxis.labels.fontSize = 6
    chart.yValueAxis.labels.fontName = "Helvetica"
    chart.lines[0].strokeColor = colors.HexColor("#303840")
    chart.lines[0].strokeWidth = 1.4
    chart.lines[0].symbol = makeMarker("FilledCircle")
    chart.lines[0].symbol.size = 2.5
    chart.lines[0].symbol.fillColor = colors.HexColor("#303840")
    drawing.add(chart)
    return drawing


def svg_for_spec(spec: PublicationChartSpec, *, width: int = 760, height: int = 310) -> str:
    # A compact deterministic SVG is used in the retained HTML so the portal and
    # PDF share the same labels, units, source path and zero-baseline policy.
    margin_left, margin_right, margin_top, margin_bottom = 56, 18, 50, 48
    plot_width = width - margin_left - margin_right
    plot_height = height - margin_top - margin_bottom
    valid_values = [value for value in spec.values if value is not None]
    y_max = max(valid_values, default=Decimal(1))
    if y_max <= 0:
        y_max = Decimal(1)
    y_max = y_max * Decimal("1.12")

    parts = [
        f"<svg class='formal-chart' viewBox='0 0 {width} {height}' role='img' aria-label='{escape(spec.title)}'>",
        f"<text x='8' y='18' font-size='13' font-weight='700'>{escape(spec.title)}</text>",
        f"<text x='8' y='34' font-size='9'>{escape(spec.subtitle)}</text>",
        f"<line x1='{margin_left}' y1='{margin_top}' x2='{margin_left}' y2='{margin_top + plot_height}' stroke='#444'/>",
        f"<line x1='{margin_left}' y1='{margin_top + plot_height}' x2='{margin_left + plot_width}' y2='{margin_top + plot_height}' stroke='#444'/>",
        f"<text x='8' y='{margin_top + 8}' font-size='8'>{escape(spec.unit)}</text>",
    ]
    if not valid_values:
        parts.append(f"<text x='{margin_left + 12}' y='{margin_top + plot_height / 2}' font-size='11' font-weight='700'>WITHHELD — no plottable governed value</text>")
        if spec.denominator_context:
            parts.append(f"<text x='{margin_left}' y='{height - 8}' font-size='7'>{escape(spec.denominator_context[:120])}</text>")
        parts.append(f"<metadata>source={escape(spec.source_path)}</metadata></svg>")
        return "".join(parts)

    count = max(len(spec.labels), 1)
    if spec.kind == "BAR":
        step = plot_width / count
        bar_width = max(step * 0.62, 1)
        for idx, (label, value) in enumerate(zip(spec.labels, spec.values)):
            if value is None:
                continue
            height_px = float(value / y_max) * plot_height
            x = margin_left + idx * step + (step - bar_width) / 2
            y = margin_top + plot_height - height_px
            parts.append(f"<rect x='{x:.2f}' y='{y:.2f}' width='{bar_width:.2f}' height='{height_px:.2f}' fill='#5f6872' stroke='#31363b'/>")
            if idx % max(1, count // 8) == 0:
                parts.append(f"<text x='{x:.2f}' y='{margin_top + plot_height + 14}' font-size='7' transform='rotate(30 {x:.2f} {margin_top + plot_height + 14})'>{escape(label[:16])}</text>")
    else:
        step = plot_width / max(count - 1, 1)
        coordinates: list[str] = []
        for idx, value in enumerate(spec.values):
            if value is None:
                continue
            x = margin_left + idx * step
            y = margin_top + plot_height - float(value / y_max) * plot_height
            coordinates.append(f"{x:.2f},{y:.2f}")
            parts.append(f"<circle cx='{x:.2f}' cy='{y:.2f}' r='2.1' fill='#303840'/>")
            if idx % max(1, count // 8) == 0:
                parts.append(f"<text x='{x:.2f}' y='{margin_top + plot_height + 14}' font-size='7' text-anchor='middle'>{escape(spec.labels[idx][:10])}</text>")
        if len(coordinates) >= 2:
            parts.append(f"<polyline fill='none' stroke='#303840' stroke-width='1.8' points='{' '.join(coordinates)}'/>")
    if spec.denominator_context:
        parts.append(f"<text x='{margin_left}' y='{height - 8}' font-size='7'>{escape(spec.denominator_context[:120])}</text>")
    parts.append(f"<metadata>source={escape(spec.source_path)}</metadata></svg>")
    return "".join(parts)
