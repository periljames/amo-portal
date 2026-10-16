import React,{useCallback,useEffect,useState} from "react";
import {apiRequest} from "../../services/apiClient";
import {authHeaders} from "../../services/auth";
import {getApiBaseUrl} from "../../services/config";
import "./external-provider-portal.css";

const CLASSES=[
  ["MAINTENANCE_AGREEMENT","Maintenance agreement"],
  ["SERVICE_LEVEL_AGREEMENT","Service-level agreement"],
  ["CONTRACT_AMENDMENT","Contract amendment"],
  ["CONTRACT_RENEWAL","Contract renewal evidence"],
  ["CONTRACT_TERMINATION","Contract termination or suspension record"],
  ["REGULATORY_APPROVAL","Regulatory approval certificate"],
  ["RATINGS_CAPABILITIES","Ratings and capability list"],
  ["INSURANCE_STATUTORY","Insurance and statutory evidence"],
  ["PROVIDER_QUALITY_MANUAL","Provider Quality manual and procedures"],
  ["QUALIFICATION_QUESTIONNAIRE","Supplier qualification questionnaire"],
  ["AUDIT_EVIDENCE","Audit evidence"],
  ["CORRECTIVE_ACTION_EVIDENCE","Corrective-action evidence"],
  ["PERSONNEL_TRAINING_EVIDENCE","Personnel training and qualification evidence"],
  ["CALIBRATION_CERTIFICATE","Calibration certificate"],
  ["TEST_CERTIFICATE","Test certificate"],
  ["COMPONENT_RELEASE_CERTIFICATE","Component release certificate"],
  ["CONFORMITY_DOCUMENT","Conformity document"],
  ["REPAIR_OVERHAUL_REPORT","Repair or overhaul report"],
  ["WORK_ORDER","Work order"],
  ["SIGNED_TECHNICAL_INSTRUCTION","Signed technical instruction"],
  ["AUTHORITY_CORRESPONDENCE","Authority correspondence and approval evidence"],
  ["CONTROLLED_FORM","Controlled form"],
  ["FORM_ACKNOWLEDGEMENT","Controlled acknowledgement"],
  ["RFQ_SPECIFICATION","Invited RFQ technical specification"],
  ["SUPPLIER_QUOTATION","Supplier quotation and revision"],
  ["PROFORMA_INVOICE","Supplier proforma invoice"],
  ["SUPPLIER_INVOICE","Supplier commercial invoice"],
  ["PACKING_LIST","Advance shipment packing list"],
  ["SHIPMENT_RELEASE","Shipment release and conformity certificate"],
  ["CREDIT_NOTE","Supplier credit or replacement note"],
  ["WARRANTY_CLAIM","Warranty claim record"],
  ["RMA_CORRESPONDENCE","Returns and RMA correspondence"],
] as const;
const KINDS=["ALL","SUPPLIER","CONTRACTOR","SUBCONTRACTOR","SERVICE_PROVIDER",
  "CONSULTANT","LABORATORY","CALIBRATION_PROVIDER","OTHER"];
type Requirement={id:string;code:string;provider_kind:string;title:string;description:string;
  mandatory:boolean;acknowledgement_required:boolean;expiry_required:boolean;reminder_days:number;form_manual_id:string|null;form_revision_id:string|null;
  enabled:boolean;retention_policy_ref:string|null;version:number};
type Submission={id:string;filename:string;status:string;evidence_type:string;
  related_kind:string;related_id:string|null;requirement_title:string|null;
  legal_name:string;supplier_id:number;email:string;sha256:string;size_bytes:number;
  valid_until:string|null;form_revision_id:string|null;form_acknowledged_at:string|null;dms_revision_id:string|null;
  qms_evidence_id:string|null;review_note:string|null;created_at:string;
  dms_evidence_asset_id:string|null;dms_retention_id:string|null;
  dms_retention_status:string|null;dms_legal_hold:boolean|null;dms_retention_until:string|null};
type DmsOption={id:string;code:string;title:string;revision_id:string;rev_number:string};
type Decision="ACCEPTED"|"RETURNED"|"REJECTED";
const blank={code:"",provider_kind:"ALL",title:"",description:"",
  mandatory:false,acknowledgement_required:false,expiry_required:false,reminder_days:0,form_manual_id:"",
  form_revision_id:"",enabled:true,retention_policy_ref:""};
