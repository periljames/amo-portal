"""Phase 4: QMS-controlled qualification with canonical supplier/evaluation/audit/CAR links.

Provider principals cannot call these staff routes. QMS approval remains the
existing independent Procurement/Quality evaluation decision, never a parallel
authorization invented by this router.
"""
from __future__ import annotations

import json
from datetime import date, timedelta, datetime, timezone
from uuid import uuid4, UUID
from typing import Any, Literal

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel, Field
from sqlalchemy import text, bindparam
from sqlalchemy.orm import Session

from amodb.apps.accounts.tenant_authority import is_tenant_admin

from amodb.apps.audit import services as audit_services
from amodb.apps.accounts import models as account_models
from amodb.apps.procurement import service as procurement_service
from amodb.apps.procurement import schemas as procurement_schemas
from amodb.apps.procurement import supplier_governance_service as evaluation_service
from amodb.apps.quality.tenant_security import set_postgres_tenant_context
from amodb.database import get_db
from amodb.security import get_current_active_user

router = APIRouter(prefix="/api/maintenance/{amo_code}/quality/external-qualification",
                   tags=["QMS external provider qualification"])
QUALITY = {"QUALITY_MANAGER", "QUALITY_OFFICER"}
MAINTENANCE = {"BASE_MAINTENANCE_MANAGER", "LINE_MAINTENANCE_MANAGER", "WORKSHOP_MANAGER"}
SAFETY = {"SAFETY_MANAGER"}
BASE_CHECKS = [
    "LEGAL_IDENTITY", "CLASSIFICATION_AND_APPLICABILITY", "SCOPE_CAPABILITY",
    "REGULATORY_APPROVAL", "FACILITIES_AND_SITES", "CONTRACT_REQUIREMENTS",
    "SAFETY_MOC", "QMS_EVALUATION", "QUALIFYING_AUDIT_OR_REVIEW",
    "TECHNICAL_ACCEPTANCE", "QUALITY_CONCLUSION",
]


def uid(): return str(uuid4())


def _role(user):
    return str(getattr(user.role, "value", user.role))


def _tenant(db: Session, amo_code: str, user):
    amo = procurement_service.resolve_tenant_amo_id(db, amo_code=amo_code,
                                                     current_user=user)
    set_postgres_tenant_context(db, amo_id=amo, user_id=str(user.id))
    return amo


def _require(user, allowed: set[str]):
    if not is_tenant_admin(user) and _role(user) not in allowed:
        raise HTTPException(403, "This decision requires the appointed department authority")


def _one(db, sql: str, **values):
    row = db.execute(text(sql), values).mappings().first()
    return dict(row) if row else None


def _all(db, sql: str, **values):
    return [dict(x) for x in db.execute(text(sql), values).mappings().all()]


def _supplier(db, amo, supplier):
    row = _one(db, """SELECT id, supplier_code, legal_name, status, risk_level
         FROM procurement_suppliers WHERE amo_id=:amo AND id=:supplier""",
         amo=amo, supplier=supplier)
    if not row: raise HTTPException(404, "Tenant supplier not found")
    return row


def _case(db, amo, case_id, lock=False):
    row = _one(db, """SELECT * FROM quality_provider_qualification_cases
        WHERE amo_id=:amo AND id=:id""" + (" FOR UPDATE" if lock else ""),
        amo=amo, id=case_id)
    if not row: raise HTTPException(404, "Qualification case not found")
    return row


def _record(db, amo, supplier, user, action, details, case_id=None):
    db.execute(text("""INSERT INTO quality_provider_qualification_events
       (id,amo_id,supplier_id,case_id,action,actor_user_id,details_json)
       VALUES(:id,:amo,:supplier,:case,:action,:actor,CAST(:details AS JSON))"""),
       {"id":uid(),"amo":amo,"supplier":supplier,"case":case_id,
        "action":action,"actor":str(user.id),"details":json.dumps(details,default=str)})


def _case_details(db, row):
    checks = _all(db, """SELECT requirement_key,status,evidence_reference,
        approval_reference,expires_on,conclusion,verified_at
        FROM quality_provider_qualification_checks
        WHERE amo_id=:amo AND case_id=:case ORDER BY requirement_key""",
        amo=row["amo_id"],case=row["id"])
    audits = _all(db, """SELECT s.id,s.audit_id,s.kind,s.risk_level,s.due_on,s.outcome,
         a.audit_ref,a.title,CAST(a.status AS TEXT) audit_status,a.actual_end
         FROM quality_provider_surveillance s
         JOIN qms_audits a ON a.amo_id=s.amo_id AND CAST(a.id AS TEXT)=s.audit_id
         WHERE s.amo_id=:amo AND s.supplier_id=:supplier
         ORDER BY s.created_at DESC LIMIT 30""",
         amo=row["amo_id"],supplier=row["supplier_id"])
    return {**row,"checks":checks,"audits":audits}


def _policy(db, amo, category):
    row = _one(db,"""SELECT * FROM quality_provider_qualification_policies
         WHERE amo_id=:amo AND category=:category""",amo=amo,category=category)
    if not row: raise HTTPException(409, "Quality Manager must approve a category-specific qualification policy first")
    return row


class PolicyWrite(BaseModel):
    questionnaire: list[dict[str, Any]] = Field(default_factory=list, max_length=80)
    required_checks: list[str] = Field(default_factory=lambda: list(BASE_CHECKS), min_length=1, max_length=50)
    surveillance_days: int = Field(default=365,ge=30,le=365)
    evaluation_template_id: str | None = Field(default=None,max_length=36)
    initial_audit_required: bool = False
    authority_required: bool = False
    safety_assessment_required: bool = False
    manual_references: list[str] = Field(default_factory=list,max_length=30)
    reason: str = Field(min_length=8,max_length=1000)
    expected_revision: int | None = Field(default=None,ge=0)


@router.get("/policies")
def policies(amo_code:str, db:Session=Depends(get_db),
             user=Depends(get_current_active_user)):
    amo=_tenant(db,amo_code,user)
    _require(user,QUALITY|MAINTENANCE|SAFETY)
    return {"items":_all(db,"""SELECT category,revision,evaluation_template_id,questionnaire_json,
        required_checks_json,surveillance_days,initial_audit_required,
        authority_required,safety_assessment_required,manual_references_json,updated_at
        FROM quality_provider_qualification_policies WHERE amo_id=:amo
        ORDER BY category""",amo=amo),
        "default_annual_audit":True, "maximum_surveillance_days":365, "policy_reference":"MOPM 3.13"}


