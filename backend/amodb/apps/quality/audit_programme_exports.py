from __future__ import annotations

from datetime import date, datetime, time, timedelta, timezone
from io import BytesIO
from typing import Any, Mapping
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

from reportlab.lib import colors
from reportlab.lib.enums import TA_CENTER
from reportlab.lib.pagesizes import A4, landscape
from reportlab.lib.styles import ParagraphStyle, getSampleStyleSheet
from reportlab.lib.units import mm
from reportlab.platypus import Paragraph, SimpleDocTemplate, Spacer, Table, TableStyle


def _text(value: Any) -> str:
    return str(value or "").strip()


def _escape_ics(value: Any) -> str:
    return (
        _text(value)
        .replace("\\", "\\\\")
        .replace(";", "\\;")
        .replace(",", "\\,")
        .replace("\r\n", "\\n")
        .replace("\n", "\\n")
    )


def _approval_value(programme: Any, field: str, people: Mapping[str, str]) -> str:
    user_id = _text(getattr(programme, f"{field}_by_user_id", None))
    at = getattr(programme, f"{field}_at", None)
    if not at:
        return "Pending"
    name = people.get(user_id, user_id or "Recorded user")
    return f"{name} · {at.strftime('%d %b %Y %H:%M UTC')}"


def _item_dates(programme: Any, item: Any) -> list[tuple[date, date]]:
    if _text(getattr(item, "recurrence", None)).upper() == "FIXED_DATES":
        rows: list[tuple[date, date]] = []
        duration = max(1, int(getattr(item, "default_duration_days", 1) or 1))
        for month_day in list(getattr(item, "fixed_dates", None) or []):
            try:
                start = date.fromisoformat(f"{programme.programme_year}-{month_day}")
            except ValueError:
                continue
            rows.append((start, start + timedelta(days=duration - 1)))
        return rows
    start = getattr(item, "target_start", None)
    if not start:
        return []
    return [(start, getattr(item, "target_end", None) or start)]


def _team(item: Any, people: Mapping[str, str]) -> str:
    rows: list[str] = []
    for label, user_id in (
        ("Lead", getattr(item, "lead_auditor_user_id", None)),
        ("Observer", getattr(item, "observer_auditor_user_id", None)),
        ("Auditee", getattr(item, "auditee_user_id", None)),
    ):
        key = _text(user_id)
        if key:
            rows.append(f"{label}: {people.get(key, key)}")
    for user_id in list(getattr(item, "supporting_auditor_user_ids", None) or []):
        key = _text(user_id)
        if key:
            rows.append(f"Auditor: {people.get(key, key)}")
    return "\n".join(rows) or "To be assigned"