function errorText(error:unknown){return error instanceof Error?error.message:"Request failed";}
export default function ExternalProviderDocumentsReview({amoCode,manager}:{
  amoCode:string;manager:boolean;
}){
  const path=`/api/maintenance/${encodeURIComponent(amoCode)}/quality/external-accounts/documents`;
  const [requirements,setRequirements]=useState<Requirement[]>([]);
  const [submissions,setSubmissions]=useState<Submission[]>([]);
  const [dms,setDms]=useState<DmsOption[]>([]);
  const [form,setForm]=useState(blank);
  const [version,setVersion]=useState<number|null>(null);
  const [reason,setReason]=useState("");
  const [selectedDms,setSelectedDms]=useState("");
  const [busy,setBusy]=useState("");
  const [error,setError]=useState("");const [notice,setNotice]=useState("");
  const [offset,setOffset]=useState(0);
  const [canRegisterDms,setCanRegisterDms]=useState(false);
  const [canQualityReview,setCanQualityReview]=useState(false);
  const [retentionManual,setRetentionManual]=useState("");
  const [retentionClass,setRetentionClass]=useState("");
  const [retentionUntil,setRetentionUntil]=useState("");
  const [retentionReason,setRetentionReason]=useState("");
  const [history,setHistory]=useState<Record<string,{action:string;occurred_at:string;details_json:unknown;actor_user_id:string|null}[]>>({});
  const [historyOpen,setHistoryOpen]=useState("");
  const refresh=useCallback(async()=>{
    const [policies,queue,docs,permissions]=await Promise.all([
      apiRequest<{items:Requirement[]}>(`${path}/requirements`,{cacheTtlMs:0}),
      apiRequest<{items:Submission[]}>(`${path}/submissions?limit=25&offset=${offset}`,{cacheTtlMs:0}),
      apiRequest<{items:DmsOption[]}>(`${path}/dms-options?limit=50`,{cacheTtlMs:0}),
      apiRequest<{document_controller:boolean;quality_reviewer:boolean}>(`${path}/permissions`,{cacheTtlMs:0}),
    ]);
    setRequirements(policies.items);setSubmissions(queue.items);setDms(docs.items);
    setCanRegisterDms(permissions.document_controller);
    setCanQualityReview(permissions.quality_reviewer);
  },[path,offset]);
  useEffect(()=>{void refresh().catch(e=>setError(errorText(e)));},[refresh]);
  function loadRequirement(r:Requirement){
    setForm({code:r.code,provider_kind:r.provider_kind,title:r.title,
      description:r.description||"",mandatory:r.mandatory,acknowledgement_required:r.acknowledgement_required,
       expiry_required:r.expiry_required,reminder_days:r.reminder_days||0,
      form_manual_id:r.form_manual_id||"",form_revision_id:r.form_revision_id||"",
      enabled:r.enabled,retention_policy_ref:r.retention_policy_ref||""});
    setVersion(r.version);setSelectedDms(r.form_revision_id||"");
  }
  async function saveRequirement(event:React.FormEvent){
    event.preventDefault();setError("");setNotice("");
    const key=form.code.trim().toUpperCase();
    if(!/^[A-Z][A-Z0-9_]{1,47}$/.test(key)){setError("Enter an uppercase requirement code, at least two characters.");return;}
    setBusy("policy");
    try{
      await apiRequest(`${path}/requirements/${encodeURIComponent(key)}`,{
        method:"PUT",body:JSON.stringify({...form,code:key,
          form_manual_id:form.form_manual_id||null,form_revision_id:form.form_revision_id||null,
          retention_policy_ref:form.retention_policy_ref||null,expected_version:version}),
      });
      setNotice("Tenant document requirement saved. It does not grant supplier approval.");
      setForm(blank);setVersion(null);setSelectedDms("");
      await refresh();
    }catch(e){setError(errorText(e));}finally{setBusy("");}
  }
  async function review(s:Submission,decision:Decision){
    if(reason.trim().length<8){setError("Enter at least 8 characters explaining the decision.");return;}
    const picked=dms.find(doc=>doc.revision_id===selectedDms);
    setBusy(s.id);setError("");setNotice("");
    try{
      await apiRequest(`${path}/submissions/${encodeURIComponent(s.id)}/review`,{
        method:"POST",body:JSON.stringify({decision,reason:reason.trim(),
          dms_manual_id:decision==="ACCEPTED"?picked?.id||null:null,
          dms_revision_id:decision==="ACCEPTED"?picked?.revision_id||null:null}),
      });
      setReason("");setSelectedDms("");setNotice(
        decision==="ACCEPTED"?
        "Submission accepted into the controlled record. QMS evidence remains pending independent verification.":
        `Submission ${decision.toLowerCase()} with documented reason.`);
      await refresh();
    }catch(e){setError(errorText(e));}finally{setBusy("");}
  }
  async function download(row:Submission){
    setBusy(row.id);setError("");
    try{
      const response=await fetch(`${getApiBaseUrl()}${path}/submissions/${encodeURIComponent(row.id)}/original`,{
        headers:new Headers(authHeaders()),credentials:"include",cache:"no-store"});
      if(!response.ok)throw new Error(`Original file access denied (${response.status})`);
      const url=URL.createObjectURL(await response.blob());
      const a=document.createElement("a");a.href=url;a.download=row.filename;
      document.body.appendChild(a);a.click();a.remove();
      window.setTimeout(()=>URL.revokeObjectURL(url),2000);
    }catch(e){setError(errorText(e));}finally{setBusy("");}
  }
  async function loadHistory(row:Submission){
    if(historyOpen===row.id){setHistoryOpen("");return;}
    setBusy(row.id);setError("");
    try{
      const response=await apiRequest<{items:{action:string;occurred_at:string;details_json:unknown;actor_user_id:string|null}[]}>(
        `${path}/submissions/${encodeURIComponent(row.id)}/history`,{cacheTtlMs:0});
      setHistory(v=>({...v,[row.id]:response.items}));setHistoryOpen(row.id);
    }catch(e){setError(errorText(e));}finally{setBusy("");}
  }
  async function registerDms(row:Submission){
    if(!retentionManual||!retentionClass.trim()||retentionReason.trim().length<8){
      setError("Choose a DMS manual, an approved retention class and a reason of at least 8 characters.");return;
    }
    setBusy(row.id);setError("");setNotice("");
    try{
      await apiRequest(`${path}/submissions/${encodeURIComponent(row.id)}/register-dms`,{
        method:"POST",body:JSON.stringify({manual_id:retentionManual,
          retention_class:retentionClass.trim().toUpperCase(),
          retention_until:retentionUntil?new Date(retentionUntil+"T23:59:59Z").toISOString():null,
          reason:retentionReason.trim()}),
      });
      setNotice("Exact original registered in DMS evidence assets and its existing retention/disposition register.");
      setRetentionReason("");await refresh();
    }catch(e){setError(errorText(e));}finally{setBusy("");}
  }
  return <section className="vendor-card">
    <h2>Controlled provider documents & forms</h2>
    <p>Configure requirements by provider category, review secure staging, link exact published DMS revisions and route accepted evidence to QMS. Only QMS verifies evidence and provider eligibility.</p>
    {error&&<p role="alert" className="vendor-error">{error}</p>}
    {notice&&<p role="status" className="vendor-success">{notice}</p>}
    <h3>Tenant document requirements</h3>
    {!requirements.length&&<p>No document policies configured. Documents are not universally mandatory.</p>}
    <div className="vendor-actions" style={{flexWrap:"wrap"}}>
      {requirements.map(r=><button type="button" key={r.id} onClick={()=>loadRequirement(r)}>
        {r.provider_kind} / {r.code} · v{r.version}</button>)}
    </div>
    {manager&&<form className="vendor-form" onSubmit={e=>void saveRequirement(e)}>
      <h3>{version?"Edit existing requirement":"Add category-specific requirement"}</h3>
      {!version&&<label className="vendor-field"><span>Start from a supported document class (optional)</span>
        <select defaultValue="" onChange={e=>{
          const selected=CLASSES.find(([code])=>code===e.target.value);
          if(selected)setForm({...form,code:selected[0],title:selected[1]});
        }}><option value="">Custom document class</option>
          {CLASSES.map(([code,title])=><option key={code} value={code}>{title}</option>)}
        </select></label>}
      <div className="vendor-fields">
        <label className="vendor-field"><span>Provider category</span><select value={form.provider_kind}
          disabled={Boolean(version)} onChange={e=>setForm({...form,provider_kind:e.target.value})}>
          {KINDS.map(k=><option key={k} value={k}>{k}</option>)}</select></label>
        <label className="vendor-field"><span>Requirement code</span><input value={form.code}
          disabled={Boolean(version)} required onChange={e=>setForm({...form,code:e.target.value.toUpperCase()})}/></label>
        <label className="vendor-field"><span>Requirement title</span><input value={form.title} required
          onChange={e=>setForm({...form,title:e.target.value})}/></label>
        <label className="vendor-field"><span>Description and evidence instructions</span>
          <textarea value={form.description} rows={3} onChange={e=>setForm({...form,description:e.target.value})}/></label>
      </div>
      <div className="vendor-actions">
        <label><input type="checkbox" checked={form.mandatory} onChange={e=>setForm({...form,mandatory:e.target.checked})}/> Required for this category</label>
        <label><input type="checkbox" checked={form.acknowledgement_required}
          onChange={e=>setForm({...form,acknowledgement_required:e.target.checked})}/>
          Require explicit read-and-understood attestation for the exact published form revision</label>
        <label><input type="checkbox" checked={form.expiry_required} onChange={e=>setForm({...form,expiry_required:e.target.checked})}/> Needs expiry</label>
        <label><input type="checkbox" checked={form.enabled} onChange={e=>setForm({...form,enabled:e.target.checked})}/> Enabled</label>
      </div>
      <label className="vendor-field"><span>Days before evidence expiry to alert Quality (0 = due date)</span>
        <input type="number" min={0} max={365} value={form.reminder_days}
          onChange={e=>setForm({...form,reminder_days:Number(e.target.value)||0})}/></label>
      <label className="vendor-field"><span>Approved form (published DMS revision)</span>
        <select value={form.form_revision_id||""} onChange={e=>{
          const option=dms.find(d=>d.revision_id===e.target.value);
          setForm({...form,form_manual_id:option?.id||"",form_revision_id:option?.revision_id||""});
        }}>
          <option value="">No controlled form attached</option>
          {dms.map(d=><option key={d.revision_id} value={d.revision_id}>{d.code} · {d.title} · {d.rev_number}</option>)}
        </select></label>
      <label className="vendor-field"><span>Existing DMS retention policy reference (no default imposed)</span>
        <input value={form.retention_policy_ref} onChange={e=>setForm({...form,retention_policy_ref:e.target.value})}/></label>
      <div className="vendor-actions">
        <button type="submit" disabled={busy==="policy"}>{busy==="policy"?"Saving…":"Save requirement"}</button>
        {version&&<button type="button" onClick={()=>{setForm(blank);setVersion(null);}}>Create another</button>}
      </div>
    </form>}
    <h3>Submitted originals awaiting controlled review</h3>
    {canRegisterDms&&<div className="vendor-form">
      <h4>Document Control evidence retention</h4>
      <p>Only Document Control registers originals and controls retention. Registration does not approve Quality evidence.</p>
      <label className="vendor-field">Governed DMS manual<select value={retentionManual} onChange={e=>setRetentionManual(e.target.value)}>
        <option value="">Choose a published DMS manual</option>
        {dms.map(d=><option key={d.revision_id} value={d.id}>{d.code} · {d.title}</option>)}
      </select></label>
      <label className="vendor-field">DMS retention class<input required maxLength={64} value={retentionClass}
        onChange={e=>setRetentionClass(e.target.value)}/></label>
      <label className="vendor-field">Retain until (leave blank only when policy specifies no end date)<input type="date"
        value={retentionUntil} onChange={e=>setRetentionUntil(e.target.value)}/></label>
      <label className="vendor-field">Registration reason<textarea minLength={8} rows={2} value={retentionReason}
        onChange={e=>setRetentionReason(e.target.value)}/></label>
    </div>}
    {!submissions.length&&<p>No submissions in this page.</p>}
    {canQualityReview&&<label className="vendor-field"><span>Reason for selected outcome</span><textarea value={reason}
      minLength={8} rows={2} onChange={e=>setReason(e.target.value)}/></label>}
    {canQualityReview&&<label className="vendor-field"><span>Optional published DMS revision link when accepting</span>
      <select value={selectedDms} onChange={e=>setSelectedDms(e.target.value)}>
        <option value="">Evidence reference only — QMS will review independently</option>
        {dms.map(d=><option key={d.revision_id} value={d.revision_id}>{d.code} · {d.title} · {d.rev_number}</option>)}
      </select></label>}
    {submissions.map(s=><div key={s.id} className="vendor-review-item">
      <strong>{s.legal_name} · {s.filename}</strong>
      <small>{s.requirement_title||s.evidence_type} · {s.size_bytes} bytes · {s.status}</small>
      <small>Submitted by {s.email} · {new Date(s.created_at).toLocaleDateString()}</small>
      <p>Original SHA-256: <code>{s.sha256}</code></p>
      <p>Validity until {s.valid_until||"not provided"} · Original form revision {s.form_revision_id||"not used"}</p>
      {s.form_revision_id&&<p>Member's acknowledgement of exact form revision:
        {s.form_acknowledged_at?new Date(s.form_acknowledged_at).toLocaleString():"Not recorded / not required by policy"}</p>}
      {s.review_note&&<p>Review: {s.review_note}</p>}
      {s.qms_evidence_id&&<p>Canonical QMS evidence ID: {s.qms_evidence_id} (separate verification required)</p>}
      {s.dms_revision_id&&<p>Exact linked DMS revision: {s.dms_revision_id}</p>}
      <p>DMS retention: {s.dms_retention_id?(s.dms_retention_status||"Registered"):"Not registered"}
        {s.dms_retention_id&&` · Legal hold: ${s.dms_legal_hold?"Yes":"No"} · Until ${s.dms_retention_until||"No prescribed date"}`}
        {" "}(legal hold and disposal are controlled in DMS)</p>
      <div className="vendor-actions">
        <button type="button" disabled={busy===s.id} onClick={()=>void download(s)}>Download original</button>
        <button type="button" disabled={busy===s.id} onClick={()=>void loadHistory(s)}>
          {historyOpen===s.id?"Hide history":"Review & provenance history"}</button>
        {canRegisterDms&&!s.dms_retention_id&&s.status!=="PENDING_REVIEW"&&<button type="button"
          disabled={busy===s.id||!retentionManual||!retentionClass.trim()||retentionReason.trim().length<8}
          onClick={()=>void registerDms(s)}>Register original in DMS</button>}
        {canQualityReview&&s.status==="PENDING_REVIEW"&&<React.Fragment>
          <button type="button" disabled={busy===s.id||reason.trim().length<8} onClick={()=>void review(s,"ACCEPTED")}>Accept into QMS (pending verification)</button>
          <button type="button" disabled={busy===s.id||reason.trim().length<8} onClick={()=>void review(s,"RETURNED")}>Return for resubmission</button>
          <button type="button" disabled={busy===s.id||reason.trim().length<8} onClick={()=>void review(s,"REJECTED")}>Reject</button>
        </React.Fragment>}
      </div>
      {historyOpen===s.id&&<div className="vendor-history" aria-label="Immutable submission event history">
        {(history[s.id]||[]).map((event,index)=><p key={index}>
          {new Date(event.occurred_at).toLocaleString()} · {event.action} · Actor {event.actor_user_id||"Provider"}
          <code>{JSON.stringify(event.details_json)}</code></p>)}
      </div>}
    </div>)}
    <div className="vendor-actions">
      <button disabled={!offset||Boolean(busy)} onClick={()=>setOffset(Math.max(0,offset-25))}>Previous</button>
      <button disabled={submissions.length<25||Boolean(busy)} onClick={()=>setOffset(offset+25)}>Next</button>
      <button onClick={()=>void refresh().catch(e=>setError(errorText(e)))}>Refresh</button>
    </div>
  </section>;
}