@router.put("/policies/{category}")
def configure_policy(amo_code:str,category:str,payload:PolicyWrite,
                     db:Session=Depends(get_db),user=Depends(get_current_active_user)):
    _require(user,{"QUALITY_MANAGER"})
    amo=_tenant(db,amo_code,user)
    category=category.strip().upper()
    if not 2<=len(category)<=64 or any(x not in "ABCDEFGHIJKLMNOPQRSTUVWXYZ0123456789_-" for x in category):
        raise HTTPException(422,"Invalid provider category")
    current=db.execute(text("""SELECT revision FROM quality_provider_qualification_policies
      WHERE amo_id=:amo AND category=:category""" +
      (" FOR UPDATE" if db.get_bind().dialect.name=="postgresql" else "")),
      {"amo":amo,"category":category}).scalar()
    if payload.expected_revision is not None and payload.expected_revision!=int(current or 0):
        raise HTTPException(409,"Qualification policy changed; refresh the policy before saving")
    keys=[str(x.get("key","")).strip().upper() for x in payload.questionnaire]
    if any(not k or len(k)>80 for k in keys) or len(keys)!=len(set(keys)):
        raise HTTPException(422,"Questionnaire keys must be unique and nonempty")
    required=[x.strip().upper() for x in payload.required_checks]
    if len(set(required))!=len(required) or not set(BASE_CHECKS).issubset(set(required)):
        raise HTTPException(422,"Cannot remove baseline qualification checks")
    if payload.evaluation_template_id:
        tmpl=_one(db,"""SELECT id FROM procurement_supplier_evaluation_templates
           WHERE amo_id=:amo AND id=:id AND status='ACTIVE'""",
           amo=amo,id=payload.evaluation_template_id)
        if not tmpl:raise HTTPException(409,"Category template must be an active canonical QMS evaluation template")
    for item in payload.questionnaire:
        if str(item.get("kind","TEXT")) not in {"TEXT","YES_NO","NUMBER","DATE"}:
            raise HTTPException(422,"Unsupported questionnaire answer type")
    db.execute(text("""INSERT INTO quality_provider_qualification_policies
       (amo_id,category,revision,evaluation_template_id,questionnaire_json,
        required_checks_json,surveillance_days,initial_audit_required,authority_required,safety_assessment_required,manual_references_json,updated_by_user_id)
       VALUES(:amo,:category,1,:template,CAST(:questions AS JSON),CAST(:checks AS JSON),
        :days,:initial_audit,:authority,:safety,CAST(:manuals AS JSON),:actor)
       ON CONFLICT(amo_id,category) DO UPDATE
       SET revision=quality_provider_qualification_policies.revision+1,
           evaluation_template_id=EXCLUDED.evaluation_template_id,
           questionnaire_json=EXCLUDED.questionnaire_json,
           required_checks_json=EXCLUDED.required_checks_json,
           surveillance_days=EXCLUDED.surveillance_days,
            initial_audit_required=EXCLUDED.initial_audit_required,
            authority_required=EXCLUDED.authority_required,
            safety_assessment_required=EXCLUDED.safety_assessment_required,
           manual_references_json=EXCLUDED.manual_references_json,
           updated_by_user_id=EXCLUDED.updated_by_user_id,updated_at=NOW()"""),
       {"amo":amo,"category":category,"questions":json.dumps(payload.questionnaire),
        "checks":json.dumps(required),"template":payload.evaluation_template_id,
        "days":payload.surveillance_days,"initial_audit":payload.initial_audit_required,
        "authority":payload.authority_required,"safety":payload.safety_assessment_required,
        "manuals":json.dumps(payload.manual_references),"actor":str(user.id)})
    # Tenant-wide category policy audit is attributable; zero is an administrative
    # supplier sentinel, not an issued supplier approval.
    audit_services.log_event(db,amo_id=amo,actor_user_id=str(user.id),
        entity_type="external_provider_policy",entity_id=category,
        action="category_policy_updated",
        before={"revision":current},
        after={"revision":int(current or 0)+1,
               "required_checks":required,"surveillance_days":payload.surveillance_days},
        correlation_id=str(uuid4()),
        metadata={"reason":payload.reason},critical=True)
    db.commit()
    return {"category":category,"status":"CONFIGURED","annual_audit_required":payload.surveillance_days==365}


class CreateCase(BaseModel):
    supplier_id: int = Field(ge=1)
    category: str = Field(min_length=2,max_length=64)
    case_kind: Literal["INITIAL","RENEWAL","REQUALIFICATION","REINSTATEMENT"]="INITIAL"
    risk_level: Literal["LOW","MEDIUM","HIGH","CRITICAL"]="MEDIUM"
    reason: str = Field(min_length=8,max_length=2000)


@router.get("/queue")
def queue(amo_code:str, status:str|None=Query(default=None,max_length=28),
          search:str=Query("",max_length=100),limit:int=Query(40,ge=1,le=100),
          offset:int=Query(0,ge=0,le=10000),
          db:Session=Depends(get_db),user=Depends(get_current_active_user)):
    _require(user,QUALITY|MAINTENANCE|SAFETY)
    amo=_tenant(db,amo_code,user)
    rows=_all(db,"""SELECT q.id,q.supplier_id,q.category,q.case_kind,q.status,q.version,
        q.risk_level,q.next_review_due_on,q.audit_id,q.evaluation_id,q.technical_state,
        q.safety_state,q.authority_state,q.created_at,s.legal_name,s.supplier_code,
        CAST(s.status AS TEXT) supplier_status
        FROM quality_provider_qualification_cases q
        JOIN procurement_suppliers s ON s.amo_id=q.amo_id AND s.id=q.supplier_id
        WHERE q.amo_id=:amo AND (:status IS NULL OR q.status=:status)
        AND lower(s.legal_name) LIKE :search
        ORDER BY q.created_at DESC,q.id DESC LIMIT :limit OFFSET :offset""",
        amo=amo,status=status,search="%"+search.strip().lower()+"%",limit=limit,offset=offset)
    return {"items":rows,"limit":limit,"offset":offset,"has_more":len(rows)==limit}


@router.post("/cases",status_code=201)
def create_case(amo_code:str,payload:CreateCase,db:Session=Depends(get_db),
                user=Depends(get_current_active_user)):
    _require(user,QUALITY)
    amo=_tenant(db,amo_code,user);_supplier(db,amo,payload.supplier_id)
    policy=_policy(db,amo,payload.category.upper())
    current=_one(db,"""SELECT id FROM quality_provider_qualification_cases
        WHERE amo_id=:amo AND supplier_id=:supplier
        AND status IN ('DRAFT','RETURNED','SUBMITTED','IN_REVIEW','READY') LIMIT 1""",
        amo=amo,supplier=payload.supplier_id)
    if current:raise HTTPException(409,"Complete or return the existing open qualification case first")
    case_id=uid()
    snapshot={"questionnaire":policy["questionnaire_json"],
              "required_checks":policy["required_checks_json"],
              "evaluation_template_id":policy["evaluation_template_id"],
              "surveillance_days":policy["surveillance_days"],
              "initial_audit_required":policy["initial_audit_required"],
              "authority_required":policy["authority_required"],
              "safety_assessment_required":policy["safety_assessment_required"],
              "manual_references":policy["manual_references_json"]}
    db.execute(text("""INSERT INTO quality_provider_qualification_cases
      (id,amo_id,supplier_id,category,case_kind,policy_revision,policy_snapshot_json,
       evaluation_template_id,answers_json,technical_scope_json,risk_level,created_by_user_id)
      VALUES(:id,:amo,:supplier,:category,:kind,:revision,CAST(:policy AS JSON),
      :template,CAST('{}' AS JSON),CAST('[]' AS JSON),:risk,:actor)"""),
      {"id":case_id,"amo":amo,"supplier":payload.supplier_id,"category":payload.category.upper(),
       "kind":payload.case_kind,"revision":policy["revision"],
       "policy":json.dumps(snapshot),"template":policy["evaluation_template_id"],
       "risk":payload.risk_level,"actor":str(user.id)})
    for key in snapshot["required_checks"]:
        db.execute(text("""INSERT INTO quality_provider_qualification_checks
          (id,amo_id,case_id,requirement_key) VALUES(:id,:amo,:case,:key)"""),
          {"id":uid(),"amo":amo,"case":case_id,"key":key})
    _record(db,amo,payload.supplier_id,user,"QUALIFICATION_OPENED",
            {"kind":payload.case_kind,"category":payload.category,"reason":payload.reason},case_id)
    db.commit()
    return _case_details(db,_case(db,amo,case_id))


@router.get("/cases/{case_id}")
def read_case(amo_code:str,case_id:str,db:Session=Depends(get_db),
              user=Depends(get_current_active_user)):
    _require(user,QUALITY|MAINTENANCE|SAFETY)
    amo=_tenant(db,amo_code,user)
    return _case_details(db,_case(db,amo,case_id))


class CaseAnswer(BaseModel):
    expected_version:int=Field(ge=1)
    answers:dict[str,Any]=Field(default_factory=dict)
    evaluation_id:str|None=Field(default=None,max_length=64)
    conclusion:str=Field(min_length=8,max_length=2000)


