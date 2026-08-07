from __future__ import annotations

import hashlib
import html
import os
from io import BytesIO
from pathlib import Path
from typing import Any

from fastapi import APIRouter, Depends, HTTPException, Response
from fastapi.responses import FileResponse
from reportlab.lib import colors
from reportlab.lib.pagesizes import A4
from reportlab.lib.styles import ParagraphStyle, getSampleStyleSheet
from reportlab.lib.units import mm
from reportlab.pdfgen import canvas as pdf_canvas
from reportlab.platypus import PageBreak, Paragraph, SimpleDocTemplate, Spacer, Table, TableStyle
from sqlalchemy.orm import Session

from amodb.apps.accounts import models as account_models
from amodb.database import get_write_db
from amodb.security import get_current_active_user

from .formal_reporting import (
    ANALYSIS_ROLES,
    _amo_id,
    _report,
    _report_dict,
    _require_editable,
    _require_role,
    completeness_result,
)
from .formal_reporting_charts import chart_manifest, drawing_for_spec, publication_chart_specs, svg_for_spec
from .formal_reporting_history import build_long_term_history
from .formal_reporting_models import FormalReportStatus, ReliabilityFormalReport, ReliabilityFormalReportSection

_RENDERABLE = {
    FormalReportStatus.DRAFT.value,
    FormalReportStatus.DATA_REVIEW.value,
    FormalReportStatus.TECHNICAL_REVIEW.value,
    FormalReportStatus.QUALITY_REVIEW.value,
}
_STORAGE_ROOT = Path(os.getenv("RELIABILITY_REPORT_STORAGE_DIR", "uploads/reliability_reports")).resolve()
_STORAGE_ROOT.mkdir(parents=True, exist_ok=True)


def _safe_path(report: ReliabilityFormalReport) -> Path:
    folder = (_STORAGE_ROOT / report.amo_id / report.id).resolve()
    if not str(folder).startswith(str(_STORAGE_ROOT)):
        raise HTTPException(status_code=500, detail="Reliability report storage path is invalid.")
    folder.mkdir(parents=True, exist_ok=True)
    path = (folder / f"revision-{report.revision}.pdf").resolve()
    if not str(path).startswith(str(_STORAGE_ROOT)):
        raise HTTPException(status_code=500, detail="Reliability report storage path is invalid.")
    return path


def _metric_map(dashboard: dict[str, Any]) -> dict[str, dict[str, Any]]:
    return {str(item.get("code")): item for item in dashboard.get("summary", [])}


