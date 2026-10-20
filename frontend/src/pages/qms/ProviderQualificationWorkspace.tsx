import React,{useCallback,useEffect,useState} from "react";
import {apiRequest} from "../../services/apiClient";
import {getCachedUser} from "../../services/auth";
import "./provider-qualification.css";

type Overview={cases:Array<{id:string;category:string;status:string;case_kind:string;version:number}>;
  restrictions:Array<{id:string;status:string;dimension:string;target_key:string;reason:string}>;
  audits:Array<{audit_id:string;audit_ref:string;audit_status:string}>;
  history:Array<{action:string;occurred_at:string;details_json:unknown}>;
  approved_scopes:Array<{id:number;category:string;site_code:string;product_family:string;status:string}>};
type Check={requirement_key:string;status:string;evidence_reference:string|null;approval_reference:string|null};
type QualCase={id:string;status:string;version:number;technical_state:string;safety_state:string;
  authority_state:string;case_kind:string;category:string;checks:Check[];evaluation_id:string|null;
  audit_id:string|null;answers_json:Record<string,string>;technical_scope_json:unknown;
  policy_snapshot_json:{questionnaire:Array<{key:string;label:string;required?:boolean}>;manual_references:string[]}};
type Policy={category:string;revision:number;surveillance_days:number|null;manual_references_json:string[];evaluation_template_id:string|null;questionnaire_json:Array<Record<string,unknown>>;initial_audit_required:boolean;authority_required:boolean;safety_assessment_required:boolean};
type Alerts={overdue_qualification_reviews:Array<{supplier_id:number;id:string;next_review_due_on:string}>;
  overdue_cars:Array<{supplier_id:number;car_number:string;due_date:string}>};
const BASE_CHECKS=["LEGAL_IDENTITY","CLASSIFICATION_AND_APPLICABILITY","SCOPE_CAPABILITY",
  "REGULATORY_APPROVAL","FACILITIES_AND_SITES","CONTRACT_REQUIREMENTS","SAFETY_MOC",
  "QMS_EVALUATION","QUALIFYING_AUDIT_OR_REVIEW","TECHNICAL_ACCEPTANCE","QUALITY_CONCLUSION"];
