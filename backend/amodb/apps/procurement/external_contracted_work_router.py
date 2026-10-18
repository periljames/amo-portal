"""Phase 7 outbound contracted maintenance: MOPM 2.23 / 2.20.

This is a technical work-order authority boundary. Vendor logins never acquire
internal maintenance, Quality, Stores, certification or Procurement privileges.
"""
from __future__ import annotations

import json
from datetime import date, datetime, timezone
from pathlib import Path
from uuid import uuid4

from fastapi import APIRouter, Depends, HTTPException, Query, Request
from fastapi.responses import FileResponse
from pydantic import BaseModel, Field, model_validator
from sqlalchemy import bindparam, text, inspect
from sqlalchemy.orm import Session

from amodb.database import get_db
from amodb.security import get_current_active_user
from . import external_partner_router as partner
from . import service, supplier_quality_control
from amodb import storage

staff_router = APIRouter(prefix="/api/maintenance/{amo_code}/contracted-work", tags=["Contracted maintenance"])
partner_router = APIRouter(prefix="/api/external-provider/partner/{tenant_slug}/maintenance-work", tags=["Contracted maintenance partner"])
MANAGERS = {"BASE":"BASE_MAINTENANCE_MANAGER","LINE":"LINE_MAINTENANCE_MANAGER",
            "WORKSHOP":"WORKSHOP_MANAGER","SPECIALISED":"WORKSHOP_MANAGER"}
QUALITY = {"QUALITY_MANAGER"}
STORES = {"STORES_MANAGER","STOREKEEPER","STORES","QUALITY_INSPECTOR"}
EVIDENCE_CATEGORIES = {"INSPECTION_REPORT","STRIP_REPORT","TEST_RESULT","MAINTENANCE_RELEASE",
                       "WORK_RECORD","SHIPPING","RECEIVING","SAFETY","ADDITIONAL_WORK","OTHER"}
NEXT = {
    "DRAFT":{"SUBMIT_SCOPE":"TECHNICAL_SCOPE_REVIEW","CANCEL":"CANCELLED"},
    "TECHNICAL_SCOPE_REVIEW":{"SCOPE_APPROVED":"QUALIFICATION_AGREEMENT_CHECK","HOLD":"ON_HOLD","CANCEL":"CANCELLED"},
    "QUALIFICATION_AGREEMENT_CHECK":{"QUALITY_ACCEPTED":"AWAITING_AUTHORIZATION","HOLD":"ON_HOLD","CANCEL":"CANCELLED"},
    "AWAITING_AUTHORIZATION":{"AUTHORIZE":"AUTHORIZED","HOLD":"ON_HOLD","CANCEL":"CANCELLED"},
    "AUTHORIZED":{"DISPATCH":"DISPATCHED","HOLD":"ON_HOLD","CANCEL":"CANCELLED"},
    "DISPATCHED":{"PROVIDER_ACCEPT":"PROVIDER_ACCEPTED","HOLD":"ON_HOLD"},
    "PROVIDER_ACCEPTED":{"START":"IN_PROGRESS","HOLD":"ON_HOLD"},
    "IN_PROGRESS":{"COMPLETE":"WORK_COMPLETED","HOLD":"ON_HOLD"},
    "WORK_COMPLETED":{"SUBMIT_RELEASE":"RELEASE_SUBMITTED","REWORK":"REWORK_REQUIRED","HOLD":"ON_HOLD"},
    "RELEASE_SUBMITTED":{"RETURN":"RETURNED","REWORK":"REWORK_REQUIRED","HOLD":"ON_HOLD"},
    "RETURNED":{"RECEIVE":"INSPECTION","HOLD":"ON_HOLD"},
    "INSPECTION":{"TECHNICAL_ACCEPT":"TECHNICALLY_ACCEPTED","REJECT":"REWORK_REQUIRED","HOLD":"ON_HOLD"},
    "TECHNICALLY_ACCEPTED":{"CLOSE":"CLOSED","HOLD":"ON_HOLD"},
    "REWORK_REQUIRED":{"RESUME_REWORK":"IN_PROGRESS","HOLD":"ON_HOLD"},
    "ON_HOLD":{"RESUME":"__PREVIOUS__","CANCEL":"CANCELLED"},
    "CLOSED":{"REOPEN":"REWORK_REQUIRED"},
    "CANCELLED":{"REOPEN":"DRAFT"},
}
PROVIDER_ACTIONS = {"PROVIDER_ACCEPT","START","COMPLETE","SUBMIT_RELEASE","RETURN"}
QUALITY_ACTIONS = {"QUALITY_ACCEPTED"}
STORES_ACTIONS = {"RECEIVE"}
MANAGER_ACTIONS = {action for transitions in NEXT.values() for action in transitions} - PROVIDER_ACTIONS - QUALITY_ACTIONS - STORES_ACTIONS


def _one(db,sql,**params):
    x=db.execute(text(sql),params).mappings().first()
    return dict(x) if x else None


def _all(db,sql,**params):
    return [dict(row) for row in db.execute(text(sql),params).mappings().all()]


def _role(user):
    return str(getattr(user.role,"value",user.role))


def _staff(db,amo_code,user):
    amo=service.resolve_tenant_amo_id(db,amo_code=amo_code,current_user=user)
    if _role(user) not in set(MANAGERS.values())|QUALITY|STORES|{"QUALITY_OFFICER","DOCUMENT_CONTROL_OFFICER"}:
        raise HTTPException(403,"An appointed maintenance, Quality, Stores or document-control role is required")
    if db.get_bind().dialect.name=="postgresql":
        db.execute(text("SELECT set_config('app.tenant_id',:amo,true)"),{"amo":amo})
        db.execute(text("SELECT set_config('app.external_provider_id','__INTERNAL_QUALITY_REVIEW__',true)"))
    return amo


def _work(db,amo,work_id,*,lock=False):
    sql="""SELECT * FROM external_contracted_work WHERE amo_id=:amo AND id=:id"""
    if lock and db.get_bind().dialect.name=="postgresql":sql+=" FOR UPDATE"
    row=_one(db,sql,amo=amo,id=work_id)
    if not row:raise HTTPException(404,"Contracted work not found in tenant")
    return row


def _partner(db,request,tenant_slug,write=False):
    session=partner._ctx(db,request,tenant_slug,cap="task.respond" if write else "task.read",write=write)
    if write:partner._cap(session,"task.respond")
    return session,partner._context(session)


def _assigned(session,work_id):
    partner._require_object(session,"contracted_work",work_id)


def _partner_work(db,session,ctx,work_id,lock=False):
    _assigned(session,work_id)
    row=_work(db,ctx["amo"],work_id,lock=lock)
    if not row["authorized_at"] or row["supplier_id"]!=ctx["supplier"] or row["provider_id"]!=ctx["provider"]:
        raise HTTPException(404,"Contracted work is not assigned to this provider")
    return row


def _event(db,work,action,reason,*,staff=None,identity=None,previous=None,target=None,details=None,retry=None):
    if retry:
        found=_one(db,"""SELECT id FROM external_contracted_work_events
             WHERE amo_id=:amo AND work_id=:work AND idempotency_key=:retry""",
             amo=work["amo_id"],work=work["id"],retry=retry)
        if found:return found["id"],False
    eid=str(uuid4())
    db.execute(text("""INSERT INTO external_contracted_work_events
       (id,amo_id,work_id,actor_user_id,actor_identity_id,action,from_state,to_state,
        reason,details_json,idempotency_key)
       VALUES(:id,:amo,:work,:staff,:identity,:action,:previous,:target,:reason,CAST(:details AS JSON),:retry)"""),
       dict(id=eid,amo=work["amo_id"],work=work["id"],staff=staff,identity=identity,
            action=action,previous=previous,target=target,reason=reason,
            details=json.dumps(details or {},default=str),retry=retry))
    return eid,True


def _notify_assigned_members(db,work,subject,message):
    """Queue only for active, individually granted vendor members, never every supplier."""
    grants=_all(db,"""SELECT g.object_scope_json,i.id AS identity_id
        FROM external_tenant_grants g
        JOIN external_organization_memberships m ON m.id=g.membership_id
         AND m.organization_id=(SELECT organization_id FROM external_tenant_providers
                                WHERE amo_id=g.amo_id AND id=g.tenant_provider_id)
        JOIN external_identities i ON i.id=m.identity_id
        WHERE g.amo_id=:amo AND g.tenant_provider_id=:provider
          AND g.status='ACTIVE' AND m.status='ACTIVE' AND i.status='ACTIVE'""",
        amo=work["amo_id"],provider=work["provider_id"])
    for grant in grants:
        if str(work["id"]) not in {str(x) for x in
                                  (grant["object_scope_json"] or {}).get("contracted_work",[])}:
            continue
        db.execute(text("""INSERT INTO external_partner_notifications
          (id,amo_id,tenant_provider_id,identity_id,category,title,message,resource_kind,resource_id)
          VALUES(:id,:amo,:provider,:identity,'MAINTENANCE',:title,:message,'CONTRACTED_WORK',:work)"""),
          dict(id=str(uuid4()),amo=work["amo_id"],provider=work["provider_id"],
               identity=grant["identity_id"],title=subject[:200],message=message,
               work=str(work["id"])))


