import React, { useMemo, useState } from "react";
import { useSearchParams } from "react-router-dom";

import {
  commercialApi,
  type CommercialInvoice,
  type PlatformDataMode,
  type PriceBookEntry,
} from "../../services/commercialControl";
import { platformApi } from "../../services/platformControl";
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

const TABS = ["overview", "modules", "plans", "price-books", "prices", "subscriptions", "invoices", "payments"] as const;
type BillingTab = (typeof TABS)[number];

type InvoiceLineDraft = {
  module_id: string;
  description: string;
  quantity: number;
  unit_amount: string;
  tax_rate: string;
};

const money = (cents = 0, currency = "USD") => new Intl.NumberFormat(undefined, { style: "currency", currency }).format(cents / 100);
const formatDate = (value?: string | null) => value ? new Date(value).toLocaleString() : "—";

function tabValue(value: string | null): BillingTab {
  return TABS.includes(value as BillingTab) ? value as BillingTab : "overview";
}

export default function PlatformBillingPage() {
  const [searchParams, setSearchParams] = useSearchParams();
  const dataMode = (searchParams.get("mode") === "DEMO" ? "DEMO" : "REAL") as PlatformDataMode;
  const activeTab = tabValue(searchParams.get("tab"));
  const [notice, setNotice] = useState<string | null>(null);
  const [actionError, setActionError] = useState<string | null>(null);
  const [drawer, setDrawer] = useState<"module" | "plan" | "book" | "price" | "invoice" | "payment" | null>(null);
  const [selectedInvoice, setSelectedInvoice] = useState<CommercialInvoice | null>(null);
  const [reason, setReason] = useState("Commercial administration from superuser console");
  const [moduleForm, setModuleForm] = useState({ code: "", name: "", category: "GENERAL", description: "", route_prefix: "", sellable: true, trial_eligible: true, status: "ACTIVE", reason: "Create commercial module" });
  const [planForm, setPlanForm] = useState({ code: "", name: "", description: "", status: "ACTIVE", is_public: false, trial_days: 14, default_billing_term: "MONTHLY", module_ids: [] as string[], reason: "Create product plan" });
  const [bookForm, setBookForm] = useState({ code: "", name: "", currency: "USD", market: "", data_mode: dataMode as PlatformDataMode, status: "ACTIVE", tax_inclusive: false, reason: "Create price book" });
  const [priceForm, setPriceForm] = useState({ price_book_id: "", target_type: "PLAN", plan_id: "", module_id: "", billing_term: "MONTHLY", unit_amount: "0", included_quantity: 1, overage_amount: "", trial_days: 0, tax_rate: "0", effective_from: new Date().toISOString().slice(0, 16), external_product_ref: "", external_price_ref: "", status: "ACTIVE", reason: "Publish price version" });
  const [invoiceForm, setInvoiceForm] = useState({ tenant_id: "", currency: "USD", due_days: 14, description: "Commercial subscription services", reason: "Manual invoice", lines: [{ module_id: "", description: "Subscription service", quantity: 1, unit_amount: "0", tax_rate: "0" }] as InvoiceLineDraft[] });
  const [paymentForm, setPaymentForm] = useState({ amount: "0", provider: "MANUAL", external_reference: "", payment_method: "", notes: "", reason: "Record received payment" });

  const summary = usePlatformData(() => commercialApi.summary(dataMode), [dataMode], { pollMs: 20_000 });
  const catalog = usePlatformData(async () => {
    await commercialApi.bootstrap();
    const [modules, plans, books, prices] = await Promise.all([
      commercialApi.modules(true),
      commercialApi.plans(true),
      commercialApi.priceBooks(dataMode),
      commercialApi.prices(dataMode, true),
    ]);
    return { modules: modules.items, plans: plans.items, books: books.items, prices: prices.items };
  }, [dataMode], { pollMs: 60_000 });
  const subscriptions = usePlatformData(() => commercialApi.subscriptions(dataMode), [dataMode], { pollMs: 20_000 });
  const invoices = usePlatformData(() => commercialApi.invoices(dataMode, { limit: 150 }), [dataMode], { pollMs: 20_000 });
  const tenants = usePlatformData(() => platformApi.tenants({ data_mode: dataMode, limit: 200 }), [dataMode], { pollMs: 30_000 });

  const modules = catalog.data?.modules || [];
  const plans = catalog.data?.plans || [];
  const books = catalog.data?.books || [];
  const prices = catalog.data?.prices || [];
  const tenantRows = tenants.data?.items || [];
  const summaryData = summary.data;

  const setQuery = (patch: Record<string, string | null>) => {
    const next = new URLSearchParams(searchParams);
    Object.entries(patch).forEach(([key, value]) => value ? next.set(key, value) : next.delete(key));
    setSearchParams(next, { replace: true });
  };

  const refresh = () => {
    summary.reload(); catalog.reload(); subscriptions.reload(); invoices.reload(); tenants.reload();
  };

  const run = async (operation: () => Promise<unknown>, success: string) => {
    setActionError(null); setNotice(null);
    try {
      await operation();
      setNotice(success);
      refresh();
    } catch (error) {
      setActionError(error instanceof Error ? error.message : String(error));
      throw error;
    }
  };

  const saveModule = async () => {
    await run(() => commercialApi.createModule(moduleForm), "Commercial module saved.");
    setDrawer(null);
    setModuleForm((current) => ({ ...current, code: "", name: "", description: "", route_prefix: "" }));
  };

  const savePlan = async () => {
    await run(() => commercialApi.createPlan({
      ...planForm,
      modules: planForm.module_ids.map((module_id, index) => ({ module_id, included: true, sort_order: (index + 1) * 10 })),
    }), "Product plan saved.");
    setDrawer(null);
    setPlanForm((current) => ({ ...current, code: "", name: "", description: "", module_ids: [] }));
  };

  const saveBook = async () => {
    await run(() => commercialApi.createPriceBook({ ...bookForm, data_mode: dataMode }), "Price book saved.");
    setDrawer(null);
    setBookForm((current) => ({ ...current, code: "", name: "", market: "", data_mode: dataMode }));
  };

  const savePrice = async () => {
    const target = priceForm.target_type === "PLAN" ? { plan_id: priceForm.plan_id, module_id: null } : { plan_id: null, module_id: priceForm.module_id };
    await run(() => commercialApi.createPrice({
      ...target,
      price_book_id: priceForm.price_book_id,
      billing_term: priceForm.billing_term,
      unit_amount_cents: Math.round(Number(priceForm.unit_amount || 0) * 100),
      included_quantity: priceForm.included_quantity,
      overage_amount_cents: priceForm.overage_amount === "" ? null : Math.round(Number(priceForm.overage_amount) * 100),
      trial_days: priceForm.trial_days,
      tax_rate_bps: Math.round(Number(priceForm.tax_rate || 0) * 100),
      effective_from: new Date(priceForm.effective_from).toISOString(),
      external_product_ref: priceForm.external_product_ref || null,
      external_price_ref: priceForm.external_price_ref || null,
      status: priceForm.status,
      reason: priceForm.reason,
    }), "Price version published.");
    setDrawer(null);
  };

  const saveInvoice = async () => {
    if (!invoiceForm.tenant_id) throw new Error("Select a tenant.");
    const lines = invoiceForm.lines.map((line, index) => ({
      module_id: line.module_id || null,
      description: line.description,
      quantity: line.quantity,
      unit_amount_cents: Math.round(Number(line.unit_amount || 0) * 100),
      tax_rate_bps: Math.round(Number(line.tax_rate || 0) * 100),
      sort_order: (index + 1) * 10,
    }));
    await run(() => commercialApi.createInvoice(invoiceForm.tenant_id, {
      currency: invoiceForm.currency,
      due_days: invoiceForm.due_days,
      description: invoiceForm.description,
      reason: invoiceForm.reason,
      idempotency_key: `console:${invoiceForm.tenant_id}:${Date.now()}`,
      lines,
    }), "Invoice created with structured line items.");
    setDrawer(null);
  };

  const openPayment = (invoice: CommercialInvoice) => {
    setSelectedInvoice(invoice);
    setPaymentForm({ amount: String(invoice.balance_cents / 100), provider: "MANUAL", external_reference: "", payment_method: "", notes: "", reason: "Record received payment" });
    setDrawer("payment");
  };

  const savePayment = async () => {
    if (!selectedInvoice) return;
    await run(() => commercialApi.recordPayment(selectedInvoice.id, {
      amount_cents: Math.round(Number(paymentForm.amount || 0) * 100),
      provider: paymentForm.provider,
      external_reference: paymentForm.external_reference || null,
      payment_method: paymentForm.payment_method || null,
      notes: paymentForm.notes || null,
      reason: paymentForm.reason,
    }), "Payment transaction recorded and invoice balance recalculated.");
    setDrawer(null); setSelectedInvoice(null);
  };

  const revenueCurrencies = Object.entries(summaryData?.revenue_by_currency || {});
  const outstandingCurrencies = Object.entries(summaryData?.outstanding_by_currency || {});
  const activeSubscriptions = Number(summaryData?.subscriptions.ACTIVE || 0);
  const trialSubscriptions = Number(summaryData?.subscriptions.TRIALING || 0);
  const pastDueSubscriptions = Number(summaryData?.subscriptions.PAST_DUE || 0);

  const priceUsage = useMemo(() => {
    const used = new Map<string, number>();
    (subscriptions.data?.items || []).forEach((subscription) => subscription.items.forEach((item) => {
      if (item.price_entry_id) used.set(item.price_entry_id, (used.get(item.price_entry_id) || 0) + 1);
    }));
    return used;
  }, [subscriptions.data?.items]);

  return (
    <PlatformShell
      title="Commercial Control"
      subtitle="Canonical modules, plans, price books, versioned prices, subscriptions, structured invoices, payments and reconciliation."
      actions={<><div className="platform-mode-switch">{(["REAL", "DEMO"] as PlatformDataMode[]).map((mode) => <button key={mode} className={dataMode === mode ? "active" : ""} onClick={() => setQuery({ mode, tab: "overview" })}>{mode}</button>)}</div><button className="platform-btn" onClick={refresh}>Refresh</button></>}
    >
      {summary.error ? <ErrorState error={summary.error} retry={summary.reload} /> : null}
      {catalog.error ? <ErrorState error={catalog.error} retry={catalog.reload} /> : null}
      {actionError ? <div className="platform-error">{actionError}</div> : null}
      {notice ? <div className="platform-inline-success">{notice}</div> : null}

      <section className="platform-grid">
        <MetricCard label="Active subscriptions" value={activeSubscriptions} caption={`${dataMode} environment`} tone="green" mark="AS" />
        <MetricCard label="Trials" value={trialSubscriptions} caption="Current trial pipeline" tone="blue" mark="TR" />
        <MetricCard label="Past due" value={pastDueSubscriptions} caption="Access and revenue risk" tone={pastDueSubscriptions ? "red" : "green"} mark="PD" />
        <MetricCard label="Overdue invoices" value={summaryData?.overdue_invoices || 0} caption="Pending beyond due date" tone={summaryData?.overdue_invoices ? "amber" : "green"} mark="OI" />
        <MetricCard label="Catalog" value={`${summaryData?.module_count || modules.length} / ${summaryData?.plan_count || plans.length}`} caption="Modules / plans" tone="purple" mark="CA" />
      </section>

      <section className="platform-card">
        <div className="platform-tabs">{TABS.map((tab) => <button key={tab} className={activeTab === tab ? "active" : ""} onClick={() => setQuery({ tab })}>{tab.replace("-", " ")}</button>)}</div>
      </section>

      {activeTab === "overview" ? (
        <section className="platform-commercial-section-grid">
          <div className="platform-card"><div className="platform-section-title"><div><h2>Recurring revenue by currency</h2><p>Currencies are intentionally not combined into a false platform total.</p></div></div>{revenueCurrencies.length ? <DataTable><thead><tr><th>Currency</th><th>MRR</th><th>ARR</th><th>At risk</th><th>Trial pipeline</th></tr></thead><tbody>{revenueCurrencies.map(([currency, totals]) => <tr key={currency}><td><strong>{currency}</strong></td><td>{money(totals.mrr_cents, currency)}</td><td>{money(totals.arr_cents, currency)}</td><td>{money(totals.at_risk_cents, currency)}</td><td>{money(totals.trial_pipeline_cents, currency)}</td></tr>)}</tbody></DataTable> : <EmptyState label="No canonical recurring revenue yet." />}</div>
          <div className="platform-card"><div className="platform-section-title"><div><h2>Outstanding balances</h2><p>Open invoice balance after successful payment transactions.</p></div></div>{outstandingCurrencies.length ? <div className="platform-commercial-kpis">{outstandingCurrencies.map(([currency, cents]) => <div className="platform-commercial-kpi" key={currency}><span>{currency}</span><strong>{money(cents, currency)}</strong><small>Outstanding</small></div>)}</div> : <EmptyState label="No outstanding invoice balance." />}</div>
          <div className="platform-card"><h2>Commercial model</h2><div className="platform-timeline"><div className="platform-timeline__item"><strong>Module catalog</strong><small>Canonical route, category, sellability and trial rules.</small></div><div className="platform-timeline__item"><strong>Product plans</strong><small>Bundles modules and entitlement limits.</small></div><div className="platform-timeline__item"><strong>Price books</strong><small>Separate REAL/DEMO markets and currencies.</small></div><div className="platform-timeline__item"><strong>Tenant subscriptions</strong><small>Projects controlled access into legacy runtime records.</small></div></div></div>
          <div className="platform-card"><h2>Quick actions</h2><div className="platform-actions"><button className="platform-btn" onClick={() => setDrawer("module")}>New module</button><button className="platform-btn" onClick={() => setDrawer("plan")}>New plan</button><button className="platform-btn" onClick={() => setDrawer("book")}>New price book</button><button className="platform-btn" onClick={() => setDrawer("price")}>Publish price</button><button className="platform-btn primary" onClick={() => setDrawer("invoice")}>Create invoice</button></div></div>
        </section>
      ) : null}

      {activeTab === "modules" ? (
        <section className="platform-card"><div className="platform-section-title"><div><h2>Module catalog</h2><p>Known product modules replace free-text module codes.</p></div><button className="platform-btn primary" onClick={() => setDrawer("module")}>New module</button></div>{modules.length ? <DataTable><thead><tr><th>Module</th><th>Category</th><th>Route</th><th>Sellable</th><th>Trial</th><th>Status</th><th>Actions</th></tr></thead><tbody>{modules.map((module) => <tr key={module.id}><td><strong>{module.name}</strong><br /><small>{module.code}</small></td><td>{module.category}</td><td>{module.route_prefix || "—"}</td><td>{module.sellable ? "Yes" : "No"}</td><td>{module.trial_eligible ? "Yes" : "No"}</td><td><StatusBadge value={module.status} /></td><td><button className="platform-btn" onClick={() => run(() => commercialApi.updateModule(module.id, { status: module.status === "ARCHIVED" ? "ACTIVE" : "ARCHIVED", reason }), `Module ${module.status === "ARCHIVED" ? "restored" : "archived"}.`)}>{module.status === "ARCHIVED" ? "Restore" : "Archive"}</button></td></tr>)}</tbody></DataTable> : <EmptyState label="No commercial modules." />}</section>
      ) : null}

      {activeTab === "plans" ? (
        <section className="platform-card"><div className="platform-section-title"><div><h2>Product plans</h2><p>Plan bundles determine default subscription module access.</p></div><button className="platform-btn primary" onClick={() => setDrawer("plan")}>New plan</button></div>{plans.length ? <DataTable><thead><tr><th>Plan</th><th>Modules</th><th>Trial</th><th>Default term</th><th>Visibility</th><th>Status</th><th>Actions</th></tr></thead><tbody>{plans.map((plan) => <tr key={plan.id}><td><strong>{plan.name}</strong><br /><small>{plan.code}</small></td><td>{plan.modules.length}</td><td>{plan.trial_days} days</td><td>{plan.default_billing_term}</td><td>{plan.is_public ? "Public" : "Private"}</td><td><StatusBadge value={plan.status} /></td><td><button className="platform-btn" onClick={() => run(() => commercialApi.updatePlan(plan.id, { status: plan.status === "ARCHIVED" ? "ACTIVE" : "ARCHIVED", reason }), `Plan ${plan.status === "ARCHIVED" ? "restored" : "archived"}.`)}>{plan.status === "ARCHIVED" ? "Restore" : "Archive"}</button></td></tr>)}</tbody></DataTable> : <EmptyState label="No product plans." />}</section>
      ) : null}

      {activeTab === "price-books" ? (
        <section className="platform-card"><div className="platform-section-title"><div><h2>{dataMode} price books</h2><p>Each book belongs to one environment and one currency.</p></div><button className="platform-btn primary" onClick={() => setDrawer("book")}>New price book</button></div>{books.length ? <DataTable><thead><tr><th>Book</th><th>Currency</th><th>Market</th><th>Tax</th><th>Environment</th><th>Status</th><th>Actions</th></tr></thead><tbody>{books.map((book) => <tr key={book.id}><td><strong>{book.name}</strong><br /><small>{book.code}</small></td><td>{book.currency}</td><td>{book.market || "Global"}</td><td>{book.tax_inclusive ? "Inclusive" : "Exclusive"}</td><td><StatusBadge value={book.data_mode} /></td><td><StatusBadge value={book.status} /></td><td><button className="platform-btn" onClick={() => run(() => commercialApi.updatePriceBook(book.id, { status: book.status === "ACTIVE" ? "ARCHIVED" : "ACTIVE", reason }), "Price book status updated.")}>{book.status === "ACTIVE" ? "Archive" : "Activate"}</button></td></tr>)}</tbody></DataTable> : <EmptyState label={`No ${dataMode} price books.`} />}</section>
      ) : null}

      {activeTab === "prices" ? (
        <section className="platform-card"><div className="platform-section-title"><div><h2>Versioned price register</h2><p>Prices have effective periods, provider mappings and usage visibility.</p></div><button className="platform-btn primary" onClick={() => setDrawer("price")}>Publish price</button></div>{prices.length ? <DataTable><thead><tr><th>Target</th><th>Book</th><th>Term</th><th>Price</th><th>Effective</th><th>Provider</th><th>Used by</th><th>Status</th><th>Actions</th></tr></thead><tbody>{prices.map((price: PriceBookEntry) => <tr key={price.id}><td><strong>{price.plan_name || price.module_name}</strong><br /><small>{price.plan_code || price.module_code}</small></td><td>{price.price_book_code}</td><td>{price.billing_term}</td><td>{money(price.unit_amount_cents, price.currency || "USD")}</td><td>{new Date(price.effective_from).toLocaleDateString()}<br /><small>{price.effective_to ? `to ${new Date(price.effective_to).toLocaleDateString()}` : "open-ended"}</small></td><td>{price.external_price_ref || "Manual"}</td><td>{priceUsage.get(price.id) || 0}</td><td><StatusBadge value={price.status} /></td><td><button className="platform-btn" disabled={(priceUsage.get(price.id) || 0) > 0 && price.status === "ACTIVE"} onClick={() => run(() => commercialApi.updatePrice(price.id, { status: price.status === "RETIRED" ? "ACTIVE" : "RETIRED", reason }), "Price status updated.")}>{price.status === "RETIRED" ? "Restore" : "Retire"}</button></td></tr>)}</tbody></DataTable> : <EmptyState label="No prices in this environment." />}</section>
      ) : null}

      {activeTab === "subscriptions" ? (
        <section className="platform-card"><div className="platform-section-title"><div><h2>Subscription register</h2><p>Canonical tenant plans, terms, provider state and module items.</p></div></div>{subscriptions.data?.items.length ? <DataTable><thead><tr><th>Tenant</th><th>Plan</th><th>Term</th><th>Items</th><th>Provider</th><th>Period end</th><th>Status</th><th>Actions</th></tr></thead><tbody>{subscriptions.data.items.map((subscription) => <tr key={subscription.id}><td><strong>{subscription.tenant_name}</strong><br /><small>{subscription.tenant_code}</small></td><td>{subscription.plan_name}<br /><small>{subscription.price_book_code || "Manual pricing"}</small></td><td>{subscription.billing_term}<br /><small>{subscription.currency}</small></td><td>{subscription.items.length}</td><td>{subscription.provider || "Manual"}</td><td>{formatDate(subscription.current_period_end)}</td><td><StatusBadge value={subscription.status} /></td><td><div className="platform-actions"><button className="platform-btn" onClick={() => run(() => commercialApi.reconcileSubscription(subscription.id, reason), "Subscription reconciled.")}>Reconcile</button>{subscription.status !== "ACTIVE" ? <button className="platform-btn" onClick={() => run(() => commercialApi.transitionSubscription(subscription.id, { target_status: "ACTIVE", reason }), "Subscription activated.")}>Activate</button> : <button className="platform-btn" onClick={() => run(() => commercialApi.transitionSubscription(subscription.id, { target_status: "PAUSED", reason }), "Subscription paused.")}>Pause</button>}</div></td></tr>)}</tbody></DataTable> : <EmptyState label={`No ${dataMode.toLowerCase()} subscriptions.`} />}</section>
      ) : null}

      {activeTab === "invoices" ? (
        <section className="platform-card"><div className="platform-section-title"><div><h2>Invoice register</h2><p>Structured line items, payment-derived balances and fiscal state.</p></div><button className="platform-btn primary" onClick={() => setDrawer("invoice")}>Create invoice</button></div>{invoices.data?.items.length ? <DataTable><thead><tr><th>Invoice</th><th>Tenant</th><th>Amount</th><th>Paid</th><th>Balance</th><th>Due</th><th>Status</th><th>Actions</th></tr></thead><tbody>{invoices.data.items.map((invoice) => <tr key={invoice.id}><td><strong>{invoice.invoice_number}</strong><br /><small>{invoice.lines.length} line(s)</small></td><td>{invoice.tenant_name}<br /><small>{invoice.tenant_code}</small></td><td>{money(invoice.amount_cents, invoice.currency)}</td><td>{money(invoice.paid_cents, invoice.currency)}</td><td>{money(invoice.balance_cents, invoice.currency)}</td><td>{formatDate(invoice.due_at)}</td><td><StatusBadge value={invoice.status} /></td><td>{invoice.balance_cents > 0 ? <button className="platform-btn" onClick={() => openPayment(invoice)}>Record payment</button> : <StatusBadge value="SETTLED" />}</td></tr>)}</tbody></DataTable> : <EmptyState label="No invoices." />}</section>
      ) : null}

      {activeTab === "payments" ? (
        <section className="platform-card"><div className="platform-section-title"><div><h2>Payments & reconciliation</h2><p>Record evidence-backed payments; invoice status is derived from successful transactions.</p></div></div>{invoices.data?.items.some((invoice) => invoice.paid_cents > 0) ? <DataTable><thead><tr><th>Invoice</th><th>Tenant</th><th>Paid</th><th>Balance</th><th>Status</th><th>Action</th></tr></thead><tbody>{invoices.data.items.filter((invoice) => invoice.paid_cents > 0 || invoice.balance_cents > 0).map((invoice) => <tr key={invoice.id}><td>{invoice.invoice_number}</td><td>{invoice.tenant_name}</td><td>{money(invoice.paid_cents, invoice.currency)}</td><td>{money(invoice.balance_cents, invoice.currency)}</td><td><StatusBadge value={invoice.status} /></td><td>{invoice.balance_cents > 0 ? <button className="platform-btn" onClick={() => openPayment(invoice)}>Record payment</button> : "Complete"}</td></tr>)}</tbody></DataTable> : <EmptyState label="No payment activity yet." />}</section>
      ) : null}

      {drawer === "module" ? <Drawer title="New commercial module" subtitle="Create a canonical module used by plans, subscriptions and pricing." close={() => setDrawer(null)}><div className="platform-form-grid"><Field label="Code"><input value={moduleForm.code} onChange={(event) => setModuleForm({ ...moduleForm, code: event.target.value.toLowerCase().replaceAll("-", "_") })} /></Field><Field label="Name"><input value={moduleForm.name} onChange={(event) => setModuleForm({ ...moduleForm, name: event.target.value })} /></Field><Field label="Category"><input value={moduleForm.category} onChange={(event) => setModuleForm({ ...moduleForm, category: event.target.value.toUpperCase() })} /></Field><Field label="Route prefix"><input value={moduleForm.route_prefix} onChange={(event) => setModuleForm({ ...moduleForm, route_prefix: event.target.value })} /></Field><Field label="Description" span><textarea value={moduleForm.description} onChange={(event) => setModuleForm({ ...moduleForm, description: event.target.value })} /></Field><label><input type="checkbox" checked={moduleForm.sellable} onChange={(event) => setModuleForm({ ...moduleForm, sellable: event.target.checked })} /> Sellable</label><label><input type="checkbox" checked={moduleForm.trial_eligible} onChange={(event) => setModuleForm({ ...moduleForm, trial_eligible: event.target.checked })} /> Trial eligible</label><Field label="Reason" span><textarea value={moduleForm.reason} onChange={(event) => setModuleForm({ ...moduleForm, reason: event.target.value })} /></Field></div><button className="platform-btn primary" onClick={saveModule}>Save module</button></Drawer> : null}

      {drawer === "plan" ? <Drawer title="New product plan" subtitle="Bundle canonical modules with a default term and trial policy." close={() => setDrawer(null)}><div className="platform-form-grid"><Field label="Code"><input value={planForm.code} onChange={(event) => setPlanForm({ ...planForm, code: event.target.value.toUpperCase() })} /></Field><Field label="Name"><input value={planForm.name} onChange={(event) => setPlanForm({ ...planForm, name: event.target.value })} /></Field><Field label="Trial days"><input type="number" min="0" max="365" value={planForm.trial_days} onChange={(event) => setPlanForm({ ...planForm, trial_days: Number(event.target.value || 0) })} /></Field><Field label="Default term"><select value={planForm.default_billing_term} onChange={(event) => setPlanForm({ ...planForm, default_billing_term: event.target.value })}><option>MONTHLY</option><option>BI_ANNUAL</option><option>ANNUAL</option></select></Field><Field label="Description" span><textarea value={planForm.description} onChange={(event) => setPlanForm({ ...planForm, description: event.target.value })} /></Field><div className="span-2"><strong>Included modules</strong><div className="platform-module-matrix" style={{ marginTop: 8 }}>{modules.filter((module) => module.status === "ACTIVE").map((module) => <label className="platform-module-card" key={module.id}><span><input type="checkbox" checked={planForm.module_ids.includes(module.id)} onChange={(event) => setPlanForm({ ...planForm, module_ids: event.target.checked ? [...planForm.module_ids, module.id] : planForm.module_ids.filter((id) => id !== module.id) })} /> {module.name}</span><small>{module.category}</small></label>)}</div></div><label><input type="checkbox" checked={planForm.is_public} onChange={(event) => setPlanForm({ ...planForm, is_public: event.target.checked })} /> Public plan</label><Field label="Reason" span><textarea value={planForm.reason} onChange={(event) => setPlanForm({ ...planForm, reason: event.target.value })} /></Field></div><button className="platform-btn primary" onClick={savePlan}>Save plan</button></Drawer> : null}

      {drawer === "book" ? <Drawer title={`New ${dataMode} price book`} subtitle="Price books cannot span REAL and DEMO environments." close={() => setDrawer(null)}><div className="platform-form-grid"><Field label="Code"><input value={bookForm.code} onChange={(event) => setBookForm({ ...bookForm, code: event.target.value.toUpperCase() })} /></Field><Field label="Name"><input value={bookForm.name} onChange={(event) => setBookForm({ ...bookForm, name: event.target.value })} /></Field><Field label="Currency"><input value={bookForm.currency} onChange={(event) => setBookForm({ ...bookForm, currency: event.target.value.toUpperCase() })} /></Field><Field label="Market"><input value={bookForm.market} onChange={(event) => setBookForm({ ...bookForm, market: event.target.value })} /></Field><label><input type="checkbox" checked={bookForm.tax_inclusive} onChange={(event) => setBookForm({ ...bookForm, tax_inclusive: event.target.checked })} /> Tax inclusive</label><Field label="Reason" span><textarea value={bookForm.reason} onChange={(event) => setBookForm({ ...bookForm, reason: event.target.value })} /></Field></div><button className="platform-btn primary" onClick={saveBook}>Save price book</button></Drawer> : null}

      {drawer === "price" ? <Drawer title="Publish price version" subtitle="Create a dated plan or module price without rewriting contracted history." close={() => setDrawer(null)}><div className="platform-form-grid"><Field label="Price book"><select value={priceForm.price_book_id} onChange={(event) => setPriceForm({ ...priceForm, price_book_id: event.target.value })}><option value="">Select book</option>{books.filter((book) => book.status === "ACTIVE").map((book) => <option key={book.id} value={book.id}>{book.name}</option>)}</select></Field><Field label="Target type"><select value={priceForm.target_type} onChange={(event) => setPriceForm({ ...priceForm, target_type: event.target.value })}><option>PLAN</option><option>MODULE</option></select></Field>{priceForm.target_type === "PLAN" ? <Field label="Plan"><select value={priceForm.plan_id} onChange={(event) => setPriceForm({ ...priceForm, plan_id: event.target.value })}><option value="">Select plan</option>{plans.filter((plan) => plan.status === "ACTIVE").map((plan) => <option key={plan.id} value={plan.id}>{plan.name}</option>)}</select></Field> : <Field label="Module"><select value={priceForm.module_id} onChange={(event) => setPriceForm({ ...priceForm, module_id: event.target.value })}><option value="">Select module</option>{modules.filter((module) => module.status === "ACTIVE").map((module) => <option key={module.id} value={module.id}>{module.name}</option>)}</select></Field>}<Field label="Billing term"><select value={priceForm.billing_term} onChange={(event) => setPriceForm({ ...priceForm, billing_term: event.target.value })}><option>MONTHLY</option><option>BI_ANNUAL</option><option>ANNUAL</option><option>ONE_TIME</option></select></Field><Field label="Unit amount"><input type="number" min="0" step="0.01" value={priceForm.unit_amount} onChange={(event) => setPriceForm({ ...priceForm, unit_amount: event.target.value })} /></Field><Field label="Included quantity"><input type="number" min="1" value={priceForm.included_quantity} onChange={(event) => setPriceForm({ ...priceForm, included_quantity: Number(event.target.value || 1) })} /></Field><Field label="Overage amount"><input type="number" min="0" step="0.01" value={priceForm.overage_amount} onChange={(event) => setPriceForm({ ...priceForm, overage_amount: event.target.value })} /></Field><Field label="Tax rate %"><input type="number" min="0" max="100" step="0.01" value={priceForm.tax_rate} onChange={(event) => setPriceForm({ ...priceForm, tax_rate: event.target.value })} /></Field><Field label="Trial days"><input type="number" min="0" max="365" value={priceForm.trial_days} onChange={(event) => setPriceForm({ ...priceForm, trial_days: Number(event.target.value || 0) })} /></Field><Field label="Effective from"><input type="datetime-local" value={priceForm.effective_from} onChange={(event) => setPriceForm({ ...priceForm, effective_from: event.target.value })} /></Field><Field label="Provider product ref"><input value={priceForm.external_product_ref} onChange={(event) => setPriceForm({ ...priceForm, external_product_ref: event.target.value })} /></Field><Field label="Provider price ref"><input value={priceForm.external_price_ref} onChange={(event) => setPriceForm({ ...priceForm, external_price_ref: event.target.value })} /></Field><Field label="Reason" span><textarea value={priceForm.reason} onChange={(event) => setPriceForm({ ...priceForm, reason: event.target.value })} /></Field></div><button className="platform-btn primary" onClick={savePrice}>Publish price</button></Drawer> : null}

      {drawer === "invoice" ? <Drawer title="Create structured invoice" subtitle="Add one or more lines and derive the total server-side." close={() => setDrawer(null)}><div className="platform-form-grid"><Field label="Tenant"><select value={invoiceForm.tenant_id} onChange={(event) => setInvoiceForm({ ...invoiceForm, tenant_id: event.target.value })}><option value="">Select tenant</option>{tenantRows.map((tenant) => <option key={tenant.id} value={tenant.id}>{tenant.name} · {tenant.amo_code}</option>)}</select></Field><Field label="Currency"><input value={invoiceForm.currency} onChange={(event) => setInvoiceForm({ ...invoiceForm, currency: event.target.value.toUpperCase() })} /></Field><Field label="Due days"><input type="number" min="0" max="365" value={invoiceForm.due_days} onChange={(event) => setInvoiceForm({ ...invoiceForm, due_days: Number(event.target.value || 0) })} /></Field><Field label="Description"><input value={invoiceForm.description} onChange={(event) => setInvoiceForm({ ...invoiceForm, description: event.target.value })} /></Field></div><h3>Invoice lines</h3><div className="platform-stack-form">{invoiceForm.lines.map((line, index) => <div className="platform-subtle-panel" key={index}><div className="platform-form-grid"><Field label="Module"><select value={line.module_id} onChange={(event) => setInvoiceForm({ ...invoiceForm, lines: invoiceForm.lines.map((item, itemIndex) => itemIndex === index ? { ...item, module_id: event.target.value } : item) })}><option value="">General service</option>{modules.map((module) => <option key={module.id} value={module.id}>{module.name}</option>)}</select></Field><Field label="Description"><input value={line.description} onChange={(event) => setInvoiceForm({ ...invoiceForm, lines: invoiceForm.lines.map((item, itemIndex) => itemIndex === index ? { ...item, description: event.target.value } : item) })} /></Field><Field label="Quantity"><input type="number" min="1" value={line.quantity} onChange={(event) => setInvoiceForm({ ...invoiceForm, lines: invoiceForm.lines.map((item, itemIndex) => itemIndex === index ? { ...item, quantity: Number(event.target.value || 1) } : item) })} /></Field><Field label="Unit amount"><input type="number" min="0" step="0.01" value={line.unit_amount} onChange={(event) => setInvoiceForm({ ...invoiceForm, lines: invoiceForm.lines.map((item, itemIndex) => itemIndex === index ? { ...item, unit_amount: event.target.value } : item) })} /></Field><Field label="Tax %"><input type="number" min="0" max="100" step="0.01" value={line.tax_rate} onChange={(event) => setInvoiceForm({ ...invoiceForm, lines: invoiceForm.lines.map((item, itemIndex) => itemIndex === index ? { ...item, tax_rate: event.target.value } : item) })} /></Field><button className="platform-btn danger" disabled={invoiceForm.lines.length === 1} onClick={() => setInvoiceForm({ ...invoiceForm, lines: invoiceForm.lines.filter((_, itemIndex) => itemIndex !== index) })}>Remove line</button></div></div>)}</div><button className="platform-btn" onClick={() => setInvoiceForm({ ...invoiceForm, lines: [...invoiceForm.lines, { module_id: "", description: "Subscription service", quantity: 1, unit_amount: "0", tax_rate: "0" }] })}>Add line</button><Field label="Reason"><textarea value={invoiceForm.reason} onChange={(event) => setInvoiceForm({ ...invoiceForm, reason: event.target.value })} /></Field><button className="platform-btn primary" onClick={saveInvoice}>Create invoice</button></Drawer> : null}

      {drawer === "payment" && selectedInvoice ? <Drawer title={`Record payment · ${selectedInvoice.invoice_number}`} subtitle={`${selectedInvoice.tenant_name} · balance ${money(selectedInvoice.balance_cents, selectedInvoice.currency)}`} close={() => { setDrawer(null); setSelectedInvoice(null); }}><div className="platform-stack-form"><Field label={`Amount (${selectedInvoice.currency})`}><input type="number" min="0.01" step="0.01" value={paymentForm.amount} onChange={(event) => setPaymentForm({ ...paymentForm, amount: event.target.value })} /></Field><Field label="Provider"><select value={paymentForm.provider} onChange={(event) => setPaymentForm({ ...paymentForm, provider: event.target.value })}><option>MANUAL</option><option>STRIPE</option><option>OFFLINE</option><option>PSP</option></select></Field>{paymentForm.provider !== "MANUAL" ? <Field label="Provider reference"><input value={paymentForm.external_reference} onChange={(event) => setPaymentForm({ ...paymentForm, external_reference: event.target.value })} /></Field> : null}<Field label="Payment method"><input value={paymentForm.payment_method} onChange={(event) => setPaymentForm({ ...paymentForm, payment_method: event.target.value })} /></Field><Field label="Notes"><textarea value={paymentForm.notes} onChange={(event) => setPaymentForm({ ...paymentForm, notes: event.target.value })} /></Field><Field label="Reason"><textarea value={paymentForm.reason} onChange={(event) => setPaymentForm({ ...paymentForm, reason: event.target.value })} /></Field><button className="platform-btn primary" onClick={savePayment}>Record payment</button></div></Drawer> : null}
    </PlatformShell>
  );
}

function Drawer({ title, subtitle, close, children }: { title: string; subtitle: string; close: () => void; children: React.ReactNode }) {
  return <div className="platform-commercial-drawer" role="dialog" aria-modal="true"><div className="platform-commercial-drawer__panel"><div className="platform-commercial-drawer__head"><div><h2>{title}</h2><p>{subtitle}</p></div><button className="platform-icon-btn" onClick={close}>×</button></div>{children}</div></div>;
}

function Field({ label, span = false, children }: { label: string; span?: boolean; children: React.ReactNode }) {
  return <label className={span ? "span-2" : undefined}><span>{label}</span>{children}</label>;
}
