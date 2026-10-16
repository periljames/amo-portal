"""Phase 6 supplier-facing collaboration over canonical Procurement and existing DMS/QMS.

Never expose requisition approvals, budgets, internal evaluation, competitors' quotes,
payment details or unissued POs. Supplier writes cannot approve POs or release stock.
"""
from __future__ import annotations

import json
from datetime import date, datetime, timezone
from decimal import Decimal
from uuid import uuid4

from fastapi import APIRouter, Depends, HTTPException, Query, Request
from fastapi.responses import FileResponse
from pydantic import BaseModel, Field, model_validator
from sqlalchemy import text
from sqlalchemy.orm import Session

from amodb.database import get_db
from amodb.security import get_current_active_user, require_roles
from . import models, schemas, service, supplier_quality_control
from . import external_partner_router as partner
from .external_provider_documents_router import _published_revision
from amodb import storage

partner_router = APIRouter(prefix="/api/external-provider/partner/{tenant_slug}/commerce",tags=["external procurement"])
staff_router = APIRouter(prefix="/api/maintenance/{amo_code}/procurement/partner-collaboration",tags=["procurement collaboration"])

def _row(db, query, **params):
    v=db.execute(text(query),params).mappings().first()
    return dict(v) if v else None

def _rows(db, query, **params):
    return [dict(r) for r in db.execute(text(query),params).mappings()]

def _session(db,request,tenant_slug,write=False):
    # A revoked tenant, membership, grant or provider remains blocked by active_session.
    user=partner._ctx(db,request,tenant_slug,cap="procurement.respond" if write else "procurement.read",write=write)
    if write:
        partner._cap(user,"procurement.respond")
    return user,partner._context(user)

def _rfq(db,ctx,rfq_id,for_write=False):
    row=_row(db,"""SELECT r.id,r.rfq_number,r.title,r.status,r.response_due_at,
       r.terms,r.quality_clauses,r.requisition_id,i.responded_at,i.declined_at,i.invited_at
       FROM procurement_rfqs r
       JOIN procurement_rfq_suppliers i ON i.rfq_id=r.id AND i.supplier_id=:supplier
       WHERE r.amo_id=:amo AND r.id=:id AND r.issued_at IS NOT NULL
         AND r.status NOT IN ('DRAFT','CANCELLED')""",**ctx,id=rfq_id)
    if not row: raise HTTPException(404,"RFQ invitation is unavailable")
    if for_write:
        if row["status"] in ("AWARDED","CLOSED"):
            raise HTTPException(409,"This RFQ is no longer accepting responses")
        due=row["response_due_at"]
        if due and (due.replace(tzinfo=timezone.utc) if due.tzinfo is None else due)<datetime.now(timezone.utc):
            raise HTTPException(409,"RFQ response deadline has passed")
        if row["declined_at"]:raise HTTPException(409,"Declined RFQ cannot be submitted")
    return row

def _po(db,ctx,po_id,for_write=False):
    row=_row(db,"""SELECT id,po_number,status,currency,delivery_terms,quality_clauses,
       promised_delivery_date,supplier_ack_reference,acknowledged_at,sent_at
       FROM procurement_purchase_orders
       WHERE amo_id=:amo AND supplier_id=:supplier AND id=:id AND sent_at IS NOT NULL""",
       amo=ctx["amo"],supplier=ctx["supplier"],id=po_id)
    if not row:raise HTTPException(404,"Issued purchase order unavailable")
    if for_write and row["status"] not in (
        "SENT","ACKNOWLEDGED","PARTIALLY_SHIPPED","SHIPPED","PARTIALLY_RECEIVED","RECEIVED_PENDING_INSPECTION"):
        raise HTTPException(409,"Purchase order no longer accepts supplier transactions")
    return row

def _gate(db,ctx,categories):
    # Deliberately recomputed for every new obligation, never from a cached UI flag.
    supplier_quality_control.assert_supplier_usage_allowed(
        db,amo_id=ctx["amo"],supplier_id=ctx["supplier"],
        categories=categories or {"PART"},allow_controlled_override=False)

def _rfq_lines(db,ctx,rfq):
    # Requisition *lines only*: no budgets, requesters, approval chain or cost centres.
    return _rows(db,"""SELECT id,line_number,part_number,description,quantity,uom,
       technical_specification,required_certification,alternates_allowed,
       approved_manufacturers,controlled_document_id,controlled_document_revision
       FROM procurement_requisition_lines WHERE requisition_id=:id ORDER BY line_number""",
       id=rfq["requisition_id"]) if rfq["requisition_id"] else []

def _po_lines(db,po_id):
    return _rows(db,"""SELECT id,line_number,part_number,description,manufacturer,quantity,
       received_quantity,uom,required_certification,promised_date
       FROM procurement_purchase_order_lines WHERE purchase_order_id=:id ORDER BY line_number""",id=po_id)

