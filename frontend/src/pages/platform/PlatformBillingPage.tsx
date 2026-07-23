import React, { useMemo, useState } from "react";

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
  const [reason, setReason] = useState("Manual platform billing correction");
  const [tenantId, setTenantId] = useState("");
  const [selectedPriceId, setSelectedPriceId] = useState("");
  const [quantity, setQuantity] = useState(1);
  const [dueDays, setDueDays] = useState(7);
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
  const invoices = usePlatformData(
    () => platformApi.invoices({ data_mode: "REAL", limit: PAGE_SIZE, offset: invoiceOffset }),
    [invoiceOffset],
  );
  const prices = usePlatformData(
    () => platformApi.modulePrices({ include_inactive: true, limit: 200 }),
    [],
  );
  const jobs = usePlatformData(
    () => platformApi.saasJobs({ queue_name: "billing", limit: 20 }),
    [],
  );

  const selectedPrice = useMemo(
    () => prices.data?.items?.find((price) => price.id === selectedPriceId) ?? null,
    [prices.data?.items, selectedPriceId],
  );

  const run = async (action: () => Promise<unknown>, success: string) => {
    setError(null);
    setNotice(null);
    try {
      await action();
      setNotice(success);
      invoices.reload();
      prices.reload();
      jobs.reload();
      summary.reload();
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

  const createCheckout = () => {
    if (!tenantId.trim() || !selectedPriceId) {
      setError("Select a tenant and Stripe-backed module price before creating checkout.");
      return;
    }
    return run(
      () => platformApi.createCheckout(tenantId.trim(), {
        module_price_id: selectedPriceId,
        idempotency_key: `checkout:${tenantId.trim()}:${selectedPriceId}:${Date.now()}`,
      }),
      "Stripe checkout creation queued. Module access will change only after a verified webhook.",
    );
  };

  const summaryData = summary.data ?? {};
  const invoiceTotal = invoices.data?.total ?? 0;

  return (
    <PlatformShell
      title="Subscription, Pricing & Billing"
      subtitle="Module prices, tenant invoices, recurring checkout, payment states, eTIMS fiscalization and queued billing operations."
      actions={<button className="platform-btn" onClick={() => { summary.reload(); invoices.reload(); prices.reload(); jobs.reload(); }}>Refresh</button>}
    >
      {summary.error ? <ErrorState error={summary.error} retry={summary.reload} /> : null}
      {error ? <div className="platform-error">{error}</div> : null}
      {notice ? <p><StatusBadge value="PENDING" /> {notice}</p> : null}

      <section className="platform-grid">
        <MetricCard label="MRR" value={money(Number(summaryData.platform_mrr ?? 0))} />
        <MetricCard label="ARR" value={money(Number(summaryData.platform_arr ?? 0))} />
        <MetricCard label="Active subscriptions" value={String(summaryData.active_subscriptions ?? 0)} />
        <MetricCard label="Trials" value={String(summaryData.trial_subscriptions ?? 0)} />
        <MetricCard label="Overdue invoices" value={String(summaryData.overdue_invoices ?? 0)} />
        <MetricCard label="Failed payments" value={String(summaryData.failed_payments ?? 0)} />
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
            <label><span>Stripe price reference</span><input placeholder="price_..." value={priceForm.external_price_ref} onChange={(event) => setPriceForm({ ...priceForm, external_price_ref: event.target.value })} /></label>
            <button className="platform-btn primary" onClick={createPrice}>Save module price</button>
          </div>
        </div>

        <div className="platform-card">
          <h2>Tenant billing action</h2>
          <div className="platform-form">
            <label><span>Tenant ID</span><input value={tenantId} onChange={(event) => setTenantId(event.target.value)} /></label>
            <label><span>Module price</span><select value={selectedPriceId} onChange={(event) => setSelectedPriceId(event.target.value)}><option value="">Select price</option>{prices.data?.items?.filter((price) => price.is_active).map((price) => <option key={price.id} value={price.id}>{price.module_code} · {price.plan_code} · {price.billing_term} · {money(price.amount_cents, price.currency)}</option>)}</select></label>
            <label><span>Quantity</span><input type="number" min="1" value={quantity} onChange={(event) => setQuantity(Number(event.target.value || 1))} /></label>
            <label><span>Invoice due days</span><input type="number" min="0" max="365" value={dueDays} onChange={(event) => setDueDays(Number(event.target.value || 0))} /></label>
            <label><span>Reason</span><textarea value={reason} onChange={(event) => setReason(event.target.value)} /></label>
          </div>
          {selectedPrice ? <p>Selected: <strong>{selectedPrice.module_code}</strong> · {money(selectedPrice.amount_cents, selectedPrice.currency)} · <StatusBadge value={selectedPrice.external_price_ref ? "STRIPE READY" : "MANUAL ONLY"} /></p> : null}
          <div className="platform-actions">
            <button className="platform-btn primary" onClick={createInvoice}>Create manual invoice</button>
            <button className="platform-btn" onClick={createCheckout}>Queue recurring checkout</button>
          </div>
          <small>Checkout does not activate access. Verified Stripe subscription/invoice webhooks control tenant module state.</small>
        </div>
      </section>

      <section className="platform-card">
        <h2>Price register</h2>
        {prices.error ? <ErrorState error={prices.error} retry={prices.reload} /> : null}
        {prices.data?.items?.length ? (
          <DataTable>
            <thead><tr><th>Module</th><th>Plan</th><th>Term</th><th>Price</th><th>Tax</th><th>Trial</th><th>Provider ref</th><th>Status</th></tr></thead>
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
              return <tr key={id}><td>{String(invoice.invoice_number ?? id)}</td><td>{String(invoice.amo_id ?? "-")}</td><td>{money(Number(invoice.amount_cents ?? 0), String(invoice.currency ?? "USD"))}</td><td><StatusBadge value={invoiceStatus} /></td><td>{invoice.due_at ? new Date(String(invoice.due_at)).toLocaleDateString() : "-"}</td><td><div className="platform-actions">{invoiceStatus !== "PAID" ? <button className="platform-btn" onClick={() => run(() => platformApi.markInvoicePaid(id, reason), "Invoice marked paid.")}>Mark paid</button> : null}<button className="platform-btn" onClick={() => run(() => platformApi.fiscalizeInvoice(id, "etims_oscu"), "eTIMS fiscalization queued." )}>Fiscalize OSCU</button></div></td></tr>;
            })}</tbody>
          </DataTable>
        ) : <EmptyState label="No invoices recorded." />}
        <div className="platform-actions" style={{ marginTop: 12 }}>
          <button className="platform-btn" disabled={invoiceOffset === 0} onClick={() => setInvoiceOffset(Math.max(0, invoiceOffset - PAGE_SIZE))}>Previous</button>
          <span>{invoiceOffset + 1}-{Math.min(invoiceOffset + PAGE_SIZE, invoiceTotal)} of {invoiceTotal}</span>
          <button className="platform-btn" disabled={invoiceOffset + PAGE_SIZE >= invoiceTotal} onClick={() => setInvoiceOffset(invoiceOffset + PAGE_SIZE)}>Next</button>
        </div>
      </section>

      <section className="platform-card">
        <h2>Billing queue</h2>
        {jobs.data?.items?.length ? <DataTable><thead><tr><th>Created</th><th>Job</th><th>Tenant</th><th>Status</th><th>Attempts</th><th>Result/Error</th></tr></thead><tbody>{jobs.data.items.map((job) => <tr key={job.id}><td>{job.created_at ? new Date(job.created_at).toLocaleString() : "-"}</td><td>{job.job_type}<br /><small>{job.id}</small></td><td>{job.tenant_id ?? "Platform"}</td><td><StatusBadge value={job.status} /></td><td>{job.attempt_count}/{job.max_attempts}</td><td>{job.last_error ?? (job.result ? JSON.stringify(job.result) : "-")}</td></tr>)}</tbody></DataTable> : <EmptyState label="No billing jobs." />}
      </section>
    </PlatformShell>
  );
}