def _technical_requirements(work):
    errors=[]
    for key in ("function","scope_text","site_code","contract_id","internal_work_reference",
                "data_reference","data_revision","required_release","defect","technical_coordinator_id"):
        if not str(work.get(key) or "").strip():errors.append(key)
    if not work.get("inspections_json"):errors.append("required inspection/test criteria")
    req=work["requirements_json"] or {}
    if req.get("foreign") and not (req.get("state_of_registry") and req.get("foreign_approval_reference")
        and req.get("operator_requirements") and req.get("release_wording")):
        errors.append("State-of-Registry, operator, foreign approval and release evidence")
    for key,ref in (("authority_approval_required","authority_acceptance_reference"),
                    ("operator_approval_required","operator_approval_reference"),
                    ("safety_assessment_required","safety_assessment_reference")):
        if req.get(key) and not req.get(ref):errors.append(ref)
    if req.get("further_subcontracting_requested") and not req.get("prior_written_acceptance_reference"):
        errors.append("prior written acceptance of further subcontracting")
    if errors:raise HTTPException(409,{"code":"TECHNICAL_WORK_INCOMPLETE","missing":errors})


def _eligibility(db,work):
    # Never substitute general supplier approval for the actual site, capability,
    # controlled written agreement or State-of-Registry conditions of this job.
    _technical_requirements(work)
    ctx=dict(amo=work["amo_id"],supplier=work["supplier_id"],scope=work["scope_id"],
             site=work["site_code"],contract=work["contract_id"],provider=work["provider_id"])
    scope=_one(db,"""SELECT id,category,site_code,product_family,approval_number,authority,restrictions
         FROM procurement_supplier_approval_scopes
         WHERE amo_id=:amo AND supplier_id=:supplier AND id=:scope
           AND site_code=:site AND status='ACTIVE'
           AND (effective_on IS NULL OR effective_on<=CURRENT_DATE)
           AND (expires_on IS NULL OR expires_on>=CURRENT_DATE)""",**ctx)
    if not scope or scope["category"] not in ("MAINTENANCE","CONTRACTED_MAINTENANCE"):
        raise HTTPException(409,"No current Quality-approved maintenance capability at the nominated site")
    if not scope["approval_number"] or not scope["authority"] or scope["authority"]=="TENANT_QMS":
        raise HTTPException(409,"Contracted AMO must have a verified aviation-authority approval reference")
    if scope.get("restrictions") and not (work["requirements_json"] or {}).get("restriction_review_reference"):
        raise HTTPException(409,"Capability limitations require documented technical disposition")
    # QMS performs an internal-privilege cross-domain check. Restore the
    # incoming member's PostgreSQL RLS marker even if the eligibility gate fails.
    previous_marker=None
    if db.get_bind().dialect.name=="postgresql":
        previous_marker=db.execute(text("SELECT current_setting('app.external_provider_id',true)")).scalar()
    try:
        supplier_quality_control.assert_supplier_usage_allowed(
            db,amo_id=work["amo_id"],supplier_id=work["supplier_id"],
            categories={scope["category"]},allow_controlled_override=False,
            site_code=work["site_code"],product_family=scope["product_family"],
            capability=str(scope["id"]),contracted_function=work["function"],contract_id=work["contract_id"])
        contract=_one(db,"""SELECT c.id FROM quality_external_provider_contracts c
          JOIN external_tenant_providers p ON p.amo_id=c.amo_id AND p.supplier_id=c.supplier_id AND p.id=:provider
          JOIN external_partner_evidence_submissions s
            ON s.amo_id=c.amo_id AND s.id=c.signed_evidence_submission_id
            AND s.related_kind='CONTRACT' AND s.related_id=c.id AND s.status='ACCEPTED'
            AND s.dms_evidence_asset_id IS NOT NULL AND s.dms_retention_id IS NOT NULL
          JOIN document_retention_dispositions d
            ON d.tenant_id=s.amo_id AND d.id=s.dms_retention_id AND d.status!='DISPOSED'
          JOIN quality_external_provider_evidence e
            ON e.amo_id=c.amo_id AND e.supplier_id=c.supplier_id AND e.id=s.qms_evidence_id
            AND e.status='VERIFIED' AND (e.valid_until IS NULL OR e.valid_until>=CURRENT_DATE)
          JOIN manuals m ON m.id=c.controlled_document_id
          JOIN manual_tenants t ON t.id=m.tenant_id AND t.amo_id=c.amo_id
          JOIN manual_revisions r ON r.manual_id=m.id AND r.id=m.current_published_rev_id
            AND r.status_enum='PUBLISHED' AND r.published_at IS NOT NULL
            AND s.sha256=r.source_sha256
            AND (r.id=c.controlled_document_revision OR r.rev_number=c.controlled_document_revision)
          WHERE c.amo_id=:amo AND c.supplier_id=:supplier AND c.id=:contract
            AND c.status='ACTIVE'
            AND (c.effective_on IS NULL OR c.effective_on<=CURRENT_DATE)
            AND (c.expires_on IS NULL OR c.expires_on>=CURRENT_DATE)
            AND c.approved_sites_json IS NOT NULL
          """,**ctx)
        if not contract:
            raise HTTPException(409,"The exact maintenance agreement is not current, DMS-retained and independently Quality-verified")
        sites=_one(db,"""SELECT approved_sites_json,scope_text FROM quality_external_provider_contracts
                          WHERE amo_id=:amo AND id=:contract""",**ctx)
        if work["site_code"] not in (sites["approved_sites_json"] or []):
            raise HTTPException(409,"Contract does not approve this contracted maintenance location")
        req=work["requirements_json"] or {}
        if work["function"].casefold() not in str(sites["scope_text"] or "").casefold() and not req.get("contract_function_approval_reference"):
            raise HTTPException(409,"Written maintenance agreement does not identify the contracted function; Quality review of a specific function reference is required")
        if scope["product_family"] not in ("ALL","*"):
            if not req.get("product_family") or str(req["product_family"]).casefold()!=str(scope["product_family"]).casefold():
                raise HTTPException(409,"Technical asset/product family is not covered by this approved contractor capability")
        if req.get("data_manual_id"):
            current=_one(db,"""SELECT r.id FROM manuals m
                JOIN manual_tenants t ON t.id=m.tenant_id AND t.amo_id=:amo
                JOIN manual_revisions r ON r.id=m.current_published_rev_id AND r.manual_id=m.id
                WHERE m.id=:manual AND r.id=:revision
                  AND r.status_enum='PUBLISHED' AND r.published_at IS NOT NULL
                  AND r.source_storage_path IS NOT NULL""",
                amo=work["amo_id"],manual=req["data_manual_id"],revision=req.get("data_revision_id"))
            if not current:
                raise HTTPException(409,"Controlled technical-data revision changed or is no longer published; obtain reviewed current instructions")
        return scope
    finally:
        if db.get_bind().dialect.name=="postgresql":
            db.execute(text("SELECT set_config('app.external_provider_id',:marker,true)"),
                       {"marker":previous_marker or ""})


def _closure_blockers(db,work):
    amo,work_id=work["amo_id"],work["id"]
    additional=_all(db,"""SELECT id,state FROM external_contracted_additional_work
         WHERE amo_id=:amo AND work_id=:id""",amo=amo,id=work_id)
    custody=_all(db,"""SELECT id,state FROM external_contracted_custody WHERE amo_id=:amo AND work_id=:id""",amo=amo,id=work_id)
    evidence=_all(db,"""SELECT l.category,s.status,s.dms_retention_id,d.status AS retention_status,
         s.qms_evidence_id,q.status AS qms_status,q.valid_until AS qms_valid_until
         FROM external_contracted_evidence_links l
         JOIN external_partner_evidence_submissions s ON s.id=l.source_submission_id AND s.amo_id=l.amo_id
         LEFT JOIN document_retention_dispositions d ON d.id=s.dms_retention_id AND d.tenant_id=s.amo_id
         LEFT JOIN quality_external_provider_evidence q ON q.id=s.qms_evidence_id
              AND q.amo_id=s.amo_id AND q.supplier_id=:supplier
         WHERE l.amo_id=:amo AND l.work_id=:id""",amo=amo,id=work_id,supplier=work["supplier_id"])
    valid={x["category"] for x in evidence if x["status"]=="ACCEPTED" and
           x["dms_retention_id"] and x["retention_status"]!="DISPOSED" and
           x["qms_status"]=="VERIFIED" and
           (x["qms_valid_until"] is None or x["qms_valid_until"]>=date.today())}
    blocked=[f"Additional work {x['id']} awaits controlled decision" for x in additional if x["state"]=="REQUESTED"]
    blocked.extend(f"Property item {x['id']} not reconciled" for x in custody if x["state"]!="RECONCILED")
    inspections=_all(db,"""SELECT i.criterion_index,i.criterion,i.result,
          s.status AS submission_status,s.dms_retention_id,d.status AS retention_status,
          q.status AS qms_status,q.valid_until AS qms_valid_until
        FROM external_contracted_inspection_checks i
        LEFT JOIN external_partner_evidence_submissions s ON s.amo_id=i.amo_id AND s.id=i.submission_id
          AND s.tenant_provider_id=:provider AND s.related_kind='CONTRACTED_WORK'
          AND s.related_id=i.work_id
        LEFT JOIN document_retention_dispositions d ON d.tenant_id=s.amo_id AND d.id=s.dms_retention_id
        LEFT JOIN quality_external_provider_evidence q ON q.amo_id=s.amo_id
          AND q.supplier_id=:supplier AND q.id=s.qms_evidence_id
        WHERE i.amo_id=:amo AND i.work_id=:id ORDER BY i.criterion_index""",
        amo=amo,id=work_id,provider=work["provider_id"],supplier=work["supplier_id"])
    if len(inspections)!=len(work.get("inspections_json") or []):
        blocked.append("Required inspection/test criteria are not fully registered")
    for check in inspections:
        if (check["result"]!="ACCEPTED" or check["submission_status"]!="ACCEPTED"
            or not check["dms_retention_id"] or check["retention_status"] in (None,"DISPOSED")
            or check["qms_status"]!="VERIFIED"
            or (check["qms_valid_until"] is not None and check["qms_valid_until"]<date.today())):
            blocked.append(f"Inspection/test criterion {check['criterion_index']+1} not independently evidenced and reviewed")
    if any(x["state"]=="APPROVED" for x in additional) and "ADDITIONAL_WORK" not in valid:
        blocked.append("Accepted governed amended-scope and additional-work evidence missing")
    for kind in ("MAINTENANCE_RELEASE","WORK_RECORD","TEST_RESULT"):
        if kind not in valid:blocked.append(f"Accepted governed {kind.lower()} evidence missing")
    req=work.get("requirements_json") or {}
    for key,kind in (("independent_inspection_required","INSPECTION_REPORT"),
                     ("safety_report_required","SAFETY")):
        if req.get(key) and kind not in valid:blocked.append(f"Required {kind.lower()} evidence missing")
    return blocked


