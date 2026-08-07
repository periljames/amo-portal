from __future__ import annotations

import hashlib
import html
from collections import Counter, defaultdict
from datetime import date
from io import BytesIO
from typing import Any, Literal

from fastapi import APIRouter, Depends, HTTPException, Response
from pydantic import BaseModel, Field, model_validator
from reportlab.graphics.charts.barcharts import VerticalBarChart
from reportlab.graphics.shapes import Drawing, String
from reportlab.lib import colors
from reportlab.lib.pagesizes import A4, landscape
from reportlab.lib.styles import ParagraphStyle, getSampleStyleSheet
from reportlab.lib.units import mm
from reportlab.platypus import KeepTogether, PageBreak, Paragraph, SimpleDocTemplate, Spacer, Table, TableStyle
from sqlalchemy.orm import Session

from amodb.apps.accounts import models as account_models
from amodb.database import get_write_db
from amodb.security import get_current_active_user

from .analytics_builder import build_dashboard
from . import workbook_parity as wp

ANALYSIS_ROLES = {
    "SUPERUSER", "AMO_ADMIN", "QUALITY_MANAGER", "SAFETY_MANAGER",
    "PLANNING_ENGINEER", "PRODUCTION_ENGINEER", "QUALITY_INSPECTOR", "AUDITOR",
}
MANAGEMENT_LAYOUT_CODE = "MANAGEMENT-PERIOD"
MAX_DETAIL_ROWS_PER_DOMAIN = 100


class ManagementReportRequest(BaseModel):
    period_start: date
    period_end: date
    aircraft: list[str] = Field(default_factory=list)
    dataset_codes: list[wp.WorkbookDatasetCode] = Field(default_factory=list)
    bucket: Literal["AUTO", "DAY", "WEEK", "MONTH"] = "AUTO"
    title: str | None = Field(default=None, max_length=180)
    include_domain_details: bool = True

    @model_validator(mode="after")
    def validate_window(self):
        if self.period_end < self.period_start:
            raise ValueError("Period end must be on or after period start.")
        if (self.period_end - self.period_start).days > 730:
            raise ValueError("Management report windows are limited to 731 days. Use the later formal annual-report pack for longer controlled periods.")
        return self


def _amo_id(user: account_models.User) -> str:
    amo_id = user.effective_amo_id
    if not amo_id:
        raise HTTPException(status_code=403, detail="A tenant context is required.")
    return str(amo_id)


def _require_analysis(user: account_models.User) -> None:
    role = str(getattr(getattr(user, "role", None), "value", getattr(user, "role", ""))).upper()
    if bool(getattr(user, "is_superuser", False)) or bool(getattr(user, "is_amo_admin", False)) or role in ANALYSIS_ROLES:
        return
    raise HTTPException(status_code=403, detail="Reliability management reporting requires analysis permission.")


def _codes(request: ManagementReportRequest) -> list[wp.WorkbookDatasetCode]:
    return request.dataset_codes or list(wp.WorkbookDatasetCode)


def _record_dict(record: wp.ReliabilityWorkbookRecord) -> dict[str, Any]:
    return {
        "record_number": record.record_number,
        "date": record.event_date.isoformat(),
        "aircraft": record.aircraft_serial_number,
        "ata": record.ata_chapter,
        "reference": record.reference_code,
        "title": record.title,
        "status": record.status,
        "payload": record.payload or {},
        "derived": record.derived_values or {},
    }


def _domain_summary(code: wp.WorkbookDatasetCode, records: list[wp.ReliabilityWorkbookRecord]) -> dict[str, Any]:
    definition = wp.DATASET_CATALOG[code]
    by_aircraft = Counter(record.aircraft_serial_number or "Fleet / unallocated" for record in records)
    by_ata = Counter(record.ata_chapter or "Unallocated" for record in records)
    return {
        "code": code.value,
        "name": definition.name,
        "count": len(records),
        "aircraft_count": len({record.aircraft_serial_number for record in records if record.aircraft_serial_number}),
        "top_aircraft": [{"label": label, "count": count} for label, count in by_aircraft.most_common(8)],
        "top_ata": [{"label": label, "count": count} for label, count in by_ata.most_common(8)],
        "records": [_record_dict(record) for record in records[:MAX_DETAIL_ROWS_PER_DOMAIN]],
        "detail_truncated": len(records) > MAX_DETAIL_ROWS_PER_DOMAIN,
    }


