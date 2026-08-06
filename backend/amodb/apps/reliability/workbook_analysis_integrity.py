"""Exact, auditable Reliability limits that supersede spreadsheet calculations."""
from __future__ import annotations
import hashlib,json
from collections import defaultdict
from datetime import date,datetime,time,timedelta,timezone
from decimal import Decimal,localcontext
from typing import Any,Literal
from fastapi import APIRouter,Depends,HTTPException
from pydantic import BaseModel,Field,model_validator
from sqlalchemy.orm import Session
from amodb.apps.accounts import models as accounts
from amodb.database import get_write_db
from amodb.security import get_current_active_user
from . import models as rm
from . import workbook_parity as wp
UTC=timezone.utc; MAX_SCAN=50_000

class Request(BaseModel):
    metric_code:str=Field(min_length=2,max_length=128); metric_label:str=Field(min_length=2,max_length=255)
    source_kind:Literal["EVENT_COUNT","EVENT_RATE","EVENT_RATE_PER_100_FH","DATASET_COUNT","DATASET_FIELD"]
    period_start:date; period_end:date; bucket:Literal["WEEK","MONTH"]="MONTH"; event_types:list[str]=Field(default_factory=list)
    dataset_code:wp.WorkbookDatasetCode|None=None; metric_field:str|None=None; aircraft_serial_number:str|None=None; ata_chapter:str|None=None
    method:Literal["SAMPLE_SIGMA","WORKBOOK_COMPATIBLE","POISSON_U_CHART"]="SAMPLE_SIGMA"
    denominator_kind:Literal["FLIGHT_HOURS","FLIGHT_CYCLES"]="FLIGHT_HOURS"; rate_scale:Decimal=Field(default=Decimal("1000"),gt=0,le=1_000_000); baseline_periods:int=Field(default=12,ge=3,le=60)
    warning_multiplier:Decimal=Field(default=Decimal("2"),ge=0,le=10); alert_multiplier:Decimal=Field(default=Decimal("3"),gt=0,le=10)
    @model_validator(mode="after")
    def valid(self):
        if self.period_end<self.period_start: raise ValueError("Period end must be on or after period start.")
        if (self.period_end-self.period_start).days>1826: raise ValueError("Analysis windows are limited to five years.")
        if self.source_kind.startswith("DATASET") and not self.dataset_code: raise ValueError("Dataset code is required.")
        if self.source_kind=="DATASET_FIELD" and not self.metric_field: raise ValueError("Metric field is required.")
        if self.alert_multiplier<self.warning_multiplier: raise ValueError("Alert multiplier cannot be lower than warning multiplier.")
        if self.source_kind=="EVENT_RATE_PER_100_FH": self.denominator_kind="FLIGHT_HOURS"; self.rate_scale=Decimal("100")
        if self.method=="POISSON_U_CHART" and not self.source_kind.startswith("EVENT_RATE"): raise ValueError("A Poisson u-chart requires an event rate.")
        if self.method=="WORKBOOK_COMPATIBLE" and self.baseline_periods!=12: raise ValueError("Workbook-reference analysis requires 12 periods.")
        return self

def amo(user):
    value=user.effective_amo_id
    if not value: raise HTTPException(403,"Tenant context is required.")
    return str(value)
def bstart(v:date,bucket:str): return v-timedelta(days=v.weekday()) if bucket=="WEEK" else v.replace(day=1)
def bnext(v:date,bucket:str):
    if bucket=="WEEK": return v+timedelta(days=7)
    return v.replace(year=v.year+1,month=1,day=1) if v.month==12 else v.replace(month=v.month+1,day=1)
def periods(start,end,bucket):
    out=[]; cur=bstart(start,bucket); terminal=bstart(end,bucket)
    while cur<=terminal: out.append(cur); cur=bnext(cur,bucket)
    return out
def sqrt(v:Decimal)->Decimal:
    if v<0: raise HTTPException(422,"Statistical variance became negative.")
    with localcontext() as c: c.prec=34; return v.sqrt(context=c)
