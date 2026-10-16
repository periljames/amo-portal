import React,{useCallback,useEffect,useState} from "react";
import {apiRequest} from "../../services/apiClient";

type Alternate={external_quote_id:string;canonical_quote_id:number;external_reference:string;revision_no:number;
  supplier_id:number;rfq_id:number;quote_line_id:number;requisition_line_id:number;
  supplier_part_number:string|null;manufacturer:string|null;quantity:number;uom:string;
  traceability_statement:string|null;deviation:string|null;requested_part_number:string|null;
  requested_description:string;alternates_allowed:boolean;required_certification:string|null;
  approved_manufacturers:string[]|null};
export default function ProviderAlternateTechnicalReview({amoCode}:{amoCode:string}){
  const root="/api/maintenance/"+encodeURIComponent(amoCode)+"/procurement/partner-collaboration";
  const [items,setItems]=useState<Alternate[]>([]);const [loading,setLoading]=useState(false);
  const [selected,setSelected]=useState<number|null>(null);const [reason,setReason]=useState("");
  const [reference,setReference]=useState("");const [busy,setBusy]=useState(false);
  const [error,setError]=useState("");const [notice,setNotice]=useState("");
  const reload=useCallback(async()=>{
    setLoading(true);setError("");
    try{setItems((await apiRequest<{items:Alternate[]}>(root+"/technical-review",{cacheTtlMs:0})).items);}
    catch(e){setError(e instanceof Error?e.message:"Technical review queue unavailable");}
    finally{setLoading(false);}
  },[root]);
  useEffect(()=>{void reload();},[reload]);
  async function decide(decision:"APPROVED"|"REJECTED"){
    if(selected===null)return;
    setBusy(true);setError("");setNotice("");
    try{
      await apiRequest(root+"/technical-review/"+selected+"/decision",{
        method:"POST",body:JSON.stringify({decision,rationale:reason,technical_reference:reference,
          idempotency_key:crypto.randomUUID().replace(/-/g,"")}),
      });
      setNotice("Technical disposition recorded on the canonical quoted line. Procurement award and Quality review remain independent.");
      setSelected(null);setReason("");setReference("");await reload();
    }catch(e){setError(e instanceof Error?e.message:"Technical disposition was not recorded");}
    finally{setBusy(false);}
  }
  return <section className="proc-panel">
    <h2>Supplier alternate technical review</h2>
    <p>Evaluate supplier-proposed equivalents before Procurement can award a quotation. This decision does not substitute an issued PO or release material.</p>
    <button type="button" onClick={()=>void reload()} disabled={loading}>Refresh alternatives</button>
    {loading&&<p role="status">Loading technical review cases…</p>}
    {error&&<p role="alert">{error}</p>}
    {notice&&<p role="status">{notice}</p>}
    {!loading&&!items.length&&<p>No pending alternate-part technical reviews.</p>}
    <table><thead><tr><th>RFQ / quote</th><th>Required part</th><th>Offered part</th><th>Technical evidence</th><th>Disposition</th></tr></thead>
    <tbody>{items.map(item=><tr key={item.quote_line_id}>
      <td>{item.rfq_id} / {item.external_reference} R{item.revision_no}</td>
      <td>{item.requested_part_number||"Service"} · {item.requested_description}</td>
      <td>{item.supplier_part_number} · {item.manufacturer||"Unknown"}</td>
      <td>{item.deviation||"Not supplied"} · {item.traceability_statement||"No traceability reference"}
        <small>Required certificate: {item.required_certification||"Not specified"}</small></td>
      <td><button type="button" onClick={()=>setSelected(item.quote_line_id)}>Review</button></td>
    </tr>)}</tbody></table>
    {selected!==null&&<div className="proc-form">
      <h3>Technical disposition · line {selected}</h3>
      <label>Controlled technical reference<input required minLength={3} maxLength={160}
        value={reference} onChange={e=>setReference(e.target.value)}/></label>
      <label>Technical justification<textarea required minLength={12} maxLength={2500}
        rows={4} value={reason} onChange={e=>setReason(e.target.value)}/></label>
      <p>Check interchangeability, applicable technical data, manufacturer eligibility, traceability and required release documents before approving an alternate.</p>
      <button type="button" disabled={busy||reference.length<3||reason.trim().length<12}
        onClick={()=>void decide("APPROVED")}>Accept technical equivalent</button>
      <button type="button" disabled={busy||reference.length<3||reason.trim().length<12}
        onClick={()=>void decide("REJECTED")}>Reject proposed equivalent</button>
      <button type="button" onClick={()=>setSelected(null)}>Cancel</button>
    </div>}
  </section>;
}