def _metric_map(dashboard: dict[str, Any]) -> dict[str, dict[str, Any]]:
    return {str(item.get("code")): item for item in dashboard.get("summary", [])}


def _period_utilisation(dashboard: dict[str, Any]) -> dict[str, Any]:
    points = dashboard.get("time_series", [])
    rows = []
    for point in points:
        metrics = point.get("metrics") or {}
        rows.append({
            "label": point.get("label") or point.get("key"),
            "flight_hours": metrics.get("flight_hours") or 0,
            "flight_cycles": metrics.get("flight_cycles") or 0,
            "events": metrics.get("events") or 0,
            "dispatch_reliability_pct": metrics.get("dispatch_reliability_pct"),
            "event_rate_per_100_fh": metrics.get("event_rate_per_100_fh"),
        })
    return {
        "flight_hours": round(sum(float(item["flight_hours"] or 0) for item in rows), 3),
        "flight_cycles": round(sum(float(item["flight_cycles"] or 0) for item in rows), 3),
        "points": rows,
    }


def _narrative(data: dict[str, Any]) -> list[str]:
    dashboard = data["dashboard"]
    metrics = _metric_map(dashboard)
    utilisation = data["utilisation"]
    sentences = [
        f"The selected Reliability population recorded {utilisation['flight_hours']:,.1f} flight hours and {utilisation['flight_cycles']:,.0f} flight cycles from {data['period_start']} through {data['period_end']}.",
    ]
    dispatch = metrics.get("dispatch_reliability_pct")
    if dispatch and dispatch.get("value") is not None:
        delta = dispatch.get("delta_pct")
        comparison = "" if delta is None else f" ({float(delta):+.1f}% versus the immediately preceding equivalent period)"
        sentences.append(f"Dispatch reliability was {float(dispatch['value']):.3f}%{comparison}.")
    event_rate = metrics.get("event_rate_per_100_fh")
    if event_rate and event_rate.get("value") is not None:
        sentences.append(f"The controlled event rate was {float(event_rate['value']):.3f} per 100 flight hours.")
    active_domains = sorted((item for item in data["domains"] if item["count"]), key=lambda item: item["count"], reverse=True)
    if active_domains:
        sentences.append("Highest-volume controlled domains were " + ", ".join(f"{item['code']} ({item['count']})" for item in active_domains[:4]) + ".")
    warnings = dashboard.get("warnings", [])
    if warnings:
        sentences.append(f"The analysis raised {len(warnings)} data-quality or completeness warning(s); these are retained below and should be reviewed before management action.")
    else:
        sentences.append("No dashboard-level data-completeness warning was raised for the selected population.")
    return sentences


def _svg_bar(items: list[dict[str, Any]], label_key: str, value_key: str, title: str, suffix: str = "") -> str:
    if not items:
        return "<p class='empty'>No values are available for this chart.</p>"
    width, height, pad = 760, 250, 42
    values = [float(item.get(value_key) or 0) for item in items]
    maximum = max(values) or 1
    usable = width - 2 * pad
    gap = usable / max(len(items), 1)
    bar_width = max(10, gap * .62)
    output: list[str] = []
    for index, item in enumerate(items):
        value = values[index]
        bar_height = (height - 92) * value / maximum
        x = pad + index * gap + (gap - bar_width) / 2
        y = height - 55 - bar_height
        label = html.escape(str(item.get(label_key) or "")[:12])
        tooltip = html.escape(f"{item.get(label_key)}: {value:g}{suffix}")
        output.append(f"<rect x='{x:.1f}' y='{y:.1f}' width='{bar_width:.1f}' height='{bar_height:.1f}' rx='2'><title>{tooltip}</title></rect>")
        output.append(f"<text x='{x + bar_width / 2:.1f}' y='{height - 34}' text-anchor='middle'>{label}</text>")
        output.append(f"<text class='value' x='{x + bar_width / 2:.1f}' y='{max(y - 5, 16):.1f}' text-anchor='middle'>{value:,.1f}{html.escape(suffix)}</text>")
    return f"<figure><figcaption>{html.escape(title)}</figcaption><svg viewBox='0 0 {width} {height}' role='img' aria-label='{html.escape(title)}'>{''.join(output)}</svg></figure>"