@router.patch("/cases/{case_id}")
def update_case(amo_code:str,case_id:str,payload:CaseAnswer,db:Session=Depends(get_db),
                user=Depends(get_current_active_user)):
    _require(user,QUALITY)
    amo=_tenant(db,amo_code,user);row=_case(db,amo,case_id,True)
    if row["status"] not in {"DRAFT","RETURNED","SUBMITTED","IN_REVIEW"}:
        raise HTTPException(409,"Case can no longer be edited")
    if int(row["version"])!=payload.expected_version:
        raise HTTPException(409,"Stale qualification case version")
    keys={q["key"] for q in row["policy_snapshot_json"].get("questionnaire",[])}
    if set(payload.answers)-keys:raise HTTPException(422,"Unknown questionnaire response key")
    if payload.evaluation_id:
        evaluation=_one(db,"""SELECT id,template_id FROM procurement_supplier_evaluations
            WHERE amo_id=:amo AND supplier_id=:supplier AND id=:evaluation""",
            amo=amo,supplier=row["supplier_id"],evaluation=payload.evaluation_id)
        if not evaluation:raise HTTPException(404,"Governed supplier evaluation is unavailable")
        if (row["evaluation_template_id"] and
            str(evaluation["template_id"])!=str(row["evaluation_template_id"])):
            raise HTTPException(409,"Evaluation uses a different category-specific template")
    db.execute(text("""UPDATE quality_provider_qualification_cases
       SET answers_json=CAST(:answers AS JSON),evaluation_id=:evaluation,
       conclusion=:note,status='IN_REVIEW',version=version+1,updated_at=NOW()
       WHERE amo_id=:amo AND id=:id"""),
       {"answers":json.dumps(payload.answers),"evaluation":payload.evaluation_id,
        "note":payload.conclusion,"amo":amo,"id":case_id})
    _record(db,amo,row["supplier_id"],user,"QUALIFICATION_UPDATED",
            {"version":payload.expected_version,"evaluation_id":payload.evaluation_id},case_id)
    db.commit()
    return _case_details(db,_case(db,amo,case_id))


class CheckDecision(BaseModel):
    status:Literal["VERIFIED","REJECTED","NOT_REQUIRED"]
    evidence_reference:str|None=Field(default=None,max_length=255)
    approval_reference:str|None=Field(default=None,max_length=180)
    expires_on:date|None=None
    conclusion:str=Field(min_length=8,max_length=2000)


@router.post("/cases/{case_id}/checks/{requirement_key}")
def verify_check(amo_code:str,case_id:str,requirement_key:str,payload:CheckDecision,
                 db:Session=Depends(get_db),user=Depends(get_current_active_user)):
    _require(user,QUALITY)
    amo=_tenant(db,amo_code,user);row=_case(db,amo,case_id,True)
    if row["status"] in {"APPROVED","CONDITIONALLY_APPROVED","REJECTED"}:
        raise HTTPException(409,"Final case cannot be changed")
    key=requirement_key.upper()
    check=_one(db,"""SELECT id FROM quality_provider_qualification_checks
        WHERE amo_id=:amo AND case_id=:case AND requirement_key=:key""",
        amo=amo,case=case_id,key=key)
    if not check:raise HTTPException(404,"Requirement not part of the approved policy snapshot")
    if payload.status=="VERIFIED":
        if not payload.evidence_reference and not payload.approval_reference:
            raise HTTPException(422,"Verified gate requires an attributable evidence or approval reference")
        if payload.expires_on and payload.expires_on<date.today():
            raise HTTPException(409,"Expired evidence cannot support current approval")
    required_verified={"LEGAL_IDENTITY","CLASSIFICATION_AND_APPLICABILITY",
        "SCOPE_CAPABILITY","QUALIFYING_AUDIT_OR_REVIEW","QMS_EVALUATION",
        "TECHNICAL_ACCEPTANCE","QUALITY_CONCLUSION"}
    if payload.status=="NOT_REQUIRED" and key in required_verified:
        raise HTTPException(409,"Mandatory evidence/qualification gates cannot be waived")
    if key in {"REGULATORY_APPROVAL","SAFETY_MOC"} and payload.status=="NOT_REQUIRED":
        raise HTTPException(409,"Use the appointed departmental gate to determine applicability")
    if key=="REGULATORY_APPROVAL" and payload.status=="VERIFIED" and not payload.approval_reference:
        raise HTTPException(422,"Regulatory approval verification requires an authority reference")
    # Documentary checks must resolve to evidence already independently verified
    # in the existing canonical QMS evidence register, not a free-text file ref.
    documented={"LEGAL_IDENTITY","CLASSIFICATION_AND_APPLICABILITY","SCOPE_CAPABILITY",
                "FACILITIES_AND_SITES","CONTRACT_REQUIREMENTS","QUALIFYING_AUDIT_OR_REVIEW"}
    if key in documented and payload.status=="VERIFIED":
        if not payload.evidence_reference:
            raise HTTPException(422,"Documentary verification requires existing QMS evidence")
        evidence=_one(db,"""SELECT id FROM quality_external_provider_evidence
            WHERE amo_id=:amo AND supplier_id=:supplier
            AND (id=:ref OR source_id=:ref)
            AND status='VERIFIED'
            AND (valid_from IS NULL OR valid_from<=CURRENT_DATE)
            AND (valid_until IS NULL OR valid_until>=CURRENT_DATE) LIMIT 1""",
            amo=amo,supplier=row["supplier_id"],ref=payload.evidence_reference)
        if not evidence:
            raise HTTPException(409,"Verification reference is not current Quality-verified evidence for this provider")
    db.execute(text("""UPDATE quality_provider_qualification_checks
       SET status=:status,evidence_reference=:evidence,approval_reference=:approval,
           expires_on=:expires,conclusion=:note,verified_by_user_id=:actor,verified_at=NOW()
       WHERE id=:id AND amo_id=:amo"""),
       {"status":payload.status,"evidence":payload.evidence_reference,
        "approval":payload.approval_reference,"expires":payload.expires_on,
        "note":payload.conclusion,"actor":str(user.id),"id":check["id"],"amo":amo})
    _record(db,amo,row["supplier_id"],user,"QUALIFICATION_GATE_REVIEWED",
            {"key":key,"decision":payload.status,"note":payload.conclusion},case_id)
    db.commit()
    return {"status":payload.status,"requirement_key":key}


class DomainDecision(BaseModel):
    state:Literal["ACCEPTED","REJECTED","NOT_REQUIRED","VERIFIED"]
    reason:str=Field(min_length=8,max_length=2000)
    reference:str|None=Field(default=None,max_length=180)
    expires_on:date|None=None
    technical_scope:list[dict[str,str]]=Field(default_factory=list,max_length=100)


