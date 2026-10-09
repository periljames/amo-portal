import React, { useCallback, useEffect, useState } from "react";
import { apiRequest } from "../../services/apiClient";
import { getCachedUser } from "../../services/auth";

type Kind = "roles" | "sites" | "contacts" | "capabilities" | "certificates" |
  "relationships" | "account-links" | "scope-links" | "source-links";
type RecordRow = { id: string; version: number; [key: string]: unknown };
const FIELDS: Record<Kind, {key: string; label: string; required?: boolean}[]> = {
  roles: [{key:"role_code",label:"Role",required:true},{key:"notes",label:"Notes"}],
  sites: [{key:"site_code",label:"Site code",required:true},{key:"site_name",label:"Site name",required:true},
          {key:"country",label:"Country"},{key:"address",label:"Address"}],
  contacts: [{key:"contact_name",label:"Name",required:true},{key:"assignment",label:"Assignment",required:true},
             {key:"email",label:"Email"},{key:"phone",label:"Phone"},{key:"site_id",label:"Site ID"}],
  capabilities: [{key:"capability_type",label:"Type",required:true},{key:"description",label:"Description",required:true},
                 {key:"site_id",label:"Site ID"},{key:"rating",label:"Rating"},
                 {key:"aircraft_type",label:"Aircraft type"},{key:"engine_type",label:"Engine type"},
                 {key:"component_part_number",label:"Component part number"},
                 {key:"service_code",label:"Service code"},
                 {key:"limitations",label:"Limitations"},{key:"regulatory_authority",label:"Authority"},
                 {key:"certificate_number",label:"Certificate number"},{key:"valid_until",label:"Valid until (YYYY-MM-DD)"}],
  certificates:[{key:"certificate_type",label:"Certificate type",required:true},
                {key:"certificate_number",label:"Approval number",required:true},
                {key:"issuing_authority",label:"Authority"},{key:"jurisdiction",label:"Jurisdiction"},
                {key:"approval_rating",label:"Ratings"},{key:"limitations",label:"Limitations"},
                {key:"valid_from",label:"Valid from"},{key:"valid_until",label:"Valid until"},
                {key:"evidence_id",label:"Governed evidence ID"}],
  relationships:[{key:"parent_supplier_id",label:"Parent supplier ID",required:true},
                 {key:"relationship_kind",label:"Relationship",required:true},
                 {key:"contract_id",label:"Parent contract ID"},
                 {key:"function_scope",label:"Contracted function",required:true},
                 {key:"consent_evidence_id",label:"Written consent evidence ID"},
                 {key:"consent_expires_on",label:"Consent expires"}],
  "account-links":[{key:"user_id",label:"Tenant user ID",required:true},
                   {key:"contact_id",label:"Provider contact ID"},
                   {key:"requested_scopes",label:"Requested scope codes (comma separated)"}],
  "scope-links":[{key:"approval_scope_id",label:"Quality approval scope ID",required:true},
                 {key:"site_id",label:"Site ID"},
                 {key:"contracted_function",label:"Contracted function"},
                 {key:"service_category",label:"Service category"},
                 {key:"product_family",label:"Product family"}],
  "source-links":[{key:"source_system",label:"Source"},{key:"source_identifier",label:"Source identifier"},
                  {key:"source_row",label:"Source row"},{key:"source_digest",label:"File digest"}],
};
const roleValues = ["SUPPLIER","VENDOR","CONTRACTOR","SUBCONTRACTOR","SERVICE_PROVIDER",
                    "LABORATORY","CALIBRATION_PROVIDER","CONSULTANT","OTHER"];
