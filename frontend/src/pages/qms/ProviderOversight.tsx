import React, {useEffect,useState} from "react";
import {apiRequest,qmsPath} from "../../services/apiClient";
import {getCachedUser} from "../../services/auth";
import { isTenantAdmin } from "../../utils/tenantAccess";

type Summary={states:{status:string;risk_level:string;total:number}[];
  queue:{qualification_pending:number;reviews_due:number};
  next_120_days:{contracts:number;certificates:number;scopes:number};
  as_of:string;computed_not_approval:boolean;
  human_classifications:{critical:number;sole_source:number}};
type CalendarRow={kind:string;supplier_code:string;reference:string;due_on:string};
type Profile={supplier:{legal_name:string;risk_level:string;status:string};
  sites:{site_code:string;site_name:string;country:string|null;is_primary:boolean}[];
  scopes:{site_code:string;category:string;product_family:string;status:string;expires_on:string|null}[];
  contracts:{contract_number:string;status:string;expires_on:string|null}[];
  certificates:{certificate_type:string;verification_state:string;valid_until:string|null}[];
  qualification_cases:{category:string;case_kind:string;status:string;next_review_due_on:string|null}[];
  surveillance:{kind:string;due_on:string|null;outcome:string}[];
  evidence:{total:number;current_verified:number;expired:number;pending:number};
  restrictions:{active:number};procurement:{total_orders:number;fulfilled:number;late_open:number;on_time_percent:number|null;dated_fulfilled:number};
  receiving:{inspections:number;discrepancies:number;returns:number};
  contracted_maintenance:{total:number;closed:number;outstanding:number;avg_turnaround_hours:number|null};
  returns:{return_requests:number;warranty_requests:number};
  concentration:{po_count_share_percent:number|null;provider_orders:number;tenant_orders:number};
  lifecycle_snapshots:{action:string;previous_status:string|null;current_status:string;risk_level:string;occurred_at:string}[];
  special_classification:{critical_service:boolean;sole_source:boolean;reason:string;revision:number}|null;
  qms_assurance:{findings:number;open_cars:number;overdue_cars:number;verified_caps:number};
  car_effectiveness:{required:number;accepted:number;rejected_or_blocked:number;overdue:number;without_control_profile:number};
  finding_months:{month:string;total:number}[];
  limitations:string[];as_of:string;computed_not_approval:boolean};