@router.post("/cases/{case_id}/review/{domain}")
def domain_review(amo_code:str,case_id:str,domain:Literal["technical","safety","authority"],
                  payload:DomainDecision,db:Session=Depends(get_db),
                  user=Depends(get_current_active_user)):
    allowed={"technical":MAINTENANCE,"safety":SAFETY,"authority":{"QUALITY_MANAGER"}}
    _require(user,allowed[domain])
    amo=_tenant(db,amo_code,user);row=_case(db,amo,case_id,True)
    if row["status"] in {"APPROVED","CONDITIONALLY_APPROVED","REJECTED"}:
        raise HTTPException(409,"Final qualification already decided")
    valid=({"ACCEPTED","REJECTED"} if domain=="technical" else
           {"ACCEPTED","REJECTED","NOT_REQUIRED"} if domain=="safety" else
           {"VERIFIED","REJECTED","NOT_REQUIRED"})
    if payload.state not in valid:raise HTTPException(422,"Invalid departmental decision")
    if domain=="authority" and payload.state=="VERIFIED" and (
        not payload.reference or (payload.expires_on and payload.expires_on<date.today())):
        raise HTTPException(422,"Current regulatory authorization requires reference and valid expiry")
    if domain=="authority" and payload.state=="NOT_REQUIRED" and row["policy_snapshot_json"].get("authority_required"):
        raise HTTPException(409,"This category requires verified State/Authority approval; revise the governed policy instead")
    if domain=="safety" and payload.state=="NOT_REQUIRED" and row["policy_snapshot_json"].get("safety_assessment_required"):
        raise HTTPException(409,"This category requires appointed Safety Manager assessment")
    if domain=="safety" and payload.state=="ACCEPTED" and not payload.reference:
        raise HTTPException(422,"Safety Manager acceptance requires the SMS/MOC assessment reference")
    if domain=="authority" and payload.state=="VERIFIED":
        verified=_one(db,"""SELECT id,valid_until FROM external_provider_certificates
            WHERE amo_id=:amo AND supplier_id=:supplier
            AND certificate_number=:reference AND verification_state='VERIFIED'
            AND (valid_from IS NULL OR valid_from<=CURRENT_DATE)
            AND (valid_until IS NULL OR valid_until>=CURRENT_DATE)
            LIMIT 1""",amo=amo,supplier=row["supplier_id"],reference=payload.reference)
        if not verified:
            raise HTTPException(409,"Referenced authority certificate is not Quality-verified and current")
        if payload.expires_on and verified["valid_until"] and payload.expires_on>verified["valid_until"]:
            raise HTTPException(409,"Claimed Authority expiry exceeds independently verified certificate")
    if domain=="technical" and payload.state=="ACCEPTED" and not payload.technical_scope:
        raise HTTPException(422,"Technical acceptance must define exact proposed scope")
    fields={"technical":"technical_state","safety":"safety_state","authority":"authority_state"}
    column=fields[domain]
    updates={column:payload.state}
    if domain=="technical":
        updates["technical_actor_id"]=str(user.id)
        updates["technical_scope_json"]=json.dumps(payload.technical_scope)
    if domain=="safety":updates["safety_actor_id"]=str(user.id)
    if domain=="authority":
        updates["authority_reference"]=payload.reference
        updates["authority_expires_on"]=payload.expires_on
    assignments=", ".join(f"{key}=:"+key for key in updates)
    if domain=="technical":assignments=assignments.replace("technical_scope_json=:technical_scope_json",
                                                              "technical_scope_json=CAST(:technical_scope_json AS JSON)")
    db.execute(text(f"""UPDATE quality_provider_qualification_cases SET {assignments},
        status='IN_REVIEW',version=version+1,updated_at=NOW()
        WHERE amo_id=:amo AND id=:id"""),{**updates,"amo":amo,"id":case_id})
    gate={"technical":"TECHNICAL_ACCEPTANCE","safety":"SAFETY_MOC",
          "authority":"REGULATORY_APPROVAL"}[domain]
    db.execute(text("""UPDATE quality_provider_qualification_checks SET
       status=:status,approval_reference=:reference,conclusion=:reason,
       verified_by_user_id=:actor,verified_at=NOW()
       WHERE amo_id=:amo AND case_id=:case AND requirement_key=:key"""),
       {"status":"VERIFIED" if payload.state in {"ACCEPTED","VERIFIED"} else
        "NOT_REQUIRED" if payload.state=="NOT_REQUIRED" else "REJECTED",
        "reference":payload.reference,"reason":payload.reason,"actor":str(user.id),
        "amo":amo,"case":case_id,"key":gate})
    _record(db,amo,row["supplier_id"],user,"DEPARTMENT_REVIEW",
            {"domain":domain,"state":payload.state,"reason":payload.reason,
             "reference":payload.reference},case_id)
    db.commit()
    return _case_details(db,_case(db,amo,case_id))


class AuditLink(BaseModel):
    audit_id:str=Field(min_length=36,max_length=36)
    kind:Literal["INITIAL","RECURRENT","FOLLOW_UP","REQUALIFICATION"]="INITIAL"
    due_on:date|None=None
    reason:str=Field(min_length=8,max_length=2000)


@router.post("/cases/{case_id}/audit")
def link_audit(amo_code:str,case_id:str,payload:AuditLink,db:Session=Depends(get_db),
               user=Depends(get_current_active_user)):
    _require(user,QUALITY)
    amo=_tenant(db,amo_code,user);row=_case(db,amo,case_id,True)
    if row["status"] in {"APPROVED","CONDITIONALLY_APPROVED","REJECTED"}:raise HTTPException(409,"Open requalification for a new audit")
    try: UUID(payload.audit_id)
    except ValueError as exc:raise HTTPException(422,"Invalid existing QMS audit identifier") from exc
    audit=_one(db,"""SELECT id,audit_ref,title,CAST(kind AS TEXT) kind,
        lead_auditor_user_id,CAST(status AS TEXT) status
        FROM qms_audits WHERE amo_id=:amo AND CAST(id AS TEXT)=:audit""",
        amo=amo,audit=payload.audit_id)
    if not audit:raise HTTPException(404,"Existing tenant QMS audit not found")
    if str(audit["kind"]).upper() not in {"EXTERNAL","THIRD_PARTY"}:
        raise HTTPException(409,"Linked QMS audit must be classified as external")
    if audit["lead_auditor_user_id"] and str(audit["lead_auditor_user_id"])==str(user.id):
        raise HTTPException(403,"Auditor cannot administer approval of their own audit")
    existing=_one(db,"""SELECT supplier_id FROM quality_provider_surveillance
        WHERE amo_id=:amo AND audit_id=:audit""",amo=amo,audit=payload.audit_id)
    if existing and existing["supplier_id"]!=row["supplier_id"]:
        raise HTTPException(409,"Audit occurrence is already linked to another provider")
    db.execute(text("""INSERT INTO quality_provider_surveillance
       (id,amo_id,supplier_id,case_id,audit_id,kind,risk_level,due_on,created_by_user_id)
       VALUES(:id,:amo,:supplier,:case,:audit,:kind,:risk,:due,:actor)
       ON CONFLICT(amo_id,supplier_id,audit_id) DO NOTHING"""),
       {"id":uid(),"amo":amo,"supplier":row["supplier_id"],"case":case_id,
        "audit":payload.audit_id,"kind":payload.kind,"risk":row["risk_level"],
        "due":payload.due_on,"actor":str(user.id)})
    db.execute(text("""UPDATE quality_provider_qualification_cases
       SET audit_id=:audit,status='IN_REVIEW',version=version+1 WHERE amo_id=:amo AND id=:id"""),
       {"audit":payload.audit_id,"amo":amo,"id":case_id})
    _record(db,amo,row["supplier_id"],user,"EXISTING_QMS_AUDIT_LINKED",
            {"audit_ref":audit["audit_ref"],"reason":payload.reason},case_id)
    db.commit()
    return _case_details(db,_case(db,amo,case_id))


class FinalDecision(BaseModel):
    action:Literal["APPROVE","CONDITIONALLY_APPROVE","REJECT","RETURN"]
    expected_version:int=Field(ge=1)
    reason:str=Field(min_length=12,max_length=2000)