def _section_payloads(report: ReliabilityFormalReport) -> dict[str, dict[str, Any]]:
    dashboard = (report.calculation_snapshots_json or {}).get("dashboard") or {}
    long_term_history = (report.calculation_snapshots_json or {}).get("long_term_history") or {}
    metrics = _metric_map(dashboard)
    return {
        "document_control": {
            "report_number": report.report_number,
            "revision": report.revision,
            "period_type": report.period_type,
            "period_start": report.period_start.isoformat(),
            "period_end": report.period_end.isoformat(),
            "data_cutoff_at": report.data_cutoff_at.isoformat() if report.data_cutoff_at else None,
            "profile_code": report.profile_code_snapshot,
            "profile_version": report.profile_version_snapshot,
            "effectivity": report.effectivity_json,
        },
        "executive_assessment": {
            "summary_metrics": dashboard.get("summary", []),
            "warnings": dashboard.get("warnings", []),
        },
        "utilisation": {
            "flight_hours": metrics.get("flight_hours"),
            "flight_cycles": metrics.get("flight_cycles"),
            "trend": dashboard.get("time_series", []),
            "long_term_history": long_term_history.get("summaries", []),
        },
        "dispatch_reliability": {
            "metric": metrics.get("dispatch_reliability_pct"),
            "trend": dashboard.get("time_series", []),
            "denominator_policy": next(
                (item for item in report.formula_revisions_json or [] if item.get("code") == "dispatch_reliability_pct"),
                None,
            ),
        },
        "operational_interruptions": {
            "event_mix": dashboard.get("event_mix", []),
            "station_delay": dashboard.get("station_delay", []),
            "route_delay": dashboard.get("route_delay", []),
            "ata_pareto": dashboard.get("ata_pareto", []),
            "aircraft_performance": dashboard.get("aircraft_performance", []),
        },
        "component_reliability": {
            "component_reliability": dashboard.get("component_reliability", []),
            "component_removal_age": dashboard.get("component_removal_age", []),
        },
        "shop_reports": {"shop_visit_trend": dashboard.get("shop_visit_trend", [])},
        "propulsion_health": {"engine_status": dashboard.get("engine_status", [])},
        "deferred_defects": {
            "status": dashboard.get("deferral_status", []),
            "expiry": dashboard.get("deferral_expiry", []),
            "categories": dashboard.get("deferral_categories", []),
            "extensions": dashboard.get("deferral_extensions", []),
            "repeats": dashboard.get("deferral_repeats", []),
            "closure": dashboard.get("deferral_closure", []),
        },
        "statistical_analysis": {
            "formulae": report.formula_revisions_json,
            "time_series": dashboard.get("time_series", []),
            "ata_pareto": dashboard.get("ata_pareto", []),
            "aircraft_performance": dashboard.get("aircraft_performance", []),
            "long_term_history": long_term_history,
        },
        "fracas": {
            "stages": dashboard.get("fracas_stages", []),
            "ageing": dashboard.get("fracas_ageing", []),
            "root_causes": dashboard.get("root_causes", []),
            "effectiveness": dashboard.get("effectiveness", []),
            "actions": dashboard.get("fracas_actions", []),
            "reopened": dashboard.get("fracas_reopened", []),
        },
        "data_quality": {
            "warnings": dashboard.get("warnings", []),
            "data_quality": dashboard.get("data_quality", []),
            "source_health": dashboard.get("source_health", []),
            "source_population": report.source_population_json,
            "long_term_source_policy": long_term_history.get("source_policy"),
        },
        "appendices": {
            "source_population": report.source_population_json,
            "formula_revisions": report.formula_revisions_json,
            "regulatory_manifest": report.regulatory_manifest,
            "publication_chart_manifest": (report.chart_data_json or {}).get("publication_chart_manifest", []),
        },
    }


def _populate_sections(db: Session, report: ReliabilityFormalReport) -> None:
    payloads = _section_payloads(report)
    rows = db.query(ReliabilityFormalReportSection).filter(
        ReliabilityFormalReportSection.amo_id == report.amo_id,
        ReliabilityFormalReportSection.report_id == report.id,
    ).all()
    for row in rows:
        row.computed_data = payloads.get(row.section_code, row.computed_data or {})


def _display_value(value: Any) -> str:
    if value is None:
        return "WITHHELD / not available"
    if isinstance(value, float):
        return f"{value:,.3f}"
    if isinstance(value, (dict, list)):
        return html.escape(str(value))
    return html.escape(str(value))


def _metric_table(metrics: list[dict[str, Any]]) -> str:
    if not metrics:
        return "<p class='empty'>No governed metric is available for this section.</p>"
    rows = []
    for item in metrics[:20]:
        value = item.get("value")
        denominator = item.get("denominator")
        rows.append(
            "<tr>"
            f"<td>{html.escape(str(item.get('label') or item.get('code') or 'Metric'))}</td>"
            f"<td>{_display_value(value)}</td>"
            f"<td>{html.escape(str(item.get('unit') or ''))}</td>"
            f"<td>{_display_value(denominator)}</td>"
            f"<td>{html.escape(str(item.get('formula_code') or '—'))}</td>"
            "</tr>"
        )
    return (
        "<div class='table-wrap'><table><thead><tr>"
        "<th>Metric</th><th>Value</th><th>Unit</th><th>Denominator</th><th>Formula</th>"
        "</tr></thead><tbody>" + "".join(rows) + "</tbody></table></div>"
    )


