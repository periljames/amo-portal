import React, { useEffect, useMemo, useState } from "react";

import { commercialApi } from "../../services/commercialControl";
import {
  fetchPlatformModuleCatalog,
  fetchTenantCommercialCatalog,
  updatePlatformModuleDefinition,
  updateTenantModuleOffer,
  type CommercialModule,
} from "../../services/moduleCommerce";
import {
  platformApi,
  type PlatformTenant,
  type SaaSModulePrice,
} from "../../services/platformControl";
import {
  DataTable,
  EmptyState,
  ErrorState,
  MetricCard,
  PlatformShell,
  StatusBadge,
} from "./components/PlatformShared";
import { usePlatformData } from "./components/usePlatformData";

const PAGE_SIZE = 25;

const money = (cents?: number, currency = "USD") => {
  try {
    return new Intl.NumberFormat(undefined, { style: "currency", currency }).format((cents ?? 0) / 100);
  } catch {
    return `${currency} ${((cents ?? 0) / 100).toFixed(2)}`;
  }
};

const currencyBuckets = (values?: Record<string, number>) => {
  const rows = Object.entries(values ?? {}).sort(([left], [right]) => left.localeCompare(right));
  return rows.length ? rows.map(([currency, cents]) => money(cents, currency)).join(" · ") : "—";
};

const countBuckets = (values?: Record<string, number>) => {
  const rows = Object.entries(values ?? {}).sort(([left], [right]) => left.localeCompare(right));
  return rows.length ? rows.map(([currency, count]) => `${currency} ${count}`).join(" · ") : "No overdue invoices";
};

const list = (value: string) => value.split(",").map((item) => item.trim()).filter(Boolean);
const amountToCents = (value: string) => Math.max(0, Math.round(Number(value || 0) * 100));
const percentToBps = (value: string) => Math.max(0, Math.min(10000, Math.round(Number(value || 0) * 100)));
const record = (value: unknown): Record<string, unknown> => value && typeof value === "object" ? value as Record<string, unknown> : {};
const text = (value: unknown) => value === null || value === undefined ? "" : String(value);
const numberValue = (value: unknown) => Number(value || 0);

const emptyModuleForm = {
  code: "",
  name: "",
  description: "",
  kind: "STANDALONE",
  customer_selectable: true,
  hard_requires: "",
  included_modules: "",
  reason: "Commercial module catalog update",
};

