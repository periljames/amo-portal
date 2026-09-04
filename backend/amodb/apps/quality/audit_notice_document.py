from __future__ import annotations

from io import BytesIO
from pathlib import Path
from typing import Any, Iterable
from xml.sax.saxutils import escape

from reportlab.lib import colors
from reportlab.lib.enums import TA_CENTER, TA_LEFT
from reportlab.lib.pagesizes import letter
from reportlab.lib.styles import ParagraphStyle, getSampleStyleSheet
from reportlab.lib.units import mm
from reportlab.pdfgen import canvas
from reportlab.platypus import Image, KeepTogether, Paragraph, SimpleDocTemplate, Spacer, Table, TableStyle


class _PageCountCanvas(canvas.Canvas):
    """Add an attributable Page x of y footer without a second PDF library."""

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self._saved_page_states: list[dict[str, Any]] = []

    def showPage(self) -> None:  # noqa: N802 - ReportLab API
        self._saved_page_states.append(dict(self.__dict__))
        self._startPage()

    def save(self) -> None:
        total = len(self._saved_page_states)
        for state in self._saved_page_states:
            self.__dict__.update(state)
            self.setFont("Helvetica", 7)
            self.setFillColor(colors.HexColor("#475467"))
            self.drawRightString(letter[0] - 13 * mm, 8 * mm, f"Page {self._pageNumber} of {total}")
            canvas.Canvas.showPage(self)
        canvas.Canvas.save(self)


def _text(value: object, fallback: str = "") -> str:
    cleaned = (
        str(value or "")
        .translate(str.maketrans({"\u2013": "-", "\u2014": "-", "\u2212": "-", "\u00b7": "-", "\u2011": "-"}))
        .strip()
    )
    return cleaned or fallback


def _paragraph(value: object, style: ParagraphStyle) -> Paragraph:
    return Paragraph(escape(_text(value)).replace("\n", "<br/>"), style)


def _logo_cell(logo_path: Path | None, amo_name: str, style: ParagraphStyle):
    if logo_path is not None and logo_path.is_file() and logo_path.suffix.lower() in {".png", ".jpg", ".jpeg"}:
        try:
            image = Image(str(logo_path))
            image._restrictSize(52 * mm, 20 * mm)
            return image
        except Exception:
            pass
    return _paragraph(amo_name, style)


def _meeting_line(meeting: dict[str, Any] | None) -> str:
    if not meeting:
        return "To be confirmed"
    window = _text(meeting.get("window"), "Time to be confirmed")
    location = _text(meeting.get("location"))
    conference = _text(meeting.get("conference_url"))
    place = location or ("Online meeting" if conference else "Location to be confirmed")
    return f"{window}, {place}"


def _staff_story(staff: Iterable[str], style: ParagraphStyle) -> list[Paragraph]:
    names = [_text(item) for item in staff if _text(item)]
    if not names:
        names = ["Responsible auditee representative"]
    return [Paragraph(f"{index})&nbsp;&nbsp;{escape(name)}", style) for index, name in enumerate(names, start=1)]


