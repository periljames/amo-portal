import React,{useEffect,useRef,useState} from "react";
import type {PartnerProps} from "./ExternalPartnerPage";
import PartnerContractedWork from "./PartnerContractedWork";
import {friendlyDate,partnerRequest,partnerUrl,type Contract,type Page} from "./partnerApi";
import {ActionNotice,Pager,Section,State,Status} from "./PartnerPrimitives";
import { usePartnerLoad } from "./usePartnerLoad";
import PartnerProcurementWorkspace from "./PartnerProcurementWorkspace";

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
export default function PartnerCommerce(props:PartnerProps&{section:"contracts"|"procurement"|"work"}){
  if(props.section==="contracts")return <Contracts {...props}/>;
  if(props.section==="procurement")return <PartnerProcurementWorkspace {...props}/>;
  return <PartnerContractedWork {...props}/>;
}
