import React, { useEffect, useMemo, useState } from "react";
import { useSearchParams } from "react-router-dom";

import {
  commercialApi,
  type CommercialModule,
  type PlatformDataMode,
  type TenantControlPlane,
} from "../../services/commercialControl";
import { platformApi, type PlatformTenant } from "../../services/platformControl";
import {
  DataTable,
  EmptyState,
  ErrorState,
  MetricCard,
  PlatformShell,
  StatusBadge,
} from "./components/PlatformShared";
import { usePlatformData } from "./components/usePlatformData";
import "../../styles/platform-commercial-control.css";

const PAGE_SIZE = 40;
const TENANT_TABS = ["overview", "profile", "users", "modules", "subscription", "billing", "usage", "support", "audit"] as const;
type TenantTab = (typeof TENANT_TABS)[number];

const formatDate = (value?: string | null) => value ? new Date(value).toLocaleString() : "—";
const money = (cents = 0, currency = "USD") => new Intl.NumberFormat(undefined, { style: "currency", currency }).format(cents / 100);

function asTenantTab(value: string | null): TenantTab {
  return TENANT_TABS.includes(value as TenantTab) ? value as TenantTab : "overview";
}

export default function PlatformTenantsPage() {
  const [searchParams, setSearchParams] = useSearchParams();
  const dataMode = (searchParams.get("mode") === "DEMO" ? "DEMO" : "REAL") as PlatformDataMode;
  const selectedId = searchParams.get("tenant");
  const activeTab = asTenantTab(searchParams.get("tab"));
  const q = searchParams.get("q") || "";
  const [status, setStatus] = useState("");
  const [offset, setOffset] = useState(0);
  const [drawer, setDrawer] = useState<"provision" | "override" | "subscription" | null>(null);
  const [notice, setNotice] = useState<string | null>(null);
  const [actionError, setActionError] = useState<string | null>(null);
  const [reason, setReason] = useState("Superuser tenant administration");
  const [profile, setProfile] = useState({ name: "", icao_code: "", country: "", contact_email: "", contact_phone: "", time_zone: "Africa/Nairobi" });
  const [provision, setProvision] = useState({
    data_mode: dataMode as PlatformDataMode,
    name: "",
    amo_code: "",
    icao_code: "",
    login_slug: "",
    country: "Kenya",
    time_zone: "Africa/Nairobi",
    owner_first_name: "",
    owner_last_name: "",
    owner_email: "",
    owner_phone: "",
    owner_staff_code: "AMO-OWNER",
    plan_id: "",
    price_book_id: "",
    billing_term: "MONTHLY",
    subscription_status: "TRIALING",
    reason: "Initial tenant provisioning",
  });
  const [subscriptionDraft, setSubscriptionDraft] = useState({ plan_id: "", price_book_id: "", billing_term: "MONTHLY", status: "TRIALING", reason: "Assign tenant subscription" });
  const [overrideDraft, setOverrideDraft] = useState({ module_id: "", access_state: "ENABLED", expires_in_days: 7, reason: "Temporary support entitlement" });
  const [moduleDraft, setModuleDraft] = useState({ module_id: "", quantity: 1, status: "ACTIVE", reason: "Add subscription module" });

  const tenants = usePlatformData(
    () => platformApi.tenants({ q, status, data_mode: dataMode, limit: PAGE_SIZE, offset }),
    [q, status, dataMode, offset],
    { pollMs: 20_000 },
  );
  const catalog = usePlatformData(
    async () => {
      await commercialApi.bootstrap();
      const [modules, plans, books] = await Promise.all([
        commercialApi.modules(),
        commercialApi.plans(),
        commercialApi.priceBooks(dataMode),
      ]);
      return { modules: modules.items, plans: plans.items, books: books.items };
    },
    [dataMode],
    { pollMs: 60_000 },
  );
  const detail = usePlatformData<TenantControlPlane | null>(
    () => selectedId ? commercialApi.tenantControlPlane(selectedId) : Promise.resolve(null),
    [selectedId],
    { pollMs: 20_000 },
  );

  const tenantRows = tenants.data?.items || [];
  const selectedTenant = detail.data;
  const plans = catalog.data?.plans || [];
  const books = catalog.data?.books || [];
  const modules = catalog.data?.modules || [];

  useEffect(() => {
    if (!selectedTenant) return;
    const tenant = selectedTenant.tenant;
    setProfile({
      name: tenant.name || "",
      icao_code: tenant.icao_code || "",
      country: tenant.country || "",
      contact_email: tenant.contact_email || "",
      contact_phone: tenant.contact_phone || "",
      time_zone: tenant.time_zone || "Africa/Nairobi",
    });
    if (selectedTenant.subscription) {
      setSubscriptionDraft((current) => ({
        ...current,
        plan_id: selectedTenant.subscription?.plan_id || "",
        price_book_id: selectedTenant.subscription?.price_book_id || "",
        billing_term: selectedTenant.subscription?.billing_term || "MONTHLY",
        status: selectedTenant.subscription?.status || "ACTIVE",
      }));
    }
  }, [selectedTenant]);

  useEffect(() => {
    const defaultPlan = plans.find((plan) => plan.status === "ACTIVE");
    const defaultBook = books.find((book) => book.status === "ACTIVE");
    setProvision((current) => ({
      ...current,
      data_mode: dataMode,
      plan_id: current.plan_id && plans.some((plan) => plan.id === current.plan_id) ? current.plan_id : defaultPlan?.id || "",
      price_book_id: current.price_book_id && books.some((book) => book.id === current.price_book_id) ? current.price_book_id : defaultBook?.id || "",
      subscription_status: defaultPlan?.trial_days ? "TRIALING" : "ACTIVE",
      billing_term: defaultPlan?.default_billing_term || "MONTHLY",
    }));
  }, [books, dataMode, plans]);

  const setQuery = (patch: Record<string, string | null>) => {
    const next = new URLSearchParams(searchParams);
    Object.entries(patch).forEach(([key, value]) => value ? next.set(key, value) : next.delete(key));
    setSearchParams(next, { replace: true });
  };

  const run = async (operation: () => Promise<unknown>, success: string) => {
    setActionError(null);
    setNotice(null);
    try {
      await operation();
      setNotice(success);
      tenants.reload();
      detail.reload();
      catalog.reload();
    } catch (error) {
      setActionError(error instanceof Error ? error.message : String(error));
      throw error;
    }
  };

  const selectTenant = (tenant: PlatformTenant) => setQuery({ tenant: tenant.id, tab: "overview" });

  const saveProfile = () => selectedId && run(
    () => commercialApi.updateTenant(selectedId, { ...profile, reason }),
    "Tenant profile updated.",
  );

  const createTenant = async () => {
    await run(() => commercialApi.provisionTenant(provision), "Tenant, owner and canonical subscription provisioned.");
    setDrawer(null);
    setProvision((current) => ({ ...current, name: "", amo_code: "", icao_code: "", login_slug: "", owner_first_name: "", owner_last_name: "", owner_email: "", owner_phone: "" }));
  };

  const createSubscription = async () => {
    if (!selectedId) return;
    const existing = selectedTenant?.subscription;
    if (existing) {
      await run(() => commercialApi.updateSubscription(existing.id, { ...subscriptionDraft, reason: subscriptionDraft.reason }), "Subscription updated and legacy access reconciled.");
    } else {
      await run(() => commercialApi.createSubscription({ tenant_id: selectedId, ...subscriptionDraft }), "Canonical subscription created.");
    }
    setDrawer(null);
  };

  const transition = (target_status: string, at_period_end = false) => {
    const subscription = selectedTenant?.subscription;
    if (!subscription) return;
    return run(() => commercialApi.transitionSubscription(subscription.id, { target_status, at_period_end, reason }), `Subscription moved to ${target_status}.`);
  };

  const addModule = () => {
    const subscription = selectedTenant?.subscription;
    if (!subscription || !moduleDraft.module_id) return;
    return run(() => commercialApi.upsertSubscriptionItem(subscription.id, moduleDraft), "Subscription module updated.");
  };

  const createOverride = async () => {
    if (!selectedId || !overrideDraft.module_id) return;
    await run(() => commercialApi.createEntitlementOverride(selectedId, overrideDraft), "Temporary entitlement override created.");
    setDrawer(null);
  };

  const tenantTotal = tenants.data?.total || 0;
  const activeModules = selectedTenant?.entitlements.filter((item) => item.access_state === "ENABLED" || item.access_state === "TRIAL").length || 0;
  const openInvoices = selectedTenant?.invoices.filter((invoice) => invoice.status === "PENDING").length || 0;
  const activeUsers = selectedTenant?.users.filter((user) => user.is_active).length || 0;

  return (
    <PlatformShell
      title="Tenants & Institutions"
      subtitle="Provision AMOs, manage profiles and users, control canonical subscriptions, modules, billing, support access and tenant audit evidence."
      actions={(
        <>
          <div className="platform-mode-switch" aria-label="Tenant environment">
            {(["REAL", "DEMO"] as PlatformDataMode[]).map((mode) => (
              <button key={mode} className={dataMode === mode ? "active" : ""} onClick={() => { setOffset(0); setQuery({ mode, tenant: null, tab: null }); }}>{mode}</button>
            ))}
          </div>
          <button className="platform-btn primary" onClick={() => setDrawer("provision")}>Provision tenant</button>
        </>
      )}
    >
      {tenants.error ? <ErrorState error={tenants.error} retry={tenants.reload} /> : null}
      {catalog.error ? <ErrorState error={catalog.error} retry={catalog.reload} /> : null}
      {actionError ? <div className="platform-error">{actionError}</div> : null}
      {notice ? <div className="platform-inline-success">{notice}</div> : null}

      <section className="platform-grid">
        <MetricCard label={`${dataMode} tenants`} value={tenantTotal} caption="Environment-isolated register" tone="blue" mark="TI" />
        <MetricCard label="Selected tenant" value={selectedTenant?.tenant.name || "None"} caption={selectedTenant?.tenant.amo_code || "Choose from the register"} tone={selectedTenant ? "green" : "amber"} mark="SE" />
        <MetricCard label="Active users" value={selectedTenant ? activeUsers : "—"} caption="Current selected tenant" tone="purple" mark="US" />
        <MetricCard label="Active modules" value={selectedTenant ? activeModules : "—"} caption="Resolved subscription and overrides" tone="green" mark="MO" />
        <MetricCard label="Open invoices" value={selectedTenant ? openInvoices : "—"} caption="Pending tenant invoices" tone={openInvoices ? "amber" : "blue"} mark="IN" />
      </section>

      <section className="platform-commercial-layout">
        <aside className="platform-card platform-commercial-sidebar">
          <div className="platform-section-title"><div><h2>Tenant register</h2><p>No mixed REAL/DEMO view is permitted.</p></div><StatusBadge value={dataMode} /></div>
          <div className="platform-toolbar">
            <input value={q} onChange={(event) => { setOffset(0); setQuery({ q: event.target.value || null }); }} placeholder="Search tenant, code or slug" />
            <select value={status} onChange={(event) => { setStatus(event.target.value); setOffset(0); }}>
              <option value="">Any state</option><option value="active">Active</option><option value="inactive">Inactive</option>
            </select>
          </div>
          <div className="platform-commercial-list">
            {tenantRows.map((tenant) => (
              <button key={tenant.id} className={`platform-commercial-list__item ${selectedId === tenant.id ? "active" : ""}`} onClick={() => selectTenant(tenant)}>
                <span><strong>{tenant.name}</strong><small>{tenant.amo_code} · {tenant.login_slug}</small></span>
                <StatusBadge value={tenant.is_read_only ? "READ ONLY" : tenant.status || (tenant.is_active ? "ACTIVE" : "INACTIVE")} />
              </button>
            ))}
            {!tenantRows.length && !tenants.loading ? <EmptyState label={`No ${dataMode.toLowerCase()} tenants match the filters.`} /> : null}
          </div>
          <div className="platform-actions" style={{ marginTop: 12 }}>
            <button className="platform-btn" disabled={offset === 0} onClick={() => setOffset(Math.max(0, offset - PAGE_SIZE))}>Previous</button>
            <span>{tenantTotal ? offset + 1 : 0}-{Math.min(offset + PAGE_SIZE, tenantTotal)} of {tenantTotal}</span>
            <button className="platform-btn" disabled={offset + PAGE_SIZE >= tenantTotal} onClick={() => setOffset(offset + PAGE_SIZE)}>Next</button>
          </div>
        </aside>

        <div className="platform-commercial-detail">
          {detail.error ? <ErrorState error={detail.error} retry={detail.reload} /> : null}
          {!selectedTenant ? (
            <section className="platform-card platform-commercial-empty"><div><strong>Select a tenant</strong><p>Open a tenant to edit its profile, owner access, modules, subscription, invoices, usage, support context and audit history.</p></div></section>
          ) : (
            <>
              <section className="platform-card">
                <div className="platform-commercial-hero">
                  <div><h2>{selectedTenant.tenant.name}</h2><p>{selectedTenant.tenant.amo_code} · {selectedTenant.tenant.login_slug} · {selectedTenant.tenant.country || "Country not set"}</p></div>
                  <div className="platform-actions"><StatusBadge value={selectedTenant.tenant.data_mode} /><StatusBadge value={selectedTenant.tenant.is_active ? "ACTIVE" : "INACTIVE"} /><StatusBadge value={selectedTenant.subscription?.status || "NO SUBSCRIPTION"} /></div>
                </div>
                <div className="platform-tabs" role="tablist">
                  {TENANT_TABS.map((tab) => <button key={tab} className={activeTab === tab ? "active" : ""} onClick={() => setQuery({ tab })}>{tab.replace("-", " ")}</button>)}
                </div>
              </section>

              {activeTab === "overview" ? (
                <>
                  <section className="platform-commercial-kpis">
                    <div className="platform-commercial-kpi"><span>Plan</span><strong>{selectedTenant.subscription?.plan_name || "Unassigned"}</strong><small>{selectedTenant.subscription?.billing_term || "No billing term"}</small></div>
                    <div className="platform-commercial-kpi"><span>Renewal / period end</span><strong>{selectedTenant.subscription?.current_period_end ? new Date(selectedTenant.subscription.current_period_end).toLocaleDateString() : "—"}</strong><small>{selectedTenant.subscription?.cancel_at_period_end ? "Cancels at period end" : "Normal renewal"}</small></div>
                    <div className="platform-commercial-kpi"><span>Users</span><strong>{selectedTenant.users.length}</strong><small>{activeUsers} active</small></div>
                    <div className="platform-commercial-kpi"><span>Entitlements</span><strong>{selectedTenant.entitlements.length}</strong><small>{activeModules} available</small></div>
                  </section>
                  <section className="platform-commercial-section-grid">
                    <div className="platform-card"><h2>Commercial state</h2><p><StatusBadge value={selectedTenant.subscription?.status || "NO SUBSCRIPTION"} /> {selectedTenant.subscription?.plan_code || "No plan"}</p><p>Provider: {selectedTenant.subscription?.provider || "Manual / not connected"}<br />Currency: {selectedTenant.subscription?.currency || "—"}<br />Collection: {selectedTenant.subscription?.auto_collection ? "Automatic" : "Manual"}</p><div className="platform-actions"><button className="platform-btn primary" onClick={() => setDrawer("subscription")}>{selectedTenant.subscription ? "Edit subscription" : "Assign subscription"}</button>{selectedTenant.subscription ? <button className="platform-btn" onClick={() => run(() => commercialApi.reconcileSubscription(selectedTenant.subscription!.id, reason), "Subscription reconciled against legacy access records.")}>Reconcile access</button> : null}</div></div>
                    <div className="platform-card"><h2>Tenant controls</h2><label className="platform-stack-form"><span>Audit reason</span><textarea value={reason} onChange={(event) => setReason(event.target.value)} /></label><div className="platform-actions"><button className="platform-btn" onClick={() => selectedId && run(() => platformApi.tenantAction(selectedId, "reactivate", { reason }), "Tenant reactivated.")}>Reactivate</button><button className="platform-btn" onClick={() => selectedId && run(() => platformApi.tenantAction(selectedId, "unlock", { reason }), "Tenant unlocked.")}>Unlock</button><button className="platform-btn danger" onClick={() => selectedId && run(() => platformApi.tenantAction(selectedId, "suspend", { reason }), "Tenant suspended.")}>Suspend</button><button className="platform-btn danger" onClick={() => selectedId && run(() => platformApi.tenantAction(selectedId, "lock", { reason }), "Tenant set read-only.")}>Read-only</button></div></div>
                  </section>
                </>
              ) : null}

              {activeTab === "profile" ? (
                <section className="platform-card"><div className="platform-section-title"><div><h2>Organisation profile</h2><p>Edit operational identity without changing immutable AMO code or login slug.</p></div></div><div className="platform-form-grid">
                  <label><span>Name</span><input value={profile.name} onChange={(event) => setProfile({ ...profile, name: event.target.value })} /></label>
                  <label><span>ICAO code</span><input value={profile.icao_code} onChange={(event) => setProfile({ ...profile, icao_code: event.target.value.toUpperCase() })} /></label>
                  <label><span>Country</span><input value={profile.country} onChange={(event) => setProfile({ ...profile, country: event.target.value })} /></label>
                  <label><span>Time zone</span><input value={profile.time_zone} onChange={(event) => setProfile({ ...profile, time_zone: event.target.value })} /></label>
                  <label><span>Contact email</span><input type="email" value={profile.contact_email} onChange={(event) => setProfile({ ...profile, contact_email: event.target.value })} /></label>
                  <label><span>Contact phone</span><input value={profile.contact_phone} onChange={(event) => setProfile({ ...profile, contact_phone: event.target.value })} /></label>
                  <label className="span-2"><span>Reason</span><textarea value={reason} onChange={(event) => setReason(event.target.value)} /></label>
                </div><div className="platform-actions" style={{ marginTop: 12 }}><button className="platform-btn primary" onClick={saveProfile}>Save profile</button></div></section>
              ) : null}

              {activeTab === "users" ? (
                <section className="platform-card"><div className="platform-section-title"><div><h2>Tenant users</h2><p>Account state, role, onboarding and security controls.</p></div><StatusBadge value={`${selectedTenant.users.length} USERS`} /></div>{selectedTenant.users.length ? <DataTable><thead><tr><th>User</th><th>Role</th><th>Status</th><th>Last login</th><th>Actions</th></tr></thead><tbody>{selectedTenant.users.map((user) => <tr key={user.id}><td><strong>{user.full_name}</strong><br /><small>{user.email}</small></td><td>{user.role}</td><td><StatusBadge value={!user.is_active ? "DISABLED" : user.must_change_password ? "PASSWORD SETUP" : "ACTIVE"} /></td><td>{formatDate(user.last_login_at)}</td><td><div className="platform-actions"><button className="platform-btn" onClick={() => run(() => commercialApi.forcePasswordReset(user.id, reason), "Password reset requirement persisted and sessions revoked.")}>Force password reset</button><button className="platform-btn" onClick={() => run(() => platformApi.userAction(user.id, user.is_active ? "disable" : "enable", reason), `User ${user.is_active ? "disabled" : "enabled"}.`)}>{user.is_active ? "Disable" : "Enable"}</button></div></td></tr>)}</tbody></DataTable> : <EmptyState label="No users found for this tenant." />}</section>
              ) : null}

              {activeTab === "modules" ? (
                <>
                  <section className="platform-card"><div className="platform-section-title"><div><h2>Resolved module access</h2><p>Subscription items are the source of truth. Temporary overrides are explicit and expiring.</p></div><button className="platform-btn" onClick={() => setDrawer("override")}>Temporary override</button></div><div className="platform-module-matrix">{selectedTenant.entitlements.map((item) => <article className="platform-module-card" key={item.module_code}><div className="platform-module-card__top"><div><strong>{item.module_name}</strong><small>{item.module_code}</small></div><StatusBadge value={item.access_state} /></div><small>Source: {item.source}{item.plan_code ? ` · ${item.plan_code}` : ""}</small><small>{item.effective_to ? `Until ${formatDate(item.effective_to)}` : "No scheduled end"}</small></article>)}</div>{!selectedTenant.entitlements.length ? <EmptyState label="No resolved module access." /> : null}</section>
                  {selectedTenant.subscription ? <section className="platform-card"><h2>Add or update subscription module</h2><div className="platform-form-grid"><label><span>Module</span><select value={moduleDraft.module_id} onChange={(event) => setModuleDraft({ ...moduleDraft, module_id: event.target.value })}><option value="">Select module</option>{modules.filter((module) => module.status !== "ARCHIVED").map((module) => <option key={module.id} value={module.id}>{module.name} · {module.category}</option>)}</select></label><label><span>Quantity</span><input type="number" min="1" value={moduleDraft.quantity} onChange={(event) => setModuleDraft({ ...moduleDraft, quantity: Number(event.target.value || 1) })} /></label><label><span>Status</span><select value={moduleDraft.status} onChange={(event) => setModuleDraft({ ...moduleDraft, status: event.target.value })}><option>ACTIVE</option><option>PAUSED</option><option>CANCELLED</option></select></label><label><span>Reason</span><input value={moduleDraft.reason} onChange={(event) => setModuleDraft({ ...moduleDraft, reason: event.target.value })} /></label></div><button className="platform-btn primary" style={{ marginTop: 12 }} onClick={addModule}>Save module item</button></section> : null}
                </>
              ) : null}

              {activeTab === "subscription" ? (
                <section className="platform-card"><div className="platform-section-title"><div><h2>Subscription lifecycle</h2><p>One canonical subscription controls plan, term, module items and legacy projections.</p></div><button className="platform-btn primary" onClick={() => setDrawer("subscription")}>{selectedTenant.subscription ? "Edit" : "Assign"}</button></div>{selectedTenant.subscription ? <><div className="platform-commercial-kpis"><div className="platform-commercial-kpi"><span>Status</span><strong>{selectedTenant.subscription.status}</strong><small>{selectedTenant.subscription.cancel_at_period_end ? "Cancellation scheduled" : "No cancellation scheduled"}</small></div><div className="platform-commercial-kpi"><span>Plan</span><strong>{selectedTenant.subscription.plan_name}</strong><small>{selectedTenant.subscription.plan_code}</small></div><div className="platform-commercial-kpi"><span>Term</span><strong>{selectedTenant.subscription.billing_term}</strong><small>{selectedTenant.subscription.currency}</small></div><div className="platform-commercial-kpi"><span>Items</span><strong>{selectedTenant.subscription.items.length}</strong><small>Canonical modules</small></div></div><div className="platform-actions" style={{ marginTop: 14 }}><button className="platform-btn" onClick={() => transition("ACTIVE")}>Activate</button><button className="platform-btn" onClick={() => transition("PAUSED")}>Pause</button><button className="platform-btn" onClick={() => transition("CANCELLED", true)}>Cancel at renewal</button><button className="platform-btn danger" onClick={() => transition("CANCELLED")}>Cancel now</button></div><h3>Event history</h3><div className="platform-timeline">{selectedTenant.subscription.events?.map((event) => <div className="platform-timeline__item" key={event.id}><strong>{event.event_type}</strong><small>{formatDate(event.created_at)} · {event.reason || "No reason recorded"}</small></div>)}</div></> : <EmptyState label="No canonical subscription assigned." />}</section>
              ) : null}

              {activeTab === "billing" ? (
                <section className="platform-card"><div className="platform-section-title"><div><h2>Tenant invoices</h2><p>Invoice balances are derived from payment transactions.</p></div></div>{selectedTenant.invoices.length ? <DataTable><thead><tr><th>Invoice</th><th>Amount</th><th>Paid</th><th>Balance</th><th>Status</th><th>Due</th></tr></thead><tbody>{selectedTenant.invoices.map((invoice) => <tr key={invoice.id}><td><strong>{invoice.invoice_number}</strong><br /><small>{invoice.description}</small></td><td>{money(invoice.amount_cents, invoice.currency)}</td><td>{money(invoice.paid_cents, invoice.currency)}</td><td>{money(invoice.balance_cents, invoice.currency)}</td><td><StatusBadge value={invoice.status} /></td><td>{formatDate(invoice.due_at)}</td></tr>)}</tbody></DataTable> : <EmptyState label="No invoices for this tenant." />}</section>
              ) : null}

              {activeTab === "usage" ? (
                <section className="platform-card"><h2>Usage meters</h2>{selectedTenant.usage.length ? <DataTable><thead><tr><th>Meter</th><th>Used</th><th>Last recorded</th></tr></thead><tbody>{selectedTenant.usage.map((meter) => <tr key={meter.id}><td>{meter.meter_key}</td><td>{meter.used_units.toLocaleString()}</td><td>{formatDate(meter.last_recorded_at)}</td></tr>)}</tbody></DataTable> : <EmptyState label="No usage meters have been recorded." />}</section>
              ) : null}

              {activeTab === "support" ? (
                <section className="platform-commercial-section-grid"><div className="platform-card"><h2>Start support access</h2><div className="platform-stack-form"><label><span>Reason</span><textarea value={reason} onChange={(event) => setReason(event.target.value)} /></label><button className="platform-btn primary" onClick={() => selectedId && run(() => platformApi.startSupportSession({ tenant_id: selectedId, reason, mode: "READ_ONLY", minutes: 30 }), "Read-only support session started.")}>Start 30-minute read-only session</button></div></div><div className="platform-card"><h2>Support tickets</h2>{selectedTenant.support.length ? selectedTenant.support.map((ticket) => <div className="platform-subtle-panel" key={String(ticket.id)}><strong>{String(ticket.title || "Support ticket")}</strong><br /><small>{String(ticket.status || "UNKNOWN")} · {String(ticket.priority || "NORMAL")}</small></div>) : <EmptyState label="No support tickets." />}</div></section>
              ) : null}

              {activeTab === "audit" ? (
                <section className="platform-card"><h2>Privileged tenant audit trail</h2><div className="platform-timeline">{selectedTenant.audit.map((event) => <div className="platform-timeline__item" key={String(event.id)}><strong>{String(event.action || "Platform action")}</strong><small>{formatDate(String(event.created_at || ""))} · {String(event.reason || "No reason")}</small></div>)}</div>{!selectedTenant.audit.length ? <EmptyState label="No platform audit events for this tenant." /> : null}</section>
              ) : null}
            </>
          )}
        </div>
      </section>

      {drawer === "provision" ? (
        <div className="platform-commercial-drawer" role="dialog" aria-modal="true"><div className="platform-commercial-drawer__panel"><div className="platform-commercial-drawer__head"><div><h2>Provision tenant</h2><p>Create the AMO, owner, default departments, canonical subscription and module access in one transaction.</p></div><button className="platform-icon-btn" onClick={() => setDrawer(null)}>×</button></div><div className="platform-inline-warning">This tenant will be created in <strong>{dataMode}</strong>. REAL and DEMO records cannot be combined.</div><div className="platform-form-grid" style={{ marginTop: 14 }}>
          <label><span>Organisation name</span><input value={provision.name} onChange={(event) => setProvision({ ...provision, name: event.target.value })} /></label><label><span>AMO code</span><input value={provision.amo_code} onChange={(event) => setProvision({ ...provision, amo_code: event.target.value.toUpperCase() })} /></label><label><span>ICAO code</span><input value={provision.icao_code} onChange={(event) => setProvision({ ...provision, icao_code: event.target.value.toUpperCase() })} /></label><label><span>Login slug</span><input value={provision.login_slug} onChange={(event) => setProvision({ ...provision, login_slug: event.target.value.toLowerCase() })} /></label><label><span>Country</span><input value={provision.country} onChange={(event) => setProvision({ ...provision, country: event.target.value })} /></label><label><span>Time zone</span><input value={provision.time_zone} onChange={(event) => setProvision({ ...provision, time_zone: event.target.value })} /></label><label><span>Owner first name</span><input value={provision.owner_first_name} onChange={(event) => setProvision({ ...provision, owner_first_name: event.target.value })} /></label><label><span>Owner last name</span><input value={provision.owner_last_name} onChange={(event) => setProvision({ ...provision, owner_last_name: event.target.value })} /></label><label><span>Owner email</span><input type="email" value={provision.owner_email} onChange={(event) => setProvision({ ...provision, owner_email: event.target.value })} /></label><label><span>Owner phone</span><input value={provision.owner_phone} onChange={(event) => setProvision({ ...provision, owner_phone: event.target.value })} /></label><label><span>Product plan</span><select value={provision.plan_id} onChange={(event) => { const plan = plans.find((item) => item.id === event.target.value); setProvision({ ...provision, plan_id: event.target.value, billing_term: plan?.default_billing_term || provision.billing_term, subscription_status: plan?.trial_days ? "TRIALING" : "ACTIVE" }); }}><option value="">Select plan</option>{plans.filter((plan) => plan.status === "ACTIVE").map((plan) => <option key={plan.id} value={plan.id}>{plan.name} · {plan.modules.length} modules</option>)}</select></label><label><span>Price book</span><select value={provision.price_book_id} onChange={(event) => setProvision({ ...provision, price_book_id: event.target.value })}><option value="">Manual / no price book</option>{books.filter((book) => book.status === "ACTIVE").map((book) => <option key={book.id} value={book.id}>{book.name} · {book.currency}</option>)}</select></label><label><span>Billing term</span><select value={provision.billing_term} onChange={(event) => setProvision({ ...provision, billing_term: event.target.value })}><option>MONTHLY</option><option>BI_ANNUAL</option><option>ANNUAL</option></select></label><label><span>Initial state</span><select value={provision.subscription_status} onChange={(event) => setProvision({ ...provision, subscription_status: event.target.value })}><option>TRIALING</option><option>ACTIVE</option><option>DRAFT</option></select></label><label className="span-2"><span>Reason</span><textarea value={provision.reason} onChange={(event) => setProvision({ ...provision, reason: event.target.value })} /></label>
        </div><div className="platform-actions" style={{ marginTop: 16 }}><button className="platform-btn" onClick={() => setDrawer(null)}>Cancel</button><button className="platform-btn primary" onClick={createTenant}>Provision tenant</button></div></div></div>
      ) : null}

      {drawer === "subscription" && selectedTenant ? (
        <div className="platform-commercial-drawer" role="dialog" aria-modal="true"><div className="platform-commercial-drawer__panel"><div className="platform-commercial-drawer__head"><div><h2>{selectedTenant.subscription ? "Edit subscription" : "Assign subscription"}</h2><p>Plan, environment-matched price book, term and status drive all module access.</p></div><button className="platform-icon-btn" onClick={() => setDrawer(null)}>×</button></div><div className="platform-stack-form"><label><span>Plan</span><select value={subscriptionDraft.plan_id} onChange={(event) => setSubscriptionDraft({ ...subscriptionDraft, plan_id: event.target.value })}><option value="">Select plan</option>{plans.filter((plan) => plan.status === "ACTIVE").map((plan) => <option key={plan.id} value={plan.id}>{plan.name}</option>)}</select></label><label><span>{dataMode} price book</span><select value={subscriptionDraft.price_book_id} onChange={(event) => setSubscriptionDraft({ ...subscriptionDraft, price_book_id: event.target.value })}><option value="">Manual / no price book</option>{books.filter((book) => book.status === "ACTIVE").map((book) => <option key={book.id} value={book.id}>{book.name}</option>)}</select></label><label><span>Billing term</span><select value={subscriptionDraft.billing_term} onChange={(event) => setSubscriptionDraft({ ...subscriptionDraft, billing_term: event.target.value })}><option>MONTHLY</option><option>BI_ANNUAL</option><option>ANNUAL</option></select></label>{!selectedTenant.subscription ? <label><span>Initial status</span><select value={subscriptionDraft.status} onChange={(event) => setSubscriptionDraft({ ...subscriptionDraft, status: event.target.value })}><option>TRIALING</option><option>ACTIVE</option><option>DRAFT</option></select></label> : null}<label><span>Reason</span><textarea value={subscriptionDraft.reason} onChange={(event) => setSubscriptionDraft({ ...subscriptionDraft, reason: event.target.value })} /></label><button className="platform-btn primary" onClick={createSubscription}>Save subscription</button></div></div></div>
      ) : null}

      {drawer === "override" && selectedTenant ? (
        <div className="platform-commercial-drawer" role="dialog" aria-modal="true"><div className="platform-commercial-drawer__panel"><div className="platform-commercial-drawer__head"><div><h2>Temporary entitlement override</h2><p>Overrides are separate from subscriptions, fully audited and automatically expire.</p></div><button className="platform-icon-btn" onClick={() => setDrawer(null)}>×</button></div><div className="platform-stack-form"><label><span>Module</span><select value={overrideDraft.module_id} onChange={(event) => setOverrideDraft({ ...overrideDraft, module_id: event.target.value })}><option value="">Select module</option>{modules.map((module: CommercialModule) => <option key={module.id} value={module.id}>{module.name}</option>)}</select></label><label><span>Access</span><select value={overrideDraft.access_state} onChange={(event) => setOverrideDraft({ ...overrideDraft, access_state: event.target.value })}><option>ENABLED</option><option>TRIAL</option><option>SUSPENDED</option><option>DISABLED</option></select></label><label><span>Expires in days</span><input type="number" min="1" max="90" value={overrideDraft.expires_in_days} onChange={(event) => setOverrideDraft({ ...overrideDraft, expires_in_days: Number(event.target.value || 1) })} /></label><label><span>Reason</span><textarea value={overrideDraft.reason} onChange={(event) => setOverrideDraft({ ...overrideDraft, reason: event.target.value })} /></label><button className="platform-btn primary" onClick={createOverride}>Create override</button></div></div></div>
      ) : null}
    </PlatformShell>
  );
}