def _requirements(db,amo,row):
    policy=row["policy_snapshot_json"]
    keys=list(policy.get("required_checks",[]))
    checks=_all(db,"""SELECT requirement_key,status,expires_on FROM
        quality_provider_qualification_checks WHERE amo_id=:amo AND case_id=:case""",
        amo=amo,case=row["id"])
    found={x["requirement_key"]:x for x in checks}
    blockers=[key for key in keys if key not in found or found[key]["status"] not in
              {"VERIFIED","NOT_REQUIRED"} or (
                found[key]["expires_on"] and found[key]["expires_on"]<date.today())]
    questions=policy.get("questionnaire",[])
    for q in questions:
        if q.get("required") and not row["answers_json"].get(q.get("key")):
            blockers.append("QUESTION:"+str(q.get("key")))
    if row["technical_state"]!="ACCEPTED":blockers.append("TECHNICAL_OWNER")
    if row["safety_state"] not in {"ACCEPTED","NOT_REQUIRED"}:blockers.append("SAFETY")
    if policy.get("safety_assessment_required") and row["safety_state"]!="ACCEPTED":
        blockers.append("CATEGORY_REQUIRES_SAFETY_ASSESSMENT")
    if row["authority_state"] not in {"VERIFIED","NOT_REQUIRED"}:blockers.append("REGULATORY_APPLICABILITY")
    if policy.get("authority_required") and row["authority_state"]!="VERIFIED":
        blockers.append("CATEGORY_REQUIRES_REGULATORY_APPROVAL")
    if row["authority_state"]=="VERIFIED":
        certificate=_one(db,"""SELECT id FROM external_provider_certificates
            WHERE amo_id=:amo AND supplier_id=:supplier
            AND certificate_number=:reference AND verification_state='VERIFIED'
            AND (valid_from IS NULL OR valid_from<=CURRENT_DATE)
            AND (valid_until IS NULL OR valid_until>=CURRENT_DATE) LIMIT 1""",
            amo=amo,supplier=row["supplier_id"],reference=row["authority_reference"])
        if not certificate or (
            row["authority_expires_on"] and row["authority_expires_on"]<date.today()):
            blockers.append("REGULATORY_CERTIFICATE_NO_LONGER_CURRENT")
    if not row["evaluation_template_id"]:
        blockers.append("CATEGORY_SCORING_TEMPLATE_REQUIRED")
    if not row["evaluation_id"]:blockers.append("GOVERNED_EVALUATION")
    else:
        evaluation=evaluation_service._latest_valid_evaluation(
            db,amo_id=amo,supplier_id=row["supplier_id"])
        if not evaluation or str(evaluation.id)!=str(row["evaluation_id"]):
            blockers.append("VALID_INDEPENDENT_EVALUATION")
        elif str(evaluation.template_id)!=str(row["evaluation_template_id"]):
            blockers.append("WRONG_CATEGORY_EVALUATION_TEMPLATE")
    if not row["technical_scope_json"]:blockers.append("APPROVED_TECHNICAL_SCOPE")
    else:
        approved=_all(db,"""SELECT category,site_code,product_family FROM
          procurement_supplier_approval_scopes WHERE amo_id=:amo
          AND supplier_id=:supplier AND qms_evaluation_id=:evaluation
          AND CAST(status AS TEXT) IN ('DRAFT','ACTIVE')""",
          amo=amo,supplier=row["supplier_id"],evaluation=row["evaluation_id"])
        keys={(str(x["category"]).upper(),str(x["site_code"]).upper(),
               str(x["product_family"]).upper()) for x in approved}
        for proposed in row["technical_scope_json"]:
            if not isinstance(proposed,dict):
                blockers.append("INVALID_TECHNICAL_SCOPE_FORMAT")
                continue
            key=(str(proposed.get("category","")).upper(),
                 str(proposed.get("site_code") or proposed.get("site") or "").upper(),
                 str(proposed.get("product_family","")).upper())
            if key not in keys:
                blockers.append("TECHNICAL_SCOPE_NOT_LINKED_TO_GOVERNED_EVALUATION")
                break
    contract_required=_one(db,"""SELECT contract_required FROM
        quality_external_provider_profiles WHERE amo_id=:amo AND supplier_id=:supplier""",
        amo=amo,supplier=row["supplier_id"])
    if contract_required and contract_required["contract_required"]:
        active_contract=_one(db,"""SELECT id FROM quality_external_provider_contracts
            WHERE amo_id=:amo AND supplier_id=:supplier AND status='ACTIVE'
            AND (effective_on IS NULL OR effective_on<=CURRENT_DATE)
            AND (expires_on IS NULL OR expires_on>=CURRENT_DATE) LIMIT 1""",
            amo=amo,supplier=row["supplier_id"])
        if not active_contract:blockers.append("CURRENT_QUALITY_CONTRACT_REQUIRED")

    if row["audit_id"]:
        audit=_one(db,"""SELECT actual_end,CAST(status AS TEXT) status FROM qms_audits
            WHERE amo_id=:amo AND CAST(id AS TEXT)=:id""",amo=amo,id=row["audit_id"])
        if not audit or not audit["actual_end"] or audit["status"]!="CLOSED":
            blockers.append("QMS_AUDIT_REQUIRES_CONTROLLED_CLOSEOUT")
        notice=_one(db,"""SELECT id FROM quality_audit_notices
            WHERE amo_id=:amo AND CAST(audit_id AS TEXT)=:id
            AND status='ACKNOWLEDGED' LIMIT 1""",amo=amo,id=row["audit_id"])
        if not notice:blockers.append("QMS_AUDIT_NOTICE_ACKNOWLEDGMENT_REQUIRED")
        open_cars=_one(db,"""SELECT count(*) AS n FROM quality_cars c
            JOIN qms_audit_findings f ON f.id=c.finding_id AND f.amo_id=c.amo_id
            WHERE c.amo_id=:amo AND CAST(f.audit_id AS TEXT)=:id
              AND c.closed_at IS NULL""",amo=amo,id=row["audit_id"])
        if open_cars and open_cars["n"]:blockers.append("AUDIT_CORRECTIVE_ACTION_OPEN")
    elif policy.get("initial_audit_required"):
        blockers.append("REQUIRED_INITIAL_QMS_AUDIT")
    return blockers


@router.post("/cases/{case_id}/decision")
def decide(amo_code:str,case_id:str,payload:FinalDecision,db:Session=Depends(get_db),
           user=Depends(get_current_active_user)):
    _require(user,{"QUALITY_MANAGER"})
    amo=_tenant(db,amo_code,user);row=_case(db,amo,case_id,True)
    previous=_one(db,"""SELECT CAST(status AS TEXT) status
        FROM procurement_suppliers WHERE amo_id=:amo AND id=:supplier""",
        amo=amo,supplier=row["supplier_id"])
    if row["status"] in {"APPROVED","CONDITIONALLY_APPROVED","REJECTED"}:
        raise HTTPException(409,"Case already finalized")
    if int(row["version"])!=payload.expected_version:
        raise HTTPException(409,"Stale qualification version")
    if payload.action in {"APPROVE","CONDITIONALLY_APPROVE"}:
        blockers=_requirements(db,amo,row)
        if row["audit_id"]:
            auditor=_one(db,"""SELECT lead_auditor_user_id,observer_auditor_user_id,
                assistant_auditor_user_id,supporting_auditor_user_ids
                FROM qms_audits WHERE amo_id=:amo AND CAST(id AS TEXT)=:audit""",
                amo=amo,audit=row["audit_id"])
            if auditor and str(user.id) in {
                str(auditor.get("lead_auditor_user_id")),
                str(auditor.get("observer_auditor_user_id")),
                str(auditor.get("assistant_auditor_user_id")),
                *[str(x) for x in (auditor.get("supporting_auditor_user_ids") or [])]
            }:
                blockers.append("AUDIT_TEAM_INDEPENDENCE_CONFLICT")
        if blockers:raise HTTPException(409,{"code":"QUALIFICATION_GATES_PENDING","blockers":blockers})
        # Marker is scoped to this SQLAlchemy transaction/request only.
        db.info["phase4_qualification_approval"]=(str(amo),int(row["supplier_id"]))
        try:
            evaluation_service.decide_supplier(
                db,amo_id=amo,supplier_id=row["supplier_id"],
                payload=procurement_schemas.SupplierDecision(
                    action=payload.action,reason=payload.reason),
                actor_user_id=str(user.id))
        finally:
            db.info.pop("phase4_qualification_approval",None)
        new_status="APPROVED" if payload.action=="APPROVE" else "CONDITIONALLY_APPROVED"
    elif payload.action=="REJECT":
        new_status="REJECTED"
        evaluation_service.decide_supplier(
            db,amo_id=amo,supplier_id=row["supplier_id"],
            payload=procurement_schemas.SupplierDecision(action="REJECT",reason=payload.reason),
            actor_user_id=str(user.id))
    else:new_status="RETURNED"
    policy=row["policy_snapshot_json"]
    interval=min(int(policy.get("surveillance_days") or 365),365)
    due=(date.today()+timedelta(days=int(interval))) if interval and new_status in {
        "APPROVED","CONDITIONALLY_APPROVED"} else None
    db.execute(text("""UPDATE quality_provider_qualification_cases
        SET status=:status,version=version+1,decided_at=NOW(),
        decided_by_user_id=:actor,conclusion=:reason,next_review_due_on=:due,
        updated_at=NOW() WHERE amo_id=:amo AND id=:id"""),
        {"status":new_status,"actor":str(user.id),"reason":payload.reason,
         "due":due,"amo":amo,"id":case_id})
    if due:
        db.execute(text("""UPDATE quality_external_provider_profiles
            SET next_review_due_on=:due,updated_at=NOW()
            WHERE amo_id=:amo AND supplier_id=:supplier"""),
            {"due":due,"amo":amo,"supplier":row["supplier_id"]})
    _record(db,amo,row["supplier_id"],user,"QUALIFICATION_"+new_status,
            {"reason":payload.reason,"evaluation_id":row["evaluation_id"],
             "audit_id":row["audit_id"],"policy_revision":row["policy_revision"],
             "next_due_on":due},case_id)
    _notify_provider_members(db,amo,row["supplier_id"],user,
        "Provider qualification review",
        "The AMO Quality Department has recorded the outcome of the qualification review.",
        "QUALIFICATION",case_id)
    if new_status in {"APPROVED","CONDITIONALLY_APPROVED","REJECTED"}:
        from .provider_oversight_events import record_status_snapshot
        record_status_snapshot(db,amo_id=amo,supplier_id=row["supplier_id"],
            actor_id=str(user.id),previous_status=(previous or {}).get("status"),
            current_status=new_status,action="QUALITY_QUALIFICATION_DECISION",
            source_reference=case_id)
    db.commit()
    return _case_details(db,_case(db,amo,case_id))


