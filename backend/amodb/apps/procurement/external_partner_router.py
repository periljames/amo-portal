"""Phase 3 partner-facing projections. Never grants internal employee or QMS authority.

All routes are attached below the external cookie/session boundary. Every query
filters AMO and the canonical supplier, and tenant privileges bound in the
Phase 2 Quality-approved grant. No staff route is proxied to the vendor.
"""
from __future__ import annotations

import hashlib
import json
import re
import tempfile
from datetime import date, timedelta
from pathlib import Path
import uuid
from typing import Any, Literal

from fastapi import APIRouter, Depends, File, Form, HTTPException, Query, Request, UploadFile
from fastapi.responses import FileResponse
from pydantic import BaseModel, Field
from sqlalchemy import bindparam, text
from sqlalchemy.orm import Session

from amodb.database import get_db
from amodb.security import get_current_active_user
from amodb import storage
from . import external_auth_core as auth

router = APIRouter(prefix="/api/external-provider/partner/{tenant_slug}",
                   tags=["External Partner Portal"])
quality_router = APIRouter(prefix="/api/maintenance/{amo_code}/quality/external-accounts",
                           tags=["Partner change review"])

MAX_PAGE = 50
ALLOWED_CHANGE_FIELDS = {
    "IDENTITY": frozenset({"legal_name","trading_name","website","country","physical_address","phone","email"}),
    "CONTACT": frozenset({"contact_name","email","phone","assignment","site_id"}),
    "SITE": frozenset({"site_code","site_name","country","address","is_primary"}),
    "CAPABILITY": frozenset({"capability_type","description","rating","limitations","aircraft_type",
                           "engine_type","product_family","site_id"}),
    "BANKING": frozenset({"payment_terms","default_currency"}),
    "RENEWAL": frozenset({"certificate_id","contract_id","requested_until","supporting_note"}),
}

class ChangeProposal(BaseModel):
    category: Literal["IDENTITY","CONTACT","SITE","CAPABILITY","BANKING","RENEWAL"]
    fields: dict[str, Any]
    reason: str = Field(min_length=12,max_length=2000)
    source_version: int | None = Field(default=None,ge=1)

class ContractReceipt(BaseModel):
    acknowledgement: Literal["RECEIVED","REQUEST_CLARIFICATION"]
    note: str = Field(default="",max_length=2000)
    version: int = Field(ge=1)

class ReviewDecision(BaseModel):
    state: Literal["UNDER_REVIEW","ACCEPTED","REJECTED"]
    note: str = Field(min_length=8,max_length=2000)

def _row(q: str, db: Session, **params):
    value=db.execute(text(q),params).mappings().first()
    return dict(value) if value else None

def _rows(q: str,db:Session,**params):
    return [dict(x) for x in db.execute(text(q),params).mappings().all()]

def _ctx(db:Session,request:Request,tenant_slug:str,*,cap:str|None="profile.read",write:bool=False):
    user=auth.active_session(db,request,required=cap,write=write)
    tenant=_row("SELECT login_slug,amo_code FROM amos WHERE id=:id",db,id=user["amo_id"])
    if not tenant or tenant_slug.strip().lower() not in {
        str(tenant["login_slug"] or "").lower(),str(tenant["amo_code"] or "").lower()
    }:
        raise HTTPException(404,"Partner tenant not found")
    if db.get_bind().dialect.name=="postgresql":
        db.execute(text("SELECT set_config('app.external_provider_id',:provider,true)"),
                   {"provider":str(user["tenant_provider_id"])})
    return user

def _context(user):
    return {"amo":str(user["amo_id"]),"supplier":int(user["supplier_id"]),
            "provider":str(user["tenant_provider_id"]),"person":str(user["identity_id"])}

def _allowed(user,key:str):
    return {str(v) for v in (user["object_scope_json"] or {}).get(key,[])}

def _require_object(user,key:str,value:str):
    if str(value) not in _allowed(user,key):
        raise HTTPException(403,f"{key} object is not assigned to this provider member")

def _require_existing_related(db:Session,user,kind:str,value:str):
    """The scoped ID must also belong to this actual canonical tenant supplier."""
    if kind=="CONTRACT":
        _require_object(user,"contracts",value)
        found=_row("""SELECT id FROM quality_external_provider_contracts
            WHERE amo_id=:amo AND supplier_id=:supplier AND id=:item""",
            db,**_context(user),item=value)
    elif kind=="ASSIGNMENT":
        _require_object(user,"assignments",value)
        found=_row("""SELECT id FROM qms_audits
            WHERE amo_id=:amo AND CAST(id AS TEXT)=:item""",
            db,amo=user["amo_id"],item=value)
    elif kind=="RFQ":
        _require_object(user,"rfqs",value)
        found=_row("""SELECT r.id FROM procurement_rfqs r JOIN procurement_rfq_suppliers i
            ON i.rfq_id=r.id AND i.supplier_id=:supplier
            WHERE r.amo_id=:amo AND CAST(r.id AS TEXT)=:item
            AND r.issued_at IS NOT NULL AND r.status NOT IN ('DRAFT','CANCELLED')""",
            db,**_context(user),item=value)
    elif kind=="PO":
        _require_object(user,"purchase_orders",value)
        found=_row("""SELECT id FROM procurement_purchase_orders
            WHERE amo_id=:amo AND supplier_id=:supplier AND CAST(id AS TEXT)=:item
            AND sent_at IS NOT NULL""",db,**_context(user),item=value)
    elif kind=="CONTRACTED_WORK":
        _require_object(user,"contracted_work",value)
        found=_row("""SELECT id FROM external_contracted_work
            WHERE amo_id=:amo AND supplier_id=:supplier AND provider_id=:provider
              AND id=:item AND authorized_at IS NOT NULL AND status!='CANCELLED'""",
              db,**_context(user),item=value)
    elif kind=="SHIPMENT":
        # The shipment must be connected to an explicitly scoped issued PO.
        shipment=_row("""SELECT sh.po_id FROM external_procurement_shipments sh
            JOIN procurement_purchase_orders po ON po.id=sh.po_id
             AND po.amo_id=sh.amo_id AND po.supplier_id=sh.supplier_id
            WHERE sh.amo_id=:amo AND sh.supplier_id=:supplier AND sh.id=:item
             AND po.sent_at IS NOT NULL""",db,**_context(user),item=value)
        if shipment:
            _require_object(user,"purchase_orders",str(shipment["po_id"]))
        found=shipment
    else:
        raise HTTPException(422,"Unsupported related record type")
    if not found:
        raise HTTPException(404,"Assigned record is unavailable in this tenant")

def _cap(user,code:str):
    if code not in set(user["capabilities_json"] or []):
        raise HTTPException(403,"External privilege not granted")
    if user["portal_state"]!="ACTIVE" or user["restrict_new_work"]:
        raise HTTPException(403,"Provider operations are currently restricted")
    if str(user["supplier_lifecycle"]).split(".")[-1] not in {"APPROVED","CONDITIONALLY_APPROVED"} or not user["supplier_active"] or user["import_pending"]:
        raise HTTPException(403,"Canonical supplier is not authorized for new work")

def _page(limit:int,offset:int):
    return {"limit":min(MAX_PAGE,max(1,limit)),"offset":min(10000,max(0,offset))}

def _paged(db,stmt:str,ctx:dict,limit:int,offset:int,**additional):
    args={**ctx,**_page(limit,offset),**additional}
    # SELECT only bounded columns, not entire internal entities or staff data.
    items=_rows(stmt+" LIMIT :limit OFFSET :offset",db,**args)
    return {"items":items,"limit":args["limit"],"offset":args["offset"],
            "has_more":len(items)==args["limit"],"next_offset":args["offset"]+len(items)}

def _notify(db:Session,user,category:str,title:str,message:str,resource_kind:str,resource_id:str):
    ctx=_context(user)
    auth.run("""INSERT INTO external_partner_notifications
       (id,amo_id,tenant_provider_id,identity_id,category,title,message,resource_kind,resource_id)
       VALUES(:id,:amo,:provider,:person,:category,:title,:message,:kind,:resource)""",
       db,**ctx,id=auth.new_id(),category=category,title=title,message=message,
       kind=resource_kind,resource=resource_id)

@router.get("/session")
def partner_session(tenant_slug:str,request:Request,db:Session=Depends(get_db)):
    # Custom task/CAPA-only members must resolve their shell before work access.
    user=_ctx(db,request,tenant_slug,cap=None)
    supplier=_row("""SELECT s.supplier_code,s.legal_name,s.trading_name,s.status,s.is_active,
       s.external_import_pending_activation,p.portal_state,p.restrict_new_work,
       i.display_name,i.email
       FROM procurement_suppliers s JOIN external_tenant_providers p
       ON p.amo_id=s.amo_id AND p.supplier_id=s.id
       JOIN external_identities i ON i.id=:person
       WHERE s.amo_id=:amo AND s.id=:supplier AND p.id=:provider""",db,**_context(user))
    return {"tenant":tenant_slug,"organization":supplier,"role":user["role_code"],
            "capabilities":user["capabilities_json"],"session_state":"ACTIVE",
            "restricted":user["portal_state"]!="ACTIVE" or user["restrict_new_work"],
            "account_url":"/vendor/account"}

