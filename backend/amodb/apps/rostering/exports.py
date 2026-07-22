# backend/amodb/apps/rostering/exports.py
from __future__ import annotations

import csv
import io
from datetime import datetime, timezone
from typing import Any, Iterable, Sequence

from openpyxl import Workbook
from openpyxl.styles import Alignment, Font
from openpyxl.utils import get_column_letter
from reportlab.lib import colors
from reportlab.lib.pagesizes import A4, landscape
from reportlab.lib.styles import getSampleStyleSheet
from reportlab.lib.units import mm
from reportlab.platypus import Paragraph, SimpleDocTemplate, Spacer, Table, TableStyle

from . import schemas

UTC = timezone.utc


ASSIGNMENT_COLUMNS = [
    "assignment_id",
    "version_id",
    "staff_code",
    "full_name",
    "department_code",
    "base_code",
    "shift_code",
    "status",
    "source",
    "starts_at",
    "ends_at",
    "planned_minutes",
    "role_label",
    "team_code",
    "location_label",
    "linked_task_count",
    "linked_task_hours",
    "change_reason",
]


def assignment_csv(rows: Sequence[dict[str, Any]]) -> str:
    output = io.StringIO()
    writer = csv.DictWriter(output, fieldnames=ASSIGNMENT_COLUMNS, extrasaction="ignore")
    writer.writeheader()
    for row in rows:
        writer.writerow(row)
    return output.getvalue()


def assignment_xlsx(rows: Sequence[dict[str, Any]]) -> bytes:
    workbook = Workbook()
    sheet = workbook.active
    sheet.title = "Published Duty Roster"
    sheet.freeze_panes = "A2"
    sheet.append([column.replace("_", " ").title() for column in ASSIGNMENT_COLUMNS])
    for cell in sheet[1]:
        cell.font = Font(bold=True)
        cell.alignment = Alignment(vertical="center", wrap_text=True)
    for row in rows:
        sheet.append([row.get(column) for column in ASSIGNMENT_COLUMNS])
    for index, column in enumerate(ASSIGNMENT_COLUMNS, start=1):
        values = [str(sheet.cell(row=row_number, column=index).value or "") for row_number in range(1, min(sheet.max_row, 250) + 1)]
        width = min(max(max((len(value) for value in values), default=10) + 2, 12), 34)
        sheet.column_dimensions[get_column_letter(index)].width = width
    sheet.auto_filter.ref = sheet.dimensions
    output = io.BytesIO()
    workbook.save(output)
    return output.getvalue()


def assignment_pdf(rows: Sequence[dict[str, Any]], *, title: str, subtitle: str) -> bytes:
    output = io.BytesIO()
    document = SimpleDocTemplate(
        output,
        pagesize=landscape(A4),
        rightMargin=10 * mm,
        leftMargin=10 * mm,
        topMargin=10 * mm,
        bottomMargin=10 * mm,
        title=title,
    )
    styles = getSampleStyleSheet()
    story = [Paragraph(title, styles["Title"]), Paragraph(subtitle, styles["Normal"]), Spacer(1, 5 * mm)]
    columns = ["staff_code", "full_name", "department_code", "base_code", "shift_code", "status", "starts_at", "ends_at", "planned_minutes", "role_label"]
    data = [[column.replace("_", " ").title() for column in columns]]
    for row in rows:
        data.append([str(row.get(column) or "") for column in columns])
    table = Table(data, repeatRows=1, colWidths=[20 * mm, 34 * mm, 23 * mm, 18 * mm, 18 * mm, 18 * mm, 34 * mm, 34 * mm, 20 * mm, 30 * mm])
    table.setStyle(TableStyle([
        ("BACKGROUND", (0, 0), (-1, 0), colors.HexColor("#E2E8F0")),
        ("TEXTCOLOR", (0, 0), (-1, 0), colors.HexColor("#0F172A")),
        ("FONTNAME", (0, 0), (-1, 0), "Helvetica-Bold"),
        ("FONTSIZE", (0, 0), (-1, -1), 7),
        ("GRID", (0, 0), (-1, -1), 0.25, colors.HexColor("#94A3B8")),
        ("VALIGN", (0, 0), (-1, -1), "TOP"),
        ("ROWBACKGROUNDS", (0, 1), (-1, -1), [colors.white, colors.HexColor("#F8FAFC")]),
        ("LEFTPADDING", (0, 0), (-1, -1), 3),
        ("RIGHTPADDING", (0, 0), (-1, -1), 3),
        ("TOPPADDING", (0, 0), (-1, -1), 4),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 4),
    ]))
    story.append(table)
    document.build(story)
    return output.getvalue()