class RestrictionCreate(BaseModel):
    supplier_id:int=Field(ge=1)
    dimension:Literal["ORGANIZATION","SITE","CATEGORY","CAPABILITY","PRODUCT_FAMILY","FUNCTION","CONTRACT"]
    target_key:str=Field(min_length=1,max_length=180)
    effective_on:date
    ends_on:date|None=None
    reason:str=Field(min_length=12,max_length=2000)
    affected_records:list[str]=Field(default_factory=list,max_length=100)
    required_car_ids:list[str]=Field(default_factory=list,max_length=50)


@router.get("/restrictions")
def restrictions(amo_code:str,supplier_id:int|None=None,db:Session=Depends(get_db),
                 user=Depends(get_current_active_user)):
    _require(user,QUALITY|MAINTENANCE|SAFETY)
    amo=_tenant(db,amo_code,user)
    return {"items":_all(db,"""SELECT id,supplier_id,dimension,target_key,status,effective_on,
        ends_on,reason,affected_records_json,required_cars_json,reinstatement_case_id,
        imposed_by_user_id,lift_reason,created_at
        FROM quality_provider_restrictions WHERE amo_id=:amo
        AND (:supplier IS NULL OR supplier_id=:supplier)
        ORDER BY created_at DESC LIMIT 200""",amo=amo,supplier=supplier_id)}


@router.post("/restrictions",status_code=201)
def impose_restriction(amo_code:str,payload:RestrictionCreate,
                       db:Session=Depends(get_db),user=Depends(get_current_active_user)):
    _require(user,{"QUALITY_MANAGER"})
    amo=_tenant(db,amo_code,user);_supplier(db,amo,payload.supplier_id)
    if payload.ends_on and payload.ends_on<payload.effective_on:
        raise HTTPException(422,"Restriction end precedes effective date")
    if payload.dimension=="ORGANIZATION" and payload.target_key!="*":
        raise HTTPException(422,"Organization-wide restrictions use target '*'")
    if payload.dimension=="CONTRACT":
        contract=_one(db,"""SELECT id FROM quality_external_provider_contracts
          WHERE amo_id=:amo AND supplier_id=:supplier AND CAST(id AS TEXT)=:ref""",
          amo=amo,supplier=payload.supplier_id,ref=payload.target_key)
        if not contract:raise HTTPException(404,"Contract does not belong to supplier")
    for car_id in payload.required_car_ids:
        try: UUID(car_id)
        except ValueError as exc:raise HTTPException(422,"Invalid CAR reference") from exc
        linked=_one(db,"""SELECT c.id FROM quality_cars c
          JOIN qms_audit_findings f ON f.id=c.finding_id AND f.amo_id=c.amo_id
          JOIN quality_provider_surveillance s ON s.amo_id=f.amo_id
               AND s.audit_id=CAST(f.audit_id AS TEXT)
          WHERE c.amo_id=:amo AND s.supplier_id=:supplier AND CAST(c.id AS TEXT)=:car""",
          amo=amo,supplier=payload.supplier_id,car=car_id)
        if not linked:raise HTTPException(409,"CAR must belong to this provider's assigned QMS audit")
    ident=uid()
    db.execute(text("""INSERT INTO quality_provider_restrictions
       (id,amo_id,supplier_id,dimension,target_key,effective_on,ends_on,reason,
        affected_records_json,required_cars_json,imposed_by_user_id)
       VALUES(:id,:amo,:supplier,:dimension,:target,:effective,:ends,:reason,
        CAST(:records AS JSON),CAST(:cars AS JSON),:actor)"""),
       {"id":ident,"amo":amo,"supplier":payload.supplier_id,"dimension":payload.dimension,
        "target":payload.target_key,"effective":payload.effective_on,
        "ends":payload.ends_on,"reason":payload.reason,
        "records":json.dumps(payload.affected_records),"cars":json.dumps(payload.required_car_ids),
        "actor":str(user.id)})
    _record(db,amo,payload.supplier_id,user,"RESTRICTION_IMPOSED",
            payload.model_dump(mode="json"),None)
    _notify_provider_members(db,amo,payload.supplier_id,user,
        "Quality restriction issued",
        "Your AMO issued a Quality restriction on provider activity. View the scope in your Qualification workspace.",
        "RESTRICTION",ident)
    db.commit()
    return {"id":ident,"status":"ACTIVE","scope":payload.dimension,"target":payload.target_key}


class LiftRestriction(BaseModel):
    reinstatement_case_id:str=Field(min_length=36,max_length=36)
    reason:str=Field(min_length=12,max_length=2000)


@router.post("/restrictions/{restriction_id}/lift")
def lift_restriction(amo_code:str,restriction_id:str,payload:LiftRestriction,
                     db:Session=Depends(get_db),user=Depends(get_current_active_user)):
    _require(user,{"QUALITY_MANAGER"})
    amo=_tenant(db,amo_code,user)
    row=_one(db,"""SELECT * FROM quality_provider_restrictions
       WHERE amo_id=:amo AND id=:id FOR UPDATE""",amo=amo,id=restriction_id)
    if not row:raise HTTPException(404,"Restriction not found")
    if row["status"]!="ACTIVE":raise HTTPException(409,"Restriction is not active")
    case=_case(db,amo,payload.reinstatement_case_id,True)
    if case["supplier_id"]!=row["supplier_id"] or case["case_kind"]!="REINSTATEMENT" or (
        case["status"] not in {"APPROVED","CONDITIONALLY_APPROVED"}):
        raise HTTPException(409,"Current Quality-approved reinstatement case for this provider required")
    for car_id in row["required_cars_json"]:
        closed=_one(db,"""SELECT c.closed_at,p.effectiveness_required,
               (SELECT m.status FROM quality_car_milestones m
                WHERE m.amo_id=c.amo_id AND m.car_id=c.id
                AND m.milestone_key='EFFECTIVENESS_REVIEW'
                ORDER BY m.updated_at DESC LIMIT 1) effectiveness_status
               FROM quality_cars c LEFT JOIN quality_car_control_profiles p
               ON p.amo_id=c.amo_id AND p.car_id=c.id
               WHERE c.amo_id=:amo AND CAST(c.id AS TEXT)=:car""",amo=amo,car=car_id)
        if not closed or not closed["closed_at"] or (
             closed["effectiveness_required"] and closed["effectiveness_status"] not in {"ACCEPTED","COMPLETED"}):
            raise HTTPException(409,"Linked CAR requires canonical Quality closure and accepted effectiveness verification")
    db.execute(text("""UPDATE quality_provider_restrictions
       SET status='LIFTED',lifted_by_user_id=:actor,lifted_at=NOW(),
       lift_reason=:reason,reinstatement_case_id=:case WHERE amo_id=:amo AND id=:id"""),
       {"actor":str(user.id),"reason":payload.reason,"case":case["id"],
        "amo":amo,"id":restriction_id})
    _record(db,amo,row["supplier_id"],user,"RESTRICTION_LIFTED",
            {"restriction_id":restriction_id,"reinstatement_case":case["id"],
             "reason":payload.reason},case["id"])
    _notify_provider_members(db,amo,row["supplier_id"],user,
        "Quality restriction updated",
        "A Quality restriction has been lifted after authorized reinstatement and verification.",
        "RESTRICTION",restriction_id)
    db.commit()
    return {"id":restriction_id,"status":"LIFTED"}




