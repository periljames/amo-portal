import React,{useCallback,useEffect,useMemo,useState} from "react";
import {Link,useParams} from "react-router-dom";
import {apiRequest} from "../../services/apiClient";

type Provider={id:string;supplier_id:number;legal_name:string};
type Scope={id:number;supplier_id:number;category:string;site_code:string;product_family:string;approval_number:string;authority:string};
type Contract={id:string;supplier_id:number;contract_number:string;title:string;status:string};
type Coordinator={id:string;full_name:string;staff_code:string;role:string};
type Options={providers:Provider[];scopes:Scope[];contracts:Contract[];coordinators:Coordinator[]};
type WorkList={id:string;work_number:string;work_type:string;work_title:string;status:string;version:number;supplier_id:number;site_code:string;updated_at:string};
type Work=WorkList&{function:string;scope_text:string;contract_id:string;purchase_order_id:number|null;
  internal_work_reference:string;technical_coordinator_id:string;asset_kind:string;registration:string|null;
  part_number:string|null;serial_number:string|null;defect:string;data_reference:string;data_revision:string;
  inspections_json:string[];required_release:string;requirements_json:Record<string,string|boolean|null>;
  authorized_by:string|null;accepted_by:string|null};
type Detail={work:Work;allowed_actions:string[];
  closure_blockers:string[];
  history:{id:string;action:string;from_state:string|null;to_state:string|null;reason:string;created_at:string}[];
  additional_work:{id:string;description:string;state:string;decision_reason:string|null;technical_data:string|null;commercial_reference:string|null}[];
  custody:{id:string;description:string;item_type:string;quantity:string;uom:string;state:string;serial_batch:string|null;stores_reference:string}[];
  evidence:{id:string;category:string;filename:string;status:string;retention_status:string|null}[]};
type Candidate={id:string;filename:string;evidence_type:string;status:string;created_at:string};
type Grant={id:string;email:string;role_code:string;capabilities_json:string[];object_scope_json:Record<string,string[]>};
const key=()=>crypto.randomUUID().replace(/-/g,"");
const EVIDENCE=["INSPECTION_REPORT","STRIP_REPORT","TEST_RESULT","MAINTENANCE_RELEASE","WORK_RECORD","SHIPPING","RECEIVING","SAFETY","ADDITIONAL_WORK","OTHER"];
const CUSTODY=["COMPONENT","EXCHANGE","LOAN","TOOL","EQUIPMENT","CUSTOMER_PROPERTY","MATERIAL","CONSUMABLE"];