def _history(db,work):
    return _all(db,"""SELECT id,action,from_state,to_state,reason,details_json,
         actor_user_id,actor_identity_id,created_at FROM external_contracted_work_events
         WHERE amo_id=:amo AND work_id=:id ORDER BY created_at,id""",amo=work["amo_id"],id=work["id"])


def _details(db,work,include_history=True):
    amo,work_id=work["amo_id"],work["id"]
    return {"work":work,
        "additional_work":_all(db,"""SELECT * FROM external_contracted_additional_work
          WHERE amo_id=:amo AND work_id=:id ORDER BY created_at""",amo=amo,id=work_id),
        "custody":_all(db,"""SELECT * FROM external_contracted_custody
          WHERE amo_id=:amo AND work_id=:id ORDER BY updated_at""",amo=amo,id=work_id),
        "inspection_checks":_all(db,"""SELECT i.criterion_index,i.criterion,i.result,i.submission_id,
            i.review_reason,i.reviewed_by_user_id,i.reviewed_at,s.filename
            FROM external_contracted_inspection_checks i
            LEFT JOIN external_partner_evidence_submissions s ON s.amo_id=i.amo_id AND s.id=i.submission_id
            WHERE i.amo_id=:amo AND i.work_id=:id ORDER BY i.criterion_index""",amo=amo,id=work_id),
        "evidence":_all(db,"""SELECT l.id,l.category,s.id AS submission_id,s.filename,s.status,
         s.sha256,s.dms_retention_id,d.status AS retention_status
         FROM external_contracted_evidence_links l
         JOIN external_partner_evidence_submissions s ON s.id=l.source_submission_id AND s.amo_id=l.amo_id
         LEFT JOIN document_retention_dispositions d ON d.id=s.dms_retention_id AND d.tenant_id=s.amo_id
         WHERE l.amo_id=:amo AND l.work_id=:id ORDER BY l.created_at""",amo=amo,id=work_id),
        "closure_blockers":_closure_blockers(db,work),
        "history":_history(db,work) if include_history else []}


class NewWork(BaseModel):
    work_number: str = Field(min_length=3,max_length=80)
    supplier_id: int = Field(gt=0)
    provider_id: str = Field(min_length=36,max_length=36)
    scope_id: int = Field(gt=0)
    contract_id: str = Field(min_length=36,max_length=36)
    work_type: str = Field(pattern="^(BASE|LINE|WORKSHOP|SPECIALISED)$")
    work_title: str = Field(min_length=5,max_length=255)
    function: str = Field(min_length=8,max_length=255)
    scope_text: str = Field(min_length=12,max_length=5000)
    site_code: str = Field(min_length=2,max_length=64)
    internal_work_reference: str = Field(min_length=3,max_length=128)
    technical_coordinator_id: str = Field(min_length=36,max_length=36)
    asset_kind: str = Field(pattern="^(AIRCRAFT|ENGINE|COMPONENT|PROPELLER|APU|SERVICE)$")
    registration: str | None = Field(default=None,max_length=40)
    part_number: str | None = Field(default=None,max_length=90)
    serial_number: str | None = Field(default=None,max_length=90)
    asset_description: str | None = Field(default=None,max_length=255)
    defect: str = Field(min_length=8,max_length=5000)
    data_reference: str = Field(min_length=4,max_length=255)
    data_revision: str = Field(min_length=1,max_length=80)
    inspections: list[str] = Field(min_length=1,max_length=100)
    required_release: str = Field(min_length=4,max_length=255)
    requirements: dict[str,str|bool|None] = Field(default_factory=dict)
    data_manual_id: str | None = Field(default=None,max_length=36)
    data_revision_id: str | None = Field(default=None,max_length=36)
    purchase_order_id: int | None = None

    @model_validator(mode="after")
    def valid(self):
        for field in ("expected_completion_at","provider_ack_due_at"):
            raw=self.requirements.get(field)
            if raw:
                try:
                    datetime.fromisoformat(str(raw).replace("Z","+00:00"))
                except ValueError as exc:
                    raise ValueError(f"{field} must be a valid ISO local date/time") from exc
        if bool(self.data_manual_id) != bool(self.data_revision_id):
            raise ValueError("Controlled maintenance data requires a document and an exact revision")
        if not any([self.registration,self.part_number,self.serial_number,self.asset_description]):
            raise ValueError("Identify the aircraft, engine, component or specialised service")
        return self


class Transition(BaseModel):
    action: str = Field(min_length=3,max_length=48)
    expected_version: int = Field(ge=1)
    reason: str = Field(min_length=8,max_length=2000)
    details: dict[str,str|bool|float|None] = Field(default_factory=dict)
    idempotency_key: str = Field(min_length=12,max_length=80)


class ProviderNote(BaseModel):
    kind: str = Field(pattern="^(PROGRESS|FINDING|DISCREPANCY|ETA_CHANGE|TECHNICAL_QUERY|RETURN_SHIPMENT|PROTECTIVE_ACTION)$")
    message: str = Field(min_length=8,max_length=4000)
    expected_version: int = Field(ge=1)
    idempotency_key: str = Field(min_length=12,max_length=80)


class AdditionalRequest(BaseModel):
    description: str = Field(min_length=12,max_length=4000)
    technical_data: str | None = Field(default=None,max_length=2000)
    commercial_reference: str | None = Field(default=None,max_length=128)
    idempotency_key: str = Field(min_length=12,max_length=80)


class AdditionalDecision(BaseModel):
    decision: str = Field(pattern="^(APPROVED|REJECTED)$")
    reason: str = Field(min_length=12,max_length=2000)
    technical_data: str | None = None
    operator_approval_reference: str | None = None
    authority_approval_reference: str | None = None
    amended_work_reference: str | None = None
    commercial_variation_reference: str | None = None


class CustodyNew(BaseModel):
    item_type: str = Field(pattern="^(COMPONENT|EXCHANGE|LOAN|TOOL|EQUIPMENT|CUSTOMER_PROPERTY|MATERIAL|CONSUMABLE)$")
    description: str = Field(min_length=3,max_length=255)
    part_number: str | None = Field(default=None,max_length=96)
    serial_batch: str | None = Field(default=None,max_length=128)
    quantity: float = Field(gt=0)
    uom: str = Field(min_length=1,max_length=24)
    condition: str | None = Field(default=None,max_length=255)
    stores_reference: str = Field(min_length=4,max_length=128)


class CustodyUpdate(BaseModel):
    state: str = Field(pattern="^(DISPATCHED|RECEIVED_BY_PROVIDER|CONSUMED|RETURNED|DISCREPANCY|RECONCILED)$")
    reason: str = Field(min_length=8,max_length=2000)
    discrepancy: str | None = None


class LinkEvidence(BaseModel):
    source_submission_id: str = Field(min_length=36,max_length=36)
    category: str


class InspectionDecision(BaseModel):
    result: str = Field(pattern="^(ACCEPTED|REJECTED)$")
    source_submission_id: str | None = Field(default=None,min_length=36,max_length=36)
    reason: str = Field(min_length=8,max_length=2000)
    expected_version: int = Field(ge=1)


class ExpectedWorkDates(BaseModel):
    expected_version: int = Field(ge=1)
    expected_completion_at: str | None = None
    provider_ack_due_at: str | None = None
    reason: str = Field(min_length=8,max_length=2000)
    idempotency_key: str = Field(min_length=12,max_length=80)

    @model_validator(mode="after")
    def valid_dates(self):
        for field in ("expected_completion_at","provider_ack_due_at"):
            raw=getattr(self,field)
            if raw:
                try: datetime.fromisoformat(raw.replace("Z","+00:00"))
                except ValueError as exc:
                    raise ValueError(field+" must be ISO local date/time") from exc
        return self

