import { getApiBaseUrl } from "../../services/config";

export type Page<T> = { items: T[]; limit: number; offset: number; has_more: boolean; next_offset?: number };
export type PartnerSession = {
  tenant: string; organization: { supplier_code: string; legal_name: string; trading_name: string | null; status: string; portal_state: string; restrict_new_work: boolean; display_name: string; email: string } | null;
  role: string; capabilities: string[]; session_state: string; restricted: boolean; account_url: string;
};
export type Summary = {
  supplier: { legal_name: string; supplier_code: string; status: string; portal_state: string; restrict_new_work: boolean; review_due?: string | null };
  expiring_certificates: Array<{ certificate_type: string; certificate_number: string; valid_until: string; verification_state: string }>;
  expiring_contracts: Array<{ id: string; title: string; contract_number: string; expires_on: string; status: string }>;
  open_change_requests: number; unread_notifications: number;
  outstanding_tasks: {rfqs:number;purchase_orders:number;audit_requests:number;cars:number};
  urgent_tasks: Array<{kind:string;title:string;due:string|null;to:string}>;
  approved_scope: Array<{category:string;product_family:string;site_code:string;approval_number:string|null}>;
  recent_notifications: Array<{id:string;title:string;category:string;created_at:string;read_at:string|null}>;
  actions: Array<{ kind: string; title: string; due: string; to: string }>;
  operational_sections_available: boolean;
};
export type Organization = {
  supplier: Record<string, string | number | boolean | null>;
  profile: Record<string, string | number | boolean | null> | null;
  roles: Array<{ role_code: string; notes: string | null }>;
  change_policy: string;
};
export type Change = {
  id: string; category: string; proposed_json: Record<string,string>;
  reason: string; status: string; review_note: string | null; created_at: string;
};
export type Contract = {
  id: string; contract_number: string; title: string; status: string;
  scope_text: string; effective_on: string | null; expires_on: string | null;
  renewal_terms: string | null; version: number;
  controlled_document_id: string | null; controlled_document_revision: string | null;
  controlled_document_access: string;
};
export type Notification = {
  id: string; category: string; title: string; message: string; read_at: string | null;
  created_at: string; resource_kind: string | null; resource_id: string | null;
};
export type Evidence = { id: string; evidence_type: string; filename: string; status: string; created_at: string; related_kind: string; related_id: string | null; review_note: string | null };
export type QualityPage = {
  notices: Page<{ id:string; subject:string; status:string; notice_date:string; audit_ref:string; revision_no:number }>;
  document_requests: Page<{ id:string; title:string; status:string; due_date:string; audit_ref:string; description:string | null }>;
  findings: Page<{ id:string; finding_ref:string|null; description:string; requirement_ref:string|null; severity:string; target_close_date:string|null; closed_at:string|null }>;
  cars: Page<{ id:string; car_number:string; title:string; status:string; due_date:string; root_cause_status:string; capa_status:string; assignment_id:string }>;
  accepted_evidence: Page<{ id:string;filename:string;evidence_type:string;related_id:string;status:string }>;
  submission_policy: string;
};
export type ProcurementPage = {
  rfqs: Page<{ id:number; rfq_number:string; title:string; status:string; response_due_at:string }>;
  purchase_orders: Page<{ id:number; po_number:string; status:string; acknowledged_at:string | null; promised_delivery_date:string | null }>;
  transaction_state:string; next_phase:string;
};
const BASE = "/api/external-provider";

export class PartnerRequestError extends Error {
  status: number;
  constructor(status:number,message:string) {
    super(message); this.status=status; this.name="PartnerRequestError";
  }
}
export function partnerUrl(tenant:string,path:string):string {
  return `${getApiBaseUrl()}${BASE}/partner/${encodeURIComponent(tenant)}/${path.replace(/^\//,"")}`;
}
export async function partnerRequest<T>(tenant:string,path:string,options:{
  method?: "GET"|"POST"|"PATCH"; body?: unknown; csrf?:string; signal?:AbortSignal;
}={}): Promise<T> {
  const response=await fetch(partnerUrl(tenant,path),{
    method:options.method||"GET",credentials:"include",signal:options.signal,cache:"no-store",
    headers:{...(options.body!==undefined?{"Content-Type":"application/json"}:{}),
      ...(options.csrf?{"X-External-CSRF":options.csrf}:{})},
    ...(options.body!==undefined?{body:JSON.stringify(options.body)}:{}),
  });
  const body=await response.json().catch(()=>({})) as {detail?:string}&T;
  if(!response.ok)throw new PartnerRequestError(response.status,
    typeof body.detail==="string"?body.detail:`Provider request failed (${response.status})`);
  return body;
}
export async function getExternalSession(signal?:AbortSignal):Promise<{csrf:string}>{
  const response=await fetch(`${getApiBaseUrl()}${BASE}/session`,{
    credentials:"include",cache:"no-store",signal,
  });
  if(!response.ok)throw new PartnerRequestError(response.status,"External session has ended or was revoked");
  return response.json() as Promise<{csrf:string}>;
}
export function partnerUpload(tenant:string,csrf:string,file:File,
  metadata:({requirement_id:string;related_kind:"PROVIDER"|"CONTRACT"|"ASSIGNMENT";related_id:string} |
    {related_kind:"DOCUMENT_REQUEST";request_id:string;response_comment?:string}),
  onProgress:(percent:number)=>void,signal?:AbortSignal):Promise<{id:string;filename:string;sha256:string;status:string}> {
  return new Promise((resolve,reject)=>{
    const xhr=new XMLHttpRequest();
    const uploadPath=metadata.related_kind==="DOCUMENT_REQUEST" ?
      `quality/document-requests/${encodeURIComponent(metadata.request_id)}/submit` : "documents/submissions";
    xhr.open("POST",partnerUrl(tenant,uploadPath));
    xhr.withCredentials=true;
    xhr.setRequestHeader("X-External-CSRF",csrf);
    xhr.upload.onprogress=(event)=>{if(event.lengthComputable)onProgress(Math.round(event.loaded*100/event.total));};
    const abort=()=>xhr.abort();
    signal?.addEventListener("abort",abort,{once:true});
    xhr.onerror=()=>reject(new Error("Evidence upload failed. The file was not confirmed by the server."));
    xhr.onabort=()=>reject(new DOMException("Upload cancelled","AbortError"));
    xhr.onload=()=>{
      signal?.removeEventListener("abort",abort);
      let body:Record<string,string>={};
      try{body=JSON.parse(xhr.responseText) as Record<string,string>;}catch{/* HTTP status still authoritative */}
      if(xhr.status>=200&&xhr.status<300)resolve(body as {id:string;filename:string;sha256:string;status:string});
      else reject(new PartnerRequestError(xhr.status,body.detail||"Evidence upload was not accepted"));
    };
    const data=new FormData();
    data.append("file",file);
    if(metadata.related_kind==="DOCUMENT_REQUEST"){
      if(metadata.response_comment)data.append("response_comment",metadata.response_comment);
    }else{
      data.append("requirement_id",metadata.requirement_id);
      data.append("idempotency_key",crypto.randomUUID().replace(/-/g,""));
      data.append("related_kind",metadata.related_kind);
      if(metadata.related_id)data.append("related_id",metadata.related_id);
    }
    xhr.send(data);
  });
}
export const friendlyDate=(value:string|null|undefined)=>value?
  new Date(value.length===10?`${value}T12:00:00`:value).toLocaleDateString(): "—";
export const label=(value:string|null|undefined)=>String(value||"Not recorded").replaceAll("_"," ").toLowerCase()
  .replace(/\b\w/g,(v)=>v.toUpperCase());