def report_csv(summary: schemas.RosterReportSummary) -> str:
    output = io.StringIO()
    writer = csv.writer(output)
    writer.writerow(["Metric", "Value"])
    for field in (
        "from_date",
        "to_date",
        "planned_minutes",
        "attendance_minutes",
        "productive_minutes",
        "overtime_minutes",
        "assignment_count",
        "assigned_people",
        "leave_minutes",
        "training_minutes",
        "standby_minutes",
        "acknowledgement_rate",
        "blocker_count",
        "warning_count",
    ):
        writer.writerow([field, getattr(summary, field)])
    writer.writerow([])
    writer.writerow(["By base"])
    if summary.by_base:
        keys = list(summary.by_base[0].keys())
        writer.writerow(keys)
        writer.writerows([[row.get(key) for key in keys] for row in summary.by_base])
    writer.writerow([])
    writer.writerow(["By department"])
    if summary.by_department:
        keys = list(summary.by_department[0].keys())
        writer.writerow(keys)
        writer.writerows([[row.get(key) for key in keys] for row in summary.by_department])
    writer.writerow([])
    writer.writerow(["By person"])
    if summary.by_user:
        keys = list(summary.by_user[0].keys())
        writer.writerow(keys)
        writer.writerows([[row.get(key) for key in keys] for row in summary.by_user])
    return output.getvalue()


def _ics_escape(value: Any) -> str:
    text = str(value or "")
    return text.replace("\\", "\\\\").replace(";", "\\;").replace(",", "\\,").replace("\n", "\\n")


def _ics_datetime(value: datetime) -> str:
    aware = value if value.tzinfo is not None else value.replace(tzinfo=UTC)
    return aware.astimezone(UTC).strftime("%Y%m%dT%H%M%SZ")


def assignment_ics(rows: Sequence[dict[str, Any]], *, calendar_name: str = "AMO Duty Roster") -> str:
    generated = datetime.now(UTC)
    lines = [
        "BEGIN:VCALENDAR",
        "VERSION:2.0",
        "PRODID:-//AMO Portal//Duty Rostering//EN",
        "CALSCALE:GREGORIAN",
        "METHOD:PUBLISH",
        f"X-WR-CALNAME:{_ics_escape(calendar_name)}",
    ]
    for row in rows:
        starts_at = datetime.fromisoformat(str(row["starts_at"]))
        ends_at = datetime.fromisoformat(str(row["ends_at"]))
        summary = f"{row.get('shift_code') or row.get('status') or 'Duty'} · {row.get('base_code') or 'Base unassigned'}"
        description = "\n".join(filter(None, [
            f"Status: {row.get('status')}",
            f"Role: {row.get('role_label')}" if row.get("role_label") else None,
            f"Team: {row.get('team_code')}" if row.get("team_code") else None,
            f"Location: {row.get('location_label')}" if row.get("location_label") else None,
        ]))
        lines.extend([
            "BEGIN:VEVENT",
            f"UID:{_ics_escape(row['assignment_id'])}@amo-portal",
            f"DTSTAMP:{_ics_datetime(generated)}",
            f"DTSTART:{_ics_datetime(starts_at)}",
            f"DTEND:{_ics_datetime(ends_at)}",
            f"SUMMARY:{_ics_escape(summary)}",
            f"DESCRIPTION:{_ics_escape(description)}",
            f"LOCATION:{_ics_escape(row.get('location_label') or row.get('base_code') or '')}",
            "STATUS:CONFIRMED",
            "END:VEVENT",
        ])
    lines.append("END:VCALENDAR")
    return "\r\n".join(lines) + "\r\n"