def render_audit_notice_pdf(
    *,
    amo_name: str,
    contact_email: str | None,
    notice_id: str,
    revision_no: int,
    notice_date_display: str,
    audit_ref: str,
    audit_title: str,
    audit_date_display: str,
    auditee: str | None,
    subject: str,
    opening_meeting: dict[str, Any] | None,
    closing_meeting: dict[str, Any] | None,
    sequence_window: str,
    staff: Iterable[str],
    issuer_name: str,
    issuer_title: str,
    signed_at_display: str,
    form_number: str,
    form_issue_date: str,
    form_revision: str,
    logo_path: Path | None = None,
    is_preview: bool = False,
) -> bytes:
    """Render the controlled audit notice using the supplied immutable values."""

    output = BytesIO()
    document = SimpleDocTemplate(
        output,
        pagesize=letter,
        leftMargin=13 * mm,
        rightMargin=13 * mm,
        topMargin=12 * mm,
        bottomMargin=14 * mm,
        title=f"Audit Notice {audit_ref}",
        author=issuer_name,
        subject=subject,
    )
    styles = getSampleStyleSheet()
    normal = ParagraphStyle(
        "NoticeNormal",
        parent=styles["BodyText"],
        fontName="Helvetica",
        fontSize=9.2,
        leading=11.4,
        textColor=colors.HexColor("#101828"),
        spaceAfter=4,
    )
    compact = ParagraphStyle("NoticeCompact", parent=normal, fontSize=8.6, leading=10.5, spaceAfter=2)
    strong = ParagraphStyle("NoticeStrong", parent=normal, fontName="Helvetica-Bold", spaceAfter=2)
    title_style = ParagraphStyle(
        "NoticeTitle",
        parent=strong,
        fontSize=12,
        leading=14,
        alignment=TA_CENTER,
    )
    brand_style = ParagraphStyle(
        "NoticeBrand",
        parent=strong,
        fontSize=13,
        leading=14,
        textColor=colors.HexColor("#9A7B00"),
        alignment=TA_CENTER,
    )
    meta_style = ParagraphStyle("NoticeMeta", parent=compact, fontSize=7.8, leading=9.5, alignment=TA_LEFT)
    section = ParagraphStyle("NoticeSection", parent=normal, leftIndent=15 * mm, spaceBefore=4, spaceAfter=3)
    bullet = ParagraphStyle("NoticeBullet", parent=strong, leftIndent=22 * mm, bulletIndent=17 * mm, spaceAfter=3)
    signature = ParagraphStyle("NoticeSignature", parent=normal, fontSize=8.6, leading=10.5)

    metadata = (
        f"Form No: {escape(form_number)}<br/>"
        f"Issue Date: {escape(form_issue_date)}<br/>"
        f"Revision: {escape(form_revision)}"
    )
    header = Table(
        [[
            _logo_cell(logo_path, amo_name, brand_style),
            Paragraph("Audit Notice/Timetable", title_style),
            Paragraph(metadata, meta_style),
        ]],
        colWidths=[55 * mm, 84 * mm, 50 * mm],
    )
    header.setStyle(TableStyle([
        ("BOX", (0, 0), (-1, -1), 0.8, colors.HexColor("#344054")),
        ("INNERGRID", (0, 0), (-1, -1), 0.6, colors.HexColor("#667085")),
        ("VALIGN", (0, 0), (-1, -1), "MIDDLE"),
        ("ALIGN", (0, 0), (1, 0), "CENTER"),
        ("LEFTPADDING", (0, 0), (-1, -1), 7),
        ("RIGHTPADDING", (0, 0), (-1, -1), 7),
        ("TOPPADDING", (0, 0), (-1, -1), 7),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 7),
    ]))

    recipient = _text(auditee, "Responsible auditee")
    area = recipient
    story: list[Any] = [
        header,
        Spacer(1, 5 * mm),
        Table(
            [[Paragraph("From: <b>Quality Department</b>", normal), Paragraph(f"Date: <b>{escape(notice_date_display)}</b>", normal)]],
            colWidths=[124 * mm, 65 * mm],
            style=TableStyle([("VALIGN", (0, 0), (-1, -1), "TOP"), ("ALIGN", (1, 0), (1, 0), "RIGHT")]),
        ),
        Paragraph(f"To: <b>{escape(recipient)}</b>", normal),
        Spacer(1, 1.5 * mm),
        Paragraph(f"Subject: <b>{escape(subject)}</b>", normal),
        Spacer(1, 1.5 * mm),
        Paragraph(
            "This memo serves as formal notification that "
            f"<b>{escape(recipient)}</b> will undergo the scheduled "
            f"<b>{escape(audit_title)}</b> (Ref: <b>{escape(audit_ref)}</b>) on "
            f"<b>{escape(audit_date_display)}</b>.",
            normal,
        ),
        Paragraph("Audit Name and Audit Reference Number:", section),
        Paragraph(f"<bullet>&bull;</bullet>{escape(audit_title)} - {escape(audit_ref)}", bullet),
        Paragraph("Date, time and place of pre-audit briefing:", section),
        Paragraph(f"<bullet>&bull;</bullet>{escape(_meeting_line(opening_meeting))}", bullet),
        Paragraph("Planned sequence of audit/examination:", section),
    ]

    sequence = Table(
        [[Paragraph("DEPARTMENT / AREA", strong), Paragraph("ALLOCATED TIME", strong)],
         [_paragraph(area, compact), _paragraph(sequence_window, compact)]],
        colWidths=[123 * mm, 61 * mm],
    )
    sequence.setStyle(TableStyle([
        ("BOX", (0, 0), (-1, -1), 0.7, colors.HexColor("#344054")),
        ("INNERGRID", (0, 0), (-1, -1), 0.5, colors.HexColor("#667085")),
        ("BACKGROUND", (0, 0), (-1, 0), colors.HexColor("#F2F4F7")),
        ("VALIGN", (0, 0), (-1, -1), "TOP"),
        ("LEFTPADDING", (0, 0), (-1, -1), 6),
        ("RIGHTPADDING", (0, 0), (-1, -1), 6),
        ("TOPPADDING", (0, 0), (-1, -1), 4),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 4),
    ]))
    story.extend([
        KeepTogether(sequence),
        Spacer(1, 2.5 * mm),
        Paragraph("The following staff members are requested to be present:", normal),
        *_staff_story(staff, compact),
        Spacer(1, 1.5 * mm),
        Paragraph(
            "The audit will generally include three phases: data gathering and review, on-site audit or examination, "
            "and analysis of the evidence. A corrective action request will be issued to the responsible manager "
            "where the evidence shows that corrective action is warranted.",
            normal,
        ),
        Paragraph("Date, time and place of post-audit briefing:", normal),
        Paragraph(f"<bullet>&bull;</bullet>{escape(_meeting_line(closing_meeting))}", bullet),
        Spacer(1, 1.5 * mm),
        Paragraph(
            "Please provide the auditor(s) any assistance they may require. Thank you in advance for your cooperation. "
            f"For further information, contact the Quality Office at <b>{escape(_text(contact_email, 'the registered AMO contact address'))}</b>.",
            normal,
        ),
        Spacer(1, 2 * mm),
        Paragraph("Sincerely,", normal),
        Paragraph(
            "Preview - electronic signature and issuance are applied on submission"
            if is_preview
            else "Electronically signed and issued through AMO Portal",
            signature,
        ),
        Paragraph(f"<b>{escape(issuer_name)}</b>", signature),
        Paragraph(escape(issuer_title), signature),
        Paragraph(f"{'Prepared' if is_preview else 'Signed'}: {escape(signed_at_display)}", signature),
        Paragraph(f"Notice record: {escape(notice_id)} / revision {revision_no}", meta_style),
    ])

    document.build(story, canvasmaker=_PageCountCanvas)
    return output.getvalue()