def _table(headers: list[str], rows: list[list[Any]]) -> str:
    head = "".join(f"<th>{html.escape(value)}</th>" for value in headers)
    body = "".join("<tr>" + "".join(f"<td>{html.escape('' if value is None else str(value))}</td>" for value in row) + "</tr>" for row in rows)
    return f"<div class='table-wrap'><table><thead><tr>{head}</tr></thead><tbody>{body}</tbody></table></div>"


def _metric_card(item: dict[str, Any]) -> str:
    raw = item.get("value")
    value = "—" if raw is None else f"{float(raw):,.3f}"
    return (
        f"<article><span>{html.escape(str(item.get('label') or item.get('code') or 'Metric'))}</span>"
        f"<strong>{value} {html.escape(str(item.get('unit') or ''))}</strong>"
        f"<small>{html.escape(str(item.get('detail') or ''))}</small></article>"
    )


def _render_html(data: dict[str, Any], snapshot_id: int | None = None, sha: str | None = None) -> str:
    dashboard = data["dashboard"]
    utilisation = data["utilisation"]
    util_points = utilisation["points"]
    metric_cards = "".join(_metric_card(item) for item in dashboard.get("summary", [])[:10])
    domain_counts = [{"label": item["code"], "count": item["count"]} for item in data["domains"]]
    domain_rows = [[item["code"], item["name"], item["count"], item["aircraft_count"], ", ".join(f"{x['label']} ({x['count']})" for x in item["top_ata"][:3])] for item in data["domains"]]
    detail_sections: list[str] = []
    if data.get("include_domain_details"):
        for item in data["domains"]:
            if not item["count"]:
                continue
            recent = [[record["date"], record["aircraft"] or "Fleet", record["ata"] or "—", record["reference"] or "—", record["title"]] for record in item["records"]]
            detail_sections.append(
                f"<section class='domain'><div class='section-heading'><div><p class='eyebrow'>{html.escape(item['code'])}</p><h2>{html.escape(item['name'])}</h2></div><strong>{item['count']} controlled record(s)</strong></div>"
                + "<div class='charts'>"
                + _svg_bar(item["top_aircraft"], "label", "count", f"{item['code']} by aircraft")
                + _svg_bar(item["top_ata"], "label", "count", f"{item['code']} by ATA")
                + "</div>"
                + _table(["Date", "Aircraft", "ATA", "Reference", "Title"], recent)
                + ("<p class='note'>Detail is intentionally bounded; use portal drill-down for the complete evidence population.</p>" if item["detail_truncated"] else "")
                + "</section>"
            )
    warnings = dashboard.get("warnings", [])
    scope = ", ".join(data["aircraft"]) if data["aircraft"] else "Fleet"
    controls = f"Snapshot {snapshot_id or 'pending'} · SHA-256 {sha or 'calculated on retention'}"
    css = """
    :root{font-family:Inter,Arial,sans-serif;color:#172033;background:#fff}*{box-sizing:border-box}body{margin:0;padding:18mm 14mm;font-size:11px;line-height:1.45}h1{font-size:24px;margin:0 0 6px}h2{font-size:16px;margin:0}p{margin:6px 0}.eyebrow{text-transform:uppercase;letter-spacing:.12em;font-size:9px;font-weight:800;color:#315b8a}.meta{display:flex;gap:20px;flex-wrap:wrap;padding:10px 0 14px;border-bottom:1px solid #ccd5df}.meta span{display:grid}.meta strong{font-size:10px}.cards{display:grid;grid-template-columns:repeat(5,minmax(0,1fr));gap:8px;margin:14px 0}.cards article{border:1px solid #d9e0e8;padding:9px;min-height:92px}.cards span,.cards small{display:block;color:#596579}.cards strong{display:block;font-size:15px;margin:5px 0}.summary{padding:12px;border-left:4px solid #315b8a;background:#f5f8fb}.charts{display:grid;grid-template-columns:1fr 1fr;gap:12px;margin:14px 0}figure{margin:0;border:1px solid #d9e0e8;padding:8px;break-inside:avoid}figcaption{font-weight:800;margin-bottom:5px}svg{width:100%;height:auto}svg rect{fill:#557fa9}svg text{font-size:9px;fill:#445066}svg text.value{font-weight:700;fill:#172033}.table-wrap{overflow:auto;margin:10px 0 16px}table{width:100%;border-collapse:collapse;font-size:9px}th,td{border:1px solid #d9e0e8;padding:5px;vertical-align:top}th{background:#eef3f8;text-align:left}.section-heading{display:flex;justify-content:space-between;gap:15px;align-items:end;border-bottom:1px solid #cfd7e1;padding-bottom:5px}.domain{margin-top:22px}.warning{border:1px solid #d3a54b;background:#fff9e8;padding:8px}.note{color:#596579;font-size:9px}.control{margin-top:20px;border-top:1px solid #cfd7e1;padding-top:8px;font-family:monospace;font-size:8px;overflow-wrap:anywhere}.actions{position:sticky;top:0;display:flex;gap:8px;justify-content:flex-end;background:#fff;padding:6px 0 10px}.actions button{padding:6px 10px}@media print{body{padding:10mm}.actions{display:none}figure,.summary,.cards article{break-inside:avoid}.table-wrap{overflow:visible}}
    """
    event_items = [{"label": point["label"], "events": point["events"]} for point in util_points]
    warnings_html = "".join(f"<p class='warning'>{html.escape(str(item))}</p>" for item in warnings) if warnings else "<p>No dashboard-level data completeness warning was raised.</p>"
    narrative_html = "".join(f"<p>{html.escape(sentence)}</p>" for sentence in data["narrative"])
    return f"""<!doctype html><html><head><meta charset='utf-8'><title>{html.escape(data['title'])}</title><style>{css}</style></head><body>
    <div class='actions'><button onclick='window.print()'>Print / save PDF</button></div>
    <p class='eyebrow'>Controlled Reliability management report</p><h1>{html.escape(data['title'])}</h1>
    <div class='meta'><span><strong>Period</strong>{data['period_start']} → {data['period_end']}</span><span><strong>Scope</strong>{html.escape(scope)}</span><span><strong>Resolution</strong>{html.escape(str(dashboard.get('bucket') or data['bucket']))}</span><span><strong>Generated</strong>{html.escape(str(data['generated_at']))}</span></div>
    <section class='summary'><h2>Management summary</h2>{narrative_html}</section>
    <div class='cards'>{metric_cards}</div>
    <section><div class='section-heading'><div><p class='eyebrow'>Exposure</p><h2>Aircraft and fleet utilisation</h2></div><strong>{utilisation['flight_hours']:,.1f} FH · {utilisation['flight_cycles']:,.0f} FC</strong></div>
    <div class='charts'>{_svg_bar(util_points, 'label', 'flight_hours', 'Flight hours by reporting bucket', ' FH')}{_svg_bar(util_points, 'label', 'flight_cycles', 'Flight cycles by reporting bucket', ' FC')}</div></section>
    <section><div class='section-heading'><div><p class='eyebrow'>All controlled domains</p><h2>Reliability source-domain overview</h2></div><strong>{sum(item['count'] for item in data['domains'])} records</strong></div>
    <div class='charts'>{_svg_bar(domain_counts, 'label', 'count', 'Controlled records by Reliability domain')}{_svg_bar(event_items, 'label', 'events', 'Reliability events by reporting bucket')}</div>
    {_table(['Code','Domain','Records','Aircraft','Leading ATA'], domain_rows)}</section>
    <section><div class='section-heading'><div><p class='eyebrow'>Limitations</p><h2>Data quality and analytical cautions</h2></div></div>{warnings_html}</section>
    {''.join(detail_sections)}
    <div class='control'>{html.escape(controls)} · Layout {MANAGEMENT_LAYOUT_CODE} · This is a retained representation of approved/closed Reliability evidence and controlled analytics at generation time.</div>
    </body></html>"""


