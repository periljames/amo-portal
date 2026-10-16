import React, {useEffect,useState} from "react";
import {Link} from "react-router-dom";
import type {PartnerProps} from "./ExternalPartnerPage";
import {friendlyDate,partnerRequest,partnerUrl} from "./partnerApi";
import {ActionNotice,Section,State,Status,usePartnerLoad} from "./PartnerPrimitives";

type RFQ={id:number;rfq_number:string;title:string;status:string;response_due_at:string|null};
type Item={id:number;line_number:number;part_number:string|null;description:string;quantity:number;uom:string;
  received_quantity?:number;alternates_allowed?:boolean;technical_specification?:string|null;
  controlled_document_id?:string|null;controlled_document_revision?:string|null};
type Event={id:string;action:string;message:string|null;created_at:string};
type Quote={id:string;external_reference:string;revision_no:number;status:string;total_amount:string;currency:string};
type RFQDetails=RFQ&{lines:Item[];terms:string|null;quality_clauses:string|null;my_quotes:Quote[];history:Event[]};
type PO={id:number;po_number:string;status:string;promised_delivery_date:string|null;currency:string;acknowledged_at:string|null};
type PODetails=PO&{lines:Item[];history:Event[];shipments:{id:string;shipment_reference:string;status:string;receiving_status?:string|null}[];
  receipts:{id:number;receipt_number:string;status:string}[]};
type QuoteLine={requisition_line_id:number;part_number:string;manufacturer:string;quantity:number;uom:string;
  unit_price:number;available_quantity:number;alternate_proposal:string;traceability_statement:string;promised_date:string};
type ShipLine={po_line_id:number;part_number:string;quantity:number;serial_lot_batch:string;manufacturer:string;source:string;
  traceability_reference:string;release_certificate_reference:string;shelf_life_expires_on:string;material_case:string};
