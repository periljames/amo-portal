"""Department-scoped Phase 8 provider alert policy, operations and acknowledgements."""
from __future__ import annotations

import json
from datetime import datetime, timezone

from fastapi import APIRouter, Depends, HTTPException, Query, Request
from pydantic import BaseModel, Field
from sqlalchemy import text
from sqlalchemy.orm import Session

from amodb.database import get_db
from amodb.security import get_current_active_user
from amodb.apps.procurement import service
from amodb.apps.procurement import external_partner_router as partner
from . import provider_alerts as alerts

router = APIRouter(prefix="/api/maintenance/{amo_code}/provider-alerts",tags=["Provider alerts"])
partner_router = APIRouter(prefix="/api/external-provider/partner/{tenant_slug}/alert-preferences",
                           tags=["Provider alert preferences"])

ADMIN_ROLES = {"ADMIN","TENANT_ADMIN","ACCOUNTABLE_EXECUTIVE","SUPERADMIN","ADMINISTRATOR"}
OWNERS = {
    "QUALITY": {"QUALITY_MANAGER","QUALITY_OFFICER"},
    "PROCUREMENT": {"PROCUREMENT_MANAGER","PROCUREMENT_OFFICER"},
    "STORES": {"STORES_MANAGER"},
    "MAINTENANCE": {"BASE_MAINTENANCE_MANAGER","LINE_MAINTENANCE_MANAGER","WORKSHOP_MANAGER"},
}

def _role(user):
    return str(getattr(user.role,"value",user.role)).upper()

def _context(db, code, user, department=None):
    role=_role(user)
    if not user.is_superuser and role not in ADMIN_ROLES and not any(role in roles for roles in OWNERS.values()):
        raise HTTPException(403,"Departmental provider notification access required")
    if department and department not in OWNERS:
        raise HTTPException(422,"Invalid department")
    if department and not user.is_superuser and role not in ADMIN_ROLES and role not in OWNERS[department]:
        raise HTTPException(403,"Department ownership required")
    tenant=service.resolve_tenant_amo_id(db,amo_code=code,current_user=user)
    if db.get_bind().dialect.name=="postgresql":
        db.execute(text("SELECT set_config('app.tenant_id',:amo,true)"),{"amo":tenant})
        db.execute(text("SELECT set_config('app.external_provider_id','__INTERNAL_QUALITY_REVIEW__',true)"))
    return tenant

def _departments(user):
    if user.is_superuser or _role(user) in ADMIN_ROLES:
        return list(alerts.DEPARTMENTS)
    return [name for name,roles in OWNERS.items() if _role(user) in roles]

class PolicyUpdate(BaseModel):
    revision: int = Field(ge=0)
    lead_days: list[int] = Field(min_length=1,max_length=12)
    escalation_days: list[int] = Field(max_length=12)
    recipient_roles: list[str] = Field(max_length=12)
    in_app: bool = True
    email: bool = False
    templates: dict[str,str] = Field(default_factory=dict)
    digest_enabled: bool = False
    digest_hour: int = Field(default=8,ge=0,le=23)
    quiet_enabled: bool = False
    quiet_start: str = "21:00"
    quiet_end: str = "07:00"

@router.get("/policy")
def get_policy(amo_code:str,db:Session=Depends(get_db),user=Depends(get_current_active_user)):
    amo=_context(db,amo_code,user)
    p=alerts._policy(db,amo)
    allowed=_departments(user)
    return {"revision":p["revision"],"departments":{
        dep: {
            "lead_days":p["lead_days_json"].get(dep,alerts.DEFAULT_LEADS),
            "escalation_days":p["escalation_days_json"].get(dep,[]),
            "recipient_roles":p["routes_json"].get(dep,[]),
            "channels":p["channels_json"].get(dep,{"in_app":True,"email":False}),
            "templates":{k:v for k,v in p["templates_json"].items() if k in alerts.CATALOG and alerts.CATALOG[k]==dep},
        } for dep in allowed},
        "digest":p["digest_json"],"quiet_hours":p["quiet_hours_json"],
        "catalog":{key:department for key,department in alerts.CATALOG.items()
                   if department in allowed},
        "can_manage_delivery_window":user.is_superuser or _role(user) in ADMIN_ROLES}