function value(n:number|string|null|undefined):string{
  return n===null||n===undefined?"Insufficient data":String(n);
}
function Table({head,items}: {head:string[];items:Array<Array<string|number|null|undefined>>}) {
  return <div className="qms-provider-table-wrap"><table className="qms-provider-table">
    <thead><tr>{head.map((h,i)=><th key={i}>{h}</th>)}</tr></thead>
    <tbody>{items.map((row,i)=><tr key={i}>{row.map((cell,j)=><td key={j}>{cell==null||cell===""?"—":String(cell)}</td>)}</tr>)}
      {!items.length&&<tr><td colSpan={head.length}>No records in this governed category.</td></tr>}</tbody>
  </table></div>;
}
function Stat({label,content}:{label:string;content:string|number}) {
  return <div className="qms-provider-summary-card"><div><strong>{content}</strong><span>{label}</span></div></div>;
}
export function ProviderPortfolio({amoCode}:{amoCode:string}) {
  const [summary,setSummary]=useState<Summary|null>(null);
  const [calendar,setCalendar]=useState<CalendarRow[]>([]);
  const [expanded,setExpanded]=useState(false);
  const [pending,setPending]=useState(false);
  const [exporting,setExporting]=useState(false);
  const [error,setError]=useState("");
  const root=qmsPath(amoCode,"/provider-oversight");
  useEffect(()=>{if(!expanded)return;let live=true;setPending(true);setError("");setSummary(null);setCalendar([]);
    Promise.all([
      apiRequest<Summary>(root+"/portfolio",{cacheTtlMs:0}),
      apiRequest<{items:CalendarRow[]}>(root+"/calendar?days=120&limit=100",{cacheTtlMs:0})
    ]).then(([a,b])=>{if(live){setSummary(a);setCalendar(b.items);}})
    .catch(e=>{if(live)setError(e instanceof Error?e.message:"Management overview unavailable.");})
    .finally(()=>{if(live)setPending(false);});return()=>{live=false;};
  },[root,expanded]);
  async function exportCsv(){
    setExporting(true);setError("");
    try{
      const csv=await apiRequest<string>(root+"/register.csv",{cacheTtlMs:0});
      const file=new Blob([csv],{type:"text/csv;charset=utf-8"});
      const href=URL.createObjectURL(file);
      const a=document.createElement("a");a.href=href;a.download="provider-register.csv";
      a.click();window.setTimeout(()=>URL.revokeObjectURL(href),1000);
    }catch(e){setError(e instanceof Error?e.message:"Controlled export failed.");}
    finally{setExporting(false);}
  }
  return <section className="qms-provider-register" aria-label="Provider management review">
    <button type="button" className="qms-provider-button is-secondary" onClick={()=>setExpanded(x=>!x)}
      aria-expanded={expanded}>{expanded?"Hide management overview":"Open management overview and expiry calendar"}</button>
    {expanded&&<div>
      <p>Source-linked observations only. Quality approval, restrictions and suspension require authorized human decisions.</p>
      {pending&&<p role="status">Loading bounded management indicators…</p>}
      {error&&<p role="alert">{error}</p>}
      {summary&&<><div className="qms-provider-summary">
        <Stat label="Qualification awaiting review" content={summary.queue.qualification_pending}/>
        <Stat label="Reviews due" content={summary.queue.reviews_due}/>
        <Stat label="Contracts expiring (120 days)" content={summary.next_120_days.contracts}/>
        <Stat label="Certificates expiring (120 days)" content={summary.next_120_days.certificates}/>
        <Stat label="Scopes expiring (120 days)" content={summary.next_120_days.scopes}/>
        <Stat label="Quality-classified critical providers" content={summary.human_classifications.critical}/>
        <Stat label="Quality-classified sole-source providers" content={summary.human_classifications.sole_source}/>
      </div><h3>Provider risk and lifecycle distribution</h3>
      <Table head={["Lifecycle","Human-classified risk","Providers"]}
        items={summary.states.map(r=>[r.status,r.risk_level,r.total])}/>
      <h3>Expiry and renewal calendar — first 100 records</h3>
      <Table head={["Record","Supplier","Reference","Due"]}
        items={calendar.map(r=>[r.kind,r.supplier_code,r.reference,r.due_on])}/>
      <button type="button" disabled={exporting} onClick={()=>void exportCsv()} className="qms-provider-button is-secondary">
        {exporting?"Preparing authorized export…":"Export controlled provider register (CSV)"}
      </button></>}
    </div>}
  </section>;
}
export default function ProviderOversight({amoCode,supplierId,evidenceOptions}:{
  amoCode:string;supplierId:number;evidenceOptions:{id:string;title:string}[]
}){
  const canClassify=isTenantAdmin(getCachedUser()) || getCachedUser()?.role==="QUALITY_MANAGER";
  const [critical,setCritical]=useState(false);
  const [sole,setSole]=useState(false);
  const [evidenceId,setEvidenceId]=useState("");
  const [reason,setReason]=useState("");
  const [saving,setSaving]=useState(false);
  const [data,setData]=useState<Profile|null>(null);
  const [error,setError]=useState("");
  const [pending,setPending]=useState(true);
  const [revision,setRevision]=useState(0);
  useEffect(()=>{let live=true;setPending(true);setError("");setData(null);
    apiRequest<Profile>(qmsPath(amoCode,"/provider-oversight/providers/"+supplierId),{cacheTtlMs:0})
      .then(v=>{if(live){setData(v);setCritical(Boolean(v.special_classification?.critical_service));
        setSole(Boolean(v.special_classification?.sole_source));setReason("");setEvidenceId("");}})
      .catch(e=>{if(live)setError(e instanceof Error?e.message:"Provider oversight unavailable.");})
      .finally(()=>{if(live)setPending(false);});
    return()=>{live=false;};
  },[amoCode,supplierId,revision]);
  async function saveClassification(){
    if(!data||reason.trim().length<12)return;
    setSaving(true);setError("");
    try{
      await apiRequest(qmsPath(amoCode,"/provider-oversight/providers/"+supplierId+"/classification"),{
        method:"PUT",headers:{"Content-Type":"application/json"},
        body:JSON.stringify({expected_revision:data.special_classification?.revision||0,
          critical_service:critical,sole_source:sole,evidence_id:evidenceId||null,reason:reason.trim()}),
        cacheTtlMs:0,
      });
      setRevision(v=>v+1);
    }catch(e){setError(e instanceof Error?e.message:"Classification not recorded.");}
    finally{setSaving(false);}
  }
  return <section className="qms-provider-detail-section" aria-label="Provider 360-degree performance">
    <h3>Provider 360° oversight</h3>
    <p>Computed operating indicators. They neither extend regulatory approvals nor authorize work.</p>
    <button type="button" className="qms-provider-button is-secondary" onClick={()=>setRevision(x=>x+1)}
      disabled={pending}>Refresh source indicators</button>
    {pending&&<p role="status">Loading current provider records…</p>}
    {error&&<p role="alert">{error}</p>}
    {data&&!pending&&<div>
      <div className="qms-provider-summary">
        <Stat label="On-time fulfilled POs" content={data.procurement.on_time_percent===null?"N/A":data.procurement.on_time_percent+"%"}/>
        <Stat label="Fulfilled PO sample" content={data.procurement.dated_fulfilled}/>
        <Stat label="Late open POs" content={data.procurement.late_open}/>
        <Stat label="Receiving discrepancies" content={data.receiving.discrepancies}/>
        <Stat label="Open contracted work" content={data.contracted_maintenance.outstanding}/>
        <Stat label="Active scope restrictions" content={data.restrictions.active}/>
        <Stat label="QMS findings (linked audits)" content={data.qms_assurance.findings}/>
        <Stat label="Overdue QMS CARs" content={data.qms_assurance.overdue_cars}/>
        <Stat label="Current verified evidence" content={data.evidence.current_verified}/>
        <Stat label="PO count concentration" content={data.concentration.po_count_share_percent===null?"N/A":data.concentration.po_count_share_percent+"%"}/>
      </div>
      <h4>Documented critical / sole-source classification</h4>
      <p>Critical service: {data.special_classification?.critical_service?"Yes":"No"}.
        Sole-source: {data.special_classification?.sole_source?"Yes":"No"}. These labels do not approve or suspend suppliers.</p>
      {canClassify&&<div className="qp-fields">
        <label><input type="checkbox" checked={critical} onChange={e=>setCritical(e.target.checked)}/> Critical service</label>
        <label><input type="checkbox" checked={sole} onChange={e=>setSole(e.target.checked)}/> Sole-source (confirmed evidence)</label>
        <label>Verified QMS evidence
          <select value={evidenceId} onChange={e=>setEvidenceId(e.target.value)}>
            <option value="">Select current verified record</option>
            {evidenceOptions.map(e=><option key={e.id} value={e.id}>{e.title}</option>)}
          </select>
        </label>
        <label>Quality Manager's documented classification reason
          <textarea rows={2} value={reason} onChange={e=>setReason(e.target.value)}/>
        </label>
        <button type="button" className="qms-provider-button" disabled={saving||reason.trim().length<12||((critical||sole)&&!evidenceId)}
          onClick={()=>void saveClassification()}>{saving?"Recording…":"Record controlled classification"}</button>
      </div>}
      <h4>Sites and approved capability records</h4>
      <Table head={["Site","Name","Country","Primary"]}
        items={data.sites.map(s=>[s.site_code,s.site_name,s.country,s.is_primary?"Yes":"No"])}/>
      <Table head={["Site","Scope","Product family","State","Expiry"]}
        items={data.scopes.map(s=>[s.site_code,s.category,s.product_family,s.status,s.expires_on])}/>
      <h4>Contracts and regulatory evidence</h4>
      <Table head={["Agreement","State","Expiry"]}
        items={data.contracts.map(c=>[c.contract_number,c.status,c.expires_on])}/>
      <Table head={["Certificate type","Verification","Expiry"]}
        items={data.certificates.map(c=>[c.certificate_type,c.verification_state,c.valid_until])}/>
      <div className="qms-provider-summary">
        <Stat label="Evidence pending" content={data.evidence.pending}/>
        <Stat label="Expired evidence" content={data.evidence.expired}/>
        <Stat label="Receiving inspections" content={data.receiving.inspections}/>
        <Stat label="Returns / RMAs" content={data.returns.return_requests}/>
        <Stat label="Warranty requests" content={data.returns.warranty_requests}/>
        <Stat label="Avg closed repair turnaround (hours)"
          content={data.contracted_maintenance.avg_turnaround_hours==null?"N/A":value(Math.round(data.contracted_maintenance.avg_turnaround_hours))}/>
      </div>
      <h4>QMS assurance and findings trend</h4>
      <div className="qms-provider-summary">
        <Stat label="Open linked CARs" content={data.qms_assurance.open_cars}/>
        <Stat label="CAP verification records (not effectiveness)" content={data.qms_assurance.verified_caps}/>
        <Stat label="CAR effectiveness reviews required" content={data.car_effectiveness.required}/>
        <Stat label="Effectiveness accepted or completed" content={data.car_effectiveness.accepted}/>
        <Stat label="Effectiveness overdue" content={data.car_effectiveness.overdue}/>
        <Stat label="Effectiveness rejected or blocked" content={data.car_effectiveness.rejected_or_blocked}/>
        <Stat label="CARs without control-loop profile" content={data.car_effectiveness.without_control_profile}/>
      </div>
      <Table head={["Finding month","Finding count"]}
        items={data.finding_months.map(r=>[r.month,r.total])}/>
      <h4>Qualification and surveillance</h4>
      <Table head={["Category","Case","State","Next due"]}
        items={data.qualification_cases.map(c=>[c.category,c.case_kind,c.status,c.next_review_due_on])}/>
      <Table head={["Audit type","Outcome","Due"]}
        items={data.surveillance.map(a=>[a.kind,a.outcome,a.due_on])}/>
      <h4>Immutable decision history (new recorded transitions)</h4>
      <Table head={["Action","Previous state","Current state","Risk","Recorded"]}
        items={data.lifecycle_snapshots.map(s=>[s.action,s.previous_status,s.current_status,s.risk_level,s.occurred_at])}/>
      <h4>Indicator provenance and limits</h4><ul>{data.limitations.map((m,i)=><li key={i}>{m}</li>)}</ul>
      <small>Observed as of {data.as_of}. A blank indicator means no authoritative denominator or available record.</small>
    </div>}
  </section>;
}