def _event(db,ctx,entity,entity_id,action,*,identity=None,actor=None,message="",details=None,key=None):
    existing=(_row(db,"""SELECT id FROM external_procurement_events
       WHERE amo_id=:amo AND supplier_id=:supplier AND idempotency_key=:key""",
       amo=ctx["amo"],supplier=ctx["supplier"],key=key) if key else None)
    if existing: return existing["id"],False
    eid=str(uuid4())
    db.execute(text("""INSERT INTO external_procurement_events
      (id,amo_id,supplier_id,actor_identity_id,actor_user_id,entity_type,entity_id,action,
       message,details_json,idempotency_key)
       VALUES(:id,:amo,:supplier,:identity,:actor,:entity,:entity_id,:action,:message,
         CAST(:details AS JSON),:key)"""),
       {"id":eid,"amo":ctx["amo"],"supplier":ctx["supplier"],"identity":identity,
        "actor":actor,"entity":entity,"entity_id":str(entity_id),"action":action,
        "message":message,"details":json.dumps(details or {}),"key":key})
    return eid,True

def _history(db,ctx,kind,id):
    return _rows(db,"""SELECT id,entity_type,entity_id,action,message,details_json,created_at,
      actor_identity_id IS NOT NULL AS submitted_by_provider
      FROM external_procurement_events
      WHERE amo_id=:amo AND supplier_id=:supplier AND entity_type=:kind AND entity_id=:id
      ORDER BY created_at,id""",amo=ctx["amo"],supplier=ctx["supplier"],kind=kind,id=str(id))

def _notify_internal(db,ctx,kind,entity,action):
    # Existing notification register; never leak internal recipient identities externally.
    db.execute(text("""INSERT INTO external_partner_notifications
       (id,amo_id,tenant_provider_id,identity_id,category,title,message,resource_kind,resource_id)
       SELECT :id,g.amo_id,p.id,g.identity_id,'PROCUREMENT',:title,:message,:kind,:resource
       FROM external_tenant_providers p
       JOIN external_tenant_grants g ON g.amo_id=p.amo_id AND g.tenant_provider_id=p.id
       WHERE p.amo_id=:amo AND p.supplier_id=:supplier AND g.status='ACTIVE'
       LIMIT 1"""),{"id":str(uuid4()),"amo":ctx["amo"],"supplier":ctx["supplier"],
       "title":"Procurement transaction updated","message":action,
       "kind":kind,"resource":str(entity)})

class Ack(BaseModel):
    reference: str | None = Field(default=None,max_length=128)
    note: str = Field(default="",max_length=2000)
    idempotency_key: str = Field(min_length=12,max_length=80)

class QuoteLine(BaseModel):
    requisition_line_id: int
    part_number: str = Field(min_length=1,max_length=64)
    manufacturer: str | None = Field(default=None,max_length=128)
    quantity: float = Field(gt=0)
    uom: str = Field(min_length=1,max_length=16)
    unit_price: Decimal = Field(ge=0,max_digits=14,decimal_places=4)
    available_quantity: float = Field(ge=0,default=0)
    alternate_proposal: str | None = Field(default=None,max_length=2000)
    traceability_statement: str | None = Field(default=None,max_length=2000)
    promised_date: date | None = None

class QuoteSubmit(BaseModel):
    quote_reference: str = Field(min_length=2,max_length=100)
    revision: int = Field(ge=1,le=1000)
    currency: str = Field(pattern=r"^[A-Z]{3}$")
    tax_amount: Decimal = Field(ge=0,max_digits=14,decimal_places=2)
    freight_amount: Decimal = Field(ge=0,max_digits=14,decimal_places=2)
    lead_time_days: int = Field(ge=0,le=3650)
    valid_until: date
    certification_offered: str | None = Field(default=None,max_length=255)
    warranty_terms: str | None = Field(default=None,max_length=2000)
    note: str = Field(default="",max_length=2000)
    lines: list[QuoteLine] = Field(min_length=1,max_length=200)
    idempotency_key: str = Field(min_length=12,max_length=80)
    @model_validator(mode="after")
    def expiry(self):
        if self.valid_until<date.today():raise ValueError("Quote has already expired")
        return self

class Message(BaseModel):
    action: str
    message: str = Field(min_length=8,max_length=4000)
    line_id: int | None = None
    proposed_part_number: str | None = Field(default=None,max_length=64)
    promised_date: date | None = None
    idempotency_key: str = Field(min_length=12,max_length=80)

class ShipmentLine(BaseModel):
    po_line_id: int
    quantity: float = Field(gt=0)
    part_number: str = Field(min_length=1,max_length=64)
    serial_lot_batch: str | None = Field(default=None,max_length=255)
    manufacturer: str | None = Field(default=None,max_length=128)
    source: str | None = Field(default=None,max_length=255)
    traceability_reference: str | None = Field(default=None,max_length=255)
    release_certificate_reference: str | None = Field(default=None,max_length=255)
    shelf_life_expires_on: date | None = None
    material_case: str | None = Field(default=None,pattern="^(EXCHANGE|LOAN|REPAIR|WARRANTY|RETURN|RMA|REPLACEMENT)$")

