import React, { useMemo, useState } from "react";
import { Link, useSearchParams } from "react-router-dom";

import {
  platformApi, type PlatformBillingInvoice, type PlatformBillingTenant,
  type SaaSModulePrice, type TenantModuleSubscription,
} from "../../services/platformControl";
import { DataTable, EmptyState, ErrorState, MetricCard, PlatformShell, StatusBadge } from "./components/PlatformShared";
import { usePlatformData } from "./components/usePlatformData";

type Section = "overview" | "invoices" | "pricing" | "subscriptions" | "jobs";
type DataMode = "REAL" | "DEMO";
type PriceDraft = {
  module_code: string; plan_code: string; billing_term: string;
  currency: string; amount: string; tax_rate: string;
  trial_days: string; external_price_ref: string;
};
const blankPrice: PriceDraft = {
  module_code: "quality", plan_code: "STANDARD", billing_term: "MONTHLY",
  currency: "KES", amount: "0", tax_rate: "0", trial_days: "0", external_price_ref: "",
};
const PAGE_SIZE = 25;
const money = (amount?: number | null, currency = "KES") => {
  try { return new Intl.NumberFormat(undefined, { style: "currency", currency }).format((amount || 0) / 100); }
  catch { return currency + " " + ((amount || 0) / 100).toFixed(2); }
};
const date = (value?: string | null) => value ? new Date(value).toLocaleDateString() : "—";
const currencyTotals = (rows?: Record<string, { pending_amount_cents: number }>) => {
  const totals = Object.entries(rows || {}).filter(([, entry]) => Number(entry.pending_amount_cents) > 0);
  return totals.length ? totals.map(([currency, entry]) => money(entry.pending_amount_cents, currency)).join(" + ") : "—";
};
const tabNames: Record<Section, string> = {
  overview: "Accounts & receivables",
  invoices: "Invoices & payments",
  pricing: "Price catalog",
  subscriptions: "Tenant subscriptions",
  jobs: "Billing operations",
};

function saveFile(blob: Blob, name: string) {
  const address = URL.createObjectURL(blob);
  const anchor = document.createElement("a");
  anchor.href = address;
  anchor.download = name;
  document.body.appendChild(anchor);
  anchor.click();
  anchor.remove();
  window.setTimeout(() => URL.revokeObjectURL(address), 1000);
}

function PriceEditor({
  price, setPrice, save, cancel, busy, editing,
}: {
  price: PriceDraft; setPrice: (value: PriceDraft) => void;
  save: () => void; cancel: () => void; busy: boolean; editing: boolean;
}) {
  const update = (key: keyof PriceDraft, value: string) => setPrice({ ...price, [key]: value });
  return <div className="platform-form">
    <label><span>Module</span><input value={price.module_code} onChange={(e) => update("module_code", e.target.value)} required /></label>
    <label><span>Plan</span><input value={price.plan_code} onChange={(e) => update("plan_code", e.target.value)} required /></label>
    <label><span>Billing interval</span><select value={price.billing_term} onChange={(e) => update("billing_term", e.target.value)}>
      <option value="MONTHLY">Monthly</option><option value="ANNUAL">Annual</option>
      <option value="BI_ANNUAL">Every six months</option><option value="ONE_TIME">One-time</option>
    </select></label>
    <label><span>Currency (ISO code)</span><input value={price.currency} maxLength={3} onChange={(e) => update("currency", e.target.value.toUpperCase())} /></label>
    <label><span>Base price</span><input type="number" value={price.amount} min="0" step="0.01" onChange={(e) => update("amount", e.target.value)} /></label>
    <label><span>VAT / tax %</span><input type="number" value={price.tax_rate} min="0" max="100" step="0.01" onChange={(e) => update("tax_rate", e.target.value)} /></label>
    <label><span>Trial days</span><input type="number" value={price.trial_days} min="0" max="365" onChange={(e) => update("trial_days", e.target.value)} /></label>
    <label><span>Stripe price ID (optional)</span><input value={price.external_price_ref} placeholder="price_..." onChange={(e) => update("external_price_ref", e.target.value)} /></label>
    <div className="platform-actions">
      <button className="platform-btn primary" onClick={save} disabled={busy}>{editing ? "Save price changes" : "Add price to catalog"}</button>
      {editing ? <button className="platform-btn" disabled={busy} onClick={cancel}>Cancel editing</button> : null}
    </div>
  </div>;
}

