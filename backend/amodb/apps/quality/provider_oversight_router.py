"""Scoped provider oversight; analytical evidence only, never approval authority."""
from __future__ import annotations

import csv
import io
from datetime import date, datetime, timedelta
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError
from uuid import uuid4
from typing import Any

from fastapi import APIRouter, Depends, HTTPException, Query
from fastapi.responses import Response
from sqlalchemy import text
from sqlalchemy.orm import Session

from amodb.apps.audit import services as audit_services
from amodb.database import get_read_db, get_write_db
from .tenant_security import TenantContext, require_quality_permission, set_postgres_tenant_context

router = APIRouter(prefix="/api/maintenance/{amo_code}/quality/provider-oversight",
                   tags=["Provider oversight"])

def _all(db: Session, sql: str, **params: Any) -> list[dict]:
    return [dict(x) for x in db.execute(text(sql),params).mappings().all()]

def _one(db: Session, sql: str, **params: Any) -> dict:
    row=db.execute(text(sql),params).mappings().first()
    return dict(row) if row else {}

def _context(db: Session, ctx: TenantContext) -> None:
    set_postgres_tenant_context(db,amo_id=ctx.amo_id,user_id=ctx.user_id)

def _tenant_today(db: Session, amo_id: str) -> date:
    tz=db.execute(text("SELECT time_zone FROM amos WHERE id=:amo"),{"amo":amo_id}).scalar()
    try: return datetime.now(ZoneInfo(tz or "UTC")).date()
    except ZoneInfoNotFoundError: return datetime.now(ZoneInfo("UTC")).date()

