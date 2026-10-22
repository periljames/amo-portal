import React, { useEffect, useState } from "react";
import { Link, useParams } from "react-router-dom";
import DepartmentLayout from "../../components/Layout/DepartmentLayout";
import { apiRequest } from "../../services/apiClient";
import { getCachedUser } from "../../services/auth";
import ExternalPartnerQualityReview from "./ExternalPartnerQualityReview";
import "./external-provider-portal.css";

type Grant = {
  grant_id: string; provider_id: string; supplier_id: number; version: number;
  legal_name: string; supplier_code: string; email: string; display_name: string;
  identity_id: string; role_code: string; capabilities_json: string[];
  object_scope_json: Record<string, string[]>;
  grant_state: string; portal_state: string; identity_state: string;
  verified_at: string | null; restrict_new_work: boolean;
};
type AuditEvent = {
  id: string; event_type: string; identity_label: string;
  actor_label: string; occurred_at: string; details_json: Record<string, unknown>;
};
const ROLES = ["PROVIDER_ADMIN", "QUALITY_REPRESENTATIVE", "TECHNICAL_REPRESENTATIVE",
  "COMMERCIAL_REPRESENTATIVE", "DOCUMENT_SUBMITTER", "READ_ONLY", "CUSTOM"];
const CAPS = ["profile.read", "profile.propose", "document.read", "document.submit", "capa.respond",
  "task.read", "task.respond", "contract.read", "contract.acknowledge", "members.read", "members.manage", "sessions.manage"];