@staff_router.put("/{work_id}/schedule")
def revise_work_schedule(amo_code:str,work_id:str,payload:ExpectedWorkDates,
                        db:Session=Depends(get_db),user=Depends(get_current_active_user)):
    """Only responsible Maintenance Manager may accept an ETA amendment."""
    amo=_staff(db,amo_code,user)
    work=_work(db,amo,work_id,lock=True)
    if _role(user)!=MANAGERS[work["work_type"]]:
        raise HTTPException(403,"Responsible Maintenance Manager schedule control required")
    prior=_one(db,"""SELECT id,action,actor_user_id FROM external_contracted_work_events
       WHERE amo_id=:amo AND work_id=:work AND idempotency_key=:key""",
       amo=amo,work=work_id,key=payload.idempotency_key)
    if prior:
        if prior["action"]!="EXPECTED_DATES_CHANGED" or prior["actor_user_id"]!=str(user.id):
            raise HTTPException(409,"Idempotency key belongs to a different action")
        return {"id":work_id,"retry":True,"version":work["version"]}
    if work["version"]!=payload.expected_version:
        raise HTTPException(409,"Work order changed; refresh before revising its schedule")
    if work["status"] in {"CANCELLED","CLOSED"}:
        raise HTTPException(409,"Closed or cancelled maintenance cannot be rescheduled")
    requirements=dict(work["requirements_json"] or {})
    for field in ("expected_completion_at","provider_ack_due_at"):
        raw=getattr(payload,field)
        if raw:requirements[field]=raw
        else:requirements.pop(field,None)
    # Signed-off schedule is a manager-controlled requirement amendment;
    # a contractor ETA_CHANGE note is only a proposal, not an authorization.
    db.execute(text("""UPDATE external_contracted_work SET
       requirements_json=CAST(:requirements AS JSON),version=version+1,updated_at=NOW()
       WHERE amo_id=:amo AND id=:id AND version=:version"""),
       {"amo":amo,"id":work_id,"version":payload.expected_version,
        "requirements":json.dumps(requirements)})
    _event(db,work,"EXPECTED_DATES_CHANGED",payload.reason,staff=str(user.id),
           details={"expected_completion_at":payload.expected_completion_at,
                    "provider_ack_due_at":payload.provider_ack_due_at},
           retry=payload.idempotency_key)
    db.commit()
    return {"id":work_id,"version":payload.expected_version+1,"updated":True}

@staff_router.get("")
def staff_queue(amo_code:str,db:Session=Depends(get_db),user=Depends(get_current_active_user),
                limit:int=Query(50,ge=1,le=100)):
    amo=_staff(db,amo_code,user)
    return {"items":_all(db,"""SELECT id,work_number,work_type,work_title,status,version,
            supplier_id,site_code,contract_id,updated_at FROM external_contracted_work
          WHERE amo_id=:amo ORDER BY updated_at DESC LIMIT :limit""",amo=amo,limit=limit),
          "can_create":_role(user) in set(MANAGERS.values())}


@staff_router.get("/options")
def work_options(amo_code:str,db:Session=Depends(get_db),
                 user=Depends(get_current_active_user)):
    amo=_staff(db,amo_code,user)
    return {
      "providers":_all(db,"""SELECT p.id,p.supplier_id,s.legal_name
         FROM external_tenant_providers p JOIN procurement_suppliers s
           ON s.amo_id=p.amo_id AND s.id=p.supplier_id
         WHERE p.amo_id=:amo ORDER BY s.legal_name LIMIT 200""",amo=amo),
      "scopes":_all(db,"""SELECT id,supplier_id,category,site_code,product_family,
              approval_number,authority,effective_on,expires_on
         FROM procurement_supplier_approval_scopes WHERE amo_id=:amo
          AND status='ACTIVE' AND category IN ('MAINTENANCE','CONTRACTED_MAINTENANCE')
         ORDER BY supplier_id,site_code LIMIT 300""",amo=amo),
      "contracts":_all(db,"""SELECT id,supplier_id,contract_number,title,status,
             effective_on,expires_on FROM quality_external_provider_contracts
         WHERE amo_id=:amo AND status='ACTIVE' ORDER BY contract_number LIMIT 200""",amo=amo),
      "coordinators":_all(db,"""SELECT id,full_name,staff_code,CAST(role AS TEXT) AS role FROM users
         WHERE amo_id=:amo AND is_active=TRUE AND role IN
           ('BASE_MAINTENANCE_MANAGER','LINE_MAINTENANCE_MANAGER','WORKSHOP_MANAGER')
         ORDER BY full_name LIMIT 100""",amo=amo),
    }


@staff_router.get("/{work_id}/available-evidence")
def evidence_candidates(amo_code:str,work_id:str,db:Session=Depends(get_db),
                        user=Depends(get_current_active_user)):
    amo=_staff(db,amo_code,user)
    work=_work(db,amo,work_id)
    return {"items":_all(db,"""SELECT s.id,s.filename,s.evidence_type,s.status,
       s.created_at,s.dms_retention_id FROM external_partner_evidence_submissions s
       WHERE s.amo_id=:amo AND s.tenant_provider_id=:provider
         AND s.related_kind='CONTRACTED_WORK' AND s.related_id=:work
       ORDER BY s.created_at DESC LIMIT 150""",
       amo=amo,provider=work["provider_id"],work=work_id)}


@staff_router.get("/{work_id}/grants")
def assignable_grants(amo_code:str,work_id:str,db:Session=Depends(get_db),
                      user=Depends(get_current_active_user)):
    amo=_staff(db,amo_code,user)
    work=_work(db,amo,work_id)
    if _role(user)!=MANAGERS[work["work_type"]]:
        raise HTTPException(403,"Responsible Maintenance Manager required")
    return {"items":_all(db,"""SELECT g.id,g.role_code,g.capabilities_json,g.object_scope_json,
        i.email FROM external_tenant_grants g
        JOIN external_organization_memberships m ON m.id=g.membership_id
        JOIN external_identities i ON i.id=m.identity_id
        WHERE g.amo_id=:amo AND g.tenant_provider_id=:provider AND g.status='ACTIVE'
          AND m.status='ACTIVE' AND i.status='ACTIVE'
        ORDER BY i.email""",amo=amo,provider=work["provider_id"])}


@staff_router.post("",status_code=201)
def create_work(amo_code:str,payload:NewWork,db:Session=Depends(get_db),
                user=Depends(get_current_active_user)):
    amo=_staff(db,amo_code,user)
    if _role(user)!=MANAGERS[payload.work_type]:
        raise HTTPException(403,"The appointed Maintenance Manager for this work type must initiate contracted work")
    coordinator=_one(db,"""SELECT id,CAST(role AS TEXT) AS role FROM users
        WHERE id=:id AND amo_id=:amo AND is_active=TRUE""",
        id=payload.technical_coordinator_id,amo=amo)
    if not coordinator or coordinator["role"] not in {
        *MANAGERS.values(),"PLANNING_ENGINEER","PRODUCTION_ENGINEER","MAINTENANCE_SUPERVISOR",
        "CERTIFYING_ENGINEER"}:
        raise HTTPException(422,"Designated coordinator must be an active authorized maintenance employee of this AMO")
    provider=_one(db,"""SELECT id FROM external_tenant_providers
       WHERE amo_id=:amo AND supplier_id=:supplier AND id=:provider""",
       amo=amo,supplier=payload.supplier_id,provider=payload.provider_id)
    if not provider:raise HTTPException(422,"Provider must belong to the selected tenant supplier")
    if payload.data_manual_id:
        published=_one(db,"""SELECT r.id FROM manuals m
            JOIN manual_tenants t ON t.id=m.tenant_id AND t.amo_id=:amo
            JOIN manual_revisions r ON r.manual_id=m.id AND r.id=m.current_published_rev_id
            WHERE m.id=:manual AND r.id=:revision AND r.status_enum='PUBLISHED'
              AND r.published_at IS NOT NULL AND r.source_storage_path IS NOT NULL""",
            amo=amo,manual=payload.data_manual_id,revision=payload.data_revision_id)
        if not published:raise HTTPException(409,"Technical data must be current controlled DMS revision")
    if payload.purchase_order_id:
        po=_one(db,"""SELECT id FROM procurement_purchase_orders WHERE
            id=:po AND amo_id=:amo AND supplier_id=:supplier""",
            po=payload.purchase_order_id,amo=amo,supplier=payload.supplier_id)
        if not po:raise HTTPException(422,"Linked commercial PO belongs to another supplier or AMO")
    work_id=str(uuid4())
    db.execute(text("""INSERT INTO external_contracted_work
      (id,amo_id,supplier_id,provider_id,work_number,work_type,work_title,function,scope_text,
       site_code,scope_id,contract_id,purchase_order_id,internal_work_reference,
       technical_coordinator_id,asset_kind,registration,part_number,serial_number,asset_description,
       defect,data_reference,data_revision,inspections_json,required_release,requirements_json,created_by)
       VALUES(:id,:amo,:supplier,:provider,:number,:type,:title,:function,:scope,:site,:scope_id,
       :contract,:po,:work_ref,:coordinator,:asset,:registration,:part,:serial,:asset_desc,:defect,
       :data,:revision,CAST(:inspections AS JSON),:release,CAST(:requirements AS JSON),:actor)"""),
       {"id":work_id,"amo":amo,"supplier":payload.supplier_id,"provider":payload.provider_id,
        "number":payload.work_number,"type":payload.work_type,"title":payload.work_title,
        "function":payload.function,"scope":payload.scope_text,"site":payload.site_code,
        "scope_id":payload.scope_id,"contract":payload.contract_id,"po":payload.purchase_order_id,
        "work_ref":payload.internal_work_reference,"coordinator":payload.technical_coordinator_id,
        "asset":payload.asset_kind,"registration":payload.registration,"part":payload.part_number,
        "serial":payload.serial_number,"asset_desc":payload.asset_description,"defect":payload.defect,
        "data":payload.data_reference,"revision":payload.data_revision,
        "inspections":json.dumps(payload.inspections),"release":payload.required_release,
        "requirements":json.dumps({**payload.requirements,"data_manual_id":payload.data_manual_id,
          "data_revision_id":payload.data_revision_id}),"actor":str(user.id)})
    for index,criterion in enumerate(payload.inspections):
        db.execute(text("""INSERT INTO external_contracted_inspection_checks
          (id,amo_id,work_id,criterion_index,criterion)
          VALUES(:id,:amo,:work,:index,:criterion)"""),
          {"id":str(uuid4()),"amo":amo,"work":work_id,"index":index,"criterion":criterion})
    work=_work(db,amo,work_id)
    _event(db,work,"CREATE","Maintenance Manager initiated defined contracted function",
           staff=str(user.id),target="DRAFT")
    db.commit()
    return {"id":work_id,"status":"DRAFT","certification_authorized":False}


