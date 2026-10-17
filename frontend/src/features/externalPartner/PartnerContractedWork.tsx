import React,{useEffect,useState} from "react";
import {Link} from "react-router-dom";
import type {PartnerProps} from "./ExternalPartnerPage";
import {friendlyDate,partnerRequest,partnerUrl} from "./partnerApi";
import {ActionNotice,Section,State,Status,usePartnerLoad} from "./PartnerPrimitives";

type WorkRow={id:string;work_number:string;work_title:string;site_code:string;status:string;work_type:string;updated_at:string};
type Work={id:string;version:number;status:string;work_number:string;work_title:string;scope_text:string;function:string;defect:string;
  data_reference:string;data_revision:string;inspections_json:string[];required_release:string;internal_work_reference:string;
  registration:string|null;part_number:string|null;serial_number:string|null;requirements_json:Record<string,string|boolean|null>;
  contract_id:string;purchase_order_id:number|null;site_code:string};
type Detail={work:Work;inspection_checks:{criterion_index:number;criterion:string;result:string;filename:string|null;review_reason:string|null}[];history:{id:string;action:string;reason:string;created_at:string;from_state:string|null;to_state:string|null}[];
  additional_work:{id:string;description:string;state:string;decision_reason:string|null;approved_amended_work_reference:string|null;approved_commercial_variation_reference:string|null}[];
  custody:{id:string;item_type:string;description:string;quantity:number;uom:string;state:string;serial_batch:string|null}[];
  evidence:{id:string;category:string;filename:string;status:string;retention_status:string|null}[];
  closure_blockers:string[]};
const next:Record<string,string[]>={
  DISPATCHED:["PROVIDER_ACCEPT"],PROVIDER_ACCEPTED:["START"],
  IN_PROGRESS:["COMPLETE"],WORK_COMPLETED:["SUBMIT_RELEASE"],
  RELEASE_SUBMITTED:["RETURN"],
};
const key=()=>crypto.randomUUID().replace(/-/g,"");

