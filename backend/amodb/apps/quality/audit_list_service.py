"""Authoritative audit list query shared by canonical pages and the legacy adapter."""
from datetime import date
from sqlalchemy import Date, String, cast, func, or_, text
from . import models
from .assurance_sources import responsibility
from .tenant_security import set_postgres_tenant_context


def audit_page(db, ctx, *, limit=100, offset=0, domain=None, status=None, kind=None,
               deleted_only=False, include_deleted=False, view="all", q=None,
               sort="planned_start", direction="asc", period=None):
    set_postgres_tenant_context(db, amo_id=ctx.amo_id, user_id=ctx.user_id)
    audit = models.QMSAudit
    query = db.query(audit).filter(audit.amo_id == ctx.amo_id)
    if deleted_only:
        query = query.filter(audit.deleted_at.is_not(None))
    elif not include_deleted:
        query = query.filter(audit.deleted_at.is_(None))
    for field, value in ((audit.domain, domain), (audit.status, status), (audit.kind, kind)):
        if value:
            query = query.filter(field == value)
    if view == "mine":
        columns = set(audit.__table__.columns.keys())
        query = query.filter(text(responsibility(db, "qms_audits", columns))).params(actor_user_id=ctx.user_id)
    elif view == "upcoming":
        query = query.filter(audit.status == models.QMSAuditStatus.PLANNED)
    elif view == "active":
        query = query.filter(audit.status.in_([models.QMSAuditStatus.IN_PROGRESS, models.QMSAuditStatus.CAP_OPEN]))
    elif view == "completed":
        query = query.filter(audit.status == models.QMSAuditStatus.CLOSED)
    if period is not None:
        cohort = func.coalesce(audit.planned_start, cast(audit.created_at, Date))
        query = query.filter(cohort >= date(period, 1, 1), cohort < date(period + 1, 1, 1))
    if q and q.strip():
        # Literal substring search: wildcard characters supplied by users are data.
        needle = "%" + q.strip().replace("\\", "\\\\").replace("%", "\\%").replace("_", "\\_") + "%"
        query = query.filter(or_(*(cast(field, String).ilike(needle, escape="\\") for field in
            (audit.audit_ref, audit.title, audit.scope, audit.audit_scope_code, audit.auditee, audit.kind))))
    total = query.order_by(None).count()
    sort_column = {"planned_start": audit.planned_start, "created_at": audit.created_at,
                   "actual_end": audit.actual_end, "deleted_at": audit.deleted_at,
                   "title": audit.title, "status": audit.status, "audit_ref": audit.audit_ref}[sort]
    ordering = sort_column.desc() if direction == "desc" else sort_column.asc()
    rows = query.order_by(ordering.nullslast(), audit.id.asc()).offset(offset).limit(limit).all()
    # Preserve the established rich public record contract and display names.
    from .router import _serialize_audit
    return {"items": [_serialize_audit(row, db) for row in rows], "total": total, "limit": limit, "offset": offset}