def exact(v): return None if v is None else format(v,"f")
def display(v): return None if v is None else float(v)

def _sample_sigma(series:list[dict[str,Any]],warn:Decimal,alert:Decimal):
    vals=[Decimal(str(x["exact_value"])) for x in series if x.get("exact_value") is not None]
    if len(vals)<3: raise HTTPException(422,"At least three valid periods are required.")
    mean=sum(vals,Decimal(0))/Decimal(len(vals)); sigma=sqrt(sum((x-mean)**2 for x in vals)/Decimal(len(vals)-1))
    return {"sample_size":len(vals),"mean":mean,"sample_stddev":sigma,"warning_level":mean+warn*sigma,"alert_level":mean+alert*sigma,"formula_text":"Exact Decimal sample sigma: mean=Σx/n; s=sqrt(Σ(x-mean)^2/(n-1)); warning=mean+k1×s; alert=mean+k2×s"}
def _workbook_compatible(series:list[dict[str,Any]]):
    if len(series)<12: raise HTTPException(422,"Workbook-reference analysis requires twelve consecutive periods.")
    base=series[-12:]
    if any(x.get("exact_value") is None for x in base): raise HTTPException(422,{"message":"Workbook-reference baseline is incomplete; missing exposure is not zero.","missing_periods":[x["period"] for x in base if x.get("exact_value") is None]})
    vals=[Decimal(str(x["exact_value"])) for x in base]; mean=sum(vals)/Decimal(12); sigma=sqrt(sum((x-mean)**2 for x in vals)/Decimal(12)); moving=[(vals[i]+vals[i+1])/2 for i in range(11)]; mm=sum(moving)/Decimal(11); ms=sqrt(sum((x-mm)**2 for x in moving)/Decimal(11))
    return {"sample_size":12,"mean":mean,"sample_stddev":sigma,"moving_mean_stddev":ms,"warning_level":mean+ms+Decimal(2)*sigma,"alert_level":mean+ms+Decimal(3)*sigma,"formula_text":"Workbook-reference 12-period method: population sigma plus sigma of 11 adjacent two-period means; warning=mean+moving_sigma+2σ; alert=mean+moving_sigma+3σ"}
def _u_chart(series,warn,alert,scale):
    valid=[x for x in series if x.get("exact_denominator") is not None and Decimal(str(x["exact_denominator"]))>0]
    if len(valid)<8: raise HTTPException(422,"Poisson u-chart requires at least eight periods with positive exposure.")
    num=sum((Decimal(str(x.get("exact_numerator") or 0)) for x in valid),Decimal(0)); den=sum((Decimal(str(x["exact_denominator"])) for x in valid),Decimal(0)); center=num/den*scale
    for x in series:
        raw=x.get("exact_denominator")
        if raw is None or Decimal(str(raw))<=0: x.update(warning_level=None,alert_level=None,exact_warning_level=None,exact_alert_level=None); continue
        sig=sqrt(center*scale/Decimal(str(raw))); w=center+warn*sig; a=center+alert*sig; x.update(warning_level=display(w),alert_level=display(a),exact_warning_level=exact(w),exact_alert_level=exact(a))
    latest=valid[-1]; sig=sqrt(center*scale/Decimal(str(latest["exact_denominator"])))
    return {"sample_size":len(valid),"mean":center,"sample_stddev":sig,"warning_level":center+warn*sig,"alert_level":center+alert*sig,"formula_text":"Poisson u-chart: centre=Σevents/Σexposure×scale; period sigma=sqrt(centre×scale/exposure); each period retains its own limits"}