def _commentary_html(items: list[dict[str, Any]]) -> str:
    if not items:
        return "<p class='empty'>No controlled engineering commentary has been accepted for this section.</p>"
    output = []
    for item in items:
        text_value = str(item.get("text") or item.get("comment") or "").strip()
        if not text_value:
            continue
        kind = str(item.get("kind") or "ENGINEERING_JUDGEMENT").upper()
        evidence = item.get("evidence_refs") or []
        suffix = f" · {len(evidence)} evidence reference(s)" if evidence else ""
        output.append(
            f"<div class='comment'><strong>{html.escape(kind)}</strong>"
            f"<p>{html.escape(text_value)}</p><small>{html.escape(suffix.strip(' ·'))}</small></div>"
        )
    return "".join(output) or "<p class='empty'>No controlled engineering commentary has been accepted for this section.</p>"


def json_dumps(value: Any) -> str:
    import json
    return json.dumps(value, indent=2, sort_keys=True, default=str)


def _render_html(report: ReliabilityFormalReport, sections: list[ReliabilityFormalReportSection]) -> str:
    dashboard = (report.calculation_snapshots_json or {}).get("dashboard") or {}
    scope = report.effectivity_json or {}
    aircraft = scope.get("aircraft_serial_numbers") or []
    scope_text = ", ".join(aircraft) if aircraft else "Tenant fleet"
    source_hash = (report.source_population_json or {}).get("source_identity_sha256") or "not frozen"
    chart_groups: dict[str, list[Any]] = {}
    for spec in publication_chart_specs(report):
        chart_groups.setdefault(spec.section_code, []).append(spec)
    body: list[str] = []
    for section in sections:
        computed = section.computed_data or {}
        body.append(
            f"<section id='{html.escape(section.section_code)}'>"
            f"<div class='section-head'><span>{section.sequence:02d}</span><h2>{html.escape(section.title)}</h2>"
            f"<b>{html.escape(section.status)}</b></div>"
        )
        if section.section_code == "executive_assessment":
            body.append(_metric_table(dashboard.get("summary", [])))
        elif section.section_code == "utilisation":
            body.append(_metric_table([
                item for item in dashboard.get("summary", [])
                if item.get("code") in {"flight_hours", "flight_cycles"}
            ]))
        elif section.section_code == "dispatch_reliability":
            metric = computed.get("metric")
            body.append(_metric_table([metric] if metric else []))
        elif section.section_code == "data_quality":
            warnings = computed.get("warnings") or []
            body.append(
                "<div class='warnings'>"
                + ("".join(f"<p>{html.escape(str(item))}</p>" for item in warnings) if warnings else "<p>No dashboard-level warning was retained.</p>")
                + "</div>"
            )
        elif computed:
            body.append(
                f"<details><summary>Retained analytical payload</summary>"
                f"<pre>{html.escape(json_dumps(computed))}</pre></details>"
            )
        else:
            body.append("<p class='empty'>No governed analytical payload is currently mapped to this chapter.</p>")
        if chart_groups.get(section.section_code):
            body.append("<div class='chart-grid'>")
            for spec in chart_groups[section.section_code]:
                body.append(svg_for_spec(spec))
            body.append("</div>")
        body.append("<h3>Engineering interpretation</h3>")
        body.append(_commentary_html(section.commentary or []))
        if section.warnings:
            body.append("<div class='warnings'>" + "".join(f"<p>{html.escape(str(item))}</p>" for item in section.warnings) + "</div>")
        body.append("</section>")

    css = """
    :root{font-family:Inter,Arial,sans-serif;color:#182331;background:#fff}
    *{box-sizing:border-box}body{margin:0;padding:18mm 16mm;font-size:11px;line-height:1.45}
    header{border-bottom:2px solid #25384d;padding-bottom:12px;margin-bottom:18px}
    .kicker{text-transform:uppercase;letter-spacing:.13em;font-size:9px;font-weight:800;color:#536579}
    h1{font-size:23px;margin:4px 0 8px}h2{font-size:16px;margin:0}h3{font-size:11px;margin:14px 0 6px}
    .meta{display:grid;grid-template-columns:repeat(4,minmax(0,1fr));gap:8px;margin-top:12px}
    .meta div{border-left:2px solid #d4dce5;padding-left:7px}.meta span{display:block;color:#647284;font-size:8px;text-transform:uppercase}.meta strong{font-size:10px}
    section{margin:22px 0;break-inside:auto}.section-head{display:grid;grid-template-columns:32px 1fr auto;gap:8px;align-items:center;border-bottom:1px solid #cfd7e1;padding-bottom:5px}
    .section-head span{font-weight:800;color:#6b7786}.section-head b{font-size:8px;border:1px solid #cfd7e1;padding:3px 6px}
    table{width:100%;border-collapse:collapse;margin:9px 0;font-size:9px}th,td{border:1px solid #d8dee6;padding:5px;text-align:left;vertical-align:top}th{background:#eef2f6}
    .chart-grid{display:grid;grid-template-columns:repeat(auto-fit,minmax(320px,1fr));gap:9px;margin:11px 0}.formal-chart{width:100%;height:auto;border:1px solid #d8dee6;background:#fff;padding:4px}.formal-chart text{font-family:Arial,sans-serif;fill:#27333f}
    .comment{border-left:3px solid #536f8d;padding:7px 10px;margin:7px 0;background:#f7f9fb}.comment p{margin:4px 0}.comment small,.empty{color:#667587}
    .warnings{border:1px solid #c9a246;background:#fff9e8;padding:7px;margin:8px 0}.warnings p{margin:3px 0}
    details{margin:8px 0;border:1px solid #d8dee6;padding:7px}pre{white-space:pre-wrap;overflow-wrap:anywhere;font-size:7px;max-height:240px;overflow:auto}
    footer{margin-top:24px;border-top:1px solid #cfd7e1;padding-top:7px;font-family:monospace;font-size:7px;overflow-wrap:anywhere}
    @media print{body{padding:10mm}.comment,table,.section-head,.formal-chart{break-inside:avoid}details pre{max-height:none;overflow:visible}.chart-grid{grid-template-columns:1fr}}
    """
    return f"""<!doctype html><html><head><meta charset='utf-8'><title>{html.escape(report.title)}</title><style>{css}</style></head>
    <body><header><div class='kicker'>Controlled Reliability Programme Report</div><h1>{html.escape(report.title)}</h1>
    <div class='meta'>
      <div><span>Report</span><strong>{html.escape(report.report_number)} Rev {report.revision}</strong></div>
      <div><span>Period</span><strong>{report.period_start} — {report.period_end}</strong></div>
      <div><span>Profile</span><strong>{html.escape(report.profile_code_snapshot)} {html.escape(report.profile_version_snapshot)}</strong></div>
      <div><span>Effectivity</span><strong>{html.escape(scope_text)}</strong></div>
      <div><span>Data cutoff</span><strong>{html.escape(str(report.data_cutoff_at or 'Not frozen'))}</strong></div>
      <div><span>Status</span><strong>{html.escape(report.status)}</strong></div>
      <div><span>Source records</span><strong>{int((report.source_population_json or {}).get('workbook_record_count') or 0) + int((report.source_population_json or {}).get('canonical_event_count') or 0)}</strong></div>
      <div><span>Formula revisions</span><strong>{len(report.formula_revisions_json or [])}</strong></div>
    </div></header>
    {''.join(body)}
    <footer>Source-population SHA-256: {html.escape(source_hash)} · Formal report ID: {html.escape(report.id)} · Retained render hash is stored after generation.</footer>
    </body></html>"""