class Shipment(BaseModel):
    shipment_reference: str = Field(min_length=2,max_length=128)
    dispatch_date: date
    estimated_arrival: date | None = None
    airway_bill: str | None = Field(default=None,max_length=128)
    packing_list_reference: str | None = Field(default=None,max_length=128)
    notes: str = Field(default="",max_length=2000)
    lines: list[ShipmentLine] = Field(min_length=1,max_length=200)

@partner_router.get("/rfqs")
def rfqs(tenant_slug:str,request:Request,db:Session=Depends(get_db),
         limit:int=Query(25,ge=1,le=50),offset:int=Query(0,ge=0,le=10000)):
    user,ctx=_session(db,request,tenant_slug)
    return {"items":_rows(db,"""SELECT r.id,r.rfq_number,r.title,r.status,r.response_due_at,
        i.invited_at,i.responded_at
      FROM procurement_rfqs r JOIN procurement_rfq_suppliers i
      ON i.rfq_id=r.id AND i.supplier_id=:supplier WHERE r.amo_id=:amo
      AND r.issued_at IS NOT NULL AND r.status NOT IN ('DRAFT','CANCELLED')
      ORDER BY r.issued_at DESC,r.id DESC LIMIT :limit OFFSET :offset""",
      amo=ctx["amo"],supplier=ctx["supplier"],limit=limit,offset=offset),
      "limit":limit,"offset":offset}

@partner_router.get("/rfqs/{rfq_id}")
def rfq_detail(tenant_slug:str,rfq_id:int,request:Request,db:Session=Depends(get_db)):
    user,ctx=_session(db,request,tenant_slug)
    rfq=_rfq(db,ctx,rfq_id)
    quotes=_rows(db,"""SELECT e.id,e.external_reference,e.revision_no,e.status,e.submitted_at,
        q.id AS quote_id,q.currency,q.total_amount,q.valid_until
      FROM external_procurement_quotes e JOIN procurement_quotes q ON q.id=e.canonical_quote_id
      WHERE e.amo_id=:amo AND e.supplier_id=:supplier AND e.rfq_id=:rfq
      ORDER BY e.submitted_at DESC""",amo=ctx["amo"],supplier=ctx["supplier"],rfq=rfq_id)
    return {**rfq,"lines":_rfq_lines(db,ctx,rfq),"my_quotes":quotes,"history":_history(db,ctx,"RFQ",rfq_id)}

@partner_router.get("/rfqs/{rfq_id}/specifications/{line_id}")
def specification(tenant_slug:str,rfq_id:int,line_id:int,request:Request,db:Session=Depends(get_db)):
    user,ctx=_session(db,request,tenant_slug)
    rfq=_rfq(db,ctx,rfq_id)
    line=next((l for l in _rfq_lines(db,ctx,rfq) if l["id"]==line_id),None)
    if not line or not line["controlled_document_id"] or not line["controlled_document_revision"]:
        raise HTTPException(404,"No released controlled specification for this invited line")
    partner._require_object(user,"documents",str(line["controlled_document_id"]))
    revision=_published_revision(db,ctx["amo"],line["controlled_document_id"],line["controlled_document_revision"])
    if not revision["source_storage_path"]:raise HTTPException(409,"Controlled source unavailable")
    f=storage.materialize(revision["source_storage_path"],expected_sha256=revision["source_sha256"])
    return FileResponse(f,filename=revision["source_filename"] or "specification",
        media_type=revision["source_mime_type"] or "application/octet-stream",
        headers={"Cache-Control":"private, no-store","X-Content-Type-Options":"nosniff"})

@partner_router.post("/rfqs/{rfq_id}/acknowledge")
def acknowledge_rfq(tenant_slug:str,rfq_id:int,payload:Ack,request:Request,db:Session=Depends(get_db)):
    user,ctx=_session(db,request,tenant_slug,True)
    rfq=_rfq(db,ctx,rfq_id,True)
    _gate(db,ctx,{"PART" if l["part_number"] else "SERVICE" for l in _rfq_lines(db,ctx,rfq)})
    eid,_=_event(db,ctx,"RFQ",rfq_id,"ACKNOWLEDGED",identity=ctx["person"],message=payload.note,
       details={"reference":payload.reference},key=payload.idempotency_key)
    db.commit()
    return {"id":eid,"acknowledged":True}

