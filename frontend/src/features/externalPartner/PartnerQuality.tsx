import React,{useEffect,useRef,useState} from "react";
import type {PartnerProps} from "./ExternalPartnerPage";
import {friendlyDate,partnerRequest,partnerUpload,type QualityPage} from "./partnerApi";
import {ActionNotice,Section,State,Status,usePartnerLoad} from "./PartnerPrimitives";
type Car=QualityPage["cars"]["items"][number];
type Draft={containment_action:string;root_cause:string;corrective_action:string;preventive_action:string;evidence_submission_id:string};
const empty:Draft={containment_action:"",root_cause:"",corrective_action:"",preventive_action:"",evidence_submission_id:""};
export default function PartnerQuality({tenant,csrf,capabilities}:PartnerProps){
  const [offset,setOffset]=useState(0);
  const data=usePartnerLoad((signal)=>partnerRequest<QualityPage>(tenant,
    `quality?limit=15&offset=${offset}`,{signal}),`${tenant}:${offset}`);
  const [activeCar,setActiveCar]=useState<Car|null>(null);
  const [draft,setDraft]=useState<Draft>(empty);
  const [busy,setBusy]=useState(false);const [error,setError]=useState("");
  const [notice,setNotice]=useState("");const [file,setFile]=useState<File|null>(null);
  const [progress,setProgress]=useState(0);const abortRef=useRef<AbortController|null>(null);
  useEffect(()=>()=>abortRef.current?.abort(),[]);
  const canSubmit=capabilities.includes("capa.respond");
  const upload=(event:React.FormEvent)=>{
    event.preventDefault();if(!file||!activeCar)return;
    const controller=new AbortController();abortRef.current=controller;
    setError("");setNotice("");setBusy(true);setProgress(0);
    void partnerUpload(tenant,csrf,file,{evidence_type:"CORRECTIVE_ACTION",
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
            {x.description&&<small>{x.description}</small>}<small>Due {friendlyDate(x.due_date)}</small></div>
          <Status value={x.status}/></div>)}
        {!data.value.document_requests.items.length&&<p className="partner-empty">No document requests assigned for display.</p>}
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
          <div className="partner-buttons"><button type="submit" disabled={busy||!file}>Upload for separate Quality acceptance</button>
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