const assignmentValues = ["COMMERCIAL","TECHNICAL","QUALITY","OTHER"];
export default function ProviderIdentityPanel({amoCode,supplierId,onClose}:{
  amoCode:string; supplierId:number; onClose:()=>void;
}) {
  const [kind,setKind]=useState<Kind>("roles");
  const isQuality=getCachedUser()?.role==="QUALITY_MANAGER";
  const canWrite=kind!=="source-links" && (!["relationships","account-links","scope-links"].includes(kind)||isQuality);
  const [governanceReason,setGovernanceReason]=useState("");
  const [rows,setRows]=useState<RecordRow[]>([]);
  const [form,setForm]=useState<Record<string,string>>({});
  const [editing,setEditing]=useState<RecordRow|null>(null);
  const [error,setError]=useState("");
  const [busy,setBusy]=useState(false);
  const [loading,setLoading]=useState(true);
  const endpoint = `/api/maintenance/${encodeURIComponent(amoCode)}/procurement/suppliers/${supplierId}/identity/${kind}`;
  const load=useCallback(async()=> {
    setLoading(true);setError("");
    try {setRows(await apiRequest<RecordRow[]>(endpoint,{cacheTtlMs:0}));}
    catch(e){setError(e instanceof Error?e.message:"Could not load provider details.");}
    finally{setLoading(false);}
  },[endpoint]);
  useEffect(()=>{void load();},[load]);
  function switchKind(next:Kind){setKind(next);setEditing(null);setForm({});}
  function edit(row:RecordRow){
    setEditing(row);
    setForm(Object.fromEntries(FIELDS[kind].map(({key})=>[key,String(row[key]??"")])));
  }
  async function submit(event:React.FormEvent<HTMLFormElement>){
    event.preventDefault();setBusy(true);setError("");
    const fields:Record<string,unknown>=Object.fromEntries(Object.entries(form).filter(([,value])=>value.trim()!==""));
    if(typeof fields.parent_supplier_id==="string")fields.parent_supplier_id=Number(fields.parent_supplier_id);
    if(typeof fields.approval_scope_id==="string")fields.approval_scope_id=Number(fields.approval_scope_id);
    if(typeof fields.requested_scopes==="string")fields.requested_scopes=fields.requested_scopes.split(",").map(v=>v.trim()).filter(Boolean);
    if(typeof fields.is_primary==="string")fields.is_primary=fields.is_primary==="true";
    try{
      await apiRequest(editing?`${endpoint}/${encodeURIComponent(editing.id)}`:endpoint,{
        method:editing?"PATCH":"POST",
        headers:{"Content-Type":"application/json"},
        body:JSON.stringify({fields,expected_version:editing?.version}),
      });
      setEditing(null);setForm({});await load();
    }catch(e){setError(e instanceof Error?e.message:"The provider record could not be saved.");}
    finally{setBusy(false);}
  }
  async function decide(row:RecordRow,action:string) {
    if(governanceReason.trim().length<8){setError("Explain the Quality decision (minimum 8 characters).");return;}
    setBusy(true);setError("");
    try{
      await apiRequest(endpoint+"/"+encodeURIComponent(row.id)+"/governance",{
        method:"POST",headers:{"Content-Type":"application/json"},
        body:JSON.stringify({action,reason:governanceReason,expected_version:row.version}),
      });
      setGovernanceReason("");await load();
    }catch(e){setError(e instanceof Error?e.message:"Quality decision failed.");}
    finally{setBusy(false);}
  }
  return <section className="proc-panel" aria-label="Provider identity administration">
    <header className="proc-section-heading proc-section-heading--split"><div><h2>Provider organization profile</h2>
      <p>Descriptive roles, locations, people and capabilities. Quality approval remains separately controlled.</p></div>
      <button type="button" className="proc-button" onClick={onClose}>Close</button></header>
    <div className="proc-toolbar">{(Object.keys(FIELDS) as Kind[]).map(item=>
      <button key={item} type="button" className="proc-button" aria-pressed={kind===item}
        onClick={()=>switchKind(item)}>{item}</button>)}</div>
    {error&&<p role="alert">{error}</p>}
    {loading?<p>Loading provider details…</p>:
      rows.length?<div className="proc-table-wrap"><table className="proc-table"><thead>
       <tr><th>Record</th><th>Details</th><th>Version</th><th>Action</th></tr></thead><tbody>
       {rows.map(row=><tr key={row.id}>
         <td>{String(row.role_code??row.site_name??row.contact_name??row.description??row.certificate_number??row.relationship_kind??row.user_id??row.source_identifier??row.id)}</td>
         <td>{FIELDS[kind].map(({key})=>row[key]? `${key}: ${String(row[key])}`:"").concat(String(row.verification_state??row.consent_state??row.account_state??"")).filter(Boolean).join(" · ")}</td>
         <td>{row.version}</td><td>{canWrite&&<button type="button" disabled={busy} onClick={()=>edit(row)}>Edit</button>}
         {isQuality&&["certificates","relationships","account-links"].includes(kind)&&<>
          <button type="button" disabled={busy||governanceReason.trim().length<8} onClick={()=>void decide(row,"VERIFY")}>Verify</button>
          <button type="button" disabled={busy||governanceReason.trim().length<8} onClick={()=>void decide(row,kind==="certificates"?"REJECT":"REVOKE")}>{kind==="certificates"?"Reject":"Revoke"}</button>
         </>}</td>
       </tr>)}</tbody></table></div>:<p>No {kind} recorded.</p>}
    {isQuality&&["certificates","relationships","account-links"].includes(kind)&&<label>Quality decision reason
      <textarea rows={2} value={governanceReason} onChange={e=>setGovernanceReason(e.target.value)} />
    </label>}
    {canWrite&&<form onSubmit={e=>void submit(e)}><h3>{editing?"Edit":"Add"} {kind.slice(0,-1)}</h3>
     {FIELDS[kind].map(field=><label key={field.key} style={{display:"block",margin:"0.5rem 0"}}>
       {field.label}
       {field.key==="role_code"||field.key==="assignment"
         ?<select required={field.required} value={form[field.key]??""}
           onChange={e=>setForm(old=>({...old,[field.key]:e.target.value}))}>
           <option value="">Select</option>{(field.key==="role_code"?roleValues:assignmentValues).map(v=>
           <option key={v} value={v}>{v.replaceAll("_"," ")}</option>)}</select>
         :<input required={field.required} type={["valid_until","valid_from","consent_expires_on"].includes(field.key)?"date":"text"}
           value={form[field.key]??""} onChange={e=>setForm(old=>({...old,[field.key]:e.target.value}))}/>}
      </label>)}
      <button type="submit" className="proc-button proc-button--primary" disabled={busy}>{busy?"Saving…":"Save record"}</button>
      {editing&&<button type="button" className="proc-button" onClick={()=>{setEditing(null);setForm({});}}>Cancel edit</button>}
    </form>}
  </section>;
}