@router.get("/home")
def home(tenant_slug:str,request:Request,db:Session=Depends(get_db)):
    user=_ctx(db,request,tenant_slug)
    ctx=_context(user)
    supplier=_row("""SELECT s.legal_name,s.supplier_code,s.status,
        p.portal_state,p.restrict_new_work,COALESCE(q.next_review_due_on, NULL) review_due
        FROM procurement_suppliers s
        JOIN external_tenant_providers p ON p.amo_id=s.amo_id AND p.supplier_id=s.id
        LEFT JOIN quality_external_provider_profiles q ON q.amo_id=s.amo_id AND q.supplier_id=s.id
        WHERE s.amo_id=:amo AND s.id=:supplier AND p.id=:provider""",db,**ctx)
    cutoff=date.today()+timedelta(days=60)
    certificates=_rows("""SELECT certificate_type,certificate_number,valid_until,verification_state
        FROM external_provider_certificates
        WHERE amo_id=:amo AND supplier_id=:supplier AND valid_until<=:cutoff
        ORDER BY valid_until ASC LIMIT 8""",db,**ctx,cutoff=cutoff)
    assigned_contracts=sorted(_allowed(user,"contracts")) if "contract.read" in set(user["capabilities_json"] or []) else []
    contracts=_rows_compiled(db,text("""SELECT id,contract_number,title,expires_on,status
        FROM quality_external_provider_contracts
        WHERE amo_id=:amo AND supplier_id=:supplier AND expires_on<=:cutoff
        AND CAST(id AS TEXT) IN :ids
        ORDER BY expires_on ASC LIMIT 8""").bindparams(bindparam("ids",expanding=True)),
        {**ctx,"cutoff":cutoff,"ids":assigned_contracts}) if assigned_contracts else []
    pending=_row("""SELECT count(*) proposals FROM external_partner_change_requests
        WHERE amo_id=:amo AND tenant_provider_id=:provider AND status IN ('PENDING','UNDER_REVIEW')""",db,**ctx)
    unread=_row("""SELECT count(*) unread FROM external_partner_notifications
        WHERE amo_id=:amo AND tenant_provider_id=:provider AND identity_id=:person AND read_at IS NULL""",db,**ctx)
    can_view_tasks=("task.read" in set(user["capabilities_json"] or [])
       and user["portal_state"]=="ACTIVE" and not user["restrict_new_work"]
       and user["supplier_active"] and not user["import_pending"]
       and str(user["supplier_lifecycle"]).split(".")[-1] in {"APPROVED","CONDITIONALLY_APPROVED"})
    counts={"rfqs":0,"purchase_orders":0,"audit_requests":0,"cars":0}
    if can_view_tasks:
        counts["rfqs"]=int(_row("""SELECT count(*) n FROM procurement_rfq_suppliers t
            JOIN procurement_rfqs r ON r.id=t.rfq_id AND r.amo_id=:amo
            WHERE t.supplier_id=:supplier AND r.status NOT IN ('DRAFT','CANCELLED')
            AND t.responded_at IS NULL AND t.declined_at IS NULL""",db,**ctx)["n"])
        counts["purchase_orders"]=int(_row("""SELECT count(*) n FROM procurement_purchase_orders
            WHERE amo_id=:amo AND supplier_id=:supplier AND sent_at IS NOT NULL
            AND acknowledged_at IS NULL""",db,**ctx)["n"])
        assigned=sorted(_allowed(user,"assignments"))
        if assigned:
            counts["audit_requests"]=int(_rows_compiled(db,text("""SELECT count(*) n FROM
                quality_audit_document_requests WHERE amo_id=:amo
                AND CAST(audit_id AS TEXT) IN :assigned AND status='REQUESTED'""").bindparams(
                bindparam("assigned",expanding=True)),{**ctx,"assigned":assigned})[0]["n"])
            counts["cars"]=int(_rows_compiled(db,text("""SELECT count(*) n FROM quality_cars c
                JOIN qms_audit_findings f ON f.id=c.finding_id AND f.amo_id=c.amo_id
                WHERE c.amo_id=:amo AND CAST(f.audit_id AS TEXT) IN :assigned
                AND c.closed_at IS NULL
                AND (SELECT release.action FROM quality_audit_finding_release_events release
                     WHERE release.amo_id=f.amo_id AND release.finding_id=f.id
                     AND release.audit_id=f.audit_id
                     ORDER BY release.created_at DESC,release.id DESC LIMIT 1)='RELEASED'""").bindparams(
                bindparam("assigned",expanding=True)),{**ctx,"assigned":assigned})[0]["n"])
    # Bounded authoritative due-work projections. No internal employee IDs,
    # hidden draft items or unpublished CARs are surfaced to partners.
    urgent_tasks=[]
    if can_view_tasks:
        urgent_tasks.extend([{"kind":"RFQ","title":f"Quotation: {x['rfq_number']}",
            "due":x["response_due_at"],"to":"procurement"} for x in _rows("""
            SELECT r.rfq_number,r.response_due_at FROM procurement_rfqs r
            JOIN procurement_rfq_suppliers t ON t.rfq_id=r.id
            WHERE r.amo_id=:amo AND t.supplier_id=:supplier
            AND r.status NOT IN ('DRAFT','CANCELLED')
            AND t.responded_at IS NULL AND t.declined_at IS NULL
            ORDER BY r.response_due_at NULLS LAST,r.id LIMIT 5""",db,**ctx)])
        urgent_tasks.extend([{"kind":"PURCHASE_ORDER","title":f"Acknowledge PO {x['po_number']}",
            "due":x["promised_delivery_date"],"to":"procurement"} for x in _rows("""
            SELECT po_number,promised_delivery_date FROM procurement_purchase_orders
            WHERE amo_id=:amo AND supplier_id=:supplier AND sent_at IS NOT NULL
            AND acknowledged_at IS NULL
            ORDER BY promised_delivery_date NULLS LAST,id LIMIT 5""",db,**ctx)])
    assigned=sorted(_allowed(user,"assignments"))
    if assigned and can_view_tasks:
        args={**ctx,"assigned":assigned}
        urgent_tasks.extend([{"kind":"AUDIT_DOCUMENT","title":f"Audit {x['audit_ref']}: {x['title']}",
            "due":x["due_date"],"to":"quality"} for x in _rows_compiled(db,text("""
            SELECT r.title,r.due_date,a.audit_ref FROM quality_audit_document_requests r
            JOIN qms_audits a ON a.id=r.audit_id AND a.amo_id=r.amo_id
            WHERE r.amo_id=:amo AND CAST(r.audit_id AS TEXT) IN :assigned
            AND r.status='REQUESTED'
            ORDER BY r.due_date NULLS LAST,r.id LIMIT 5""").bindparams(
            bindparam("assigned",expanding=True)),args)])
    if assigned and (can_view_tasks or "capa.respond" in set(user["capabilities_json"] or [])):
        urgent_tasks.extend([{"kind":"CAR","title":f"Corrective action {x['car_number']}",
            "due":x["due_date"],"to":"quality"} for x in _rows_compiled(db,text("""
            SELECT c.car_number,c.due_date FROM quality_cars c
            JOIN qms_audit_findings f ON f.amo_id=c.amo_id AND f.id=c.finding_id
            WHERE c.amo_id=:amo AND CAST(f.audit_id AS TEXT) IN :assigned
            AND c.closed_at IS NULL
            AND (SELECT re.action FROM quality_audit_finding_release_events re
                WHERE re.amo_id=f.amo_id AND re.audit_id=f.audit_id
                AND re.finding_id=f.id
                ORDER BY re.created_at DESC,re.id DESC LIMIT 1)='RELEASED'
            ORDER BY c.due_date NULLS LAST,c.id LIMIT 5""").bindparams(
            bindparam("assigned",expanding=True)),{**ctx,"assigned":assigned})])
    urgent_tasks.sort(key=lambda item: (str(item["due"] or "9999-12-31"),item["kind"]))
    latest_notifications=_rows("""SELECT id,title,category,created_at,read_at FROM
        external_partner_notifications WHERE amo_id=:amo AND tenant_provider_id=:provider
        AND identity_id=:person ORDER BY created_at DESC,id DESC LIMIT 5""",db,**ctx)
    approved_scope=_rows("""SELECT category,product_family,site_code,approval_number
        FROM procurement_supplier_approval_scopes
        WHERE amo_id=:amo AND supplier_id=:supplier AND status='ACTIVE'
        AND (expires_on IS NULL OR expires_on>=CURRENT_DATE)
        ORDER BY category,product_family,id LIMIT 8""",db,**ctx)
    return {"supplier":supplier,"expiring_certificates":certificates,
            "expiring_contracts":contracts,"outstanding_tasks":counts,
            "urgent_tasks":urgent_tasks[:16],
            "recent_notifications":latest_notifications,"approved_scope":approved_scope,
            "open_change_requests":int(pending["proposals"] or 0),
            "unread_notifications":int(unread["unread"] or 0),
            "actions":[{"kind":"CERTIFICATE_RENEWAL","title":f"Renew {c['certificate_type']}",
                        "due":c["valid_until"],"to":"compliance"} for c in certificates],
            "operational_sections_available":user["portal_state"]=="ACTIVE" and not user["restrict_new_work"]}

