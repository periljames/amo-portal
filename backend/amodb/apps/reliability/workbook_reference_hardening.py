"""Controlled workbook domains and exact component analysis."""
from __future__ import annotations
from datetime import date
from decimal import Decimal
from enum import Enum
from typing import Any
from fastapi import HTTPException
from pydantic import model_validator
from sqlalchemy import Numeric
from . import models as rm
from . import workbook_parity as wp
from . import workbook_parity_defaults as defaults

class WorkbookDatasetCode(str, Enum):
    AU="AU"; AI="AI"; FI="FI"; PM="PM"; OOS="OOS"; RM="RM"; SM="SM"; SR="SR"
    SB="SB"; CS="CS"; AS="AS"; UR="UR"; STRUCTURES="STRUCTURES"; RECURRING="RECURRING"; ECTM="ECTM"; ADD="ADD"
class DatasetDefinition(wp.DatasetDefinition): code: WorkbookDatasetCode
class WorkbookRecordCreate(wp.WorkbookRecordCreate): dataset_code: WorkbookDatasetCode
class MappingCreate(wp.MappingCreate): dataset_code: WorkbookDatasetCode
class StatisticalAlertRequest(wp.StatisticalAlertRequest):
    dataset_code: WorkbookDatasetCode | None = None
    @model_validator(mode="after")
    def _contract(self): return super().validate_contract()

def F(key,label,kind="text",req=False,unit=None,opts=()):
    return wp._field(key,label,kind,required=req,unit=unit,options=opts)
def D(code,name,sheets,description,fields):
    return DatasetDefinition(code=code,name=name,workbook_sheet_names=sheets,description=description,event_type="OTHER",fields=fields)

def _catalogue():
    out={WorkbookDatasetCode(k.value):DatasetDefinition.model_validate(v.model_dump()) for k,v in wp.DATASET_CATALOG.items()}
    for f in out[WorkbookDatasetCode.FI].fields:
        if f.key in {"reporting_period","departures"}: f.required=False
    have={f.key for f in out[WorkbookDatasetCode.FI].fields}
    for f in [F("delay_indicator","Delay indicator","boolean"),F("cancellation_indicator","Cancellation indicator","boolean"),F("substitute_aircraft_indicator","Substitute aircraft indicator","boolean"),F("interruption_code","Interruption code"),F("delay_time_minutes","Delay time","integer",unit="min"),F("event_corrective_action","Event corrective action","textarea")]:
        if f.key not in have: out[WorkbookDatasetCode.FI].fields.append(f)
    out[WorkbookDatasetCode.SB]=D(WorkbookDatasetCode.SB,"Service bulletins and modifications",["SB","SERVICE BULLETINS","MODIFICATIONS"],"Controlled SB, AD, STC and modification incorporation evidence",[
        F("implementation_type","Implementation type",req=True),F("accomplishment_date","Accomplishment date","date",True),F("document_type","Document type",req=True),F("document_source","Document source"),F("service_bulletin_number","Service bulletin number"),F("stc_mod_number","STC / modification number"),F("airworthiness_directive_number","Airworthiness directive number"),F("issue_date","Issue date","date"),F("revision","Revision"),F("incorporation_status","Incorporation status",req=True),F("findings","Findings","textarea"),F("labour_hours","Labour hours","decimal",unit="h"),F("material_cost","Material cost","decimal"),F("currency","Currency")])
    out[WorkbookDatasetCode.CS]=D(WorkbookDatasetCode.CS,"Maintenance cost",["CS","MAINTENANCE COST","COST"],"Controlled maintenance cost evidence",[
        F("reporting_period_start","Reporting period start","date",True),F("reporting_period_end","Reporting period end","date",True),F("company_name","Company name"),F("item_description","Item description",req=True),F("part_number","Part number"),F("serial_number","Serial number"),F("quantity_per_aircraft","Quantity per aircraft","integer"),F("work_order_reference","Work order / package reference"),F("maintenance_reason","Maintenance reason"),F("warranty_indicator","Warranty applicable","boolean"),F("invoice_reference","Invoice reference"),F("currency","Currency",req=True),F("labour_cost","Labour cost","decimal"),F("material_cost","Material cost","decimal"),F("other_cost","Other cost","decimal"),F("total_cost","Total cost","decimal")])
    out[WorkbookDatasetCode.AS]=D(WorkbookDatasetCode.AS,"Aircraft change status",["AS","AIRCRAFT CHANGE STATUS","AIRCRAFT STATUS"],"Revisioned aircraft and powerplant status evidence",[
        F("operator_name","Operator name"),F("aircraft_model","Aircraft model",req=True),F("aircraft_series","Aircraft series"),F("manufacturer_serial_number","Manufacturer serial number",req=True),F("registration_number","Registration number",req=True),F("aircraft_total_hours","Aircraft total hours","decimal",unit="FH"),F("aircraft_total_cycles","Aircraft total cycles","integer",unit="FC"),F("engine_1_serial_number","Engine 1 serial number"),F("engine_1_total_hours","Engine 1 total hours","decimal",unit="FH"),F("engine_1_total_cycles","Engine 1 total cycles","integer",unit="FC"),F("engine_2_serial_number","Engine 2 serial number"),F("engine_2_total_hours","Engine 2 total hours","decimal",unit="FH"),F("engine_2_total_cycles","Engine 2 total cycles","integer",unit="FC"),F("apu_serial_number","APU serial number"),F("apu_total_hours","APU total hours","decimal",unit="h"),F("apu_total_cycles","APU total cycles","integer"),F("effective_change_date","Effective change date","date",True),F("removed_from_service_date","Removed from service","date"),F("returned_to_service_date","Returned to service","date"),F("operational_change_status","Operational change status")])
    out[WorkbookDatasetCode.UR]=D(WorkbookDatasetCode.UR,"Component removal-rate analysis",["UR","UR ","UNSCHEDULED REMOVALS","COMPONENT REMOVAL ANALYSIS"],"Exact URR, MTBUR, total removal rate and MTBR per 1,000 unit-hours",[
        F("reporting_period","Reporting period",req=True),F("fleet_variant","Fleet variant",req=True),F("component_description","Component description",req=True),F("part_number","Part number",req=True),F("quantity_per_aircraft","Quantity per aircraft","integer",True),F("unit_hours","Fleet unit-hours","decimal",True,"FH"),F("unscheduled_removals","Unscheduled removals","integer",True),F("total_removals","Total removals","integer",True)])
    return out

