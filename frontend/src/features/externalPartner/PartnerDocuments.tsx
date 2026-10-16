import React,{useEffect,useRef,useState} from "react";
import type {PartnerProps} from "./ExternalPartnerPage";
import {friendlyDate,label,partnerRequest,partnerUrl,type Contract,type Page} from "./partnerApi";
import {ActionNotice,Section,State,Status,usePartnerLoad} from "./PartnerPrimitives";

type Requirement={id:string;code:string;title:string;description:string;mandatory:boolean;
  expiry_required:boolean;acknowledgement_required:boolean;acknowledged_by_me:boolean;
  reminder_days:number;form_manual_id:string|null;form_revision_id:string|null;
  form_available:boolean;version:number};
type Submission={id:string;filename:string;evidence_type:string;status:string;
  requirement_id:string|null;related_kind:string;related_id:string|null;
  supersedes_submission_id:string|null;form_revision_id:string|null;
  valid_until:string|null;created_at:string;review_note:string|null;
  qms_evidence_id:string|null;dms_revision_id:string|null;sha256:string};
type ResponsePage={items:Submission[];limit:number;offset:number;has_more:boolean};

function saveBlob(blob:Blob,filename:string){
  const url=URL.createObjectURL(blob);
  const link=document.createElement("a");link.href=url;link.download=filename;
  document.body.appendChild(link);link.click();link.remove();
  window.setTimeout(()=>URL.revokeObjectURL(url),2000);
}
export default function PartnerDocuments({tenant,csrf,capabilities}:PartnerProps){
  const [refresh,setRefresh]=useState(0);const [offset,setOffset]=useState(0);
  const [requirementId,setRequirementId]=useState("");
  const [file,setFile]=useState<File|null>(null);
  const [related,setRelated]=useState("PROVIDER");const [relatedId,setRelatedId]=useState("");
  const [supersedes,setSupersedes]=useState("");const [validUntil,setValidUntil]=useState("");
  const [busy,setBusy]=useState(false);const [progress,setProgress]=useState(0);
  const [notice,setNotice]=useState("");const [error,setError]=useState("");
  const [acknowledgeChecked,setAcknowledgeChecked]=useState(false);
  const [acknowledging,setAcknowledging]=useState("");
  const pendingKey=useRef("");const xhrRef=useRef<XMLHttpRequest|null>(null);
  const requirements=usePartnerLoad((signal)=>partnerRequest<{items:Requirement[]}>(tenant,
    "documents/requirements",{signal}),`${tenant}:${refresh}`);
  const submissions=usePartnerLoad((signal)=>partnerRequest<ResponsePage>(tenant,
    `documents/submissions?limit=25&offset=${offset}`,{signal}),`${tenant}:${offset}:${refresh}`);
  const assignments=usePartnerLoad((signal)=>partnerRequest<{items:{id:string}[]}>(tenant,
    "documents/assignment-scopes",{signal}),`${tenant}:${refresh}:assignments`);
  const contracts=usePartnerLoad((signal)=>capabilities.includes("contract.read")?
    partnerRequest<Page<Contract>>(tenant,"contracts?limit=50",{signal}):
    Promise.resolve({items:[],limit:50,offset:0,has_more:false}),`${tenant}:${refresh}`);
  useEffect(()=>()=>xhrRef.current?.abort(),[]);
  const current=requirements.value?.items.find(r=>r.id===requirementId);
  const prior=(submissions.value?.items||[]).filter(s=>s.requirement_id===requirementId &&
     s.related_kind===related && (s.related_id||"")===(relatedId||""));
  const supersededIds=new Set((submissions.value?.items||[]).map(s=>s.supersedes_submission_id).filter(Boolean));

  async function getOriginal(path:string,filename:string){
    setError("");setNotice("");
    try{
      const response=await fetch(partnerUrl(tenant,path),{credentials:"include",cache:"no-store"});
      if(!response.ok)throw new Error(`Controlled file access denied (${response.status})`);
      const mime=response.headers.get("Content-Type")||"";
      const ext=mime.includes("wordprocessingml")?".docx":mime.includes("application/pdf")?".pdf":
        mime.includes("image/png")?".png":mime.includes("image/jpeg")?".jpg":mime.includes("text/plain")?".txt":"";
      const resolved=/\\.[a-z0-9]{2,5}$/i.test(filename)?filename:filename+ext;
      saveBlob(await response.blob(),resolved);
    }catch(e){setError(e instanceof Error?e.message:"File could not be downloaded");}
  }
  async function acknowledgeForm(item:Requirement){
    if(!acknowledgeChecked||!item.form_available){setError("Open the granted form and confirm the declaration.");return;}
    setAcknowledging(item.id);setError("");setNotice("");
    try{
      await partnerRequest(tenant,`documents/requirements/${encodeURIComponent(item.id)}/acknowledge`,{
        method:"POST",csrf,body:{accepted:true,declaration:
          "I confirm that I have read and understood the controlled form identified by this exact published revision."},
      });
      setAcknowledgeChecked(false);setNotice("Read-and-understood acknowledgement recorded for the exact form revision.");
      setRefresh(v=>v+1);
    }catch(e){setError(e instanceof Error?e.message:"Acknowledgement was not recorded");}
    finally{setAcknowledging("");}
  }
  function upload(e:React.FormEvent){
    e.preventDefault();
    if(!file||!current||busy)return;
    if(current.acknowledgement_required&&!current.acknowledged_by_me){
      setError("Acknowledge the current controlled form before uploading this document.");return;
    }
    if(!pendingKey.current)pendingKey.current=crypto.randomUUID().replace(/-/g,"");
    const key=pendingKey.current;
    const xhr=new XMLHttpRequest();xhrRef.current=xhr;
    setBusy(true);setError("");setNotice("");setProgress(0);
    xhr.open("POST",partnerUrl(tenant,"documents/submissions"));xhr.withCredentials=true;
    xhr.setRequestHeader("X-External-CSRF",csrf);
    xhr.upload.onprogress=event=>{if(event.lengthComputable)setProgress(Math.round(event.loaded*100/event.total));};
    xhr.onerror=()=>{setError("Connection interrupted. Retry with the same file to avoid a duplicate.");
      setBusy(false);xhrRef.current=null;};
    xhr.onabort=()=>{setError("Transfer cancelled. No submission confirmation was received.");
      setBusy(false);xhrRef.current=null;};
    xhr.onload=()=>{
      const result=(()=>{try{return JSON.parse(xhr.responseText) as {detail?:string;filename?:string};}
        catch{return {};}})();
      if(xhr.status>=200&&xhr.status<300){
        setNotice(`${result.filename||file.name} is in controlled review. Submission does not approve this provider.`);
        pendingKey.current="";setFile(null);setSupersedes("");setValidUntil("");setProgress(100);
        setRefresh(v=>v+1);
      }else setError(result.detail||`Upload rejected (${xhr.status}). Retry after correction.`);
      setBusy(false);xhrRef.current=null;
    };
    const payload=new FormData();
    payload.append("file",file);payload.append("requirement_id",requirementId);
    payload.append("related_kind",related);
    payload.append("related_id",related==="PROVIDER"?"":relatedId);
    payload.append("supersedes_submission_id",supersedes);
    payload.append("idempotency_key",key);
    if(validUntil)payload.append("valid_until",validUntil);
    xhr.send(payload);
  }
  const refreshAll=()=>setRefresh(v=>v+1);
  const resetRetry=()=>{pendingKey.current="";setProgress(0);};
  return <div className="partner-stack">
    <Section title="Required documents and approved forms"
      description="Your AMO controls these requirements by provider category. Only documents released to your account are downloadable.">
      <State pending={requirements.pending} error={requirements.error} retry={requirements.reload}/>
      {!requirements.value?.items.length&&<p className="partner-empty">No document requirements have been configured for your provider category. Contact Quality before sending files.</p>}
      {requirements.value?.items.map(r=><div key={r.id} className="partner-row">
        <div><strong>{r.title}{r.mandatory?" · Required":""}</strong>
          <small>{r.code} · Policy version {r.version}{r.expiry_required?" · Expiry date required":""}</small>
          {r.description&&<small>{r.description}</small>}
          {r.acknowledgement_required&&<small>Form acknowledgement:
            {r.acknowledged_by_me?" Recorded for this revision":" Required before submission"}</small>}
          {r.form_revision_id&&<small>Approved form revision: {r.form_revision_id}</small>}
        </div><div className="partner-buttons">
          {r.form_available&&<button type="button" onClick={()=>void getOriginal(
            `documents/requirements/${encodeURIComponent(r.id)}/form`,`${r.code}-approved-form`)}>
            Download current form</button>}
          {!r.form_available&&r.form_revision_id&&<small>Form access not granted</small>}
          {r.acknowledgement_required&&!r.acknowledged_by_me&&r.form_available&&<div>
            <label><input type="checkbox" checked={acknowledgeChecked}
              onChange={e=>setAcknowledgeChecked(e.target.checked)}/>
              I have opened, read and understood the controlled form revision shown.</label>
            <button type="button" disabled={!acknowledgeChecked||acknowledging===r.id}
              onClick={()=>void acknowledgeForm(r)}>
              {acknowledging===r.id?"Recording…":"Record read-and-understood acknowledgement"}</button>
          </div>}
        </div>
      </div>)}
    </Section>
    {capabilities.includes("document.submit")&&<Section title="Submit a controlled response"
      description="Attach a PDF, DOCX, JPEG, PNG or UTF-8 text file (maximum 20 MB). Your file is scanned and staged before Quality review.">
      <form className="partner-form" onSubmit={upload}>
        <label>Requirement
          <select required value={requirementId} onChange={e=>{setRequirementId(e.target.value);setSupersedes("");resetRetry();}}>
            <option value="">Select a document requirement</option>
            {requirements.value?.items.map(r=><option key={r.id} value={r.id}>{r.title}</option>)}
          </select></label>
        <label>Linked scope<select value={related} onChange={e=>{setRelated(e.target.value);setRelatedId("");setSupersedes("");resetRetry();}}>
          <option value="PROVIDER">Provider-level record</option>
          {contracts.value?.items.length?<option value="CONTRACT">Assigned agreement</option>:null}
          {assignments.value?.items.length?<option value="ASSIGNMENT">Assigned audit or QMS work</option>:null}
        </select></label>
        {related==="CONTRACT"&&<label>Assigned agreement<select required value={relatedId} onChange={e=>{setRelatedId(e.target.value);setSupersedes("");resetRetry();}}>
          <option value="">Choose assigned agreement</option>
          {contracts.value?.items.map(c=><option key={c.id} value={c.id}>{c.contract_number} · {c.title}</option>)}
        </select></label>}
        {related==="ASSIGNMENT"&&<label>Assigned audit<select required value={relatedId}
          onChange={e=>{setRelatedId(e.target.value);setSupersedes("");resetRetry();}}>
          <option value="">Choose authorized audit assignment</option>
          {assignments.value?.items.map(a=><option key={a.id} value={a.id}>{a.id}</option>)}
        </select></label>}
        <label>Replace earlier submission (optional)<select value={supersedes} onChange={e=>{setSupersedes(e.target.value);resetRetry();}}>
          <option value="">First submission</option>
          {prior.map(s=><option key={s.id} value={s.id}>{s.filename} · {label(s.status)} · {friendlyDate(s.created_at)}</option>)}
        </select></label>
        <label>Evidence expiry{current?.expiry_required?" (required)":""}
          <input type="date" required={Boolean(current?.expiry_required)} value={validUntil}
            onChange={e=>{setValidUntil(e.target.value);resetRetry();}}/></label>
        <label>Source document<input type="file" required={!file}
          accept=".pdf,.docx,.png,.jpg,.jpeg,.txt"
          onChange={e=>{setFile(e.target.files?.[0]||null);resetRetry();}}/></label>
        {busy&&<div className="partner-progress"><progress max={100} value={progress}/><span>{progress}% uploaded</span></div>}
        <div className="partner-buttons"><button className="partner-primary" disabled={!current||!file||busy||(related!=="PROVIDER"&&!relatedId)||
             (current.acknowledgement_required&&!current.acknowledged_by_me)}>
          {busy?"Uploading…":"Submit for controlled review"}</button>
          {busy&&<button type="button" onClick={()=>xhrRef.current?.abort()}>Cancel transfer</button>}
          {!busy&&file&&error&&<button type="button" onClick={resetRetry}>Start a new upload attempt</button>}
        </div>
      </form>
    </Section>}
    <Section title="Document submission history" description="Original evidence, previous revisions and Quality feedback remain available when a provider agreement ends.">
      <State pending={submissions.pending} error={submissions.error} retry={submissions.reload}/>
      {submissions.value?.items.map(s=><div key={s.id} className="partner-row">
        <div><strong>{s.filename}</strong>
          <small>{s.evidence_type} · {friendlyDate(s.created_at)} · {s.sha256.slice(0,12)}…</small>
          {s.form_revision_id&&<small>Form revision: {s.form_revision_id}</small>}
          {s.qms_evidence_id&&<small>QMS evidence reference: {s.qms_evidence_id} (verification separate)</small>}
          {s.dms_revision_id&&<small>Linked DMS revision: {s.dms_revision_id}</small>}
          {supersededIds.has(s.id)&&<small>Later submission recorded — retained as history</small>}
          {s.review_note&&<small>Review: {s.review_note}</small>}
        </div><div className="partner-buttons"><Status value={s.status}/>
          <button type="button" onClick={()=>void getOriginal(
            `documents/submissions/${encodeURIComponent(s.id)}/original`,s.filename)}>Original</button>
        </div>
      </div>)}
      {submissions.value&&!submissions.value.items.length&&<p className="partner-empty">No document submissions have been recorded.</p>}
      <div className="partner-buttons">
        <button disabled={!offset} onClick={()=>setOffset(Math.max(0,offset-25))}>Previous</button>
        <button disabled={!submissions.value?.has_more} onClick={()=>setOffset(offset+25)}>Next</button>
        <button type="button" onClick={refreshAll}>Refresh</button>
      </div>
    </Section>
    <ActionNotice value={error} error/><ActionNotice value={notice}/>
  </div>;
}
