import React,{useCallback,useEffect,useState} from "react";
import {apiRequest} from "../../services/apiClient";
import {authHeaders} from "../../services/auth";
import {getApiBaseUrl} from "../../services/config";
import "./external-provider-portal.css";

const KINDS=["ALL","SUPPLIER","CONTRACTOR","SUBCONTRACTOR","SERVICE_PROVIDER",
  "CONSULTANT","LABORATORY","CALIBRATION_PROVIDER","OTHER"];
type Requirement={id:string;code:string;provider_kind:string;title:string;description:string;
  mandatory:boolean;expiry_required:boolean;form_manual_id:string|null;form_revision_id:string|null;
  enabled:boolean;retention_policy_ref:string|null;version:number};
type Submission={id:string;filename:string;status:string;evidence_type:string;
  related_kind:string;related_id:string|null;requirement_title:string|null;
  legal_name:string;supplier_id:number;email:string;sha256:string;size_bytes:number;
  valid_until:string|null;form_revision_id:string|null;dms_revision_id:string|null;
  qms_evidence_id:string|null;review_note:string|null;created_at:string};
type DmsOption={id:string;code:string;title:string;revision_id:string;rev_number:string};
type Decision="ACCEPTED"|"RETURNED"|"REJECTED";
const blank={code:"",provider_kind:"ALL",title:"",description:"",
  mandatory:false,expiry_required:false,form_manual_id:"",
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
  const refresh=useCallback(async()=>{
    const [policies,queue,docs]=await Promise.all([
      apiRequest<{items:Requirement[]}>(`${path}/requirements`,{cacheTtlMs:0}),
      apiRequest<{items:Submission[]}>(`${path}/submissions?limit=25&offset=${offset}`,{cacheTtlMs:0}),
      apiRequest<{items:DmsOption[]}>(`${path}/dms-options?limit=50`,{cacheTtlMs:0}),
    ]);
    setRequirements(policies.items);setSubmissions(queue.items);setDms(docs.items);
  },[path,offset]);
  useEffect(()=>{void refresh().catch(e=>setError(errorText(e)));},[refresh]);
  function loadRequirement(r:Requirement){
    setForm({code:r.code,provider_kind:r.provider_kind,title:r.title,
      description:r.description||"",mandatory:r.mandatory,expiry_required:r.expiry_required,
      form_manual_id:r.form_manual_id||"",form_revision_id:r.form_revision_id||"",
      enabled:r.enabled,retention_policy_ref:r.retention_policy_ref||""});
    setVersion(r.version);setSelectedDms(r.form_revision_id||"");
  }
  async function saveRequirement(event:React.FormEvent){
    event.preventDefault();setError("");setNotice("");
    const key=form.code.trim().toUpperCase();
    if(!/^[A-Z][A-Z0-9_]{1,63}$/.test(key)){setError("Enter an uppercase requirement code, at least two characters.");return;}
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
        <label><input type="checkbox" checked={form.expiry_required} onChange={e=>setForm({...form,expiry_required:e.target.checked})}/> Needs expiry</label>
        <label><input type="checkbox" checked={form.enabled} onChange={e=>setForm({...form,enabled:e.target.checked})}/> Enabled</label>
      </div>
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
    {!submissions.length&&<p>No submissions in this page.</p>}
    <label className="vendor-field"><span>Reason for selected outcome</span><textarea value={reason}
      minLength={8} rows={2} onChange={e=>setReason(e.target.value)}/></label>
    <label className="vendor-field"><span>Optional published DMS revision link when accepting</span>
      <select value={selectedDms} onChange={e=>setSelectedDms(e.target.value)}>
        <option value="">Evidence reference only — QMS will review independently</option>
        {dms.map(d=><option key={d.revision_id} value={d.revision_id}>{d.code} · {d.title} · {d.rev_number}</option>)}
      </select></label>
    {submissions.map(s=><div key={s.id} className="vendor-review-item">
      <strong>{s.legal_name} · {s.filename}</strong>
      <small>{s.requirement_title||s.evidence_type} · {s.size_bytes} bytes · {s.status}</small>
      <small>Submitted by {s.email} · {new Date(s.created_at).toLocaleDateString()}</small>
      <p>Original SHA-256: <code>{s.sha256}</code></p>
      <p>Validity until {s.valid_until||"not provided"} · Original form revision {s.form_revision_id||"not used"}</p>
      {s.review_note&&<p>Review: {s.review_note}</p>}
      {s.qms_evidence_id&&<p>Canonical QMS evidence ID: {s.qms_evidence_id} (separate verification required)</p>}
      {s.dms_revision_id&&<p>Exact linked DMS revision: {s.dms_revision_id}</p>}
      <div className="vendor-actions">
        <button type="button" disabled={busy===s.id} onClick={()=>void download(s)}>Download original</button>
        {s.status==="PENDING_REVIEW"&&<React.Fragment>
          <button type="button" disabled={busy===s.id||reason.trim().length<8} onClick={()=>void review(s,"ACCEPTED")}>Accept into QMS (pending verification)</button>
          <button type="button" disabled={busy===s.id||reason.trim().length<8} onClick={()=>void review(s,"RETURNED")}>Return for resubmission</button>
          <button type="button" disabled={busy===s.id||reason.trim().length<8} onClick={()=>void review(s,"REJECTED")}>Reject</button>
        </React.Fragment>}
      </div>
    </div>)}
    <div className="vendor-actions">
      <button disabled={!offset||Boolean(busy)} onClick={()=>setOffset(Math.max(0,offset-25))}>Previous</button>
      <button disabled={submissions.length<25||Boolean(busy)} onClick={()=>setOffset(offset+25)}>Next</button>
      <button onClick={()=>void refresh().catch(e=>setError(errorText(e)))}>Refresh</button>
    </div>
  </section>;
}