@partner_router.post("/rfqs/{rfq_id}/quotes",status_code=201)
def submit_quote(tenant_slug:str,rfq_id:int,payload:QuoteSubmit,request:Request,db:Session=Depends(get_db)):
    user,ctx=_session(db,request,tenant_slug,True)
    rfq=_rfq(db,ctx,rfq_id,True)
    existing=_row(db,"""SELECT id,entity_id FROM external_procurement_events
       WHERE amo_id=:amo AND supplier_id=:supplier AND idempotency_key=:key""",
       amo=ctx["amo"],supplier=ctx["supplier"],key=payload.idempotency_key)
    if existing:return {"id":existing["entity_id"],"retry":True}
    source=_rfq_lines(db,ctx,rfq)
    allowed={l["id"]:l for l in source}
    if not allowed or len({l.requisition_line_id for l in payload.lines})!=len(payload.lines):
        raise HTTPException(422,"Select each invited requisition line at most once")
    types=set()
    canonical=[]
    details=[]
    for line in payload.lines:
        original=allowed.get(line.requisition_line_id)
        if not original:raise HTTPException(422,"Quote line is not part of this invitation")
        if line.uom.strip().upper()!=str(original["uom"]).upper():
            raise HTTPException(422,"Quoted unit must match the invited line; request clarification")
        if line.part_number!=original["part_number"] and not original["alternates_allowed"]:
            raise HTTPException(409,"An alternate requires prior technical authorization")
        if line.quantity>float(original["quantity"])*10:
            raise HTTPException(422,"Unreasonable quantity: request clarification")
        if line.available_quantity>line.quantity:
            raise HTTPException(422,"Available quantity cannot exceed quoted quantity")
        alternate=bool(line.alternate_proposal or line.part_number!=original["part_number"])
        types.add("PART" if original["part_number"] else "SERVICE")
        canonical.append(schemas.QuoteLineCreate(requisition_line_id=line.requisition_line_id,
           supplier_part_number=line.part_number,manufacturer=line.manufacturer,
           quantity=line.quantity,uom=line.uom,unit_price=line.unit_price,
           promised_date=line.promised_date,traceability_statement=line.traceability_statement,
           is_technically_compliant=not alternate,deviation=line.alternate_proposal))
        details.append(line.model_dump(mode="json"))
    _gate(db,ctx,types)
    prior=_row(db,"""SELECT e.id,e.revision_no,e.status,e.canonical_quote_id,q.status AS canonical_state
       FROM external_procurement_quotes e JOIN procurement_quotes q ON q.id=e.canonical_quote_id
       WHERE e.amo_id=:amo AND e.supplier_id=:supplier AND e.rfq_id=:rfq
         AND e.external_reference=:ref ORDER BY e.revision_no DESC LIMIT 1 FOR UPDATE""",
       amo=ctx["amo"],supplier=ctx["supplier"],rfq=rfq_id,ref=payload.quote_reference)
    if payload.revision!=(int(prior["revision_no"])+1 if prior else 1):
        raise HTTPException(409,"Quotation revision must be sequential and based on the current submission")
    if prior and (prior["status"]!="SUBMITTED" or prior["canonical_state"]!="RECEIVED"):
        raise HTTPException(409,"The evaluated or withdrawn quotation is locked; contact Procurement")
    # A new canonical Procurement quotation is created for each immutable revision.
    # Evaluation and award remain entirely inside the existing staff workflow.
    ref=f"V{ctx['supplier']}-RFQ{rfq_id}-{payload.quote_reference[:70]}-R{payload.revision}"
    created=service.create_quote(db,amo_id=ctx["amo"],actor_user_id=None,
       payload=schemas.QuoteCreate(rfq_id=rfq_id,supplier_id=ctx["supplier"],
         quote_reference=ref,currency=payload.currency,
         tax_amount=payload.tax_amount,freight_amount=payload.freight_amount,
         lead_time_days=payload.lead_time_days,valid_until=payload.valid_until,
         certification_offered=payload.certification_offered,
         warranty_terms=payload.warranty_terms,technical_deviations=payload.note,
         lines=canonical))
    record=str(uuid4())
    db.execute(text("""INSERT INTO external_procurement_quotes
       (id,amo_id,supplier_id,rfq_id,canonical_quote_id,external_reference,revision_no,
        previous_id,status,details_json,submitted_by_identity_id)
       VALUES(:id,:amo,:supplier,:rfq,:quote,:reference,:revision,:prior,'SUBMITTED',
         CAST(:details AS JSON),:identity)"""),
       {"id":record,"amo":ctx["amo"],"supplier":ctx["supplier"],"rfq":rfq_id,
       "quote":created.id,"reference":payload.quote_reference,"revision":payload.revision,
       "prior":prior["id"] if prior else None,
       "details":json.dumps({"lines":details,"message":payload.note}),"identity":ctx["person"]})
    if prior:
        db.execute(text("""UPDATE external_procurement_quotes SET status='REPLACED'
          WHERE amo_id=:amo AND id=:id"""),{"amo":ctx["amo"],"id":prior["id"]})
    _event(db,ctx,"QUOTE",record,"SUBMITTED",identity=ctx["person"],
       details={"rfq_id":rfq_id,"canonical_quote_id":created.id,"revision":payload.revision},
       key=payload.idempotency_key)
    _event(db,ctx,"RFQ",rfq_id,"QUOTE_RECEIVED",identity=ctx["person"],
       details={"quote_id":created.id,"revision":payload.revision})
    db.commit()
    return {"id":record,"canonical_quote_id":created.id,"status":"SUBMITTED","revision":payload.revision}

