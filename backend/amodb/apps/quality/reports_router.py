"""Tenant report previews and complete, bounded downloadable outputs."""
import csv
from collections import Counter
import io
from datetime import date, datetime, time, timedelta, timezone
from html import escape
from typing import Literal

from fastapi import APIRouter, Depends, HTTPException
from fastapi.responses import Response
from sqlalchemy import func, or_
from sqlalchemy.orm import Session

from amodb.database import get_read_db
from amodb.apps.accounts.models import User
from amodb.apps.training.models import TrainingCourse, TrainingRecord
from .models import QMSAudit, QMSAuditFinding, CorrectiveActionRequest
from .tenant_security import TenantContext, require_quality_permission, set_postgres_tenant_context

router = APIRouter(prefix="/reports", tags=["Quality reports"])
ReportKind = Literal["executive-dashboard", "audit-performance", "car-performance", "finding-trends", "training-compliance"]
MAX_ROWS = 10000
TITLES = {"executive-dashboard": "Quality executive summary", "audit-performance": "Audit performance", "car-performance": "CAR performance", "finding-trends": "Finding trends", "training-compliance": "Training record validity"}

def _value(value):
    value = getattr(value, "value", value)
    return value.isoformat() if isinstance(value, (datetime, date)) else str(value) if value is not None else ""

def report_snapshot(db, amo_id, amo_code, kind, start=None, end=None):
    now = datetime.now(timezone.utc)
    start, end = start or now.date().replace(month=1, day=1), end or now.date()
    if end == date.max or end < start or (end-start).days > 366*5:
        raise HTTPException(422, "Choose an ordered reporting period of at most five years.")
    lower, upper = datetime.combine(start, time.min, timezone.utc), datetime.combine(end+timedelta(days=1), time.min, timezone.utc)
    a, f, c = QMSAudit, QMSAuditFinding, CorrectiveActionRequest
    if kind == "executive-dashboard":
        columns = ["Source", "Status", "Records"]
        rows = []
        for model, label in ((a, "Audits"), (c, "CARs")):
            query = db.query(model.status, func.count(model.id)).filter(model.amo_id == amo_id, model.created_at >= lower, model.created_at < upper)
            if model is a: query = query.filter(a.deleted_at.is_(None))
            rows.extend([[label, _value(status), count] for status, count in query.group_by(model.status).order_by(model.status).all()])
        population = "Audits and CARs created in the period, grouped by current status. Deleted audits excluded."
    elif kind == "audit-performance":
        columns = ["Audit reference", "Title", "Kind", "Status", "Planned start", "Planned end", "Actual end", "Created (UTC)"]
        query = db.query(a.audit_ref, a.title, a.kind, a.status, a.planned_start, a.planned_end, a.actual_end, a.created_at).filter(a.amo_id == amo_id, a.deleted_at.is_(None), a.created_at >= lower, a.created_at < upper).order_by(a.created_at, a.id)
        rows = query.limit(MAX_ROWS+1).all()
        population = "Non-deleted audits created in the period. Planning dates and completion dates are shown separately."
    elif kind == "finding-trends":
        columns = ["Finding reference", "Audit reference", "Description", "Severity", "Type", "Requirement", "Target close", "Closed (UTC)", "Created (UTC)"]
        rows = db.query(f.finding_ref, a.audit_ref, f.description, f.severity, f.finding_type, f.requirement_ref, f.target_close_date, f.closed_at, f.created_at).join(a, a.id == f.audit_id).filter(f.amo_id == amo_id, a.amo_id == amo_id, a.deleted_at.is_(None), f.created_at >= lower, f.created_at < upper).order_by(f.created_at, f.id).limit(MAX_ROWS+1).all()
        population = "Findings created in the period within non-deleted audits. Outcomes reflect retrieval time."
    elif kind == "car-performance":
        columns = ["CAR reference", "Title", "Program", "Priority", "Status", "Due date", "Target closure", "Closed (UTC)", "Created (UTC)"]
        rows = db.query(c.car_number, c.title, c.program, c.priority, c.status, c.due_date, c.target_closure_date, c.closed_at, c.created_at).filter(c.amo_id == amo_id, c.created_at >= lower, c.created_at < upper).order_by(c.created_at, c.id).limit(MAX_ROWS+1).all()
        population = "CARs created in the period, across Quality and Reliability programs, with current outcomes."
    elif kind == "training-compliance":
        t, course = TrainingRecord, TrainingCourse
        columns = ["Person", "Course code", "Course", "Completed", "Valid until", "Verification", "Validity at retrieval"]
        raw = db.query(User.full_name, course.course_id, course.course_name, t.completion_date, t.valid_until, t.verification_status).select_from(t).join(course, course.id == t.course_id).join(User, User.id == t.user_id).filter(t.amo_id == amo_id, course.amo_id == amo_id, User.amo_id == amo_id, or_(t.record_status == "ACTIVE", t.record_status.is_(None)), t.completion_date >= start, t.completion_date <= end).order_by(t.completion_date, t.id).limit(MAX_ROWS+1).all()
        rows = [list(row)+["EXPIRED" if row.valid_until and row.valid_until < now.date() else "UNVERIFIED" if _value(row.verification_status) != "VERIFIED" else "CURRENT" if row.valid_until else "NO_EXPIRY_RECORDED"] for row in raw]
        population = "Active training records completed in the period. Validity is assessed at retrieval, not the period end. This is not a role-requirement compliance certification."
    else:
        raise HTTPException(422, "Unknown report type.")
    if len(rows) > MAX_ROWS:
        raise HTTPException(413, "This report exceeds 10,000 rows. Choose a shorter period; no partial output has been generated.")
    serialized = [[_value(value) for value in row] for row in rows]
    summary = []
    if kind == "finding-trends":
        summary = [{"label": month, "value": count} for month, count in sorted(Counter(row[-1][:7] for row in serialized).items())]
    elif kind == "executive-dashboard":
        counts = Counter()
        for row in serialized:
            counts[row[1]] += int(row[2])
        summary = [{"label": label, "value": count} for label, count in sorted(counts.items())]
    elif "Status" in columns or "Validity at retrieval" in columns:
        index = columns.index("Status") if "Status" in columns else columns.index("Validity at retrieval")
        summary = [{"label": label, "value": count} for label, count in sorted(Counter(row[index] for row in serialized).items())]
    return {"summary": summary, "kind": kind, "title": TITLES[kind], "tenant": amo_code, "generated_at": now.isoformat(), "start": start.isoformat(), "end": end.isoformat(), "population": population, "columns": columns, "rows": serialized, "total": len(rows)}