@router.get("/organization")
def organization(tenant_slug:str,request:Request,db:Session=Depends(get_db)):
    user=_ctx(db,request,tenant_slug)
    ctx=_context(user)
    supplier=_row("""SELECT supplier_code,legal_name,trading_name,supplier_type,status,
       email,phone,website,country,physical_address,default_currency,
       payment_terms,approved_at FROM procurement_suppliers
       WHERE amo_id=:amo AND id=:supplier""",db,**ctx)
    profile=_row("""SELECT provider_kind,scope_summary,quality_requirements,
       review_interval_days,next_review_due_on,contract_required
       FROM quality_external_provider_profiles
       WHERE amo_id=:amo AND supplier_id=:supplier""",db,**ctx)
    roles=_rows("""SELECT role_code,notes FROM external_provider_roles
       WHERE amo_id=:amo AND supplier_id=:supplier ORDER BY role_code LIMIT 40""",db,**ctx)
    if "contract.read" not in set(user["capabilities_json"] or []):
        supplier.pop("payment_terms",None)
    return {"supplier":supplier,"profile":profile,"roles":roles,
            "change_policy":"PROPOSE_THEN_QUALITY_REVIEW",
            "banking_change_policy":"NO_DIRECT_BANK_DETAILS"}

_ORG_LIST={
    "sites":("external_provider_sites","site_code,site_name,country,address,is_primary,version","site_code"),
    "contacts":("external_provider_contacts","contact_name,email,phone,assignment,version","contact_name"),
    "capabilities":("external_provider_capabilities","description,capability_type,aircraft_type,engine_type,rating,limitations,valid_until,version","description"),
}
@router.get("/organization/{kind}")
def organization_list(tenant_slug:str,kind:str,request:Request,db:Session=Depends(get_db),
                      limit:int=Query(20,ge=1,le=50),offset:int=Query(0,ge=0,le=10000),
                      search:str=Query("",max_length=100)):
    user=_ctx(db,request,tenant_slug)
    if kind not in _ORG_LIST:raise HTTPException(404,"Unknown organization section")
    table,columns,order=_ORG_LIST[kind]
    return _paged(db,f"""SELECT {columns} FROM {table}
        WHERE amo_id=:amo AND supplier_id=:supplier
        AND lower({order}) LIKE :search ORDER BY {order},id""",_context(user),
        limit,offset,search=f"%{search.strip().lower()}%")

@router.get("/change-requests")
def changes(tenant_slug:str,request:Request,db:Session=Depends(get_db),
            limit:int=Query(20,ge=1,le=50),offset:int=Query(0,ge=0,le=10000)):
    user=_ctx(db,request,tenant_slug)
    return _paged(db,"""SELECT id,category,proposed_json,status,reason,review_note,
       created_at,reviewed_at,version FROM external_partner_change_requests
       WHERE amo_id=:amo AND tenant_provider_id=:provider
       ORDER BY created_at DESC,id DESC""",_context(user),limit,offset)

@router.post("/change-requests",status_code=201)
def propose(tenant_slug:str,payload:ChangeProposal,request:Request,db:Session=Depends(get_db)):
    user=_ctx(db,request,tenant_slug,cap="profile.propose",write=True)
    _cap(user,"profile.propose")
    allowed=ALLOWED_CHANGE_FIELDS[payload.category]
    if not payload.fields or set(payload.fields)-allowed:
        raise HTTPException(422,"Unsupported or empty governed change fields")
    if len(json.dumps(payload.fields))>6000:
        raise HTTPException(413,"Proposed changes exceed the supported size")
    # PII and bank-account numbers are not accepted into freeform JSON;
    # bank account details require the later approved commercial workflow.
    if payload.category=="BANKING":
        if "contract.read" not in set(user["capabilities_json"] or []):
            raise HTTPException(403,"Commercial change privilege not granted")
        auth.require_recent_mfa(db,user)
        if set(payload.fields)-{"payment_terms","default_currency"}:
            raise HTTPException(403,"Sensitive banking account details require the controlled commercial process")
    if payload.category=="RENEWAL":
        ident=payload.fields.get("certificate_id") or payload.fields.get("contract_id")
        if not ident:raise HTTPException(422,"Identify the certificate or assigned contract to renew")
        if "contract_id" in payload.fields:
            _require_object(user,"contracts",str(payload.fields["contract_id"]))
            if not _row("""SELECT id FROM quality_external_provider_contracts
                WHERE amo_id=:amo AND supplier_id=:supplier AND id=:id""",db,
                **_context(user),id=str(payload.fields["contract_id"])):
                raise HTTPException(404,"Assigned renewal contract not found")
        if "certificate_id" in payload.fields:
            if not _row("""SELECT id FROM external_provider_certificates
                WHERE amo_id=:amo AND supplier_id=:supplier
                AND CAST(id AS TEXT)=:id""",db,
                **_context(user),id=str(payload.fields["certificate_id"])):
                raise HTTPException(404,"Certificate is not part of this provider")
    auth.auth_limit(request,str(user["identity_id"]),"partner-change-proposal")
    ctx=_context(user);id=auth.new_id()
    auth.run("""INSERT INTO external_partner_change_requests
        (id,amo_id,tenant_provider_id,identity_id,category,proposed_json,reason,source_version)
        VALUES(:id,:amo,:provider,:person,:category,CAST(:data AS JSON),:reason,:version)""",
        db,**ctx,id=id,category=payload.category,data=json.dumps(payload.fields),
        reason=payload.reason.strip(),version=payload.source_version)
    auth.event(db,amo=ctx["amo"],identity=ctx["person"],grant=user["grant_id"],
        action="PARTNER_CHANGE_PROPOSED",actor_identity=ctx["person"],
        details={"proposal_id":id,"category":payload.category})
    _notify(db,user,"REVIEW","Change request submitted",
        "Your change is pending authorized Quality/commercial review.","CHANGE",id)
    db.commit()
    return {"id":id,"status":"PENDING","applied_to_supplier":False}

@router.get("/compliance")
def compliance(tenant_slug:str,request:Request,db:Session=Depends(get_db),
               limit:int=Query(20,ge=1,le=50),offset:int=Query(0,ge=0,le=10000)):
    user=_ctx(db,request,tenant_slug)
    ctx=_context(user)
    scopes=_paged(db,"""SELECT category,product_family,site_code,authority,status,expires_on,
        restrictions,approval_number,evidence_reference FROM procurement_supplier_approval_scopes
        WHERE amo_id=:amo AND supplier_id=:supplier ORDER BY expires_on NULLS LAST,id""",ctx,limit,offset)
    certificates=_paged(db,"""SELECT id,certificate_type,certificate_number,issuing_authority,
       approval_rating,verification_state,valid_from,valid_until,limitations
       FROM external_provider_certificates WHERE amo_id=:amo AND supplier_id=:supplier
       ORDER BY valid_until NULLS LAST,id""",ctx,limit,offset)
    page=_page(limit,offset)
    blank={"items":[],"limit":page["limit"],"offset":page["offset"],"has_more":False,
           "next_offset":page["offset"]}
    if "document.read" in set(user["capabilities_json"] or []):
        scope={"contracts":sorted(_allowed(user,"contracts")),
               "assignments":sorted(_allowed(user,"assignments"))}
        q=text("""SELECT id,evidence_type,title,status,valid_until,source_system,created_at
            FROM quality_external_provider_evidence
            WHERE amo_id=:amo AND supplier_id=:supplier
            AND (contract_id IS NULL OR CAST(contract_id AS TEXT) IN :contracts)
            ORDER BY created_at DESC,id DESC LIMIT :limit OFFSET :offset""").bindparams(
            bindparam("contracts",expanding=True))
        governed=_rows_compiled(db,q,{**ctx,**page,"contracts":scope["contracts"]})
        evidence={**page,"items":governed,"has_more":len(governed)==page["limit"],
                  "next_offset":page["offset"]+len(governed)}
        sql=text("""SELECT id,evidence_type,filename,status,related_kind,related_id,
             created_at,review_note FROM external_partner_evidence_submissions
             WHERE amo_id=:amo AND tenant_provider_id=:provider
             AND (related_kind='PROVIDER'
               OR (related_kind='CONTRACT' AND related_id IN :contracts)
               OR (related_kind='ASSIGNMENT' AND related_id IN :assignments))
             ORDER BY created_at DESC,id DESC LIMIT :limit OFFSET :offset""").bindparams(
             bindparam("contracts",expanding=True),bindparam("assignments",expanding=True))
        rows=_rows_compiled(db,sql,{**ctx,**page,**scope})
        submissions={**page,"items":rows,"has_more":len(rows)==page["limit"],
                     "next_offset":page["offset"]+len(rows)}
    else:
        evidence=blank
        submissions=blank
    return {"approval_scopes":scopes,"certificates":certificates,"governed_evidence":evidence,
            "submitted_evidence":submissions,
            "verification_notice":"New uploads remain pending Quality review; an upload does not renew or approve a certificate."}