@staff_router.get("/{work_id}")
def staff_detail(amo_code:str,work_id:str,db:Session=Depends(get_db),user=Depends(get_current_active_user)):
    amo=_staff(db,amo_code,user)
    work=_work(db,amo,work_id)
    allowed=[]
    for action in NEXT.get(work["status"],{}):
        role=_role(user)
        if action in QUALITY_ACTIONS and role in QUALITY:allowed.append(action)
        elif action in STORES_ACTIONS and role in STORES:allowed.append(action)
        elif action in MANAGER_ACTIONS and role==MANAGERS[work["work_type"]]:
            allowed.append(action)
    return {**_details(db,work),"allowed_actions":allowed,
            "can_review_inspections":_role(user)==MANAGERS[work["work_type"]]}


def _transition(db,work,payload,*,user=None,identity=None):
    # Every retry key belongs to one exact work order, actor, action and request.
    # A committed first attempt must be returned without applying a second event.
    replay=_one(db,"""SELECT id,action,to_state,actor_user_id,actor_identity_id,reason
         FROM external_contracted_work_events
         WHERE amo_id=:amo AND work_id=:work AND idempotency_key=:retry""",
         amo=work["amo_id"],work=work["id"],retry=payload.idempotency_key)
    if replay:
        expected_actor=str(user.id) if user is not None else None
        if (replay["action"]!=payload.action or replay["reason"]!=payload.reason
            or replay["actor_user_id"]!=expected_actor
            or replay["actor_identity_id"]!=identity):
            raise HTTPException(409,"Idempotency key has already been used for a different decision")
        return {"id":work["id"],"status":replay["to_state"],
            "version":work["version"],"retry":True,"maintenance_release_issued":False}
    if work["version"]!=payload.expected_version:
        raise HTTPException(409,{"code":"STALE_WORK_ORDER","current_version":work["version"],"state":work["status"]})
    action=payload.action
    if action not in NEXT.get(work["status"],{}):
        raise HTTPException(409,{"code":"INVALID_WORK_TRANSITION","state":work["status"],"action":action})
    role=_role(user) if user is not None else None
    if identity is not None:
        if action not in PROVIDER_ACTIONS:
            raise HTTPException(403,"Contractor cannot authorize technical, Quality or custody decisions")
    elif action in QUALITY_ACTIONS:
        if role not in QUALITY:raise HTTPException(403,"Appointed Quality Manager decision required")
    elif action in STORES_ACTIONS:
        if role not in STORES:raise HTTPException(403,"Internal Stores or Quality Inspector receipt required")
    elif action in MANAGER_ACTIONS:
        if role!=MANAGERS[work["work_type"]]:
            raise HTTPException(403,"Appointed responsible Maintenance Manager decision required")
    else:
        raise HTTPException(403,"Unauthorized transition")
    if action=="SCOPE_APPROVED":
        _technical_requirements(work)
    if action in {"QUALITY_ACCEPTED","AUTHORIZE","DISPATCH","PROVIDER_ACCEPT","START",
                  "COMPLETE","SUBMIT_RELEASE","RETURN","TECHNICAL_ACCEPT","CLOSE","RESUME","RESUME_REWORK"}:
        _eligibility(db,work)
    if action in {"AUTHORIZE","DISPATCH"}:
        # A one-off component repair order is an alternative only when the
        # manager recorded a specific same-order MOPM 2.20 instruction.
        repair_ref=str((work["requirements_json"] or {}).get("governed_repair_order_reference") or "").strip()
        if repair_ref and (work["work_type"] not in {"WORKSHOP","SPECIALISED"}
                           or len(repair_ref)<6 or repair_ref==str(work["purchase_order_id"] or "")):
            raise HTTPException(409,"A controlled component repair order must be specifically referenced")
        reference=_one(db,"""SELECT id FROM work_orders WHERE amo_id=:amo
           AND (wo_number=:reference OR work_package_ref=:reference) LIMIT 1""",
           amo=work["amo_id"],reference=work["internal_work_reference"])
        if not reference and not repair_ref:
            raise HTTPException(409,"A canonical work package or governed MOPM 2.20 repair order reference is required")
    if action=="DISPATCH" and work["purchase_order_id"]:
        po=_one(db,"""SELECT sent_at FROM procurement_purchase_orders
          WHERE amo_id=:amo AND supplier_id=:supplier AND id=:po""",
          amo=work["amo_id"],supplier=work["supplier_id"],po=work["purchase_order_id"])
        if not po or not po["sent_at"]:
            raise HTTPException(409,"Linked commercial PO must be issued before dispatch; it does not authorize maintenance")
    if action in {"COMPLETE","SUBMIT_RELEASE","RETURN","TECHNICAL_ACCEPT","CLOSE"}:
        pending=_one(db,"""SELECT id FROM external_contracted_additional_work
          WHERE amo_id=:amo AND work_id=:id AND state='REQUESTED' LIMIT 1""",
          amo=work["amo_id"],id=work["id"])
        if pending:raise HTTPException(409,"Additional maintenance awaits written technical disposition")
    if action in {"SUBMIT_RELEASE","TECHNICAL_ACCEPT","CLOSE"}:
        blockers=_closure_blockers(db,work)
        required={"MAINTENANCE_RELEASE"} if action=="SUBMIT_RELEASE" else set()
        if action in {"TECHNICAL_ACCEPT","CLOSE"}:required={"MAINTENANCE_RELEASE","WORK_RECORD","TEST_RESULT"}
        if required and any(f"Accepted governed {kind.lower()} evidence missing" in blockers for kind in required):
            raise HTTPException(409,"DMS-retained and Quality-reviewed contracted maintenance evidence is missing")
        if action in {"TECHNICAL_ACCEPT","CLOSE"} and blockers:
            raise HTTPException(409,{"code":"TECHNICAL_CLOSURE_BLOCKED","items":blockers})
    if action=="CLOSE" and not work["accepted_by"]:
        raise HTTPException(409,"Maintenance Manager technical acceptance must precede closure")
    previous=work["status"]
    target=NEXT[previous][action]
    if target=="__PREVIOUS__":
        held=_one(db,"""SELECT from_state FROM external_contracted_work_events
          WHERE amo_id=:amo AND work_id=:id AND action='HOLD'
          ORDER BY created_at DESC,id DESC LIMIT 1""",amo=work["amo_id"],id=work["id"])
        target=held["from_state"] if held and held["from_state"] in NEXT else "TECHNICAL_SCOPE_REVIEW"
        if target in {"CANCELLED","CLOSED","ON_HOLD"}:target="TECHNICAL_SCOPE_REVIEW"
    updates=["status=:target","version=version+1","updated_at=NOW()"]
    bind=dict(amo=work["amo_id"],id=work["id"],target=target,version=payload.expected_version)
    if action=="SCOPE_APPROVED":
        updates+=["technical_review_by=:actor","technical_review_at=NOW()"];bind["actor"]=str(user.id)
    if action=="QUALITY_ACCEPTED":
        updates+=["quality_checked_by=:actor","quality_checked_at=NOW()"];bind["actor"]=str(user.id)
    if action=="AUTHORIZE":
        if not work["technical_review_by"] or not work["quality_checked_by"]:
            raise HTTPException(409,"Written technical review and independent Quality verification required")
        updates+=["authorized_by=:actor","authorized_at=NOW()"];bind["actor"]=str(user.id)
    if action=="TECHNICAL_ACCEPT":
        updates+=["accepted_by=:actor","accepted_at=NOW()"];bind["actor"]=str(user.id)
    if action in {"REWORK","REJECT","REOPEN"}:
        # A return/reopen invalidates previously accepted inspection/test reviews.
        db.execute(text("""UPDATE external_contracted_inspection_checks
          SET result='PENDING',submission_id=NULL,review_reason=NULL,
              reviewed_by_user_id=NULL,reviewed_at=NULL
          WHERE amo_id=:amo AND work_id=:id"""),
          {"amo":work["amo_id"],"id":work["id"]})
    if action in {"CLOSE","CANCEL"}:
        updates+=["closure_reason=:reason"];bind["reason"]=payload.reason
        if action=="CLOSE":updates+=["closed_at=NOW()"]
    db.execute(text(f"""UPDATE external_contracted_work SET {','.join(updates)}
       WHERE amo_id=:amo AND id=:id AND version=:version"""),bind)
    _event(db,work,action,payload.reason,staff=str(user.id) if user else None,
           identity=identity,previous=previous,target=target,details=payload.details,
           retry=payload.idempotency_key)
    delegated_phase8=(action in {"DISPATCH","REWORK","HOLD","RESUME"}
        and inspect(db.get_bind()).has_table("external_provider_alert_jobs"))
    if user is not None and not delegated_phase8 and action in {"AUTHORIZE","DISPATCH","REWORK","REJECT","HOLD","RESUME","CANCEL","CLOSE"}:
        _notify_assigned_members(db,work,f"Contracted work: {action.replace('_',' ').title()}",
            f"{work['work_number']}: {payload.reason}")
    db.commit()
    return {"id":work["id"],"status":target,"version":payload.expected_version+1,
            "maintenance_release_issued":False}