def dec(v,label):
    x=Decimal(str(v or 0))
    if x<0: raise HTTPException(422,f"{label} cannot be negative.")
    return x

def _normaliser():
    base=wp._normalise_payload
    def normalise(ds,payload):
        p,d=base(ds,payload); code=WorkbookDatasetCode(getattr(ds.code,"value",ds.code))
        if code==WorkbookDatasetCode.CS:
            if date.fromisoformat(p["reporting_period_end"])<date.fromisoformat(p["reporting_period_start"]): raise HTTPException(422,"Cost period end cannot precede start.")
            total=sum((dec(p.get(k),k) for k in ("labour_cost","material_cost","other_cost")),Decimal(0)); d["calculated_total_cost"]=f"{total:.2f}"
            if p.get("total_cost") not in (None,""):
                stated=dec(p["total_cost"],"total_cost"); d["cost_reconciliation_variance"]=f"{stated-total:.2f}"; d["cost_reconciled"]=(stated-total).quantize(Decimal(".01"))==0
        elif code==WorkbookDatasetCode.UR:
            q,h,u,t=(dec(p.get("quantity_per_aircraft"),"QPA"),dec(p.get("unit_hours"),"unit hours"),dec(p.get("unscheduled_removals"),"unscheduled removals"),dec(p.get("total_removals"),"total removals"))
            if q<=0 or h<=0: d.update(exposure_unit_hours=None,urr_per_1000_unit_hours=None,mtbur_unit_hours=None,trr_per_1000_unit_hours=None,mtbr_unit_hours=None,analysis_withheld_reason="QPA and unit-hours must be positive")
            else:
                e=q*h; d.update(exposure_unit_hours=f"{e:f}",urr_per_1000_unit_hours=f"{u/e*1000:.6f}",trr_per_1000_unit_hours=f"{t/e*1000:.6f}")
                d["mtbur_unit_hours"]=f"{e/u:.6f}" if u else None; d["mtbr_unit_hours"]=f"{e/t:.6f}" if t else None
                if not u: d["mtbur_status"]="NO_UNSCHEDULED_REMOVALS_IN_PERIOD"
                if not t: d["mtbr_status"]="NO_REMOVALS_IN_PERIOD"
        return p,d
    wp._normalise_payload=normalise

def _model_types():
    for n in ("utilisation_hours","utilisation_cycles"): rm.ReliabilityDefectTrend.__table__.c[n].type=Numeric(20,6)
    rm.ReliabilityDefectTrend.__table__.c.defect_rate_per_100_fh.type=Numeric(20,9)
    for n in ("value","numerator","denominator"): rm.ReliabilityKPI.__table__.c[n].type=Numeric(24,9)

def _layouts():
    for layout in wp.DEFAULT_LAYOUTS:
        if layout["code"]=="OPERATOR-RP": layout["sections"]=[{"code":c.value,"title":d.name,"kind":"DATASET","dataset_code":c.value} for c,d in wp.DATASET_CATALOG.items()]+[{"code":"ALERTS","title":"Statistical alert calculations","kind":"STATISTICAL_ALERTS"}]
        else:
            have={s.get("dataset_code") for s in layout["sections"]}; at=next((i for i,s in enumerate(layout["sections"]) if s.get("kind")=="STATISTICAL_ALERTS"),len(layout["sections"]))
            for c in (WorkbookDatasetCode.SB,WorkbookDatasetCode.CS,WorkbookDatasetCode.AS,WorkbookDatasetCode.UR):
                if c.value not in have: layout["sections"].insert(at,{"code":c.value,"title":wp.DATASET_CATALOG[c].name,"kind":"DATASET","dataset_code":c.value}); at+=1

def apply():
    wp.DATASET_CATALOG=_catalogue(); wp.WorkbookDatasetCode=WorkbookDatasetCode; wp.DatasetDefinition=DatasetDefinition; wp.WorkbookRecordCreate=WorkbookRecordCreate; wp.MappingCreate=MappingCreate; wp.StatisticalAlertRequest=StatisticalAlertRequest
    for cls in (DatasetDefinition,WorkbookRecordCreate,MappingCreate,StatisticalAlertRequest): cls.model_rebuild(force=True)
    _model_types(); _normaliser(); _layouts(); defaults.DATASET_CATALOG=wp.DATASET_CATALOG; defaults.WorkbookDatasetCode=WorkbookDatasetCode; defaults.DEFAULT_MAPPING_ROWS=defaults.default_mapping_rows()
apply()