def _ensure_layout(db: Session, amo_id: str, user_id: str | None) -> wp.ReliabilityReportLayout:
    row = db.query(wp.ReliabilityReportLayout).filter(
        wp.ReliabilityReportLayout.amo_id == amo_id,
        wp.ReliabilityReportLayout.code == MANAGEMENT_LAYOUT_CODE,
        wp.ReliabilityReportLayout.active.is_(True),
    ).order_by(wp.ReliabilityReportLayout.revision.desc()).first()
    if row:
        return row
    row = wp.ReliabilityReportLayout(
        amo_id=amo_id,
        code=MANAGEMENT_LAYOUT_CODE,
        name="Reliability Management Period Report",
        aircraft_family="FLEET",
        revision=1,
        active=True,
        sections=[{"kind": "SUMMARY", "code": "MANAGEMENT", "title": "Management period review"}],
        page_settings={"paper_size": "A4", "orientation": "landscape", "margins_mm": 10},
        created_by_user_id=user_id,
    )
    db.add(row)
    db.flush()
    return row


def _build_data(db: Session, amo_id: str, request: ManagementReportRequest) -> dict[str, Any]:
    codes = _codes(request)
    dashboard = build_dashboard(
        db,
        amo_id=amo_id,
        period_start=request.period_start,
        period_end=request.period_end,
        bucket_requested=request.bucket,
        aircraft=request.aircraft,
        aircraft_types=[], ata_chapters=[], stations=[], event_types=[], severities=[], source_systems=[],
    ).model_dump(mode="json")
    query = db.query(wp.ReliabilityWorkbookRecord).filter(
        wp.ReliabilityWorkbookRecord.amo_id == amo_id,
        wp.ReliabilityWorkbookRecord.dataset_code.in_([code.value for code in codes]),
        wp.ReliabilityWorkbookRecord.status.in_([wp.WorkbookRecordStatus.APPROVED.value, wp.WorkbookRecordStatus.CLOSED.value]),
        wp.ReliabilityWorkbookRecord.event_date >= request.period_start,
        wp.ReliabilityWorkbookRecord.event_date <= request.period_end,
    )
    if request.aircraft:
        query = query.filter(wp.ReliabilityWorkbookRecord.aircraft_serial_number.in_(request.aircraft))
    records = query.order_by(wp.ReliabilityWorkbookRecord.event_date.desc(), wp.ReliabilityWorkbookRecord.id.desc()).all()
    grouped: dict[str, list[wp.ReliabilityWorkbookRecord]] = defaultdict(list)
    for record in records:
        grouped[record.dataset_code].append(record)
    data: dict[str, Any] = {
        "report_kind": "MANAGEMENT_PERIOD",
        "title": request.title or f"Reliability Management Report — {request.period_start.isoformat()} to {request.period_end.isoformat()}",
        "period_start": request.period_start.isoformat(),
        "period_end": request.period_end.isoformat(),
        "aircraft": request.aircraft,
        "dataset_codes": [code.value for code in codes],
        "bucket": request.bucket,
        "generated_at": dashboard.get("generated_at"),
        "dashboard": dashboard,
        "utilisation": _period_utilisation(dashboard),
        "domains": [_domain_summary(code, grouped.get(code.value, [])) for code in codes],
        "include_domain_details": request.include_domain_details,
    }
    data["narrative"] = _narrative(data)
    return data