@router.get("/contracts")
def contracts(tenant_slug:str,request:Request,db:Session=Depends(get_db),
              limit:int=Query(20,ge=1,le=50),offset:int=Query(0,ge=0,le=10000),
              search:str=Query("",max_length=100)):
    user=_ctx(db,request,tenant_slug,cap="contract.read")
    ids=_allowed(user,"contracts")
    if not ids:return {"items":[],"limit":limit,"offset":offset,"has_more":False,"next_offset":offset}
    return _page_contracts(db,user,ids,limit,offset,search)

def _page_contracts(db,user,ids,limit,offset,search=""):
    # Safe expanding SQL parameter; never interpolate member-controlled identifiers.
    sql=text("""SELECT id,contract_number,title,status,scope_text,effective_on,expires_on,
       renewal_terms,version,controlled_document_id,controlled_document_revision
       FROM quality_external_provider_contracts
       WHERE amo_id=:amo AND supplier_id=:supplier AND CAST(id AS TEXT) IN :assigned
       AND lower(title) LIKE :search ORDER BY expires_on NULLS LAST,id
       LIMIT :limit OFFSET :offset""").bindparams(bindparam("assigned",expanding=True))
    args={**_context(user),"assigned":sorted(ids),**_page(limit,offset),"search":f"%{search.strip().lower()}%"}
    found=_rows_compiled(db,sql,args)
    document_grants=_allowed(user,"documents")
    has_doc_read="document.read" in set(user["capabilities_json"] or [])
    return {"items":[{**x,"controlled_document_access":(
                  "PUBLISHED_REVISION_CHECK_REQUIRED" if has_doc_read
                  and str(x["controlled_document_id"]) in document_grants
                  and x["controlled_document_revision"] else "REQUIRES_EXPLICIT_DMS_RELEASE")}
                    for x in found],"limit":args["limit"],"offset":args["offset"],
            "has_more":len(found)==args["limit"],"next_offset":args["offset"]+len(found)}

def _rows_compiled(db,sql,args):
    return [dict(r) for r in db.execute(sql,args).mappings().all()]

@router.get("/contracts/{contract_id}/document")
def download_controlled_agreement(tenant_slug:str,contract_id:str,
                                 request:Request,db:Session=Depends(get_db)):
    """Permit only a published, exact-revision DMS attachment assigned to the
    current provider, contract and external identity. Internal DMS routes remain
    inaccessible to vendor cookie sessions.
    """
    user=_ctx(db,request,tenant_slug,cap="document.read")
    if "contract.read" not in set(user["capabilities_json"] or []):
        raise HTTPException(403,"Agreement read privilege required")
    _require_existing_related(db,user,"CONTRACT",contract_id)
    ctx=_context(user)
    contract=_row("""SELECT status,controlled_document_id,controlled_document_revision,
            effective_on,expires_on FROM quality_external_provider_contracts
            WHERE amo_id=:amo AND supplier_id=:supplier AND id=:contract""",
            db,**ctx,contract=contract_id)
    if not contract or contract["status"]=="DRAFT":
        raise HTTPException(404,"No executed controlled agreement available")
    if contract["status"]=="ACTIVE" and contract["effective_on"] and contract["effective_on"]>date.today():
        raise HTTPException(403,"Agreement has not reached its effective date")
    historical = contract["status"]!="ACTIVE" or (
        contract["expires_on"] is not None and contract["expires_on"]<date.today())
    # Historical originals remain readable by expressly assigned members,
    # without implying that the agreement permits current maintenance work.
    manual_id=contract["controlled_document_id"]
    desired_revision=contract["controlled_document_revision"]
    if not manual_id or not desired_revision:
        raise HTTPException(404,"No controlled document revision linked to this agreement")
    _require_object(user,"documents",str(manual_id))
    revision=_row("""SELECT r.id,r.rev_number,r.source_filename,
           r.stamped_export_uri,r.source_storage_path,r.source_mime_type,r.source_sha256
        FROM manuals m
        JOIN manual_tenants t ON t.id=m.tenant_id
        JOIN manual_revisions r ON r.manual_id=m.id
        WHERE t.amo_id=:amo AND m.id=:manual
        AND r.status_enum IN ('PUBLISHED','SUPERSEDED','ARCHIVED')
        AND (r.id=:revision OR r.rev_number=:revision)
        AND (:historical OR r.id=m.current_published_rev_id)
        AND r.published_at IS NOT NULL""",
        db,amo=ctx["amo"],manual=str(manual_id),revision=str(desired_revision),
         historical=historical)
    if not revision:
        raise HTTPException(409,"The linked original is no longer a valid controlled revision for this agreement")
    uri=revision["stamped_export_uri"] or revision["source_storage_path"]
    if not uri:
        raise HTTPException(409,"The published document has no secured source attachment")
    # Only our storage adapter can resolve the controlled binary. Never redirect
    # the provider to a raw signed S3/internal manual URL.
    try:
        filepath=storage.materialize(uri,
            expected_sha256=None if revision["stamped_export_uri"] else revision["source_sha256"])
    except (OSError,ValueError,RuntimeError) as exc:
        raise HTTPException(409,"Controlled document source is temporarily unavailable") from exc
    source_name=Path(revision["source_filename"] or "controlled-agreement").name
    filename=(str(Path(source_name).with_suffix(".pdf")) if revision["stamped_export_uri"]
              else source_name)
    content_type="application/pdf" if revision["stamped_export_uri"] else (
        revision["source_mime_type"] or "application/octet-stream"
    )
    auth.event(db,amo=ctx["amo"],identity=ctx["person"],grant=user["grant_id"],
        action="PARTNER_CONTROLLED_REVISION_DOWNLOADED",actor_identity=ctx["person"],
        details={"contract_id":contract_id,"manual_id":manual_id,"revision_id":revision["id"]})
    db.commit()
    return FileResponse(filepath,media_type=content_type,filename=filename,
        headers={"Cache-Control":"private, no-store","X-Content-Type-Options":"nosniff",
                  "X-Agreement-Historical-Record":"true" if historical else "false"})

@router.post("/contracts/{contract_id}/receipt",status_code=201)
def contract_receipt(tenant_slug:str,contract_id:str,payload:ContractReceipt,
                     request:Request,db:Session=Depends(get_db)):
    user=_ctx(db,request,tenant_slug,cap="contract.acknowledge",write=True)
    _cap(user,"contract.acknowledge")
    _require_object(user,"contracts",contract_id)
    ctx=_context(user)
    row=_row("""SELECT id,version,status,controlled_document_revision
        FROM quality_external_provider_contracts WHERE amo_id=:amo
        AND supplier_id=:supplier AND id=:id""",db,**ctx,id=contract_id)
    if not row:raise HTTPException(404,"Assigned agreement not found")
    if int(row["version"])!=payload.version:raise HTTPException(409,"Agreement revision changed; refresh and review it again")
    if row["status"] not in {"ACTIVE","SUSPENDED"}:raise HTTPException(409,"Agreement is not available for acknowledgement")
    # This is a non-signature receipt. Formal acceptance requires controlled
    # document release, party authorization and later contract workflows.
    id=auth.new_id()
    found=_row("""SELECT id FROM external_partner_contract_receipts WHERE
        amo_id=:amo AND tenant_provider_id=:provider AND identity_id=:person
        AND contract_id=:contract AND contract_version=:version""",db,**ctx,
        contract=contract_id,version=payload.version)
    if found:raise HTTPException(409,"This revision is already acknowledged by this member")
    auth.run("""INSERT INTO external_partner_contract_receipts
        (id,amo_id,tenant_provider_id,identity_id,contract_id,supplier_id,contract_version,
         document_revision,acknowledgement,note)
         VALUES(:id,:amo,:provider,:person,:contract,:supplier,:version,:revision,:ack,:note)""",
        db,**ctx,id=id,contract=contract_id,version=payload.version,
        revision=row["controlled_document_revision"],ack=payload.acknowledgement,note=payload.note)
    auth.event(db,amo=ctx["amo"],identity=ctx["person"],grant=user["grant_id"],
        action="CONTRACT_RECEIPT_RECORDED",actor_identity=ctx["person"],
        details={"contract_id":contract_id,"version":payload.version,"receipt":payload.acknowledgement})
    _notify(db,user,"CONTRACT","Agreement receipt recorded",
        "Your receipt is recorded. It is not a contractual signature.","CONTRACT",contract_id)
    db.commit()
    return {"id":id,"status":"RECORDED","binding_signature":False}