@router.get("/providers/{supplier_id}")
def provider_360(amo_code: str,supplier_id: int,
                 ctx: TenantContext=Depends(require_quality_permission("qms.supplier.view")),
                 db: Session=Depends(get_read_db)):
    _context(db,ctx)
    key={"amo":ctx.amo_id,"supplier":supplier_id}
    identity=_one(db,"""SELECT id,supplier_code,legal_name,
        CAST(status AS TEXT) status, CAST(risk_level AS TEXT) risk_level,is_active
        FROM procurement_suppliers WHERE amo_id=:amo AND id=:supplier""",**key)
    if not identity:raise HTTPException(404,"Provider not found")
    today=_tenant_today(db,ctx.amo_id)
    sites=_all(db,"""SELECT site_code,site_name,country,is_primary
        FROM external_provider_sites WHERE amo_id=:amo AND supplier_id=:supplier
        ORDER BY is_primary DESC,site_code LIMIT 100""",**key)
    scopes=_all(db,"""SELECT site_code,category,product_family,authority,
        approval_number,CAST(status AS TEXT) status,expires_on
        FROM procurement_supplier_approval_scopes
        WHERE amo_id=:amo AND supplier_id=:supplier ORDER BY site_code,category LIMIT 150""",**key)
    contracts=_all(db,"""SELECT contract_number,title,status,effective_on,expires_on,
        termination_notice_days FROM quality_external_provider_contracts
        WHERE amo_id=:amo AND supplier_id=:supplier ORDER BY expires_on NULLS LAST LIMIT 100""",**key)
    certificates=_all(db,"""SELECT certificate_type,issuing_authority,
        verification_state,valid_until FROM external_provider_certificates
        WHERE amo_id=:amo AND supplier_id=:supplier
        ORDER BY valid_until NULLS LAST LIMIT 100""",**key)
    evidence=_one(db,"""SELECT COUNT(*) total,
        COUNT(*) FILTER (WHERE status='VERIFIED' AND
        (valid_until IS NULL OR valid_until>=:today)) current_verified,
        COUNT(*) FILTER (WHERE status='VERIFIED' AND valid_until<:today) expired,
        COUNT(*) FILTER (WHERE status='PENDING') pending
        FROM quality_external_provider_evidence
        WHERE amo_id=:amo AND supplier_id=:supplier""",**key,today=today)
    cases=_all(db,"""SELECT id,category,case_kind,status,technical_state,
        safety_state,authority_state,next_review_due_on,decided_at
        FROM quality_provider_qualification_cases
        WHERE amo_id=:amo AND supplier_id=:supplier ORDER BY updated_at DESC LIMIT 30""",**key)
    surveillance=_all(db,"""SELECT kind,risk_level,due_on,outcome,audit_id
        FROM quality_provider_surveillance WHERE amo_id=:amo AND supplier_id=:supplier
        ORDER BY due_on DESC NULLS LAST LIMIT 60""",**key)
    restrictions=_one(db,"""SELECT COUNT(*) FILTER (WHERE status='ACTIVE') active,
        COUNT(*) recorded FROM quality_provider_restrictions
        WHERE amo_id=:amo AND supplier_id=:supplier""",**key)
    purchasing=_one(db,"""SELECT COUNT(*) total_orders,
        COUNT(*) FILTER (WHERE CAST(p.status AS TEXT)='FULFILLED') fulfilled,
        COUNT(*) FILTER (WHERE CAST(p.status AS TEXT)='FULFILLED'
          AND p.promised_delivery_date IS NOT NULL AND receipt.last_received IS NOT NULL) dated_fulfilled,
        COUNT(*) FILTER (WHERE CAST(p.status AS TEXT)='FULFILLED'
          AND p.promised_delivery_date IS NOT NULL AND
          CAST(receipt.last_received AS DATE)<=p.promised_delivery_date) on_time_fulfilled,
        COUNT(*) FILTER (WHERE p.promised_delivery_date<:today
          AND CAST(p.status AS TEXT) NOT IN ('FULFILLED','CLOSED','CANCELLED')) late_open
        FROM procurement_purchase_orders p LEFT JOIN (
          SELECT amo_id,purchase_order_id,MAX(received_at) last_received
          FROM procurement_receipts WHERE amo_id=:amo GROUP BY amo_id,purchase_order_id
        ) receipt ON receipt.amo_id=p.amo_id AND receipt.purchase_order_id=p.id
        WHERE p.amo_id=:amo AND p.supplier_id=:supplier""",**key,today=today)
    receiving=_one(db,"""SELECT COUNT(*) inspections,
        COUNT(*) FILTER (WHERE CAST(i.disposition AS TEXT) IN
          ('REJECTED','RETURN_TO_SUPPLIER','ON_HOLD','ESCALATED_TO_QUALITY')) discrepancies,
        COUNT(*) FILTER (WHERE CAST(i.disposition AS TEXT)='RETURN_TO_SUPPLIER') returns
        FROM procurement_receiving_inspections i
        JOIN procurement_receipts r ON r.amo_id=i.amo_id AND r.id=i.receipt_id
        JOIN procurement_purchase_orders p ON p.amo_id=r.amo_id AND p.id=r.purchase_order_id
        WHERE p.amo_id=:amo AND p.supplier_id=:supplier""",**key)
    work=_one(db,"""SELECT COUNT(*) total,
        COUNT(*) FILTER (WHERE status='CLOSED') closed,
        COUNT(*) FILTER (WHERE status NOT IN ('CLOSED','CANCELLED')) outstanding,
        AVG(EXTRACT(EPOCH FROM (closed_at-created_at))/3600)
          FILTER (WHERE closed_at IS NOT NULL) avg_turnaround_hours
        FROM external_contracted_work WHERE amo_id=:amo AND supplier_id=:supplier""",**key)
    returns=_one(db,"""SELECT COUNT(*) FILTER (WHERE action IN ('RMA','RETURN')) return_requests,
        COUNT(*) FILTER (WHERE action='WARRANTY') warranty_requests
        FROM external_procurement_events WHERE amo_id=:amo AND supplier_id=:supplier""",**key)
    concentration=_one(db,"""SELECT
        (SELECT COUNT(*) FROM procurement_purchase_orders WHERE amo_id=:amo) tenant_orders,
        (SELECT COUNT(*) FROM procurement_purchase_orders
         WHERE amo_id=:amo AND supplier_id=:supplier) provider_orders""",**key)
    history=_all(db,"""SELECT action,occurred_at
        FROM quality_provider_qualification_events WHERE amo_id=:amo
        AND supplier_id=:supplier ORDER BY occurred_at DESC,id DESC LIMIT 40""",**key)
    snapshots=_all(db,"""SELECT action,previous_status,current_status,risk_level,occurred_at
        FROM external_provider_oversight_snapshots WHERE amo_id=:amo AND supplier_id=:supplier
        ORDER BY occurred_at DESC,id DESC LIMIT 40""",**key)
    total_dated=int(purchasing.get("dated_fulfilled") or 0)
    all_orders=int(concentration.get("tenant_orders") or 0)
    supplier_orders=int(concentration.get("provider_orders") or 0)
    purchasing["on_time_percent"]=(round(100*int(purchasing.get("on_time_fulfilled") or 0)/total_dated,1)
                                     if total_dated else None)
    concentration["po_count_share_percent"]=(round(100*supplier_orders/all_orders,1) if all_orders else None)
    return {"supplier":identity,"sites":sites,"scopes":scopes,"contracts":contracts,
            "certificates":certificates,"evidence":evidence,"qualification_cases":cases,
            "surveillance":surveillance,"restrictions":restrictions,"procurement":purchasing,
            "receiving":receiving,"contracted_maintenance":work,"returns":returns,
            "concentration":concentration,"qualification_history":history,
            "lifecycle_snapshots":snapshots,"as_of":today.isoformat(),
            "computed_not_approval":True,
            "limitations":[
              "On-time indicator uses last recorded receipt of fulfilled orders, not carrier delivery proof.",
              "Concentration uses purchase-order count; multi-currency totals are not combined.",
              "Sole-source and critical supplier determinations require documented human review.",
              "Repeat findings, CAR effectiveness and warranty outcomes remain governed by their source departments.",
              "Snapshots begin with Phase 9 deployment; historic QMS events remain separately retained."]}