def _pdf_chart(title: str, labels: list[str], values: list[float]) -> Drawing:
    width, height = 245 * mm, 72 * mm
    drawing = Drawing(width, height)
    chart = VerticalBarChart()
    chart.x, chart.y = 28, 28
    chart.height, chart.width = height - 50, width - 45
    chart.data = [values or [0]]
    chart.categoryAxis.categoryNames = [label[:10] for label in (labels or ["None"])]
    chart.categoryAxis.labels.fontSize = 6
    chart.categoryAxis.labels.angle = 30
    chart.categoryAxis.labels.dy = -8
    chart.valueAxis.valueMin = 0
    chart.valueAxis.labels.fontSize = 7
    chart.bars[0].fillColor = colors.HexColor("#557FA9")
    drawing.add(chart)
    drawing.add(String(width / 2, height - 12, title, textAnchor="middle", fontSize=9, fillColor=colors.HexColor("#172033")))
    return drawing


def _styled_table(rows: list[list[Any]], widths: list[float]) -> Table:
    table = Table(rows, colWidths=widths, repeatRows=1)
    table.setStyle(TableStyle([
        ("BACKGROUND", (0, 0), (-1, 0), colors.HexColor("#EAF0F5")),
        ("GRID", (0, 0), (-1, -1), .35, colors.HexColor("#BCC7D2")),
        ("FONTNAME", (0, 0), (-1, 0), "Helvetica-Bold"),
        ("FONTSIZE", (0, 0), (-1, -1), 7),
        ("VALIGN", (0, 0), (-1, -1), "TOP"),
        ("PADDING", (0, 0), (-1, -1), 3),
    ]))
    return table


