import React,{useEffect,useRef,useState} from "react";
import type {PartnerProps} from "./ExternalPartnerPage";
import {friendlyDate,partnerRequest,partnerUpload,type QualityPage} from "./partnerApi";
import {ActionNotice,Section,State,Status,usePartnerLoad} from "./PartnerPrimitives";
type Car=QualityPage["cars"]["items"][number];
type AuditDocumentRequest=QualityPage["document_requests"]["items"][number];
type Draft={containment_action:string;root_cause:string;corrective_action:string;preventive_action:string;evidence_submission_id:string};
const empty:Draft={containment_action:"",root_cause:"",corrective_action:"",preventive_action:"",evidence_submission_id:""};
export default function PartnerQuality({tenant,csrf,capabilities}:PartnerProps){
  const [offset,setOffset]=useState(0);
  const data=usePartnerLoad((signal)=>partnerRequest<QualityPage>(tenant,
    `quality?limit=15&offset=${offset}`,{signal}),`${tenant}:${offset}`);
  const [activeCar,setActiveCar]=useState<Car|null>(null);
  const [carRequirement,setCarRequirement]=useState("");
  const configuredRequirements=usePartnerLoad(signal=>partnerRequest<{items:{id:string;code:string;title:string}[]}>(
    tenant,"documents/requirements",{signal}),tenant+":controlled-evidence-classes");
  const carClasses=(configuredRequirements.value?.items||[]).filter(x=>
    x.code==="CORRECTIVE_ACTION_EVIDENCE"||x.code==="AUDIT_EVIDENCE");
  const [activeRequest,setActiveRequest]=useState<AuditDocumentRequest|null>(null);
  const [requestFile,setRequestFile]=useState<File|null>(null);
  const [requestComment,setRequestComment]=useState("");
  const [draft,setDraft]=useState<Draft>(empty);
  const [busy,setBusy]=useState(false);const [error,setError]=useState("");
  const [notice,setNotice]=useState("");const [file,setFile]=useState<File|null>(null);
  const [progress,setProgress]=useState(0);const abortRef=useRef<AbortController|null>(null);
  useEffect(()=>()=>abortRef.current?.abort(),[]);
  const canSubmit=capabilities.includes("capa.respond");
  const canSubmitRequests=capabilities.includes("document.submit")&&capabilities.includes("task.read");
  const uploadRequestedDocument=(event:React.FormEvent)=>{
    event.preventDefault();if(!activeRequest||!requestFile)return;
    const controller=new AbortController();abortRef.current=controller;
    setBusy(true);setProgress(0);setError("");setNotice("");
    void partnerUpload(tenant,csrf,requestFile,{
      related_kind:"DOCUMENT_REQUEST",request_id:activeRequest.id,
      response_comment:requestComment.trim(),
    },setProgress,controller.signal)
      .then(result=>{
        setNotice(`${result.filename} uploaded into the governed QMS document request. Quality review is still required.`);
        setActiveRequest(null);setRequestFile(null);setRequestComment("");data.reload();
      })
      .catch(reason=>{
        if(!controller.signal.aborted)setError(reason instanceof Error?reason.message:"QMS document upload failed");
      }).finally(()=>{abortRef.current=null;setBusy(false);});
  };
  const upload=(event:React.FormEvent)=>{
    event.preventDefault();if(!file||!activeCar)return;
    if(!carRequirement||!carClasses.some(x=>x.id===carRequirement)){
      setError("Select a Quality-configured corrective-action evidence class.");return;
    }
    const controller=new AbortController();abortRef.current=controller;
    setError("");setNotice("");setBusy(true);setProgress(0);
    void partnerUpload(tenant,csrf,file,{requirement_id:carRequirement,
      related_kind:"ASSIGNMENT",related_id:activeCar.assignment_id},setProgress,controller.signal)
      .then(r=>{setNotice(`File ${r.filename} received. Quality must review and accept it before this CAR can be submitted with the evidence reference.`);
        setFile(null);data.reload();})
      .catch(e=>{if(!controller.signal.aborted)setError(e instanceof Error?e.message:"Upload was not accepted");})
      .finally(()=>{setBusy(false);abortRef.current=null;});
  };
  const submit=(event:React.FormEvent)=>{
    event.preventDefault();if(!activeCar)return;
    setBusy(true);setError("");setNotice("");
    void partnerRequest<{status:string}>(tenant,`quality/cars/${encodeURIComponent(activeCar.id)}/submit`,{
      method:"POST",csrf,body:{...draft,evidence_submission_id:draft.evidence_submission_id||null},
    }).then(()=>{setNotice("Corrective-action response submitted to the authoritative QMS CAR review queue.");
      setActiveCar(null);setDraft(empty);data.reload();
    }).catch(e=>setError(e instanceof Error?e.message:"The CAR submission was not accepted")).finally(()=>setBusy(false));
  };
  return <div className="partner-stack">
    <State pending={data.pending} error={data.error} retry={data.reload}/>
    {data.value&&<>
      <Section title="Assigned audit notices" description="Only Quality-issued, delivered or acknowledged audit notices for your assigned audits are shown.">
        {data.value.notices.items.map(x=><div className="partner-row" key={x.id}>
          <div><strong>{x.audit_ref} · {x.subject}</strong><small>Issued notice Rev {x.revision_no} · {friendlyDate(x.notice_date)}</small></div>
          <Status value={x.status}/></div>)}
        {!data.value.notices.items.length&&<p className="partner-empty">No released notices for your current assignment.</p>}
      </Section>
      <Section title="Document requests" description="Requests are controlled by the audit. Upload supporting records through the evidence facility when authorized.">
        {data.value.document_requests.items.map(x=><div className="partner-row" key={x.id}>
          <div><strong>{x.audit_ref} · {x.title}</strong>
            {x.description&&<small>{x.description}</small>}<small>Due {friendlyDate(x.due_date)}</small>
            {canSubmitRequests&&!["ACCEPTED","WAIVED"].includes(x.status)&&
              <button type="button" disabled={busy} onClick={()=>{
                setActiveRequest(x);setRequestFile(null);setRequestComment("");setError("");setNotice("");
              }}>Submit requested document</button>}
          </div><Status value={x.status}/>
        </div>)}
        {!data.value.document_requests.items.length&&<p className="partner-empty">No document requests assigned for display.</p>}
        {activeRequest&&canSubmitRequests&&<form className="partner-form" onSubmit={uploadRequestedDocument}>
          <h3>QMS document request: {activeRequest.title}</h3>
          <p className="partner-muted">This upload goes directly into the existing authoritative audit request history. It does not approve the evidence.</p>
          <label>Requested file<input type="file" required accept=".pdf,.docx,.doc,.xlsx,.xls,.csv,.txt,.png,.jpg,.jpeg,.webp"
            onChange={event=>setRequestFile(event.target.files?.[0]||null)}/></label>
          <label>Response comment<textarea maxLength={4000} rows={2} value={requestComment}
            onChange={event=>setRequestComment(event.target.value)}/></label>
          {busy&&<div className="partner-progress"><progress max={100} value={progress}/><span>{progress}%</span></div>}
          <div className="partner-buttons">
            <button type="submit" className="partner-primary" disabled={busy||!requestFile}>
              Upload to QMS for review</button>
            <button type="button" disabled={busy} onClick={()=>setActiveRequest(null)}>Cancel</button>
            {busy&&<button type="button" onClick={()=>abortRef.current?.abort()}>Cancel upload</button>}
          </div>
          <ActionNotice value={error} error/><ActionNotice value={notice}/>
        </form>}
      </Section>
      <Section title="Audit findings" description="The audit team retains finding classification and closure authority.">
        {data.value.findings.items.map(x=><div className="partner-row" key={x.id}>
          <div><strong>{x.finding_ref||"Audit finding"} · {x.requirement_ref||"Requirement not linked"}</strong>
            <small>{x.description}</small><small>Target closure {friendlyDate(x.target_close_date)}</small></div>
          <Status value={x.closed_at?"CLOSED":x.severity}/></div>)}
        {!data.value.findings.items.length&&<p className="partner-empty">No released finding records for the assigned audit.</p>}
      </Section>
      <Section title="Corrective-action requests" description="Respond only to assigned CARs. Submission uses the authoritative QMS CAR response workflow.">
        {data.value.cars.items.map(x=><div key={x.id} className="partner-record">
          <div className="partner-row"><div><strong>{x.car_number} · {x.title}</strong>
            <small>Due {friendlyDate(x.due_date)} · Root cause review {x.root_cause_status} · CAPA review {x.capa_status}</small></div><Status value={x.status}/></div>
          {canSubmit&&<button type="button" disabled={busy} onClick={()=>{
            setActiveCar(x);setDraft(empty);setError("");setNotice("");
          }}>Prepare governed CAR response</button>}
        </div>)}
        {!data.value.cars.items.length&&<p className="partner-empty">No CARs currently assigned to this external organization.</p>}
        <p className="partner-muted">{data.value.submission_policy}</p>
      </Section>
      {activeCar&&canSubmit&&<Section title={`Respond to ${activeCar.car_number}`} description="The root cause and corrective-action plan become a formal Quality submission only after the server confirms receipt.">
        <form className="partner-form" onSubmit={submit}>
          {([
            ["containment_action","Immediate containment"],
            ["root_cause","Root cause analysis"],
            ["corrective_action","Corrective action plan"],
            ["preventive_action","Preventive action"],
          ] as const).map(([name,title])=><label key={name}>{title}
            <textarea value={draft[name]} minLength={name==="preventive_action"?0:12}
              required={name!=="preventive_action"} maxLength={500} rows={3}
              onChange={e=>setDraft(d=>({...d,[name]:e.target.value}))}/>
          </label>)}
          <label>Quality-reviewed objective evidence<select value={draft.evidence_submission_id}
            onChange={e=>setDraft(d=>({...d,evidence_submission_id:e.target.value}))}>
            <option value="">No accepted evidence selected</option>
            {data.value.accepted_evidence.items.filter(x=>x.related_id===activeCar.assignment_id).map(x=>
              <option value={x.id} key={x.id}>{x.filename}</option>)}
          </select></label>
          <div className="partner-buttons"><button className="partner-primary" disabled={busy}>Submit corrective action for Quality review</button>
            <button type="button" disabled={busy} onClick={()=>setActiveCar(null)}>Cancel</button></div>
        </form>
        {capabilities.includes("document.submit")&&<form className="partner-form" onSubmit={upload}>
          <h3>Upload CAR supporting evidence</h3>
          <label>Document<input type="file" required accept=".pdf,.docx,.png,.jpg,.jpeg,.txt"
            onChange={e=>setFile(e.target.files?.[0]||null)}/></label>
          {busy&&<div className="partner-progress"><progress max={100} value={progress}/><span>{progress}%</span></div>}
          <label>Controlled document requirement<select required value={carRequirement}
            onChange={e=>setCarRequirement(e.target.value)}>
            <option value="">Select authorized CAR or audit evidence class</option>
            {carClasses.map(x=><option key={x.id} value={x.id}>{x.title}</option>)}
          </select></label>
          {!carClasses.length&&<p>Quality must configure the corrective-action evidence requirement before a classified submission can be made.</p>}
          <div className="partner-buttons"><button type="submit" disabled={busy||!file||!carRequirement}>Upload for separate Quality acceptance</button>
            {busy&&<button type="button" onClick={()=>abortRef.current?.abort()}>Cancel upload</button>}</div>
        </form>}
        <ActionNotice value={error} error/><ActionNotice value={notice}/>
      </Section>}
      {!activeCar&&<ActionNotice value={notice}/>}
      <div className="partner-pager"><button disabled={offset===0} onClick={()=>setOffset(v=>Math.max(0,v-15))}>Previous</button>
        <button disabled={!data.value.cars.items.length&&!data.value.findings.items.length&&!data.value.notices.items.length} onClick={()=>setOffset(v=>v+15)}>Next</button></div>
    </>}
  </div>;
}