@router.get("/portfolio")
def portfolio(amo_code: str,
              ctx: TenantContext=Depends(require_quality_permission("qms.supplier.view")),
              db: Session=Depends(get_read_db)):
    _context(db,ctx)
    today=_tenant_today(db,ctx.amo_id)
    states=_all(db,"""SELECT CAST(status AS TEXT) status,
        CAST(risk_level AS TEXT) risk_level,COUNT(*) total
        FROM procurement_suppliers WHERE amo_id=:amo AND is_active=TRUE
        GROUP BY status,risk_level ORDER BY status,risk_level""",amo=ctx.amo_id)
    queue=_one(db,"""SELECT COUNT(*) FILTER
          (WHERE status IN ('SUBMITTED','IN_REVIEW','READY')) qualification_pending,
        COUNT(*) FILTER (WHERE next_review_due_on<=:today AND
          status IN ('APPROVED','CONDITIONALLY_APPROVED')) reviews_due
        FROM quality_provider_qualification_cases WHERE amo_id=:amo""",
        amo=ctx.amo_id,today=today)
    expires=_one(db,"""SELECT
        (SELECT COUNT(*) FROM quality_external_provider_contracts
          WHERE amo_id=:amo AND status='ACTIVE' AND expires_on BETWEEN :today AND :end) contracts,
        (SELECT COUNT(*) FROM external_provider_certificates
          WHERE amo_id=:amo AND verification_state='VERIFIED'
          AND valid_until BETWEEN :today AND :end) certificates,
        (SELECT COUNT(*) FROM procurement_supplier_approval_scopes
          WHERE amo_id=:amo AND CAST(status AS TEXT)='ACTIVE'
          AND expires_on BETWEEN :today AND :end) scopes""",
        amo=ctx.amo_id,today=today,end=today+timedelta(days=120))
    return {"states":states,"queue":queue,"next_120_days":expires,
            "as_of":today.isoformat(),"computed_not_approval":True}

@router.get("/calendar")
def expiry_calendar(amo_code: str,days:int=Query(default=120,ge=1,le=730),
              limit:int=Query(default=200,ge=1,le=500),
              ctx:TenantContext=Depends(require_quality_permission("qms.supplier.view")),
              db:Session=Depends(get_read_db)):
    _context(db,ctx)
    today=_tenant_today(db,ctx.amo_id)
    data=_all(db,"""SELECT due.kind,s.supplier_code, due.reference,due.due_on FROM (
        SELECT 'CONTRACT' kind,supplier_id,contract_number reference,expires_on due_on
        FROM quality_external_provider_contracts WHERE amo_id=:amo AND status='ACTIVE'
        UNION ALL SELECT 'CERTIFICATE',supplier_id,certificate_type,valid_until
        FROM external_provider_certificates WHERE amo_id=:amo AND verification_state='VERIFIED'
        UNION ALL SELECT 'CAPABILITY',supplier_id,category,expires_on
        FROM procurement_supplier_approval_scopes WHERE amo_id=:amo AND CAST(status AS TEXT)='ACTIVE'
        ) due JOIN procurement_suppliers s ON s.amo_id=:amo AND s.id=due.supplier_id
        WHERE due.due_on BETWEEN :today AND :end
        ORDER BY due.due_on,due.kind,due.supplier_id LIMIT :limit""",
        amo=ctx.amo_id,today=today,end=today+timedelta(days=days),limit=limit)
    return {"items":data,"limit":limit,"days":days,"as_of":today.isoformat()}

@router.get("/register.csv")
def export_register(amo_code: str,
             ctx:TenantContext=Depends(require_quality_permission("qms.supplier.view")),
             db:Session=Depends(get_write_db)):
    _context(db,ctx)
    data=_all(db,"""SELECT s.supplier_code,s.legal_name,
       CAST(s.status AS TEXT) status,CAST(s.risk_level AS TEXT) risk_level,
       COALESCE(p.provider_kind,s.supplier_type,'SUPPLIER') provider_kind,p.next_review_due_on
       FROM procurement_suppliers s LEFT JOIN quality_external_provider_profiles p
          ON p.amo_id=s.amo_id AND p.supplier_id=s.id
       WHERE s.amo_id=:amo AND s.is_active=TRUE
       ORDER BY s.legal_name,s.id LIMIT 10001""",amo=ctx.amo_id)
    if len(data)>10000: raise HTTPException(409,"Register too large for synchronous export")
    def safe(value):
        v=str(value or "")
        return "'"+v if v.lstrip().startswith(("=","+","-","@","\t","\r")) else v
    stream=io.StringIO()
    writer=csv.writer(stream)
    writer.writerow(["Supplier code","Legal name","Status","Risk","Kind","Next review"])
    for row in data:
        writer.writerow([safe(row.get(k)) for k in
           ("supplier_code","legal_name","status","risk_level","provider_kind","next_review_due_on")])
    audit_services.log_event(db,amo_id=ctx.amo_id,actor_user_id=ctx.user_id,
        entity_type="external_provider_register",entity_id=ctx.amo_id,
        action="controlled_export",after={"records":len(data)},
        correlation_id=str(uuid4()),metadata={"format":"CSV"},critical=True)
    db.commit()
    return Response(stream.getvalue(),media_type="text/csv; charset=utf-8",
        headers={"Content-Disposition":'attachment; filename="provider-register.csv"',
                 "Cache-Control":"no-store"})