def _notify_provider_members(db, amo:str, supplier:int, user, title:str, body:str,
                             kind:str="QUALIFICATION", reference:str|None=None):
    """Reuse Phase 3 partner inbox; never expose staff-only raw review records.
    Quality authorization is checked BEFORE the internal-review RLS marker.
    """
    _require(user,{"QUALITY_MANAGER"})
    if db.get_bind().dialect.name=="postgresql":
        db.execute(text("SELECT set_config('app.external_provider_id','__INTERNAL_QUALITY_REVIEW__',true)"))
    recipients=_all(db,"""SELECT DISTINCT p.id provider,g.identity_id
        FROM external_tenant_providers p JOIN external_tenant_grants g
        ON g.amo_id=p.amo_id AND g.tenant_provider_id=p.id
        WHERE p.amo_id=:amo AND p.supplier_id=:supplier AND g.status='ACTIVE'""",
        amo=amo,supplier=supplier)
    for dest in recipients:
        db.execute(text("""INSERT INTO external_partner_notifications
          (id,amo_id,tenant_provider_id,identity_id,category,title,message,
           resource_kind,resource_id)
          VALUES(:id,:amo,:provider,:identity,'QUALITY',:title,:message,:kind,:ref)"""),
          {"id":uid(),"amo":amo,"provider":dest["provider"],
           "identity":dest["identity_id"],"title":title,"message":body,
           "kind":kind,"ref":reference})


@router.get("/alerts")
def surveillance_alerts(amo_code:str,db:Session=Depends(get_db),
                        user=Depends(get_current_active_user)):
    _require(user,QUALITY|MAINTENANCE|SAFETY)
    amo=_tenant(db,amo_code,user)
    review_due=_all(db,"""SELECT q.id,q.supplier_id,q.category,q.next_review_due_on,s.legal_name
      FROM quality_provider_qualification_cases q JOIN procurement_suppliers s
      ON s.amo_id=q.amo_id AND s.id=q.supplier_id
      WHERE q.amo_id=:amo AND q.status IN ('APPROVED','CONDITIONALLY_APPROVED')
      AND q.next_review_due_on<=CURRENT_DATE
      AND NOT EXISTS(SELECT 1 FROM quality_provider_qualification_cases newer
          WHERE newer.amo_id=q.amo_id AND newer.supplier_id=q.supplier_id
          AND newer.created_at>q.created_at AND newer.status IN
          ('APPROVED','CONDITIONALLY_APPROVED'))
      ORDER BY q.next_review_due_on,q.supplier_id LIMIT 100""",amo=amo)
    overdue_cars=_all(db,"""SELECT c.id,c.car_number,c.due_date,s.supplier_id,a.audit_ref
        FROM quality_cars c
        JOIN qms_audit_findings f ON f.id=c.finding_id AND f.amo_id=c.amo_id
        JOIN qms_audits a ON a.amo_id=f.amo_id AND a.id=f.audit_id
        JOIN quality_provider_surveillance s ON s.amo_id=f.amo_id
             AND s.audit_id=CAST(f.audit_id AS TEXT)
        WHERE c.amo_id=:amo AND c.closed_at IS NULL AND c.due_date<CURRENT_DATE
        ORDER BY c.due_date LIMIT 100""",amo=amo)
    return {"overdue_qualification_reviews":review_due,"overdue_cars":overdue_cars,
            "policy":"Existing QMS CAR escalation/acceptance remains authoritative"}


class SurveillanceDecision(BaseModel):
    outcome:Literal["IN_PROGRESS","SATISFACTORY","UNSATISFACTORY","CANCELLED"]
    reason:str=Field(min_length=12,max_length=2000)


@router.post("/surveillance/{surveillance_id}/review")
def surveillance_review(amo_code:str,surveillance_id:str,payload:SurveillanceDecision,
                        db:Session=Depends(get_db),user=Depends(get_current_active_user)):
    _require(user,{"QUALITY_MANAGER"})
    amo=_tenant(db,amo_code,user)
    row=_one(db,"""SELECT * FROM quality_provider_surveillance
      WHERE amo_id=:amo AND id=:id FOR UPDATE""",amo=amo,id=surveillance_id)
    if not row:raise HTTPException(404,"Linked surveillance audit not found")
    if row["outcome"] in {"SATISFACTORY","UNSATISFACTORY","CANCELLED"}:
        raise HTTPException(409,"Final surveillance outcome is immutable; link a follow-up QMS audit")
    if payload.outcome=="SATISFACTORY":
        audit=_one(db,"""SELECT actual_end,CAST(status AS TEXT) status
            FROM qms_audits WHERE amo_id=:amo AND CAST(id AS TEXT)=:audit""",
            amo=amo,audit=row["audit_id"])
        if not audit or not audit["actual_end"] or audit["status"]!="CLOSED":
            raise HTTPException(409,"Only a completed and closed canonical QMS audit may be satisfactory")
        cars=_one(db,"""SELECT count(*) n FROM quality_cars c
            JOIN qms_audit_findings f ON f.amo_id=c.amo_id AND f.id=c.finding_id
            WHERE c.amo_id=:amo AND CAST(f.audit_id AS TEXT)=:audit
            AND c.closed_at IS NULL""",amo=amo,audit=row["audit_id"])
        if cars and cars["n"]:
            raise HTTPException(409,"Open canonical QMS corrective actions block satisfactory surveillance")
    db.execute(text("""UPDATE quality_provider_surveillance
      SET outcome=:state,conclusion=:reason WHERE amo_id=:amo AND id=:id"""),
      {"state":payload.outcome,"reason":payload.reason,"amo":amo,"id":surveillance_id})
    _record(db,amo,row["supplier_id"],user,"SURVEILLANCE_"+payload.outcome,
            {"audit_id":row["audit_id"],"reason":payload.reason},row["case_id"])
    _notify_provider_members(db,amo,row["supplier_id"],user,
        "Quality surveillance outcome updated",
        "Your provider surveillance record has been reviewed by the AMO Quality Department.",
        "QUALIFICATION",row["case_id"])
    db.commit()
    return {"id":surveillance_id,"outcome":payload.outcome}


class EscalationRequest(BaseModel):
    supplier_id:int=Field(ge=1)
    reason:str=Field(min_length=12,max_length=2000)