@router.put("/policy/{department}")
def update_policy(amo_code:str,department:str,payload:PolicyUpdate,
                  db:Session=Depends(get_db),user=Depends(get_current_active_user)):
    department=department.upper()
    amo=_context(db,amo_code,user,department)
    if sorted(set(payload.lead_days),reverse=True)!=payload.lead_days or any(not 0<=d<=365 for d in payload.lead_days):
        raise HTTPException(422,"Lead days must be unique descending values between 0 and 365")
    if sorted(set(payload.escalation_days))!=payload.escalation_days or any(not 0<=d<=365 for d in payload.escalation_days):
        raise HTTPException(422,"Escalation days must be unique ascending values between 0 and 365")
    valid_roles=set(OWNERS[department])|set(alerts.DEFAULT_ROUTES.get(department,[]))
    if not set(payload.recipient_roles).issubset(valid_roles):
        raise HTTPException(422,"Recipient roles must belong to the selected department")
    if any(k not in alerts.CATALOG or alerts.CATALOG[k]!=department or len(v)>200
           for k,v in payload.templates.items()):
        raise HTTPException(422,"Template overrides must use this department's event catalog")
    try:
        from datetime import time
        time.fromisoformat(payload.quiet_start)
        time.fromisoformat(payload.quiet_end)
    except ValueError:
        raise HTTPException(422,"Quiet hours require HH:MM")
    current=alerts._policy(db,amo)
    if int(current["revision"])!=payload.revision:
        raise HTTPException(409,"Notification policy changed; refresh before saving")
    is_admin=user.is_superuser or _role(user) in ADMIN_ROLES
    if not is_admin and (
        payload.digest_enabled!=current["digest_json"].get("enabled",False)
        or payload.digest_hour!=current["digest_json"].get("hour",8)
        or payload.quiet_enabled!=current["quiet_hours_json"].get("enabled",False)
        or payload.quiet_start!=current["quiet_hours_json"].get("start","21:00")
        or payload.quiet_end!=current["quiet_hours_json"].get("end","07:00")
    ):
        raise HTTPException(403,"Only tenant administration may change global delivery windows")
    updated={key:dict(current[key]) for key in (
        "lead_days_json","escalation_days_json","routes_json","channels_json","templates_json",
        "digest_json","quiet_hours_json")}
    updated["lead_days_json"][department]=payload.lead_days
    updated["escalation_days_json"][department]=payload.escalation_days
    updated["routes_json"][department]=payload.recipient_roles
    updated["channels_json"][department]={"in_app":payload.in_app,"email":payload.email}
    updated["templates_json"]={
        **{k:v for k,v in updated["templates_json"].items() if alerts.CATALOG.get(k)!=department},
        **payload.templates}
    if is_admin:
        updated["digest_json"]={"enabled":payload.digest_enabled,"hour":payload.digest_hour}
        updated["quiet_hours_json"]={
            "enabled":payload.quiet_enabled,"start":payload.quiet_start,"end":payload.quiet_end}
    binds={k:json.dumps(v,separators=(",",":")) for k,v in updated.items()}
    binds.update(amo=amo,revision=payload.revision,actor=str(user.id))
    if payload.revision==0:
        result=db.execute(text("""INSERT INTO external_provider_alert_policies
           (amo_id,revision,lead_days_json,escalation_days_json,routes_json,
            channels_json,templates_json,digest_json,quiet_hours_json,updated_by)
           VALUES(:amo,1,CAST(:lead_days_json AS JSON),CAST(:escalation_days_json AS JSON),
             CAST(:routes_json AS JSON),CAST(:channels_json AS JSON),
             CAST(:templates_json AS JSON),CAST(:digest_json AS JSON),
             CAST(:quiet_hours_json AS JSON),:actor)
           ON CONFLICT (amo_id) DO NOTHING"""),binds)
    else:
        result=db.execute(text("""UPDATE external_provider_alert_policies SET
           revision=revision+1,lead_days_json=CAST(:lead_days_json AS JSON),
           escalation_days_json=CAST(:escalation_days_json AS JSON),
           routes_json=CAST(:routes_json AS JSON),channels_json=CAST(:channels_json AS JSON),
           templates_json=CAST(:templates_json AS JSON),digest_json=CAST(:digest_json AS JSON),
           quiet_hours_json=CAST(:quiet_hours_json AS JSON),updated_by=:actor,
           updated_at=NOW()
           WHERE amo_id=:amo AND revision=:revision"""),binds)
    if result.rowcount!=1:
        db.rollback()
        raise HTTPException(409,"Notification policy changed concurrently")
    db.commit()
    return {"revision":payload.revision+1,"department":department,"updated":True}

