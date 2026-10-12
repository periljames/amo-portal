import React,{useEffect,useRef,useState} from "react";
import {Link} from "react-router-dom";
import type {PartnerProps} from "./ExternalPartnerPage";
import {friendlyDate,label,partnerRequest,partnerUpload,type Evidence,type Page} from "./partnerApi";
import {ActionNotice,Pager,Section,State,Status,usePartnerLoad} from "./PartnerPrimitives";

type Certificate={certificate_type:string;certificate_number:string;approval_rating:string|null;verification_state:string;valid_until:string|null};
type Scope={category:string;site_code:string;status:string;expires_on:string|null;restrictions:string|null;approval_number:string|null};
type Compliance={certificates:Page<Certificate>;approval_scopes:Page<Scope>;governed_evidence:Page<{id:string;evidence_type:string;title:string;status:string;valid_until:string|null}>;submitted_evidence:Page<Evidence>;verification_notice:string};
export default function PartnerCompliance({tenant,csrf,capabilities}:PartnerProps){
  const [offset,setOffset]=useState(0);
  const query=usePartnerLoad((signal)=>partnerRequest<Compliance>(tenant,
    `compliance?limit=15&offset=${offset}`,{signal}),`${tenant}:${offset}`);
  const [file,setFile]=useState<File|null>(null);
  const [evidenceType,setEvidenceType]=useState("CERTIFICATE_RENEWAL");
  const [progress,setProgress]=useState(0);const [busy,setBusy]=useState(false);
  const [notice,setNotice]=useState("");const [error,setError]=useState("");
  const abortRef=useRef<AbortController|null>(null);
  useEffect(()=>()=>abortRef.current?.abort(),[]);
  const upload=(event:React.FormEvent)=>{
    event.preventDefault();if(!file)return;
    setBusy(true);setProgress(0);setError("");setNotice("");
    const controller=new AbortController();abortRef.current=controller;
    void partnerUpload(tenant,csrf,file,{evidence_type:evidenceType,
      related_kind:"PROVIDER",related_id:""},setProgress,controller.signal)
      .then(result=>{setNotice(`${result.filename} received and awaiting controlled Quality review.`);
        setFile(null);setProgress(100);query.reload();})
      .catch(ex=>{if(!controller.signal.aborted)setError(ex instanceof Error?ex.message:"Upload failed; please retry");})
      .finally(()=>{abortRef.current=null;setBusy(false);});
  };
  return <div className="partner-stack">
    <State pending={query.pending} error={query.error} retry={query.reload}/>
    {query.value&&<>
      <Section title="Approved scope and restrictions" description="Canonical supplier Quality approval scopes, not self-declared capabilities.">
        {query.value.approval_scopes.items.length?query.value.approval_scopes.items.map((item,i)=><div key={i} className="partner-row">
          <div><strong>{label(item.category)} · {item.site_code}</strong>
            <small>{item.approval_number||"No approval number"} · Ends {friendlyDate(item.expires_on)}</small>
            {item.restrictions&&<small>Restriction: {item.restrictions}</small>}</div>
          <Status value={item.status}/></div>):<p className="partner-empty">No approved category has been published for this supplier.</p>}
      </Section>
      <Section title="Certificates & approvals" action={<Link to={`/partner/${tenant}/organization`}>Request renewal →</Link>}>
        {query.value.certificates.items.length?query.value.certificates.items.map((item,i)=><div className="partner-row" key={i}>
          <div><strong>{item.certificate_type} · {item.certificate_number}</strong>
            <small>{item.approval_rating||"Rating pending"} · Expires {friendlyDate(item.valid_until)}</small></div>
          <Status value={item.verification_state}/></div>):<p className="partner-empty">No controlled certificates are listed.</p>}
      </Section>
      <Section title="Evidence register" description="The Quality register is authoritative. Pending uploads do not change verification or approval.">
        {query.value.governed_evidence.items.length?query.value.governed_evidence.items.map(row=><div key={row.id} className="partner-row">
          <div><strong>{row.title}</strong><small>{label(row.evidence_type)} · Valid until {friendlyDate(row.valid_until)}</small></div><Status value={row.status}/></div>)
          :<p className="partner-empty">No governed evidence is currently recorded.</p>}
      </Section>
      <Section title="My submitted evidence" description="File status is based on the server-side submission and Quality review record.">
        {query.value.submitted_evidence.items.length?query.value.submitted_evidence.items.map(row=><div className="partner-row" key={row.id}>
          <div><strong>{row.filename}</strong><small>{label(row.evidence_type)} · {friendlyDate(row.created_at)}</small>
            {row.review_note&&<small>Quality feedback: {row.review_note}</small>}</div><Status value={row.status}/>
        </div>):<p className="partner-empty">No evidence files submitted through the partner portal yet.</p>}
      </Section>
      {capabilities.includes("document.submit")&&<Section title="Submit compliance evidence"
        description="PDF, Word, image or text documents up to 20 MB. Uploads are held for Quality review; certification remains a separate decision.">
        <form className="partner-form" onSubmit={upload}>
          <label>Evidence type<select value={evidenceType} onChange={e=>setEvidenceType(e.target.value)}>
            <option value="CERTIFICATE_RENEWAL">Certificate renewal</option>
            <option value="INSURANCE">Insurance evidence</option>
            <option value="QUALITY_SYSTEM">Quality system evidence</option>
            <option value="CAPABILITY">Capability documentation</option>
            <option value="CORRECTIVE_ACTION">Corrective-action evidence</option>
            <option value="OTHER">Other supporting evidence</option>
          </select></label>
          <label>Evidence file<input type="file" accept=".pdf,.docx,.png,.jpg,.jpeg,.txt"
            required onChange={event=>setFile(event.target.files?.[0]||null)}/></label>
          {busy&&<div className="partner-progress"><progress max={100} value={progress}/><span>{progress}% uploaded</span></div>}
          <ActionNotice value={error} error/><ActionNotice value={notice}/>
          <div className="partner-buttons"><button className="partner-primary" disabled={!file||busy}>Submit for Quality review</button>
            {busy&&<button type="button" onClick={()=>abortRef.current?.abort()}>Cancel upload</button>}</div>
        </form>
      </Section>}
      <Pager value={query.value.certificates} onChange={setOffset}/>
    </>}
  </div>;
}