def _pdf(snapshot: wp.ReliabilityWorkbookReportSnapshot, layout: wp.ReliabilityReportLayout) -> bytes:
    data = snapshot.rendered_data or {}
    buffer = BytesIO()
    styles = getSampleStyleSheet()
    styles.add(ParagraphStyle(name="SmallReliability", parent=styles["BodyText"], fontSize=7.5, leading=10))
    doc = SimpleDocTemplate(buffer, pagesize=landscape(A4), leftMargin=10 * mm, rightMargin=10 * mm, topMargin=10 * mm, bottomMargin=13 * mm, title=str(data.get("title") or layout.name))
    story: list[Any] = [
        Paragraph("CONTROLLED RELIABILITY MANAGEMENT REPORT", styles["Heading4"]),
        Paragraph(html.escape(str(data.get("title") or layout.name)), styles["Title"]),
        Paragraph(f"Period: {snapshot.period_start} to {snapshot.period_end} &nbsp;&nbsp; Scope: {html.escape(', '.join(snapshot.aircraft_filter or []) or 'Fleet')}", styles["SmallReliability"]),
        Spacer(1, 4 * mm), Paragraph("Management summary", styles["Heading2"]),
    ]
    story.extend(Paragraph(html.escape(str(sentence)), styles["BodyText"]) for sentence in data.get("narrative", []))
    metrics = [["Metric", "Value", "Unit", "Vs prior"]]
    for item in data.get("dashboard", {}).get("summary", [])[:10]:
        value = "—" if item.get("value") is None else f"{float(item['value']):,.3f}"
        delta = "—" if item.get("delta_pct") is None else f"{float(item['delta_pct']):+.1f}%"
        metrics.append([item.get("label") or item.get("code"), value, item.get("unit") or "", delta])
    story.extend([Spacer(1, 4 * mm), _styled_table(metrics, [78 * mm, 30 * mm, 28 * mm, 28 * mm])])
    points = data.get("utilisation", {}).get("points", [])
    story.extend([Spacer(1, 5 * mm), KeepTogether([Paragraph("Aircraft and fleet utilisation", styles["Heading2"]), _pdf_chart("Flight hours by reporting bucket", [str(item.get("label") or "") for item in points], [float(item.get("flight_hours") or 0) for item in points])])])
    domains = [["Code", "Domain", "Records", "Aircraft", "Leading ATA"]]
    for item in data.get("domains", []):
        domains.append([item["code"], item["name"], item["count"], item["aircraft_count"], ", ".join(f"{x['label']} ({x['count']})" for x in item.get("top_ata", [])[:3])])
    story.extend([PageBreak(), Paragraph("Controlled Reliability domain overview", styles["Heading2"]), _styled_table(domains, [18 * mm, 74 * mm, 22 * mm, 22 * mm, 88 * mm]), Spacer(1, 5 * mm), Paragraph("Data quality and analytical cautions", styles["Heading2"])])
    warnings = data.get("dashboard", {}).get("warnings", [])
    if warnings:
        story.extend(Paragraph(html.escape(str(warning)), styles["SmallReliability"]) for warning in warnings)
    else:
        story.append(Paragraph("No dashboard-level data completeness warning was raised.", styles["SmallReliability"]))

    def footer(canvas, doc_obj):
        canvas.saveState()
        canvas.setFont("Helvetica", 6.5)
        canvas.setFillColor(colors.HexColor("#586474"))
        text = f"Snapshot {snapshot.id} | {layout.code} Rev {layout.revision} | SHA-256 {snapshot.sha256_hash} | Page {doc_obj.page}"
        canvas.drawString(10 * mm, 6 * mm, text[:190])
        canvas.restoreState()

    doc.build(story, onFirstPage=footer, onLaterPages=footer)
    return buffer.getvalue()


