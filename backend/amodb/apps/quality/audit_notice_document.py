from __future__ import annotations

from io import BytesIO
from pathlib import Path
from typing import Any, Iterable
from xml.sax.saxutils import escape

from reportlab.graphics.barcode import qr
from reportlab.graphics.shapes import Drawing
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


def _qr_flowable(target: str, size: float = 23 * mm) -> Drawing:
    widget = qr.QrCodeWidget(target)
    x1, y1, x2, y2 = widget.getBounds()
    width = max(1.0, x2 - x1)
    height = max(1.0, y2 - y1)
    scale = min(size / width, size / height)
    drawing = Drawing(size, size, transform=[scale, 0, 0, scale, -x1 * scale, -y1 * scale])
    drawing.add(widget)
    return drawing


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
    auditee_representative: str | None,
    audit_area: str,
    audit_scope: str,
    audit_criteria: str,
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
    record_url: str,
    logo_path: Path | None = None,
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
    section = ParagraphStyle("NoticeSection", parent=normal, fontName="Helvetica-Bold", spaceBefore=4, spaceAfter=2)
    bullet = ParagraphStyle("NoticeBullet", parent=normal, leftIndent=7 * mm, bulletIndent=2 * mm, spaceAfter=2)
    signature = ParagraphStyle("NoticeSignature", parent=normal, fontSize=8.6, leading=10.5)
    qr_caption = ParagraphStyle("NoticeQrCaption", parent=meta_style, alignment=TA_CENTER, leading=8.5)

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

    representative = _text(auditee_representative, "Responsible auditee representative")
    area = _text(audit_area, "Defined audit area / process")
    representative_names = [representative]
    representative_names.extend(_text(item) for item in staff if _text(item) and _text(item) != representative)
    representative_story = [
        Paragraph(f"{index})&nbsp;&nbsp;{escape(name)}", compact)
        for index, name in enumerate(representative_names, start=1)
    ]
    story: list[Any] = [
        header,
        Spacer(1, 5 * mm),
        Table(
            [[Paragraph("From: <b>Quality Department</b>", normal), Paragraph(f"Date: <b>{escape(notice_date_display)}</b>", normal)]],
            colWidths=[124 * mm, 65 * mm],
            style=TableStyle([("VALIGN", (0, 0), (-1, -1), "TOP"), ("ALIGN", (1, 0), (1, 0), "RIGHT")]),
        ),
        Paragraph(f"To: <b>{escape(representative)}</b>", normal),
        Paragraph(f"Role: Auditee representative for <b>{escape(area)}</b>", compact),
        Spacer(1, 1.5 * mm),
        Paragraph(f"Subject: <b>{escape(subject)}</b>", normal),
        Spacer(1, 1.5 * mm),
        Paragraph(
            f"<b>{escape(representative)}</b> is the auditee representative and coordination contact.",
            normal,
        ),
        Paragraph(
            "<b>Role note:</b> accountability for the process and records remains with process owners.",
            normal,
        ),
        Paragraph(
            f"This notice confirms that the <b>{escape(area)}</b> area/process is scheduled for the "
            f"<b>{escape(audit_title)}</b> (Ref: <b>{escape(audit_ref)}</b>) on "
            f"<b>{escape(audit_date_display)}</b>.",
            normal,
        ),
        Paragraph("Audit particulars", section),
    ]

    sequence = Table(
        [
            [Paragraph("REFERENCE", strong), Paragraph("AREA / PROCESS", strong), Paragraph("AUDIT WINDOW", strong)],
            [_paragraph(audit_ref, compact), _paragraph(area, compact), _paragraph(f"{audit_date_display}; {sequence_window}", compact)],
        ],
        colWidths=[42 * mm, 79 * mm, 63 * mm],
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
        Spacer(1, 2 * mm),
        Table(
            [
                [Paragraph("CONTROLLED SCOPE", strong), Paragraph("AUDIT CRITERIA", strong)],
                [_paragraph(audit_scope, compact), _paragraph(audit_criteria, compact)],
            ],
            colWidths=[92 * mm, 92 * mm],
            style=TableStyle([
                ("BOX", (0, 0), (-1, -1), 0.5, colors.HexColor("#98A2B3")),
                ("INNERGRID", (0, 0), (-1, -1), 0.4, colors.HexColor("#D0D5DD")),
                ("BACKGROUND", (0, 0), (-1, 0), colors.HexColor("#F8FAFC")),
                ("VALIGN", (0, 0), (-1, -1), "TOP"),
                ("LEFTPADDING", (0, 0), (-1, -1), 6),
                ("RIGHTPADDING", (0, 0), (-1, -1), 6),
                ("TOPPADDING", (0, 0), (-1, -1), 4),
                ("BOTTOMPADDING", (0, 0), (-1, -1), 4),
            ]),
        ),
        Paragraph("Pre-audit briefing", section),
        Paragraph(f"<bullet>&bull;</bullet>{escape(_meeting_line(opening_meeting))}", bullet),
        Paragraph("Auditee coordination", section),
        Paragraph(
            "The representative should coordinate the availability of applicable process owners, record custodians, "
            "facilities, systems and controlled records. The following auditee representatives are recorded for this notice:",
            normal,
        ),
        *representative_story,
        Spacer(1, 1 * mm),
        Paragraph(
            "The audit will generally include three phases: data gathering and review, on-site audit or examination, "
            "and analysis of the evidence. A corrective action request will be issued to the responsible manager "
            "where the evidence shows that corrective action is warranted.",
            normal,
        ),
        Paragraph("Post-audit briefing", section),
        Paragraph(f"<bullet>&bull;</bullet>{escape(_meeting_line(closing_meeting))}", bullet),
        Spacer(1, 1.5 * mm),
        Paragraph(
            "Please provide the auditor(s) any assistance they may require. Thank you in advance for your cooperation. "
            f"For further information, contact the Quality Office at <b>{escape(_text(contact_email, 'the registered AMO contact address'))}</b>.",
            normal,
        ),
        Spacer(1, 1.5 * mm),
        Table(
            [[
                [
                    Paragraph("<b>Electronically signed in AMO Portal</b>", signature),
                    Paragraph(f"<b>{escape(issuer_name)}</b>", signature),
                    Paragraph(escape(issuer_title), signature),
                    Paragraph(f"Signed: {escape(signed_at_display)}", signature),
                    Paragraph(f"Notice record: {escape(notice_id)} / revision {revision_no}", meta_style),
                    Paragraph("The stored document hash and issuance history are retained in the controlled digital record.", meta_style),
                ],
                [
                    _qr_flowable(record_url),
                    Paragraph("Scan to open the controlled digital notice.<br/>Login required.<br/>QR identifies the record only.", qr_caption),
                ],
            ]],
            colWidths=[134 * mm, 50 * mm],
            style=TableStyle([
                ("BOX", (0, 0), (-1, -1), 0.5, colors.HexColor("#98A2B3")),
                ("VALIGN", (0, 0), (-1, -1), "MIDDLE"),
                ("ALIGN", (1, 0), (1, 0), "CENTER"),
                ("LEFTPADDING", (0, 0), (-1, -1), 7),
                ("RIGHTPADDING", (0, 0), (-1, -1), 7),
                ("TOPPADDING", (0, 0), (-1, -1), 6),
                ("BOTTOMPADDING", (0, 0), (-1, -1), 6),
            ]),
        ),
    ])

    document.build(story, canvasmaker=_PageCountCanvas)
    return output.getvalue()