@router.get("/quality")
def quality(tenant_slug:str,request:Request,db:Session=Depends(get_db),
            limit:int=Query(20,ge=1,le=50),offset:int=Query(0,ge=0,le=10000)):
    # This read projection admits either task.read or capa.respond below.
    user=_ctx(db,request,tenant_slug,cap=None)
    capabilities=set(user["capabilities_json"] or [])
    if not capabilities.intersection({"task.read","capa.respond"}):
        raise HTTPException(403,"Assigned Quality tasks are not granted")
    ctx=_context(user)
    assignments=_allowed(user,"assignments")
    empty={"items":[],"limit":limit,"offset":offset,"has_more":False}
    if not assignments:
        return {"notices":empty,"document_requests":empty,"findings":empty,
                "cars":empty,"accepted_evidence":empty,"submission_policy":"No assigned audit work"}
    params={**ctx,**_page(limit,offset),"assigned":sorted(assignments)}
    read_operations=("task.read" in capabilities and user["portal_state"]=="ACTIVE"
        and not user["restrict_new_work"] and user["supplier_active"]
        and not user["import_pending"]
        and str(user["supplier_lifecycle"]).split(".")[-1] in {"APPROVED","CONDITIONALLY_APPROVED"})
    notices=_rows_compiled(db,text("""SELECT n.id,n.subject,n.status,n.revision_no,n.notice_date,
        a.audit_ref,a.title FROM quality_audit_notices n
        JOIN qms_audits a ON a.id=n.audit_id AND a.amo_id=n.amo_id
        WHERE n.amo_id=:amo AND CAST(n.audit_id AS TEXT) IN :assigned
        AND n.status IN ('DELIVERED','ACKNOWLEDGED')
        ORDER BY n.notice_date DESC LIMIT :limit OFFSET :offset""").bindparams(
          bindparam("assigned",expanding=True)),params) if read_operations else []
    requests=_rows_compiled(db,text("""SELECT r.id,r.title,r.description,r.due_date,r.status,
        a.audit_ref FROM quality_audit_document_requests r
        JOIN qms_audits a ON a.amo_id=r.amo_id AND a.id=r.audit_id
        WHERE r.amo_id=:amo AND CAST(r.audit_id AS TEXT) IN :assigned
        ORDER BY r.due_date NULLS LAST,r.id LIMIT :limit OFFSET :offset""").bindparams(
          bindparam("assigned",expanding=True)),params) if read_operations else []
    findings=_rows_compiled(db,text("""SELECT f.id,f.finding_ref,f.description,f.requirement_ref,
        CAST(f.severity AS TEXT) severity,f.target_close_date,f.closed_at
        FROM qms_audit_findings f
        WHERE f.amo_id=:amo AND CAST(f.audit_id AS TEXT) IN :assigned
        AND (SELECT release.action FROM quality_audit_finding_release_events release
             WHERE release.amo_id=f.amo_id AND release.audit_id=f.audit_id
             AND release.finding_id=f.id
             ORDER BY release.created_at DESC,release.id DESC LIMIT 1)='RELEASED'
        ORDER BY f.created_at DESC,f.id LIMIT :limit OFFSET :offset""").bindparams(
          bindparam("assigned",expanding=True)),params) if read_operations else []
    may_read_cars=read_operations or "capa.respond" in capabilities
    cars=_rows_compiled(db,text("""SELECT c.id,c.car_number,c.title,c.status,c.due_date,
        c.root_cause_status,c.capa_status,CAST(f.audit_id AS TEXT) assignment_id
        FROM quality_cars c
        JOIN qms_audit_findings f ON f.id=c.finding_id AND f.amo_id=c.amo_id
        WHERE c.amo_id=:amo AND CAST(f.audit_id AS TEXT) IN :assigned
        AND (SELECT release.action FROM quality_audit_finding_release_events release
             WHERE release.amo_id=f.amo_id AND release.audit_id=f.audit_id
             AND release.finding_id=f.id
             ORDER BY release.created_at DESC,release.id DESC LIMIT 1)='RELEASED'
        ORDER BY c.due_date NULLS LAST,c.id LIMIT :limit OFFSET :offset""").bindparams(
          bindparam("assigned",expanding=True)),params) if may_read_cars else []
    evidence=_rows_compiled(db,text("""SELECT id,related_id,filename,evidence_type,status
        FROM external_partner_evidence_submissions
        WHERE amo_id=:amo AND tenant_provider_id=:provider
        AND related_kind='ASSIGNMENT' AND related_id IN :assigned
        AND status='ACCEPTED'
        AND (identity_id=:person OR :can_read)
        ORDER BY created_at DESC LIMIT :limit OFFSET :offset""").bindparams(
          bindparam("assigned",expanding=True)),{**params,"can_read":"document.read" in capabilities}) if may_read_cars else []
    return {"notices":{"items":notices,"limit":limit,"offset":offset},
        "document_requests":{"items":requests,"limit":limit,"offset":offset},
        "findings":{"items":findings,"limit":limit,"offset":offset},
        "cars":{"items":cars,"limit":limit,"offset":offset},
        "accepted_evidence":{"items":evidence,"limit":limit,"offset":offset},
        "submission_policy":"CARs are submitted through the authoritative Quality response handler; supporting uploads require Quality review."}


class CorrectiveActionSubmission(BaseModel):
    containment_action: str = Field(min_length=2,max_length=500)
    root_cause: str = Field(min_length=12,max_length=500)
    corrective_action: str = Field(min_length=12,max_length=500)
    preventive_action: str = Field(default="",max_length=500)
    evidence_submission_id: str | None = Field(default=None,max_length=36)

@router.post("/quality/cars/{car_id}/submit")
def submit_partner_capa(tenant_slug:str,car_id:str,payload:CorrectiveActionSubmission,
                        request:Request,db:Session=Depends(get_db)):
    """Invoke the existing Quality CAR submission workflow, never a parallel CAR."""
    user=_ctx(db,request,tenant_slug,cap="capa.respond",write=True)
    ctx=_context(user)
    assigned=_allowed(user,"assignments")
    if not assigned:raise HTTPException(403,"No issued audit/CAR assignment")
    car=_rows_compiled(db,text("""SELECT c.id,c.invite_token,c.evidence_required,
        CAST(f.audit_id AS TEXT) assignment_id FROM quality_cars c
        JOIN qms_audit_findings f ON f.id=c.finding_id AND f.amo_id=c.amo_id
        WHERE c.amo_id=:amo AND CAST(c.id AS TEXT)=:id
        AND CAST(f.audit_id AS TEXT) IN :assignments
        AND (SELECT release.action FROM quality_audit_finding_release_events release
             WHERE release.amo_id=f.amo_id AND release.audit_id=f.audit_id
             AND release.finding_id=f.id
             ORDER BY release.created_at DESC,release.id DESC LIMIT 1)='RELEASED'""").bindparams(bindparam("assignments",expanding=True)),
        {**ctx,"id":car_id,"assignments":sorted(assigned)})
    if len(car)!=1:raise HTTPException(404,"Assigned corrective action not found")
    evidence_reference=None
    if payload.evidence_submission_id:
        evidence=_row("""SELECT id,sha256,related_kind,related_id,status
            FROM external_partner_evidence_submissions
            WHERE amo_id=:amo AND tenant_provider_id=:provider AND id=:id""",
            db,**ctx,id=payload.evidence_submission_id)
        if (not evidence or evidence["status"]!="ACCEPTED" or
                evidence["related_kind"]!="ASSIGNMENT" or evidence["related_id"]!=car[0]["assignment_id"]):
            raise HTTPException(409,"Attach Quality-reviewed evidence assigned to this exact audit")
        evidence_reference=f"PARTNER:{evidence['id']}:{evidence['sha256']}"
    if car[0]["evidence_required"] and not evidence_reference:
        raise HTTPException(409,"This CAR requires reviewed and linked objective evidence")
    from amodb.apps.quality.router import submit_car_from_invite
    from amodb.apps.quality.schemas import CARInviteUpdate
    actor=_row("SELECT display_name,email FROM external_identities WHERE id=:id",db,id=ctx["person"])
    submit_car_from_invite(str(car[0]["invite_token"]),CARInviteUpdate(
        containment_action=payload.containment_action,root_cause=payload.root_cause,
        corrective_action=payload.corrective_action,preventive_action=payload.preventive_action,
        evidence_ref=evidence_reference,
        submitted_by_name=actor["display_name"],submitted_by_email=actor["email"]),request,db)
    # The authoritative CAR handler commits, ending SET LOCAL RLS context.
    # Restore BOTH tenant and external provider before recording partner events
    # and notifications in the new transaction.
    auth.context(db,ctx["amo"],ctx["person"])
    if db.get_bind().dialect.name=="postgresql":
        db.execute(text("SELECT set_config('app.external_provider_id',:provider,true)"),
                   {"provider":ctx["provider"]})
    auth.event(db,amo=ctx["amo"],identity=ctx["person"],grant=user["grant_id"],
        action="PARTNER_CAR_RESPONSE_SUBMITTED",actor_identity=ctx["person"],
        details={"car_id":car_id,"assignment_id":car[0]["assignment_id"]})
    _notify(db,user,"QUALITY","Corrective action submitted",
        "Your response is now in the authoritative Quality CAR review queue.","CAR",car_id)
    db.commit()
    return {"status":"SUBMITTED","authoritative_domain":"QUALITY_CAR"}


