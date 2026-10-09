import React, { useState } from "react";
import { apiRequest } from "../../services/apiClient";

type ImportRow = {
  id: string;
  sheet_name: string;
  row_number: number;
  normalized_json: Record<string, string | null> | string;
  diagnostics_json: string[] | string;
  status: string;
  supplier_id: number | null;
};
type ImportDetail = { batch: {id:string;filename:string;status:string}; rows: ImportRow[] };
type Preview = {
  batch_id: string;
  source_sha256: string;
  status: string;
  already_uploaded?: boolean;
  counts?: {total:number;ready:number;errors:number;duplicates:number};
};

function unpack<T,>(value:T|string):T {
  if(typeof value==="string")return JSON.parse(value) as T;
  return value;
}
export default function ProviderImportPanel({amoCode,onImported}:{
  amoCode:string;onImported:()=>Promise<void>;
}) {
  const [file,setFile]=useState<File|null>(null);
  const [mapping,setMapping]=useState("{}");
  const [preview,setPreview]=useState<Preview|null>(null);
  const [detail,setDetail]=useState<ImportDetail|null>(null);
  const [busy,setBusy]=useState(false);
  const [error,setError]=useState("");
  const [message,setMessage]=useState("");
  const base=`/api/maintenance/${encodeURIComponent(amoCode)}/procurement/external-provider-imports`;
  async function getDetail(id:string) {
    const data=await apiRequest<ImportDetail>(`${base}/${encodeURIComponent(id)}`,{cacheTtlMs:0});
    setDetail(data);return data;
  }
  async function upload(event:React.FormEvent<HTMLFormElement>) {
    event.preventDefault();if(!file)return;
    setBusy(true);setError("");setMessage("");
    try {
      const parsed=JSON.parse(mapping) as unknown;
      if(!parsed||typeof parsed!=="object"||Array.isArray(parsed))throw new Error("Mapping must be a JSON object.");
      const data=new FormData();data.append("file",file);data.append("mapping_json",mapping);
      const result=await apiRequest<Preview>(`${base}/preview`,{method:"POST",body:data});
      setPreview(result);await getDetail(result.batch_id);
      if(result.already_uploaded)setMessage("This exact workbook has already been staged. Showing its existing reconciliation.");
    }catch(e){setError(e instanceof Error?e.message:"Could not stage workbook.");}
    finally{setBusy(false);}
  }
  async function confirm() {
    if(!preview)return;
    setBusy(true);setError("");setMessage("");
    try{
      const result=await apiRequest<{created_supplier_ids:number[];operational_eligibility_granted:boolean}>(
        `${base}/${encodeURIComponent(preview.batch_id)}/confirm`,{method:"POST"});
      setMessage(`${result.created_supplier_ids.length} prospective suppliers recorded. Quality approval was not granted.`);
      await getDetail(preview.batch_id);await onImported();
    }catch(e){setError(e instanceof Error?e.message:"Could not confirm reconciliation.");}
    finally{setBusy(false);}
  }
  function download() {
    if(!detail)return;
    const escape=(value:unknown)=>`"${String(value??"").replaceAll('"','""')}"`;
    const header=["sheet","row","supplier_code","legal_name","status","issues","supplier_id"];
    const lines=[header.map(escape).join(","),...detail.rows.map(row=>{
      const fields=unpack<Record<string,string|null>>(row.normalized_json);
      const issues=unpack<string[]>(row.diagnostics_json);
      return [row.sheet_name,row.row_number,fields.supplier_code,fields.legal_name,
        row.status,issues.join("; "),row.supplier_id].map(escape).join(",");
    })];
    const url=URL.createObjectURL(new Blob([lines.join("\r\n")],{type:"text/csv;charset=utf-8"}));
    const anchor=document.createElement("a");anchor.href=url;
    anchor.download=`provider-reconciliation-${detail.batch.id}.csv`;anchor.click();
    URL.revokeObjectURL(url);
  }
  const errors=detail?.rows.filter(row=>row.status==="ERROR")??[];
  return <section className="proc-panel" aria-label="External provider spreadsheet import">
    <header><div><h2>Import vendor and contracts trackers</h2>
      <p>Preview spreadsheet records before adding inactive prospective suppliers.
         Contract and approval columns are not treated as authorizations.</p></div></header>
    <form onSubmit={e=>void upload(e)}>
      <label>Workbook (XLSX or XLSM)
        <input type="file" accept=".xlsx,.xlsm" required onChange={e=>{
          setFile(e.target.files?.[0]??null);setPreview(null);setDetail(null);
        }}/>
      </label>
      <label style={{display:"block",margin:"0.8rem 0"}}>Optional source header mapping (JSON object)
        <textarea rows={2} value={mapping} onChange={e=>setMapping(e.target.value)}
          aria-label="Source column mappings" />
      </label>
      <button type="submit" className="proc-button proc-button--primary" disabled={!file||busy}>
        {busy?"Working…":"Stage and preview"}</button>
    </form>
    {error&&<p role="alert">{error}</p>}
    {message&&<p role="status">{message}</p>}
    {preview&&<p>Import {preview.batch_id}: {preview.status}.
      {preview.counts&&` ${preview.counts.total} rows; ${preview.counts.ready} ready; ${preview.counts.errors} errors.`}</p>}
    {detail&&<>
      <div className="proc-table-wrap"><table className="proc-table"><thead><tr>
        <th>Sheet / row</th><th>Provider</th><th>Status</th><th>Issues</th>
      </tr></thead><tbody>{detail.rows.map(row=>{
        const fields=unpack<Record<string,string|null>>(row.normalized_json);
        const issues=unpack<string[]>(row.diagnostics_json);
        return <tr key={row.id}><td>{row.sheet_name} #{row.row_number}</td>
          <td>{fields.supplier_code||"—"} — {fields.legal_name||"—"}</td>
          <td>{row.status}</td><td>{issues.join(", ")||"—"}</td></tr>;
      })}</tbody></table></div>
      <div className="proc-toolbar">
        <button type="button" className="proc-button" onClick={download}>Export reconciliation CSV</button>
        {detail.batch.status==="STAGED"&&<button type="button"
          className="proc-button proc-button--primary" disabled={busy||errors.length>0||detail.rows.length===0}
          onClick={()=>void confirm()}>Confirm {detail.rows.length} prospective records</button>}
      </div>
      {errors.length>0&&<p role="alert">Resolve {errors.length} row errors in the source workbook and stage the corrected file before confirmation.</p>}
    </>}
  </section>;
}