def _events(db,tenant,r):
    q=db.query(rm.ReliabilityEvent).filter(rm.ReliabilityEvent.amo_id==tenant,rm.ReliabilityEvent.occurred_at>=datetime.combine(r.period_start,time.min,tzinfo=UTC),rm.ReliabilityEvent.occurred_at<=datetime.combine(r.period_end,time.max,tzinfo=UTC))
    if r.aircraft_serial_number:q=q.filter(rm.ReliabilityEvent.aircraft_serial_number==r.aircraft_serial_number)
    if r.ata_chapter:q=q.filter(rm.ReliabilityEvent.ata_chapter==r.ata_chapter)
    if r.event_types:q=q.filter(rm.ReliabilityEvent.event_type.in_(r.event_types))
    rows=q.order_by(rm.ReliabilityEvent.occurred_at).limit(MAX_SCAN+1).all()
    if len(rows)>MAX_SCAN: raise HTTPException(422,"Event population exceeds 50,000 rows; narrow the scope.")
    return rows
def _util(db,tenant,r):
    q=db.query(rm.AircraftUtilizationDaily).filter(rm.AircraftUtilizationDaily.amo_id==tenant,rm.AircraftUtilizationDaily.date>=r.period_start,rm.AircraftUtilizationDaily.date<=r.period_end)
    if r.aircraft_serial_number:q=q.filter(rm.AircraftUtilizationDaily.aircraft_serial_number==r.aircraft_serial_number)
    rows=q.order_by(rm.AircraftUtilizationDaily.date).limit(MAX_SCAN+1).all()
    if len(rows)>MAX_SCAN: raise HTTPException(422,"Utilisation population exceeds 50,000 rows; narrow the scope.")
    return rows

def series(db,tenant,r):
    seq=periods(r.period_start,r.period_end,r.bucket); totals=defaultdict(lambda:Decimal(0)); observations=defaultdict(int)
    if r.source_kind.startswith("EVENT"):
        for row in _events(db,tenant,r): totals[bstart(row.occurred_at.date(),r.bucket)]+=1; observations[bstart(row.occurred_at.date(),r.bucket)]+=1
        if r.source_kind=="EVENT_COUNT": return [{"period":k.isoformat(),"value":display(totals[k]),"exact_value":exact(totals[k]),"numerator":int(totals[k]),"exact_numerator":exact(totals[k]),"quality":"VALID"} for k in seq]
        exposure=defaultdict(lambda:Decimal(0)); exposure_rows=defaultdict(int)
        for row in _util(db,tenant,r):
            k=bstart(row.date,r.bucket); raw=row.flight_hours if r.denominator_kind=="FLIGHT_HOURS" else row.cycles; exposure[k]+=Decimal(str(raw or 0)); exposure_rows[k]+=1
        out=[]
        for k in seq:
            den=exposure[k]; value=totals[k]/den*r.rate_scale if den>0 else None
            out.append({"period":k.isoformat(),"value":display(value),"exact_value":exact(value),"numerator":int(totals[k]),"exact_numerator":exact(totals[k]),"denominator":display(den),"exact_denominator":exact(den),"denominator_kind":r.denominator_kind,"rate_scale":exact(r.rate_scale),"exposure_rows":exposure_rows[k],"quality":"VALID" if den>0 else "WITHHELD_NO_EXPOSURE"})
        return out
    q=db.query(wp.ReliabilityWorkbookRecord).filter(wp.ReliabilityWorkbookRecord.amo_id==tenant,wp.ReliabilityWorkbookRecord.dataset_code==r.dataset_code.value,wp.ReliabilityWorkbookRecord.status.in_(["APPROVED","CLOSED"]),wp.ReliabilityWorkbookRecord.event_date>=r.period_start,wp.ReliabilityWorkbookRecord.event_date<=r.period_end)
    if r.aircraft_serial_number:q=q.filter(wp.ReliabilityWorkbookRecord.aircraft_serial_number==r.aircraft_serial_number)
    if r.ata_chapter:q=q.filter(wp.ReliabilityWorkbookRecord.ata_chapter==r.ata_chapter)
    rows=q.order_by(wp.ReliabilityWorkbookRecord.event_date).limit(MAX_SCAN+1).all()
    if len(rows)>MAX_SCAN: raise HTTPException(422,"Controlled register population exceeds 50,000 rows.")
    for row in rows:
        k=bstart(row.event_date,r.bucket); observations[k]+=1
        if r.source_kind=="DATASET_COUNT": totals[k]+=1
        else:
            raw=(row.derived_values or {}).get(r.metric_field,(row.payload or {}).get(r.metric_field))
            if raw not in (None,""): totals[k]+=Decimal(str(raw))
    return [{"period":k.isoformat(),"value":display(totals[k]) if r.source_kind=="DATASET_COUNT" or observations[k] else None,"exact_value":exact(totals[k]) if r.source_kind=="DATASET_COUNT" or observations[k] else None,"observations":observations[k],"quality":"VALID" if r.source_kind=="DATASET_COUNT" or observations[k] else "WITHHELD_NO_APPROVED_SOURCE"} for k in seq]