export default function ContractedWorkModule(){
  const {amoCode=""}=useParams();
  const root="/api/maintenance/"+encodeURIComponent(amoCode)+"/contracted-work";
  const [items,setItems]=useState<WorkList[]>([]);
  const [options,setOptions]=useState<Options|null>(null);
  const [selected,setSelected]=useState("");
  const [detail,setDetail]=useState<Detail|null>(null);
  const [candidates,setCandidates]=useState<Candidate[]>([]);
  const [grants,setGrants]=useState<Grant[]>([]);
  const [tab,setTab]=useState<"scope"|"communications"|"additional"|"custody"|"evidence"|"history">("scope");
  const [loading,setLoading]=useState(true);const [busy,setBusy]=useState(false);
  const [error,setError]=useState("");const [notice,setNotice]=useState("");
  const [newOpen,setNewOpen]=useState(false);
  const [supplier,setSupplier]=useState("");
  const [form,setForm]=useState<Record<string,string>>({
    work_number:"",work_type:"WORKSHOP",work_title:"",function:"",scope_text:"",site_code:"",
    scope_id:"",contract_id:"",internal_work_reference:"",technical_coordinator_id:"",
    asset_kind:"COMPONENT",registration:"",part_number:"",serial_number:"",asset_description:"",
    defect:"",data_reference:"",data_revision:"",inspections:"",required_release:"",
    purchase_order_id:"",data_manual_id:"",data_revision_id:"",governed_repair_order_reference:"",product_family:"",contract_function_approval_reference:"",state_of_registry:"",foreign_approval_reference:"",
    operator_requirements:"",release_wording:"",authority_acceptance_reference:"",
    safety_assessment_reference:"",operator_approval_reference:"",restriction_review_reference:"",
  });
  const [foreign,setForeign]=useState(false);const [authorityRequired,setAuthorityRequired]=useState(false);
  const [safetyRequired,setSafetyRequired]=useState(false);
  const [decision,setDecision]=useState("");const [reason,setReason]=useState("");
  const [variationId,setVariationId]=useState("");const [variationDecision,setVariationDecision]=useState("APPROVED");
  const [variationData,setVariationData]=useState("");const [amendment,setAmendment]=useState("");
  const [variationCommercial,setVariationCommercial]=useState("");
  const [custodyType,setCustodyType]=useState("COMPONENT");const [custodyDescription,setCustodyDescription]=useState("");
  const [custodyPart,setCustodyPart]=useState("");const [custodySerial,setCustodySerial]=useState("");
  const [custodyQty,setCustodyQty]=useState("1");const [custodyUom,setCustodyUom]=useState("EA");
  const [storesRef,setStoresRef]=useState("");const [custodyItem,setCustodyItem]=useState("");
  const [custodyState,setCustodyState]=useState("");const [custodyReason,setCustodyReason]=useState("");
  const [evidenceId,setEvidenceId]=useState("");const [evidenceCategory,setEvidenceCategory]=useState("MAINTENANCE_RELEASE");
  const [grantId,setGrantId]=useState("");
  const field=(name:string)=>(e:React.ChangeEvent<HTMLInputElement|HTMLTextAreaElement|HTMLSelectElement>)=>
    setForm(old=>({...old,[name]:e.target.value}));
  const load=useCallback(async()=>{
    setLoading(true);setError("");
    try{const [queue,opts]=await Promise.all([
      apiRequest<{items:WorkList[]}>(root,{cacheTtlMs:0}),
      apiRequest<Options>(root+"/options",{cacheTtlMs:0})]);
      setItems(queue.items);setOptions(opts);
      setSelected(current=>queue.items.some(i=>i.id===current)?current:(queue.items[0]?.id||""));
    }catch(e){setError(e instanceof Error?e.message:"Maintenance register could not load");}
    finally{setLoading(false);}
  },[root]);
  const reloadDetail=useCallback(async()=>{
    if(!selected){setDetail(null);return;}
    try{const [value,evidence,assigned]=await Promise.all([
      apiRequest<Detail>(root+"/"+encodeURIComponent(selected),{cacheTtlMs:0}),
      apiRequest<{items:Candidate[]}>(root+"/"+encodeURIComponent(selected)+"/available-evidence",{cacheTtlMs:0}),
      apiRequest<{items:Grant[]}>(root+"/"+encodeURIComponent(selected)+"/grants",{cacheTtlMs:0}).catch(()=>({items:[]})),
    ]);
      setDetail(value);setCandidates(evidence.items);setGrants(assigned.items);
    }catch(e){setError(e instanceof Error?e.message:"The selected work record is unavailable");}
  },[root,selected]);
  useEffect(()=>{void load();},[load]);
  useEffect(()=>{void reloadDetail();},[reloadDetail]);
  const provider=options?.providers.find(p=>String(p.supplier_id)===supplier);
  const scopes=useMemo(()=>options?.scopes.filter(x=>String(x.supplier_id)===supplier)||[],[options,supplier]);
  const contracts=useMemo(()=>options?.contracts.filter(x=>String(x.supplier_id)===supplier)||[],[options,supplier]);
  const work=detail?.work;
  async function mutate(endpoint:string,body:unknown,message:string){
    setBusy(true);setError("");setNotice("");
    try{
      const response=await apiRequest<{id?:string}>(root+endpoint,{method:"POST",body:JSON.stringify(body)});
      setNotice(message);setReason("");
      if(endpoint==="")setSelected(response.id||"");
      await load();await reloadDetail();
    }catch(e){setError(e instanceof Error?e.message:"The governed maintenance transaction was rejected");}
    finally{setBusy(false);}
  }
  function submitNew(event:React.FormEvent){
    event.preventDefault();if(!provider)return;
    void mutate("",{
      work_number:form.work_number,work_type:form.work_type,work_title:form.work_title,
      supplier_id:provider.supplier_id,provider_id:provider.id,scope_id:Number(form.scope_id),
      contract_id:form.contract_id,function:form.function,scope_text:form.scope_text,
      site_code:form.site_code,internal_work_reference:form.internal_work_reference,
      technical_coordinator_id:form.technical_coordinator_id,asset_kind:form.asset_kind,
      registration:form.registration||null,part_number:form.part_number||null,
      serial_number:form.serial_number||null,asset_description:form.asset_description||null,
      defect:form.defect,data_reference:form.data_reference,data_revision:form.data_revision,
      inspections:form.inspections.split("\n").map(x=>x.trim()).filter(Boolean),
      required_release:form.required_release,
      purchase_order_id:form.purchase_order_id?Number(form.purchase_order_id):null,
      data_manual_id:form.data_manual_id||null,data_revision_id:form.data_revision_id||null,
      requirements:{
        foreign,governed_repair_order_reference:form.governed_repair_order_reference||null,
        product_family:form.product_family||null,
        contract_function_approval_reference:form.contract_function_approval_reference||null,state_of_registry:form.state_of_registry,foreign_approval_reference:form.foreign_approval_reference,
        operator_requirements:form.operator_requirements,release_wording:form.release_wording,
        authority_approval_required:authorityRequired,authority_acceptance_reference:form.authority_acceptance_reference,
        safety_assessment_required:safetyRequired,safety_assessment_reference:form.safety_assessment_reference,
        restriction_review_reference:form.restriction_review_reference,
        operator_approval_reference:form.operator_approval_reference,
      }
    },"Technical work order drafted. It cannot be dispatched until Maintenance and Quality approvals are recorded.");
    setNewOpen(false);
  }
  return <main className="proc-section" style={{padding:"1.5rem",maxWidth:1400,margin:"auto"}}>
    <header className="proc-section__head"><div><h1>Contracted Maintenance</h1>
      <p>MOPM §2.23: controlled technical authorization, external AMO execution, Stores custody and Safarilink acceptance. Commercial POs never authorize maintenance or release.</p>
      <Link to={`/maintenance/${encodeURIComponent(amoCode)}/procurement`}>Related Procurement</Link>
      {" · "}<Link to={`/maintenance/${encodeURIComponent(amoCode)}/quality/external-providers`}>Provider Quality</Link></div>
      <div><button onClick={()=>void load()} disabled={loading}>Refresh</button>{" "}
        <button onClick={()=>setNewOpen(x=>!x)}>{newOpen?"Close form":"New controlled work order"}</button></div>
    </header>
    {loading&&<p role="status">Loading contracted work and approved sources…</p>}
    {error&&<p role="alert">{error}</p>}{notice&&<p role="status">{notice}</p>}
    {newOpen&&<form className="partner-form" onSubmit={submitNew} style={{marginBlock:"1rem"}}>
      <h2>Initiate technical contracted work</h2>
      <label>Contractor<select required value={supplier} onChange={e=>{setSupplier(e.target.value);setForm(v=>({...v,scope_id:"",contract_id:"",site_code:""}));}}>
        <option value="">Choose Quality-managed provider</option>
        {options?.providers.map(x=><option key={x.id} value={x.supplier_id}>{x.legal_name}</option>)}
      </select></label>
      <label>Exact approved site and capability<select required value={form.scope_id} onChange={e=>{const v=scopes.find(x=>String(x.id)===e.target.value);setForm(old=>({...old,scope_id:e.target.value,site_code:v?.site_code||""}));}}>
        <option value="">Select a verified maintenance capability</option>
        {scopes.map(x=><option key={x.id} value={x.id}>{x.site_code} · {x.category} · {x.product_family} · {x.approval_number}</option>)}
      </select></label>
      <label>Executed maintenance agreement<select required value={form.contract_id} onChange={field("contract_id")}><option value="">Choose governing agreement</option>
        {contracts.map(x=><option key={x.id} value={x.id}>{x.contract_number} · {x.title}</option>)}</select></label>
      <label>Work type<select value={form.work_type} onChange={field("work_type")}>{["BASE","LINE","WORKSHOP","SPECIALISED"].map(x=><option key={x}>{x}</option>)}</select></label>
      <label>Unique repair/work order<input required minLength={3} value={form.work_number} onChange={field("work_number")}/></label>
      <label>Work title<input required minLength={5} value={form.work_title} onChange={field("work_title")}/></label>
      <label>Defined contracted maintenance function<input required minLength={8} value={form.function} onChange={field("function")}/></label>
      <label>Exact approved aircraft/engine/component product family<input value={form.product_family} onChange={field("product_family")} placeholder="Must match Quality-approved capability where restricted"/></label>
      <label>Agreement-specific contracted function reference<input value={form.contract_function_approval_reference} onChange={field("contract_function_approval_reference")} placeholder="Required if the exact function is not explicitly written in contract scope"/></label>
      <label>Controlling internal work-package / maintenance request reference<input required value={form.internal_work_reference} onChange={field("internal_work_reference")}/></label>
      <label>Responsible technical coordinator<select required value={form.technical_coordinator_id} onChange={field("technical_coordinator_id")}>
        <option value="">Select appointed person</option>{options?.coordinators.map(x=><option key={x.id} value={x.id}>{x.full_name} · {x.role}</option>)}
      </select></label>
      <label>Aircraft or equipment type<select value={form.asset_kind} onChange={field("asset_kind")}>
        {["AIRCRAFT","ENGINE","COMPONENT","PROPELLER","APU","SERVICE"].map(x=><option key={x}>{x}</option>)}</select></label>
      <label>Registration<input value={form.registration} onChange={field("registration")}/></label>
      <label>Part number<input value={form.part_number} onChange={field("part_number")}/></label>
      <label>Serial number<input value={form.serial_number} onChange={field("serial_number")}/></label>
      <label>Article or service description<input value={form.asset_description} onChange={field("asset_description")}/></label>
      <label>Defect / reason for contracted maintenance<textarea required minLength={8} value={form.defect} onChange={field("defect")}/></label>
      <label>Authorized scope<textarea required minLength={12} value={form.scope_text} onChange={field("scope_text")}/></label>
      <label>Approved maintenance-data reference<input required value={form.data_reference} onChange={field("data_reference")}/></label>
      <label>Exact technical-data revision<input required value={form.data_revision} onChange={field("data_revision")}/></label>
      <label>Controlled DMS technical-data document ID (for assigned supplier download)<input value={form.data_manual_id} onChange={field("data_manual_id")}/></label>
      <label>Exact currently published DMS revision ID<input value={form.data_revision_id} onChange={field("data_revision_id")}/></label>
      <label>Governed MOPM 2.20 repair-order reference (where no internal work_orders record exists)<input value={form.governed_repair_order_reference} onChange={field("governed_repair_order_reference")}/></label>
      <label>Required inspections/tests/hold points, one per line<textarea required value={form.inspections} onChange={field("inspections")}/></label>
      <label>Required release/certification and approval reference<input required value={form.required_release} onChange={field("required_release")}/></label>
      <label>Related approved commercial PO ID (optional; not technical authorization)<input type="number" min={1} value={form.purchase_order_id} onChange={field("purchase_order_id")}/></label>
      <label><input type="checkbox" checked={foreign} onChange={e=>setForeign(e.target.checked)}/> Foreign/State-of-Registry requirements apply</label>
      {foreign&&<>
        <label>State of Registry<input required value={form.state_of_registry} onChange={field("state_of_registry")}/></label>
        <label>Foreign approval/acceptance reference<input required value={form.foreign_approval_reference} onChange={field("foreign_approval_reference")}/></label>
        <label>Operator-specific procedures<input required value={form.operator_requirements} onChange={field("operator_requirements")}/></label>
        <label>Required foreign release wording<input required value={form.release_wording} onChange={field("release_wording")}/></label>
      </>}
      <label><input type="checkbox" checked={authorityRequired} onChange={e=>setAuthorityRequired(e.target.checked)}/> Competent Authority acceptance/approval required</label>
      {authorityRequired&&<label>Authority approval/acceptance<input required value={form.authority_acceptance_reference} onChange={field("authority_acceptance_reference")}/></label>}
      <label><input type="checkbox" checked={safetyRequired} onChange={e=>setSafetyRequired(e.target.checked)}/> Safety assessment required</label>
      {safetyRequired&&<label>Safety assessment reference<input required value={form.safety_assessment_reference} onChange={field("safety_assessment_reference")}/></label>}
      <label>Restriction review reference (if scope limitations apply)<input value={form.restriction_review_reference} onChange={field("restriction_review_reference")}/></label>
      <button disabled={busy||!supplier||!form.scope_id||!form.contract_id}>{busy?"Saving…":"Save draft technical order"}</button>
    </form>}
    <div style={{display:"grid",gridTemplateColumns:"minmax(240px,0.32fr) minmax(0,1fr)",gap:"1rem"}}>
      <section><h2>Work queue ({items.length})</h2>
        {!items.length&&!loading&&<p>No contracted maintenance jobs created.</p>}
        {items.map(x=><button type="button" key={x.id} onClick={()=>{setSelected(x.id);setTab("scope");setNotice("");}}
          aria-pressed={selected===x.id} style={{display:"block",width:"100%",textAlign:"left",padding:12,marginBlock:6}}>
          <strong>{x.work_number}</strong><div>{x.work_title}</div><small>{x.status} · {x.site_code}</small>
        </button>)}
      </section>
      <section>{!work?<p>Select a work order to inspect its controls.</p>:<>
        <header><h2>{work.work_number} · {work.work_title}</h2><p>{work.status} · Version {work.version}</p></header>
        <nav aria-label="Contracted maintenance workspaces" style={{display:"flex",flexWrap:"wrap",gap:8}}>
          {(["scope","communications","additional","custody","evidence","history"] as const).map(x=><button key={x} type="button" aria-pressed={tab===x} onClick={()=>setTab(x)}>{x.toUpperCase()}</button>)}
        </nav>
        {tab==="scope"&&<div>
          <h3>Controlled scope and authorization</h3><p>{work.scope_text}</p>
          <dl><dt>Maintenance function</dt><dd>{work.function}</dd><dt>Defect</dt><dd>{work.defect}</dd>
          <dt>Technical data</dt><dd>{work.data_reference} · {work.data_revision}</dd>
          <dt>Release requirement</dt><dd>{work.required_release}</dd>
          <dt>Internal work package</dt><dd>{work.internal_work_reference}</dd>
          <dt>Written agreement</dt><dd>{work.contract_id}</dd><dt>Approved site</dt><dd>{work.site_code}</dd>
          <dt>Related commercial PO</dt><dd>{work.purchase_order_id||"Not linked"}</dd></dl>
          <h4>Inspections / tests / hold points</h4><ul>{work.inspections_json.map((x,i)=><li key={i}>{x}</li>)}</ul>
          <h4>Operator and foreign authority conditions</h4><pre style={{whiteSpace:"pre-wrap"}}>{JSON.stringify(work.requirements_json,null,2)}</pre>
          <form className="partner-form" onSubmit={e=>{e.preventDefault();if(!decision)return;
            void mutate("/"+encodeURIComponent(work.id)+"/transitions",
              {action:decision,expected_version:work.version,reason,idempotency_key:key(),details:{}},
              "Authorized staff decision recorded. No maintenance release or Procurement payment was generated.");}}>
            <h4>Governed role-specific transition</h4>
            <label>Action<select required value={decision} onChange={e=>setDecision(e.target.value)}>
              <option value="">Select an authorized decision</option>
              {detail?.allowed_actions.map(x=><option key={x} value={x}>{x.replaceAll("_"," ")}</option>)}
            </select></label>
            <label>Written technical basis / reason<textarea required minLength={8} value={reason} onChange={e=>setReason(e.target.value)}/></label>
            <button disabled={busy||!decision||reason.trim().length<8}>Record governed transition</button>
          </form>
        </div>}
        {tab==="communications"&&<div><h3>Technical communications</h3><p>Contractor technical questions, findings, ETA changes, progress, return and protective actions are recorded in the immutable timeline. An additional-work request cannot authorize itself.</p>
          {detail?.history.filter(x=>["PROGRESS","FINDING","DISCREPANCY","ETA_CHANGE","TECHNICAL_QUERY","RETURN_SHIPMENT","PROTECTIVE_ACTION"].includes(x.action)).map(x=><p key={x.id}>{x.action} · {x.reason}</p>)}
        </div>}
        {tab==="additional"&&<div><h3>Additional work requests</h3>
          {!detail?.additional_work.length&&<p>No scope extensions requested.</p>}
          {detail?.additional_work.map(x=><div key={x.id}><p>{x.state} · {x.description}</p>
            {x.commercial_reference&&<small>Supplier revised quotation: {x.commercial_reference}</small>}
            {x.state==="REQUESTED"&&<button onClick={()=>setVariationId(x.id)}>Review technical variation</button>}
            {x.decision_reason&&<p>Decision: {x.decision_reason}</p>}
          </div>)}
          {variationId&&<form className="partner-form" onSubmit={e=>{e.preventDefault();void mutate(
            "/"+encodeURIComponent(work.id)+"/additional-work/"+encodeURIComponent(variationId)+"/decision",
            {decision:variationDecision,reason,technical_data:variationData||null,
              amended_work_reference:amendment||null,commercial_variation_reference:variationCommercial||null},
            "Responsible Maintenance Manager decision preserved. Commercial changes do not replace technical scope authorization.");}}>
            <label>Decision<select value={variationDecision} onChange={e=>setVariationDecision(e.target.value)}><option>APPROVED</option><option>REJECTED</option></select></label>
            {variationDecision==="APPROVED"&&<>
              <label>Amended work authorization reference<input required value={amendment} onChange={e=>setAmendment(e.target.value)}/></label>
              <label>Approved maintenance-data reference<input required value={variationData} onChange={e=>setVariationData(e.target.value)}/></label>
              <label>Separate commercial variation reference<input value={variationCommercial} onChange={e=>setVariationCommercial(e.target.value)}/></label>
            </>}
            <label>Attributable decision basis<textarea required minLength={12} value={reason} onChange={e=>setReason(e.target.value)}/></label>
            <button disabled={busy||reason.trim().length<12}>Record Maintenance Manager decision</button></form>}
        </div>}
        {tab==="custody"&&<div><h3>Safarilink property / tools / components</h3>
          {!detail?.custody.length&&<p>No company property registered for this work order.</p>}
          <table><thead><tr><th>Item</th><th>Reference</th><th>Qty</th><th>Custody</th><th>Action</th></tr></thead>
            <tbody>{detail?.custody.map(x=><tr key={x.id}><td>{x.item_type} · {x.description}</td><td>{x.stores_reference} / {x.serial_batch||"—"}</td><td>{x.quantity} {x.uom}</td><td>{x.state}</td>
              <td><button onClick={()=>setCustodyItem(x.id)}>Update custody</button></td></tr>)}</tbody></table>
          <form className="partner-form" onSubmit={e=>{e.preventDefault();void mutate("/"+encodeURIComponent(work.id)+"/custody",
            {item_type:custodyType,description:custodyDescription,part_number:custodyPart||null,
              serial_batch:custodySerial||null,quantity:Number(custodyQty),uom:custodyUom,stores_reference:storesRef},
            "Stores property record created. Canonical stock release remains a separate controlled action.");}}>
            <h4>Register company property for contractor</h4>
            <label>Category<select value={custodyType} onChange={e=>setCustodyType(e.target.value)}>{CUSTODY.map(x=><option key={x}>{x}</option>)}</select></label>
            <label>Description<input required value={custodyDescription} onChange={e=>setCustodyDescription(e.target.value)}/></label>
            <label>Part number<input value={custodyPart} onChange={e=>setCustodyPart(e.target.value)}/></label>
            <label>Serial/lot/batch<input value={custodySerial} onChange={e=>setCustodySerial(e.target.value)}/></label>
            <label>Quantity<input required type="number" min=".001" step=".001" value={custodyQty} onChange={e=>setCustodyQty(e.target.value)}/></label>
            <label>Unit<input required value={custodyUom} onChange={e=>setCustodyUom(e.target.value)}/></label>
            <label>Stores issue/custody reference<input required value={storesRef} onChange={e=>setStoresRef(e.target.value)}/></label>
            <button disabled={busy}>Register controlled custody item</button>
          </form>
          {custodyItem&&<form className="partner-form" onSubmit={e=>{e.preventDefault();void mutate(
            "/"+encodeURIComponent(work.id)+"/custody/"+encodeURIComponent(custodyItem),
            {state:custodyState,reason:custodyReason},
            "Stores-controlled custody change recorded. Physical receipt and serviceability remain subject to canonical Stores procedures.");}}>
            <label>Custody disposition<select required value={custodyState} onChange={e=>setCustodyState(e.target.value)}>
              <option value="">Select allowed status</option>
              {["DISPATCHED","RECEIVED_BY_PROVIDER","CONSUMED","RETURNED","DISCREPANCY","RECONCILED"].map(x=><option key={x}>{x}</option>)}
            </select></label>
            <label>Reason/custody handoff reference<textarea required minLength={8} value={custodyReason} onChange={e=>setCustodyReason(e.target.value)}/></label>
            <button disabled={busy||!custodyState}>Record Stores action</button></form>}
        </div>}
        {tab==="evidence"&&<div><h3>Approved controlled maintenance evidence</h3>
          {!detail?.evidence.length&&<p>No work evidence linked. Provider uploads remain pending until DMS and Quality independently accept them.</p>}
          {detail?.evidence.map(x=><p key={x.id}>{x.category} · {x.filename} · {x.status} / {x.retention_status}</p>)}
          <form className="partner-form" onSubmit={e=>{e.preventDefault();void mutate(
            "/"+encodeURIComponent(work.id)+"/evidence",{source_submission_id:evidenceId,category:evidenceCategory},
            "DMS-retained controlled original linked. Contractor certification and Safarilink technical acceptance remain separate.");}}>
            <label>Submitted work document<select required value={evidenceId} onChange={e=>setEvidenceId(e.target.value)}>
              <option value="">Choose work-scoped uploaded original</option>
              {candidates.map(x=><option key={x.id} value={x.id}>{x.filename} · {x.evidence_type} · {x.status}</option>)}</select></label>
            <label>Technical evidence class<select value={evidenceCategory} onChange={e=>setEvidenceCategory(e.target.value)}>{EVIDENCE.map(x=><option key={x}>{x}</option>)}</select></label>
            <button disabled={busy||!evidenceId}>Link accepted governed original</button></form>
          <p>Closure must account for maintenance releases, inspected records, component movements, Safety reporting and all contractor-owned obligations.</p>
          <h4>Open closure blockers</h4>{detail?.closure_blockers.length?<ul>{detail.closure_blockers.map((x,i)=><li key={i}>{x}</li>)}</ul>:<p>No remaining detected record reconciliation blockers.</p>}
        </div>}
        {tab==="history"&&<div><h3>Attributable work history</h3>
          {!detail?.history.length&&<p>No history yet.</p>}
          {detail?.history.map(x=><p key={x.id}>{new Date(x.created_at).toLocaleString()} · {x.action} · {x.from_state||"—"} → {x.to_state||"—"} · {x.reason}</p>)}
          <h4>Assign provider member to this specific work</h4>
          <form className="partner-form" onSubmit={e=>{e.preventDefault();void mutate(
            "/"+encodeURIComponent(work.id)+"/grant/"+encodeURIComponent(grantId),{},
            "Current provider member granted only this contracted work scope.");}}>
            <select required value={grantId} onChange={e=>setGrantId(e.target.value)}>
              <option value="">Select existing authorized provider member</option>
              {grants.map(x=><option key={x.id} value={x.id}>{x.email} · {x.role_code}</option>)}
            </select><button disabled={busy||!grantId}>Assign controlled job</button>
          </form>
        </div>}
      </>}</section>
    </div>
  </main>;
}