def _pdf_table(rows: list[list[str]], widths: list[float] | None = None) -> Table:
    table = Table(rows, colWidths=widths, repeatRows=1)
    table.setStyle(TableStyle([
        ("BACKGROUND", (0, 0), (-1, 0), colors.HexColor("#eef2f6")),
        ("GRID", (0, 0), (-1, -1), 0.35, colors.HexColor("#c7d0da")),
        ("FONTNAME", (0, 0), (-1, 0), "Helvetica-Bold"),
        ("FONTSIZE", (0, 0), (-1, -1), 7.2),
        ("VALIGN", (0, 0), (-1, -1), "TOP"),
        ("LEFTPADDING", (0, 0), (-1, -1), 4),
        ("RIGHTPADDING", (0, 0), (-1, -1), 4),
        ("TOPPADDING", (0, 0), (-1, -1), 3),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 3),
    ]))
    return table


def _render_pdf(report: ReliabilityFormalReport, sections: list[ReliabilityFormalReportSection]) -> bytes:
    buffer = BytesIO()
    styles = getSampleStyleSheet()
    small = ParagraphStyle("FormalSmall", parent=styles["BodyText"], fontSize=7.5, leading=10)
    note = ParagraphStyle("FormalNote", parent=small, textColor=colors.HexColor("#59697a"))
    doc = SimpleDocTemplate(
        buffer,
        pagesize=A4,
        leftMargin=13 * mm,
        rightMargin=13 * mm,
        topMargin=13 * mm,
        bottomMargin=15 * mm,
        title=report.title,
        author="AMO Portal",
    )
    story: list[Any] = [
        Paragraph("CONTROLLED RELIABILITY PROGRAMME REPORT", styles["Heading4"]),
        Paragraph(html.escape(report.title), styles["Title"]),
        Paragraph(
            f"Report {html.escape(report.report_number)} Rev {report.revision} | "
            f"{report.period_start} to {report.period_end} | "
            f"{html.escape(report.profile_code_snapshot)} {html.escape(report.profile_version_snapshot)}",
            small,
        ),
        Spacer(1, 4 * mm),
    ]
    dashboard = (report.calculation_snapshots_json or {}).get("dashboard") or {}
    chart_groups: dict[str, list[Any]] = {}
    for spec in publication_chart_specs(report):
        chart_groups.setdefault(spec.section_code, []).append(spec)
    for index, section in enumerate(sections):
        story.append(Paragraph(f"{section.sequence}. {html.escape(section.title)}", styles["Heading2"]))
        story.append(Paragraph(f"Section status: {html.escape(section.status)}", note))
        if section.section_code in {"executive_assessment", "utilisation", "dispatch_reliability"}:
            if section.section_code == "utilisation":
                metrics = [item for item in dashboard.get("summary", []) if item.get("code") in {"flight_hours", "flight_cycles"}]
            elif section.section_code == "dispatch_reliability":
                metrics = [item for item in dashboard.get("summary", []) if item.get("code") == "dispatch_reliability_pct"]
            else:
                metrics = dashboard.get("summary", [])[:12]
            rows = [["Metric", "Value", "Unit", "Denominator", "Formula"]]
            for item in metrics:
                rows.append([
                    str(item.get("label") or item.get("code") or ""),
                    "WITHHELD" if item.get("value") is None else str(item.get("value")),
                    str(item.get("unit") or ""),
                    "—" if item.get("denominator") is None else str(item.get("denominator")),
                    str(item.get("formula_code") or "—"),
                ])
            if len(rows) > 1:
                story.append(_pdf_table(rows, [55 * mm, 28 * mm, 21 * mm, 28 * mm, 44 * mm]))
        if section.section_code == "data_quality":
            warnings = (section.computed_data or {}).get("warnings") or []
            if warnings:
                for warning in warnings:
                    story.append(Paragraph(f"• {html.escape(str(warning))}", small))
            else:
                story.append(Paragraph("No dashboard-level warning was retained.", small))
        for spec in chart_groups.get(section.section_code, []):
            drawing = drawing_for_spec(spec, width=500, height=245)
            drawing.hAlign = "CENTER"
            story.append(Spacer(1, 2 * mm))
            story.append(drawing)
            story.append(Spacer(1, 2 * mm))
        commentary = section.commentary or []
        story.append(Paragraph("Engineering interpretation", styles["Heading3"]))
        if commentary:
            for item in commentary:
                kind = html.escape(str(item.get("kind") or "ENGINEERING_JUDGEMENT"))
                text_value = html.escape(str(item.get("text") or item.get("comment") or ""))
                story.append(Paragraph(f"<b>{kind}</b> — {text_value}", small))
        else:
            story.append(Paragraph("No controlled engineering commentary has been accepted for this section.", note))
        if index < len(sections) - 1 and (index + 1) % 5 == 0:
            story.append(PageBreak())
        else:
            story.append(Spacer(1, 3 * mm))

    def footer(canvas, doc_obj):
        canvas.saveState()
        canvas.setFont("Helvetica", 6.5)
        canvas.setFillColor(colors.HexColor("#59697a"))
        source_hash = (report.source_population_json or {}).get("source_identity_sha256") or "not frozen"
        footer_text = (
            f"{report.report_number} Rev {report.revision} | {report.profile_code_snapshot} "
            f"| Source {source_hash[:16]}… | Page {doc_obj.page}"
        )
        canvas.drawString(13 * mm, 7 * mm, footer_text)
        canvas.restoreState()

    def invariant_canvas(*args, **kwargs):
        kwargs["invariant"] = 1
        return pdf_canvas.Canvas(*args, **kwargs)

    doc.build(story, onFirstPage=footer, onLaterPages=footer, canvasmaker=invariant_canvas)
    return buffer.getvalue()