def csv_output(snapshot):
    output = io.StringIO(newline="")
    writer = csv.writer(output)
    def safe(value):
        value = str(value)
        return "'"+value if value.lstrip().startswith(("=", "+", "-", "@")) or value.startswith(("\t", "\r", "\n")) else value
    for row in ([snapshot["title"]], ["Tenant", snapshot["tenant"]], ["Generated UTC", snapshot["generated_at"]], ["Period", snapshot["start"], snapshot["end"]], ["Population", snapshot["population"]], *[[item["label"], item["value"]] for item in snapshot.get("summary", [])], [], snapshot["columns"], *snapshot["rows"]):
        writer.writerow([safe(cell) for cell in row])
    return "\ufeff"+output.getvalue()

def html_output(snapshot):
    e = lambda value: escape(str(value), quote=True)
    headings = "".join(f"<th>{e(c)}</th>" for c in snapshot["columns"])
    rows = "".join("<tr>"+"".join(f"<td>{e(c)}</td>" for c in row)+"</tr>" for row in snapshot["rows"])
    summary = " · ".join(f"{e(item['label'])}: {item['value']}" for item in snapshot.get("summary", []))
    return f'<!doctype html><html lang="en"><meta charset="utf-8"><meta name="viewport" content="width=device-width"><title>{e(snapshot["title"])}</title><style>body{{font:14px system-ui;margin:24px;color:#182639}}h1{{font-size:24px}}table{{border-collapse:collapse;width:100%;font-size:12px}}th,td{{border:1px solid #ccd5df;padding:8px;text-align:left;vertical-align:top;overflow-wrap:anywhere}}th{{background:#eef2f7}}@media print{{@page{{size:A4 landscape;margin:12mm}}thead{{display:table-header-group}}tr{{break-inside:avoid}}}}</style><h1>{e(snapshot["title"])}</h1><p>{e(snapshot["tenant"])} · {e(snapshot["start"])} to {e(snapshot["end"])}</p><p>Generated UTC: {e(snapshot["generated_at"])} · {snapshot["total"]} rows</p><p>{e(snapshot["population"])}</p><p>{summary}</p><table><thead><tr>{headings}</tr></thead><tbody>{rows}</tbody></table><p>{"No matching records." if not rows else "End of report."}</p></html>'

@router.get("/preview")
def preview_report(kind: ReportKind, start: date | None = None, end: date | None = None,
                   ctx: TenantContext = Depends(require_quality_permission("qms.reports.view")), db: Session = Depends(get_read_db)):
    set_postgres_tenant_context(db, amo_id=ctx.amo_id, user_id=ctx.user_id)
    return report_snapshot(db, ctx.amo_id, ctx.amo_code, kind, start, end)

@router.get("/output")
def download_report(kind: ReportKind, output: Literal["csv", "html"] = "csv", start: date | None = None, end: date | None = None,
                    ctx: TenantContext = Depends(require_quality_permission("qms.reports.export")), db: Session = Depends(get_read_db)):
    set_postgres_tenant_context(db, amo_id=ctx.amo_id, user_id=ctx.user_id)
    snapshot = report_snapshot(db, ctx.amo_id, ctx.amo_code, kind, start, end)
    content = csv_output(snapshot) if output == "csv" else html_output(snapshot)
    return Response(content, media_type="text/csv" if output == "csv" else "text/html", headers={"Content-Disposition": f'attachment; filename="QMS-{kind}-{snapshot["end"]}.{output}"', "Cache-Control": "no-store", "X-Content-Type-Options": "nosniff"})