@router.get("/delivery-history")
def history(amo_code:str,department:str|None=None,status:str|None=None,
            limit:int=Query(60,ge=1,le=200),db:Session=Depends(get_db),
            user=Depends(get_current_active_user)):
    amo=_context(db,amo_code,user)
    permitted=_departments(user)
    if department and department.upper() not in permitted:
        raise HTTPException(403,"Department history not permitted")
    rows=db.execute(text("""SELECT id,event_key,source_kind,source_id,due_at,status,attempts,
            next_attempt_at,last_error,in_app_id,email_log_id,acknowledged_at,
            delivered_at,cancelled_at,created_at
         FROM external_provider_alert_jobs WHERE amo_id=:amo
         AND (:status IS NULL OR status=:status)
         ORDER BY created_at DESC LIMIT :limit"""),{"amo":amo,"status":status,"limit":min(1000,limit*8)}).mappings()
    items=[dict(r) for r in rows if alerts.CATALOG.get(r["event_key"]) in permitted
           and (department is None or alerts.CATALOG.get(r["event_key"])==department.upper())]
    return {"items":items[:limit],"has_more":len(items)>limit,
            "email_status_note":"Email accepted by provider is not proof of recipient delivery or read."}

@router.post("/delivery-history/{job_id}/retry")
def retry_delivery(amo_code:str,job_id:str,db:Session=Depends(get_db),
                   user=Depends(get_current_active_user)):
    amo=_context(db,amo_code,user)
    row=db.execute(text("""SELECT event_key,status FROM external_provider_alert_jobs
        WHERE amo_id=:amo AND id=:id FOR UPDATE"""),{"amo":amo,"id":job_id}).mappings().first()
    if not row:
        raise HTTPException(404,"Delivery job not found")
    _context(db,amo_code,user,alerts.CATALOG[row["event_key"]])
    if row["status"] not in ("FAILED","RETRY"):
        raise HTTPException(409,"Only failed or retrying delivery may be retried")
    db.execute(text("""UPDATE external_provider_alert_jobs SET status='RETRY',attempts=0,
        next_attempt_at=NOW(),last_error=NULL,updated_at=NOW() WHERE amo_id=:amo AND id=:id"""),
        {"amo":amo,"id":job_id})
    db.commit()
    return {"queued":True}

@router.post("/delivery-history/{job_id}/acknowledge")
def acknowledge(amo_code:str,job_id:str,db:Session=Depends(get_db),
                user=Depends(get_current_active_user)):
    amo=_context(db,amo_code,user)
    changed=db.execute(text("""UPDATE external_provider_alert_jobs
        SET acknowledged_at=COALESCE(acknowledged_at,NOW()),updated_at=NOW()
        WHERE amo_id=:amo AND id=:id AND recipient_user_id=:person AND status='DELIVERED'"""),
        {"amo":amo,"id":job_id,"person":str(user.id)})
    if not changed.rowcount:
        raise HTTPException(404,"No delivered action assigned to this user")
    db.commit()
    return {"acknowledged":True}

class PartnerPreferenceUpdate(BaseModel):
    revision:int=Field(ge=0)
    in_app_enabled:bool=True
    email_enabled:bool=False
    digest_enabled:bool=False