class PartnerQualificationAnswers(BaseModel):
    case_version:int=Field(ge=1)
    answers:dict[str,str]
    note:str=Field(min_length=8,max_length=2000)


@router.get("/qualification")
def partner_qualification(tenant_slug:str,request:Request,db:Session=Depends(get_db)):
    """Only the canonical supplier's partner-facing qualification items.
    Staff-only evidence verdicts, internal risk deliberations and raw IDs are
    excluded. Qualification does not grant the provider approval rights.
    """
    user=_ctx(db,request,tenant_slug,cap="profile.read")
    ctx=_context(user)
    rows=_rows("""SELECT id,category,case_kind,status,version,
        policy_snapshot_json,answers_json,submitted_at,next_review_due_on,
        technical_state,safety_state,authority_state
        FROM quality_provider_qualification_cases
        WHERE amo_id=:amo AND supplier_id=:supplier
        ORDER BY created_at DESC LIMIT 20""",db,**ctx)
    # Keep internal-only decisions out of the partner projection.
    for row in rows:
        policy=row.pop("policy_snapshot_json") or {}
        row["questionnaire"]=policy.get("questionnaire",[])
        row["can_submit"]=row["status"] in {"DRAFT","RETURNED","SUBMITTED"}
    restrictions=_rows("""SELECT dimension,target_key,effective_on,ends_on
        FROM quality_provider_restrictions WHERE amo_id=:amo AND supplier_id=:supplier
        AND status='ACTIVE' AND effective_on<=CURRENT_DATE
        AND (ends_on IS NULL OR ends_on>=CURRENT_DATE)
        ORDER BY effective_on DESC LIMIT 40""",db,**ctx)
    return {"items":rows,"restrictions":restrictions,
            "approval_notice":"Only authorized AMO Quality management approves scope, evidence and provider status."}


@router.post("/qualification/{case_id}/answers")
def partner_submit_qualification(tenant_slug:str,case_id:str,
    payload:PartnerQualificationAnswers,request:Request,db:Session=Depends(get_db)):
    # Qualification submission is preparation, not permission to start work.
    # Explicitly delegated applicants may be prospective or restricted.
    user=_ctx(db,request,tenant_slug,cap="profile.propose",write=True)
    ctx=_context(user)
    row=_row("""SELECT id,status,version,policy_snapshot_json FROM
        quality_provider_qualification_cases WHERE amo_id=:amo
        AND supplier_id=:supplier AND id=:case FOR UPDATE""",db,
        **ctx,case=case_id)
    if not row:raise HTTPException(404,"Assigned qualification request unavailable")
    if row["status"] not in {"DRAFT","RETURNED","SUBMITTED"}:
        raise HTTPException(409,"Qualification is currently under internal review")
    if int(row["version"])!=payload.case_version:
        raise HTTPException(409,"Qualification was updated; refresh its current version")
    questionnaire=row["policy_snapshot_json"].get("questionnaire",[])
    keys={str(q["key"]) for q in questionnaire}
    if set(payload.answers)-keys:
        raise HTTPException(422,"Response contains an unapproved questionnaire key")
    if any(q.get("required") and not str(payload.answers.get(q["key"],"")).strip()
           for q in questionnaire):
        raise HTTPException(422,"Complete mandatory qualification responses")
    if any(len(str(value))>4000 for value in payload.answers.values()):
        raise HTTPException(413,"Qualification response field too long")
    db.execute(text("""UPDATE quality_provider_qualification_cases
       SET answers_json=CAST(:answers AS JSON),status='SUBMITTED',
       submitted_at=NOW(),version=version+1,updated_at=NOW()
       WHERE amo_id=:amo AND supplier_id=:supplier AND id=:case"""),
       {**ctx,"case":case_id,"answers":json.dumps(payload.answers)})
    auth.event(db,amo=ctx["amo"],identity=ctx["person"],grant=user["grant_id"],
       action="PARTNER_QUALIFICATION_SUBMITTED",actor_identity=ctx["person"],
       details={"case_id":case_id,"case_version":row["version"],"note":payload.note})
    _notify(db,user,"QUALITY","Qualification questionnaire submitted",
        "The AMO Quality Department will independently evaluate your response.",
        "QUALIFICATION",case_id)
    db.commit()
    return {"status":"SUBMITTED","approval_granted":False}


@router.get("/procurement")
def procurement(tenant_slug:str,request:Request,db:Session=Depends(get_db),
                limit:int=Query(20,ge=1,le=50),offset:int=Query(0,ge=0,le=10000)):
    user=_ctx(db,request,tenant_slug,cap="task.read")
    ctx=_context(user);args={**ctx,**_page(limit,offset)}
    rfqs=_rows("""SELECT r.id,r.rfq_number,r.title,r.status,r.response_due_at
       FROM procurement_rfqs r JOIN procurement_rfq_suppliers t ON t.rfq_id=r.id
       WHERE r.amo_id=:amo AND t.supplier_id=:supplier
       AND r.status NOT IN ('DRAFT','CANCELLED')
       ORDER BY r.response_due_at NULLS LAST,r.id LIMIT :limit OFFSET :offset""",db,**args)
    pos=_rows("""SELECT po.id,po.po_number,po.status,po.promised_delivery_date,
       po.acknowledged_at,po.sent_at FROM procurement_purchase_orders po
       WHERE po.amo_id=:amo AND po.supplier_id=:supplier AND po.sent_at IS NOT NULL
       ORDER BY po.created_at DESC,po.id LIMIT :limit OFFSET :offset""",db,**args)
    return {"rfqs":{"items":rfqs,"limit":limit,"offset":offset},
            "purchase_orders":{"items":pos,"limit":limit,"offset":offset},
            "transaction_state":"READ_PROJECTION_ONLY",
            "next_phase":"Phase 6: governed quotation, PO acknowledgement and delivery transactions"}

@router.get("/contracted-work")
def contracted_work(tenant_slug:str,request:Request,db:Session=Depends(get_db)):
    user=_ctx(db,request,tenant_slug,cap="task.read")
    ctx=_context(user)
    scopes=_rows("""SELECT s.category,s.site_code,s.product_family,s.status,s.restrictions,s.expires_on
        FROM procurement_supplier_approval_scopes s
        WHERE s.amo_id=:amo AND s.supplier_id=:supplier
        AND s.status='ACTIVE'
        AND (s.expires_on IS NULL OR s.expires_on >= CURRENT_DATE)
        ORDER BY s.category,s.site_code LIMIT 30""",db,**ctx)
    assigned=_allowed(user,"contracted_work")
    issued=_rows("""SELECT id FROM external_contracted_work WHERE amo_id=:amo
        AND supplier_id=:supplier AND provider_id=:provider AND authorized_at IS NOT NULL
        ORDER BY updated_at DESC LIMIT 100""",db,**ctx)
    assigned_count=sum(str(item["id"]) in assigned for item in issued)
    return {"approved_scopes":scopes,"assigned_work_count":assigned_count,
       "execution_enabled":assigned_count>0 and "task.respond" in (user["capabilities_json"] or []),
       "message":"Technical work orders are governed by appointed Safarilink Maintenance Managers and independent Quality checks; provider certification remains under its own approval."}