export default function PartnerContractedWork({tenant,csrf,capabilities}:PartnerProps){
  const [selected,setSelected]=useState("");
  const [revision,setRevision]=useState(0);
  const [busy,setBusy]=useState(false);
  const [error,setError]=useState("");
  const [notice,setNotice]=useState("");
  const [reason,setReason]=useState("");
  const [noteType,setNoteType]=useState("PROGRESS");
  const [note,setNote]=useState("");
  const [additional,setAdditional]=useState("");
  const [additionalData,setAdditionalData]=useState("");
  const [commercial,setCommercial]=useState("");
  const [custodyReceipt,setCustodyReceipt]=useState("");
  const [action,setAction]=useState("");
  const canRespond=capabilities.includes("task.respond");
  const listing=usePartnerLoad(signal=>partnerRequest<{items:WorkRow[]}>(tenant,"maintenance-work",{signal}),tenant+":maintenance:"+revision);
  useEffect(()=>{if(!selected && listing.value?.items.length)setSelected(listing.value.items[0].id);},[listing.value,selected]);
  const detail=usePartnerLoad(signal=>selected?partnerRequest<Detail>(tenant,"maintenance-work/"+encodeURIComponent(selected),{signal}):Promise.resolve(null),tenant+":work:"+selected+":"+revision);
  const refresh=()=>{setRevision(v=>v+1);setError("");};
  async function run(path:string,body:unknown,success:string){
    setBusy(true);setError("");setNotice("");
    try{
      await partnerRequest(tenant,"maintenance-work/"+encodeURIComponent(selected)+path,{
        method:"POST",csrf,body,
      });
      setNotice(success);setReason("");setNote("");setAdditional("");refresh();
    }catch(e){setError(e instanceof Error?e.message:"Technical transaction was refused");}
    finally{setBusy(false);}
  }
  const work=detail.value?.work;
  async function downloadTechnicalData(){
    if(!selected)return;
    setError("");
    try{
      const response=await fetch(partnerUrl(tenant,"maintenance-work/"+encodeURIComponent(selected)+"/technical-data"),{
        credentials:"include",cache:"no-store"
      });
      if(!response.ok)throw new Error("Current controlled technical data is not released to this member");
      const blob=await response.blob();const url=URL.createObjectURL(blob);
      const link=document.createElement("a");link.href=url;link.download="controlled-maintenance-data";link.click();
      window.setTimeout(()=>URL.revokeObjectURL(url),2000);
      setNotice("The exact authorized maintenance-data original was downloaded; revision and applicability remain mandatory.");
    }catch(e){setError(e instanceof Error?e.message:"Maintenance data unavailable");}
  }
  const allowed=work?next[work.status]||[]:[];
  return <div className="partner-stack">
    <Section title="Assigned contracted maintenance" description="Technical work orders are distinct from purchase orders. Contractor releases are issued only under the contractor's own aviation approval.">
      <State pending={listing.pending} error={listing.error} retry={listing.reload} empty={!listing.value?.items.length}/>
      <div className="partner-grid">
        {listing.value?.items.map(w=><button type="button" key={w.id} aria-pressed={selected===w.id}
          onClick={()=>{setSelected(w.id);setAction("");setNotice("");setError("");}}
          className={selected===w.id?"partner-row is-selected":"partner-row"}>
          <span><strong>{w.work_number} · {w.work_title}</strong><small>{w.work_type} · {w.site_code} · {friendlyDate(w.updated_at)}</small></span><Status value={w.status}/>
        </button>)}
      </div>
    </Section>
    {selected&&<Section title="Technical work control" description="Only your specifically assigned work and approved technical instructions are displayed.">
      <State pending={detail.pending} error={detail.error} retry={detail.reload}/>
      <ActionNotice value={error} error/><ActionNotice value={notice}/>
      {work&&<>
        <div className="partner-row"><div><strong>{work.work_number} · {work.work_title}</strong><p>{work.function}</p></div><Status value={work.status}/></div>
        <div className="partner-grid">
          <div><strong>Authorized scope</strong><p>{work.scope_text}</p><small>Internal work package: {work.internal_work_reference}</small><small>Agreement: {work.contract_id}</small>{work.purchase_order_id&&<small>Related commercial PO: {work.purchase_order_id}</small>}</div>
          <div><strong>Aircraft / component identity</strong><p>{[work.registration,work.part_number,work.serial_number].filter(Boolean).join(" · ")||"See work package"}</p><small>Location: {work.site_code}</small><small>Defect/requirement: {work.defect}</small></div>
          <div><strong>Controlled technical data</strong><p>{work.data_reference} · revision {work.data_revision}</p>
          {typeof work.requirements_json.data_manual_id==="string"&&<button type="button" onClick={()=>void downloadTechnicalData()}>Download assigned DMS technical original</button>}
          <small>Do not substitute superseded data, processes or unapproved parts.</small></div>
          <div><strong>Mandatory inspection and release</strong>
            {(detail.value?.inspection_checks||[]).map(x=><p key={x.criterion_index}>{x.criterion_index+1}. {x.criterion}: {x.result}
              {x.filename&&<small> · Reviewed report: {x.filename}</small>}</p>)}
            <p>{work.required_release}</p><small>Only Safarilink reviews documentary compliance; this is not a contractor or Safarilink release.</small>
          </div>
        </div>
        {work.requirements_json.foreign&&<p role="note">Foreign maintenance: State-of-Registry, operator and authority conditions must be met independently of Kenyan supplier approval.</p>}
        {canRespond&&allowed.length>0&&<form className="partner-form" onSubmit={e=>{e.preventDefault();if(!action||!work)return;void run("/transitions",{action,reason,expected_version:work.version,details:{},idempotency_key:key()},"Transaction recorded. Internal technical and Quality approvals remain independent.");}}>
          <label>Authorized provider action<select required value={action} onChange={e=>setAction(e.target.value)}>
            <option value="">Select action</option>{allowed.map(x=><option key={x} value={x}>{x.replaceAll("_"," ")}</option>)}
          </select></label>
          <label>Attributable confirmation / reference<textarea required minLength={8} value={reason} onChange={e=>setReason(e.target.value)}/></label>
          <button type="submit" disabled={busy||!action||reason.trim().length<8}>{busy?"Recording…":"Record action"}</button>
        </form>}
        {work.status==="IN_PROGRESS"&&canRespond&&<form className="partner-form" onSubmit={e=>{e.preventDefault();void run("/additional-work",
          {description:additional,technical_data:additionalData||null,commercial_reference:commercial||null,idempotency_key:key()},
          "Additional work has been referred to Safarilink. It is NOT authorized until the responsible Maintenance Manager formally approves the amended scope.");}}>
          <h3>Request additional maintenance / variation</h3>
          <label>New defect or additional work<textarea value={additional} minLength={12} required onChange={e=>setAdditional(e.target.value)}/></label>
          <label>Proposed maintenance-data reference<input value={additionalData} onChange={e=>setAdditionalData(e.target.value)}/></label>
          <label>Related revised quotation / commercial reference<input value={commercial} onChange={e=>setCommercial(e.target.value)}/></label>
          <button disabled={busy||additional.trim().length<12}>Submit for written technical decision</button>
        </form>}
        {canRespond&&["DISPATCHED","PROVIDER_ACCEPTED","IN_PROGRESS","WORK_COMPLETED","RELEASE_SUBMITTED","REWORK_REQUIRED","ON_HOLD"].includes(work.status)&&
        <form className="partner-form" onSubmit={e=>{e.preventDefault();void run("/communications",
          {kind:noteType,message:note,expected_version:work.version,idempotency_key:key()},
          "Technical correspondence recorded in the immutable work history.");}}>
          <h3>Findings, progress and technical correspondence</h3>
          <label>Communication type<select value={noteType} onChange={e=>setNoteType(e.target.value)}>
            {["PROGRESS","FINDING","DISCREPANCY","ETA_CHANGE","TECHNICAL_QUERY","RETURN_SHIPMENT","PROTECTIVE_ACTION"].map(x=><option key={x} value={x}>{x.replaceAll("_"," ")}</option>)}
          </select></label><label>Message and reference<textarea required minLength={8} value={note} onChange={e=>setNote(e.target.value)}/></label>
          <button disabled={busy||note.trim().length<8}>Submit technical communication</button>
        </form>}
        <h3>Controlled supporting evidence</h3>
        <p>Upload inspection/strip reports, test results, release certificates and shipping documents as <strong>Contracted work</strong> originals. They must pass DMS retention and independent Quality review before the internal team may count them toward closure.</p>
        <Link to={`/partner/${encodeURIComponent(tenant)}/documents`}>Open governed work-document uploads</Link>
        {!detail.value?.evidence.length?<p>No accepted technical originals linked yet.</p>:<ul>{detail.value.evidence.map(x=><li key={x.id}>{x.category}: {x.filename} · {x.status} / {x.retention_status||"unregistered"}</li>)}</ul>}
        <h3>Safarilink property and custody</h3>
        {!detail.value?.custody.length?<p>No Stores-controlled property transferred.</p>:<table><thead><tr><th>Item</th><th>Reference</th><th>Quantity</th><th>Custody</th><th>Receipt</th></tr></thead>
          <tbody>{detail.value.custody.map(x=><tr key={x.id}><td>{x.item_type}: {x.description}</td><td>{x.serial_batch||"—"}</td><td>{x.quantity} {x.uom}</td><td>{x.state}</td><td>{canRespond&&x.state==="DISPATCHED"?<button disabled={busy} onClick={()=>setCustodyReceipt(x.id)}>Acknowledge physical receipt</button>:null}</td></tr>)}</tbody></table>}
        {custodyReceipt&&work&&<form className="partner-form" onSubmit={e=>{e.preventDefault();
          void run("/custody/"+encodeURIComponent(custodyReceipt)+"/acknowledge",
            {kind:"PROGRESS",message:reason,expected_version:work.version,idempotency_key:key()},
            "Receipt acknowledgment recorded. Safarilink Stores retains reconciliation and Quality release responsibility.");
          setCustodyReceipt("");
        }}>
          <label>Received quantity, condition and discrepancies<textarea required minLength={8} value={reason} onChange={e=>setReason(e.target.value)}/></label>
          <button disabled={busy||reason.trim().length<8}>Record provider receipt</button>
        </form>}
        <h3>Additional work decisions</h3>
        {!detail.value?.additional_work.length?<p>No scope variations.</p>:detail.value.additional_work.map(x=><p key={x.id}>{x.state} · {x.description} · {x.decision_reason||"Decision pending; do not commence additional work"}{x.approved_amended_work_reference&&<small> · Authorized amended instruction: {x.approved_amended_work_reference}</small>}</p>)}
        <h3>Technical closure readiness</h3>
        {detail.value?.closure_blockers.length?<ul>{detail.value.closure_blockers.map((x,i)=><li key={i}>{x}</li>)}</ul>:<p>No outstanding record-reconciliation blockers in the current work projection. Only Safarilink may technically accept and close the order.</p>}
        <details><summary>Immutable technical history ({detail.value?.history.length||0})</summary>
          {detail.value?.history.map(x=><p key={x.id}>{friendlyDate(x.created_at)} · {x.action.replaceAll("_"," ")} · {x.reason}</p>)}
        </details>
      </>}
    </Section>}
  </div>;
}
