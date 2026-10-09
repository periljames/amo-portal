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
type ImportDetail = { batch: {id:string;filename:string;status:string;import_kind:string}; rows: ImportRow[] };
type Preview = {
  batch_id: string;
  source_sha256: string;
  status: string;
  import_kind: string;
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
  const [importKind,setImportKind]=useState<"SUPPLIERS"|"CONTRACTS">("SUPPLIERS");
  const [sourceSheet,setSourceSheet]=useState("");
  const [headerRow,setHeaderRow]=useState(1);
  const [reason,setReason]=useState("");
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
      data.append("import_kind",importKind);data.append("source_sheet",sourceSheet);
      data.append("header_row",String(headerRow));
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
      const result=await apiRequest<{created_record_ids:Array<string|number>;operational_eligibility_granted:boolean}>(
        `${base}/${encodeURIComponent(preview.batch_id)}/confirm`,{method:"POST"});
      setMessage(`${result.created_record_ids.length} ${importKind==="CONTRACTS"?"draft contracts":"prospective suppliers"} recorded. Quality approval was not granted.`);
      await getDetail(preview.batch_id);await onImported();
    }catch(e){setError(e instanceof Error?e.message:"Could not confirm reconciliation.");}
    finally{setBusy(false);}
  }
  function download() {
    if(!detail)return;
    const escape=(value:unknown)=>`"${String(value??"").replaceAll('"','""')}"`;
    const header=["sheet","row","supplier_code","supplier_name","contract_number","title","source_status","effective_on","expires_on","status","issues","supplier_id"];
    const lines=[header.map(escape).join(","),...detail.rows.map(row=>{
      const fields=unpack<Record<string,string|null>>(row.normalized_json);
      const issues=unpack<string[]>(row.diagnostics_json);
      return [row.sheet_name,row.row_number,fields.supplier_code,fields.legal_name||fields.supplier_name,
        fields.contract_number,fields.title,fields.source_status,fields.effective_on,fields.expires_on,
        row.status,issues.join("; "),row.supplier_id].map(escape).join(",");
    })];
    const url=URL.createObjectURL(new Blob([lines.join("\r\n")],{type:"text/csv;charset=utf-8"}));
    const anchor=document.createElement("a");anchor.href=url;
    anchor.download=`provider-reconciliation-${detail.batch.id}.csv`;anchor.click();
    URL.revokeObjectURL(url);
  }
  async function changeBatch(action: "rollback" | "supersede") {
    if(!detail||reason.trim().length<8){
      setError("Provide a documented reason of at least 8 characters.");
      return;
    }
    setBusy(true);setError("");setMessage("");
    try{
      const form=new FormData();form.append("reason",reason);
      await apiRequest(base+"/"+encodeURIComponent(detail.batch.id)+"/"+action,{method:"POST",body:form});
      await getDetail(detail.batch.id);
      await onImported();
      setMessage("Reconciliation "+action+" recorded.");
      setReason("");
    }catch(e){setError(e instanceof Error?e.message:"Reconciliation action failed.");}
    finally{setBusy(false);}
  }
  const errors=detail?.rows.filter(row=>row.status==="ERROR")??[];
  return <section className="proc-panel" aria-label="External provider spreadsheet import">
    <header><div><h2>Import vendor and contracts trackers</h2>
      <p>Stage prospective suppliers or draft contracts.
         Contract and approval columns are not treated as authorizations.</p></div></header>
    <form onSubmit={e=>void upload(e)}>
      <label>Tracker type <select value={importKind} onChange={e=>{setImportKind(e.target.value as "SUPPLIERS"|"CONTRACTS");setPreview(null);setDetail(null);}}><option value="SUPPLIERS">Vendor register</option><option value="CONTRACTS">Contracts & agreements</option></select></label>
      <label>Worksheet (optional) <input type="text" value={sourceSheet} onChange={e=>setSourceSheet(e.target.value)} placeholder="All sheets"/></label>
      <label>Header row <input type="number" min={1} max={100} value={headerRow} onChange={e=>setHeaderRow(Number(e.target.value)||1)}/></label>
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
        <th>Sheet / row</th><th>Provider</th><th>Source label (not authority)</th><th>Import status</th><th>Issues</th>
      </tr></thead><tbody>{detail.rows.map(row=>{
        const fields=unpack<Record<string,string|null>>(row.normalized_json);
        const issues=unpack<string[]>(row.diagnostics_json);
        return <tr key={row.id}><td>{row.sheet_name} #{row.row_number}</td>
          <td>{fields.supplier_code||fields.contract_number||"—"} — {fields.legal_name||fields.supplier_name||fields.title||"—"}</td>
          <td>{fields.source_status||"—"} → {detail.batch.import_kind==="CONTRACTS"?"DRAFT":"PROSPECTIVE"}</td>
          <td>{row.status}</td><td>{issues.join(", ")||"—"}</td></tr>;
      })}</tbody></table></div>
      <div className="proc-toolbar">
        <button type="button" className="proc-button" onClick={download}>Export reconciliation CSV</button>
        {detail.batch.status==="STAGED"&&<button type="button"
          className="proc-button proc-button--primary" disabled={busy||errors.length>0||detail.rows.length===0}
          onClick={()=>void confirm()}>Confirm {detail.rows.length} {detail.batch.import_kind==="CONTRACTS"?"draft contracts":"prospective suppliers"}</button>}
      </div>
      {errors.length>0&&<p role="alert">Resolve {errors.length} row errors in the source workbook and stage the corrected file before confirmation.</p>}
      {["STAGED","COMMITTED"].includes(detail.batch.status)&&<div>
        <label>Reason for correction or rollback<textarea value={reason} onChange={e=>setReason(e.target.value)} rows={2}/></label>
        <button type="button" disabled={busy||reason.trim().length<8} onClick={()=>void changeBatch(detail.batch.status==="COMMITTED"?"rollback":"supersede")}>{detail.batch.status==="COMMITTED"?"Controlled rollback":"Supersede preview"}</button>
      </div>}
    </>}
  </section>;
}