@partner_router.get("")
def partner_preferences(tenant_slug:str,request:Request,db:Session=Depends(get_db)):
    u=partner._ctx(db,request,tenant_slug,cap=None)
    ctx=partner._context(u)
    row=db.execute(text("""SELECT revision,in_app_enabled,email_enabled,digest_enabled
       FROM external_provider_alert_preferences WHERE amo_id=:amo
       AND tenant_provider_id=:provider AND identity_id=:person"""),ctx).mappings().first()
    return dict(row) if row else {"revision":0,"in_app_enabled":True,
                                  "email_enabled":False,"digest_enabled":False}

@partner_router.put("")
def save_partner_preferences(tenant_slug:str,payload:PartnerPreferenceUpdate,
                             request:Request,db:Session=Depends(get_db)):
    u=partner._ctx(db,request,tenant_slug,cap=None,write=True)
    ctx=partner._context(u)
    ctx.update(revision=payload.revision,in_app=payload.in_app_enabled,
               email=payload.email_enabled,digest=payload.digest_enabled)
    if payload.revision==0:
        result=db.execute(text("""INSERT INTO external_provider_alert_preferences
         (amo_id,tenant_provider_id,identity_id,in_app_enabled,email_enabled,digest_enabled)
         VALUES(:amo,:provider,:person,:in_app,:email,:digest)
         ON CONFLICT (amo_id,tenant_provider_id,identity_id) DO NOTHING"""),ctx)
    else:
        result=db.execute(text("""UPDATE external_provider_alert_preferences SET
            revision=revision+1,in_app_enabled=:in_app,email_enabled=:email,
            digest_enabled=:digest,updated_at=NOW()
            WHERE amo_id=:amo AND tenant_provider_id=:provider AND identity_id=:person
            AND revision=:revision"""),ctx)
    if result.rowcount!=1:
        db.rollback()
        raise HTTPException(409,"Preferences changed; reload to reconcile")
    db.commit()
    return {"updated":True,"revision":payload.revision+1}

@partner_router.post("/actions/{job_id}/acknowledge")
def partner_acknowledge(tenant_slug:str,job_id:str,request:Request,
                        db:Session=Depends(get_db)):
    user=partner._ctx(db,request,tenant_slug,cap=None,write=True)
    ctx=partner._context(user)
    changed=db.execute(text("""UPDATE external_provider_alert_jobs
       SET acknowledged_at=COALESCE(acknowledged_at,NOW()),updated_at=NOW()
       WHERE amo_id=:amo AND recipient_provider_id=:provider
       AND recipient_identity_id=:person AND id=:id AND status='DELIVERED'"""),
       {**ctx,"id":job_id})
    if not changed.rowcount:
        raise HTTPException(404,"Assigned alert action unavailable")
    db.commit()
    return {"acknowledged":True}

@partner_router.get("/actions/{job_id}")
def partner_alert_action(tenant_slug:str,job_id:str,request:Request,
                         db:Session=Depends(get_db)):
    user=partner._ctx(db,request,tenant_slug,cap=None)
    ctx=partner._context(user)
    job=db.execute(text("""SELECT id,event_key,source_kind,source_id,status,acknowledged_at
       FROM external_provider_alert_jobs
       WHERE amo_id=:amo AND recipient_provider_id=:provider
       AND recipient_identity_id=:person AND id=:id AND status='DELIVERED'"""),
       {**ctx,"id":job_id}).mappings().first()
    if not job:
        raise HTTPException(404,"Assigned alert action unavailable")
    scope=user["object_scope_json"] or {}
    if job["source_kind"]=="maintenance_event":
        target="contracted_work"
        link="work"
    else:
        raise HTTPException(404,"No actionable provider record")
    if str(job["source_id"]) not in {str(item) for item in scope.get(target,[])}:
        raise HTTPException(404,"Work item is not in the current member grant")
    from urllib.parse import quote
    return {"event_key":job["event_key"],"acknowledged_at":job["acknowledged_at"],
            "link":"/partner/"+quote(tenant_slug,safe="")+"/"+link+
                   "?work="+quote(str(job["source_id"]),safe="")}
