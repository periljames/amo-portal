import React, { useCallback, useEffect, useState } from "react";
import { apiRequest } from "../../services/apiClient";

type Kind = "roles" | "sites" | "contacts" | "capabilities";
type RecordRow = { id: string; version: number; [key: string]: unknown };
const FIELDS: Record<Kind, {key: string; label: string; required?: boolean}[]> = {
  roles: [{key:"role_code",label:"Role",required:true},{key:"notes",label:"Notes"}],
  sites: [{key:"site_code",label:"Site code",required:true},{key:"site_name",label:"Site name",required:true},
          {key:"country",label:"Country"},{key:"address",label:"Address"}],
  contacts: [{key:"contact_name",label:"Name",required:true},{key:"assignment",label:"Assignment",required:true},
             {key:"email",label:"Email"},{key:"phone",label:"Phone"},{key:"site_id",label:"Site ID"}],
  capabilities: [{key:"capability_type",label:"Type",required:true},{key:"description",label:"Description",required:true},
                 {key:"site_id",label:"Site ID"},{key:"rating",label:"Rating"},
                 {key:"limitations",label:"Limitations"},{key:"regulatory_authority",label:"Authority"},
                 {key:"certificate_number",label:"Certificate number"},{key:"valid_until",label:"Valid until (YYYY-MM-DD)"}],
};
const roleValues = ["SUPPLIER","VENDOR","CONTRACTOR","SUBCONTRACTOR","SERVICE_PROVIDER",
                    "LABORATORY","CALIBRATION_PROVIDER","CONSULTANT","OTHER"];
const assignmentValues = ["COMMERCIAL","TECHNICAL","QUALITY","OTHER"];
export default function ProviderIdentityPanel({amoCode,supplierId,onClose}:{
  amoCode:string; supplierId:number; onClose:()=>void;
}) {
  const [kind,setKind]=useState<Kind>("roles");
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
    const fields=Object.fromEntries(Object.entries(form).filter(([,value])=>value.trim()!==""));
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
         <td>{String(row.role_code??row.site_name??row.contact_name??row.description??row.id)}</td>
         <td>{FIELDS[kind].map(({key})=>row[key]? `${key}: ${String(row[key])}`:"").filter(Boolean).join(" · ")}</td>
         <td>{row.version}</td><td><button type="button" disabled={busy} onClick={()=>edit(row)}>Edit</button></td>
       </tr>)}</tbody></table></div>:<p>No {kind} recorded.</p>}
    <form onSubmit={e=>void submit(e)}><h3>{editing?"Edit":"Add"} {kind.slice(0,-1)}</h3>
     {FIELDS[kind].map(field=><label key={field.key} style={{display:"block",margin:"0.5rem 0"}}>
       {field.label}
       {field.key==="role_code"||field.key==="assignment"
         ?<select required={field.required} value={form[field.key]??""}
           onChange={e=>setForm(old=>({...old,[field.key]:e.target.value}))}>
           <option value="">Select</option>{(field.key==="role_code"?roleValues:assignmentValues).map(v=>
           <option key={v} value={v}>{v.replaceAll("_"," ")}</option>)}</select>
         :<input required={field.required} type={field.key==="valid_until"?"date":"text"}
           value={form[field.key]??""} onChange={e=>setForm(old=>({...old,[field.key]:e.target.value}))}/>}
      </label>)}
      <button type="submit" className="proc-button proc-button--primary" disabled={busy}>{busy?"Saving…":"Save record"}</button>
      {editing&&<button type="button" className="proc-button" onClick={()=>{setEditing(null);setForm({});}}>Cancel edit</button>}
    </form>
  </section>;
}
