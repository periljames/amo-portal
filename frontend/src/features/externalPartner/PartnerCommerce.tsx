import React,{useEffect,useRef,useState} from "react";
import type {PartnerProps} from "./ExternalPartnerPage";
import {friendlyDate,partnerRequest,partnerUrl,type Contract,type Page,type ProcurementPage} from "./partnerApi";
import {ActionNotice,Pager,Section,State,Status,usePartnerLoad} from "./PartnerPrimitives";

function Contracts({tenant,csrf,capabilities}:PartnerProps){
  const [search,setSearch]=useState("");const [offset,setOffset]=useState(0);
  const [expanded,setExpanded]=useState("");const [reason,setReason]=useState("");
  const [busy,setBusy]=useState(false);const [message,setMessage]=useState("");const [error,setError]=useState("");
  const abortRef=useRef<AbortController|null>(null);
  useEffect(()=>()=>abortRef.current?.abort(),[]);
  const query=usePartnerLoad((signal)=>partnerRequest<Page<Contract>>(tenant,
    `contracts?offset=${offset}&limit=15&search=${encodeURIComponent(search)}`,{signal}),
    `${tenant}:${offset}:${search}`);
  function receipt(item:Contract,kind:"RECEIVED"|"REQUEST_CLARIFICATION"){
    setBusy(true);setMessage("");setError("");
    void partnerRequest(tenant,`contracts/${encodeURIComponent(item.id)}/receipt`,{
      method:"POST",csrf,body:{acknowledgement:kind,version:item.version,note:reason},
    }).then(()=>{setMessage("Receipt recorded against this exact agreement version. This is not a contractual signature.");
      setReason("");setExpanded("");query.reload();
    }).catch(e=>setError(e instanceof Error?e.message:"Receipt was not recorded")).finally(()=>setBusy(false));
  }
  async function download(item:Contract){
    if(item.controlled_document_access!=="PUBLISHED_REVISION_CHECK_REQUIRED"){
      setError("Document Control has not granted this exact revision to your external account.");
      return;
    }
    const abort=new AbortController();abortRef.current=abort;
    setBusy(true);setError("");setMessage("");
    try{
      const response=await fetch(partnerUrl(tenant,`contracts/${encodeURIComponent(item.id)}/document`),{
        credentials:"include",cache:"no-store",signal:abort.signal,
      });
      if(!response.ok){
        const detail=await response.json().catch(()=>({detail:"Document release was denied"})) as {detail?:string};
        throw new Error(typeof detail.detail==="string"?detail.detail:"Controlled document is unavailable");
      }
      const binary=await response.blob();
      if(abort.signal.aborted)return;
      const url=URL.createObjectURL(binary);
      try{
        const link=document.createElement("a");link.href=url;
        const ext=response.headers.get("Content-Type")?.includes("wordprocessingml")?".docx":".pdf";
        const safeNumber=item.contract_number.replace(/[^a-zA-Z0-9_-]/g,"_");
        link.download=`${safeNumber}-revision-${item.version}${ext}`;
        link.click();
        setMessage("Controlled published revision downloaded. Verify the displayed revision and validity before use.");
      }finally{window.setTimeout(()=>URL.revokeObjectURL(url),1500);}
    }catch(reason){
      if(!abort.signal.aborted)setError(reason instanceof Error?reason.message:"Controlled document download failed");
    }finally{abortRef.current=null;setBusy(false);}
  }
  return <Section title="My assigned agreements" description="These are Quality-governed agreement records individually granted to your provider membership.">
    <div className="partner-toolbar"><label className="partner-search">
      <span className="sr-only">Search agreements</span>
      <input placeholder="Search titles" type="search" value={search}
        onChange={e=>{setSearch(e.target.value);setOffset(0);}}/></label></div>
    <State pending={query.pending} error={query.error} retry={query.reload}
      empty={!query.pending&&!query.error&&!query.value?.items.length}/>
    {query.value?.items.map(item=><div className="partner-record" key={item.id}>
      <div className="partner-row"><div><strong>{item.title}</strong>
        <small>{item.contract_number} · Version {item.version} · Expires {friendlyDate(item.expires_on)}</small></div>
        <Status value={item.status}/></div>
      <p className="partner-muted">{item.scope_text}</p>
      <div className="partner-inline"><span>Controlled document revision</span>
        <strong>{item.controlled_document_revision||"Not linked"}</strong></div>
      {item.controlled_document_id&&(
        item.controlled_document_access==="PUBLISHED_REVISION_CHECK_REQUIRED"?
        <button type="button" disabled={busy} onClick={()=>void download(item)}>
          Download granted published revision</button>:
        <p className="partner-muted">The controlled DMS file is not released to this member. Request explicit document access from your AMO. Agreement metadata alone does not authorize a download.</p>
      )}
      {capabilities.includes("contract.acknowledge") && expanded===item.id?<div className="partner-form">
        <label>Receipt or clarification note<textarea rows={3} maxLength={2000} value={reason}
          onChange={e=>setReason(e.target.value)}/></label>
        <div className="partner-buttons">
          <button type="button" disabled={busy} onClick={()=>receipt(item,"RECEIVED")}>Record summary receipt</button>
          <button type="button" disabled={busy||reason.trim().length<8}
            onClick={()=>receipt(item,"REQUEST_CLARIFICATION")}>Request clarification</button>
          <button type="button" onClick={()=>setExpanded("")}>Cancel</button>
        </div>
      </div>:capabilities.includes("contract.acknowledge") ?
        <button type="button" disabled={busy} onClick={()=>setExpanded(item.id)}>Receipt / clarification</button>:null}
    </div>)}
    <ActionNotice value={error} error/><ActionNotice value={message}/>
    {query.value&&<Pager value={query.value} onChange={setOffset}/>}
  </Section>;
}
function Procurement({tenant}:PartnerProps){
  const [offset,setOffset]=useState(0);
  const query=usePartnerLoad((signal)=>partnerRequest<ProcurementPage>(tenant,
    `procurement?limit=20&offset=${offset}`,{signal}),`${tenant}:${offset}`);
  return <div className="partner-stack">
    <State pending={query.pending} error={query.error} retry={query.reload}/>
    {query.value&&<>
      <Section title="Invited quotations (RFQs)" description="Only RFQs issued to the canonical supplier. Quotation transactions are reserved for Phase 6.">
        {query.value.rfqs.items.length?query.value.rfqs.items.map(q=><div className="partner-row" key={q.id}>
          <div><strong>{q.rfq_number} · {q.title}</strong>
            <small>Response due {friendlyDate(q.response_due_at)}</small></div><Status value={q.status}/>
        </div>):<p className="partner-empty">No current invited RFQs for this supplier.</p>}
      </Section>
      <Section title="Issued purchase orders" description="Only purchase orders sent to your organization are visible. Acknowledgement and delivery transactions remain governed by Procurement.">
        {query.value.purchase_orders.items.length?query.value.purchase_orders.items.map(q=><div className="partner-row" key={q.id}>
          <div><strong>{q.po_number}</strong>
            <small>Delivery commitment {friendlyDate(q.promised_delivery_date)}</small>
            <small>{q.acknowledged_at?"Acknowledged by Procurement":"Acknowledgement pending"}</small></div>
          <Status value={q.status}/>
        </div>):<p className="partner-empty">No issued purchase orders at present.</p>}
      </Section>
      <Section title="Transactional boundaries"><p className="partner-muted">This is a live Procurement read projection. RFQ responses, supplier quotations, purchase-order acknowledgements and shipment commitments require the Phase 6 authorized transaction workflows. No simulated submission controls are displayed.</p></Section>
      <Pager value={query.value.rfqs} onChange={setOffset}/>
    </>}
  </div>;
}
type Work={approved_scopes:Array<{category:string;site_code:string;product_family:string;status:string;restrictions:string|null;expires_on:string|null}>;assigned_work_count:number;execution_enabled:boolean;message:string};
function WorkPreview({tenant}:PartnerProps){
  const query=usePartnerLoad((signal)=>partnerRequest<Work>(tenant,"contracted-work",{signal}),tenant);
  return <Section title="Approved work boundaries" description="A scoped read projection, not a maintenance execution or release screen.">
    <State pending={query.pending} error={query.error} retry={query.reload}/>
    {query.value&&<>
      <div className="partner-inline"><span>Explicitly assigned references</span><strong>{query.value.assigned_work_count}</strong></div>
      {query.value.approved_scopes.map((row,i)=><div key={i} className="partner-row">
        <div><strong>{row.category} / {row.site_code}</strong>
          <small>{row.product_family} · Ends {friendlyDate(row.expires_on)}</small>
          {row.restrictions&&<small>Limits: {row.restrictions}</small>}</div><Status value={row.status}/>
      </div>)}
      <p className="partner-muted">{query.value.message}</p>
    </>}
  </Section>;
}
export default function PartnerCommerce(props:PartnerProps&{section:"contracts"|"procurement"|"work"}){
  if(props.section==="contracts")return <Contracts {...props}/>;
  if(props.section==="procurement")return <Procurement {...props}/>;
  return <WorkPreview {...props}/>;
}