@partner_router.post("/quotes/{quote_id}/withdraw")
def withdraw_quote(tenant_slug:str,quote_id:str,payload:Ack,request:Request,db:Session=Depends(get_db)):
    user,ctx=_session(db,request,tenant_slug,True)
    row=_row(db,"""SELECT e.id,e.status,q.status AS quote_state,e.rfq_id
       FROM external_procurement_quotes e JOIN procurement_quotes q ON q.id=e.canonical_quote_id
       WHERE e.amo_id=:amo AND e.supplier_id=:supplier AND e.id=:id FOR UPDATE""",
       amo=ctx["amo"],supplier=ctx["supplier"],id=quote_id)
    if not row:raise HTTPException(404,"Quotation unavailable")
    if row["status"]!="SUBMITTED" or row["quote_state"]!="RECEIVED":
        raise HTTPException(409,"Only an unevaluated current quotation may be withdrawn")
    if len(payload.note.strip())<8:raise HTTPException(422,"Withdrawal requires a reason")
    db.execute(text("UPDATE external_procurement_quotes SET status='WITHDRAWN' WHERE amo_id=:amo AND id=:id"),
       {"amo":ctx["amo"],"id":quote_id})
    _event(db,ctx,"QUOTE",quote_id,"WITHDRAWN",identity=ctx["person"],message=payload.note,
       key=payload.idempotency_key)
    db.commit()
    return {"id":quote_id,"status":"WITHDRAWN"}

@partner_router.get("/purchase-orders")
def purchase_orders(tenant_slug:str,request:Request,db:Session=Depends(get_db),
       limit:int=Query(25,ge=1,le=50),offset:int=Query(0,ge=0,le=10000)):
    user,ctx=_session(db,request,tenant_slug)
    return {"items":_rows(db,"""SELECT id,po_number,status,currency,promised_delivery_date,
       acknowledged_at,sent_at FROM procurement_purchase_orders
       WHERE amo_id=:amo AND supplier_id=:supplier AND sent_at IS NOT NULL
       ORDER BY sent_at DESC,id DESC LIMIT :limit OFFSET :offset""",
       amo=ctx["amo"],supplier=ctx["supplier"],limit=limit,offset=offset),
       "limit":limit,"offset":offset}

@partner_router.get("/purchase-orders/{po_id}")
def purchase_order(tenant_slug:str,po_id:int,request:Request,db:Session=Depends(get_db)):
    user,ctx=_session(db,request,tenant_slug)
    po=_po(db,ctx,po_id)
    shipments=_rows(db,"""SELECT id,shipment_reference,status,details_json,lines_json,created_at
       FROM external_procurement_shipments
       WHERE amo_id=:amo AND supplier_id=:supplier AND po_id=:po ORDER BY created_at DESC""",
       amo=ctx["amo"],supplier=ctx["supplier"],po=po_id)
    receipts=_rows(db,"""SELECT id,receipt_number,status,received_at,delivery_note_number
       FROM procurement_receipts WHERE amo_id=:amo AND purchase_order_id=:po
       ORDER BY received_at DESC""",amo=ctx["amo"],po=po_id)
    return {**po,"lines":_po_lines(db,po_id),"shipments":shipments,"receipts":receipts,
        "history":_history(db,ctx,"PO",po_id)}

@partner_router.get("/purchase-orders/{po_id}/documents")
def purchase_order_documents(tenant_slug:str,po_id:int,request:Request,db:Session=Depends(get_db)):
    user,ctx=_session(db,request,tenant_slug)
    _po(db,ctx,po_id)
    # Only explicit partner-releasable DMS revision IDs; no internal attachments.
    return {"items":_rows(db,"""SELECT d.id,d.title,d.document_type,d.document_number,d.revision,
       d.dms_document_id,d.dms_revision_id
       FROM procurement_documents d WHERE d.amo_id=:amo
         AND d.entity_type='PURCHASE_ORDER' AND d.entity_id=:id
         AND d.source='DMS_CONTROLLED' AND d.status='ACTIVE'
         AND d.dms_document_id IS NOT NULL AND d.dms_revision_id IS NOT NULL
       ORDER BY d.uploaded_at""",amo=ctx["amo"],id=str(po_id))}

@partner_router.get("/purchase-orders/{po_id}/documents/{document_id}/download")
def po_document(tenant_slug:str,po_id:int,document_id:int,request:Request,db:Session=Depends(get_db)):
    user,ctx=_session(db,request,tenant_slug)
    _po(db,ctx,po_id)
    d=_row(db,"""SELECT d.dms_document_id,d.dms_revision_id FROM procurement_documents d
      WHERE d.amo_id=:amo AND d.id=:id AND d.entity_type='PURCHASE_ORDER'
        AND d.entity_id=:po AND d.status='ACTIVE' AND d.source='DMS_CONTROLLED'""",
        amo=ctx["amo"],id=document_id,po=str(po_id))
    if not d or not d["dms_document_id"] or not d["dms_revision_id"]:
        raise HTTPException(404,"No provider-releasable PO attachment")
    partner._require_object(user,"documents",str(d["dms_document_id"]))
    rev=_published_revision(db,ctx["amo"],d["dms_document_id"],d["dms_revision_id"])
    f=storage.materialize(rev["source_storage_path"],expected_sha256=rev["source_sha256"])
    return FileResponse(f,filename=rev["source_filename"] or "purchase-order",
        media_type=rev["source_mime_type"] or "application/octet-stream",
        headers={"Cache-Control":"private, no-store","X-Content-Type-Options":"nosniff"})