@router.get("/notifications")
def notifications(tenant_slug:str,request:Request,db:Session=Depends(get_db),
                  limit:int=Query(20,ge=1,le=50),offset:int=Query(0,ge=0,le=10000),
                  unread_only:bool=False):
    user=_ctx(db,request,tenant_slug)
    return _paged(db,"""SELECT id,category,title,message,resource_kind,resource_id,
        read_at,created_at FROM external_partner_notifications
        WHERE amo_id=:amo AND tenant_provider_id=:provider AND identity_id=:person
        AND (:all OR read_at IS NULL) ORDER BY created_at DESC,id DESC""",_context(user),
        limit,offset,all=not unread_only)

@router.post("/notifications/{notification_id}/read")
def mark_read(tenant_slug:str,notification_id:str,request:Request,db:Session=Depends(get_db)):
    user=_ctx(db,request,tenant_slug,write=True)
    result=auth.run("""UPDATE external_partner_notifications SET read_at=COALESCE(read_at,:at)
        WHERE amo_id=:amo AND tenant_provider_id=:provider AND identity_id=:person AND id=:id""",
        db,**_context(user),id=notification_id,at=auth.now())
    if not result.rowcount:raise HTTPException(404,"Notification not found")
    db.commit();return {"status":"READ"}

@router.get("/activity")
def activity(tenant_slug:str,request:Request,db:Session=Depends(get_db),
             limit:int=Query(20,ge=1,le=50),offset:int=Query(0,ge=0,le=10000)):
    user=_ctx(db,request,tenant_slug)
    # Attribution history shows only this person. Internal staff IDs and secret
    # hashes are never projected into the external activity screen.
    ctx=_context(user)
    return _paged(db,"""SELECT e.id,e.event_type,e.occurred_at FROM external_security_events e
        WHERE e.amo_id=:amo AND e.identity_id=:person AND e.grant_id=:grant
        ORDER BY e.occurred_at DESC,e.id DESC""",{**ctx,"grant":user["grant_id"]},limit,offset)

@router.post("/quality/document-requests/{request_id}/submit",status_code=201)
async def submit_partner_audit_document(tenant_slug:str,request_id:str,
    request:Request,db:Session=Depends(get_db),
    file:UploadFile=File(...),
    response_comment:str|None=Form(default=None,max_length=4000)):
    """Use the SAME QMS document-request submission and storage models as
    existing guest/auditee users. No forged status, free-text file refs, or
    internal staff identity may be supplied by the external account.
    """
    user=_ctx(db,request,tenant_slug,cap="document.submit",write=True)
    assignments=_allowed(user,"assignments")
    if not assignments or "task.read" not in set(user["capabilities_json"] or []):
        raise HTTPException(403,"Audit document submissions require an issued work assignment")
    try:
        request_uuid=uuid.UUID(request_id)
    except (ValueError,TypeError):
        raise HTTPException(404,"Assigned audit document request not found")
    ctx=_context(user)
    from amodb.apps.quality import models as quality_models
    from amodb.apps.quality.audit_guest_document_models import QualityAuditDocumentSubmission
    from amodb.apps.quality.audit_guest_document_storage import (
        resolve_guest_document, store_guest_document,
    )
    # Row lock serializes return/review/closure transitions with the upload.
    row=(db.query(quality_models.QualityAuditDocumentRequest)
        .filter(quality_models.QualityAuditDocumentRequest.amo_id==ctx["amo"],
                quality_models.QualityAuditDocumentRequest.id==request_uuid)
        .with_for_update(of=quality_models.QualityAuditDocumentRequest).first())
    if not row or str(row.audit_id) not in assignments:
        raise HTTPException(404,"Assigned audit document request not found")
    if row.status in {"ACCEPTED","WAIVED"}:
        raise HTTPException(409,"This request is already closed to new submissions")
    auth.auth_limit(request,str(user["identity_id"]),"partner-audit-document-upload")
    stored=await store_guest_document(file,amo_id=ctx["amo"],
        audit_id=str(row.audit_id),request_id=str(row.id))
    try:
        submission=QualityAuditDocumentSubmission(
            amo_id=ctx["amo"],audit_id=row.audit_id,
            document_request_id=row.id,participant_id=None,source_type="UPLOAD",
            filename=stored.filename,content_type=stored.content_type,
            size_bytes=stored.size_bytes,sha256=stored.sha256,
            storage_ref=stored.storage_ref,
            response_comment=(response_comment or "").strip() or None,
            submitted_by_user_id=None,
        )
        db.add(submission);db.flush()
        row.status="UPLOADED"
        row.file_ref=f"audit-submission:{submission.id}"
        row.uploaded_at=submission.created_at
        row.uploaded_by_user_id=None
        auth.event(db,amo=ctx["amo"],identity=ctx["person"],grant=user["grant_id"],
            actor_identity=ctx["person"],action="PARTNER_QMS_DOCUMENT_SUBMITTED",
            details={"audit_id":str(row.audit_id),"request_id":str(row.id),
                     "submission_id":submission.id,"sha256":stored.sha256})
        _notify(db,user,"QUALITY","Requested audit evidence submitted",
            "QMS received your document for independent audit review.",
            "AUDIT_DOCUMENT",str(row.id))
        db.commit()
    except Exception:
        db.rollback()
        resolve_guest_document(stored.storage_ref).unlink(missing_ok=True)
        raise
    return {"id":submission.id,"filename":submission.filename,
            "request_id":str(row.id),"status":"UPLOADED",
            "sha256":stored.sha256,"review_status":"AWAITING_QMS_REVIEW"}

@router.post("/evidence",status_code=201)
def evidence_upload(tenant_slug:str,request:Request,db:Session=Depends(get_db),
    file:UploadFile=File(...),evidence_type:str=Form(...),
    related_kind:Literal["PROVIDER","CONTRACT","ASSIGNMENT"]=Form("PROVIDER"),
    related_id:str=Form("")):
    raise HTTPException(410,"Legacy unclassified uploads are retired. Use controlled document requirements and /documents/submissions.")
    user=_ctx(db,request,tenant_slug,cap="document.submit",write=True)
    ctx=_context(user)
    auth.auth_limit(request,str(user["identity_id"]),"partner-evidence-upload")
    if related_kind in {"CONTRACT","ASSIGNMENT"}:
        _require_existing_related(db,user,related_kind,related_id)
    if related_kind!="PROVIDER" and not related_id:
        raise HTTPException(422,"An authorized related record is required")
    original=Path(file.filename or "evidence").name.strip()
    if not re.fullmatch(r"[\w .()\-]{1,200}\.(pdf|png|jpg|jpeg|docx|txt)",original,re.I):
        raise HTTPException(415,"Use a PDF, DOCX, PNG, JPEG or TXT filename")
    if len(evidence_type)>48 or not evidence_type.strip():raise HTTPException(422,"Invalid evidence type")
    content_type=(file.content_type or "application/octet-stream")[:100]
    suffix=Path(original).suffix.lower()
    ext_type={".pdf":"application/pdf",".png":"image/png",".jpg":"image/jpeg",
              ".jpeg":"image/jpeg",".docx":"application/vnd.openxmlformats-officedocument.wordprocessingml.document",
              ".txt":"text/plain"}[suffix]
    maximum=20*1024*1024
    size=0;h=hashlib.sha256()
    with tempfile.NamedTemporaryFile(prefix="external-provider-",suffix=suffix) as handle:
        prefix=b""
        while True:
            part=file.file.read(1024*1024)
            if not part:break
            size+=len(part)
            if size>maximum:raise HTTPException(413,"Maximum evidence upload size is 20 MB")
            if len(prefix)<8:prefix=(prefix+part)[:8]
            h.update(part);handle.write(part)
        if size==0:raise HTTPException(422,"Empty evidence file")
        if not ((suffix==".pdf" and prefix.startswith(b"%PDF-")) or
                (suffix==".png" and prefix.startswith(b"\x89PNG\r\n\x1a\n")) or
                (suffix in (".jpg",".jpeg") and prefix.startswith(b"\xff\xd8\xff")) or
                (suffix==".docx" and prefix.startswith(b"PK")) or suffix==".txt"):
            raise HTTPException(415,"File signature does not match extension")
        handle.flush();record=auth.new_id()
        stored=storage.put_file(handle.name,
            key=f"external-provider/{ctx['amo']}/{ctx['supplier']}/{record}{suffix}",
            content_type=ext_type)
    try:
        auth.run("""INSERT INTO external_partner_evidence_submissions
           (id,amo_id,tenant_provider_id,identity_id,evidence_type,related_kind,
            related_id,filename,content_type,object_uri,sha256,size_bytes)
           VALUES(:id,:amo,:provider,:person,:type,:kind,:related,:filename,
            :mime,:uri,:sha,:size)""",db,**ctx,id=record,type=evidence_type.strip(),
            kind=related_kind,related=related_id or None,filename=original,mime=ext_type,
            uri=stored.uri,sha=h.hexdigest(),size=size)
        auth.event(db,amo=ctx["amo"],identity=ctx["person"],grant=user["grant_id"],
            action="PARTNER_EVIDENCE_SUBMITTED",actor_identity=ctx["person"],
            details={"evidence_id":record,"sha256":h.hexdigest(),"size_bytes":size})
        _notify(db,user,"EVIDENCE","Evidence received for review",
            "The upload is pending Quality review; no approval was inferred.","EVIDENCE",record)
        db.commit()
    except Exception:
        db.rollback()
        storage.delete(stored.uri)
        raise
    return {"id":record,"status":"PENDING_REVIEW","sha256":h.hexdigest(),
            "size_bytes":size,"filename":original}

