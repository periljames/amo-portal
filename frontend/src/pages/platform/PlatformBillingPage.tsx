import React, { useMemo, useState } from "react";

import { commercialApi } from "../../services/commercialControl";
import { platformApi, type SaaSModulePrice } from "../../services/platformControl";
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
const money = (cents?: number, currency = "USD") => new Intl.NumberFormat(undefined, {
  style: "currency",
  currency,
}).format((cents ?? 0) / 100);

export default function PlatformBillingPage() {
  const [invoiceOffset, setInvoiceOffset] = useState(0);
  const [reason, setReason] = useState("Verified platform billing operation");
  const [tenantId, setTenantId] = useState("");
  const [selectedPriceId, setSelectedPriceId] = useState("");
  const [quantity, setQuantity] = useState(1);
  const [dueDays, setDueDays] = useState(7);
  const [offlineReference, setOfflineReference] = useState("");
  const [mpesaPhone, setMpesaPhone] = useState("");
  const [notice, setNotice] = useState<string | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [priceForm, setPriceForm] = useState({
    module_code: "quality",
    plan_code: "STANDARD",
    billing_term: "MONTHLY",
    amount: "0",
    currency: "USD",
    trial_days: "0",
    tax_rate: "0",
    external_price_ref: "",
  });

  const summary = usePlatformData(() => platformApi.billingSummary("REAL"), []);
  const commercial = usePlatformData(() => commercialApi.summary("REAL"), [], { pollMs: 15_000 });
  const invoices = usePlatformData(
    () => platformApi.invoices({ data_mode: "REAL", limit: PAGE_SIZE, offset: invoiceOffset }),
    [invoiceOffset],
  );
  const prices = usePlatformData(
    () => platformApi.modulePrices({ include_inactive: true, limit: 200 }),
    [],
  );
  const jobs = usePlatformData(
    () => platformApi.saasJobs({ queue_name: "billing", limit: 30 }),
    [],
    { pollMs: 5_000 },
  );

  const selectedPrice = useMemo(
    () => prices.data?.items?.find((price) => price.id === selectedPriceId) ?? null,
    [prices.data?.items, selectedPriceId],
  );

  const reloadBilling = () => {
    invoices.reload();
    prices.reload();
    jobs.reload();
    summary.reload();
    commercial.reload();
  };

  const run = async (action: () => Promise<unknown>, success: string) => {
    setError(null);
    setNotice(null);
    try {
      await action();
      setNotice(success);
      reloadBilling();
    } catch (caught) {
      setError(caught instanceof Error ? caught.message : String(caught));
    }
  };

  const createPrice = () => {
    const amountCents = Math.round(Number(priceForm.amount || 0) * 100);
    const taxRateBps = Math.round(Number(priceForm.tax_rate || 0) * 100);
    return run(
      () => platformApi.createModulePrice({
        module_code: priceForm.module_code,
        plan_code: priceForm.plan_code,
        billing_term: priceForm.billing_term,
        amount_cents: amountCents,
        currency: priceForm.currency,
        trial_days: Number(priceForm.trial_days || 0),
        tax_rate_bps: taxRateBps,
        external_price_ref: priceForm.external_price_ref || null,
        is_active: true,
        reason: "Module pricing updated from the superuser console",
      }),
      "Module price saved.",
    );
  };

  const createInvoice = () => {
    if (!tenantId.trim() || !selectedPriceId) {
      setError("Select a tenant and module price before creating an invoice.");
      return;
    }
    return run(
      () => platformApi.createManualInvoice(tenantId.trim(), {
        module_price_id: selectedPriceId,
        quantity,
        due_days: dueDays,
        reason,
        idempotency_key: `manual:${tenantId.trim()}:${selectedPriceId}:${Date.now()}`,
      }),
      "Invoice created from the server-side price catalog.",
    );
  };

  const createStripeCheckout = () => {
    if (!tenantId.trim() || !selectedPriceId) {
      setError("Select a tenant and Stripe-backed module price before creating checkout.");
      return;
    }
    return run(
      () => platformApi.createCheckout(tenantId.trim(), {
        module_price_id: selectedPriceId,
        idempotency_key: `checkout:${tenantId.trim()}:${selectedPriceId}:${Date.now()}`,
      }),
      "Stripe subscription checkout queued. Access changes only after a verified provider event.",
    );
  };

  const collectInvoice = (invoiceId: string, provider: "paystack" | "mpesa_daraja") => run(
    () => commercialApi.startInvoicePayment(invoiceId, provider, {
      phone: provider === "mpesa_daraja" ? mpesaPhone.trim() || undefined : undefined,
    }),
    provider === "paystack"
      ? "Paystack checkout queued. Open the authorization URL from the successful billing job result."
      : "M-PESA STK Push queued. Settlement is recorded only after callback plus server-side verification.",
  );

  const settleOffline = (invoiceId: string) => {
    if (!offlineReference.trim()) {
      setError("Enter the bank/offline payment reference before recording settlement.");
      return;
    }
    return run(
      () => commercialApi.recordOfflinePayment(invoiceId, offlineReference.trim(), reason),
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
  const invoiceTotal = invoices.data?.total ?? 0;
  const providerStatuses = commercialData?.provider_statuses ?? {};

  return (
    <PlatformShell
      title="Subscription, Pricing & Billing"
      subtitle="Invoice-first subscription billing, verified collections, eTIMS fiscalization and external accounting synchronization."
      actions={<button className="platform-btn" onClick={reloadBilling}>Refresh</button>}
    >
      {summary.error ? <ErrorState error={summary.error} retry={summary.reload} /> : null}
      {commercial.error ? <ErrorState error={commercial.error} retry={commercial.reload} /> : null}
      {error ? <div className="platform-error">{error}</div> : null}
      {notice ? <p><StatusBadge value="PENDING" /> {notice}</p> : null}

      <section className="platform-grid">
        <MetricCard label="MRR" value={money(Number(summaryData.platform_mrr ?? 0))} caption="Legacy license model pending module-price cohort reconciliation" />
        <MetricCard label="Outstanding A/R" value={money(commercialData?.outstanding_ar_cents ?? 0)} caption={`${commercialData?.overdue_invoice_count ?? 0} overdue invoices`} tone="amber" mark="AR" />
        <MetricCard label="Collected 30d" value={money(commercialData?.collected_30d_cents ?? 0)} caption="Paid portal invoices" tone="green" mark="CA" />
        <MetricCard label="Invoiced 30d" value={money(commercialData?.invoiced_30d_cents ?? 0)} caption="Operational billing subledger" tone="blue" mark="IV" />
        <MetricCard label="Failed payment jobs" value={String(commercialData?.failed_payment_jobs_30d ?? 0)} caption="Last 30 days" tone={(commercialData?.failed_payment_jobs_30d ?? 0) ? "red" : "green"} mark="FP" />
        <MetricCard label="QuickBooks" value={providerStatuses.quickbooks_online ?? "NOT_CONFIGURED"} caption="External GL/accounting boundary" tone={providerStatuses.quickbooks_online === "HEALTHY" ? "green" : "amber"} mark="QB" />
      </section>

      <section className="platform-two">
        <div className="platform-card">
          <h2>Module price catalog</h2>
          <div className="platform-form">
            <label><span>Module code</span><input value={priceForm.module_code} onChange={(event) => setPriceForm({ ...priceForm, module_code: event.target.value })} /></label>
            <label><span>Plan</span><input value={priceForm.plan_code} onChange={(event) => setPriceForm({ ...priceForm, plan_code: event.target.value })} /></label>
            <label><span>Term</span><select value={priceForm.billing_term} onChange={(event) => setPriceForm({ ...priceForm, billing_term: event.target.value })}><option>MONTHLY</option><option>ANNUAL</option><option>BI_ANNUAL</option><option>ONE_TIME</option></select></label>
            <label><span>Amount</span><input type="number" min="0" step="0.01" value={priceForm.amount} onChange={(event) => setPriceForm({ ...priceForm, amount: event.target.value })} /></label>
            <label><span>Currency</span><input value={priceForm.currency} onChange={(event) => setPriceForm({ ...priceForm, currency: event.target.value.toUpperCase() })} /></label>
            <label><span>Trial days</span><input type="number" min="0" max="365" value={priceForm.trial_days} onChange={(event) => setPriceForm({ ...priceForm, trial_days: event.target.value })} /></label>
            <label><span>Tax rate %</span><input type="number" min="0" max="100" step="0.01" value={priceForm.tax_rate} onChange={(event) => setPriceForm({ ...priceForm, tax_rate: event.target.value })} /></label>
            <label><span>Stripe price reference</span><input placeholder="price_... (only for Stripe subscriptions)" value={priceForm.external_price_ref} onChange={(event) => setPriceForm({ ...priceForm, external_price_ref: event.target.value })} /></label>
            <button className="platform-btn primary" onClick={createPrice}>Save module price</button>
          </div>
        </div>

        <div className="platform-card">
          <h2>Invoice & subscription action</h2>
          <div className="platform-form">
            <label><span>Tenant ID</span><input value={tenantId} onChange={(event) => setTenantId(event.target.value)} /></label>
            <label><span>Module price</span><select value={selectedPriceId} onChange={(event) => setSelectedPriceId(event.target.value)}><option value="">Select price</option>{prices.data?.items?.filter((price) => price.is_active).map((price) => <option key={price.id} value={price.id}>{price.module_code} · {price.plan_code} · {price.billing_term} · {money(price.amount_cents, price.currency)}</option>)}</select></label>
            <label><span>Quantity</span><input type="number" min="1" value={quantity} onChange={(event) => setQuantity(Number(event.target.value || 1))} /></label>
            <label><span>Invoice due days</span><input type="number" min="0" max="365" value={dueDays} onChange={(event) => setDueDays(Number(event.target.value || 0))} /></label>
            <label><span>Reason</span><textarea value={reason} onChange={(event) => setReason(event.target.value)} /></label>
          </div>
          {selectedPrice ? <p>Selected: <strong>{selectedPrice.module_code}</strong> · {money(selectedPrice.amount_cents, selectedPrice.currency)} · <StatusBadge value={selectedPrice.external_price_ref ? "STRIPE READY" : "INVOICE FIRST"} /></p> : null}
          <div className="platform-actions">
            <button className="platform-btn primary" onClick={createInvoice}>Create invoice</button>
            <button className="platform-btn" onClick={createStripeCheckout}>Stripe recurring checkout</button>
          </div>
          <small>Paystack and M-PESA collect an existing portal invoice. Stripe recurring checkout remains provider-led but module access still changes only after verified settlement/subscription events.</small>
        </div>
      </section>

      <section className="platform-two">
        <div className="platform-card">
          <h2>Collections controls</h2>
          <div className="platform-form">
            <label><span>M-PESA phone override</span><input placeholder="2547XXXXXXXX (blank uses tenant contact phone)" value={mpesaPhone} onChange={(event) => setMpesaPhone(event.target.value)} /></label>
            <label><span>Bank/offline payment reference</span><input placeholder="Bank receipt / transfer / cheque reference" value={offlineReference} onChange={(event) => setOfflineReference(event.target.value)} /></label>
          </div>
          <p><StatusBadge value={providerStatuses.paystack ?? "PAYSTACK NOT_CONFIGURED"} /> <StatusBadge value={providerStatuses.mpesa_daraja ?? "MPESA NOT_CONFIGURED"} /></p>
          <small>Manual settlement is not a generic “mark paid” action. It requires a reference and the reason above, and creates an auditable PAYMENT ledger entry.</small>
        </div>
        <div className="platform-card">
          <h2>Accounting & tax integrations</h2>
          <p><StatusBadge value={providerStatuses.quickbooks_online ?? "QUICKBOOKS NOT_CONFIGURED"} /> <StatusBadge value={providerStatuses.etims_oscu ?? providerStatuses.etims_vscu ?? "ETIMS NOT_CONFIGURED"} /></p>
          <div className="platform-actions"><button className="platform-btn primary" onClick={connectQuickBooks}>Connect QuickBooks Online</button></div>
          <small>AMO Portal remains the subscription billing subledger. QuickBooks is the external general-ledger/accounting boundary. Tax-bearing invoice writeback is blocked until QuickBooks tax/item mappings are configured; eTIMS fiscalization remains independent.</small>
        </div>
      </section>

      <section className="platform-card">
        <h2>Price register</h2>
        {prices.error ? <ErrorState error={prices.error} retry={prices.reload} /> : null}
        {prices.data?.items?.length ? (
          <DataTable>
            <thead><tr><th>Module</th><th>Plan</th><th>Term</th><th>Price</th><th>Tax</th><th>Trial</th><th>Stripe ref</th><th>Status</th></tr></thead>
            <tbody>{prices.data.items.map((price: SaaSModulePrice) => <tr key={price.id}><td>{price.module_code}</td><td>{price.plan_code}</td><td>{price.billing_term}</td><td>{money(price.amount_cents, price.currency)}</td><td>{(price.tax_rate_bps / 100).toFixed(2)}%</td><td>{price.trial_days} days</td><td>{price.external_price_ref ?? "-"}</td><td><StatusBadge value={price.is_active ? "ACTIVE" : "INACTIVE"} /></td></tr>)}</tbody>
          </DataTable>
        ) : <EmptyState label="No module prices configured." />}
      </section>

      <section className="platform-card">
        <h2>Invoice control</h2>
        {invoices.error ? <ErrorState error={invoices.error} retry={invoices.reload} /> : null}
        {invoices.data?.items?.length ? (
          <DataTable>
            <thead><tr><th>Invoice</th><th>Tenant</th><th>Amount</th><th>Status</th><th>Due</th><th>Actions</th></tr></thead>
            <tbody>{invoices.data.items.map((invoice) => {
              const id = String(invoice.id ?? "");
              const invoiceStatus = String(invoice.status ?? "UNKNOWN");
              const currency = String(invoice.currency ?? "USD").toUpperCase();
              return <tr key={id}><td>{String(invoice.invoice_number ?? id)}</td><td>{String(invoice.amo_id ?? "-")}</td><td>{money(Number(invoice.amount_cents ?? 0), currency)}</td><td><StatusBadge value={invoiceStatus} /></td><td>{invoice.due_at ? new Date(String(invoice.due_at)).toLocaleDateString() : "-"}</td><td><div className="platform-actions">{invoiceStatus === "PENDING" ? <><button className="platform-btn primary" onClick={() => collectInvoice(id, "paystack")}>Paystack</button><button className="platform-btn" disabled={currency !== "KES"} onClick={() => collectInvoice(id, "mpesa_daraja")}>M-PESA STK</button><button className="platform-btn" onClick={() => settleOffline(id)}>Record bank/offline</button></> : null}<button className="platform-btn" onClick={() => run(() => platformApi.fiscalizeInvoice(id, "etims_oscu"), "eTIMS fiscalization queued.")}>Fiscalize OSCU</button>{invoiceStatus === "PAID" ? <button className="platform-btn" onClick={() => run(() => commercialApi.syncQuickBooks(id), "QuickBooks synchronization queued.")}>Sync QuickBooks</button> : null}</div></td></tr>;
            })}</tbody>
          </DataTable>
        ) : <EmptyState label="No invoices recorded." />}
        <div className="platform-actions" style={{ marginTop: 12 }}>
          <button className="platform-btn" disabled={invoiceOffset === 0} onClick={() => setInvoiceOffset(Math.max(0, invoiceOffset - PAGE_SIZE))}>Previous</button>
          <span>{invoiceTotal ? invoiceOffset + 1 : 0}-{Math.min(invoiceOffset + PAGE_SIZE, invoiceTotal)} of {invoiceTotal}</span>
          <button className="platform-btn" disabled={invoiceOffset + PAGE_SIZE >= invoiceTotal} onClick={() => setInvoiceOffset(invoiceOffset + PAGE_SIZE)}>Next</button>
        </div>
      </section>

      <section className="platform-card">
        <h2>Billing queue</h2>
        {jobs.data?.items?.length ? <DataTable><thead><tr><th>Created</th><th>Job</th><th>Tenant</th><th>Status</th><th>Attempts</th><th>Result/Error</th></tr></thead><tbody>{jobs.data.items.map((job) => {
          const authorizationUrl = job.result && typeof job.result.authorization_url === "string" ? job.result.authorization_url : null;
          return <tr key={job.id}><td>{job.created_at ? new Date(job.created_at).toLocaleString() : "-"}</td><td>{job.job_type}<br /><small>{job.id}</small></td><td>{job.tenant_id ?? "Platform"}</td><td><StatusBadge value={job.status} /></td><td>{job.attempt_count}/{job.max_attempts}</td><td>{authorizationUrl ? <a href={authorizationUrl} target="_blank" rel="noreferrer">Open Paystack checkout</a> : job.last_error ?? (job.result ? JSON.stringify(job.result) : "-")}</td></tr>;
        })}</tbody></DataTable> : <EmptyState label="No billing jobs." />}
      </section>
    </PlatformShell>
  );
}