const LABEL = (value: string) => value.replaceAll("_", " ");
export default function ExternalProviderQualityPage() {
  const { amoCode = "" } = useParams();
  const manager = getCachedUser()?.role === "QUALITY_MANAGER";
  const [items, setItems] = useState<Grant[]>([]);
  const [events, setEvents] = useState<AuditEvent[]>([]);
  const [supplier, setSupplier] = useState("");
  const [supplierSearch, setSupplierSearch] = useState("");
  const [supplierOffset,setSupplierOffset] = useState(0);
  const [supplierOptions,setSupplierOptions] = useState<Array<{
    id:number;supplier_code:string;legal_name:string;status:string;is_active:boolean;
    external_import_pending_activation:boolean;
  }>>([]);
  const [hasMoreSuppliers,setHasMoreSuppliers]=useState(false);
  const [name, setName] = useState("");
  const [email, setEmail] = useState("");
  const [role, setRole] = useState("READ_ONLY");
  const [reason, setReason] = useState("");
  const [search, setSearch] = useState("");
  const [error, setError] = useState("");
  const [message, setMessage] = useState("");
  const [busy, setBusy] = useState(false);
  const [editing, setEditing] = useState<Grant | null>(null);
  const [newRole, setNewRole] = useState("READ_ONLY");
  const [capabilities, setCapabilities] = useState<string[]>([]);
  const [scopes, setScopes] = useState("{}");
  const base = `/api/maintenance/${encodeURIComponent(amoCode)}/quality/external-accounts`;
  const refresh = async () => {
    const [accounts, audit] = await Promise.all([
      apiRequest<{ items: Grant[] }>(base,{cacheTtlMs:0}),
      apiRequest<{ items: AuditEvent[] }>(`${base}/events`,{cacheTtlMs:0}),
    ]);
    setItems(accounts.items); setEvents(audit.items);
  };
  useEffect(() => { void refresh().catch((e) => setError(e instanceof Error ? e.message : "Could not load accounts")); }, [amoCode]);
  useEffect(() => {
    if (!manager) return;
    const abort = new AbortController();
    void apiRequest<{items:typeof supplierOptions;has_more:boolean}>(
      `${base}/suppliers?search=${encodeURIComponent(supplierSearch)}&limit=25&offset=${supplierOffset}`,
      {cacheTtlMs:0,signal:abort.signal}
    ).then(data=>{
      if (!abort.signal.aborted) {
        setSupplierOptions(data.items);
        setHasMoreSuppliers(data.has_more);
      }
    }).catch(e=>{
      if (!abort.signal.aborted) setError(e instanceof Error?e.message:"Supplier list unavailable");
    });
    return () => abort.abort();
  },[amoCode,manager,supplierSearch,supplierOffset]);

  async function act(path: string, body: object, success: string, method = "POST") {
    setBusy(true);setError("");setMessage("");
    try {
      const result = await apiRequest<{delivery_status?:string}>(base + path, {
        method, headers: {"Content-Type":"application/json"}, body:JSON.stringify(body),
      });
      await refresh();
      setMessage(result.delivery_status && result.delivery_status !== "SENT"
        ? `Account record saved. Email delivery status: ${result.delivery_status}. Configure the notification provider or resend the invitation.`
        : success);
      setEditing(null);
    } catch(e) { setError(e instanceof Error ? e.message : "Account operation failed"); }
    finally {setBusy(false);}
  }
  const selectGrant = (item: Grant) => {
    setEditing(item);setNewRole(item.role_code);
    setCapabilities(item.capabilities_json || []);
    setScopes(JSON.stringify(Object.fromEntries(
      Object.entries(item.object_scope_json || {}).filter(([key])=>key!=="contracted_work")
    ),null,2));
  };
  const filtered=items.filter((i) => `${i.legal_name} ${i.email} ${i.supplier_code}`
    .toLowerCase().includes(search.toLowerCase()));
  return <DepartmentLayout amoCode={amoCode} activeDepartment="quality"><main className="vendor-portal vendor-quality-workspace">
    <div className="vendor-shell">
      <header className="vendor-header">
        <div><span className="vendor-eyebrow">QUALITY DEPARTMENT · EXTERNAL ACCOUNT GOVERNANCE</span>
          <h1>External provider access</h1>
          <p>Portal account decisions do not approve suppliers commercially or authorize maintenance work.</p>
          <nav aria-label="Provider management">
            <Link to={`/maintenance/${encodeURIComponent(amoCode)}/quality/suppliers/register`}>External Providers register</Link>
            <a href={`/vendor/login?amo=${encodeURIComponent(amoCode)}`} target="_blank" rel="noreferrer">Open vendor sign in</a>
          </nav>
        </div>
        <button type="button" disabled={busy} onClick={() => void refresh().catch((e) => setError(String(e)))}>Refresh access register</button>
      </header>
      {error ? <div role="alert" className="vendor-error">{error}</div> : null}
      {message ? <div role="status" className="vendor-success">{message}</div> : null}
      {manager && <section className="vendor-card">
        <h2>Invite provider representative</h2>
        <form className="vendor-grid-form" onSubmit={(e) => {
          e.preventDefault();
          void act("/invitations", {
            supplier_id:Number(supplier), name,email,role_code:role,capabilities:null,object_scope:{},
          },"Invitation sent. User must verify their email; Quality must separately activate the grant and provider portal.");
        }}>
          <label className="vendor-field"><span>Find canonical supplier</span>
            <input type="search" value={supplierSearch} placeholder="Search supplier name or vendor code"
              onChange={e=>{setSupplierSearch(e.target.value);setSupplierOffset(0);setSupplier("");}}/>
          </label>
          <label className="vendor-field"><span>Provider organization</span>
            <select required value={supplier} onChange={e=>setSupplier(e.target.value)}>
              <option value="">Select a registered supplier</option>
              {supplierOptions.map(item=><option value={item.id} key={item.id}>
                {item.legal_name} · {item.supplier_code} · {item.status}
                {item.external_import_pending_activation?" · import pending":""}
              </option>)}
            </select>
          </label>
          <div className="vendor-actions">
            <button type="button" disabled={supplierOffset===0}
              onClick={()=>{setSupplierOffset(v=>Math.max(0,v-25));setSupplier("");}}>Previous suppliers</button>
            <button type="button" disabled={!hasMoreSuppliers}
              onClick={()=>{setSupplierOffset(v=>v+25);setSupplier("");}}>More suppliers</button>
          </div>
          <label className="vendor-field"><span>Full name</span>
            <input required minLength={2} value={name} onChange={(e)=>setName(e.target.value)}/></label>
          <label className="vendor-field"><span>Email</span>
            <input type="email" required value={email} onChange={(e)=>setEmail(e.target.value)}/></label>
          <label className="vendor-field"><span>External role</span>
            <select value={role} onChange={(e)=>setRole(e.target.value)}>{ROLES.filter(x=>x!=="CUSTOM").map(x=><option key={x} value={x}>{LABEL(x)}</option>)}</select></label>
          <button type="submit" disabled={busy||!supplier}>Issue one-time email invitation</button>
        </form>
      </section>}
      <section className="vendor-card">
        <div className="vendor-toolbar"><h2>Accounts and provider organizations</h2>
          <label className="vendor-field"><span>Find representative or provider</span>
            <input type="search" value={search} onChange={(e)=>setSearch(e.target.value)}/></label></div>
        <div className="vendor-table-wrap"><table className="vendor-table">
          <thead><tr><th>Provider / key</th><th>Person / identity</th><th>Role</th>
            <th>Verification</th><th>Grant</th><th>Portal</th><th>Controls</th></tr></thead>
          <tbody>{filtered.map((item)=><tr key={item.grant_id}>
            <td><strong>{item.legal_name}</strong><small>{item.supplier_code}</small></td>
            <td><strong>{item.display_name}</strong><small>{item.email}</small></td>
            <td>{LABEL(item.role_code)}</td><td>{item.verified_at?"Verified":"Pending"}</td>
            <td>{item.grant_state}</td><td>{item.portal_state}{item.restrict_new_work?" · restricted":""}</td>
            <td><div className="vendor-actions">
              {manager && <>
                {!item.verified_at && item.grant_state==="PENDING" &&
                  <button disabled={busy} onClick={()=>void act(`/grants/${item.grant_id}/resend-invitation`,{},"One-time invitation reissued.")}>Resend invitation</button>}
                {item.verified_at && item.grant_state!=="ACTIVE" &&
                  <button disabled={busy} onClick={()=>void act(`/grants/${item.grant_id}/decision`,{state:"ACTIVE",reason:reason||"Quality reviewed and approved provider user access."},"Account grant activated.")}>Approve account</button>}
                {item.grant_state==="ACTIVE" &&
                  <button disabled={busy} onClick={()=>void act(`/grants/${item.grant_id}/decision`,{state:"SUSPENDED",reason:reason||"Quality suspended this external access grant."},"Account suspended and sessions revoked.")}>Suspend account</button>}
                {item.grant_state!=="REVOKED" &&
                  <button disabled={busy} onClick={()=>void act(`/grants/${item.grant_id}/decision`,{state:"REVOKED",reason:reason||"Quality revoked this external account access after review."},"Account revoked; sessions invalidated.")}>Revoke account</button>}
                {item.portal_state!=="ACTIVE" &&
                  <button disabled={busy} onClick={()=>void act(`/providers/${item.provider_id}/decision`,{state:"ACTIVE",reason:reason||"Quality approved external portal organization access."},"Provider portal activated.")}>Activate portal</button>}
                {item.portal_state==="ACTIVE" &&
                  <button disabled={busy} onClick={()=>void act(`/providers/${item.provider_id}/decision`,{state:"SUSPENDED",reason:reason||"Quality suspended provider portal access.",restrict_new_work:true},"Provider suspended. Corrective-action response capability may remain available.")}>Suspend portal</button>}
                {item.portal_state==="ACTIVE" && !item.restrict_new_work &&
                  <button disabled={busy} onClick={()=>void act(`/providers/${item.provider_id}/decision`,{state:"ACTIVE",reason:reason||"Quality restricted the provider to existing permitted corrective work.",restrict_new_work:true},"Provider restricted; new work is blocked.")}>Restrict new work</button>}
                {item.portal_state==="ACTIVE" && item.restrict_new_work &&
                  <button disabled={busy} onClick={()=>void act(`/providers/${item.provider_id}/decision`,{state:"ACTIVE",reason:reason||"Quality reviewed restrictions and restored approved portal capabilities.",restrict_new_work:false},"Portal capability restrictions lifted.")}>Lift restriction</button>}
                <button disabled={busy} onClick={()=>void act(`/grants/${item.grant_id}/sessions/revoke`,
                  {state:"PENDING",reason:reason||"Quality revoked all active sessions pending identity access review."},
                  "All provider account sessions revoked without changing the account grant.")}>End sessions</button>
                <button disabled={busy} onClick={()=>selectGrant(item)}>Privileges</button>
                <button disabled={busy} onClick={()=>void act(`/grants/${item.grant_id}/reverify`,{state:"PENDING",reason:reason||"Quality requires identity re-verification before restoration."},"One-time verification code issued and sessions revoked.")}>Reverify</button>
                <button disabled={busy} onClick={()=>void act(`/identities/${item.identity_id}/unlock`,{state:"ACTIVE",reason:reason||"Quality reviewed login lockout and approved unlock."},"Login lockout cleared.")}>Unlock login</button>
              </>}
            </div></td>
          </tr>)}</tbody>
        </table></div>
        {!filtered.length && <p>No external accounts found for this tenant.</p>}
        <label className="vendor-field"><span>Recorded decision reason (optional quick actions use prescribed rationale)</span>
          <textarea value={reason} onChange={(e)=>setReason(e.target.value)} rows={2}/></label>
      </section>
      {manager && editing && <section className="vendor-card">
        <h2>Review assigned privilege boundaries · {editing.email}</h2>
        <p>Updating permissions immediately revokes current sessions. Internal QMS approvals are never available here.</p>
        <label className="vendor-field"><span>External role</span>
          <select value={newRole} onChange={(e)=>setNewRole(e.target.value)}>
            {ROLES.map((value)=><option key={value} value={value}>{LABEL(value)}</option>)}
          </select></label>
        <fieldset><legend>Allowed capabilities</legend><div className="vendor-capabilities">
          {CAPS.map((cap)=><label key={cap}><input type="checkbox" checked={capabilities.includes(cap)}
            onChange={(e)=>setCapabilities((values)=>e.target.checked?[...values,cap]:values.filter(v=>v!==cap))}/>{cap}</label>)}
        </div></fieldset>
        <p>Maintenance work assignments are issued by the responsible Maintenance Manager, not this Quality privilege editor.</p>
        {Boolean(editing.object_scope_json?.contracted_work?.length) && <p role="status">
          Assigned contracted work (read-only): {editing.object_scope_json.contracted_work.join(", ")}
        </p>}
        <label className="vendor-field"><span>Exact object scope JSON (contracts, documents, assignments, RFQs, purchase_orders; contracted_work is Maintenance-managed and read-only here)</span>
          <textarea rows={5} value={scopes} onChange={(e)=>setScopes(e.target.value)} /></label>
        <div className="vendor-actions">
          <button type="button" disabled={busy} onClick={()=>{
            let scope: Record<string,string[]>;
            try{scope=JSON.parse(scopes) as Record<string,string[]>;}catch{setError("Object scope must be valid JSON");return;}
            void act(`/grants/${editing.grant_id}`,{
              role_code:newRole,capabilities,object_scope:scope,
              version:editing.version,reason:reason||"Quality reviewed and constrained provider portal privileges.",
            },"Privileges updated; all existing sessions revoked.","PATCH");
          }}>Save governed privileges</button>
          <button type="button" onClick={()=>setEditing(null)}>Cancel</button>
        </div>
      </section>}
      <ExternalPartnerQualityReview amoCode={amoCode} manager={manager} />
      <section className="vendor-card">
        <h2>Security event history</h2>
        <div className="vendor-table-wrap"><table className="vendor-table">
          <thead><tr><th>Event</th><th>Identity</th><th>Actor</th><th>Timestamp</th></tr></thead>
          <tbody>{events.map((e)=><tr key={e.id}><td>{LABEL(e.event_type)}</td>
            <td>{e.identity_label}</td><td>{e.actor_label}</td>
            <td>{new Date(e.occurred_at).toLocaleString()}</td></tr>)}</tbody>
        </table></div>
      </section>
    </div>
  </main></DepartmentLayout>;
}