@partner_router.post("/purchase-orders/{po_id}/acknowledge")
def acknowledge_po(tenant_slug:str,po_id:int,payload:Ack,request:Request,db:Session=Depends(get_db)):
    user,ctx=_session(db,request,tenant_slug,True)
    po=_po(db,ctx,po_id,True)
    _gate(db,ctx,{"PART" if l["part_number"] else "SERVICE" for l in _po_lines(db,po_id)})
    if po["status"] not in ("SENT","ACKNOWLEDGED"):
        raise HTTPException(409,"Purchase order cannot be acknowledged in this state")
    if not payload.reference or len(payload.reference.strip())<2:
        raise HTTPException(422,"Supplier acknowledgement reference required")
    previous=_row(db,"""SELECT id FROM external_procurement_events WHERE amo_id=:amo
      AND supplier_id=:supplier AND idempotency_key=:key""",
      amo=ctx["amo"],supplier=ctx["supplier"],key=payload.idempotency_key)
    if previous:return {"id":previous["id"],"acknowledged":True,"retry":True}
    if po["status"]=="SENT":
        service.acknowledge_purchase_order(db,amo_id=ctx["amo"],po_id=po_id,
          payload=schemas.PurchaseOrderAcknowledge(supplier_ack_reference=payload.reference),actor_user_id=None)
    elif po["supplier_ack_reference"]!=payload.reference:
        raise HTTPException(409,"PO already acknowledged; request clarification for amendments")
    eid,_=_event(db,ctx,"PO",po_id,"ACKNOWLEDGED",identity=ctx["person"],
       message=payload.note,details={"reference":payload.reference},key=payload.idempotency_key)
    db.commit()
    return {"id":eid,"acknowledged":True}

@partner_router.post("/rfqs/{rfq_id}/messages")
def rfq_message(tenant_slug:str,rfq_id:int,payload:Message,request:Request,db:Session=Depends(get_db)):
    if payload.action not in ("CLARIFICATION","ALTERNATE_REQUEST","AVAILABILITY"):
        raise HTTPException(422,"Unsupported RFQ collaboration action")
    user,ctx=_session(db,request,tenant_slug,True)
    rfq=_rfq(db,ctx,rfq_id,True)
    if payload.line_id and payload.line_id not in {l["id"] for l in _rfq_lines(db,ctx,rfq)}:
        raise HTTPException(422,"Line is not part of the RFQ")
    _gate(db,ctx,{"PART" if l["part_number"] else "SERVICE" for l in _rfq_lines(db,ctx,rfq)})
    eid,_=_event(db,ctx,"RFQ",rfq_id,payload.action,identity=ctx["person"],message=payload.message,
       details={"line_id":payload.line_id,"proposed_part_number":payload.proposed_part_number},
       key=payload.idempotency_key)
    db.commit()
    return {"id":eid,"pending_internal_decision":True}

@partner_router.post("/purchase-orders/{po_id}/messages")
def po_message(tenant_slug:str,po_id:int,payload:Message,request:Request,db:Session=Depends(get_db)):
    if payload.action not in ("CLARIFICATION","DELIVERY_CHANGE","PARTIAL_AVAILABILITY",
       "WARRANTY","RETURN","RMA","REPAIR","EXCHANGE","LOAN","REJECTED_MATERIAL","CREDIT","REPLACEMENT"):
        raise HTTPException(422,"Unsupported PO collaboration action")
    user,ctx=_session(db,request,tenant_slug,True)
    _po(db,ctx,po_id,True)
    lines=_po_lines(db,po_id)
    if payload.line_id and payload.line_id not in {l["id"] for l in lines}:
        raise HTTPException(422,"PO line not assigned to this supplier")
    _gate(db,ctx,{"PART" if l["part_number"] else "SERVICE" for l in lines})
    if payload.action=="DELIVERY_CHANGE" and not payload.promised_date:
        raise HTTPException(422,"Proposed delivery date required")
    eid,_=_event(db,ctx,"PO",po_id,payload.action,identity=ctx["person"],
      message=payload.message,details={"line_id":payload.line_id,"proposed_part_number":payload.proposed_part_number,
      "promised_date":payload.promised_date.isoformat() if payload.promised_date else None},
      key=payload.idempotency_key)
    db.commit()
    return {"id":eid,"pending_internal_decision":True}