def _snapshot(db: Session, amo_id: str, report_id: int) -> wp.ReliabilityWorkbookReportSnapshot:
    row = db.query(wp.ReliabilityWorkbookReportSnapshot).filter(
        wp.ReliabilityWorkbookReportSnapshot.id == report_id,
        wp.ReliabilityWorkbookReportSnapshot.amo_id == amo_id,
    ).one_or_none()
    if not row:
        raise HTTPException(status_code=404, detail="Reliability report snapshot not found.")
    return row


def register(router: APIRouter) -> None:
    @router.post("/workbook-parity/management-reports/render", status_code=201)
    def render_management_report(payload: ManagementReportRequest, current_user: account_models.User = Depends(get_current_active_user), db: Session = Depends(get_write_db)):
        amo_id = _amo_id(current_user)
        _require_analysis(current_user)
        layout = _ensure_layout(db, amo_id, current_user.id)
        data = _build_data(db, amo_id, payload)
        snapshot = wp.ReliabilityWorkbookReportSnapshot(
            amo_id=amo_id, layout_id=layout.id, period_start=payload.period_start, period_end=payload.period_end,
            aircraft_filter=payload.aircraft, rendered_data=data, rendered_html="", sha256_hash="0" * 64,
            generated_by_user_id=current_user.id,
        )
        db.add(snapshot)
        db.flush()
        # The hash is over the retained HTML bytes. The visible control line contains
        # the snapshot identity but deliberately does not recursively embed the final hash.
        rendered = _render_html(data, snapshot.id)
        checksum = hashlib.sha256(rendered.encode("utf-8")).hexdigest()
        snapshot.rendered_html = rendered
        snapshot.sha256_hash = checksum
        db.commit()
        db.refresh(snapshot)
        return {
            "id": snapshot.id, "layout_id": layout.id, "layout_code": layout.code, "layout_name": layout.name,
            "period_start": snapshot.period_start, "period_end": snapshot.period_end, "aircraft": snapshot.aircraft_filter,
            "sha256_hash": snapshot.sha256_hash, "generated_at": snapshot.generated_at,
            "download_url": f"/reliability/workbook-parity/reports/{snapshot.id}/html",
            "view_url": f"/reliability/workbook-parity/reports/{snapshot.id}/view",
            "pdf_url": f"/reliability/workbook-parity/reports/{snapshot.id}/pdf",
            "data_url": f"/reliability/workbook-parity/reports/{snapshot.id}/data",
        }

    @router.get("/workbook-parity/reports/{report_id}/data")
    def report_data(report_id: int, current_user: account_models.User = Depends(get_current_active_user), db: Session = Depends(get_write_db)):
        row = _snapshot(db, _amo_id(current_user), report_id)
        layout = db.query(wp.ReliabilityReportLayout).filter(wp.ReliabilityReportLayout.id == row.layout_id).one()
        return {"id": row.id, "layout_code": layout.code, "layout_name": layout.name, "period_start": row.period_start, "period_end": row.period_end, "aircraft": row.aircraft_filter, "sha256_hash": row.sha256_hash, "generated_at": row.generated_at, "rendered_data": row.rendered_data}

    @router.get("/workbook-parity/reports/{report_id}/view", response_class=Response)
    def view_report(report_id: int, current_user: account_models.User = Depends(get_current_active_user), db: Session = Depends(get_write_db)):
        row = _snapshot(db, _amo_id(current_user), report_id)
        return Response(content=row.rendered_html, media_type="text/html", headers={"ETag": row.sha256_hash, "Cache-Control": "private, no-store"})

    @router.get("/workbook-parity/reports/{report_id}/pdf", response_class=Response)
    def report_pdf(report_id: int, current_user: account_models.User = Depends(get_current_active_user), db: Session = Depends(get_write_db)):
        row = _snapshot(db, _amo_id(current_user), report_id)
        layout = db.query(wp.ReliabilityReportLayout).filter(wp.ReliabilityReportLayout.id == row.layout_id).one()
        output = _pdf(row, layout)
        filename = f"reliability-{layout.code.lower()}-{row.period_start}-{row.period_end}-snapshot-{row.id}.pdf"
        return Response(content=output, media_type="application/pdf", headers={"Content-Disposition": f'attachment; filename="{filename}"', "ETag": row.sha256_hash, "Cache-Control": "private, no-store"})
