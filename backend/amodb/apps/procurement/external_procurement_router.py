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

class Ack(BaseModel):
    reference: str | None = Field(default=None,max_length=128)
    note: str = Field(default="",max_length=2000)
    idempotency_key: str = Field(min_length=12,max_length=80)

class QuoteLine(BaseModel):
    requisition_line_id: int
    part_number: str | None = Field(default=None,max_length=64)
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
    part_number: str | None = Field(default=None,max_length=64)
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
        if (line.part_number or None)!=(original["part_number"] or None) and not original["alternates_allowed"]:
            raise HTTPException(409,"An alternate requires prior technical authorization")
        if line.quantity>float(original["quantity"])*10:
            raise HTTPException(422,"Unreasonable quantity: request clarification")
        if line.available_quantity>line.quantity:
            raise HTTPException(422,"Available quantity cannot exceed quoted quantity")
        alternate=bool(line.alternate_proposal or (line.part_number or None)!=(original["part_number"] or None))
        types.add("PART" if original["part_number"] else "SERVICE")
        canonical.append(schemas.QuoteLineCreate(requisition_line_id=line.requisition_line_id,
           supplier_part_number=line.part_number or None,manufacturer=line.manufacturer,
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

@partner_router.get("/shipments")
def shipment_scopes(tenant_slug:str,request:Request,db:Session=Depends(get_db)):
    user,ctx=_session(db,request,tenant_slug)
    # The member must also have received explicit scope for the underlying PO.
    allowed=partner._allowed(user,"purchase_orders")
    if not allowed:return {"items":[]}
    candidates=_rows(db,"""SELECT sh.id,sh.po_id,sh.shipment_reference,sh.status
       FROM external_procurement_shipments sh JOIN procurement_purchase_orders p
       ON p.id=sh.po_id AND p.amo_id=sh.amo_id AND p.supplier_id=sh.supplier_id
       WHERE sh.amo_id=:amo AND sh.supplier_id=:supplier AND p.sent_at IS NOT NULL
       ORDER BY sh.created_at DESC LIMIT 250""",amo=ctx["amo"],supplier=ctx["supplier"])
    return {"items":[item for item in candidates if str(item["po_id"]) in allowed][:100]}


@partner_router.get("/purchase-orders/{po_id}")
def purchase_order(tenant_slug:str,po_id:int,request:Request,db:Session=Depends(get_db)):
    user,ctx=_session(db,request,tenant_slug)
    po=_po(db,ctx,po_id)
    shipments=_rows(db,"""SELECT sh.id,sh.shipment_reference,sh.status,sh.details_json,sh.lines_json,sh.created_at,
         (SELECT r.status FROM procurement_receipts r WHERE r.amo_id=sh.amo_id
          AND r.purchase_order_id=sh.po_id AND r.supplier_shipment_reference=sh.shipment_reference
          ORDER BY r.received_at DESC LIMIT 1) AS receiving_status
       FROM external_procurement_shipments sh
       WHERE sh.amo_id=:amo AND sh.supplier_id=:supplier AND sh.po_id=:po ORDER BY sh.created_at DESC""",
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
    # Lock the canonical PO before comparing unreceived quantity against
    # already-advised shipments; otherwise simultaneous ASNs can over-book it.
    db.execute(text("""SELECT id FROM procurement_purchase_orders
        WHERE amo_id=:amo AND supplier_id=:supplier AND id=:po FOR UPDATE"""),
        {"amo":ctx["amo"],"supplier":ctx["supplier"],"po":po_id})
    previous_advices=_rows(db,"""SELECT lines_json FROM external_procurement_shipments
        WHERE amo_id=:amo AND supplier_id=:supplier AND po_id=:po AND status='ADVISED'""",
        amo=ctx["amo"],supplier=ctx["supplier"],po=po_id)
    advised={}
    for earlier in previous_advices:
        for part in earlier["lines_json"] or []:
            identity=int(part["po_line_id"])
            advised[identity]=advised.get(identity,0.0)+float(part["quantity"])
    if len({l.po_line_id for l in payload.lines})!=len(payload.lines):
        raise HTTPException(422,"Each PO line may occur once in one shipment notice")
    for item in payload.lines:
        source=lines.get(item.po_line_id)
        if not source:raise HTTPException(422,"Shipment line not on issued PO")
        if (item.part_number or None)!=(source["part_number"] or None):
            raise HTTPException(409,"Unapproved alternate part: request technical approval before shipment")
        if item.quantity+advised.get(item.po_line_id,0)>float(source["quantity"])-float(source["received_quantity"] or 0)+1e-8:
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

@partner_router.post("/shipments/{shipment_id}/cancel")
def cancel_undelivered_shipment(tenant_slug:str,shipment_id:str,payload:Ack,
                               request:Request,db:Session=Depends(get_db)):
    user,ctx=_session(db,request,tenant_slug,True)
    sh=_row(db,"""SELECT id,po_id,shipment_reference,status
         FROM external_procurement_shipments
         WHERE amo_id=:amo AND supplier_id=:supplier AND id=:id FOR UPDATE""",
         amo=ctx["amo"],supplier=ctx["supplier"],id=shipment_id)
    if not sh:raise HTTPException(404,"Shipment unavailable")
    _po(db,ctx,sh["po_id"],True)
    _gate(db,ctx,{"PART" if l["part_number"] else "SERVICE" for l in _po_lines(db,sh["po_id"])})
    if sh["status"]!="ADVISED":raise HTTPException(409,"Shipment notice already cancelled")
    if len(payload.note.strip())<8:raise HTTPException(422,"Cancellation reason required")
    physical=_row(db,"""SELECT id FROM procurement_receipts
        WHERE amo_id=:amo AND purchase_order_id=:po
          AND supplier_shipment_reference=:ref LIMIT 1""",
          amo=ctx["amo"],po=sh["po_id"],ref=sh["shipment_reference"])
    if physical:raise HTTPException(409,"Stores already received this shipment; use the internal RMA/return workflow")
    db.execute(text("""UPDATE external_procurement_shipments SET status='CANCELLED'
         WHERE amo_id=:amo AND supplier_id=:supplier AND id=:id""",
         amo=ctx["amo"],supplier=ctx["supplier"],id=shipment_id)
    eid,_=_event(db,ctx,"SHIPMENT",shipment_id,"CANCELLED",identity=ctx["person"],
       message=payload.note,details={"po_id":sh["po_id"]},key=payload.idempotency_key)
    _event(db,ctx,"PO",sh["po_id"],"SHIPMENT_CANCELLED",identity=ctx["person"],
       details={"shipment_id":shipment_id,"reference":sh["shipment_reference"]})
    db.commit()
    return {"id":shipment_id,"status":"CANCELLED","event_id":eid}


@partner_router.get("/purchase-orders/{po_id}/invoice-status")
def invoice_status(tenant_slug:str,po_id:int,request:Request,db:Session=Depends(get_db)):
    user,ctx=_session(db,request,tenant_slug)
    _po(db,ctx,po_id)
    # Invoice matching state only; never expose banking, remittance or approval actors.
    return {"items":_rows(db,"""SELECT id,invoice_reference AS invoice_number,status,matched_at
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
    candidates=_rows(db,"""SELECT s.id,s.filename,s.evidence_type,s.related_kind,s.related_id,
       p.supplier_id,v.legal_name,s.dms_evidence_asset_id,s.dms_retention_id
       FROM external_partner_evidence_submissions s
       JOIN external_tenant_providers p ON p.amo_id=s.amo_id AND p.id=s.tenant_provider_id
       JOIN procurement_suppliers v ON v.amo_id=p.amo_id AND v.id=p.supplier_id
       JOIN document_retention_dispositions d ON d.tenant_id=s.amo_id
         AND d.id=s.dms_retention_id AND d.status!='DISPOSED'
       WHERE s.amo_id=:amo AND s.status='ACCEPTED' AND s.dms_evidence_asset_id IS NOT NULL
         AND s.related_kind IN ('RFQ','PO','SHIPMENT')
         AND NOT EXISTS (SELECT 1 FROM procurement_documents docs
           WHERE docs.amo_id=s.amo_id AND docs.source='SUPPLIER_PORTAL'
             AND docs.external_reference=s.id)
       ORDER BY s.created_at DESC LIMIT :limit""",amo=amo,limit=limit)
    return {"events":items,"quotes":quotes,"shipments":shipments,
        "document_candidates":candidates,
        "boundary":"No provider action authorizes award, PO, Stores receiving, Quality release or Finance payment"}

class StaffDecision(BaseModel):
    action: str = Field(pattern="^(REPLY|ACCEPT_DATE_PROPOSAL|REJECT_PROPOSAL|ACKNOWLEDGE|REFER_ALTERNATE_TO_TECHNICAL)$")
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


def _technical_tenant(db,amo_code,user):
    from .router import TECHNICAL_APPROVAL_ROLES
    if user.role not in TECHNICAL_APPROVAL_ROLES:
        raise HTTPException(403,"Appointed technical reviewer required")
    amo=service.resolve_tenant_amo_id(db,amo_code=amo_code,current_user=user)
    if db.get_bind().dialect.name=="postgresql":
        db.execute(text("SELECT set_config('app.tenant_id',:amo,true)"),{"amo":amo})
    return amo

@staff_router.get("/technical-review")
def technical_review_queue(amo_code:str,db:Session=Depends(get_db),
                           user=Depends(get_current_active_user)):
    amo=_technical_tenant(db,amo_code,user)
    return {"items":_rows(db,"""SELECT e.id AS external_quote_id,q.id AS canonical_quote_id,
        e.external_reference,e.revision_no,q.supplier_id,q.rfq_id,
        l.id AS quote_line_id,l.requisition_line_id,l.supplier_part_number,l.manufacturer,
        l.quantity,l.uom,l.traceability_statement,l.deviation,
        r.part_number AS requested_part_number,r.description AS requested_description,
        r.alternates_allowed,r.required_certification,r.approved_manufacturers
      FROM external_procurement_quotes e
      JOIN procurement_quotes q ON q.id=e.canonical_quote_id AND q.amo_id=e.amo_id
      JOIN procurement_quote_lines l ON l.quote_id=q.id AND l.is_technically_compliant=false
      JOIN procurement_requisition_lines r ON r.id=l.requisition_line_id
      WHERE e.amo_id=:amo AND e.status='SUBMITTED' AND q.status IN ('RECEIVED','NONCOMPLIANT')
      ORDER BY e.submitted_at,l.id LIMIT 100""",amo=amo)}

class TechnicalAlternateDecision(BaseModel):
    decision: str = Field(pattern="^(APPROVED|REJECTED)$")
    rationale: str = Field(min_length=12,max_length=2500)
    technical_reference: str = Field(min_length=3,max_length=160)
    idempotency_key: str = Field(min_length=12,max_length=80)

@staff_router.post("/technical-review/{quote_line_id}/decision")
def technical_alternate_decision(amo_code:str,quote_line_id:int,
             payload:TechnicalAlternateDecision,db:Session=Depends(get_db),
             user=Depends(get_current_active_user)):
    amo=_technical_tenant(db,amo_code,user)
    row=_row(db,"""SELECT l.id,l.requisition_line_id,l.is_technically_compliant,
          l.supplier_part_number,l.manufacturer,e.id AS external_quote_id,
          e.supplier_id,e.status AS external_state,q.status AS quote_state,
          r.alternates_allowed,r.part_number AS requested_part_number
        FROM procurement_quote_lines l JOIN procurement_quotes q ON q.id=l.quote_id
        JOIN external_procurement_quotes e ON e.canonical_quote_id=q.id AND e.amo_id=q.amo_id
        JOIN procurement_requisition_lines r ON r.id=l.requisition_line_id
        WHERE q.amo_id=:amo AND l.id=:id FOR UPDATE""",amo=amo,id=quote_line_id)
    if not row:raise HTTPException(404,"External alternate quote line unavailable")
    if row["external_state"]!="SUBMITTED" or row["quote_state"] not in ("RECEIVED","NONCOMPLIANT"):
        raise HTTPException(409,"Only current unevaluated revisions accept technical decisions")
    if payload.decision=="APPROVED" and not row["alternates_allowed"]:
        raise HTTPException(409,"Requisition does not permit alternate parts; create a governed technical amendment first")
    ctx={"amo":amo,"supplier":row["supplier_id"]}
    already=_row(db,"""SELECT id FROM external_procurement_events WHERE amo_id=:amo
      AND supplier_id=:supplier AND idempotency_key=:key""",
      amo=amo,supplier=row["supplier_id"],key=payload.idempotency_key)
    if already:return {"id":already["id"],"retry":True}
    db.execute(text("""UPDATE procurement_quote_lines SET is_technically_compliant=:approved
        WHERE id=:line"""),{"approved":payload.decision=="APPROVED","line":quote_line_id})
    eid,_=_event(db,ctx,"QUOTE",row["external_quote_id"],
       "ALTERNATE_TECHNICAL_"+payload.decision,actor=str(user.id),message=payload.rationale,
       details={"quote_line_id":quote_line_id,"original_pn":row["requested_part_number"],
       "offered_pn":row["supplier_part_number"],"reference":payload.technical_reference},
       key=payload.idempotency_key)
    db.commit()
    return {"id":eid,"decision":payload.decision,"quality_approval_conferred":False,
      "purchase_order_approved":False}


class InvoiceNotice(BaseModel):
    invoice_reference: str = Field(min_length=2,max_length=128)
    invoice_total: Decimal = Field(gt=0,max_digits=14,decimal_places=2)
    currency: str = Field(pattern=r"^[A-Z]{3}$")
    source_submission_id: str = Field(min_length=36,max_length=36)
    note: str = Field(default="",max_length=1500)
    idempotency_key: str = Field(min_length=12,max_length=80)

@partner_router.post("/purchase-orders/{po_id}/invoice-notices")
def submit_invoice_notice(tenant_slug:str,po_id:int,payload:InvoiceNotice,
                          request:Request,db:Session=Depends(get_db)):
    user,ctx=_session(db,request,tenant_slug,True)
    _po(db,ctx,po_id,True)
    _gate(db,ctx,{"PART" if l["part_number"] else "SERVICE" for l in _po_lines(db,po_id)})
    original=_row(db,"""SELECT s.id,s.status,s.evidence_type,s.dms_retention_id,
         d.status AS retention_status
       FROM external_partner_evidence_submissions s
       LEFT JOIN document_retention_dispositions d ON d.id=s.dms_retention_id
         AND d.tenant_id=s.amo_id
       WHERE s.amo_id=:amo AND s.tenant_provider_id=:provider AND s.id=:id
         AND s.related_kind='PO' AND s.related_id=:po""",
       amo=ctx["amo"],provider=ctx["provider"],id=payload.source_submission_id,po=str(po_id))
    if not original or original["status"]!="ACCEPTED" or not original["dms_retention_id"] or original["retention_status"]=="DISPOSED":
        raise HTTPException(409,"Invoice original must first be accepted and registered in governed DMS retention")
    if original["evidence_type"] not in ("SUPPLIER_INVOICE","PROFORMA_INVOICE","CREDIT_NOTE"):
        raise HTTPException(422,"Select a classified supplier invoice or credit note")
    existing=_row(db,"""SELECT id FROM external_procurement_events WHERE amo_id=:amo
         AND supplier_id=:supplier AND idempotency_key=:key""",
         amo=ctx["amo"],supplier=ctx["supplier"],key=payload.idempotency_key)
    if existing:return {"id":existing["id"],"retry":True}
    eid,_=_event(db,ctx,"PO",po_id,"INVOICE_SUBMITTED",identity=ctx["person"],message=payload.note,
      details={"invoice_reference":payload.invoice_reference,"total":str(payload.invoice_total),
        "currency":payload.currency,"source_submission_id":payload.source_submission_id},
      key=payload.idempotency_key)
    db.commit()
    return {"id":eid,"status":"PENDING_FINANCE_REGISTRATION",
        "payment_approved":False,"finance_ownership_preserved":True}


class ImportProviderDocument(BaseModel):
    reason: str = Field(min_length=8,max_length=2000)

@staff_router.post("/documents/{submission_id}/import")
def import_governed_supplier_document(amo_code:str,submission_id:str,
             payload:ImportProviderDocument,db:Session=Depends(get_db),
             user=Depends(get_current_active_user)):
    """Reference the same DMS-retained original in canonical Procurement documents."""
    from . import document_models
    amo=_staff(db,amo_code,user)
    stage=_row(db,"""SELECT s.*,p.supplier_id,
          a.storage_path AS dms_path,a.sha256 AS dms_hash,
          d.status AS retention_status
        FROM external_partner_evidence_submissions s
        JOIN external_tenant_providers p ON p.id=s.tenant_provider_id AND p.amo_id=s.amo_id
        JOIN document_evidence_assets a ON a.id=s.dms_evidence_asset_id AND a.tenant_id=s.amo_id
        JOIN document_retention_dispositions d ON d.id=s.dms_retention_id AND d.tenant_id=s.amo_id
          AND d.source_type='EVIDENCE_ASSET' AND d.source_id=a.id
        WHERE s.amo_id=:amo AND s.id=:id FOR UPDATE""",amo=amo,id=submission_id)
    if not stage or stage["status"]!="ACCEPTED" or stage["retention_status"]=="DISPOSED":
        raise HTTPException(409,"Only DMS-retained and accepted provider originals may enter Procurement")
    if stage["sha256"]!=stage["dms_hash"]:
        raise HTTPException(409,"Original hash and DMS custody evidence do not match")
    kind=stage["related_kind"]
    if kind not in ("RFQ","PO","SHIPMENT"):
        raise HTTPException(422,"Only supplier transaction evidence belongs in Procurement")
    if kind=="SHIPMENT":
        shipment=_row(db,"""SELECT po_id FROM external_procurement_shipments
          WHERE amo_id=:amo AND supplier_id=:supplier AND id=:id""",
          amo=amo,supplier=stage["supplier_id"],id=stage["related_id"])
        if not shipment:raise HTTPException(404,"Shipment is not assigned to this supplier")
        entity_type=document_models.ProcurementDocumentEntityType.PURCHASE_ORDER
        entity_id=str(shipment["po_id"])
    else:
        entity_type=(document_models.ProcurementDocumentEntityType.RFQ if kind=="RFQ"
            else document_models.ProcurementDocumentEntityType.PURCHASE_ORDER)
        entity_id=stage["related_id"]
    if kind=="RFQ":
        eligible=_row(db,"""SELECT r.id FROM procurement_rfqs r JOIN procurement_rfq_suppliers i
           ON i.rfq_id=r.id WHERE r.amo_id=:amo AND i.supplier_id=:supplier
             AND CAST(r.id AS TEXT)=:item""",amo=amo,supplier=stage["supplier_id"],item=entity_id)
    else:
        eligible=_row(db,"""SELECT id FROM procurement_purchase_orders WHERE amo_id=:amo
           AND supplier_id=:supplier AND CAST(id AS TEXT)=:item""",
           amo=amo,supplier=stage["supplier_id"],item=entity_id)
    if not eligible:raise HTTPException(409,"Original was not assigned to this canonical supplier transaction")
    existing=db.query(document_models.ProcurementDocument).filter(
        document_models.ProcurementDocument.amo_id==amo,
        document_models.ProcurementDocument.source==document_models.ProcurementDocumentSource.SUPPLIER_PORTAL,
        document_models.ProcurementDocument.external_reference==submission_id).first()
    if existing:return {"id":existing.id,"already_imported":True}
    quality_type=stage["evidence_type"] in {
        "COMPONENT_RELEASE_CERTIFICATE","CONFORMITY_DOCUMENT","CALIBRATION_CERTIFICATE",
        "TEST_CERTIFICATE","SHIPMENT_RELEASE"}
    rec=document_models.ProcurementDocument(
        amo_id=amo,entity_type=entity_type,entity_id=entity_id,
        document_type=stage["evidence_type"],title=stage["filename"],
        source=document_models.ProcurementDocumentSource.SUPPLIER_PORTAL,
        original_filename=stage["filename"],stored_path=stage["object_uri"],
        mime_type=stage["content_type"],size_bytes=stage["size_bytes"],
        sha256=stage["sha256"],external_reference=submission_id,
        # Staging originals are governed DMS *evidence assets*, not published manual
        # revisions. Never represent their containing revision as the original.
        dms_document_id=None,dms_revision_id=None,
        is_quality_evidence=quality_type,
        verification_status=(document_models.ProcurementDocumentVerificationStatus.PENDING
            if quality_type else document_models.ProcurementDocumentVerificationStatus.NOT_REQUIRED),
        notes=payload.reason,uploaded_by_user_id=str(user.id))
    db.add(rec);db.flush()
    # No physical receiving/stock change, no QMS verification, no Finance payment.
    _event(db,{"amo":amo,"supplier":stage["supplier_id"]},"PO" if kind!="RFQ" else "RFQ",
       entity_id,"SUPPORTING_DOCUMENT_LINKED",actor=str(user.id),
       details={"document_id":rec.id,"submission_id":submission_id,"dms_retention_id":stage["dms_retention_id"]})
    db.commit()
    return {"id":rec.id,"canonical_procurement_document":True,"stores_released":False,
            "finance_payment_authorized":False}
