"""Finding classifications and event counts from retained tenant sources."""
from datetime import date
from typing import Literal

from fastapi import APIRouter, Depends, Query
from sqlalchemy import text
from sqlalchemy.orm import Session

from amodb.database import get_read_db
from .tenant_security import TenantContext, assert_quality_permission, resolve_tenant_context, set_postgres_tenant_context

router = APIRouter(prefix="/findings/insights", tags=["Finding insights"])


def process_mapping_condition(finding_alias, *, matching=False):
    # Only recorded, current, verified links to approved active controls classify
    # a finding. Audit titles and descriptions never supply guessed processes.
    match = " AND trim(c.process_area)=:quality_process" if matching else ""
    return f"""EXISTS (SELECT 1 FROM quality_assurance_evidence_links l
        JOIN quality_assurance_controls c ON c.id=l.control_id AND c.amo_id=l.amo_id
        WHERE l.amo_id={finding_alias}.amo_id AND l.source_type='FINDING'
        AND l.source_id=CAST({finding_alias}.id AS TEXT)
        AND l.evidence_status='VERIFIED' AND l.invalidated_at IS NULL
        AND (l.valid_until IS NULL OR l.valid_until>=CURRENT_DATE)
        AND c.status='ACTIVE' AND c.approval_status='APPROVED'
        AND trim(COALESCE(c.process_area,''))<>''{match})"""


@router.get("")
def insights(view: Literal["by-severity", "by-process", "trends"],
             year: int = Query(default_factory=lambda: date.today().year, ge=2000, le=2199),
             ctx: TenantContext = Depends(resolve_tenant_context), db: Session = Depends(get_read_db)):
    assert_quality_permission(db, ctx, "qms.finding.view")
    set_postgres_tenant_context(db, amo_id=ctx.amo_id, user_id=ctx.user_id)
    params = {"amo": ctx.amo_id, "start": date(year, 1, 1), "end": date(year + 1, 1, 1)}
    source = "FROM qms_audit_findings f JOIN qms_audits a ON a.id=f.audit_id AND a.amo_id=f.amo_id"
    tenant = "f.amo_id=:amo AND a.deleted_at IS NULL"
    cohort = tenant + " AND f.created_at>=:start AND f.created_at<:end"
    totals = dict(db.execute(text(f"SELECT count(*) AS total, sum(CASE WHEN f.closed_at IS NULL THEN 1 ELSE 0 END) AS open {source} WHERE {cohort}"), params).mappings().one())
    totals["open"] = int(totals["open"] or 0)
    groups = []
    months = []
    unmapped = None
    if view == "by-severity":
        groups = [dict(row) for row in db.execute(text(f"""SELECT COALESCE(CAST(f.severity AS TEXT),'UNCLASSIFIED') AS key,
            count(*) AS total, sum(CASE WHEN f.closed_at IS NULL THEN 1 ELSE 0 END) AS open
            {source} WHERE {cohort} GROUP BY COALESCE(CAST(f.severity AS TEXT),'UNCLASSIFIED')
            ORDER BY count(*) DESC, key"""), params).mappings()]
    elif view == "by-process":
        groups = [dict(row) for row in db.execute(text(f"""SELECT trim(c.process_area) AS key,
            count(DISTINCT f.id) AS total, count(DISTINCT CASE WHEN f.closed_at IS NULL THEN f.id END) AS open
            {source} JOIN quality_assurance_evidence_links l ON l.amo_id=f.amo_id AND l.source_id=CAST(f.id AS TEXT)
            JOIN quality_assurance_controls c ON c.id=l.control_id AND c.amo_id=l.amo_id
            WHERE {cohort} AND l.source_type='FINDING' AND l.evidence_status='VERIFIED'
            AND l.invalidated_at IS NULL AND (l.valid_until IS NULL OR l.valid_until>=CURRENT_DATE)
            AND c.status='ACTIVE' AND c.approval_status='APPROVED' AND trim(COALESCE(c.process_area,''))<>''
            GROUP BY trim(c.process_area) ORDER BY count(DISTINCT f.id) DESC, key"""), params).mappings()]
        unmapped = int(db.execute(text(f"SELECT count(*) {source} WHERE {cohort} AND NOT {process_mapping_condition('f')}"), params).scalar_one())
    else:
        counts = {}
        for event, column in (("raised", "created_at"), ("closed", "closed_at")):
            expression = f"EXTRACT(MONTH FROM f.{column})" if db.bind.dialect.name == "postgresql" else f"CAST(strftime('%m',f.{column}) AS INTEGER)"
            counts[event] = {int(row["month"]): int(row["count"]) for row in db.execute(text(f"SELECT {expression} AS month,count(*) AS count {source} WHERE {tenant} AND f.{column}>=:start AND f.{column}<:end GROUP BY {expression}"), params).mappings()}
        months = [{"month": f"{year}-{number:02d}", **{event: counts[event].get(number, 0) for event in counts}} for number in range(1, 13)]
    return {"view": view, "year": year, "total": int(totals["total"]), "open": totals["open"], "groups": groups, "months": months, "unmapped": unmapped}