@partner_router.post("/purchase-orders/{po_id}/shipments",status_code=201)
def advise_shipment(tenant_slug:str,po_id:int,payload:Shipment,request:Request,db:Session=Depends(get_db)):
    user,ctx=_session(db,request,tenant_slug,True)
    _po(db,ctx,po_id,True)
    lines={l["id"]:l for l in _po_lines(db,po_id)}
    types={"PART" if l["part_number"] else "SERVICE" for l in lines.values()}
    _gate(db,ctx,types)
    if len({l.po_line_id for l in payload.lines})!=len(payload.lines):
        raise HTTPException(422,"Each PO line may occur once in one shipment notice")
    for item in payload.lines:
        source=lines.get(item.po_line_id)
        if not source:raise HTTPException(422,"Shipment line not on issued PO")
        if item.part_number!=source["part_number"]:
            raise HTTPException(409,"Unapproved alternate part: request technical approval before shipment")
        if item.quantity>float(source["quantity"])-float(source["received_quantity"] or 0):
            raise HTTPException(409,"Shipment exceeds outstanding PO quantity")
        if item.shelf_life_expires_on and item.shelf_life_expires_on<date.today():
            raise HTTPException(409,"Expired shelf-life item cannot be advised as current")
    if payload.estimated_arrival and payload.estimated_arrival<payload.dispatch_date:
        raise HTTPException(422,"Arrival cannot precede dispatch")
    prior=_row(db,"""SELECT id FROM external_procurement_shipments
      WHERE amo_id=:amo AND supplier_id=:supplier AND po_id=:po AND shipment_reference=:ref""",
      amo=ctx["amo"],supplier=ctx["supplier"],po=po_id,ref=payload.shipment_reference)
    if prior:return {"id":prior["id"],"retry":True}
    sid=str(uuid4())
    db.execute(text("""INSERT INTO external_procurement_shipments
      (id,amo_id,supplier_id,po_id,shipment_reference,lines_json,details_json,created_by_identity_id)
      VALUES(:id,:amo,:supplier,:po,:ref,CAST(:lines AS JSON),CAST(:details AS JSON),:actor)"""),
       {"id":sid,"amo":ctx["amo"],"supplier":ctx["supplier"],"po":po_id,"ref":payload.shipment_reference,
        "lines":json.dumps([l.model_dump(mode="json") for l in payload.lines]),
        "details":json.dumps(payload.model_dump(mode="json",exclude={"lines"})),"actor":ctx["person"]})
    _event(db,ctx,"PO",po_id,"SHIPMENT_ADVISED",identity=ctx["person"],
       details={"shipment_id":sid,"reference":payload.shipment_reference})
    _event(db,ctx,"SHIPMENT",sid,"ADVISED",identity=ctx["person"],
       details={"po_id":po_id,"reference":payload.shipment_reference})
    db.commit()
    return {"id":sid,"status":"ADVISED","receiving_status":"AWAITING_INTERNAL_RECEIVING_AND_INSPECTION"}

@partner_router.get("/purchase-orders/{po_id}/invoice-status")
def invoice_status(tenant_slug:str,po_id:int,request:Request,db:Session=Depends(get_db)):
    user,ctx=_session(db,request,tenant_slug)
    _po(db,ctx,po_id)
    # Invoice matching state only; never expose banking, remittance or approval actors.
    return {"items":_rows(db,"""SELECT id,invoice_number,status,matched_at
        FROM procurement_invoice_matches WHERE amo_id=:amo AND purchase_order_id=:po
        ORDER BY id DESC""",amo=ctx["amo"],po=po_id)}

@partner_router.get("/{kind}/{entity_id}/history")
def history(tenant_slug:str,kind:str,entity_id:str,request:Request,db:Session=Depends(get_db)):
    user,ctx=_session(db,request,tenant_slug)
    if kind=="RFQ":_rfq(db,ctx,int(entity_id))
    elif kind=="PO":_po(db,ctx,int(entity_id))
    elif kind=="SHIPMENT":
        if not _row(db,"""SELECT id FROM external_procurement_shipments WHERE amo_id=:amo
           AND supplier_id=:supplier AND id=:id""",amo=ctx["amo"],supplier=ctx["supplier"],id=entity_id):
            raise HTTPException(404,"Shipment not assigned")
    elif kind=="QUOTE":
        if not _row(db,"""SELECT id FROM external_procurement_quotes WHERE amo_id=:amo
           AND supplier_id=:supplier AND id=:id""",amo=ctx["amo"],supplier=ctx["supplier"],id=entity_id):
            raise HTTPException(404,"Quote not assigned")
    else:raise HTTPException(422,"Unsupported transaction")
    return {"items":_history(db,ctx,kind,entity_id)}

def _staff(db,amo_code,user):
    from .router import PROCUREMENT_ROLES
    if user.role not in PROCUREMENT_ROLES:
        raise HTTPException(403,"Appointed Procurement staff required")
    amo=service.resolve_tenant_amo_id(db,amo_code=amo_code,current_user=user)
    if db.get_bind().dialect.name=="postgresql":
        db.execute(text("SELECT set_config('app.tenant_id',:amo,true)"),{"amo":amo})
        db.execute(text("SELECT set_config('app.external_provider_id','__INTERNAL_QUALITY_REVIEW__',true)"))
    return amo