export default function PlatformBillingPage() {
  const [invoiceOffset, setInvoiceOffset] = useState(0);
  const [notice, setNotice] = useState<string | null>(null);
  const [error, setError] = useState<string | null>(null);

  const [moduleForm, setModuleForm] = useState(emptyModuleForm);
  const [savingModule, setSavingModule] = useState(false);

  const [priceForm, setPriceForm] = useState({
    module_code: "quality",
    plan_code: "STANDARD",
    billing_term: "MONTHLY",
    amount: "0",
    currency: "KES",
    trial_days: "0",
    tax_rate: "0",
    external_price_ref: "",
  });

  const [tenantId, setTenantId] = useState("");
  const [tenantModuleCode, setTenantModuleCode] = useState("");
  const [tenantBasePriceId, setTenantBasePriceId] = useState("");
  const [offerForm, setOfferForm] = useState({
    amount: "0",
    currency: "KES",
    billing_term: "MONTHLY",
    tax_rate: "0",
    trial_days: "0",
    customer_selectable: true,
    valid_until: "",
    reason: "Tenant-specific commercial terms",
  });
  const [savingOffer, setSavingOffer] = useState(false);

  const [invoiceTenantId, setInvoiceTenantId] = useState("");
  const [invoicePriceId, setInvoicePriceId] = useState("");
  const [quantity, setQuantity] = useState(1);
  const [dueDays, setDueDays] = useState(7);
  const [operationReason, setOperationReason] = useState("Verified platform billing operation");
  const [offlineReference, setOfflineReference] = useState("");
  const [mpesaPhone, setMpesaPhone] = useState("");

  const summary = usePlatformData(() => platformApi.billingSummary("REAL"), []);
  const commercial = usePlatformData(() => commercialApi.summary("REAL"), [], { pollMs: 15_000 });
  const modules = usePlatformData(() => fetchPlatformModuleCatalog(true), [], { pollMs: 0 });
  const tenants = usePlatformData(() => platformApi.tenants({ data_mode: "REAL", limit: 250, offset: 0 }), [], { pollMs: 30_000 });
  const prices = usePlatformData(() => platformApi.modulePrices({ include_inactive: true, limit: 500 }), [], { pollMs: 30_000 });
  const invoices = usePlatformData(
    () => platformApi.invoices({ data_mode: "REAL", limit: PAGE_SIZE, offset: invoiceOffset }),
    [invoiceOffset],
    { pollMs: 15_000 },
  );
  const jobs = usePlatformData(() => platformApi.saasJobs({ queue_name: "billing", limit: 40 }), [], { pollMs: 5_000 });
  const tenantCatalog = usePlatformData(
    () => tenantId
      ? fetchTenantCommercialCatalog(tenantId)
      : Promise.resolve({ items: [] as CommercialModule[], active_modules: [] as string[] }),
    [tenantId],
    { pollMs: 0 },
  );

  const moduleItems = modules.data?.items ?? [];
  const tenantItems = tenants.data?.items ?? [];
  const priceItems = prices.data?.items ?? [];
  const selectedInvoicePrice = priceItems.find((row) => row.id === invoicePriceId) ?? null;
  const tenantModule = tenantCatalog.data?.items?.find((row) => row.code === tenantModuleCode) ?? null;
  const tenantModulePrices = priceItems.filter((row) => row.module_code === tenantModuleCode && row.is_active);

  useEffect(() => {
    if (!tenantId && tenantItems.length) {
      setTenantId(tenantItems[0].id);
      setInvoiceTenantId(tenantItems[0].id);
    }
  }, [tenantId, tenantItems]);

  useEffect(() => {
    if (!tenantModuleCode && tenantCatalog.data?.items?.length) {
      setTenantModuleCode(tenantCatalog.data.items[0].code);
    }
  }, [tenantCatalog.data, tenantModuleCode]);

  const reloadAll = () => {
    summary.reload();
    commercial.reload();
    modules.reload();
    tenants.reload();
    prices.reload();
    invoices.reload();
    jobs.reload();
    tenantCatalog.reload();
  };

  const run = async (action: () => Promise<unknown>, success: string) => {
    setError(null);
    setNotice(null);
    try {
      await action();
      setNotice(success);
      reloadAll();
    } catch (caught) {
      setError(caught instanceof Error ? caught.message : String(caught));
    }
  };

  const editModule = (item: CommercialModule) => {
    setModuleForm({
      code: item.code,
      name: item.name,
      description: item.description || "",
      kind: item.kind,
      customer_selectable: item.customer_selectable,
      hard_requires: (item.hard_requires || []).join(", "),
      included_modules: (item.included_modules || []).join(", "),
      reason: "Commercial module catalog update",
    });
  };

  const saveModule = async () => {
    if (!moduleForm.code.trim() || !moduleForm.name.trim()) {
      setError("Module code and name are required.");
      return;
    }
    setSavingModule(true);
    setError(null);
    try {
      const updated = await updatePlatformModuleDefinition(moduleForm.code.trim(), {
        name: moduleForm.name.trim(),
        description: moduleForm.description.trim() || null,
        kind: moduleForm.kind,
        customer_selectable: moduleForm.customer_selectable,
        hard_requires: list(moduleForm.hard_requires),
        included_modules: list(moduleForm.included_modules),
        reason: moduleForm.reason.trim() || "Commercial module catalog update",
      });
      setNotice(`${updated.name} catalog definition saved.`);
      editModule(updated);
      modules.reload();
      tenantCatalog.reload();
    } catch (caught) {
      setError(caught instanceof Error ? caught.message : String(caught));
    } finally {
      setSavingModule(false);
    }
  };

  const createPrice = () => run(
    () => platformApi.createModulePrice({
      module_code: priceForm.module_code,
      plan_code: priceForm.plan_code.trim().toUpperCase() || "STANDARD",
      billing_term: priceForm.billing_term,
      amount_cents: amountToCents(priceForm.amount),
      currency: priceForm.currency.trim().toUpperCase(),
      trial_days: Math.max(0, Number(priceForm.trial_days || 0)),
      tax_rate_bps: percentToBps(priceForm.tax_rate),
      external_price_ref: priceForm.external_price_ref.trim() || null,
      is_active: true,
      reason: "Global module price created by platform superuser",
    }),
    "Global module price saved.",
  );

  const selectBasePrice = (priceId: string) => {
    setTenantBasePriceId(priceId);
    const selected = priceItems.find((row) => row.id === priceId);
    if (!selected) return;
    setOfferForm((current) => ({
      ...current,
      amount: (selected.amount_cents / 100).toFixed(2),
      currency: selected.currency,
      billing_term: selected.billing_term,
      tax_rate: (selected.tax_rate_bps / 100).toFixed(2),
      trial_days: String(selected.trial_days || 0),
    }));
  };

  const saveTenantOffer = async () => {
    if (!tenantId || !tenantModuleCode) {
      setError("Select a tenant and module first.");
      return;
    }
    setSavingOffer(true);
    setError(null);
    try {
      await updateTenantModuleOffer(tenantId, tenantModuleCode, {
        base_price_id: tenantBasePriceId || null,
        amount_cents: amountToCents(offerForm.amount),
        currency: offerForm.currency.trim().toUpperCase(),
        billing_term: offerForm.billing_term,
        tax_rate_bps: percentToBps(offerForm.tax_rate),
        trial_days: Math.max(0, Number(offerForm.trial_days || 0)),
        customer_selectable: offerForm.customer_selectable,
        valid_until: offerForm.valid_until ? new Date(`${offerForm.valid_until}T23:59:59Z`).toISOString() : null,
        reason: offerForm.reason.trim() || "Tenant-specific commercial terms",
      });
      setNotice("Tenant-specific module terms saved. They affect offers only and do not grant access until verified settlement.");
      tenantCatalog.reload();
    } catch (caught) {
      setError(caught instanceof Error ? caught.message : String(caught));
    } finally {
      setSavingOffer(false);
    }
  };

  const createManualInvoice = () => {
    if (!invoiceTenantId || !invoicePriceId) {
      setError("Select a tenant and module price before creating an invoice.");
      return;
    }
    void run(
      () => platformApi.createManualInvoice(invoiceTenantId, {
        module_price_id: invoicePriceId,
        quantity,
        due_days: dueDays,
        reason: operationReason,
        idempotency_key: `manual:${invoiceTenantId}:${invoicePriceId}:${Date.now()}`,
      }),
      "Invoice created from the server-side price catalog.",
    );
  };

  const createStripeCheckout = () => {
    if (!invoiceTenantId || !invoicePriceId || !selectedInvoicePrice?.external_price_ref) {
      setError("Choose a tenant and a module price with a configured Stripe Price ID.");
      return;
    }
    void run(
      () => platformApi.createCheckout(invoiceTenantId, {
        module_price_id: invoicePriceId,
        idempotency_key: `stripe:${invoiceTenantId}:${invoicePriceId}:${Date.now()}`,
      }),
      "Hosted Stripe checkout queued. Module access remains unchanged until Stripe verifies the subscription/payment event.",
    );
  };

  const collectInvoice = (invoiceId: string, paymentProvider: "paystack" | "mpesa_daraja") => {
    void run(
      () => commercialApi.startInvoicePayment(invoiceId, paymentProvider, {
        phone: paymentProvider === "mpesa_daraja" ? mpesaPhone.trim() || undefined : undefined,
      }),
      paymentProvider === "paystack"
        ? "Paystack hosted checkout queued. The customer should use the authorization URL from the successful billing job."
        : "M-PESA STK Push queued. Settlement requires callback plus server-side verification.",
    );
  };

  const settleOffline = (invoiceId: string) => {
    if (!offlineReference.trim()) {
      setError("Enter the bank/offline payment reference before recording settlement.");
      return;
    }
    void run(
      () => commercialApi.recordOfflinePayment(invoiceId, offlineReference.trim(), operationReason),
      "Referenced offline settlement recorded in the billing subledger.",
    );
  };

  const connectQuickBooks = async () => {
    setError(null);
    try {
      const response = await commercialApi.quickBooksAuthorize();
      if (!response.authorization_url) throw new Error("QuickBooks authorization URL was not returned.");
      window.location.assign(response.authorization_url);
    } catch (caught) {
      setError(caught instanceof Error ? caught.message : String(caught));
    }
  };

  const summaryData = summary.data ?? {};
  const commercialData = commercial.data;
  const providerStatuses = commercialData?.provider_statuses ?? {};
  const invoiceTotal = invoices.data?.total ?? 0;

  return (
    <PlatformShell
      title="Commercial Control & Billing"
      subtitle="Govern modules, bundles, prices, tenant-specific terms, invoice settlement, tax fiscalization and accounting from one authoritative workspace."
      actions={<button className="platform-btn" onClick={reloadAll}>Refresh</button>}
    >
      {summary.error ? <ErrorState error={summary.error} retry={summary.reload} /> : null}
      {commercial.error ? <ErrorState error={commercial.error} retry={commercial.reload} /> : null}
      {error ? <div className="platform-error">{error}</div> : null}
      {notice ? <p><StatusBadge value="PENDING" /> {notice}</p> : null}

      <section className="platform-grid">
        <MetricCard label="Active subscriptions" value={String(summaryData.active_subscriptions ?? 0)} caption={`${summaryData.trial_subscriptions ?? 0} trials`} tone="blue" mark="SU" />
        <MetricCard label="Outstanding A/R" value={currencyBuckets(commercialData?.outstanding_ar_by_currency)} caption={countBuckets(commercialData?.overdue_invoice_count_by_currency)} tone="amber" mark="AR" />
        <MetricCard label="Collected 30d" value={currencyBuckets(commercialData?.collected_30d_by_currency)} caption="Verified paid portal invoices" tone="green" mark="CA" />
        <MetricCard label="Invoiced 30d" value={currencyBuckets(commercialData?.invoiced_30d_by_currency)} caption="Currencies are never blended" tone="blue" mark="IV" />
        <MetricCard label="Commercial modules" value={String(moduleItems.length)} caption={`${moduleItems.filter((item) => item.customer_selectable).length} customer selectable`} tone="purple" mark="MO" />
        <MetricCard label="Failed payment jobs" value={String(commercialData?.failed_payment_jobs_30d ?? 0)} caption="Last 30 days" tone={(commercialData?.failed_payment_jobs_30d ?? 0) ? "red" : "green"} mark="FP" />
      </section>

      <section className="platform-card">
        <h2>Payment-card security boundary</h2>
        <p>AMO Portal does not collect or store PAN/card numbers, CVV/CVC, PIN/PIN blocks, magnetic-stripe/track data or bank authentication credentials. Card entry occurs on Paystack/Stripe hosted or provider-controlled PCI checkout. The portal keeps business records only: invoice identity, opaque provider references, verified settlement evidence and provider-supplied masked metadata when operationally required.</p>
        <p><StatusBadge value={providerStatuses.paystack ?? "PAYSTACK NOT_CONFIGURED"} /> <StatusBadge value={providerStatuses.mpesa_daraja ?? "MPESA NOT_CONFIGURED"} /> <StatusBadge value={providerStatuses.stripe ?? "STRIPE NOT_CONFIGURED"} /></p>
      </section>

      <section className="platform-two">
        <div className="platform-card">
          <div className="platform-actions" style={{ justifyContent: "space-between" }}><h2>Module definition</h2><button className="platform-btn" onClick={() => setModuleForm(emptyModuleForm)}>New catalog entry</button></div>
          <div className="platform-form">
            <label><span>Module code</span><input value={moduleForm.code} onChange={(event) => setModuleForm({ ...moduleForm, code: event.target.value.toLowerCase().replace(/[^a-z0-9_]+/g, "_") })} placeholder="custom_capability" /></label>
            <label><span>Name</span><input value={moduleForm.name} onChange={(event) => setModuleForm({ ...moduleForm, name: event.target.value })} /></label>
            <label><span>Kind</span><select value={moduleForm.kind} onChange={(event) => setModuleForm({ ...moduleForm, kind: event.target.value })}><option>STANDALONE</option><option>ADD_ON</option><option>BUNDLE</option><option>PLATFORM_INCLUDED</option><option>CATALOG_ONLY</option></select></label>
            <label><span>Description</span><textarea value={moduleForm.description} onChange={(event) => setModuleForm({ ...moduleForm, description: event.target.value })} /></label>
            <label><span>Hard dependencies</span><input value={moduleForm.hard_requires} onChange={(event) => setModuleForm({ ...moduleForm, hard_requires: event.target.value })} placeholder="fleet, work" /></label>
            <label><span>Bundle members</span><input value={moduleForm.included_modules} onChange={(event) => setModuleForm({ ...moduleForm, included_modules: event.target.value })} placeholder="quality, training" disabled={moduleForm.kind !== "BUNDLE"} /></label>
            <label><span>Audit reason</span><input value={moduleForm.reason} onChange={(event) => setModuleForm({ ...moduleForm, reason: event.target.value })} /></label>
            <label><span><input type="checkbox" checked={moduleForm.customer_selectable} onChange={(event) => setModuleForm({ ...moduleForm, customer_selectable: event.target.checked })} /> Customer selectable</span></label>
            <button className="platform-btn primary" disabled={savingModule} onClick={() => void saveModule()}>{savingModule ? "Saving…" : "Save module definition"}</button>
          </div>
          <small>Unknown/custom capability codes are deliberately created as catalog-only until application code implements an enforceable entitlement boundary. Pricing a catalog entry never makes an unimplemented feature purchasable.</small>
        </div>

        <div className="platform-card">
          <h2>Global module price</h2>
          <div className="platform-form">
            <label><span>Module</span><select value={priceForm.module_code} onChange={(event) => setPriceForm({ ...priceForm, module_code: event.target.value })}>{moduleItems.map((item) => <option key={item.code} value={item.code}>{item.name} ({item.code})</option>)}</select></label>
            <label><span>Plan code</span><input value={priceForm.plan_code} onChange={(event) => setPriceForm({ ...priceForm, plan_code: event.target.value })} /></label>
            <label><span>Billing term</span><select value={priceForm.billing_term} onChange={(event) => setPriceForm({ ...priceForm, billing_term: event.target.value })}><option>MONTHLY</option><option>BI_ANNUAL</option><option>ANNUAL</option><option>ONE_TIME</option></select></label>
            <label><span>Amount</span><input type="number" min="0" step="0.01" value={priceForm.amount} onChange={(event) => setPriceForm({ ...priceForm, amount: event.target.value })} /></label>
            <label><span>Currency</span><input value={priceForm.currency} onChange={(event) => setPriceForm({ ...priceForm, currency: event.target.value.toUpperCase() })} /></label>
            <label><span>Tax rate %</span><input type="number" min="0" max="100" step="0.01" value={priceForm.tax_rate} onChange={(event) => setPriceForm({ ...priceForm, tax_rate: event.target.value })} /></label>
            <label><span>Trial days</span><input type="number" min="0" max="365" value={priceForm.trial_days} onChange={(event) => setPriceForm({ ...priceForm, trial_days: event.target.value })} /></label>
            <label><span>Stripe Price ID</span><input value={priceForm.external_price_ref} onChange={(event) => setPriceForm({ ...priceForm, external_price_ref: event.target.value })} placeholder="price_..." /></label>
            <button className="platform-btn primary" onClick={createPrice}>Create price</button>
          </div>
        </div>
      </section>

      <section className="platform-card">
        <h2>Commercial module register</h2>
        {modules.error ? <ErrorState error={modules.error} retry={modules.reload} /> : null}
        {moduleItems.length ? <DataTable><thead><tr><th>Module</th><th>Kind</th><th>Dependencies</th><th>Bundle contents</th><th>Implementation</th><th>Sale state</th><th>Action</th></tr></thead><tbody>{moduleItems.map((item) => <tr key={item.code}><td><strong>{item.name}</strong><br /><small>{item.code}</small></td><td>{item.kind}</td><td>{item.hard_requires?.join(", ") || "—"}</td><td>{item.included_modules?.join(", ") || "—"}</td><td><StatusBadge value={item.implemented ? "IMPLEMENTED" : "CATALOG_ONLY"} /></td><td><StatusBadge value={item.customer_selectable ? "CUSTOMER SELECTABLE" : "INTERNAL/DRAFT"} /></td><td><button className="platform-btn" onClick={() => editModule(item)}>Edit</button></td></tr>)}</tbody></DataTable> : <EmptyState label="No commercial modules are registered." />}
      </section>

      <section className="platform-two">
        <div className="platform-card">
          <h2>Tenant-specific commercial terms</h2>
          <div className="platform-form">
            <label><span>Tenant</span><select value={tenantId} onChange={(event) => { setTenantId(event.target.value); setTenantModuleCode(""); setTenantBasePriceId(""); }}><option value="">Select tenant</option>{tenantItems.map((tenant: PlatformTenant) => <option key={tenant.id} value={tenant.id}>{tenant.amo_code} — {tenant.name}</option>)}</select></label>
            <label><span>Module</span><select value={tenantModuleCode} onChange={(event) => { setTenantModuleCode(event.target.value); setTenantBasePriceId(""); }}><option value="">Select module</option>{tenantCatalog.data?.items?.map((item) => <option key={item.code} value={item.code}>{item.name} {item.is_active_for_tenant ? "· ACTIVE" : ""}</option>)}</select></label>
            <label><span>Base global price</span><select value={tenantBasePriceId} onChange={(event) => selectBasePrice(event.target.value)}><option value="">Custom terms / no base</option>{tenantModulePrices.map((price) => <option key={price.id} value={price.id}>{price.plan_code} · {price.billing_term} · {money(price.amount_cents, price.currency)}</option>)}</select></label>
            <label><span>Negotiated amount</span><input type="number" min="0" step="0.01" value={offerForm.amount} onChange={(event) => setOfferForm({ ...offerForm, amount: event.target.value })} /></label>
            <label><span>Currency</span><input value={offerForm.currency} onChange={(event) => setOfferForm({ ...offerForm, currency: event.target.value.toUpperCase() })} /></label>
            <label><span>Billing term</span><select value={offerForm.billing_term} onChange={(event) => setOfferForm({ ...offerForm, billing_term: event.target.value })}><option>MONTHLY</option><option>BI_ANNUAL</option><option>ANNUAL</option></select></label>
            <label><span>Tax rate %</span><input type="number" min="0" max="100" step="0.01" value={offerForm.tax_rate} onChange={(event) => setOfferForm({ ...offerForm, tax_rate: event.target.value })} /></label>
            <label><span>Trial days</span><input type="number" min="0" max="365" value={offerForm.trial_days} onChange={(event) => setOfferForm({ ...offerForm, trial_days: event.target.value })} /></label>
            <label><span>Offer valid through</span><input type="date" value={offerForm.valid_until} onChange={(event) => setOfferForm({ ...offerForm, valid_until: event.target.value })} /></label>
            <label><span>Reason / agreement reference</span><textarea value={offerForm.reason} onChange={(event) => setOfferForm({ ...offerForm, reason: event.target.value })} /></label>
            <label><span><input type="checkbox" checked={offerForm.customer_selectable} onChange={(event) => setOfferForm({ ...offerForm, customer_selectable: event.target.checked })} /> Make offer visible to tenant</span></label>
            <button className="platform-btn primary" disabled={savingOffer || !tenantId || !tenantModuleCode} onClick={() => void saveTenantOffer()}>{savingOffer ? "Saving…" : "Save tenant terms"}</button>
          </div>
          {tenantModule ? <p><StatusBadge value={tenantModule.is_active_for_tenant ? "ACTIVE" : "NOT SUBSCRIBED"} /> {tenantModule.missing_dependencies?.length ? `Requires: ${tenantModule.missing_dependencies.join(", ")}` : "Dependencies satisfied."}</p> : null}
          <small>A commercial offer does not enable a module. Verified settlement activates the enforceable capability/bundle and records the paid service period.</small>
        </div>

        <div className="platform-card">
          <h2>Invoice & provider action</h2>
          <div className="platform-form">
            <label><span>Tenant</span><select value={invoiceTenantId} onChange={(event) => setInvoiceTenantId(event.target.value)}><option value="">Select tenant</option>{tenantItems.map((tenant: PlatformTenant) => <option key={tenant.id} value={tenant.id}>{tenant.amo_code} — {tenant.name}</option>)}</select></label>
            <label><span>Module price</span><select value={invoicePriceId} onChange={(event) => setInvoicePriceId(event.target.value)}><option value="">Select price</option>{priceItems.filter((price) => price.is_active).map((price) => <option key={price.id} value={price.id}>{price.module_code} · {price.plan_code} · {price.billing_term} · {money(price.amount_cents, price.currency)}</option>)}</select></label>
            <label><span>Quantity</span><input type="number" min="1" value={quantity} onChange={(event) => setQuantity(Math.max(1, Number(event.target.value || 1)))} /></label>
            <label><span>Due days</span><input type="number" min="0" max="365" value={dueDays} onChange={(event) => setDueDays(Math.max(0, Number(event.target.value || 0)))} /></label>
            <label><span>Operation reason</span><textarea value={operationReason} onChange={(event) => setOperationReason(event.target.value)} /></label>
          </div>
          <div className="platform-actions"><button className="platform-btn primary" onClick={createManualInvoice}>Create invoice</button><button className="platform-btn" onClick={createStripeCheckout}>Hosted Stripe checkout</button></div>
          <small>Stripe checkout is available only when the selected price is mapped to a Stripe Price ID. It never activates access until verified provider events succeed.</small>
        </div>
      </section>

      <section className="platform-card">
        <h2>Global price register</h2>
        {prices.data?.items?.length ? <DataTable><thead><tr><th>Module</th><th>Plan</th><th>Term</th><th>Price</th><th>Tax</th><th>Trial</th><th>Stripe</th><th>Status</th><th>Action</th></tr></thead><tbody>{prices.data.items.map((price: SaaSModulePrice) => <tr key={price.id}><td>{price.module_code}</td><td>{price.plan_code}</td><td>{price.billing_term}</td><td>{money(price.amount_cents, price.currency)}</td><td>{(price.tax_rate_bps / 100).toFixed(2)}%</td><td>{price.trial_days}d</td><td>{price.external_price_ref || "—"}</td><td><StatusBadge value={price.is_active ? "ACTIVE" : "INACTIVE"} /></td><td>{price.is_active ? <button className="platform-btn" onClick={() => void run(() => platformApi.updateModulePrice(price.id, { is_active: false, reason: "Price retired by platform superuser" }), "Price retired; historical invoices remain unchanged.")}>Retire</button> : null}</td></tr>)}</tbody></DataTable> : <EmptyState label="No global module prices configured." />}
      </section>

      <section className="platform-two">
        <div className="platform-card">
          <h2>Collection controls</h2>
          <div className="platform-form"><label><span>M-PESA phone override</span><input value={mpesaPhone} onChange={(event) => setMpesaPhone(event.target.value)} placeholder="2547XXXXXXXX" /></label><label><span>Bank/offline reference</span><input value={offlineReference} onChange={(event) => setOfflineReference(event.target.value)} placeholder="Bank receipt / transfer reference" /></label></div>
          <p><StatusBadge value={providerStatuses.paystack ?? "PAYSTACK NOT_CONFIGURED"} /> <StatusBadge value={providerStatuses.mpesa_daraja ?? "MPESA NOT_CONFIGURED"} /></p>
          <small>Manual settlement requires a real external reference and reason and creates an auditable PAYMENT ledger entry. There is no generic unreferenced “mark paid” action.</small>
        </div>
        <div className="platform-card">
          <h2>Accounting & tax</h2>
          <p><StatusBadge value={providerStatuses.quickbooks_online ?? "QUICKBOOKS NOT_CONFIGURED"} /> <StatusBadge value={providerStatuses.etims_oscu ?? providerStatuses.etims_vscu ?? "ETIMS NOT_CONFIGURED"} /></p>
          <button className="platform-btn primary" onClick={() => void connectQuickBooks()}>Connect QuickBooks Online</button>
          <p><small>AMO Portal owns the subscription billing subledger. QuickBooks is the optional external GL boundary; eTIMS fiscalization is independent. Cross-currency writeback remains blocked until an explicit accounting policy exists.</small></p>
        </div>
      </section>

      <section className="platform-card">
        <div className="platform-actions" style={{ justifyContent: "space-between" }}><h2>Invoices</h2><span>{invoiceTotal} records</span></div>
        {invoices.error ? <ErrorState error={invoices.error} retry={invoices.reload} /> : null}
        {invoices.data?.items?.length ? <DataTable><thead><tr><th>Invoice</th><th>Tenant</th><th>Status</th><th>Amount</th><th>Due</th><th>Fiscal</th><th>Actions</th></tr></thead><tbody>{invoices.data.items.map((raw) => { const invoice = record(raw); const id = text(invoice.id); const currency = text(invoice.currency) || "USD"; const status = text(invoice.status); return <tr key={id}><td>{text(invoice.invoice_number) || id}</td><td>{text(invoice.amo_code) || text(invoice.tenant_name) || text(invoice.amo_id)}</td><td><StatusBadge value={status} /></td><td>{money(numberValue(invoice.total_cents ?? invoice.amount_cents), currency)}</td><td>{text(invoice.due_at) ? new Date(text(invoice.due_at)).toLocaleDateString() : "—"}</td><td><StatusBadge value={invoice.etims_status || "NOT FISCALIZED"} /></td><td><div className="platform-actions">{status === "PENDING" ? <><button className="platform-btn" onClick={() => collectInvoice(id, "paystack")}>Paystack</button><button className="platform-btn" onClick={() => collectInvoice(id, "mpesa_daraja")}>M-PESA</button><button className="platform-btn" onClick={() => settleOffline(id)}>Offline</button></> : null}<button className="platform-btn" onClick={() => void run(() => platformApi.fiscalizeInvoice(id, "etims_oscu"), "eTIMS fiscalization queued.")}>eTIMS</button><button className="platform-btn" onClick={() => void run(() => commercialApi.syncQuickBooks(id), "QuickBooks synchronization queued.")}>QuickBooks</button></div></td></tr>; })}</tbody></DataTable> : <EmptyState label="No invoices in this page." />}
        <div className="platform-actions"><button className="platform-btn" disabled={invoiceOffset === 0} onClick={() => setInvoiceOffset(Math.max(0, invoiceOffset - PAGE_SIZE))}>Previous</button><button className="platform-btn" disabled={invoiceOffset + PAGE_SIZE >= invoiceTotal} onClick={() => setInvoiceOffset(invoiceOffset + PAGE_SIZE)}>Next</button></div>
      </section>

      <section className="platform-card">
        <h2>Billing jobs</h2>
        {jobs.data?.items?.length ? <DataTable><thead><tr><th>Type</th><th>Tenant</th><th>Status</th><th>Attempts</th><th>Result</th></tr></thead><tbody>{jobs.data.items.map((job) => <tr key={job.id}><td>{job.job_type}</td><td>{job.tenant_id || "Platform"}</td><td><StatusBadge value={job.status} /></td><td>{job.attempt_count}/{job.max_attempts}</td><td>{job.last_error || (job.result ? "Result retained" : "—")}</td></tr>)}</tbody></DataTable> : <EmptyState label="No recent billing jobs." />}
      </section>
    </PlatformShell>
  );
}