const DIMENSIONS=["ORGANIZATION","SITE","CATEGORY","CAPABILITY","PRODUCT_FAMILY","FUNCTION","CONTRACT"];
const readable=(value:string)=>value.replaceAll("_"," ");
const messageOf=(error:unknown)=>error instanceof Error?error.message:"Governance request rejected";
export default function ProviderQualificationWorkspace({amoCode,supplierId}:{
  amoCode:string;supplierId:number;
}):React.ReactElement{
  const path="/api/maintenance/"+encodeURIComponent(amoCode)+"/quality/external-qualification";
  const role=String(getCachedUser()?.role||"");
  const manager=role==="QUALITY_MANAGER";
  const preparer=manager||role==="QUALITY_OFFICER";
  const technical=["BASE_MAINTENANCE_MANAGER","LINE_MAINTENANCE_MANAGER","WORKSHOP_MANAGER"].includes(role);
  const safety=role==="SAFETY_MANAGER";
  const [data,setData]=useState<Overview|null>(null);
  const [policies,setPolicies]=useState<Policy[]>([]);
  const [alerts,setAlerts]=useState<Alerts|null>(null);
  const [caseItem,setCase]=useState<QualCase|null>(null);
  const [category,setCategory]=useState("SUBCONTRACTOR");
  const [reason,setReason]=useState("");
  const [reference,setReference]=useState("");
  const [expires,setExpires]=useState("");
  const [evaluation,setEvaluation]=useState("");
  const [audit,setAudit]=useState("");
  const [answers,setAnswers]=useState<Record<string,string>>({});
  const [technicalScope,setTechnicalScope]=useState('[{"category":"SERVICE","site":"PRIMARY","product_family":"ALL"}]');
  const [checkKey,setCheckKey]=useState("");
  const [restrictionDimension,setRestrictionDimension]=useState("ORGANIZATION");
  const [restrictionTarget,setRestrictionTarget]=useState("*");
  const [interval,setInterval]=useState("365");
  const [templateId,setTemplateId]=useState("");
  const [initialAudit,setInitialAudit]=useState(false);
  const [authorityRequired,setAuthorityRequired]=useState(false);
  const [safetyRequired,setSafetyRequired]=useState(false);
  const [policyQuestions,setPolicyQuestions]=useState('[{"key":"REGULATORY_BASIS","label":"Regulatory applicability basis","kind":"TEXT","required":true}]');
  const [manuals,setManuals]=useState("");
  const [tab,setTab]=useState("qualification");
  const [error,setError]=useState("");
  const [notice,setNotice]=useState("");
  const [busy,setBusy]=useState(false);
  const refresh=useCallback(async()=>{
    const [overview,policy,alertData]=await Promise.all([
      apiRequest<Overview>(path+"/providers/"+supplierId+"/overview",{cacheTtlMs:0}),
      apiRequest<{items:Policy[]}>(path+"/policies",{cacheTtlMs:0}),
      apiRequest<Alerts>(path+"/alerts",{cacheTtlMs:0}),
    ]);
    setData(overview);setPolicies(policy.items);setAlerts(alertData);
    setCategory(current=>policy.items.some(p=>p.category===current)
      ? current : (policy.items[0]?.category||current));
  },[path,supplierId]);
  useEffect(()=>{void refresh().catch(x=>setError(messageOf(x)));},[refresh]);
  useEffect(()=>{
    const policy=policies.find(p=>p.category===category);
    if(!policy)return;
    setTemplateId(policy.evaluation_template_id||"");
    setInterval(policy.surveillance_days?String(policy.surveillance_days):"");
    setInitialAudit(Boolean(policy.initial_audit_required));
    setAuthorityRequired(Boolean(policy.authority_required));
    setSafetyRequired(Boolean(policy.safety_assessment_required));
    setPolicyQuestions(JSON.stringify(policy.questionnaire_json||[],null,2));
    setManuals((policy.manual_references_json||[]).join("; "));
  },[category,policies]);
  const open=async(id:string)=>{
    try{
      const value=await apiRequest<QualCase>(path+"/cases/"+encodeURIComponent(id),{cacheTtlMs:0});
      setCase(value);setAnswers(value.answers_json||{});setEvaluation(value.evaluation_id||"");
      setCheckKey(value.checks[0]?.requirement_key||"");
      setTechnicalScope(JSON.stringify(value.technical_scope_json||[],null,2));
    }catch(x){setError(messageOf(x));}
  };
  const change=async(url:string,body:unknown,method:"POST"|"PATCH"|"PUT"="POST")=>{
    setBusy(true);setError("");setNotice("");
    try{
      const result=await apiRequest<{id?:string}>(path+url,{
        method,body:JSON.stringify(body),headers:{"Content-Type":"application/json"},
      });
      setNotice("Governed decision saved. Regulatory and canonical QMS approvals remain independent.");
      await refresh();
      if(result.id&&url==="/cases")await open(result.id);
      else if(caseItem)await open(caseItem.id);
    }catch(x){setError(messageOf(x));}
    finally{setBusy(false);}
  };
  const note=reason.trim();
  return <div className="qp-workspace">
    <h3>Qualification and surveillance</h3>
    <p>Approval, audit and corrective-action records remain in their existing QMS and Procurement systems.</p>
    <nav className="qp-tabs">{["qualification","surveillance","restrictions","history","policy"].map(t=>
      <button key={t} type="button" aria-pressed={tab===t} onClick={()=>setTab(t)}>{readable(t)}</button>)}</nav>
    {error&&<p className="qp-error" role="alert">{error}</p>}
    {notice&&<p className="qp-success" role="status">{notice}</p>}
    {tab==="qualification"&&<section className="qp-panel">
      <h4>Qualification queue and requalification</h4>
      <div className="qp-table"><table><thead><tr><th>Category</th><th>Type</th><th>Status</th><th>Case</th></tr></thead>
        <tbody>{data?.cases.map(c=><tr key={c.id}><td>{c.category}</td><td>{c.case_kind}</td>
          <td>{c.status}</td><td><button onClick={()=>void open(c.id)}>Open {c.id.slice(0,8)}</button></td></tr>)}</tbody></table></div>
      {preparer&&<div className="qp-fields">
        <label>Qualification category<select value={category} onChange={e=>setCategory(e.target.value)}>
          {policies.map(p=><option key={p.category} value={p.category}>{p.category}</option>)}
          {!policies.length&&<option value="SUBCONTRACTOR">Configure policy first</option>}
        </select></label>
        <label>Reason<input value={reason} onChange={e=>setReason(e.target.value)}/></label>
        <div className="qp-actions">{["INITIAL","RENEWAL","REQUALIFICATION","REINSTATEMENT"].map(kind=>
          <button key={kind} disabled={busy||note.length<8||!policies.some(p=>p.category===category)}
            onClick={()=>void change("/cases",{supplier_id:supplierId,category,case_kind:kind,
              risk_level:"MEDIUM",reason:note})}>{readable(kind)}</button>)}</div>
      </div>}
      {caseItem&&<article className="qp-panel"><h4>Case: {caseItem.id.slice(0,8)} — {caseItem.status}</h4>
        <p>Version {caseItem.version} · Technical {caseItem.technical_state} · Safety {caseItem.safety_state} · Authority {caseItem.authority_state}</p>
        <p>Current evaluation: {caseItem.evaluation_id||"Unlinked"} · Audit: {caseItem.audit_id||"Unlinked"}</p>
        <h4>Questionnaire</h4>
        {caseItem.policy_snapshot_json.questionnaire.map(q=><label key={q.key}>{q.label||q.key}
          <input disabled={!preparer} value={answers[q.key]||""}
            onChange={e=>setAnswers(old=>({...old,[q.key]:e.target.value}))}/></label>)}
        {preparer&&<>
          <label>Existing independent evaluation identifier<input value={evaluation} onChange={e=>setEvaluation(e.target.value)}/></label>
          <button disabled={busy||note.length<8} onClick={()=>void change("/cases/"+caseItem.id,
            {expected_version:caseItem.version,answers,evaluation_id:evaluation||null,conclusion:note},"PATCH")}>
            Save qualification assessment</button>
        </>}
        <h4>Required control checks</h4>
        <div className="qp-table"><table><thead><tr><th>Requirement</th><th>Decision</th><th>Reference</th></tr></thead>
          <tbody>{caseItem.checks.map(c=><tr key={c.requirement_key}><td>{readable(c.requirement_key)}</td>
            <td>{c.status}</td><td>{c.evidence_reference||c.approval_reference||"Pending"}</td></tr>)}</tbody></table></div>
        {preparer&&<div className="qp-fields"><label>Review check<select value={checkKey} onChange={e=>setCheckKey(e.target.value)}>
          {caseItem.checks.map(c=><option key={c.requirement_key}>{c.requirement_key}</option>)}</select></label>
          <label>Verified evidence/approval reference<input value={reference} onChange={e=>setReference(e.target.value)}/></label>
          <label>Expiry<input type="date" value={expires} onChange={e=>setExpires(e.target.value)}/></label>
          <button disabled={busy||!reference||note.length<8||!checkKey}
            onClick={()=>void change("/cases/"+caseItem.id+"/checks/"+checkKey,
              {status:"VERIFIED",evidence_reference:reference,approval_reference:reference,
                expires_on:expires||null,conclusion:note})}>Record verification</button></div>}
        {(technical||safety||manager)&&<div className="qp-fields">
          {technical&&<><label>Exact technical scope JSON<textarea rows={3} value={technicalScope}
            onChange={e=>setTechnicalScope(e.target.value)}/></label>
            <button disabled={busy||note.length<8} onClick={()=>{
              try{const values=JSON.parse(technicalScope) as unknown;
                if(!Array.isArray(values))throw Error("Scope must be an array");
                void change("/cases/"+caseItem.id+"/review/technical",
                  {state:"ACCEPTED",reason:note,technical_scope:values});}
              catch{setError("Enter a JSON array of approved scope items");}
            }}>Maintenance Manager: approve technical scope</button></>}
          {safety&&["ACCEPTED","NOT_REQUIRED","REJECTED"].map(state=>
            <button key={state} disabled={busy||note.length<8} onClick={()=>void change(
              "/cases/"+caseItem.id+"/review/safety",{state,reason:note,reference:reference||null})}>Safety {state}</button>)}
          {manager&&["VERIFIED","NOT_REQUIRED","REJECTED"].map(state=>
            <button key={state} disabled={busy||note.length<8} onClick={()=>void change(
              "/cases/"+caseItem.id+"/review/authority",
              {state,reason:note,reference:reference||null,expires_on:expires||null})}>Authority {state}</button>)}
        </div>}
        {preparer&&<div className="qp-fields"><label>Existing external QMS audit UUID
          <input value={audit} onChange={e=>setAudit(e.target.value)}/></label>
          <button disabled={busy||note.length<8||!audit} onClick={()=>void change(
            "/cases/"+caseItem.id+"/audit",{audit_id:audit,kind:"INITIAL",reason:note})}>Link QMS audit occurrence</button>
          <p>Use Live Audit for independence, notice issuance, auditee acknowledgment, fieldwork, findings, CAR and effectiveness.</p></div>}
        {manager&&<div className="qp-actions">{["APPROVE","CONDITIONALLY_APPROVE","REJECT","RETURN"].map(action=>
          <button key={action} disabled={busy||note.length<12} onClick={()=>void change(
            "/cases/"+caseItem.id+"/decision",{action,expected_version:caseItem.version,reason:note})}>
            {readable(action)}</button>)}</div>}
      </article>}
    </section>}
    {tab==="surveillance"&&<section className="qp-panel"><h4>Linked QMS audits</h4>
      <h4>Overdue review and corrective-action escalation</h4>
      {alerts?.overdue_qualification_reviews.filter(x=>x.supplier_id===supplierId).map(x=>
        <p key={x.id}>Qualification review overdue since {x.next_review_due_on}</p>)}
      {alerts?.overdue_cars.filter(x=>x.supplier_id===supplierId).map(x=>
        <p key={x.car_number}>CAR {x.car_number} overdue since {x.due_date}</p>)}
      {manager&&<button disabled={busy||note.length<12} onClick={()=>void change(
        "/alerts/escalate",{supplier_id:supplierId,reason:note})}>
        Record Quality escalation and notify provider</button>}
      <p>These are existing audit occurrences, not a second audit engine.</p>
      {data?.audits.map(a=><p key={a.audit_id}>{a.audit_ref} · {a.audit_status} · {a.audit_id}</p>)}
      {!data?.audits.length&&<p>No linked audit occurrences.</p>}</section>}
    {tab==="restrictions"&&<section className="qp-panel"><h4>Scoped restrictions</h4>
      {data?.restrictions.map(r=><div className="qp-record" key={r.id}><strong>{r.dimension} / {r.target_key}</strong>
        <p>{r.status} · {r.reason}</p>{manager&&r.status==="ACTIVE"&&<button disabled={!caseItem||busy||note.length<12}
          onClick={()=>void change("/restrictions/"+r.id+"/lift",
            {reinstatement_case_id:caseItem?.id,reason:note})}>Lift after approved reinstatement</button>}</div>)}
      {manager&&<div className="qp-fields"><label>Restriction dimension<select value={restrictionDimension}
        onChange={e=>{setRestrictionDimension(e.target.value);setRestrictionTarget(e.target.value==="ORGANIZATION"?"*":"");}}>
        {DIMENSIONS.map(x=><option key={x}>{x}</option>)}</select></label>
        <label>Target key<input value={restrictionTarget} onChange={e=>setRestrictionTarget(e.target.value)}/></label>
        <button disabled={busy||note.length<12||!restrictionTarget} onClick={()=>void change(
          "/restrictions",{supplier_id:supplierId,dimension:restrictionDimension,target_key:restrictionTarget,
            effective_on:new Date().toISOString().slice(0,10),reason:note,
            affected_records:[],required_car_ids:[]})}>Impose restriction</button></div>}
    </section>}
    {tab==="history"&&<section className="qp-panel"><h4>Attributable decisions</h4>
      {data?.history.map((item,i)=><p key={i}>{item.action} · {new Date(item.occurred_at).toLocaleString()}</p>)}
      {preparer&&<button disabled={busy} onClick={()=>{
        setBusy(true);setError("");
        void apiRequest<Record<string,unknown>>(path+"/providers/"+supplierId+"/export",{cacheTtlMs:0})
          .then(payload=>{
            const blob=new Blob([JSON.stringify(payload,null,2)],{type:"application/json"});
            const url=URL.createObjectURL(blob);const link=document.createElement("a");
            link.href=url;link.download="provider-"+supplierId+"-regulatory-trace.json";link.click();
            window.setTimeout(()=>URL.revokeObjectURL(url),1000);
          }).catch(e=>setError(messageOf(e))).finally(()=>setBusy(false));
      }}>Export full source-linked regulatory trace</button>}</section>}
    {tab==="policy"&&<section className="qp-panel"><h4>Tenant category policy</h4>
      <p>Safarilink annual audits are not assumed for every tenant; an approved category interval controls scheduling.</p>
      {policies.map(p=><p key={p.category}>{p.category} Rev {p.revision} · Evaluation {p.evaluation_template_id||"Not configured"} · {p.surveillance_days||"Risk-assessed"} days
        · {p.manual_references_json.join("; ")}</p>)}
      {manager&&<div className="qp-fields">
        <label>Category<input value={category} onChange={e=>setCategory(e.target.value.toUpperCase())}/></label>
        <label>Active QMS supplier evaluation template UUID<input value={templateId} onChange={e=>setTemplateId(e.target.value)} placeholder="Use canonical Procurement/QMS evaluation templates"/></label>
        <label>Surveillance days (blank = risk-based)<input type="number" min={30} max={3650} value={interval}
          onChange={e=>setInterval(e.target.value)}/></label>
        <label><input type="checkbox" checked={initialAudit} onChange={e=>setInitialAudit(e.target.checked)}/> Require initial QMS audit (rather than qualifying document review)</label>
        <label><input type="checkbox" checked={authorityRequired} onChange={e=>setAuthorityRequired(e.target.checked)}/> Require verified authority or State-of-Registry approval</label>
        <label><input type="checkbox" checked={safetyRequired} onChange={e=>setSafetyRequired(e.target.checked)}/> Require Safety Manager risk assessment</label>
        <label>Questionnaire JSON<textarea rows={4} value={policyQuestions} onChange={e=>setPolicyQuestions(e.target.value)}/></label>
        <label>Exact manual references (semicolon separated)<textarea value={manuals} onChange={e=>setManuals(e.target.value)}/></label>
        <button disabled={busy||note.length<8} onClick={()=>{
          try{const questions=JSON.parse(policyQuestions) as unknown;
            if(!Array.isArray(questions))throw Error("Array required");
            void change("/policies/"+encodeURIComponent(category),{
              questionnaire:questions,required_checks:BASE_CHECKS,
              surveillance_days:interval?Number(interval):null,
              evaluation_template_id:templateId||null,
              initial_audit_required:initialAudit,authority_required:authorityRequired,
              safety_assessment_required:safetyRequired,
              manual_references:manuals.split(";").map(x=>x.trim()).filter(Boolean),reason:note,
              expected_revision:policies.find(p=>p.category===category)?.revision||0,
            },"PUT");}
          catch{setError("Questionnaire must be an array in JSON");}
        }}>Save Quality-approved policy</button></div>}</section>}
    <label className="qp-rationale">Attributable rationale
      <textarea rows={2} value={reason} onChange={e=>setReason(e.target.value)}
        placeholder="Record evidence, issue, findings, disposition, decision reason"/></label>
    <button type="button" disabled={busy} onClick={()=>void refresh().catch(x=>setError(messageOf(x)))}>Refresh governance</button>
  </div>;
}
