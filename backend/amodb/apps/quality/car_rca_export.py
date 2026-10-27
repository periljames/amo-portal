"""Include authoritative structured CAR RCA in the existing evidence package.

No substitute Quality approvals are inferred from respondent-entered RCA data.
"""
from __future__ import annotations
import io
from uuid import UUID
from sqlalchemy.orm import Session

from .car_rca_models import (
    QualityCarRcaDocument, QualityCarRcaRevision, QualityCarRcaAction,
    QualityCarRcaActionEvent, QualityCarRcaParetoSnapshot,
    QualityCarResponseRetainedRevision,
)
from .assurance_case_models import QualityEffectivenessPlan


def collect_car_rca_evidence(db: Session, *, amo_id: str, car_id: UUID, serialize):
    def list_records(model, order=None):
        query = db.query(model).filter(model.amo_id == amo_id, model.car_id == car_id)
        if order is not None:
            query = query.order_by(order)
        return [serialize(record) for record in query.all()]

    doc = db.query(QualityCarRcaDocument).filter(
        QualityCarRcaDocument.amo_id == amo_id,
        QualityCarRcaDocument.car_id == car_id,
    ).first()
    effect = db.query(QualityEffectivenessPlan).filter(
        QualityEffectivenessPlan.amo_id == amo_id,
        QualityEffectivenessPlan.source_type == "CAR",
        QualityEffectivenessPlan.source_id == str(car_id),
    ).order_by(QualityEffectivenessPlan.created_at.asc()).all()
    return {
        "rca_document": serialize(doc) if doc is not None else None,
        "rca_revisions": list_records(QualityCarRcaRevision, QualityCarRcaRevision.created_at.asc()),
        "rca_actions": list_records(QualityCarRcaAction, QualityCarRcaAction.sequence_no.asc()),
        "rca_action_events": list_records(QualityCarRcaActionEvent, QualityCarRcaActionEvent.created_at.asc()),
        "rca_pareto_snapshots": list_records(QualityCarRcaParetoSnapshot, QualityCarRcaParetoSnapshot.created_at.asc()),
        "recalled_responses": list_records(QualityCarResponseRetainedRevision, QualityCarResponseRetainedRevision.retained_at.asc()),
        "effectiveness_plans": [serialize(record) for record in effect],
    }


def render_submitted_rca_pdf(linked: dict, *, car_number: str) -> bytes | None:
    """Render the submitted source snapshot. Drafts never masquerade as verified."""
    doc = linked.get("rca_document")
    snapshot = (doc or {}).get("submitted_snapshot")
    if not isinstance(snapshot, dict):
        return None
    investigation = snapshot.get("investigation")
    if not isinstance(investigation, dict):
        return None

    from reportlab.lib.pagesizes import A4
    from reportlab.lib.utils import simpleSplit
    from reportlab.pdfgen import canvas

    output = io.BytesIO()
    pdf = canvas.Canvas(output, pagesize=A4, pageCompression=1)
    width, height = A4
    left, right, bottom = 48, 48, 58
    y = height - 52

    def line(label: str, value: object = "", *, heading: bool = False):
        nonlocal y
        text = (str(label) + (": " + str(value) if value not in (None, "") else "")).replace("\x00", "")
        fontsize = 12 if heading else 9
        font = "Helvetica-Bold" if heading else "Helvetica"
        for row in simpleSplit(text, font, fontsize, width - left - right):
            if y < bottom:
                pdf.showPage()
                y = height - 52
            pdf.setFont(font, fontsize)
            pdf.drawString(left, y, row)
            y -= 16 if heading else 13
        y -= 5 if heading else 2

    line("Submitted CAR Root Cause Investigation", heading=True)
    line("CAR", car_number)
    line("Investigation revision", (doc or {}).get("submitted_revision"))
    line("Submitted", (doc or {}).get("submitted_at"))
    line("Problem", investigation.get("problem_statement"))
    line("Proposed conclusion (Quality acceptance separate)", investigation.get("conclusion"))
    line("Supported cause IDs", ", ".join(investigation.get("supported_cause_ids") or []))
    line("Conclusion evidence", ", ".join(investigation.get("conclusion_evidence_references") or []))

    for method in investigation.get("investigations") or []:
        if not isinstance(method, dict):
            continue
        line("Method: " + str(method.get("method", "Unknown")), heading=True)
        for node in method.get("nodes") or []:
            if not isinstance(node, dict):
                continue
            line("Cause [" + str(node.get("entry_type", "HYPOTHESIS")) + "]",
                 str(node.get("statement", "")))
            line("Category / parent", str(node.get("category", "")) + " / " + str(node.get("parent_id", "") or "ROOT"))
            if node.get("evidence_references"):
                line("Cause evidence", ", ".join(node.get("evidence_references") or []))
        if method.get("context"):
            line("Method metadata", str(method.get("context"))[:4000])

    for action in linked.get("rca_actions") or []:
        line("Action " + str(action.get("sequence_no")) + " (" + str(action.get("kind")) + ")", heading=True)
        line("Description", action.get("description"))
        line("State (Quality decision independent)", action.get("state"))
        line("Owner", action.get("external_owner_name") or action.get("owner_user_id"))
        line("Target", action.get("target_date"))
        line("Evidence", ", ".join(action.get("evidence_references") or []))
        line("Quality review", action.get("quality_review_note"))

    for plan in linked.get("effectiveness_plans") or []:
        line("Effectiveness plan", heading=True)
        line("Status / conclusion", str(plan.get("status")) + " / " + str(plan.get("conclusion")))
        line("Measure", plan.get("effectiveness_measure"))

    line("Appendices", "Machine-readable revisions, event history and Pareto snapshots are in this evidence ZIP.")

    # Visual pages come from the identical submitted source snapshot, never
    # reconstructed hypotheses or fabricated Quality-verified categories.
    from .car_rca_export_charts import render_fishbone, render_pareto
    for method in investigation.get("investigations") or []:
        if isinstance(method, dict) and method.get("method") == "ISHIKAWA":
            render_fishbone(pdf, method)

    saved_pareto = linked.get("rca_pareto_snapshots") or []
    if saved_pareto:
        latest = saved_pareto[-1]
        render_pareto(
            pdf, latest.get("categories") or [],
            source_label="Authoritative QMS findings snapshot; source filters and record IDs retained in ZIP.",
        )
    else:
        for method in investigation.get("investigations") or []:
            if not isinstance(method, dict) or method.get("method") != "PARETO":
                continue
            context = method.get("context") or {}
            render_pareto(
                pdf, context.get("frequencies") or [],
                source_label="Respondent-entered frequency observations; not verified against QMS source records.",
            )
    pdf.save()
    return output.getvalue()