export default function BillingWorkbench() {
  const [params, setParams] = useSearchParams();
  const [tab, setTab] = useState<Section>("overview");
  const [mode, setMode] = useState<DataMode>("REAL");
  const tenantId = params.get("tenant") || "";
  const [tenantSearch, setTenantSearch] = useState("");
  const [invoiceSearch, setInvoiceSearch] = useState("");
  const [invoiceStatus, setInvoiceStatus] = useState("");
  const [invoiceOffset, setInvoiceOffset] = useState(0);
  const [selectedInvoiceId, setSelectedInvoiceId] = useState("");
  const [reason, setReason] = useState("");
  const [paymentReference, setPaymentReference] = useState("");
  const [selectedPriceId, setSelectedPriceId] = useState("");
  const [priceEditId, setPriceEditId] = useState("");
  const [priceForm, setPriceForm] = useState<PriceDraft>(blankPrice);
  const [quantity, setQuantity] = useState(1);
  const [dueDays, setDueDays] = useState(14);
  const [moduleDrafts, setModuleDrafts] = useState<Record<string, string>>({});
  const [busy, setBusy] = useState(false);
  const [notice, setNotice] = useState("");
  const [error, setError] = useState("");

  const overview = usePlatformData(() => platformApi.billingControl(mode), [mode]);
  const summary = usePlatformData(() => platformApi.billingSummary(mode), [mode]);
  const invoices = usePlatformData(
    () => platformApi.invoices({
      data_mode: mode, tenant_id: tenantId || undefined, q: invoiceSearch.trim() || undefined,
      status: invoiceStatus || undefined, limit: PAGE_SIZE, offset: invoiceOffset,
    }),
    [mode, tenantId, invoiceSearch, invoiceStatus, invoiceOffset],
  );
  const prices = usePlatformData(() => platformApi.modulePrices({ include_inactive: true, limit: 200 }), []);
  const modules = usePlatformData(
    () => tenantId ? platformApi.tenantModules(tenantId) : Promise.resolve({ items: [] as TenantModuleSubscription[] }),
    [tenantId],
  );
  const catalog = usePlatformData(() => platformApi.moduleCatalog(), [], { pollMs: 0, live: false });
  const jobs = usePlatformData(() => platformApi.saasJobs({ queue_name: "billing", tenant_id: tenantId || undefined, limit: 40 }), [tenantId]);

  const refresh = () => {
    overview.reload(); summary.reload(); invoices.reload(); prices.reload(); modules.reload(); jobs.reload();
  };
  const act = async (job: () => Promise<unknown>, success: string) => {
    if (busy) return;
    setBusy(true); setError(""); setNotice("");
    try {
      await job();
      setNotice(success);
      refresh();
    } catch (caught) {
      setError(caught instanceof Error ? caught.message : String(caught));
    } finally { setBusy(false); }
  };
  const selectTenant = (id: string) => {
    const next = new URLSearchParams(params);
    if (id) next.set("tenant", id); else next.delete("tenant");
    setParams(next); setInvoiceOffset(0); setModuleDrafts({}); setSelectedInvoiceId("");
  };

  const tenants = overview.data?.tenants ?? [];
  const tenant = tenants.find((record) => record.id === tenantId) ?? null;
  const shownTenants = useMemo(() => tenants.filter((record) =>
    (record.name + " " + record.amo_code).toLowerCase().includes(tenantSearch.toLowerCase()),
  ), [tenants, tenantSearch]);
  const tenantName = (id: string) => tenants.find((record) => record.id === id)?.name || id;
  const selectedPrice = prices.data?.items?.find((price) => price.id === selectedPriceId) ?? null;
  const selectedInvoice = invoices.data?.items?.find((inv) => inv.id === selectedInvoiceId) ?? null;

  const pricePayload = () => ({
    module_code: priceForm.module_code.trim(),
    plan_code: priceForm.plan_code.trim(),
    billing_term: priceForm.billing_term,
    amount_cents: Math.round(Number(priceForm.amount) * 100),
    tax_rate_bps: Math.round(Number(priceForm.tax_rate) * 100),
    trial_days: Number(priceForm.trial_days),
    currency: priceForm.currency.trim().toUpperCase(),
    external_price_ref: priceForm.external_price_ref.trim() || null,
    reason: reason.trim(),
  });
  const savePrice = () => {
    if (!reason.trim()) return setError("Enter a reason for the catalog change.");
    const payload = pricePayload();
    if (!payload.module_code || !payload.plan_code || !Number.isFinite(payload.amount_cents)
      || payload.amount_cents < 0 || !Number.isFinite(payload.tax_rate_bps)
      || payload.tax_rate_bps < 0 || payload.tax_rate_bps > 10000
      || payload.trial_days < 0 || payload.trial_days > 365 || !/^[A-Z]{3}$/.test(payload.currency)) {
      return setError("Review the module, plan, amount, tax, trial days and three-letter currency.");
    }
    void act(() => priceEditId ? platformApi.updateModulePrice(priceEditId, payload) : platformApi.createModulePrice(payload),
      "Catalog change saved and logged.");
  };
  const editPrice = (price: SaaSModulePrice) => {
    setTab("pricing"); setPriceEditId(price.id);
    setPriceForm({
      module_code: price.module_code, plan_code: price.plan_code,
      billing_term: price.billing_term, amount: String(price.amount_cents / 100),
      currency: price.currency, tax_rate: String(price.tax_rate_bps / 100),
      trial_days: String(price.trial_days), external_price_ref: price.external_price_ref || "",
    });
  };
  const saveModules = () => {
    if (!tenantId || !reason.trim()) return setError("Select a tenant and enter a reason.");
    const changes = Object.entries(moduleDrafts).map(([module_code, status]) => ({
      module_code, status, plan_code: modules.data?.items?.find((row) => row.module_code === module_code)?.plan_code || "STANDARD",
    }));
    if (!changes.length) return setError("Change at least one module first.");
    void act(() => platformApi.updateTenantModules(tenantId, changes, reason.trim()), "Module changes saved to the tenant account.");
    setModuleDrafts({});
  };
  const makeInvoice = () => {
    if (!tenantId || !selectedPriceId || !reason.trim()) return setError("Choose the tenant, price and reason.");
    if (!Number.isInteger(quantity) || quantity < 1 || !Number.isInteger(dueDays) || dueDays < 0 || dueDays > 365) return setError("Review quantity and payment terms.");
    void act(() => platformApi.createManualInvoice(tenantId, {
      module_price_id: selectedPriceId, quantity, due_days: dueDays, reason: reason.trim(),
      idempotency_key: "manual:" + tenantId + ":" + crypto.randomUUID(),
    }), "Invoice created using the approved catalog price.");
  };
  const checkout = () => {
    if (!tenantId || !selectedPrice?.external_price_ref) return setError("Select a tenant and a Stripe-backed price.");
    if (!window.confirm("Queue Stripe checkout for " + (tenant?.name || tenantId) + "? Access changes only after verified payment events.")) return;
    void act(() => platformApi.createCheckout(tenantId, {
      module_price_id: selectedPrice.id, idempotency_key: "checkout:" + tenantId + ":" + crypto.randomUUID(),
    }), "Checkout request queued. Review its result in Billing operations.");
  };
  const recordPayment = (invoice: PlatformBillingInvoice) => {
    if (!reason.trim() || !paymentReference.trim()) return setError("A reason and payment reference are required to record an offline payment.");
    if (!window.confirm("Confirm an independently verified offline payment for " + money(invoice.amount_cents, invoice.currency) + "?")) return;
    void act(() => platformApi.markInvoicePaid(invoice.id, reason.trim(), paymentReference.trim()), "Offline payment recorded with an audit trail.");
  };
  const voidInvoice = (invoice: PlatformBillingInvoice) => {
    if (!reason.trim()) return setError("Enter the reason before voiding.");
    if (!window.confirm("Void this unpaid invoice? The ledger charge will be reversed where present.")) return;
    void act(() => platformApi.voidInvoice(invoice.id, reason.trim()), "Unpaid invoice voided and audit logged.");
  };
  const downloadInvoice = (invoice: PlatformBillingInvoice) =>
    void act(async () => saveFile(await platformApi.invoiceDocument(invoice.id), (invoice.invoice_number || invoice.id) + ".pdf"), "Invoice PDF generated.");
  const exportRegister = () => {
    if (!tenantId) return setError("Select a tenant before exporting the billing register.");
    void act(async () => saveFile(await platformApi.exportTenantInvoices(tenantId, mode), "venspera-" + (tenant?.amo_code || "tenant") + "-invoices.csv"), "Tenant invoice register exported.");
  };
  const counts = overview.data?.counts ?? {};
  const invoiceCounts = overview.data?.invoices ?? {};
  const totalInvoices = invoices.data?.total || 0;

  return <PlatformShell title="Billing & Revenue Operations" subtitle="Commercial control centre · Accounts, payments, subscriptions and provider jobs"
    actions={<div className="platform-actions"><StatusBadge value={mode === "REAL" ? "LIVE COMMERCIAL DATA" : "DEMO DATA"} /><button className="platform-btn" onClick={refresh}>Refresh</button></div>}>
    {error ? <div role="alert" className="platform-error">{error}</div> : null}
    {notice ? <p role="status"><StatusBadge value="SUCCEEDED" /> {notice}</p> : null}
    {overview.error ? <ErrorState error={overview.error} retry={overview.reload} /> : null}

    <section className="platform-card" aria-label="Billing filters">
      <div className="platform-section-title">
        <div><h2>Workspace scope</h2><p>Choose a tenant from the register; no internal IDs need to be entered manually.</p></div>
        <Link className="platform-btn" to="/platform/tenants">Manage tenants</Link>
      </div>
      <div className="platform-toolbar">
        <label><span>Environment</span><select value={mode} onChange={(e) => { setMode(e.target.value as DataMode); selectTenant(""); }}>
          <option value="REAL">Production tenants</option><option value="DEMO">Demo tenants</option>
        </select></label>
        <label><span>Search accounts</span><input value={tenantSearch} placeholder="Company name or AMO code" onChange={(e) => setTenantSearch(e.target.value)} /></label>
        <label><span>Account</span><select aria-label="Billing tenant" value={tenantId} onChange={(e) => selectTenant(e.target.value)}>
          <option value="">All accounts</option>
          {shownTenants.map((t) => <option key={t.id} value={t.id}>{t.name} · {t.amo_code}</option>)}
        </select></label>
      </div>
      {tenant ? <div className="platform-actions">
        <strong>{tenant.name}</strong><StatusBadge value={tenant.access_state} />
        <span>{tenant.subscription?.sku_code || "No licensed plan"}</span>
        <span>Renewal: {date(tenant.subscription?.current_period_end)}</span>
        <Link className="platform-btn" to={"/platform/tenants?q=" + encodeURIComponent(tenant.amo_code)}>Open account</Link>
      </div> : null}
    </section>

    <section className="platform-grid">
      <MetricCard label="Monthly recurring revenue" value={summary.data?.platform_mrr != null ? String(summary.data.platform_mrr) + " minor units" : "Not available"} caption="Legacy rollups do not identify currency; do not treat mixed currencies as USD" />
      <MetricCard label="Annual recurring revenue" value={summary.data?.platform_arr != null ? String(summary.data.platform_arr) + " minor units" : "Not available"} caption="Currency breakdown required for reliable revenue reporting" />
      <MetricCard label="Outstanding receivables" value={currencyTotals(overview.data?.invoice_currencies)} caption="Unpaid invoices, separated by currency" tone="amber" />
      <MetricCard label="Overdue invoices" value={String(invoiceCounts.OVERDUE ?? 0)} tone="red" />
      <MetricCard label="Active accounts" value={String(counts.ACTIVE ?? 0)} tone="green" />
      <MetricCard label="Trials" value={String(counts.TRIALING ?? 0)} tone="purple" />
    </section>

    <div className="platform-toolbar" role="tablist" aria-label="Billing workspaces">
      {(Object.keys(tabNames) as Section[]).map((item) =>
        <button key={item} role="tab" aria-selected={tab === item}
          className={"platform-btn " + (tab === item ? "primary" : "")} onClick={() => setTab(item)}>{tabNames[item]}</button>)}
    </div>

    {tab === "overview" ? <section className="platform-card">
      <div className="platform-section-title"><div><h2>Account health & collection queue</h2><p>Overdue invoices and restricted tenants are prioritized for follow-up.</p></div>
        <button className="platform-btn" disabled={busy || !reason.trim()} onClick={() => {
          if (!window.confirm("Run the billing period maintenance process?")) return;
          void act(() => platformApi.runBillingMaintenance(reason), "Billing maintenance completed.");
        }}>Run billing maintenance</button>
      </div>
      <p>Any maintenance run must include a reason in the action log below.</p>
      {tenants.length ? <DataTable><thead><tr><th>Tenant</th><th>Access</th><th>Plan</th><th>Unpaid amount</th><th>Overdue</th><th>Next period</th><th></th></tr></thead>
        <tbody>{[...tenants].sort((a,b) => b.overdue_invoice_count - a.overdue_invoice_count).map((t: PlatformBillingTenant) =>
          <tr key={t.id}><td><strong>{t.name}</strong><br /><small>{t.amo_code}</small></td>
          <td><StatusBadge value={t.access_state} /></td><td>{t.subscription?.sku_code || "Not subscribed"}</td>
          <td>{currencyTotals(t.invoice_currencies)}</td><td>{t.overdue_invoice_count}</td>
          <td>{date(t.subscription?.current_period_end)}</td>
          <td><button className="platform-btn" onClick={() => { selectTenant(t.id); setTab("invoices"); }}>Review invoices</button></td></tr>)}
        </tbody></DataTable> : <EmptyState label="No tenant accounts in the selected environment." />}
    </section> : null}

    {tab === "invoices" ? <>
      <section className="platform-card">
        <div className="platform-section-title"><div><h2>Invoice register & payment review</h2><p>Only verified offline payments should be entered manually. Stripe payments are handled by signed webhooks.</p></div>
          <button disabled={!tenantId || busy} onClick={exportRegister} className="platform-btn">Export tenant CSV</button></div>
        <div className="platform-toolbar">
          <label><span>Search</span><input value={invoiceSearch} onChange={(e) => { setInvoiceSearch(e.target.value); setInvoiceOffset(0); }} placeholder="Tenant or invoice description" /></label>
          <label><span>Status</span><select value={invoiceStatus} onChange={(e) => { setInvoiceStatus(e.target.value); setInvoiceOffset(0); }}>
            <option value="">All statuses</option><option value="PENDING">Pending</option><option value="OVERDUE">Overdue</option>
            <option value="PAID">Paid</option><option value="VOID">Voided</option>
          </select></label>
        </div>
        {invoices.error ? <ErrorState error={invoices.error} retry={invoices.reload} /> : null}
        {invoices.loading && !invoices.data ? <p role="status">Loading invoices…</p> : null}
        {invoices.data?.items?.length ? <DataTable><thead><tr><th>Invoice</th><th>Account</th><th>Amount</th><th>Status</th><th>Due</th><th>Actions</th></tr></thead>
          <tbody>{invoices.data.items.map((inv) =>
            <tr key={inv.id}><td><button className="platform-btn" onClick={() => setSelectedInvoiceId(selectedInvoiceId === inv.id ? "" : inv.id)}>{inv.invoice_number || inv.id.slice(0,8)}</button></td>
              <td>{tenantName(inv.amo_id)}</td><td>{money(inv.amount_cents, inv.currency)}</td>
              <td><StatusBadge value={inv.status === "PENDING" && inv.due_at && Date.parse(inv.due_at) < Date.now() ? "OVERDUE" : inv.status} /></td>
              <td>{date(inv.due_at)}</td>
              <td><div className="platform-actions"><button disabled={busy} className="platform-btn" onClick={() => downloadInvoice(inv)}>PDF</button>
                {inv.status === "PENDING" ? <><button className="platform-btn" disabled={busy} onClick={() => recordPayment(inv)}>Record payment</button>
                  <button className="platform-btn danger" disabled={busy} onClick={() => voidInvoice(inv)}>Void</button></> : null}
              </div></td></tr>)}</tbody></DataTable> : <EmptyState label="No invoices match the current filters." />}
        <div className="platform-actions"><button className="platform-btn" disabled={invoiceOffset === 0} onClick={() => setInvoiceOffset(Math.max(0,invoiceOffset-PAGE_SIZE))}>Previous</button>
          <span>{totalInvoices ? invoiceOffset+1 : 0}–{Math.min(totalInvoices, invoiceOffset+PAGE_SIZE)} of {totalInvoices}</span>
          <button className="platform-btn" disabled={invoiceOffset+PAGE_SIZE >= totalInvoices} onClick={() => setInvoiceOffset(invoiceOffset+PAGE_SIZE)}>Next</button></div>
        {selectedInvoice ? <div className="platform-card"><h3>Invoice details</h3><p><strong>{selectedInvoice.invoice_number}</strong> · {tenantName(selectedInvoice.amo_id)} · {money(selectedInvoice.amount_cents, selectedInvoice.currency)}</p>
          <p>Issued {date(selectedInvoice.issued_at)} · Due {date(selectedInvoice.due_at)} · Paid {date(selectedInvoice.paid_at)}</p>
          <p>{selectedInvoice.description || "No description entered"}</p>
          <button className="platform-btn" onClick={() => void act(async () => {
            const result = await platformApi.invoiceDetail(selectedInvoice.id); setNotice("Invoice " + (result.invoice_number || result.id) + " verified against the ledger.");
          }, "Invoice checked.")}>Check current invoice status</button></div> : null}
      </section>
      <section className="platform-two">
        <div className="platform-card"><h2>Create catalog-priced invoice</h2>
          <p>Select the account above, then choose the agreed price. The server calculates tax and prevents duplicate submissions.</p>
          <div className="platform-form">
            <label><span>Price</span><select value={selectedPriceId} onChange={(e) => setSelectedPriceId(e.target.value)}><option value="">Choose price</option>{prices.data?.items?.filter((price) => price.is_active).map((price) =>
              <option key={price.id} value={price.id}>{price.module_code} · {price.plan_code} · {price.billing_term} · {money(price.amount_cents,price.currency)}</option>)}</select></label>
            <label><span>Quantity</span><input type="number" min={1} value={quantity} onChange={(e) => setQuantity(Number(e.target.value))} /></label>
            <label><span>Days to pay</span><input type="number" min={0} max={365} value={dueDays} onChange={(e) => setDueDays(Number(e.target.value))} /></label>
            <div className="platform-actions">
              <button className="platform-btn primary" disabled={busy || !tenantId} onClick={makeInvoice}>Issue invoice</button>
              <button className="platform-btn" disabled={busy || !tenantId || !selectedPrice?.external_price_ref} onClick={checkout}>Queue Stripe checkout</button>
            </div>
          </div>
        </div>
        <div className="platform-card"><h2>Payment evidence & authorization</h2><p>These details are mandatory for manual payment recording, invoice voids and other sensitive actions.</p>
          <div className="platform-form">
            <label><span>Operator justification</span><textarea rows={3} value={reason} onChange={(e) => setReason(e.target.value)} placeholder="Reason or approved ticket reference" /></label>
            <label><span>External payment reference</span><input value={paymentReference} onChange={(e) => setPaymentReference(e.target.value)} placeholder="Bank transfer / M-Pesa receipt" /></label>
          </div>
          <small>Payment and invoice operations are recorded against your platform superuser account. Do not enter customer card data.</small>
        </div>
      </section>
    </> : null}

    {tab === "pricing" ? <section className="platform-two">
      <div className="platform-card"><h2>{priceEditId ? "Edit catalog price" : "Create catalog price"}</h2>
        <PriceEditor price={priceForm} setPrice={setPriceForm} save={savePrice} busy={busy} editing={!!priceEditId}
          cancel={() => { setPriceEditId(""); setPriceForm(blankPrice); }} />
        <label><span>Change justification</span><textarea value={reason} onChange={(e) => setReason(e.target.value)} /></label>
      </div>
      <div className="platform-card"><h2>Price register</h2>
        {prices.error ? <ErrorState error={prices.error} retry={prices.reload} /> : null}
        {prices.data?.items?.length ? <DataTable><thead><tr><th>Module / plan</th><th>Price</th><th>Status</th><th></th></tr></thead>
          <tbody>{prices.data.items.map((price) => <tr key={price.id}><td><strong>{price.module_code}</strong><br /><small>{price.plan_code} · {price.billing_term}</small></td>
            <td>{money(price.amount_cents, price.currency)}<br /><small>{(price.tax_rate_bps/100).toFixed(2)}% tax</small></td>
            <td><StatusBadge value={price.is_active ? "ACTIVE" : "INACTIVE"} /></td>
            <td><div className="platform-actions"><button className="platform-btn" onClick={() => editPrice(price)}>Edit</button>
              <button className="platform-btn" disabled={busy || !reason.trim()} onClick={() => {
                if (!window.confirm((price.is_active ? "Deactivate" : "Reactivate") + " this catalog price?")) return;
                void act(() => platformApi.updateModulePrice(price.id, { is_active: !price.is_active, reason }), "Price availability changed.");
              }}>{price.is_active ? "Deactivate" : "Activate"}</button></div></td></tr>)}</tbody>
        </DataTable> : <EmptyState label="No prices in the catalog." />}
      </div>
    </section> : null}

    {tab === "subscriptions" ? <section className="platform-two">
      <div className="platform-card">
        <h2>Tenant license & access</h2>
        {tenant ? <><p><strong>{tenant.name}</strong></p><p><StatusBadge value={tenant.access_state} /> {tenant.lock_reason || ""}</p>
          <p>Commercial plan: {tenant.subscription?.sku_code || "Not assigned"} · Period end: {date(tenant.subscription?.current_period_end)}</p>
          <p>Pending charges: {currencyTotals(tenant.invoice_currencies)} · Overdue: {tenant.overdue_invoice_count}</p>
          <div className="platform-actions">
            <button className="platform-btn" disabled={busy || !reason.trim()} onClick={() => {
              if (!window.confirm("Lock this tenant to read-only access?")) return;
              void act(() => platformApi.tenantAction(tenant.id, "lock", { reason }), "Tenant placed in read-only mode.");
            }}>Lock billing access</button>
            <button className="platform-btn" disabled={busy || !reason.trim()} onClick={() => {
              if (!window.confirm("Unlock this tenant after confirming payment and compliance?")) return;
              void act(() => platformApi.tenantAction(tenant.id, "unlock", { reason }), "Tenant access unlocked.");
            }}>Unlock billing access</button>
          </div>
        </> : <EmptyState label="Select an account above to inspect subscription details." />}
        <label><span>Reason for access changes</span><textarea value={reason} onChange={(e) => setReason(e.target.value)} /></label>
        <p><Link to="/platform/tenants">Open tenant lifecycle and user governance</Link></p>
      </div>
      <div className="platform-card"><h2>Module entitlement management</h2>
        {!tenantId ? <EmptyState label="Select a tenant to manage subscribed modules." /> : null}
        {modules.error ? <ErrorState error={modules.error} retry={modules.reload} /> : null}
        {tenantId ? <><DataTable><thead><tr><th>Module</th><th>Status</th></tr></thead><tbody>
          {catalog.data?.items?.map((item) => {
            const row = modules.data?.items?.find((m) => m.module_code === item.code);
            const current = moduleDrafts[item.code] || row?.status || "DISABLED";
            return <tr key={item.code}><td>{item.label}<br /><small>{item.category}</small></td><td>
              <select value={current} aria-label={"Status for " + item.label} onChange={(e) => setModuleDrafts((draft) => ({ ...draft, [item.code]: e.target.value }))}>
                <option value="ENABLED">Enabled</option><option value="TRIAL">Trial</option>
                <option value="SUSPENDED">Suspended</option><option value="DISABLED">Disabled</option>
              </select></td></tr>;
          })}</tbody></DataTable>
          <button className="platform-btn primary" disabled={busy || !Object.keys(moduleDrafts).length || !reason.trim()} onClick={saveModules}>Apply module changes</button>
          <small>Module activation is not a substitute for a paid subscription or a signed Stripe webhook.</small></> : null}
      </div>
    </section> : null}

    {tab === "jobs" ? <section className="platform-card"><div className="platform-section-title"><div><h2>Billing provider job queue</h2><p>Checkout, invoice processing and fiscalization jobs are managed here.</p></div><button className="platform-btn" onClick={jobs.reload}>Refresh jobs</button></div>
      {jobs.error ? <ErrorState error={jobs.error} retry={jobs.reload} /> : null}
      {jobs.data?.items?.length ? <DataTable><thead><tr><th>Created</th><th>Operation</th><th>Account</th><th>Status</th><th>Attempts</th><th>Result</th><th>Actions</th></tr></thead>
        <tbody>{jobs.data.items.map((job) => <tr key={job.id}><td>{date(job.created_at)}</td><td><strong>{job.job_type.replaceAll("_"," ")}</strong><br /><small>{job.id.slice(0,8)}</small></td>
          <td>{job.tenant_id ? tenantName(job.tenant_id) : "Platform"}</td><td><StatusBadge value={job.status} /></td>
          <td>{job.attempt_count}/{job.max_attempts}</td><td>{job.last_error || (job.result ? JSON.stringify(job.result).slice(0,140) : "—")}</td>
          <td><div className="platform-actions">
            {["FAILED","RETRY"].includes(job.status) ? <button className="platform-btn" disabled={busy} onClick={() => void act(() => platformApi.retrySaasJob(job.id), "Billing job queued for retry.")}>Retry</button> : null}
            {["PENDING","RETRY"].includes(job.status) ? <button className="platform-btn danger" disabled={busy || !reason.trim()} onClick={() => {
              if (!window.confirm("Cancel this pending job?")) return;
              void act(() => platformApi.cancelSaasJob(job.id, reason), "Job cancellation recorded.");
            }}>Cancel</button> : null}
          </div></td></tr>)}</tbody></DataTable> : <EmptyState label="No billing jobs for the selected scope." />}
      <label><span>Reason for cancellations</span><textarea value={reason} onChange={(e) => setReason(e.target.value)} /></label>
      <p><Link to="/platform/integrations?tab=providers">Configure payment and tax providers</Link></p>
    </section> : null}
  </PlatformShell>;
}