@staff_router.post("/{work_id}/transitions")
def staff_transition(amo_code:str,work_id:str,payload:Transition,db:Session=Depends(get_db),
                     user=Depends(get_current_active_user)):
    amo=_staff(db,amo_code,user)
    return _transition(db,_work(db,amo,work_id,lock=True),payload,user=user)


@partner_router.get("")
def partner_queue(tenant_slug:str,request:Request,db:Session=Depends(get_db)):
    session,ctx=_partner(db,request,tenant_slug)
    ids=partner._allowed(session,"contracted_work")
    return {"items":[dict(row) for row in db.execute(
        text("""SELECT id,work_number,work_title,site_code,status,work_type,updated_at
            FROM external_contracted_work WHERE amo_id=:amo AND supplier_id=:supplier
            AND provider_id=:provider AND authorized_at IS NOT NULL AND id IN :ids ORDER BY updated_at DESC""")
        .bindparams(bindparam("ids",expanding=True)),
        {**ctx,"ids":sorted(ids)}).mappings()],
        "authority":"The contracted AMO certifies solely under its own applicable approval"}


@partner_router.get("/{work_id}/technical-data")
def download_work_data(tenant_slug:str,work_id:str,request:Request,db:Session=Depends(get_db)):
    session,ctx=_partner(db,request,tenant_slug)
    if "document.read" not in (session["capabilities_json"] or []):
        raise HTTPException(403,"Controlled technical-data read privilege is required")
    work=_partner_work(db,session,ctx,work_id)
    if work["status"] in {"DRAFT","TECHNICAL_SCOPE_REVIEW","QUALIFICATION_AGREEMENT_CHECK",
                          "AWAITING_AUTHORIZATION","CANCELLED"}:
        raise HTTPException(403,"Technical data cannot be released before authorization")
    if work["status"] not in {"CLOSED"}:
        _eligibility(db,work)
    req=work["requirements_json"] or {}
    manual_id,revision_id=req.get("data_manual_id"),req.get("data_revision_id")
    if not manual_id or not revision_id:
        raise HTTPException(404,"The work cites approved technical data but has no released DMS original")
    partner._require_object(session,"documents",str(manual_id))
    row=_one(db,"""SELECT r.id,r.source_filename,r.source_mime_type,r.source_storage_path,r.source_sha256
       FROM manuals m JOIN manual_tenants t ON t.id=m.tenant_id AND t.amo_id=:amo
       JOIN manual_revisions r ON r.manual_id=m.id
       WHERE m.id=:manual AND r.id=:revision AND r.published_at IS NOT NULL
        AND r.status_enum IN ('PUBLISHED','SUPERSEDED','ARCHIVED')""",
       amo=ctx["amo"],manual=manual_id,revision=revision_id)
    if not row or not row["source_storage_path"]:
        raise HTTPException(404,"Controlled technical-data original is not accessible")
    try:
        filepath=storage.materialize(row["source_storage_path"],expected_sha256=row["source_sha256"])
    except (OSError,ValueError,RuntimeError) as exc:
        raise HTTPException(409,"Controlled technical-data source is unavailable") from exc
    _event(db,work,"TECHNICAL_DATA_READ","Exact granted maintenance-data original accessed",
        identity=ctx["person"],details={"manual_id":manual_id,"revision_id":revision_id})
    db.commit()
    return FileResponse(filepath,filename=Path(row["source_filename"] or "maintenance-data.pdf").name,
         media_type=row["source_mime_type"] or "application/octet-stream",
         headers={"Cache-Control":"private, no-store","X-Content-Type-Options":"nosniff"})


@partner_router.post("/{work_id}/custody/{item_id}/acknowledge")
def acknowledge_provider_custody(tenant_slug:str,work_id:str,item_id:str,payload:ProviderNote,
                                 request:Request,db:Session=Depends(get_db)):
    session,ctx=_partner(db,request,tenant_slug,True)
    work=_partner_work(db,session,ctx,work_id,lock=True)
    replay=_one(db,"""SELECT action,reason,actor_identity_id,details_json
       FROM external_contracted_work_events
       WHERE amo_id=:amo AND work_id=:work AND idempotency_key=:retry""",
       amo=ctx["amo"],work=work_id,retry=payload.idempotency_key)
    if replay:
        if (replay["action"],replay["reason"],replay["actor_identity_id"]) != ("PROPERTY_RECEIVED_BY_PROVIDER",payload.message,ctx["person"]):
            raise HTTPException(409,"Idempotency key reused for a different custody receipt")
        if str((replay["details_json"] or {}).get("item_id")) != item_id:
            raise HTTPException(409,"Receipt retry does not match the original custody item")
        return {"id":item_id,"state":"RECEIVED_BY_PROVIDER","retry":True,"stores_release":False}
    if work["version"]!=payload.expected_version:raise HTTPException(409,"Work changed; reload custody")
    if work["status"] in {"CANCELLED","CLOSED","DRAFT","TECHNICAL_SCOPE_REVIEW","QUALIFICATION_AGREEMENT_CHECK","AWAITING_AUTHORIZATION","AUTHORIZED"}:
        raise HTTPException(409,"Provider receipt is not permitted at this work stage")
    if payload.kind!="PROGRESS":raise HTTPException(422,"Receipt acknowledgement is distinct from a technical finding")
    item=_one(db,"""SELECT id,state,stores_reference FROM external_contracted_custody
      WHERE amo_id=:amo AND work_id=:work AND id=:item FOR UPDATE""",
      amo=ctx["amo"],work=work_id,item=item_id)
    if not item or item["state"]!="DISPATCHED":raise HTTPException(409,"Stores must dispatch the item before provider custody receipt")
    if len(payload.message.strip())<8:raise HTTPException(422,"Record receiving condition and count")
    db.execute(text("""UPDATE external_contracted_custody
       SET state='RECEIVED_BY_PROVIDER',updated_at=NOW()
       WHERE amo_id=:amo AND work_id=:work AND id=:item"""),
       {"amo":ctx["amo"],"work":work_id,"item":item_id})
    _event(db,work,"PROPERTY_RECEIVED_BY_PROVIDER",payload.message,
      identity=ctx["person"],details={"item_id":item_id,"stores_reference":item["stores_reference"]},
      retry=payload.idempotency_key)
    db.commit()
    return {"id":item_id,"state":"RECEIVED_BY_PROVIDER","stores_release":False,"quality_release":False}


@partner_router.get("/{work_id}")
def partner_detail(tenant_slug:str,work_id:str,request:Request,db:Session=Depends(get_db)):
    session,ctx=_partner(db,request,tenant_slug)
    result=_details(db,_partner_work(db,session,ctx,work_id))
    # Never serialize the raw maintenance ORM/SQL record to an external session:
    # it includes internal identities, unreleased approvals and financial links.
    allowed_fields={"id","work_number","work_title","work_type","function","scope_text",
        "site_code","status","version","internal_work_reference","asset_kind",
        "registration","part_number","serial_number","asset_description","defect",
        "data_reference","data_revision","inspections_json","required_release",
        "contract_id","purchase_order_id","requirements_json","authorized_at","updated_at"}
    result["work"]={k:v for k,v in result["work"].items() if k in allowed_fields}
    for item in result["additional_work"]:
        for field in ("requested_by_identity_id","reviewed_by_user_id"):
            item.pop(field,None)
    for item in result["inspection_checks"]:
        item.pop("reviewed_by_user_id",None)
    result["history"]=[{k:v for k,v in item.items() if k not in
        {"actor_user_id","actor_identity_id"}} for item in result["history"]]
    return result


@partner_router.post("/{work_id}/transitions")
def partner_transition(tenant_slug:str,work_id:str,payload:Transition,request:Request,
                       db:Session=Depends(get_db)):
    session,ctx=_partner(db,request,tenant_slug,True)
    return _transition(db,_partner_work(db,session,ctx,work_id,lock=True),
                       payload,identity=ctx["person"])