def _write_pdf(report: ReliabilityFormalReport, pdf_bytes: bytes) -> str:
    path = _safe_path(report)
    tmp = path.with_suffix(".tmp")
    tmp.write_bytes(pdf_bytes)
    os.replace(tmp, path)
    return str(path)


def _ensure_long_term_history(db: Session, report: ReliabilityFormalReport) -> None:
    calculations = dict(report.calculation_snapshots_json or {})
    if calculations.get("long_term_history") is not None:
        return
    history = build_long_term_history(db, report)
    calculations["long_term_history"] = history
    report.calculation_snapshots_json = calculations
    charts = dict(report.chart_data_json or {})
    charts["long_term_history"] = history.get("series", [])
    report.chart_data_json = charts


def render_formal_report(db: Session, report: ReliabilityFormalReport) -> ReliabilityFormalReport:
    _require_editable(report)
    if report.status not in _RENDERABLE:
        raise HTTPException(status_code=409, detail="Return the report to a review stage before rendering a new controlled artifact.")
    if not report.data_cutoff_at or not report.effectivity_frozen_at:
        raise HTTPException(status_code=409, detail="Freeze data cutoff and fleet effectivity before rendering.")
    if not (report.calculation_snapshots_json or {}).get("dashboard"):
        raise HTTPException(status_code=409, detail="A governed Reliability calculation snapshot is required before rendering.")
    _ensure_long_term_history(db, report)
    specs = publication_chart_specs(report)
    charts = dict(report.chart_data_json or {})
    charts["publication_chart_manifest"] = chart_manifest(specs)
    report.chart_data_json = charts
    _populate_sections(db, report)
    db.flush()
    sections = db.query(ReliabilityFormalReportSection).filter(
        ReliabilityFormalReportSection.amo_id == report.amo_id,
        ReliabilityFormalReportSection.report_id == report.id,
    ).order_by(ReliabilityFormalReportSection.sequence).all()
    rendered_html = _render_html(report, sections)
    html_hash = hashlib.sha256(rendered_html.encode("utf-8")).hexdigest()
    pdf_bytes = _render_pdf(report, sections)
    pdf_hash = hashlib.sha256(pdf_bytes).hexdigest()
    storage_ref = _write_pdf(report, pdf_bytes)

    report.rendered_html = rendered_html
    report.html_sha256 = html_hash
    report.pdf_storage_ref = storage_ref
    report.pdf_sha256 = pdf_hash
    report.pdf_size_bytes = len(pdf_bytes)
    completeness_result(db, report, persist=True)
    db.commit()
    db.refresh(report)
    return report


