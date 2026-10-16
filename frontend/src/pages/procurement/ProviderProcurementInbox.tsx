import React, {useCallback,useEffect,useState} from "react";
import {Link} from "react-router-dom";
import {apiRequest} from "../../services/apiClient";

type Event={id:string;supplier_id:number;legal_name:string;entity_type:string;entity_id:string;
  action:string;message:string|null;details_json:Record<string,unknown>;created_at:string};
type Quote={id:string;supplier_id:number;rfq_id:number;canonical_quote_id:number;external_reference:string;
  revision_no:number;status:string;submitted_at:string};
type Shipment={id:string;po_id:number;supplier_id:number;shipment_reference:string;status:string;created_at:string};
type Candidate={id:string;filename:string;evidence_type:string;related_kind:string;related_id:string;legal_name:string;dms_retention_id:string};
type Inbox={events:Event[];quotes:Quote[];shipments:Shipment[];document_candidates:Candidate[];boundary:string};
type Decision="REPLY"|"ACCEPT_DATE_PROPOSAL"|"REJECT_PROPOSAL"|"ACKNOWLEDGE"|"REFER_ALTERNATE_TO_TECHNICAL";
export default function ProviderProcurementInbox({amoCode}:{amoCode:string}){
  const root="/api/maintenance/"+encodeURIComponent(amoCode)+"/procurement/partner-collaboration";
  const [view,setView]=useState<"inbox"|"quotes"|"shipments"|"documents">("inbox");
  const [data,setData]=useState<Inbox|null>(null);
  const [loading,setLoading]=useState(false);const [saving,setSaving]=useState(false);
  const [error,setError]=useState("");const [notice,setNotice]=useState("");
  const [selected,setSelected]=useState<Event|null>(null);
  const [action,setAction]=useState<Decision>("REPLY");
  const [message,setMessage]=useState("");
  const [importReason,setImportReason]=useState("");
  const [importId,setImportId]=useState("");
  const reload=useCallback(async()=>{
    setLoading(true);setError("");
    try{setData(await apiRequest<Inbox>(root+"/inbox?limit=100",{cacheTtlMs:0}));}
    catch(e){setError(e instanceof Error?e.message:"Supplier collaboration inbox unavailable");}
    finally{setLoading(false);}
  },[root]);
  useEffect(()=>{void reload();},[reload]);
  async function decide(event:React.FormEvent){
    event.preventDefault();if(!selected||message.trim().length<8)return;
    setSaving(true);setError("");setNotice("");
    try{
      await apiRequest(root+"/"+encodeURIComponent(selected.entity_type)+"/"+
        encodeURIComponent(selected.entity_id)+"/decisions",{
          method:"POST",body:JSON.stringify({
            action,message:message.trim(),proposal_event_id:selected.id,
            idempotency_key:crypto.randomUUID().replace(/-/g,""),
          }),
        });
      setNotice("Internal response recorded. The supplier has been notified; existing purchase approvals and QMS decisions remain separate.");
      setSelected(null);setMessage("");await reload();
    }catch(e){setError(e instanceof Error?e.message:"Supplier proposal decision was rejected");}
    finally{setSaving(false);}
  }
  async function importDocument(event:React.FormEvent){
    event.preventDefault();
    if(!importId||importReason.trim().length<8)return;
    setSaving(true);setError("");setNotice("");
    try{
      await apiRequest(root+"/documents/"+encodeURIComponent(importId)+"/import",{
        method:"POST",body:JSON.stringify({reason:importReason.trim()})
      });
      setNotice("The retained DMS original is now referenced in canonical Procurement Documents. No supplier Quality release or Finance authorization was granted.");
      setImportId("");setImportReason("");await reload();
    }catch(e){setError(e instanceof Error?e.message:"The DMS original could not be registered");}
    finally{setSaving(false);}
  }
  return <div className="proc-section">
    <header className="proc-section__head"><div><h2>Supplier collaboration</h2>
      <p>Supplier responses to issued RFQs and POs. Procurement owns evaluation and commercial decisions; Stores and Quality own inspection and release.</p>
      </div><button onClick={()=>void reload()} disabled={loading}>{loading?"Refreshing…":"Refresh"}</button>
    </header>
    <div className="proc-actions">
      <button type="button" aria-pressed={view==="inbox"} onClick={()=>setView("inbox")}>Responses ({data?.events.length||0})</button>
      <button type="button" aria-pressed={view==="quotes"} onClick={()=>setView("quotes")}>Quote revisions ({data?.quotes.length||0})</button>
      <button type="button" aria-pressed={view==="shipments"} onClick={()=>setView("shipments")}>Advance shipments ({data?.shipments.length||0})</button>
      <button type="button" aria-pressed={view==="documents"} onClick={()=>setView("documents")}>Governed originals ({data?.document_candidates.length||0})</button>
      <Link to={"/maintenance/"+encodeURIComponent(amoCode)+"/procurement/sourcing"}>Canonical quote evaluation</Link>
      <Link to={"/maintenance/"+encodeURIComponent(amoCode)+"/procurement/receiving"}>Stores receiving</Link>
      <Link to={"/maintenance/"+encodeURIComponent(amoCode)+"/procurement/documents"}>Controlled documents</Link>
    </div>
    {loading&&<p role="status">Loading supplier responses…</p>}
    {error&&<p role="alert">{error}</p>}
    {notice&&<p role="status">{notice}</p>}
    {data&&view==="inbox"&&<div>
      {!data.events.length&&<p>No supplier responses have been received.</p>}
      <table><thead><tr><th>Supplier</th><th>Transaction</th><th>Action and date</th><th>Message</th><th>Internal response</th></tr></thead>
        <tbody>{data.events.map(e=><tr key={e.id}><td>{e.legal_name}</td>
          <td>{e.entity_type} {e.entity_id}</td>
          <td>{e.action.replaceAll("_"," ")}<small>{new Date(e.created_at).toLocaleString()}</small></td>
          <td>{e.message||"—"}</td><td><button type="button" onClick={()=>{setSelected(e);setAction("REPLY");setMessage("");}}>Review / respond</button></td>
        </tr>)}</tbody></table>
    </div>}
    {data&&view==="quotes"&&<div>
      {!data.quotes.length&&<p>No externally submitted quotations.</p>}
      <table><thead><tr><th>RFQ</th><th>Canonical quote</th><th>Supplier reference</th><th>Revision</th><th>External state</th></tr></thead>
        <tbody>{data.quotes.map(q=><tr key={q.id}><td>{q.rfq_id}</td><td>{q.canonical_quote_id}</td>
          <td>{q.external_reference}</td><td>{q.revision_no}</td><td>{q.status}</td></tr>)}</tbody></table>
      <p>Use the existing Sourcing page for technical and commercial evaluation. A supplier response cannot approve a PO.</p>
    </div>}
    {data&&view==="shipments"&&<div>
      {!data.shipments.length&&<p>No supplier advance shipment notices.</p>}
      <table><thead><tr><th>PO</th><th>Shipment</th><th>Advised</th><th>State</th></tr></thead>
        <tbody>{data.shipments.map(s=><tr key={s.id}><td>{s.po_id}</td><td>{s.shipment_reference}</td>
          <td>{new Date(s.created_at).toLocaleString()}</td><td>{s.status} — not received</td></tr>)}</tbody></table>
    </div>}
    {data&&view==="documents"&&<div>
      <p>Only files already accepted by document intake and registered with DMS evidence retention are eligible. Import creates a reference in existing Procurement Documents, not another file copy.</p>
      {!data.document_candidates.length&&<p>No retained supplier originals await Procurement registration.</p>}
      <table><thead><tr><th>Supplier</th><th>Related transaction</th><th>Evidence class</th><th>Original</th><th>Action</th></tr></thead>
      <tbody>{data.document_candidates.map(d=><tr key={d.id}>
        <td>{d.legal_name}</td><td>{d.related_kind} · {d.related_id}</td>
        <td>{d.evidence_type}</td><td>{d.filename}</td>
        <td><button type="button" onClick={()=>{setImportId(d.id);setImportReason("");}}>Register in Procurement</button></td>
      </tr>)}</tbody></table>
      {importId&&<form className="proc-panel" onSubmit={e=>void importDocument(e)}>
        <h3>Reference DMS-retained provider original</h3>
        <p>Original {importId}. The existing Procurement evidence verification workflow will remain authoritative.</p>
        <label>Controlled registration reason<textarea required minLength={8} rows={3} maxLength={2000}
          value={importReason} onChange={e=>setImportReason(e.target.value)}/></label>
        <button disabled={saving||importReason.trim().length<8}>{saving?"Registering…":"Register exact original"}</button>
        <button type="button" onClick={()=>setImportId("")}>Cancel</button>
      </form>}
    </div>}
    {selected&&<form className="proc-panel" onSubmit={e=>void decide(e)}>
      <h3>Review {selected.action.replaceAll("_"," ")} — {selected.legal_name}</h3>
      <p>{selected.entity_type} {selected.entity_id} · {selected.message}</p>
      <label>Response action<select value={action} onChange={e=>setAction(e.target.value as Decision)}>
        <option value="REPLY">Clarification / correspondence reply</option>
        <option value="ACKNOWLEDGE">Acknowledge supplier response</option>
        <option value="REJECT_PROPOSAL">Reject requested change</option>
        {selected.entity_type==="PO"&&selected.action==="DELIVERY_CHANGE"&&
          <option value="ACCEPT_DATE_PROPOSAL">Accept proposed delivery date (Procurement only)</option>}
        {selected.entity_type==="RFQ"&&selected.action==="ALTERNATE_REQUEST"&&
          <option value="REFER_ALTERNATE_TO_TECHNICAL">Refer alternate for technical approval</option>}
      </select></label>
      <label>Decision rationale / response<textarea required minLength={8} maxLength={3000} rows={3}
        value={message} onChange={e=>setMessage(e.target.value)}/></label>
      <p>Alternate approvals and substitution remain subject to Technical and Quality control; this response does not change an approved requisition or PO part.</p>
      <button disabled={saving||message.trim().length<8}>{saving?"Recording…":"Record supplier response"}</button>
      <button type="button" disabled={saving} onClick={()=>setSelected(null)}>Cancel</button>
    </form>}
  </div>;
}
