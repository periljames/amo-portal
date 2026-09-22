"""Complete-population analysis with bounded source drill-downs.

Finding creation time defines the cohort. Linked QUALITY CARs describe the
current outcome of that cohort; they are not a separate issuance cohort.
"""
from datetime import date, datetime, time, timedelta, timezone

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy import and_, case, extract, func, select
from sqlalchemy.orm import Session

from amodb.database import get_read_db
from .models import QMSAudit, QMSAuditFinding, CorrectiveActionRequest
from .enums import QMSFindingSeverity, QMSFindingType
from .tenant_security import TenantContext, require_quality_permission, set_postgres_tenant_context

router = APIRouter(prefix="/analysis", tags=["Quality analysis"])


def _text(value):
    return str(getattr(value, "value", value) or "Unspecified")


def build_snapshot(db: Session, amo_id: str, start: date, end: date,
                   severity=None, finding_type=None, requirement=None, offset=0, limit=50):
    if end < start or (end - start).days > 366 * 5:
        raise HTTPException(422, "Choose an ordered date range of at most five years.")
    now = datetime.now(timezone.utc)
    f, a, c = QMSAuditFinding, QMSAudit, CorrectiveActionRequest
    predicates = [f.amo_id == amo_id, a.amo_id == amo_id, a.deleted_at.is_(None),
                  f.created_at >= datetime.combine(start, time.min, timezone.utc),
                  f.created_at < datetime.combine(end + timedelta(days=1), time.min, timezone.utc)]
    if severity:
        predicates.append(f.severity == severity)
    if finding_type:
        predicates.append(f.finding_type == finding_type)
    if requirement:
        predicates.append(func.coalesce(func.nullif(func.trim(f.requirement_ref), ""), "Unspecified") == requirement)

    def cohort(*columns):
        return db.query(*columns).select_from(f).join(a, a.id == f.audit_id).filter(*predicates)

    missing_evidence = func.length(func.trim(func.coalesce(f.objective_evidence, ""))) == 0
    missing_requirement = func.length(func.trim(func.coalesce(f.requirement_ref, ""))) == 0
    counts = cohort(func.count(f.id), func.sum(case((f.closed_at.is_(None), 1), else_=0)),
                    func.sum(case((missing_evidence, 1), else_=0)),
                    func.sum(case((missing_requirement, 1), else_=0))).one()
    total = int(counts[0])
    severity_rows = cohort(f.severity, func.count(f.id)).group_by(f.severity).all()
    type_rows = cohort(f.finding_type, func.count(f.id)).group_by(f.finding_type).all()
    req = func.coalesce(func.nullif(func.trim(f.requirement_ref), ""), "Unspecified")
    # Bound response cardinality, but retain omitted groups in an explicit tail.
    requirements = cohort(req.label("name"), func.count(f.id).label("count")).group_by(req).order_by(func.count(f.id).desc(), req).limit(30).all()
    tail = total - sum(int(row.count) for row in requirements)
    year, month = extract("year", f.created_at), extract("month", f.created_at)
    months = cohort(year.label("year"), month.label("month"), func.count(f.id).label("count")).group_by(year, month).order_by(year, month).all()
    month_counts = {f"{int(row.year):04d}-{int(row.month):02d}": int(row.count) for row in months}
    cursor = start.replace(day=1)
    trend = []
    while cursor <= end:
        key = cursor.strftime("%Y-%m")
        next_month = (cursor.replace(day=28) + timedelta(days=4)).replace(day=1)
        trend.append({"name": key, "count": month_counts.get(key, 0),
                      "partial": start > cursor or end < next_month - timedelta(days=1)})
        cursor = next_month

    finding_ids = cohort(f.id).subquery()
    cars = db.query(c).filter(c.amo_id == amo_id, c.program == "QUALITY", c.finding_id.in_(select(finding_ids.c.id)))
    due = func.coalesce(c.target_closure_date, c.due_date)
    measurable = and_(c.status == "CLOSED", c.closed_at.is_not(None), due.is_not(None))
    on_time = and_(measurable, func.date(c.closed_at) <= due)
    car_counts = cars.with_entities(func.count(c.id),
        func.sum(case((c.status == "CLOSED", 1), else_=0)),
        func.sum(case((and_(c.status.notin_(["CLOSED", "CANCELLED"]), due < now.date()), 1), else_=0)),
        func.sum(case((measurable, 1), else_=0)), func.sum(case((on_time, 1), else_=0)),
        func.sum(case((c.status == "CANCELLED", 1), else_=0))).one()
    # Select only scalar source fields, avoiding ORM relationship hydration/N+1.
    rows = cohort(f.id, f.audit_id, f.finding_ref, f.description, f.severity, f.finding_type,
                  f.requirement_ref, f.objective_evidence, f.created_at, f.closed_at,
                  a.audit_ref).order_by(f.created_at.desc(), f.id).offset(offset).limit(limit).all()
    sources = [{"id": str(row.id), "audit_id": str(row.audit_id), "reference": row.finding_ref or str(row.id),
                "audit_reference": row.audit_ref, "description": row.description,
                "severity": _text(row.severity), "finding_type": _text(row.finding_type),
                "requirement": row.requirement_ref, "objective_evidence": row.objective_evidence,
                "created_at": row.created_at, "closed_at": row.closed_at} for row in rows]
    return {"generated_at": now, "filters": {"start": start, "end": end, "severity": severity,
            "finding_type": finding_type, "requirement": requirement},
            "population": "Findings in non-deleted audits, by finding creation date (UTC). CAR outcomes include only linked QUALITY CARs, at retrieval time.",
            "total": total, "open": int(counts[1] or 0),
            "missing_evidence": int(counts[2] or 0), "missing_requirement": int(counts[3] or 0),
            "severity": [{"name": _text(name), "count": int(count)} for name, count in severity_rows],
            "types": [{"name": _text(name), "count": int(count)} for name, count in type_rows],
            "requirements": [{"name": row.name, "count": int(row.count)} for row in requirements],
            "requirement_tail": tail, "trend": trend,
            "cars": dict(zip(["total", "closed", "overdue", "measurable", "on_time", "cancelled"], [int(n or 0) for n in car_counts])),
            "sources": sources, "offset": offset, "limit": limit, "has_more": offset + len(rows) < total}


@router.get("/snapshot")
def analysis_snapshot(
    start: date, end: date,
    severity: QMSFindingSeverity | None = None,
    finding_type: QMSFindingType | None = None,
    requirement: str | None = Query(default=None, max_length=255),
    offset: int = Query(default=0, ge=0), limit: int = Query(default=50, ge=1, le=100),
    ctx: TenantContext = Depends(require_quality_permission("qms.reports.view")),
    db: Session = Depends(get_read_db),
):
    set_postgres_tenant_context(db, amo_id=ctx.amo_id, user_id=ctx.user_id)
    return build_snapshot(db, ctx.amo_id, start, end, severity, finding_type, requirement, offset, limit)