@router.get("/evidence/{submission_id}/download")
def evidence_download(tenant_slug:str,submission_id:str,request:Request,db:Session=Depends(get_db)):
    user=_ctx(db,request,tenant_slug,cap="document.read")
    row=_row("""SELECT filename,content_type,object_uri,sha256,related_kind,related_id
        FROM external_partner_evidence_submissions WHERE amo_id=:amo
        AND tenant_provider_id=:provider AND id=:id""",db,**_context(user),id=submission_id)
    if not row:raise HTTPException(404,"Evidence not found")
    if row["related_kind"] in {"CONTRACT","ASSIGNMENT"}:
        _require_existing_related(db,user,row["related_kind"],row["related_id"])
    path=storage.materialize(row["object_uri"],expected_sha256=row["sha256"])
    return FileResponse(path,media_type=row["content_type"],filename=row["filename"],
        headers={"Cache-Control":"no-store","X-Content-Type-Options":"nosniff"})


class EvidenceDecision(BaseModel):
    status: Literal["ACCEPTED","REJECTED"]
    note: str = Field(min_length=8,max_length=2000)

def _quality_context(db:Session,amo_code:str,user):
    from .external_auth_router import _authorized_quality
    amo=_authorized_quality(db,amo_code,user)
    if db.get_bind().dialect.name=="postgresql":
        # The explicit marker is reachable only after authenticated tenant
        # Quality authorization, never by an unauthenticated provider request.
        db.execute(text("SELECT set_config('app.external_provider_id','__INTERNAL_QUALITY_REVIEW__',true)"))
    return amo

@quality_router.get("/partner-change-requests")
def quality_changes(amo_code:str,db:Session=Depends(get_db),
                    user=Depends(get_current_active_user),
                    limit:int=Query(25,ge=1,le=50),offset:int=Query(0,ge=0,le=10000)):
    amo=_quality_context(db,amo_code,user)
    return _paged(db,"""SELECT c.id,c.category,c.status,c.proposed_json,c.reason,
        c.source_version,c.created_at,c.review_note,c.reviewed_at,s.legal_name,
        s.supplier_code,i.email,i.display_name
        FROM external_partner_change_requests c
        JOIN external_tenant_providers p ON p.amo_id=c.amo_id AND p.id=c.tenant_provider_id
        JOIN procurement_suppliers s ON s.amo_id=p.amo_id AND s.id=p.supplier_id
        JOIN external_identities i ON i.id=c.identity_id
        WHERE c.amo_id=:amo ORDER BY c.created_at DESC,c.id DESC""",
        {"amo":amo},limit,offset)

@quality_router.post("/partner-change-requests/{change_id}/review")
def review_change(amo_code:str,change_id:str,payload:ReviewDecision,
                  db:Session=Depends(get_db),
                  user=Depends(get_current_active_user)):
    from .external_auth_router import _quality_manager
    _quality_manager(user);amo=_quality_context(db,amo_code,user)
    change=_row("""SELECT * FROM external_partner_change_requests
        WHERE amo_id=:amo AND id=:id FOR UPDATE""",db,amo=amo,id=change_id)
    if not change:raise HTTPException(404,"Partner change request not found")
    if change["status"] not in {"PENDING","UNDER_REVIEW"}:
        raise HTTPException(409,"Request is already finalized")
    auth.run("""UPDATE external_partner_change_requests
        SET status=:state,review_note=:note,reviewed_by_user_id=:actor,
        reviewed_at=:at,version=version+1
        WHERE amo_id=:amo AND id=:id""",db,amo=amo,id=change_id,
        state=payload.state,note=payload.note,actor=str(user.id),at=auth.now())
    auth.run("""INSERT INTO external_partner_notifications
       (id,amo_id,tenant_provider_id,identity_id,category,title,message,resource_kind,resource_id)
       VALUES(:id,:amo,:provider,:person,'REVIEW',:title,:message,'CHANGE',:resource)""",
       db,id=auth.new_id(),amo=amo,provider=change["tenant_provider_id"],
       person=change["identity_id"],title="Provider change review updated",
       message=f"Your proposal is {payload.state.lower().replace('_',' ')}. Approved master data does not change until its domain owner applies the decision.",
       resource=change_id)
    auth.event(db,amo=amo,identity=change["identity_id"],grant=None,
        actor_user=str(user.id),action="PARTNER_CHANGE_REVIEWED",
        details={"proposal_id":change_id,"status":payload.state,"reason":payload.note})
    db.commit()
    return {"status":payload.state,"applied_to_supplier":False}

@quality_router.get("/partner-evidence")
def quality_evidence(amo_code:str,db:Session=Depends(get_db),
                     user=Depends(get_current_active_user),
                     limit:int=Query(25,ge=1,le=50),offset:int=Query(0,ge=0,le=10000)):
    amo=_quality_context(db,amo_code,user)
    return _paged(db,"""SELECT e.id,e.evidence_type,e.filename,e.status,e.related_kind,
        e.related_id,e.created_at,e.review_note,e.sha256,e.size_bytes,
        s.legal_name,s.supplier_code,i.email
        FROM external_partner_evidence_submissions e
        JOIN external_tenant_providers p ON p.amo_id=e.amo_id AND p.id=e.tenant_provider_id
        JOIN procurement_suppliers s ON s.amo_id=p.amo_id AND s.id=p.supplier_id
        JOIN external_identities i ON i.id=e.identity_id
        WHERE e.amo_id=:amo ORDER BY e.created_at DESC,e.id DESC""",{"amo":amo},limit,offset)

@quality_router.get("/partner-evidence/{submission_id}/download")
def quality_download_evidence(amo_code:str,submission_id:str,
    db:Session=Depends(get_db),user=Depends(get_current_active_user)):
    amo=_quality_context(db,amo_code,user)
    row=_row("""SELECT object_uri,sha256,filename,content_type
      FROM external_partner_evidence_submissions WHERE amo_id=:amo AND id=:id""",
      db,amo=amo,id=submission_id)
    if not row:raise HTTPException(404,"Evidence not found")
    path=storage.materialize(row["object_uri"],expected_sha256=row["sha256"])
    return FileResponse(path,media_type=row["content_type"],filename=row["filename"],
        headers={"Cache-Control":"no-store","X-Content-Type-Options":"nosniff"})

@quality_router.post("/partner-evidence/{submission_id}/review")
def quality_review_evidence(amo_code:str,submission_id:str,payload:EvidenceDecision,
                            db:Session=Depends(get_db),
                            user=Depends(get_current_active_user)):
    from .external_auth_router import _quality_manager
    raise HTTPException(410,"Legacy evidence review is retired. Use Phase 5 controlled submission review.")
    _quality_manager(user);amo=_quality_context(db,amo_code,user)
    evidence=_row("""SELECT * FROM external_partner_evidence_submissions
        WHERE amo_id=:amo AND id=:id FOR UPDATE""",db,amo=amo,id=submission_id)
    if not evidence:raise HTTPException(404,"Evidence submission not found")
    if evidence["status"]!="PENDING_REVIEW":
        raise HTTPException(409,"Evidence has already been reviewed")
    auth.run("""UPDATE external_partner_evidence_submissions
        SET status=:state,review_note=:note,reviewed_by_user_id=:actor,reviewed_at=:at
        WHERE amo_id=:amo AND id=:id""",db,amo=amo,id=submission_id,
        state=payload.status,note=payload.note,actor=str(user.id),at=auth.now())
    auth.run("""INSERT INTO external_partner_notifications
       (id,amo_id,tenant_provider_id,identity_id,category,title,message,resource_kind,resource_id)
       VALUES(:id,:amo,:provider,:person,'EVIDENCE',:title,:message,'EVIDENCE',:resource)""",
       db,id=auth.new_id(),amo=amo,provider=evidence["tenant_provider_id"],
       person=evidence["identity_id"],title="Evidence reviewed",
       message=f"Your submission was {payload.status.lower()}. Formal documentary verification remains within the authoritative QMS review.",
       resource=submission_id)
    auth.event(db,amo=amo,identity=evidence["identity_id"],grant=None,
        actor_user=str(user.id),action="PARTNER_EVIDENCE_REVIEWED",
        details={"submission_id":submission_id,"status":payload.status})
    db.commit()
    return {"status":payload.status,"regulatory_approval":False}