@router.post("/alerts/escalate")
def escalate_provider_overdue(amo_code:str,payload:EscalationRequest,
                             db:Session=Depends(get_db),user=Depends(get_current_active_user)):
    _require(user,{"QUALITY_MANAGER"})
    amo=_tenant(db,amo_code,user);_supplier(db,amo,payload.supplier_id)
    outstanding=_one(db,"""SELECT
      (SELECT count(*) FROM quality_provider_qualification_cases q
       WHERE q.amo_id=:amo AND q.supplier_id=:supplier
       AND q.status IN ('APPROVED','CONDITIONALLY_APPROVED')
       AND q.next_review_due_on<CURRENT_DATE) review_count,
      (SELECT count(*) FROM quality_cars c
       JOIN qms_audit_findings f ON f.amo_id=c.amo_id AND f.id=c.finding_id
       JOIN quality_provider_surveillance a ON a.amo_id=f.amo_id
            AND a.audit_id=CAST(f.audit_id AS TEXT)
       WHERE c.amo_id=:amo AND a.supplier_id=:supplier
       AND c.closed_at IS NULL AND c.due_date<CURRENT_DATE) car_count""",
       amo=amo,supplier=payload.supplier_id)
    if not outstanding or not (outstanding["review_count"] or outstanding["car_count"]):
        raise HTTPException(409,"No overdue QMS surveillance or corrective action to escalate")
    _record(db,amo,payload.supplier_id,user,"OVERDUE_PROVIDER_ESCALATED",
        {"reason":payload.reason,"review_count":outstanding["review_count"],
         "car_count":outstanding["car_count"]})
    _notify_provider_members(db,amo,payload.supplier_id,user,
        "Overdue Quality obligations",
        "Quality has escalated outstanding surveillance or corrective actions; review assigned QMS work.",
        "QUALIFICATION")
    db.commit()
    return {"status":"ESCALATED","review_count":outstanding["review_count"],
            "car_count":outstanding["car_count"]}



@router.get("/providers/{supplier_id}/export")
def regulatory_export(amo_code:str,supplier_id:int,db:Session=Depends(get_db),
                      user=Depends(get_current_active_user)):
    """Controlled structured export of source-linked governance records.
    DMS binaries and raw security credentials are deliberately excluded.
    """
    _require(user,QUALITY)
    amo=_tenant(db,amo_code,user)
    supplier=_supplier(db,amo,supplier_id)
    cases=_all(db,"""SELECT * FROM quality_provider_qualification_cases
        WHERE amo_id=:amo AND supplier_id=:supplier ORDER BY created_at""",
        amo=amo,supplier=supplier_id)
    for row in cases:
        row["checks"]=_all(db,"""SELECT requirement_key,status,evidence_reference,
            approval_reference,expires_on,conclusion,verified_by_user_id,verified_at
            FROM quality_provider_qualification_checks
            WHERE amo_id=:amo AND case_id=:case ORDER BY requirement_key""",
            amo=amo,case=row["id"])
    evaluations=_all(db,"""SELECT id,template_id,template_revision_no,status,score,outcome,
        valid_until,reviewed_at,reviewed_by_user_id
        FROM procurement_supplier_evaluations
        WHERE amo_id=:amo AND supplier_id=:supplier ORDER BY created_at""",
        amo=amo,supplier=supplier_id)
    scopes=_all(db,"""SELECT id,category,product_family,site_code,authority,approval_number,
        CAST(status AS TEXT) status,effective_on,expires_on,qms_evaluation_id,qms_audit_id,
        evidence_reference,restrictions,approved_at,approved_by_user_id
        FROM procurement_supplier_approval_scopes
        WHERE amo_id=:amo AND supplier_id=:supplier ORDER BY category,site_code""",
        amo=amo,supplier=supplier_id)
    contracts=_all(db,"""SELECT id,contract_number,title,status,version,
        controlled_document_id,controlled_document_revision,effective_on,expires_on
        FROM quality_external_provider_contracts
        WHERE amo_id=:amo AND supplier_id=:supplier ORDER BY created_at""",
        amo=amo,supplier=supplier_id)
    verified=_all(db,"""SELECT id,evidence_type,source_system,source_id,title,status,
        valid_from,valid_until,contract_id,verified_at,verified_by_user_id
        FROM quality_external_provider_evidence
        WHERE amo_id=:amo AND supplier_id=:supplier ORDER BY created_at""",
        amo=amo,supplier=supplier_id)
    audits=_all(db,"""SELECT s.audit_id,s.kind,s.risk_level,s.due_on,s.outcome,
        s.conclusion,a.audit_ref,CAST(a.status AS TEXT) status,a.actual_end,
        (SELECT count(*) FROM quality_cars c JOIN qms_audit_findings f ON
            f.amo_id=c.amo_id AND f.id=c.finding_id
            WHERE c.amo_id=s.amo_id AND CAST(f.audit_id AS TEXT)=s.audit_id
            AND c.closed_at IS NULL) open_cars
        FROM quality_provider_surveillance s
        JOIN qms_audits a ON a.amo_id=s.amo_id AND CAST(a.id AS TEXT)=s.audit_id
        WHERE s.amo_id=:amo AND s.supplier_id=:supplier
        ORDER BY s.created_at""",amo=amo,supplier=supplier_id)
    restrictions=_all(db,"""SELECT * FROM quality_provider_restrictions
        WHERE amo_id=:amo AND supplier_id=:supplier ORDER BY created_at""",
        amo=amo,supplier=supplier_id)
    events=_all(db,"""SELECT action,actor_user_id,details_json,occurred_at FROM
        quality_provider_qualification_events
        WHERE amo_id=:amo AND supplier_id=:supplier
        ORDER BY occurred_at,id""",amo=amo,supplier=supplier_id)
    return {"export_type":"QMS_PROVIDER_REGULATORY_TRACE",
            "exported_at":datetime.now(timezone.utc).isoformat(),
            "manual_scope":"Tenant-approved category procedure references in policy snapshots",
            "supplier":supplier,"cases":cases,"evaluations":evaluations,
            "approved_scopes":scopes,"contracts":contracts,"evidence":verified,
            "audits":audits,"restrictions":restrictions,"events":events,
            "document_note":"Controlled binaries are available only via independent DMS release."}


@router.get("/providers/{supplier_id}/overview")
def provider_overview(amo_code:str,supplier_id:int,db:Session=Depends(get_db),
                      user=Depends(get_current_active_user)):
    _require(user,QUALITY|MAINTENANCE|SAFETY)
    amo=_tenant(db,amo_code,user);supplier=_supplier(db,amo,supplier_id)
    cases=_all(db,"""SELECT id,category,case_kind,status,version,next_review_due_on,
        technical_state,safety_state,authority_state,evaluation_id,audit_id
        FROM quality_provider_qualification_cases
        WHERE amo_id=:amo AND supplier_id=:supplier ORDER BY created_at DESC LIMIT 30""",
        amo=amo,supplier=supplier_id)
    restrictions=_all(db,"""SELECT id,dimension,target_key,status,effective_on,ends_on,
        reason,required_cars_json FROM quality_provider_restrictions
        WHERE amo_id=:amo AND supplier_id=:supplier ORDER BY created_at DESC LIMIT 40""",
        amo=amo,supplier=supplier_id)
    scope=_all(db,"""SELECT id,site_code,category,product_family,
        CAST(status AS TEXT) status,expires_on,approval_number,restrictions,qms_evaluation_id
        FROM procurement_supplier_approval_scopes
        WHERE amo_id=:amo AND supplier_id=:supplier ORDER BY category,site_code,id""",
        amo=amo,supplier=supplier_id)
    events=_all(db,"""SELECT action,details_json,occurred_at FROM
        quality_provider_qualification_events
        WHERE amo_id=:amo AND supplier_id=:supplier
        ORDER BY occurred_at DESC,id DESC LIMIT 100""",amo=amo,supplier=supplier_id)
    audits=_all(db,"""SELECT s.audit_id,s.kind,s.due_on,s.outcome,a.audit_ref,
        CAST(a.status AS TEXT) audit_status
        FROM quality_provider_surveillance s JOIN qms_audits a
        ON a.amo_id=s.amo_id AND CAST(a.id AS TEXT)=s.audit_id
        WHERE s.amo_id=:amo AND s.supplier_id=:supplier
        ORDER BY s.created_at DESC LIMIT 30""",amo=amo,supplier=supplier_id)
    return {"supplier":supplier,"cases":cases,"restrictions":restrictions,
            "approved_scopes":scope,"audits":audits,"history":events,
            "annual_audit_universal":False}
