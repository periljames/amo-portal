import React, { useEffect, useRef, useState } from "react";
import { Link, useParams, useSearchParams } from "react-router-dom";
import DepartmentLayout from "../../components/Layout/DepartmentLayout";
import { apiRequest } from "../../services/apiClient";
import { getCachedUser } from "../../services/auth";
import { isTenantAdmin } from "../../utils/tenantAccess";
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
type DeliveryReceipt = {
  email_status: string;
  email_delivery_status: string;
  email_log_id: string | null;
  provider_message_id: string | null;
  sending_mode: string | null;
  provider_accepted: boolean;
};
type DeliveryAttempt = DeliveryReceipt & {
  attempted_at: string;
  recipient: string;
  effective_recipient: string | null;
  template_key: string;
  events: Array<{ event: string; at: string }>;
};
type DeliveryHistory = {
  grant_id: string; grant_status: string; recipient: string; verified: boolean;
  attempts: DeliveryAttempt[]; note: string;
};
const deliveryLabel = (status: string) => {
  const value = status.toUpperCase();
  if (value === "ACCEPTED") return "Accepted by Resend — recipient delivery not confirmed";
  if (value === "DELIVERED") return "Accepted by recipient's mail server — inbox placement not confirmed";
  if (value === "BLOCKED") return "Sending blocked by the configured provider or policy";
  if (value === "FAILED") return "Email send failed";
  if (value === "BOUNCED" || value === "COMPLAINED" || value === "SUPPRESSED") return "Email not deliverable";
  return LABEL(value);
};
const LABEL = (value: string) => value.replaceAll("_", " ").toLowerCase().replace(/\b\w/g,letter=>letter.toUpperCase());
export default function ExternalProviderQualityPage() {
  const { amoCode = "" } = useParams();
  const [query, setQuery] = useSearchParams();
  const section = ["accounts", "invite", "reviews", "history"].includes(query.get("view") || "") ? query.get("view")! : "accounts";
  const supplierFilter = query.get("supplier");
  const focusedGrant = query.get("grant");
  const [stateFilter, setStateFilter] = useState("");
  const [loading, setLoading] = useState(true);
  const setSection = (view: string) => { const next = new URLSearchParams(query); next.set("view", view); setQuery(next); setEditing(null); setError(""); };

  const accountRole = getCachedUser()?.role;
  const manager = isTenantAdmin(getCachedUser()) || accountRole === "QUALITY_MANAGER";
  const canReviewAccounts = manager || accountRole === "QUALITY_OFFICER";
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
  const [historyGrant, setHistoryGrant] = useState<string | null>(null);
  const [deliveryHistory, setDeliveryHistory] = useState<DeliveryHistory | null>(null);
  const [historyLoading, setHistoryLoading] = useState(false);
  const [historyError, setHistoryError] = useState("");
  const historySequence = useRef(0);
  const [editing, setEditing] = useState<Grant | null>(null);
  const [newRole, setNewRole] = useState("READ_ONLY");
  const [capabilities, setCapabilities] = useState<string[]>([]);
  const [scopes, setScopes] = useState<Record<string, string[]>>({});
  const [scopeKind, setScopeKind] = useState("contracts");
  const [scopeSearch, setScopeSearch] = useState("");
  const [scopeOffset, setScopeOffset] = useState(0);
  const [scopeOptions, setScopeOptions] = useState<Array<{id:string;label:string}>>([]);
  const [scopeMore, setScopeMore] = useState(false);
  const [scopeLoading, setScopeLoading] = useState(false);
  const base = `/api/maintenance/${encodeURIComponent(amoCode)}/quality/external-accounts`;
  const requestSequence = useRef(0);
  const refresh = async () => {
    const requestId = ++requestSequence.current;
    setLoading(true);
    try {
    const [accounts, audit] = await Promise.all([
      apiRequest<{ items: Grant[] }>(base,{cacheTtlMs:0}),
      apiRequest<{ items: AuditEvent[] }>(`${base}/events`,{cacheTtlMs:0}),
    ]);
    if(requestId === requestSequence.current) { setItems(accounts.items); setEvents(audit.items); }
    } finally { if(requestId === requestSequence.current) setLoading(false); }
  };
  useEffect(() => { if (canReviewAccounts) void refresh().catch((e) => setError(e instanceof Error ? e.message : "Could not load accounts")); }, [amoCode, canReviewAccounts]);
  useEffect(() => {
    if (!manager || section !== "invite") return;
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
  },[amoCode,manager,section,supplierSearch,supplierOffset]);

  useEffect(()=>{
    if(!editing || !manager) return;
    const controller=new AbortController();setScopeLoading(true);setScopeOptions([]);
    apiRequest<{items:Array<{id:string;label:string}>;has_more:boolean}>(`${base}/grants/${encodeURIComponent(editing.grant_id)}/scope-options?kind=${scopeKind}&search=${encodeURIComponent(scopeSearch)}&offset=${scopeOffset}`,{signal:controller.signal,cacheTtlMs:0})
      .then(data=>{if(!controller.signal.aborted){setScopeOptions(data.items);setScopeMore(data.has_more);}})
      .catch(e=>{if(!controller.signal.aborted)setError(e instanceof Error?e.message:"Record options could not load");})
      .finally(()=>{if(!controller.signal.aborted)setScopeLoading(false);});
    return()=>controller.abort();
  },[base,editing?.grant_id,manager,scopeKind,scopeSearch,scopeOffset]);

  async function loadDeliveryHistory(grantId: string) {
    const sequence = ++historySequence.current;
    setHistoryGrant(grantId);
    setHistoryError("");
    setHistoryLoading(true);
    try {
      const result = await apiRequest<DeliveryHistory>(
        base + "/grants/" + encodeURIComponent(grantId) + "/delivery-history",
        { cacheTtlMs: 0 },
      );
      if (sequence === historySequence.current) setDeliveryHistory(result);
    } catch (cause) {
      if (sequence === historySequence.current) {
        setHistoryError(cause instanceof Error ? cause.message : "Delivery history is not available.");
        setDeliveryHistory(null);
      }
    } finally {
      if (sequence === historySequence.current) setHistoryLoading(false);
    }
  }

  async function act(path: string, body: object, success: string, method = "POST") {
    if (busy) return;
    if ("reason" in body && (typeof body.reason !== "string" || body.reason.trim().length < 8)) {
      setError("Enter a specific decision reason of at least 8 characters before changing access.");
      return;
    }
    setBusy(true);
    setError("");
    setMessage("");
    try {
      const result = await apiRequest<{
        id?: string;
        delivery_status?: string;
        delivery?: DeliveryReceipt;
      }>(base + path, {
        method, headers: {"Content-Type":"application/json"}, body:JSON.stringify(body),
      });
      if (result.delivery) {
        const receipt = result.delivery;
        const accepted = receipt.provider_accepted;
        const sandbox = receipt.sending_mode === "SANDBOX";
        if (!accepted) {
          setError("Account record saved, but invitation email was not accepted. " +
            deliveryLabel(receipt.email_delivery_status) +
            (receipt.email_log_id ? " · Mail log: " + receipt.email_log_id : "") +
            ". Review delivery history and mail configuration before resending.");
        } else {
          setMessage(sandbox
            ? "Invitation recorded. Resend accepted the sandbox message, but the intended recipient was NOT emailed."
            : "Invitation recorded. Resend accepted the email; recipient delivery is not yet confirmed.");
        }
        const grantId = result.id || (path.match(/\/grants\/([^/]+)/)?.[1] ?? null);
        if (grantId) void loadDeliveryHistory(grantId);
      } else if (result.delivery_status && result.delivery_status !== "SENT") {
        setError("Account record saved. Email delivery status: " + result.delivery_status +
          ". Review the mail configuration before resending.");
      } else {
        setMessage(success);
      }
      setEditing(null);
      setReason("");
      // The invite record was committed even if the mail send failed;
      // resetting prevents accidental duplicate-grant submission.
      if (path === "/invitations") { setName(""); setEmail(""); setSupplier(""); }
      try {
        await refresh();
      } catch {
        setError("The change was saved, but the register could not refresh. Use Refresh before repeating the action.");
      }
    } catch (cause) {
      setError(cause instanceof Error ? cause.message : "Account operation failed");
    } finally { setBusy(false); }
  }
  useEffect(() => {
    if (focusedGrant && section === "accounts" && canReviewAccounts) {
      void loadDeliveryHistory(focusedGrant);
    }
    // Grant deep links select only a permitted tenant account via the server.
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [focusedGrant, section, canReviewAccounts, amoCode]);
  useEffect(()=>{
    if(!editing) return;
    const panel=document.getElementById("vendor-privilege-editor");
    panel?.scrollIntoView({behavior:"smooth",block:"start"});
    panel?.focus({preventScroll:true});
  },[editing?.grant_id]);
  const selectGrant = (item: Grant) => {
    setEditing(item);setNewRole(item.role_code);setScopeSearch("");setScopeOffset(0);setScopeKind("contracts");
    setCapabilities(item.capabilities_json || []);
    setScopes(Object.fromEntries(
      Object.entries(item.object_scope_json || {}).filter(([key])=>key!=="contracted_work")
    ));
  };
  if (!canReviewAccounts) return <DepartmentLayout amoCode={amoCode} activeDepartment="quality">
    <div className="vendor-portal vendor-quality-workspace"><div className="vendor-shell">
      <section className="vendor-card">
        <span className="vendor-eyebrow">QMS · Vendor accounts & access</span>
        <h1>External provider access</h1>
        <h2>Quality appointment required</h2>
        <p>A tenant administrator, Quality Manager or Quality Officer manages vendor accounts and reviews provider submissions. Your current account does not have this access.</p>
        <p>Ask your AMO administrator or Quality team to review your access.</p>
        <nav aria-label="Provider management">
          <Link to={`/maintenance/${encodeURIComponent(amoCode)}/quality/suppliers/register`}>External Providers register</Link>
          <a href={`/vendor/login?amo=${encodeURIComponent(amoCode)}`} target="_blank" rel="noreferrer">Open vendor sign in</a>
        </nav>
      </section>
    </div></div>
  </DepartmentLayout>;
  const filtered=items.filter(i=>(!focusedGrant || i.grant_id===focusedGrant) && (!supplierFilter || String(i.supplier_id)===supplierFilter) && (!stateFilter || i.grant_state===stateFilter)).filter((i) => `${i.legal_name} ${i.email} ${i.supplier_code}`
    .toLowerCase().includes(search.toLowerCase()));
  return <DepartmentLayout amoCode={amoCode} activeDepartment="quality"><main className="vendor-portal vendor-quality-workspace">
    <div className="vendor-shell">
      <header className="vendor-header vendor-header--quality">
          <div><span className="vendor-workspace-eyebrow">External providers</span><h1>Vendor accounts &amp; access</h1><p>Manage representatives and review submissions against the shared provider record.</p></div>
          <nav aria-label="Provider management">
            <Link to={`/maintenance/${encodeURIComponent(amoCode)}/quality/suppliers/register`}>External Providers register</Link>
            <a href={`/vendor/login?amo=${encodeURIComponent(amoCode)}`} target="_blank" rel="noreferrer">Open vendor sign in</a>
          </nav>
        <button type="button" disabled={busy} onClick={() => void refresh().catch((e) => setError(String(e)))}>Refresh access register</button>
      </header>
      <nav className="vendor-workspace-tabs" aria-label="Vendor account workspace">
        {[["accounts","Accounts"],["invite","Invite representative"],["reviews","Submissions & reviews"],["history","Access history"]].filter(([key])=>key!=="invite"||manager).map(([key,label])=><button key={key} type="button" aria-current={section===key?"page":undefined} onClick={()=>setSection(key)}>{label}</button>)}
      </nav>
      <section className="vendor-workspace-summary" aria-label="Vendor account totals">
        <div><strong>{new Set(items.map(i=>i.supplier_id)).size}</strong><span>Provider organizations</span></div>
        <div><strong>{items.filter(i=>i.grant_state==="ACTIVE").length}</strong><span>Active accounts</span></div>
        <div><strong>{items.filter(i=>!i.verified_at).length}</strong><span>Awaiting verification</span></div>
        <div><strong>{items.filter(i=>["SUSPENDED","REVOKED"].includes(i.grant_state)).length}</strong><span>Suspended or revoked</span></div>
      </section>
      <nav className="vendor-connected-work" aria-label="Connected provider work">
        <Link to={`/maintenance/${encodeURIComponent(amoCode)}/quality/suppliers/register`}>Provider registration & approval</Link>
        <Link to={`/maintenance/${encodeURIComponent(amoCode)}/quality/suppliers/supplier-findings`}>Provider findings</Link>
        <Link to={`/maintenance/${encodeURIComponent(amoCode)}/doc-control/provider-evidence`}>Document Control evidence</Link>
        <Link to={`/maintenance/${encodeURIComponent(amoCode)}/procurement/suppliers`}>Procurement suppliers</Link>
        <Link to={`/maintenance/${encodeURIComponent(amoCode)}/contracted-work`}>Contracted maintenance work</Link>
      </nav>
      {error ? <div role="alert" className="vendor-error">{error}</div> : null}
      {message ? <div role="status" className="vendor-success">{message}</div> : null}
      {manager && section === "invite" && <section className="vendor-card">
        <h2>Invite provider representative</h2>
        <form className="vendor-grid-form" onSubmit={(e) => {
          e.preventDefault();
          void act("/invitations", {
            supplier_id:Number(supplier), name:name.trim(),email:email.trim(),role_code:role,capabilities:null,object_scope:{},
          },"Invitation sent. User must verify their email; Quality must separately activate the grant and provider portal.");
        }}>
          <label className="vendor-field"><span>Find registered provider</span>
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
      {section === "accounts" && <section className="vendor-card">
        <div className="vendor-toolbar"><h2>Provider representatives</h2>
          <label className="vendor-field"><span>Find representative or provider</span>
            <input type="search" value={search} onChange={(e)=>setSearch(e.target.value)}/></label></div>
        <div className="vendor-account-filters"><label className="vendor-field"><span>Account state</span><select value={stateFilter} onChange={e=>setStateFilter(e.target.value)}><option value="">All states</option>{["PENDING","ACTIVE","SUSPENDED","REVOKED"].map(v=><option key={v} value={v}>{LABEL(v)}</option>)}</select></label>
        {(supplierFilter || focusedGrant) && <button type="button" onClick={()=>{const next=new URLSearchParams(query);next.delete("supplier");next.delete("grant");setQuery(next);}}>Show all providers and accounts</button>}
        {manager && <label className="vendor-field vendor-decision-reason"><span>Reason for the next access decision</span><textarea value={reason} onChange={e=>setReason(e.target.value)} minLength={8} rows={2} placeholder="Record why you are approving, restricting or revoking access." /></label>}</div>
        {loading && <p role="status">Loading provider accounts...</p>}
        <div className="vendor-table-wrap"><table className="vendor-table">
          <thead><tr><th>Provider</th><th>Representative</th><th>Role</th>
            <th>Verification</th><th>Grant</th><th>Portal</th><th>Controls</th></tr></thead>
          <tbody>{filtered.map((item)=><tr key={item.grant_id}>
            <td><Link to={`/maintenance/${encodeURIComponent(amoCode)}/quality/suppliers/${item.supplier_id}/overview`}><strong>{item.legal_name}</strong></Link><small>{item.supplier_code}</small></td>
            <td><strong>{item.display_name}</strong><small>{item.email}</small></td>
            <td>{LABEL(item.role_code)}</td><td>{item.verified_at?"Verified":"Pending"}</td>
            <td>{item.grant_state}</td><td>{item.portal_state}{item.restrict_new_work?" · restricted":""}</td>
            <td><div className="vendor-account-delivery">
              <button type="button" className="vendor-delivery-trigger"
                onClick={() => void loadDeliveryHistory(item.grant_id)}
                aria-label={`Inspect invitation delivery for ${item.display_name}`}>
                Email delivery
              </button>
              {manager ? <details className="vendor-account-controls"><summary>Manage account</summary><div className="vendor-actions">
              {manager && <>
                {!item.verified_at && item.grant_state==="PENDING" &&
                  <button disabled={busy} onClick={()=>void act(`/grants/${item.grant_id}/resend-invitation`,{},"One-time invitation reissued.")}>Resend invitation</button>}
                {item.verified_at && item.grant_state!=="ACTIVE" &&
                  <button disabled={busy} onClick={()=>void act(`/grants/${item.grant_id}/decision`,{state:"ACTIVE",reason:reason.trim()},"Account grant activated.")}>Approve account</button>}
                {item.grant_state==="ACTIVE" &&
                  <button disabled={busy} onClick={()=>void act(`/grants/${item.grant_id}/decision`,{state:"SUSPENDED",reason:reason.trim()},"Account suspended and sessions revoked.")}>Suspend account</button>}
                {item.grant_state!=="REVOKED" &&
                  <button disabled={busy} onClick={()=>void act(`/grants/${item.grant_id}/decision`,{state:"REVOKED",reason:reason.trim()},"Account revoked; sessions invalidated.")}>Revoke account</button>}
                {item.portal_state!=="ACTIVE" &&
                  <button disabled={busy} onClick={()=>void act(`/providers/${item.provider_id}/decision`,{state:"ACTIVE",reason:reason.trim()},"Provider portal activated.")}>Activate portal</button>}
                {item.portal_state==="ACTIVE" &&
                  <button disabled={busy} onClick={()=>void act(`/providers/${item.provider_id}/decision`,{state:"SUSPENDED",reason:reason.trim(),restrict_new_work:true},"Provider suspended. Corrective-action response capability may remain available.")}>Suspend portal</button>}
                {item.portal_state==="ACTIVE" && !item.restrict_new_work &&
                  <button disabled={busy} onClick={()=>void act(`/providers/${item.provider_id}/decision`,{state:"ACTIVE",reason:reason.trim(),restrict_new_work:true},"Provider restricted; new work is blocked.")}>Restrict new work</button>}
                {item.portal_state==="ACTIVE" && item.restrict_new_work &&
                  <button disabled={busy} onClick={()=>void act(`/providers/${item.provider_id}/decision`,{state:"ACTIVE",reason:reason.trim(),restrict_new_work:false},"Portal capability restrictions lifted.")}>Lift restriction</button>}
                <button disabled={busy} onClick={()=>void act(`/grants/${item.grant_id}/sessions/revoke`,
                  {state:"PENDING",reason:reason.trim()},
                  "All provider account sessions revoked without changing the account grant.")}>End sessions</button>
                <button disabled={busy} onClick={()=>selectGrant(item)}>Privileges</button>
                <button disabled={busy} onClick={()=>void act(`/grants/${item.grant_id}/reverify`,{state:"PENDING",reason:reason.trim()},"One-time verification code issued and sessions revoked.")}>Reverify</button>
                <button disabled={busy} onClick={()=>void act(`/identities/${item.identity_id}/unlock`,{state:"ACTIVE",reason:reason.trim()},"Login lockout cleared.")}>Unlock login</button>
              </>}
            </div></details> : null}</div></td>
          </tr>)}</tbody>
        </table></div>
        {!loading && !filtered.length && <div className="vendor-empty-state"><h3>No matching vendor accounts</h3><p>Register the organization in External Providers, then invite a representative. Organization approval and portal access remain separate decisions.</p>{manager && <button type="button" className="vendor-primary" onClick={()=>setSection("invite")}>Invite a representative</button>}</div>}
        <p className="vendor-table-caption">{filtered.length} of {items.length} representative accounts. Open a provider name for qualification, agreements and oversight.</p>
      </section>}
      {historyGrant && section === "accounts" && <section className="vendor-card vendor-delivery-history" aria-label="Provider invitation delivery history">
        <div className="vendor-toolbar">
          <div><h2>Invitation delivery history</h2>
            <p>Invitation creation, provider acceptance and recipient delivery are separate events.</p>
          </div>
          <div className="vendor-actions">
            <button type="button" disabled={historyLoading} onClick={() => void loadDeliveryHistory(historyGrant)}>
              {historyLoading ? "Checking…" : "Refresh delivery status"}
            </button>
            <button type="button" onClick={() => {
              historySequence.current++;
              setHistoryGrant(null);
              setDeliveryHistory(null);
              setHistoryError("");
              setHistoryLoading(false);
            }}>Close</button>
          </div>
        </div>
        {historyLoading && <p role="status">Loading provider delivery receipts…</p>}
        {historyError && <p role="alert" className="vendor-error">{historyError}</p>}
        {deliveryHistory && <>
          <p><strong>Intended recipient:</strong> {deliveryHistory.recipient} ·
            <strong> Account:</strong> {deliveryHistory.grant_status} ·
            <strong> Email verified:</strong> {deliveryHistory.verified ? "Yes" : "Not yet"}</p>
          <p className="vendor-delivery-note">{deliveryHistory.note}</p>
          {deliveryHistory.attempts.length ? <ol className="vendor-delivery-attempts">
            {deliveryHistory.attempts.map(attempt => <li key={attempt.email_log_id || attempt.attempted_at}>
              <div className="vendor-delivery-attempt-head">
                <strong>{deliveryLabel(attempt.email_delivery_status)}</strong>
                <time dateTime={attempt.attempted_at}>{new Date(attempt.attempted_at).toLocaleString()}</time>
              </div>
              <p>Template: {attempt.template_key} · Log: {attempt.email_log_id || "Unavailable"}</p>
              {attempt.provider_message_id && <p>Resend message: {attempt.provider_message_id}</p>}
              {attempt.sending_mode === "SANDBOX" && <p className="vendor-delivery-warning">
                Sandbox routing was active. The intended recipient was not the actual delivery destination.
              </p>}
              {attempt.effective_recipient && <p>Effective destination: {attempt.effective_recipient}</p>}
              {!!attempt.events.length && <ul aria-label="Provider events">
                {attempt.events.map((event, index) => <li key={index}>
                  {LABEL(event.event)} · <time dateTime={event.at}>{new Date(event.at).toLocaleString()}</time>
                </li>)}
              </ul>}
            </li>)}
          </ol> : <p role="status">No correlated email receipts have been recorded for this grant.
            Legacy invitations may predate delivery-correlation tracking.</p>}
          {manager && <p><Link to={`/maintenance/${encodeURIComponent(amoCode)}/quality/mail-identity/overview`}>
            Check Quality mail identity</Link></p>}
        </>}
      </section>}
      {manager && editing && <section id="vendor-privilege-editor" tabIndex={-1} className="vendor-card">
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
        <fieldset><legend>Assign specific records</legend>
          <div className="vendor-grid-form"><label className="vendor-field"><span>Record type</span><select value={scopeKind} onChange={e=>{setScopeKind(e.target.value);setScopeOffset(0);}}>{[["contracts","Provider agreements"],["rfqs","Issued RFQs"],["purchase_orders","Sent purchase orders"],["assignments","Audit assignments"]].map(([value,label])=><option key={value} value={value}>{label}</option>)}</select></label>
          <label className="vendor-field"><span>Find a record</span><input type="search" maxLength={200} value={scopeSearch} onChange={e=>{setScopeSearch(e.target.value);setScopeOffset(0);}} /></label></div>
          {scopeLoading ? <p role="status">Loading eligible records...</p> : scopeOptions.length ? scopeOptions.map(option=><label className="vendor-scope-option" key={option.id}><input type="checkbox" checked={(scopes[scopeKind]||[]).includes(option.id)} onChange={e=>setScopes(old=>({...old,[scopeKind]:e.target.checked?[...(old[scopeKind]||[]),option.id]:(old[scopeKind]||[]).filter(v=>v!==option.id)}))}/>{option.label}</label>) : <p>No eligible records match this search. Agreements and commercial records must belong to this provider.</p>}
          <div className="vendor-actions"><button type="button" disabled={scopeLoading||scopeOffset===0} onClick={()=>setScopeOffset(v=>Math.max(0,v-50))}>Previous records</button><button type="button" disabled={scopeLoading||!scopeMore} onClick={()=>setScopeOffset(v=>v+50)}>More records</button></div>
        </fieldset>
        <fieldset><legend>Assigned record boundaries</legend><p>These identifiers come from the saved grant. Uncheck a saved record to remove access, or use the eligible-record selector above to add access.</p>
          {Object.entries(editing.object_scope_json || {}).filter(([key])=>key!=="contracted_work").map(([key,ids])=><div key={key}><h3>{LABEL(key)}</h3>{ids.map(id=><label className="vendor-scope-option" key={id}><input type="checkbox" checked={(scopes[key]||[]).includes(id)} onChange={e=>setScopes(old=>({...old,[key]:e.target.checked?[...(old[key]||[]),id]:(old[key]||[]).filter(v=>v!==id)}))} />{id}</label>)}</div>)}
          {!Object.keys(scopes).length && <p>No specific record access is assigned. This does not grant unrestricted access.</p>}
        </fieldset>
        <div className="vendor-actions">
          <button type="button" disabled={busy} onClick={()=>{
            void act(`/grants/${editing.grant_id}`,{
              role_code:newRole,capabilities,object_scope:scopes,
              version:editing.version,reason:reason.trim(),
            },"Privileges updated; all existing sessions revoked.","PATCH");
          }}>Save governed privileges</button>
          <button type="button" onClick={()=>setEditing(null)}>Cancel</button>
        </div>
      </section>}
      {section === "reviews" && <ExternalPartnerQualityReview amoCode={amoCode} manager={manager} />}
      {section === "history" && <section className="vendor-card">
        <h2>Access decisions and security history</h2>
        <div className="vendor-table-wrap"><table className="vendor-table">
          <thead><tr><th>Event</th><th>Identity</th><th>Actor</th><th>Timestamp</th></tr></thead>
          <tbody>{events.map((e)=><tr key={e.id}><td>{LABEL(e.event_type)}</td>
            <td>{e.identity_label}</td><td>{e.actor_label}</td>
            <td>{new Date(e.occurred_at).toLocaleString()}</td></tr>)}</tbody>
        </table></div>
      </section>}
    </div>
  </main></DepartmentLayout>;
}