@staff_router.get("/inbox")
def staff_inbox(amo_code:str,db:Session=Depends(get_db),
                user=Depends(get_current_active_user),limit:int=Query(50,ge=1,le=100)):
    amo=_staff(db,amo_code,user)
    # Procurement sees all vendor responses in its tenant, not vendor competitors.
    items=_rows(db,"""SELECT e.id,e.supplier_id,s.legal_name,e.entity_type,e.entity_id,
       e.action,e.message,e.details_json,e.created_at
       FROM external_procurement_events e JOIN procurement_suppliers s ON s.id=e.supplier_id
       AND s.amo_id=e.amo_id WHERE e.amo_id=:amo
       ORDER BY e.created_at DESC LIMIT :limit""",amo=amo,limit=limit)
    quotes=_rows(db,"""SELECT q.id,q.supplier_id,q.rfq_id,q.canonical_quote_id,q.external_reference,
       q.revision_no,q.status,q.submitted_at FROM external_procurement_quotes q
       WHERE q.amo_id=:amo ORDER BY q.submitted_at DESC LIMIT :limit""",amo=amo,limit=limit)
    shipments=_rows(db,"""SELECT id,po_id,supplier_id,shipment_reference,status,created_at
       FROM external_procurement_shipments WHERE amo_id=:amo
       ORDER BY created_at DESC LIMIT :limit""",amo=amo,limit=limit)
    return {"events":items,"quotes":quotes,"shipments":shipments,
        "boundary":"No provider action authorizes award, PO, Stores receiving, Quality release or Finance payment"}

class StaffDecision(BaseModel):
    action: str = Field(pattern="^(REPLY|ACCEPT_DATE_PROPOSAL|REJECT_PROPOSAL|ACKNOWLEDGE|TECHNICAL_ALTERNATE_REVIEW)$")
    message: str = Field(min_length=8,max_length=3000)
    proposal_event_id: str | None = Field(default=None,max_length=36)
    idempotency_key: str = Field(min_length=12,max_length=80)

@staff_router.post("/{kind}/{entity_id}/decisions")
def staff_decision(amo_code:str,kind:str,entity_id:str,payload:StaffDecision,
                   db:Session=Depends(get_db),user=Depends(get_current_active_user)):
    amo=_staff(db,amo_code,user)
    if kind not in {"RFQ","PO","SHIPMENT"}:raise HTTPException(422,"Unsupported staff action")
    proposal=_row(db,"""SELECT * FROM external_procurement_events
       WHERE amo_id=:amo AND id=:id AND entity_type=:kind AND entity_id=:entity""",
       amo=amo,id=payload.proposal_event_id,kind=kind,entity=entity_id) if payload.proposal_event_id else None
    if payload.proposal_event_id and not proposal:raise HTTPException(404,"Related provider proposal unavailable")
    if payload.action=="ACCEPT_DATE_PROPOSAL":
        if kind!="PO" or not proposal or proposal["action"]!="DELIVERY_CHANGE":
            raise HTTPException(422,"Select the supplier's original PO delivery-date proposal")
        requested=proposal["details_json"].get("promised_date")
        if not requested:raise HTTPException(422,"No proposed delivery date")
        db.execute(text("""UPDATE procurement_purchase_orders SET promised_delivery_date=:delivery,
            updated_at=NOW() WHERE amo_id=:amo AND supplier_id=:supplier AND id=:id
            AND status NOT IN ('CANCELLED','CLOSED')"""),
            {"delivery":date.fromisoformat(requested),"amo":amo,
             "supplier":proposal["supplier_id"],"id":int(entity_id)})
    if not proposal and payload.action!="REPLY":
        raise HTTPException(422,"Select an attributable provider proposal")
    ctx={"amo":amo,"supplier":proposal["supplier_id"] if proposal else None}
    if ctx["supplier"] is None:
        raise HTTPException(422,"A supplier-specific thread is required")
    eid,_=_event(db,ctx,kind,entity_id,payload.action,actor=str(user.id),
       message=payload.message,details={"proposal_event_id":payload.proposal_event_id},
       key=payload.idempotency_key)
    # Notification to the actual proposing member; no cross-provider broadcast.
    if proposal and proposal["actor_identity_id"]:
        p=_row(db,"""SELECT id FROM external_tenant_providers WHERE amo_id=:amo
             AND supplier_id=:supplier""",amo=amo,supplier=ctx["supplier"])
        if p:
            db.execute(text("""INSERT INTO external_partner_notifications
                (id,amo_id,tenant_provider_id,identity_id,category,title,message,resource_kind,resource_id)
                VALUES(:id,:amo,:provider,:identity,'PROCUREMENT',:title,:message,:kind,:resource)"""),
                {"id":str(uuid4()),"amo":amo,"provider":p["id"],
                 "identity":proposal["actor_identity_id"],"title":"Procurement replied",
                 "message":payload.message,"kind":kind,"resource":entity_id})
    db.commit()
    return {"id":eid,"staff_decision_recorded":True,
        "internal_approval_preserved":True}
