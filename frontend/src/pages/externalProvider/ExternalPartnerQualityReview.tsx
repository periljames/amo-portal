import React,{useEffect,useState} from "react";
import ExternalProviderDocumentsReview from "./ExternalProviderDocumentsReview";
import {apiRequest} from "../../services/apiClient";
import {authHeaders} from "../../services/auth";
import {getApiBaseUrl} from "../../services/config";
import "./external-provider-portal.css";

type Proposal={id:string;legal_name:string;supplier_code:string;email:string;category:string;
  proposed_json:Record<string,unknown>;reason:string;status:string;created_at:string;review_note:string|null};
type Evidence={id:string;legal_name:string;supplier_code:string;email:string;filename:string;
  evidence_type:string;status:string;related_kind:string;sha256:string;size_bytes:number;review_note:string|null};
export default function ExternalPartnerQualityReview({amoCode,manager}:{
  amoCode:string;manager:boolean;
}){
  const path=`/api/maintenance/${encodeURIComponent(amoCode)}/quality/external-accounts`;
  const [proposals,setProposals]=useState<Proposal[]>([]);
  const [evidence,setEvidence]=useState<Evidence[]>([]);
  const [offset,setOffset]=useState(0);const [busy,setBusy]=useState("");
  const [decisionReason,setDecisionReason]=useState("");
  const [error,setError]=useState("");const [notice,setNotice]=useState("");
  const refresh=async()=>{
    const [p,e]=await Promise.all([
      apiRequest<{items:Proposal[]}>(`${path}/partner-change-requests?limit=25&offset=${offset}`,{cacheTtlMs:0}),
      apiRequest<{items:Evidence[]}>(`${path}/partner-evidence?limit=25&offset=${offset}`,{cacheTtlMs:0}),
    ]);
    setProposals(p.items);setEvidence(e.items);
  };
  useEffect(()=>{void refresh().catch(e=>setError(e instanceof Error?e.message:"Unable to load partner review queue"));},
    [amoCode,offset]);
  async function decide(kind:"proposal"|"evidence",id:string,state:string){
    if(decisionReason.trim().length<8){setError("Provide at least 8 characters of review rationale.");return;}
    setBusy(id);setError("");setNotice("");
    try{
      if(kind==="proposal"){
        await apiRequest(`${path}/partner-change-requests/${id}/review`,{
          method:"POST",body:JSON.stringify({state,note:decisionReason})});
      }else{
        await apiRequest(`${path}/partner-evidence/${id}/review`,{
          method:"POST",body:JSON.stringify({status:state,note:decisionReason})});
      }
      await refresh();
      setDecisionReason("");
      setNotice("Review decision recorded and made visible to the provider. Supplier approval and controlled-document verification remain separate.");
    }catch(e){setError(e instanceof Error?e.message:"Unable to record Quality decision");}
    finally{setBusy("");}
  }
  async function download(row:Evidence){
    setBusy(row.id);setError("");
    try{
      const response=await fetch(`${getApiBaseUrl()}${path}/partner-evidence/${encodeURIComponent(row.id)}/download`,{
        headers:new Headers(authHeaders()),credentials:"include",cache:"no-store"});
      if(!response.ok)throw new Error(`Evidence download rejected (${response.status})`);
      const data=await response.blob();const url=URL.createObjectURL(data);
      const link=document.createElement("a");link.href=url;link.download=row.filename;
      link.click();window.setTimeout(()=>URL.revokeObjectURL(url),1000);
    }catch(e){setError(e instanceof Error?e.message:"Evidence download failed");}
    finally{setBusy("");}
  }
  return <section className="vendor-card">
    <h2>Partner self-service review queue</h2>
    <p>Supplier master changes, certificates and contracts are never approved automatically by receiving a portal request.</p>
    {error&&<p role="alert" className="vendor-error">{error}</p>}
    {notice&&<p role="status" className="vendor-success">{notice}</p>}
    {manager&&<label className="vendor-field"><span>Review rationale for selected decision</span>
      <textarea value={decisionReason} rows={2} minLength={8} maxLength={2000}
        onChange={e=>setDecisionReason(e.target.value)}/></label>}
    <h3>Requested organization changes</h3>
    {!proposals.length&&<p>No change requests in this page.</p>}
    {proposals.map(row=><details className="vendor-review-item" key={row.id}>
      <summary><strong>{row.legal_name} · {row.category}</strong> <span>{row.status}</span></summary>
      <p>Submitted by {row.email} · {row.supplier_code}</p>
      <p>{row.reason}</p>
      <dl>{Object.entries(row.proposed_json||{}).map(([key,v])=><div key={key}>
        <dt>{key.replaceAll("_"," ")}</dt><dd>{String(v)}</dd></div>)}</dl>
      {row.review_note&&<p>Last Quality note: {row.review_note}</p>}
      {manager&&["PENDING","UNDER_REVIEW"].includes(row.status)&&<div className="vendor-actions">
        <button disabled={busy===row.id} onClick={()=>void decide("proposal",row.id,"UNDER_REVIEW")}>Under review</button>
        <button disabled={busy===row.id} onClick={()=>void decide("proposal",row.id,"ACCEPTED")}>Accept for controlled processing</button>
        <button disabled={busy===row.id} onClick={()=>void decide("proposal",row.id,"REJECTED")}>Reject proposal</button>
      </div>}
    </details>)}
    <h3>Provider-submitted objective evidence</h3>
    {!evidence.length&&<p>No evidence submissions in this page.</p>}
    {evidence.map(row=><div className="vendor-review-item" key={row.id}>
      <div><strong>{row.legal_name} · {row.filename}</strong><small>{row.evidence_type} · {row.size_bytes} bytes · {row.status}</small></div>
      <button disabled={busy===row.id} onClick={()=>void download(row)}>Download for review</button>
      {row.review_note&&<p>Review note: {row.review_note}</p>}
      {row.status==="PENDING_REVIEW"&&<p>Legacy unclassified evidence is preserved for historical review. Submit a new classified response through the controlled documents queue below.</p>}
    </div>)}
    <div className="vendor-actions">
      <button disabled={offset===0||Boolean(busy)} onClick={()=>setOffset(Math.max(0,offset-25))}>Previous</button>
      <button disabled={Boolean(busy)||(!proposals.length&&!evidence.length)} onClick={()=>setOffset(offset+25)}>Next</button>
    </div>
    <ExternalProviderDocumentsReview amoCode={amoCode} manager={manager}/>
  </section>;
}