@partner_router.post("/{work_id}/communications",status_code=201)
def provider_communication(tenant_slug:str,work_id:str,payload:ProviderNote,
                           request:Request,db:Session=Depends(get_db)):
    session,ctx=_partner(db,request,tenant_slug,True)
    work=_partner_work(db,session,ctx,work_id,lock=True)
    replay=_one(db,"""SELECT action,reason,actor_identity_id FROM external_contracted_work_events
       WHERE amo_id=:amo AND work_id=:work AND idempotency_key=:retry""",
       amo=ctx["amo"],work=work_id,retry=payload.idempotency_key)
    if replay:
        if (replay["action"],replay["reason"],replay["actor_identity_id"]) != (payload.kind,payload.message,ctx["person"]):
            raise HTTPException(409,"Idempotency key reused for a different communication")
        return {"recorded":True,"status":work["status"],"retry":True}
    if work["version"]!=payload.expected_version:raise HTTPException(409,"Work order changed; refresh")
    if work["status"] not in {"DISPATCHED","PROVIDER_ACCEPTED","IN_PROGRESS","WORK_COMPLETED",
        "RELEASE_SUBMITTED","REWORK_REQUIRED","ON_HOLD"}:
        raise HTTPException(409,"Technical correspondence is unavailable at this stage")
    _event(db,work,payload.kind,payload.message,identity=ctx["person"],
           details={"message":payload.message},retry=payload.idempotency_key)
    db.commit()
    return {"recorded":True,"status":work["status"]}


@partner_router.post("/{work_id}/additional-work",status_code=201)
def request_additional(tenant_slug:str,work_id:str,payload:AdditionalRequest,request:Request,
                       db:Session=Depends(get_db)):
    session,ctx=_partner(db,request,tenant_slug,True)
    work=_partner_work(db,session,ctx,work_id,lock=True)
    replay=_one(db,"""SELECT action,reason,actor_identity_id,details_json
       FROM external_contracted_work_events
       WHERE amo_id=:amo AND work_id=:work AND idempotency_key=:retry""",
       amo=ctx["amo"],work=work_id,retry=payload.idempotency_key)
    if replay:
        if (replay["action"],replay["reason"],replay["actor_identity_id"]) != ("ADDITIONAL_WORK_REQUESTED",payload.description,ctx["person"]):
            raise HTTPException(409,"Idempotency key reused for a different request")
        info=replay["details_json"] or {}
        return {"id":info.get("additional_work_id"),"status":"AWAITING_SAFARILINK_TECHNICAL_DECISION",
                "work_status":work["status"],"retry":True}
    if work["status"]!="IN_PROGRESS":
        raise HTTPException(409,"Additional work may be requested only during authorized maintenance")
    _eligibility(db,work)
    outstanding=_one(db,"""SELECT id FROM external_contracted_additional_work
      WHERE amo_id=:amo AND work_id=:id AND state='REQUESTED'""",amo=ctx["amo"],id=work_id)
    if outstanding:raise HTTPException(409,"Resolve outstanding technical variation first")
    rid=str(uuid4())
    db.execute(text("""INSERT INTO external_contracted_additional_work
       (id,amo_id,work_id,description,technical_data,commercial_reference,requested_by_identity_id)
       VALUES(:id,:amo,:work,:description,:data,:commercial,:identity)"""),
       dict(id=rid,amo=ctx["amo"],work=work_id,description=payload.description,
            data=payload.technical_data,commercial=payload.commercial_reference,identity=ctx["person"]))
    db.execute(text("""UPDATE external_contracted_work SET status='ADDITIONAL_WORK_REQUESTED',
       version=version+1,updated_at=NOW() WHERE amo_id=:amo AND id=:work"""),
       {"amo":ctx["amo"],"work":work_id})
    _event(db,work,"ADDITIONAL_WORK_REQUESTED",payload.description,identity=ctx["person"],
           previous="IN_PROGRESS",target="ADDITIONAL_WORK_REQUESTED",
           details={"additional_work_id":rid,"commercial_reference":payload.commercial_reference},
           retry=payload.idempotency_key)
    db.commit()
    return {"id":rid,"status":"AWAITING_SAFARILINK_TECHNICAL_DECISION","work_status":"ADDITIONAL_WORK_REQUESTED"}


@staff_router.post("/{work_id}/additional-work/{request_id}/decision")
def decide_additional(amo_code:str,work_id:str,request_id:str,payload:AdditionalDecision,
                      db:Session=Depends(get_db),user=Depends(get_current_active_user)):
    amo=_staff(db,amo_code,user)
    work=_work(db,amo,work_id,lock=True)
    if _role(user)!=MANAGERS[work["work_type"]]:raise HTTPException(403,"Responsible Maintenance Manager approval required")
    if work["status"]!="ADDITIONAL_WORK_REQUESTED":
        raise HTTPException(409,"Additional work is not awaiting a technical decision")
    variation=_one(db,"""SELECT * FROM external_contracted_additional_work
       WHERE amo_id=:amo AND work_id=:work AND id=:id FOR UPDATE""",
       amo=amo,work=work_id,id=request_id)
    if not variation or variation["state"]!="REQUESTED":raise HTTPException(409,"Request already decided")
    if payload.decision=="APPROVED":
        _eligibility(db,work)
        if not payload.amended_work_reference or not payload.technical_data:
            raise HTTPException(422,"Amended controlled work instruction and approved data are required")
        if variation["commercial_reference"] and not payload.commercial_variation_reference:
            raise HTTPException(409,"Commercial variation must be separately recorded before work authorization")
        req=work["requirements_json"] or {}
        if req.get("operator_approval_required") and not payload.operator_approval_reference:
            raise HTTPException(409,"Operator additional-work authorization is required")
        if req.get("authority_approval_required") and not payload.authority_approval_reference:
            raise HTTPException(409,"Authority additional-work authorization is required")
    db.execute(text("""UPDATE external_contracted_additional_work SET
      state=:state,reviewed_by_user_id=:actor,decision_reason=:reason,
      technical_data=:data,operator_approval_reference=:operator,
      approved_amended_work_reference=:amended,
      approved_commercial_variation_reference=:commercial,
      authority_approval_reference=:authority,updated_at=NOW()
      WHERE amo_id=:amo AND work_id=:work AND id=:id"""),
       dict(state=payload.decision,actor=str(user.id),reason=payload.reason,
            data=payload.technical_data,operator=payload.operator_approval_reference,
            amended=payload.amended_work_reference,commercial=payload.commercial_variation_reference,
            authority=payload.authority_approval_reference,amo=amo,work=work_id,id=request_id))
    db.execute(text("""UPDATE external_contracted_work SET status='IN_PROGRESS',version=version+1,
      updated_at=NOW() WHERE amo_id=:amo AND id=:work"""),{"amo":amo,"work":work_id})
    _event(db,work,"ADDITIONAL_WORK_"+payload.decision,payload.reason,staff=str(user.id),
      previous="ADDITIONAL_WORK_REQUESTED",target="IN_PROGRESS",
      details={"request_id":request_id,"amended_work_reference":payload.amended_work_reference,
        "technical_data":payload.technical_data,
        "commercial_variation_reference":payload.commercial_variation_reference,
        "operator_approval_reference":payload.operator_approval_reference,
        "authority_approval_reference":payload.authority_approval_reference})
    _notify_assigned_members(db,work,"Contracted maintenance additional work: "+payload.decision,
        f"{work['work_number']} — {payload.reason}. Only approved amended instructions authorize extra work.")
    db.commit()
    return {"id":request_id,"decision":payload.decision,"may_perform_additional_work":payload.decision=="APPROVED"}


@staff_router.post("/{work_id}/custody",status_code=201)
def register_custody(amo_code:str,work_id:str,payload:CustodyNew,db:Session=Depends(get_db),
                     user=Depends(get_current_active_user)):
    amo=_staff(db,amo_code,user)
    if _role(user) not in STORES:raise HTTPException(403,"Stores custody registration required")
    work=_work(db,amo,work_id,lock=True)
    if work["status"] in {"CLOSED","CANCELLED"}:raise HTTPException(409,"Work is closed")
    item_id=str(uuid4())
    db.execute(text("""INSERT INTO external_contracted_custody
      (id,amo_id,work_id,item_type,description,part_number,serial_batch,quantity,uom,condition,stores_reference)
      VALUES(:id,:amo,:work,:type,:description,:part,:serial,:quantity,:uom,:condition,:reference)"""),
      dict(id=item_id,amo=amo,work=work_id,type=payload.item_type,description=payload.description,
           part=payload.part_number,serial=payload.serial_batch,quantity=payload.quantity,
           uom=payload.uom,condition=payload.condition,reference=payload.stores_reference))
    _event(db,work,"PROPERTY_REGISTERED","Stores registered externally controlled property",
      staff=str(user.id),details={"item_id":item_id,"stores_reference":payload.stores_reference})
    db.commit()
    return {"id":item_id,"state":"REGISTERED","stores_decision_unchanged":True}


@staff_router.post("/{work_id}/custody/{item_id}")
def update_custody(amo_code:str,work_id:str,item_id:str,payload:CustodyUpdate,
                   db:Session=Depends(get_db),user=Depends(get_current_active_user)):
    amo=_staff(db,amo_code,user)
    work=_work(db,amo,work_id,lock=True)
    if _role(user) not in STORES:raise HTTPException(403,"Stores custody decision required")
    item=_one(db,"""SELECT state FROM external_contracted_custody
       WHERE amo_id=:amo AND work_id=:work AND id=:id FOR UPDATE""",amo=amo,work=work_id,id=item_id)
    if not item:raise HTTPException(404,"Custody record unavailable")
    states={"REGISTERED":{"DISPATCHED"},"DISPATCHED":{"RECEIVED_BY_PROVIDER","DISCREPANCY"},
            "RECEIVED_BY_PROVIDER":{"CONSUMED","RETURNED","DISCREPANCY"},
            "CONSUMED":{"RECONCILED","DISCREPANCY"},
            "RETURNED":{"RECONCILED","DISCREPANCY"},"DISCREPANCY":{"RECONCILED"}}
    if payload.state not in states.get(item["state"],set()):
        raise HTTPException(409,"Custody transition is invalid")
    if payload.state=="RECONCILED" and item["state"]=="DISCREPANCY" and not payload.discrepancy:
        raise HTTPException(422,"Record disposition of lost or discrepant property before reconciling")
    db.execute(text("""UPDATE external_contracted_custody SET state=:state,
       discrepancy=:note,updated_at=NOW() WHERE amo_id=:amo AND work_id=:work AND id=:id"""),
       dict(state=payload.state,note=payload.discrepancy,amo=amo,work=work_id,id=item_id))
    _event(db,work,"PROPERTY_"+payload.state,payload.reason,staff=str(user.id),
      details={"item_id":item_id,"from":item["state"],"to":payload.state,
               "stores_reference":item.get("stores_reference")})
    db.commit()
    return {"id":item_id,"state":payload.state,"canonical_stores_updated":False}