def register(router:APIRouter):
    @router.post("/workbook-parity/statistical-alerts/calculate",status_code=201)
    def calculate(r:Request,user:accounts.User=Depends(get_current_active_user),db:Session=Depends(get_write_db)):
        tenant=amo(user); s=series(db,tenant,r)
        levels=_workbook_compatible(s) if r.method=="WORKBOOK_COMPATIBLE" else _u_chart(s,r.warning_multiplier,r.alert_multiplier,r.rate_scale) if r.method=="POISSON_U_CHART" else _sample_sigma(s,r.warning_multiplier,r.alert_multiplier)
        snapshot=hashlib.sha256(json.dumps({"request":r.model_dump(mode="json"),"series":s,"levels":{k:exact(v) if isinstance(v,Decimal) else v for k,v in levels.items()}},sort_keys=True,default=str,separators=(",",":")).encode()).hexdigest(); formula=f"{levels['formula_text']}; method={r.method}; denominator={r.denominator_kind}; scale={r.rate_scale}; snapshot_sha256={snapshot}"
        warn=Decimal(2) if r.method=="WORKBOOK_COMPATIBLE" else r.warning_multiplier; alert=Decimal(3) if r.method=="WORKBOOK_COMPATIBLE" else r.alert_multiplier
        row=wp.ReliabilityStatisticalAlertResult(amo_id=tenant,metric_code=r.metric_code,metric_label=r.metric_label,source_kind=r.source_kind,dataset_code=r.dataset_code.value if r.dataset_code else None,metric_field=r.metric_field,scope_type="AIRCRAFT" if r.aircraft_serial_number else "ATA" if r.ata_chapter else "FLEET",scope_value=r.aircraft_serial_number or r.ata_chapter,period_start=r.period_start,period_end=r.period_end,bucket=r.bucket,sample_size=levels["sample_size"],mean_value=levels["mean"],sample_stddev=levels["sample_stddev"],warning_multiplier=warn,alert_multiplier=alert,warning_level=levels["warning_level"],alert_level=levels["alert_level"],formula=formula,series=s,generated_by_user_id=user.id); db.add(row); db.commit(); db.refresh(row)
        completeness={"periods":len(s),"valid_periods":sum(x.get("exact_value") is not None for x in s),"withheld_periods":sum(x.get("exact_value") is None for x in s)}
        return {"id":row.id,"metric_code":row.metric_code,"metric_label":row.metric_label,"source_kind":row.source_kind,"dataset_code":row.dataset_code,"scope_type":row.scope_type,"scope_value":row.scope_value,"period_start":row.period_start,"period_end":row.period_end,"bucket":row.bucket,"method":r.method,"denominator_kind":r.denominator_kind,"rate_scale":exact(r.rate_scale),"sample_size":row.sample_size,"mean":float(row.mean_value),"exact_mean":exact(Decimal(row.mean_value)),"sample_stddev":float(row.sample_stddev),"exact_sample_stddev":exact(Decimal(row.sample_stddev)),"warning_level":float(row.warning_level),"exact_warning_level":exact(Decimal(row.warning_level)),"alert_level":float(row.alert_level),"exact_alert_level":exact(Decimal(row.alert_level)),"moving_mean_stddev":exact(levels.get("moving_mean_stddev")),"formula":row.formula,"formula_snapshot_hash":snapshot,"data_completeness":completeness,"series":row.series,"generated_at":row.generated_at}