def audit_programme_pdf(programme: Any, people: Mapping[str, str]) -> bytes:
    """Render the approved programme as a controlled, print-ready schedule."""
    stream = BytesIO()
    styles = getSampleStyleSheet()
    body = ParagraphStyle("ProgrammeBody", parent=styles["BodyText"], fontSize=7.2, leading=9)
    heading = ParagraphStyle(
        "ProgrammeHeading",
        parent=styles["Title"],
        alignment=TA_CENTER,
        fontSize=15,
        leading=18,
        textColor=colors.HexColor("#172033"),
    )

    def page(canvas, document) -> None:
        canvas.saveState()
        canvas.setFont("Helvetica", 7)
        canvas.setFillColor(colors.HexColor("#526078"))
        canvas.drawString(14 * mm, 8 * mm, f"Controlled audit programme · {programme.programme_ref}")
        canvas.drawRightString(283 * mm, 8 * mm, f"Page {document.page}")
        canvas.restoreState()

    document = SimpleDocTemplate(
        stream,
        pagesize=landscape(A4),
        leftMargin=14 * mm,
        rightMargin=14 * mm,
        topMargin=13 * mm,
        bottomMargin=14 * mm,
        title=f"{programme.programme_ref} {programme.title}",
        author="AMO Portal Quality Assurance",
    )
    story: list[Any] = [
        Paragraph(_text(programme.title), heading),
        Paragraph(
            f"<b>{programme.programme_ref}</b> · Revision {programme.revision_no} · "
            f"{programme.period_start.strftime('%d %b %Y')} to {programme.period_end.strftime('%d %b %Y')} · "
            f"Status: {_text(programme.status).replace('_', ' ').title()}",
            ParagraphStyle("ProgrammeMeta", parent=body, alignment=TA_CENTER, fontSize=8.5, leading=11),
        ),
        Spacer(1, 4 * mm),
    ]
    approval_rows = [
        ["Prepared / submitted", _approval_value(programme, "submitted", people)],
        ["Quality Manager review", _approval_value(programme, "quality_reviewed", people)],
        ["Accountable Executive approval", _approval_value(programme, "approved", people)],
    ]
    approval_table = Table(approval_rows, colWidths=[52 * mm, 212 * mm])
    approval_table.setStyle(TableStyle([
        ("BACKGROUND", (0, 0), (0, -1), colors.HexColor("#eef3fb")),
        ("FONTNAME", (0, 0), (0, -1), "Helvetica-Bold"),
        ("FONTSIZE", (0, 0), (-1, -1), 8),
        ("GRID", (0, 0), (-1, -1), 0.35, colors.HexColor("#b9c5d8")),
        ("VALIGN", (0, 0), (-1, -1), "MIDDLE"),
        ("TOPPADDING", (0, 0), (-1, -1), 4),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 4),
    ]))
    story.extend([approval_table, Spacer(1, 4 * mm)])

    rows: list[list[Any]] = [["Date / cadence", "Audit area", "Scope & criteria", "Audit team / auditee", "Distribution"]]
    for item in list(getattr(programme, "items", None) or []):
        dates = _item_dates(programme, item)
        date_value = "\n".join(
            start.strftime("%d %b %Y") if start == end else f"{start.strftime('%d %b')} – {end.strftime('%d %b %Y')}"
            for start, end in dates
        ) or _text(getattr(item, "recurrence", "Unscheduled")).replace("_", " ").title()
        criteria = "; ".join(_text(value) for value in list(getattr(item, "criteria", None) or []) if _text(value))
        area = getattr(getattr(item, "universe_item", None), "display_label", None) or item.title
        distribution = "Auditors" if bool(getattr(item, "notify_auditors", False)) else ""
        if bool(getattr(item, "notify_auditees", False)):
            distribution = f"{distribution}; Auditee" if distribution else "Auditee"
        rows.append([
            Paragraph(date_value.replace("\n", "<br/>"), body),
            Paragraph(f"<b>{_text(area)}</b><br/>{_text(item.audit_type).replace('_', ' ').title()}", body),
            Paragraph(f"{_text(item.scope)}<br/><i>{criteria or 'Criteria not stated'}</i>", body),
            Paragraph(_team(item, people).replace("\n", "<br/>"), body),
            Paragraph(distribution or "Portal only", body),
        ])
    table = Table(rows, repeatRows=1, colWidths=[35 * mm, 48 * mm, 83 * mm, 63 * mm, 35 * mm])
    table.setStyle(TableStyle([
        ("BACKGROUND", (0, 0), (-1, 0), colors.HexColor("#173a70")),
        ("TEXTCOLOR", (0, 0), (-1, 0), colors.white),
        ("FONTNAME", (0, 0), (-1, 0), "Helvetica-Bold"),
        ("FONTSIZE", (0, 0), (-1, 0), 8),
        ("GRID", (0, 0), (-1, -1), 0.35, colors.HexColor("#b9c5d8")),
        ("VALIGN", (0, 0), (-1, -1), "TOP"),
        ("ROWBACKGROUNDS", (0, 1), (-1, -1), [colors.white, colors.HexColor("#f7f9fc")]),
        ("TOPPADDING", (0, 0), (-1, -1), 5),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 5),
    ]))
    story.append(table)
    document.build(story, onFirstPage=page, onLaterPages=page)
    return stream.getvalue()


def audit_programme_ics(
    programme: Any,
    people: Mapping[str, str],
    timezone_name: str = "UTC",
) -> str:
    """Create a portable snapshot; live updates use the personal subscription feed."""
    now = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    try:
        calendar_zone = ZoneInfo(timezone_name)
    except ZoneInfoNotFoundError:
        timezone_name = "UTC"
        calendar_zone = ZoneInfo("UTC")
    lines = [
        "BEGIN:VCALENDAR",
        "VERSION:2.0",
        "PRODID:-//AMO Portal//Approved Quality Audit Programme//EN",
        "CALSCALE:GREGORIAN",
        "METHOD:PUBLISH",
        f"X-WR-CALNAME:{_escape_ics(programme.programme_ref + ' · ' + programme.title)}",
        f"X-WR-TIMEZONE:{_escape_ics(timezone_name)}",
        "X-WR-CALDESC:Controlled snapshot. Subscribe to the AMO Portal operations calendar for automatic updates.",
    ]
    for item in list(getattr(programme, "items", None) or []):
        start_time = getattr(item, "default_start_time", None) or time(hour=9)
        end_time = getattr(item, "default_end_time", None) or time(hour=17)
        for index, (start, end) in enumerate(_item_dates(programme, item), start=1):
            uid = f"audit-programme:{programme.id}:{item.id}:{start.isoformat()}:{index}@amo-portal"
            starts_at = datetime.combine(start, start_time, tzinfo=calendar_zone).astimezone(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
            ends_at = datetime.combine(end, end_time, tzinfo=calendar_zone).astimezone(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
            area = getattr(getattr(item, "universe_item", None), "display_label", None) or item.title
            lines.extend([
                "BEGIN:VEVENT",
                f"UID:{_escape_ics(uid)}",
                f"DTSTAMP:{now}",
                f"DTSTART:{starts_at}",
                f"DTEND:{ends_at}",
                f"SUMMARY:{_escape_ics(programme.programme_ref + ' · ' + area)}",
                f"DESCRIPTION:{_escape_ics(item.scope + ' | ' + _team(item, people))}",
                f"LOCATION:{_escape_ics(getattr(item, 'default_location', None))}",
                f"STATUS:{'CONFIRMED' if programme.status == 'ACTIVE' else 'TENTATIVE'}",
                f"SEQUENCE:{int(programme.revision_no)}",
                "END:VEVENT",
            ])
    lines.append("END:VCALENDAR")
    return "\r\n".join(lines) + "\r\n"