@staff_router.post("/{work_id}/inspections/{criterion_index}")
def review_inspection_criterion(amo_code:str,work_id:str,criterion_index:int,
                                payload:InspectionDecision,db:Session=Depends(get_db),
                                user=Depends(get_current_active_user)):
    amo=_staff(db,amo_code,user)
    work=_work(db,amo,work_id,lock=True)
    if _role(user)!=MANAGERS[work["work_type"]]:
        raise HTTPException(403,"The responsible Maintenance Manager must review technical inspection evidence")
    if work["version"]!=payload.expected_version:
        raise HTTPException(409,"Work changed; reload the current inspection evidence")
    if not work["authorized_at"] or work["status"] in {"CLOSED","CANCELLED","DRAFT","ON_HOLD"}:
        raise HTTPException(409,"Inspection evidence review is not permitted at this stage")
    criterion=_one(db,"""SELECT criterion FROM external_contracted_inspection_checks
      WHERE amo_id=:amo AND work_id=:work AND criterion_index=:index FOR UPDATE""",
      amo=amo,work=work_id,index=criterion_index)
    if not criterion:raise HTTPException(404,"Inspection/test criterion not registered")
    submission_id=payload.source_submission_id if payload.result=="ACCEPTED" else None
    if payload.result=="ACCEPTED":
        if not submission_id:raise HTTPException(422,"Choose a specific DMS-retained and Quality-verified test/inspection original")
        source=_one(db,"""SELECT s.id FROM external_partner_evidence_submissions s
          JOIN document_retention_dispositions d ON d.tenant_id=s.amo_id
            AND d.id=s.dms_retention_id AND d.status!='DISPOSED'
          JOIN quality_external_provider_evidence q ON q.id=s.qms_evidence_id
            AND q.amo_id=s.amo_id AND q.supplier_id=:supplier
            AND q.status='VERIFIED' AND (q.valid_until IS NULL OR q.valid_until>=CURRENT_DATE)
          WHERE s.amo_id=:amo AND s.tenant_provider_id=:provider AND s.id=:submission
            AND s.related_kind='CONTRACTED_WORK' AND s.related_id=:work
            AND s.status='ACCEPTED' AND s.dms_evidence_asset_id IS NOT NULL
            AND s.evidence_type IN ('INSPECTION_REPORT','TEST_RESULT')""",
            amo=amo,provider=work["provider_id"],supplier=work["supplier_id"],
            submission=submission_id,work=work_id)
        if not source:raise HTTPException(409,"The chosen original is not a current, independently verified inspection/test report")
    db.execute(text("""UPDATE external_contracted_inspection_checks
      SET result=:result,submission_id=:submission,review_reason=:reason,
          reviewed_by_user_id=:actor,reviewed_at=NOW()
      WHERE amo_id=:amo AND work_id=:work AND criterion_index=:index"""),
      {"result":payload.result,"submission":submission_id,"reason":payload.reason,
       "actor":str(user.id),"amo":amo,"work":work_id,"index":criterion_index})
    db.execute(text("""UPDATE external_contracted_work SET version=version+1,updated_at=NOW()
      WHERE amo_id=:amo AND id=:work"""),{"amo":amo,"work":work_id})
    _event(db,work,"INSPECTION_"+payload.result,payload.reason,staff=str(user.id),
      details={"criterion_index":criterion_index,"criterion":criterion["criterion"],
               "source_submission_id":submission_id})
    db.commit()
    return {"criterion_index":criterion_index,"result":payload.result,"version":work["version"]+1,
            "maintenance_release_issued":False}


@staff_router.post("/{work_id}/evidence",status_code=201)
def attach_verified_evidence(amo_code:str,work_id:str,payload:LinkEvidence,db:Session=Depends(get_db),
                             user=Depends(get_current_active_user)):
    amo=_staff(db,amo_code,user)
    if _role(user) not in {"DOCUMENT_CONTROL_OFFICER","QUALITY_MANAGER","QUALITY_OFFICER",
                           *MANAGERS.values()}:
        raise HTTPException(403,"Governed document review role required")
    if payload.category not in EVIDENCE_CATEGORIES:raise HTTPException(422,"Invalid maintenance evidence category")
    work=_work(db,amo,work_id,lock=True)
    if work["status"] in {"CLOSED","CANCELLED"}:raise HTTPException(409,"Cannot change evidence of closed work")
    submission=_one(db,"""SELECT s.id FROM external_partner_evidence_submissions s
      JOIN external_tenant_providers p ON p.amo_id=s.amo_id AND p.id=s.tenant_provider_id
      JOIN document_retention_dispositions d ON d.tenant_id=s.amo_id
        AND d.id=s.dms_retention_id AND d.status!='DISPOSED'
      JOIN quality_external_provider_evidence q ON q.id=s.qms_evidence_id
        AND q.amo_id=s.amo_id AND q.supplier_id=p.supplier_id
        AND q.status='VERIFIED' AND (q.valid_until IS NULL OR q.valid_until>=CURRENT_DATE)
      WHERE s.amo_id=:amo AND p.id=:provider AND p.supplier_id=:supplier
        AND s.id=:submission AND s.status='ACCEPTED' AND s.dms_evidence_asset_id IS NOT NULL
        AND s.related_kind='CONTRACTED_WORK' AND s.related_id=:work""",
       amo=amo,provider=work["provider_id"],supplier=work["supplier_id"],
       submission=payload.source_submission_id,work=work_id)
    if not submission:raise HTTPException(409,"Select an accepted DMS-retained original scoped to this work")
    existing=_one(db,"""SELECT id FROM external_contracted_evidence_links
      WHERE amo_id=:amo AND work_id=:work AND source_submission_id=:submission""",
      amo=amo,work=work_id,submission=submission["id"])
    if existing:return {"id":existing["id"],"retry":True}
    link=str(uuid4())
    db.execute(text("""INSERT INTO external_contracted_evidence_links
      (id,amo_id,work_id,source_submission_id,category,linked_by_user_id)
      VALUES(:id,:amo,:work,:submission,:category,:actor)"""),
      dict(id=link,amo=amo,work=work_id,submission=submission["id"],
           category=payload.category,actor=str(user.id)))
    _event(db,work,"EVIDENCE_LINKED","Accepted controlled original linked to work order",
      staff=str(user.id),details={"evidence":submission["id"],"category":payload.category})
    db.commit()
    return {"id":link,"status":"LINKED","maintenance_release_issued":False}


@staff_router.post("/{work_id}/grant/{grant_id}")
def assign_partner_member(amo_code:str,work_id:str,grant_id:str,db:Session=Depends(get_db),
                          user=Depends(get_current_active_user)):
    amo=_staff(db,amo_code,user)
    work=_work(db,amo,work_id,lock=True)
    if _role(user)!=MANAGERS[work["work_type"]]:
        raise HTTPException(403,"Responsible Maintenance Manager must assign a contractor representative")
    grant=_one(db,"""SELECT g.id,g.object_scope_json,g.capabilities_json
        FROM external_tenant_grants g JOIN external_tenant_providers p ON p.amo_id=g.amo_id AND p.id=g.tenant_provider_id
        JOIN external_organization_memberships m ON m.id=g.membership_id AND m.status='ACTIVE'
        JOIN external_identities i ON i.id=m.identity_id AND i.status='ACTIVE'
        WHERE g.amo_id=:amo AND g.id=:id AND g.status='ACTIVE'
          AND g.tenant_provider_id=:provider AND p.supplier_id=:supplier""",
        amo=amo,id=grant_id,provider=work["provider_id"],supplier=work["supplier_id"])
    if not grant or "task.read" not in (grant["capabilities_json"] or []):
        raise HTTPException(403,"Selected active grant lacks assigned provider access")
    current=grant["object_scope_json"] or {}
    current["contracted_work"]=sorted(set(str(x) for x in current.get("contracted_work",[]))|{str(work_id)})
    db.execute(text("""UPDATE external_tenant_grants SET object_scope_json=CAST(:scopes AS JSON)
        WHERE amo_id=:amo AND id=:id"""),dict(scopes=json.dumps(current),amo=amo,id=grant_id))
    _event(db,work,"MEMBER_ASSIGNED","Responsible manager assigned member to contracted work",
       staff=str(user.id),details={"grant_id":grant_id})
    _notify_assigned_members(db,work,"Maintenance work assigned",
        f"{work['work_number']} has been explicitly assigned to your account.")
    db.commit()
    return {"granted":True,"work_id":work_id,"grant_id":grant_id}