def _stored_pdf(report: ReliabilityFormalReport) -> Path:
    if not report.pdf_storage_ref or not report.pdf_sha256:
        raise HTTPException(status_code=404, detail="Formal Reliability PDF has not been generated.")
    path = Path(report.pdf_storage_ref).resolve()
    if not str(path).startswith(str(_STORAGE_ROOT)) or not path.is_file():
        raise HTTPException(status_code=404, detail="Retained formal Reliability PDF is unavailable.")
    digest = hashlib.sha256(path.read_bytes()).hexdigest()
    if digest != report.pdf_sha256:
        raise HTTPException(status_code=409, detail="Retained formal Reliability PDF failed SHA-256 integrity verification.")
    return path


def register(router: APIRouter) -> None:
    @router.post("/formal-reporting/reports/{report_id}/render")
    def render_report(
        report_id: str,
        current_user: account_models.User = Depends(get_current_active_user),
        db: Session = Depends(get_write_db),
    ):
        amo_id = _amo_id(current_user)
        _require_role(current_user, ANALYSIS_ROLES, "Reliability report preparation permission is required.")
        row = render_formal_report(db, _report(db, amo_id, report_id))
        return _report_dict(db, row, detail=True)

    @router.get("/formal-reporting/reports/{report_id}/view", response_class=Response)
    def view_report(
        report_id: str,
        current_user: account_models.User = Depends(get_current_active_user),
        db: Session = Depends(get_write_db),
    ):
        amo_id = _amo_id(current_user)
        _require_role(current_user, ANALYSIS_ROLES, "Reliability analysis permission is required.")
        row = _report(db, amo_id, report_id)
        if not row.rendered_html or not row.html_sha256:
            raise HTTPException(status_code=404, detail="Formal Reliability HTML has not been generated.")
        digest = hashlib.sha256(row.rendered_html.encode("utf-8")).hexdigest()
        if digest != row.html_sha256:
            raise HTTPException(status_code=409, detail="Retained formal Reliability HTML failed SHA-256 integrity verification.")
        return Response(
            content=row.rendered_html,
            media_type="text/html",
            headers={"ETag": row.html_sha256, "Cache-Control": "private, no-store"},
        )

    @router.get("/formal-reporting/reports/{report_id}/pdf")
    def download_pdf(
        report_id: str,
        current_user: account_models.User = Depends(get_current_active_user),
        db: Session = Depends(get_write_db),
    ):
        amo_id = _amo_id(current_user)
        _require_role(current_user, ANALYSIS_ROLES, "Reliability analysis permission is required.")
        row = _report(db, amo_id, report_id)
        path = _stored_pdf(row)
        filename = f"{row.report_number}-rev-{row.revision}.pdf".replace("/", "-")
        return FileResponse(
            path=str(path),
            media_type="application/pdf",
            filename=filename,
            headers={"ETag": row.pdf_sha256 or "", "Cache-Control": "private, no-store"},
        )

    @router.get("/formal-reporting/reports/{report_id}/retained-data")
    def retained_data(
        report_id: str,
        current_user: account_models.User = Depends(get_current_active_user),
        db: Session = Depends(get_write_db),
    ):
        amo_id = _amo_id(current_user)
        _require_role(current_user, ANALYSIS_ROLES, "Reliability analysis permission is required.")
        row = _report(db, amo_id, report_id)
        return {
            "id": row.id,
            "report_number": row.report_number,
            "revision": row.revision,
            "status": row.status,
            "period_start": row.period_start,
            "period_end": row.period_end,
            "data_cutoff_at": row.data_cutoff_at,
            "effectivity": row.effectivity_json,
            "source_population": row.source_population_json,
            "formula_revisions": row.formula_revisions_json,
            "calculation_snapshots": row.calculation_snapshots_json,
            "chart_data": row.chart_data_json,
            "data_quality": row.data_quality_json,
            "regulatory_manifest": row.regulatory_manifest,
            "completeness": row.completeness_json,
            "html_sha256": row.html_sha256,
            "pdf_sha256": row.pdf_sha256,
        }
