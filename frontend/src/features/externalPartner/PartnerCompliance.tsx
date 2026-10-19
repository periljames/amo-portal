import React,{useState} from "react";
import {Link} from "react-router-dom";
import type {PartnerProps} from "./ExternalPartnerPage";
import {friendlyDate,label,partnerRequest,type Evidence,type Page} from "./partnerApi";
import {ActionNotice,Pager,Section,State,Status} from "./PartnerPrimitives";
import { usePartnerLoad } from "./usePartnerLoad";

type Certificate={id:string;certificate_type:string;certificate_number:string;approval_rating:string|null;verification_state:string;valid_until:string|null};
type Scope={category:string;site_code:string;status:string;expires_on:string|null;restrictions:string|null;approval_number:string|null};
type Compliance={certificates:Page<Certificate>;approval_scopes:Page<Scope>;governed_evidence:Page<{id:string;evidence_type:string;title:string;status:string;valid_until:string|null}>;submitted_evidence:Page<Evidence>;verification_notice:string};
export default function PartnerCompliance({tenant,csrf,capabilities}:PartnerProps){
  const [offset,setOffset]=useState(0);
  const [renewal,setRenewal]=useState<Certificate|null>(null);
  const [renewalReason,setRenewalReason]=useState("");
  const [renewalBusy,setRenewalBusy]=useState(false);
  const [renewalMessage,setRenewalMessage]=useState("");
  const [renewalError,setRenewalError]=useState("");
  const query=usePartnerLoad((signal)=>partnerRequest<Compliance>(tenant,
    `compliance?limit=15&offset=${offset}`,{signal}),`${tenant}:${offset}`);
  const submitRenewal=(event:React.FormEvent)=>{
    event.preventDefault();
    if(!renewal||renewalReason.trim().length<12)return;
    setRenewalBusy(true);setRenewalError("");setRenewalMessage("");
    void partnerRequest(tenant,"change-requests",{method:"POST",csrf,
      body:{category:"RENEWAL",fields:{certificate_id:renewal.id},reason:renewalReason.trim()},
    }).then(()=>{
      setRenewalMessage(`Renewal proposal for ${renewal.certificate_number} sent to Quality for controlled review. Certificate validity remains unchanged.`);
      setRenewal(null);setRenewalReason("");
    }).catch(e=>setRenewalError(e instanceof Error?e.message:"Renewal proposal was not received"))
      .finally(()=>setRenewalBusy(false));
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
      <Section title="Certificates & approvals" description="Renewal proposals require Quality review and do not extend the recorded expiry date.">
        {query.value.certificates.items.length?query.value.certificates.items.map((item,i)=><div className="partner-row" key={i}>
          <div><strong>{item.certificate_type} · {item.certificate_number}</strong>
            <small>{item.approval_rating||"Rating pending"} · Expires {friendlyDate(item.valid_until)}</small></div>
          <div className="partner-buttons"><Status value={item.verification_state}/>
            {capabilities.includes("profile.propose")&&
              <button type="button" disabled={renewalBusy} onClick={()=>{setRenewal(item);setRenewalReason("");setRenewalError("");setRenewalMessage("");}}>
                Propose renewal</button>}</div></div>):<p className="partner-empty">No controlled certificates are listed.</p>}
        {renewal&&<form className="partner-form" onSubmit={submitRenewal}>
          <h3>Renew {renewal.certificate_type} · {renewal.certificate_number}</h3>
          <label>Renewal reason and relevant details
            <textarea required minLength={12} maxLength={2000} rows={3} value={renewalReason}
              onChange={e=>setRenewalReason(e.target.value)}/></label>
          <div className="partner-buttons">
            <button className="partner-primary" disabled={renewalBusy||renewalReason.trim().length<12}>
              {renewalBusy?"Submitting…":"Submit renewal proposal"}</button>
            <button type="button" disabled={renewalBusy} onClick={()=>setRenewal(null)}>Cancel</button>
          </div>
        </form>}
        <ActionNotice value={renewalError} error/><ActionNotice value={renewalMessage}/>
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
      <Section title="Controlled document intake" description="Use the applicable tenant and category requirements, published forms, secure submission and revision history.">
        <p className="partner-muted">The former unclassified evidence upload is retired. All new certificate, qualification, agreement and other governed submissions must select a controlled requirement.</p>
        <Link to={`/partner/${encodeURIComponent(tenant)}/documents`}>Open controlled documents and forms</Link>
      </Section>
      <Pager value={query.value.certificates} onChange={setOffset}/>
    </>}
  </div>;
}