const retryKey=()=>crypto.randomUUID().replace(/-/g,"");
const errmsg=(e:unknown)=>e instanceof Error?e.message:"Transaction failed";
const today=()=>new Date().toISOString().slice(0,10);
function Timeline({events}:{events:Event[]}){
  return <details><summary>Submission / clarification history ({events.length})</summary>
    {!events.length&&<p>No responses yet.</p>}
    {events.map(ev=><p key={ev.id}><strong>{ev.action.replaceAll("_"," ")}</strong>
      {" · "}{friendlyDate(ev.created_at)}{ev.message&&" · "+ev.message}</p>)}
  </details>;
}
async function controlledFile(tenant:string,path:string,label:string){
  const r=await fetch(partnerUrl(tenant,path),{credentials:"include",cache:"no-store"});
  if(!r.ok)throw Error("Access to the controlled document was denied");
  const url=URL.createObjectURL(await r.blob());
  const anchor=document.createElement("a");anchor.href=url;anchor.download=label;anchor.click();
  window.setTimeout(()=>URL.revokeObjectURL(url),2000);
}
export default function PartnerProcurementWorkspace({tenant,csrf,capabilities}:PartnerProps){
  const [tab,setTab]=useState<"rfq"|"po">("rfq");const [revision,setRevision]=useState(0);
  const [rfqId,setRfqId]=useState<number|null>(null);const [poId,setPoId]=useState<number|null>(null);
  const [error,setError]=useState("");const [notice,setNotice]=useState("");const [busy,setBusy]=useState(false);
  const [reference,setReference]=useState("");const [quoteRevision,setQuoteRevision]=useState(1);
  const [currency,setCurrency]=useState("USD");const [validUntil,setValidUntil]=useState("");
  const [tax,setTax]=useState(0);const [freight,setFreight]=useState(0);const [lead,setLead]=useState(7);
  const [quoteLines,setQuoteLines]=useState<QuoteLine[]>([]);
  const [poAck,setPoAck]=useState("");const [shipmentRef,setShipmentRef]=useState("");
  const [dispatch,setDispatch]=useState(today());const [arrival,setArrival]=useState("");
  const [airwayBill,setAirwayBill]=useState("");const [packingList,setPackingList]=useState("");
  const [shipLines,setShipLines]=useState<ShipLine[]>([]);
  const [message,setMessage]=useState("");const [action,setAction]=useState("CLARIFICATION");
  const [lineId,setLineId]=useState<number|null>(null);const [newDate,setNewDate]=useState("");
  const [documents,setDocuments]=useState<{id:number;title:string;revision:string|null}[]>([]);
  const [invoiceRef,setInvoiceRef]=useState("");const [invoiceTotal,setInvoiceTotal]=useState(0);
  const [invoiceOriginal,setInvoiceOriginal]=useState("");
  const [invoiceCandidates,setInvoiceCandidates]=useState<{id:string;filename:string;status:string}[]>([]);
  const [invoiceMatches,setInvoiceMatches]=useState<{id:number;invoice_number:string;status:string;matched_at:string}[]>([]);
  const canRespond=capabilities.includes("procurement.respond");
  const listing=usePartnerLoad(signal=>partnerRequest<{items:RFQ[]}>(tenant,"commerce/rfqs",{signal}),tenant+":rfqs:"+revision);
  const purchases=usePartnerLoad(signal=>partnerRequest<{items:PO[]}>(tenant,"commerce/purchase-orders",{signal}),tenant+":pos:"+revision);
  const rfq=usePartnerLoad(signal=>rfqId===null?Promise.resolve(null):
    partnerRequest<RFQDetails>(tenant,"commerce/rfqs/"+rfqId,{signal}),tenant+":rfq:"+rfqId+":"+revision);
  const po=usePartnerLoad(signal=>poId===null?Promise.resolve(null):
    partnerRequest<PODetails>(tenant,"commerce/purchase-orders/"+poId,{signal}),tenant+":po:"+poId+":"+revision);
  useEffect(()=>{if(!rfq.value)return;
    setQuoteLines(rfq.value.lines.map(l=>({requisition_line_id:l.id,part_number:l.part_number||"",
      manufacturer:"",quantity:l.quantity,uom:l.uom,unit_price:0,available_quantity:l.quantity,
      alternate_proposal:"",traceability_statement:"",promised_date:""})));
    const previous=rfq.value.my_quotes[0];
    setReference(previous?.external_reference||"");setQuoteRevision(previous?previous.revision_no+1:1);
    setValidUntil(rfq.value.response_due_at?.slice(0,10)||today());
  },[rfq.value]);
  useEffect(()=>{if(!po.value)return;
    setShipLines(po.value.lines.map(l=>({po_line_id:l.id,part_number:l.part_number||"",
      quantity:Math.max(0,l.quantity-(l.received_quantity||0)),serial_lot_batch:"",
      manufacturer:"",source:"",traceability_reference:"",release_certificate_reference:"",
      shelf_life_expires_on:"",material_case:""})));
    if(capabilities.includes("document.read")){
      void partnerRequest<{items:{id:string;filename:string;status:string;related_kind:string;
        related_id:string|null;evidence_type:string}[]}>(tenant,"documents/submissions?limit=50&offset=0")
        .then(q=>setInvoiceCandidates(q.items.filter(item=>item.related_kind==="PO" &&
          item.related_id===String(po.value!.id) &&
          ["SUPPLIER_INVOICE","PROFORMA_INVOICE","CREDIT_NOTE"].includes(item.evidence_type) &&
          item.status==="ACCEPTED")))
        .catch(()=>setInvoiceCandidates([]));
    }
    void partnerRequest<{items:{id:number;invoice_number:string;status:string;matched_at:string}[]}>(tenant,
      "commerce/purchase-orders/"+po.value.id+"/invoice-status")
      .then(q=>setInvoiceMatches(q.items)).catch(()=>setInvoiceMatches([]));
    void partnerRequest<{items:{id:number;title:string;revision:string|null}[]}>(tenant,
      "commerce/purchase-orders/"+po.value.id+"/documents").then(r=>setDocuments(r.items)).catch(()=>setDocuments([]));
  },[po.value,tenant]);
  async function execute(call:()=>Promise<unknown>,ok:string){
    setBusy(true);setError("");setNotice("");
    try{await call();setNotice(ok);setRevision(n=>n+1);setMessage("");}
    catch(e){setError(errmsg(e));}finally{setBusy(false);}
  }
  async function submitQuote(e:React.FormEvent){
    e.preventDefault();if(rfqId===null)return;
    await execute(()=>partnerRequest(tenant,"commerce/rfqs/"+rfqId+"/quotes",{
      method:"POST",csrf,body:{quote_reference:reference,revision:quoteRevision,currency,
        tax_amount:tax,freight_amount:freight,lead_time_days:lead,valid_until:validUntil,
        note:message,idempotency_key:retryKey(),lines:quoteLines.map(l=>({...l,
          manufacturer:l.manufacturer||null,alternate_proposal:l.alternate_proposal||null,
          traceability_statement:l.traceability_statement||null,promised_date:l.promised_date||null}))}}),
      "Quote received by internal Procurement for evaluation; no PO was approved.");
  }
  async function sendMessage(kind:"rfqs"|"purchase-orders",id:number){
    await execute(()=>partnerRequest(tenant,"commerce/"+kind+"/"+id+"/messages",{
      method:"POST",csrf,body:{action,message,line_id:lineId,promised_date:newDate||null,
        idempotency_key:retryKey()}}),"Correspondence submitted for internal review.");
  }
  async function submitShipment(e:React.FormEvent){
    e.preventDefault();if(poId===null)return;
    await execute(()=>partnerRequest(tenant,"commerce/purchase-orders/"+poId+"/shipments",{
      method:"POST",csrf,body:{shipment_reference:shipmentRef,dispatch_date:dispatch,
        estimated_arrival:arrival||null,airway_bill:airwayBill||null,packing_list_reference:packingList||null,
        notes:message,lines:shipLines.filter(l=>l.quantity>0).map(l=>({...l,
          manufacturer:l.manufacturer||null,source:l.source||null,serial_lot_batch:l.serial_lot_batch||null,
          traceability_reference:l.traceability_reference||null,
          release_certificate_reference:l.release_certificate_reference||null,
          shelf_life_expires_on:l.shelf_life_expires_on||null,
          material_case:l.material_case||null}))}}),
      "Advance shipment notice recorded. Stores receipt and Quality inspection remain internal.");
  }
  async function submitInvoiceNotice(e:React.FormEvent){
    e.preventDefault();if(poId===null)return;
    await execute(()=>partnerRequest(tenant,"commerce/purchase-orders/"+poId+"/invoice-notices",{
      method:"POST",csrf,body:{invoice_reference:invoiceRef,invoice_total:invoiceTotal,
        currency:po.value?.currency||"USD",source_submission_id:invoiceOriginal,
        note:message,idempotency_key:retryKey()}}),
      "Invoice recorded for Finance registration; no payment approval was granted.");
  }
  function qfield(id:number,field:keyof QuoteLine,value:string|number){
    setQuoteLines(a=>a.map(v=>v.requisition_line_id===id?{...v,[field]:value}:v));
  }
  function sfield(id:number,field:keyof ShipLine,value:string|number){
    setShipLines(a=>a.map(v=>v.po_line_id===id?{...v,[field]:value}:v));
  }
  return <div className="partner-stack">
    <div className="partner-buttons">
      <button type="button" aria-pressed={tab==="rfq"} onClick={()=>setTab("rfq")}>RFQs and quotations</button>
      <button type="button" aria-pressed={tab==="po"} onClick={()=>setTab("po")}>POs and deliveries</button>
      <button type="button" onClick={()=>setRevision(v=>v+1)}>Refresh</button>
    </div>
    {tab==="rfq"&&<Section title="Assigned RFQ invitations" description="Only RFQs issued to your supplier. Competitors and internal approvals are never shown.">
      <State pending={listing.pending} error={listing.error} retry={listing.reload}/>
      {!listing.pending&&!listing.value?.items.length&&<p className="partner-empty">No RFQ invitations.</p>}
      {listing.value?.items.map(r=><div className="partner-row" key={r.id}><div><strong>{r.rfq_number} · {r.title}</strong>
        <small>Respond by {friendlyDate(r.response_due_at)}</small></div><div><Status value={r.status}/>
        <button type="button" onClick={()=>setRfqId(r.id)}>Open</button></div></div>)}
    </Section>}
    {tab==="rfq"&&rfqId!==null&&<Section title="RFQ response & revisions" description="Alternates and deviations require technical review; a quote does not authorize award.">
      <State pending={rfq.pending} error={rfq.error} retry={rfq.reload}/>
      {rfq.value&&<>
        <strong>{rfq.value.rfq_number}</strong><p>{rfq.value.terms}</p><p>{rfq.value.quality_clauses}</p>
        <table><thead><tr><th>Invited line</th><th>Quantity</th><th>Controlled specification</th></tr></thead><tbody>
          {rfq.value.lines.map(l=><tr key={l.id}><td>{l.line_number} · {l.part_number||"Service"} · {l.description}</td>
            <td>{l.quantity} {l.uom}</td><td>{l.technical_specification||"—"}
              {l.controlled_document_id&&<button type="button" onClick={()=>void controlledFile(tenant,
                "commerce/rfqs/"+rfqId+"/specifications/"+l.id,
                rfq.value!.rfq_number+"-line-"+l.line_number).catch(e=>setError(errmsg(e)))}>Download released specification</button>}
            </td></tr>)}</tbody></table>
        {canRespond&&<button type="button" disabled={busy} onClick={()=>void execute(
          ()=>partnerRequest(tenant,"commerce/rfqs/"+rfqId+"/acknowledge",{
            method:"POST",csrf,body:{reference:null,note:message,idempotency_key:retryKey()}}),
          "RFQ receipt acknowledged.")}>Acknowledge invitation</button>}
        <Timeline events={rfq.value.history}/>
        {rfq.value.my_quotes.map(q=><div className="partner-row" key={q.id}><div>
          <strong>{q.external_reference} · R{q.revision_no}</strong>
          <small>{q.currency} {q.total_amount}</small></div><div><Status value={q.status}/>
          {canRespond&&q.status==="SUBMITTED"&&<button type="button" disabled={busy} onClick={()=>void execute(
            ()=>partnerRequest(tenant,"commerce/quotes/"+q.id+"/withdraw",{
              method:"POST",csrf,body:{reference:null,note:message.length>=8?message:"Supplier withdraws this unevaluated quotation revision.",idempotency_key:retryKey()}}),
            "Quotation withdrawal recorded.")}>Withdraw unevaluated revision</button>}</div></div>)}
        {canRespond&&<form className="partner-form" onSubmit={e=>void submitQuote(e)}>
          <h3>Submit quote / next revision</h3><div className="partner-buttons">
            <label>Reference<input required minLength={2} value={reference} onChange={e=>setReference(e.target.value)}/></label>
            <label>Revision<input type="number" min={1} value={quoteRevision} onChange={e=>setQuoteRevision(Number(e.target.value))}/></label>
            <label>Currency<input required maxLength={3} value={currency} onChange={e=>setCurrency(e.target.value.toUpperCase())}/></label>
            <label>Valid to<input required type="date" value={validUntil} onChange={e=>setValidUntil(e.target.value)}/></label>
            <label>Lead days<input type="number" min={0} value={lead} onChange={e=>setLead(Number(e.target.value))}/></label>
            <label>Tax<input type="number" min={0} step=".01" value={tax} onChange={e=>setTax(Number(e.target.value))}/></label>
            <label>Freight<input type="number" min={0} step=".01" value={freight} onChange={e=>setFreight(Number(e.target.value))}/></label>
          </div>
          {quoteLines.map(l=><fieldset key={l.requisition_line_id}><legend>Invited line #{l.requisition_line_id}</legend>
            <div className="partner-buttons">
              <label>Part number<input required value={l.part_number} onChange={e=>qfield(l.requisition_line_id,"part_number",e.target.value)}/></label>
              <label>Manufacturer<input value={l.manufacturer} onChange={e=>qfield(l.requisition_line_id,"manufacturer",e.target.value)}/></label>
              <label>Quantity<input type="number" min=".001" step="any" value={l.quantity} onChange={e=>qfield(l.requisition_line_id,"quantity",Number(e.target.value))}/></label>
              <label>Unit price<input type="number" min={0} step=".0001" value={l.unit_price} onChange={e=>qfield(l.requisition_line_id,"unit_price",Number(e.target.value))}/></label>
              <label>Available<input type="number" min={0} step="any" value={l.available_quantity} onChange={e=>qfield(l.requisition_line_id,"available_quantity",Number(e.target.value))}/></label>
              <label>Promise date<input type="date" value={l.promised_date} onChange={e=>qfield(l.requisition_line_id,"promised_date",e.target.value)}/></label>
              <label>Alternate / deviation<input value={l.alternate_proposal} onChange={e=>qfield(l.requisition_line_id,"alternate_proposal",e.target.value)}/></label>
              <label>Traceability<input value={l.traceability_statement} onChange={e=>qfield(l.requisition_line_id,"traceability_statement",e.target.value)}/></label>
            </div></fieldset>)}
          <label>Notes<textarea rows={2} value={message} onChange={e=>setMessage(e.target.value)}/></label>
          <button disabled={busy||!reference||!validUntil||!quoteLines.length}>Submit to Procurement</button>
        </form>}
        {canRespond&&<div className="partner-form"><h3>Clarification / alternate proposal</h3>
          <select value={action} onChange={e=>setAction(e.target.value)}>
            {["CLARIFICATION","ALTERNATE_REQUEST","AVAILABILITY"].map(v=><option key={v} value={v}>{v.replaceAll("_"," ")}</option>)}
          </select><select value={lineId||""} onChange={e=>setLineId(e.target.value?Number(e.target.value):null)}>
            <option value="">General</option>{rfq.value.lines.map(l=><option value={l.id} key={l.id}>{l.line_number} · {l.description}</option>)}
          </select><textarea minLength={8} value={message} onChange={e=>setMessage(e.target.value)}/>
          <button type="button" disabled={busy||message.length<8} onClick={()=>void sendMessage("rfqs",rfqId)}>Send request</button>
        </div>}
        <Link to={"/partner/"+encodeURIComponent(tenant)+"/documents"}>Attach quotation or technical documents (controlled intake)</Link>
      </>}
    </Section>}
    {tab==="po"&&<Section title="Issued purchase orders" description="Only purchase orders sent to your supplier. No internal budgets, payment approval or other supplier data.">
      <State pending={purchases.pending} error={purchases.error} retry={purchases.reload}/>
      {!purchases.pending&&!purchases.value?.items.length&&<p className="partner-empty">No issued purchase orders.</p>}
      {purchases.value?.items.map(p=><div key={p.id} className="partner-row"><div><strong>{p.po_number}</strong>
        <small>{friendlyDate(p.promised_delivery_date)}</small></div><div><Status value={p.status}/>
          <button type="button" onClick={()=>setPoId(p.id)}>Open PO</button></div></div>)}
    </Section>}
    {tab==="po"&&poId!==null&&<Section title="PO acceptance, shipment and receiving" description="Stores and Quality control physical acceptance, quarantine, inspection and release.">
      <State pending={po.pending} error={po.error} retry={po.reload}/>
      {po.value&&<>
        <strong>{po.value.po_number} · {po.value.currency}</strong>
        <table><thead><tr><th>Part / material</th><th>Ordered</th><th>Internally received</th></tr></thead><tbody>
          {po.value.lines.map(l=><tr key={l.id}><td>{l.part_number||"Service"} · {l.description}</td>
            <td>{l.quantity} {l.uom}</td><td>{l.received_quantity||0} {l.uom}</td></tr>)}</tbody></table>
        {documents.map(d=><button key={d.id} type="button" onClick={()=>void controlledFile(tenant,
          "commerce/purchase-orders/"+poId+"/documents/"+d.id+"/download",
          po.value!.po_number+"-"+d.title).catch(e=>setError(errmsg(e)))}>Download {d.title} {d.revision||""}</button>)}
        {canRespond&&<div className="partner-form"><label>Supplier PO acceptance reference<input value={poAck} onChange={e=>setPoAck(e.target.value)}/></label>
          <button type="button" disabled={busy||poAck.trim().length<2} onClick={()=>void execute(
            ()=>partnerRequest(tenant,"commerce/purchase-orders/"+poId+"/acknowledge",{
              method:"POST",csrf,body:{reference:poAck,note:message,idempotency_key:retryKey()}}),
            "PO acknowledgement received.")}>Accept issued PO</button></div>}
        {canRespond&&<form className="partner-form" onSubmit={e=>void submitShipment(e)}>
          <h3>Advance shipment notice</h3><div className="partner-buttons">
            <label>Shipment ref<input required value={shipmentRef} onChange={e=>setShipmentRef(e.target.value)}/></label>
            <label>Dispatch<input type="date" required value={dispatch} onChange={e=>setDispatch(e.target.value)}/></label>
            <label>Expected arrival<input type="date" value={arrival} onChange={e=>setArrival(e.target.value)}/></label>
            <label>Airway bill<input value={airwayBill} onChange={e=>setAirwayBill(e.target.value)}/></label>
            <label>Packing list ref<input value={packingList} onChange={e=>setPackingList(e.target.value)}/></label>
          </div>
          {shipLines.map(l=><fieldset key={l.po_line_id}><legend>PO line {l.po_line_id}</legend><div className="partner-buttons">
            <label>Part number<input required value={l.part_number} onChange={e=>sfield(l.po_line_id,"part_number",e.target.value)}/></label>
            <label>Qty<input type="number" min={0} step="any" value={l.quantity} onChange={e=>sfield(l.po_line_id,"quantity",Number(e.target.value))}/></label>
            <label>Manufacturer<input value={l.manufacturer} onChange={e=>sfield(l.po_line_id,"manufacturer",e.target.value)}/></label>
            <label>Manufacturer / vendor source<input value={l.source} onChange={e=>sfield(l.po_line_id,"source",e.target.value)}/></label>
            <label>Serial/lot/batch<input value={l.serial_lot_batch} onChange={e=>sfield(l.po_line_id,"serial_lot_batch",e.target.value)}/></label>
            <label>Traceability<input value={l.traceability_reference} onChange={e=>sfield(l.po_line_id,"traceability_reference",e.target.value)}/></label>
            <label>Release/conformity ref<input value={l.release_certificate_reference} onChange={e=>sfield(l.po_line_id,"release_certificate_reference",e.target.value)}/></label>
            <label>Shelf life expires<input type="date" value={l.shelf_life_expires_on} onChange={e=>sfield(l.po_line_id,"shelf_life_expires_on",e.target.value)}/></label>
            <label>Material case<select value={l.material_case} onChange={e=>sfield(l.po_line_id,"material_case",e.target.value)}>
              <option value="">Normal</option>{["EXCHANGE","LOAN","REPAIR","WARRANTY","RETURN","RMA","REPLACEMENT"].map(v=><option key={v} value={v}>{v}</option>)}
            </select></label>
          </div></fieldset>)}
          <button disabled={busy||!shipmentRef||!shipLines.some(l=>l.quantity>0)}>Submit ASN — pending Stores receipt</button>
        </form>}
        {po.value.shipments.map(sh=><div className="partner-row" key={sh.id}>
          <div><strong>ASN {sh.shipment_reference}</strong>
            <small>Stores receipt: {sh.receiving_status||"Not received"}</small></div>
          <div><Status value={sh.status}/>
            {canRespond&&sh.status==="ADVISED"&&<button type="button" disabled={busy} onClick={()=>void execute(
              ()=>partnerRequest(tenant,"commerce/shipments/"+sh.id+"/cancel",{
                method:"POST",csrf,body:{reference:null,
                  note:message.length>=8?message:"Supplier withdraws the undelivered shipment notice.",
                  idempotency_key:retryKey()}}),"Advance shipment notice cancelled before receiving.")}>Cancel undelivered ASN</button>}
          </div></div>)}
        <Section title="Internal receiving and inspection" description="Supplier uploads never mark material serviceable.">
          {po.value.receipts.length?po.value.receipts.map(rc=><div className="partner-row" key={rc.id}>
            <strong>{rc.receipt_number}</strong><Status value={rc.status}/></div>):
            <p className="partner-empty">No goods received.</p>}
        </Section>
        <Timeline events={po.value.history}/>
        {canRespond&&<div className="partner-form"><h3>Clarification, delivery changes, returns/RMA and warranty</h3>
          <select value={action} onChange={e=>setAction(e.target.value)}>
            {["CLARIFICATION","DELIVERY_CHANGE","PARTIAL_AVAILABILITY","WARRANTY","RETURN","RMA","REPAIR","EXCHANGE","LOAN","REJECTED_MATERIAL","CREDIT","REPLACEMENT"].map(v=>
              <option key={v} value={v}>{v.replaceAll("_"," ")}</option>)}
          </select>
          <select value={lineId||""} onChange={e=>setLineId(e.target.value?Number(e.target.value):null)}>
            <option value="">Whole PO</option>{po.value.lines.map(l=><option key={l.id} value={l.id}>{l.line_number} · {l.description}</option>)}
          </select>
          {action==="DELIVERY_CHANGE"&&<label>Proposed delivery<input required type="date" value={newDate} onChange={e=>setNewDate(e.target.value)}/></label>}
          <textarea rows={3} minLength={8} value={message} onChange={e=>setMessage(e.target.value)}/>
          <button type="button" disabled={busy||message.trim().length<8} onClick={()=>void sendMessage("purchase-orders",poId)}>Request internal decision</button>
        </div>}
        {canRespond&&<form className="partner-form" onSubmit={e=>void submitInvoiceNotice(e)}>
          <h3>Submit invoice to Finance (without payment authority)</h3>
          <p>First upload the supplier invoice to the controlled Documents workspace against this PO and obtain Document Control retention registration.</p>
          <label>Invoice original<select required value={invoiceOriginal}
            onChange={e=>setInvoiceOriginal(e.target.value)}>
            <option value="">Select accepted supplier invoice original</option>
            {invoiceCandidates.map(i=><option key={i.id} value={i.id}>{i.filename}</option>)}
          </select></label>
          <label>Invoice number<input required minLength={2} maxLength={128} value={invoiceRef}
            onChange={e=>setInvoiceRef(e.target.value)}/></label>
          <label>Invoice total ({po.value.currency})<input required type="number" min=".01" step=".01"
            value={invoiceTotal} onChange={e=>setInvoiceTotal(Number(e.target.value))}/></label>
          <button disabled={busy||!invoiceOriginal||invoiceTotal<=0||invoiceRef.length<2}>Notify Finance of invoice</button>
        </form>}
        <details><summary>Permitted invoice matching status ({invoiceMatches.length})</summary>
          {invoiceMatches.map(i=><p key={i.id}>{i.invoice_number}: {i.status}</p>)}
          {!invoiceMatches.length&&<p>No Finance invoice matching record is available.</p>}
        </details>
        <Link to={"/partner/"+encodeURIComponent(tenant)+"/documents"}>Upload invoice, packing list and conformity documents</Link>
      </>}
    </Section>}
    <ActionNotice value={error} error/><ActionNotice value={notice}/>
  </div>;
}
