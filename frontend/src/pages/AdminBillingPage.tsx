import React, { useEffect, useMemo, useState } from "react";
import { useLocation, useNavigate, useParams } from "react-router-dom";

import DepartmentLayout from "../components/Layout/DepartmentLayout";
import { Button, InlineAlert, PageHeader, Panel, Table } from "../components/UI/Admin";
import { getCachedUser } from "../services/auth";
import {
  fetchBillingAccessStatus,
  fetchInvoiceDocument,
  fetchInvoices,
} from "../services/billing";
import {
  cancelTenantModuleSubscription,
  createModuleSubscriptionOrder,
  fetchSelfServiceModuleCatalog,
  fetchTenantPaymentJob,
  initiateTenantInvoicePayment,
  type CommercialModule,
  type ModulePrice,
  type SelfServiceCatalog,
} from "../services/moduleCommerce";
import type { BillingAccessStatus, Invoice } from "../types/billing";
import { saveDownloadedFile } from "../utils/downloads";

type UrlParams = { amoCode?: string };
type PaymentProvider = "paystack" | "mpesa_daraja";
type Checkout = { module: CommercialModule; price: ModulePrice };

const sleep = (ms: number) => new Promise((resolve) => window.setTimeout(resolve, ms));

const money = (cents: number, currency = "USD") => {
  try {
    return new Intl.NumberFormat(undefined, { style: "currency", currency }).format((cents || 0) / 100);
  } catch {
    return `${currency} ${((cents || 0) / 100).toFixed(2)}`;
  }
};

const dateLabel = (value?: string | null) => value ? new Date(value).toLocaleDateString() : "—";

function invoiceDetails(invoice: Invoice): Record<string, unknown> {
  if (!invoice.description) return {};
  try {
    const parsed = JSON.parse(invoice.description) as unknown;
    return parsed && typeof parsed === "object" ? parsed as Record<string, unknown> : {};
  } catch {
    return {};
  }
}

function invoiceLabel(invoice: Invoice) {
  const details = invoiceDetails(invoice);
  return String(details.module_name || details.module_code || details.description || "Platform services");
}

function providerLabel(provider: PaymentProvider) {
  return provider === "mpesa_daraja" ? "M-PESA" : "Paystack";
}

const AdminBillingPage: React.FC = () => {
  const { amoCode = "UNKNOWN" } = useParams<UrlParams>();
  const navigate = useNavigate();
  const location = useLocation();
  const user = useMemo(() => getCachedUser(), []);
  const role = String(user?.role || "").toUpperCase();
  const isSuperuser = !!user?.is_superuser;
  const canSubscribe = !isSuperuser && (!!user?.is_amo_admin || role === "AMO_ADMIN" || role === "FINANCE_MANAGER");
  const canPay = canSubscribe || (!isSuperuser && role === "ACCOUNTS_OFFICER");
  const canViewBillingDetails = canPay;

  const query = useMemo(() => new URLSearchParams(location.search), [location.search]);
  const stateFrom = (location.state as { from?: string } | null)?.from;
  const returnTo = query.get("returnTo") || stateFrom || null;

  const [access, setAccess] = useState<BillingAccessStatus | null>(null);
  const [invoices, setInvoices] = useState<Invoice[]>([]);
  const [catalog, setCatalog] = useState<SelfServiceCatalog | null>(null);
  const [loading, setLoading] = useState(true);
  const [refreshing, setRefreshing] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [notice, setNotice] = useState<string | null>(null);

  const [paymentInvoiceId, setPaymentInvoiceId] = useState<string | null>(null);
  const [provider, setProvider] = useState<PaymentProvider>("paystack");
  const [phone, setPhone] = useState("");
  const [paying, setPaying] = useState(false);

  const [checkout, setCheckout] = useState<Checkout | null>(null);
  const [termsAccepted, setTermsAccepted] = useState(false);
  const [ordering, setOrdering] = useState(false);

  const [cancelModule, setCancelModule] = useState<CommercialModule | null>(null);
  const [cancelReason, setCancelReason] = useState("");
  const [cancelling, setCancelling] = useState(false);

  const load = async (quiet = false) => {
    quiet ? setRefreshing(true) : setLoading(true);
    setError(null);
    try {
      const accessResult = await fetchBillingAccessStatus();
      setAccess(accessResult);

      if (!canViewBillingDetails) {
        setInvoices([]);
        setCatalog(null);
        return;
      }

      const [invoiceResult, catalogResult] = await Promise.all([
        fetchInvoices(),
        fetchSelfServiceModuleCatalog(),
      ]);
      setInvoices(invoiceResult);
      setCatalog(catalogResult);
    } catch (caught) {
      setError(caught instanceof Error ? caught.message : String(caught));
    } finally {
      setLoading(false);
      setRefreshing(false);
    }
  };

  useEffect(() => { void load(); }, [canViewBillingDetails]);

  const pendingInvoices = useMemo(
    () => invoices.filter((invoice) => String(invoice.status).toUpperCase() === "PENDING"),
    [invoices],
  );

  const outstandingByCurrency = useMemo(() => {
    const totals = new Map<string, number>();
    pendingInvoices.forEach((invoice) => {
      const currency = String(invoice.currency || "USD").toUpperCase();
      totals.set(currency, (totals.get(currency) || 0) + Number(invoice.total_cents ?? invoice.amount_cents ?? 0));
    });
    return [...totals.entries()].sort(([a], [b]) => a.localeCompare(b));
  }, [pendingInvoices]);

  const activeModules = useMemo(
    () => (catalog?.items || []).filter((item) => item.is_active_for_tenant),
    [catalog],
  );
  const availableModules = useMemo(
    () => (catalog?.items || []).filter((item) => !item.is_active_for_tenant),
    [catalog],
  );
  const paymentRequired = Boolean(access && !access.has_access && access.redirect_to_billing);

  const downloadInvoice = async (invoice: Invoice) => {
    if (!canViewBillingDetails) return;
    setError(null);
    try {
      saveDownloadedFile(await fetchInvoiceDocument(invoice.id, "pdf"));
    } catch (caught) {
      setError(caught instanceof Error ? caught.message : String(caught));
    }
  };

  const waitForPaymentJob = async (jobId: string) => {
    for (let i = 0; i < 45; i += 1) {
      const job = await fetchTenantPaymentJob(jobId);
      const status = String(job.status || "").toUpperCase();
      if (status === "SUCCEEDED") return job;
      if (["FAILED", "DEAD", "CANCELLED"].includes(status)) {
        throw new Error(job.last_error || "Payment provider request failed.");
      }
      await sleep(1000);
    }
    throw new Error("Payment initialization is taking longer than expected. Refresh Billing to check the current status before retrying.");
  };

  const waitForInvoiceSettlement = async (invoiceId: string) => {
    for (let i = 0; i < 45; i += 1) {
      await sleep(2000);
      const freshInvoices = await fetchInvoices();
      setInvoices(freshInvoices);
      if (freshInvoices.some((row) => row.id === invoiceId && String(row.status).toUpperCase() === "PAID")) {
        const freshAccess = await fetchBillingAccessStatus();
        setAccess(freshAccess);
        await fetchSelfServiceModuleCatalog().then(setCatalog).catch(() => undefined);
        return true;
      }
    }
    return false;
  };

  const payInvoice = async (invoiceId: string) => {
    if (!canPay) return;
    if (provider === "mpesa_daraja" && !phone.trim()) {
      setError("Enter the mobile number that should receive the M-PESA STK prompt.");
      return;
    }
    setPaying(true);
    setError(null);
    setNotice(null);
    try {
      const queued = await initiateTenantInvoicePayment(invoiceId, {
        provider,
        phone: provider === "mpesa_daraja" ? phone.trim() : undefined,
      });
      const initialized = await waitForPaymentJob(queued.id);
      if (provider === "paystack") {
        const url = String(initialized.result?.authorization_url || "").trim();
        if (!url) throw new Error("Paystack did not return a hosted checkout URL.");
        window.location.assign(url);
        return;
      }

      setNotice("M-PESA request sent. Complete the STK prompt on the phone. Access changes only after Safaricom confirms settlement.");
      const settled = await waitForInvoiceSettlement(invoiceId);
      if (settled) {
        setNotice("Payment verified. Billing and subscribed access have been refreshed.");
        setPaymentInvoiceId(null);
      } else {
        setNotice("The M-PESA request was initiated, but settlement is still pending. Do not submit a duplicate payment; use Refresh to check status.");
      }
    } catch (caught) {
      setError(caught instanceof Error ? caught.message : String(caught));
    } finally {
      setPaying(false);
    }
  };

  const orderModule = async () => {
    if (!checkout || !catalog?.terms || !canSubscribe) return;
    if (!termsAccepted) {
      setError("Accept the recurring billing terms before creating the order.");
      return;
    }
    setOrdering(true);
    setError(null);
    setNotice(null);
    try {
      const invoice = await createModuleSubscriptionOrder({
        module_code: checkout.module.code,
        price_id: checkout.price.id,
        expected_amount_cents: checkout.price.amount_cents,
        currency: checkout.price.currency,
        terms_version: catalog.terms.version,
        auto_renew_accepted: true,
      });
      await load(true);
      setCheckout(null);
      setTermsAccepted(false);
      setPaymentInvoiceId(invoice.id);
      setNotice("Order created. Pay the invoice below to activate the module; creating an order alone does not grant access.");
    } catch (caught) {
      setError(caught instanceof Error ? caught.message : String(caught));
    } finally {
      setOrdering(false);
    }
  };

  const confirmCancellation = async () => {
    if (!cancelModule || !canSubscribe) return;
    if (!cancelReason.trim()) {
      setError("Enter a cancellation reason for the commercial audit trail.");
      return;
    }
    setCancelling(true);
    setError(null);
    try {
      await cancelTenantModuleSubscription(cancelModule.code, cancelReason.trim());
      setNotice(`${cancelModule.name} will not renew. Access remains available through the already-paid service period.`);
      setCancelModule(null);
      setCancelReason("");
      await load(true);
    } catch (caught) {
      setError(caught instanceof Error ? caught.message : String(caught));
    } finally {
      setCancelling(false);
    }
  };

  const selectedTax = checkout ? Math.round(checkout.price.amount_cents * (checkout.price.tax_rate_bps || 0) / 10000) : 0;
  const selectedTotal = checkout ? checkout.price.amount_cents + selectedTax : 0;

  return (
    <DepartmentLayout amoCode={amoCode} activeDepartment="admin-billing">
      <div className="admin-page admin-billing">
        <PageHeader
          title="Billing & subscriptions"
          subtitle="Resolve account billing status and, for authorised finance roles, manage invoices and subscribed modules."
          actions={
            <Button type="button" size="sm" variant="secondary" disabled={refreshing} onClick={() => void load(true)}>
              {refreshing ? "Refreshing…" : "Refresh"}
            </Button>
          }
        />

        {paymentRequired && (
          <InlineAlert tone="danger" title="Payment required to restore platform access">
            <span>{access?.lock_reason || "This account has an overdue billing obligation."} An AMO administrator or authorised finance user can settle the account from this page.</span>
          </InlineAlert>
        )}
        {error && <InlineAlert tone="danger" title="Billing action failed"><span>{error}</span></InlineAlert>}
        {notice && <InlineAlert tone="info" title="Billing update"><span>{notice}</span></InlineAlert>}

        <div className="admin-summary-strip">
          <div className="admin-summary-item"><span className="admin-summary-item__label">Access</span><span className="admin-summary-item__value">{access?.access_state || (loading ? "Loading…" : "Unknown")}</span></div>
          <div className="admin-summary-item"><span className="admin-summary-item__label">Commercial details</span><span className="admin-summary-item__value">{canViewBillingDetails ? "Authorised" : "Restricted"}</span></div>
          <div className="admin-summary-item"><span className="admin-summary-item__label">Open invoices</span><span className="admin-summary-item__value">{canViewBillingDetails ? pendingInvoices.length : "—"}</span></div>
          <div className="admin-summary-item"><span className="admin-summary-item__label">Outstanding</span><span className="admin-summary-item__value">{canViewBillingDetails ? (outstandingByCurrency.length ? outstandingByCurrency.map(([currency, cents]) => money(cents, currency)).join(" · ") : "None") : "Restricted"}</span></div>
        </div>

        <div className="admin-page__grid">
          {canViewBillingDetails ? (
            <Panel title={paymentRequired ? "Settle outstanding billing" : "Invoices & payments"} subtitle="Only verified provider settlement changes invoice or access state.">
              {loading && <p className="admin-muted">Loading billing records…</p>}
              {!loading && invoices.length === 0 && <p className="admin-muted">No invoices have been issued to this AMO.</p>}
              {!loading && invoices.length > 0 && (
                <Table>
                  <thead><tr><th>Invoice</th><th>For</th><th>Status</th><th>Due</th><th>Total</th><th>Actions</th></tr></thead>
                  <tbody>
                    {invoices.map((invoice) => (
                      <tr key={invoice.id} style={access?.actionable_invoice_id === invoice.id ? { fontWeight: 700 } : undefined}>
                        <td>{invoice.invoice_number || invoice.id.slice(-8).toUpperCase()}</td>
                        <td>{invoiceLabel(invoice)}</td>
                        <td>{invoice.status}</td>
                        <td>{dateLabel(invoice.due_at)}</td>
                        <td>{money(invoice.total_cents ?? invoice.amount_cents, invoice.currency)}</td>
                        <td><div className="page-section__actions">
                          <Button type="button" size="sm" variant="secondary" onClick={() => navigate(`/maintenance/${amoCode}/admin/invoices/${invoice.id}`)}>View</Button>
                          <Button type="button" size="sm" variant="secondary" onClick={() => void downloadInvoice(invoice)}>PDF</Button>
                          {String(invoice.status).toUpperCase() === "PENDING" && canPay && <Button type="button" size="sm" onClick={() => setPaymentInvoiceId(invoice.id)}>Pay</Button>}
                        </div></td>
                      </tr>
                    ))}
                  </tbody>
                </Table>
              )}

              {paymentInvoiceId && pendingInvoices.some((row) => row.id === paymentInvoiceId) && (
                <div style={{ marginTop: 18, paddingTop: 16, borderTop: "1px solid var(--border-color, #d8dde6)" }}>
                  <h3 style={{ marginTop: 0 }}>Process payment</h3>
                  <p className="admin-muted">Card/bank entry is handled on the payment provider's hosted checkout. AMO Portal never asks for or stores a card number, CVV/CVC, PIN, magnetic-stripe data or bank authentication secret.</p>
                  <div className="form-row"><label htmlFor="billing-provider">Payment method</label><select id="billing-provider" value={provider} onChange={(event) => setProvider(event.target.value as PaymentProvider)}><option value="paystack">Paystack — hosted card/bank checkout</option><option value="mpesa_daraja">M-PESA — STK Push</option></select></div>
                  {provider === "mpesa_daraja" && <div className="form-row"><label htmlFor="billing-phone">M-PESA mobile number</label><input id="billing-phone" value={phone} onChange={(event) => setPhone(event.target.value)} placeholder="07XX XXX XXX" inputMode="tel" autoComplete="tel" /></div>}
                  <div className="form-actions"><Button type="button" disabled={paying} onClick={() => void payInvoice(paymentInvoiceId)}>{paying ? "Starting payment…" : `Continue with ${providerLabel(provider)}`}</Button><Button type="button" variant="ghost" disabled={paying} onClick={() => setPaymentInvoiceId(null)}>Cancel</Button></div>
                </div>
              )}
            </Panel>
          ) : (
            <Panel title="Billing action is restricted" subtitle="Commercial records are protected by tenant billing roles.">
              <p className="admin-muted">You can see whether the AMO account is locked, but invoice values, payment references, negotiated prices and recurring contract terms are visible only to the AMO Administrator, Finance Manager or Accounts Officer.</p>
              {paymentRequired && <InlineAlert tone="warning" title="Contact an authorised billing user"><span>Ask your AMO Administrator, Finance Manager or Accounts Officer to settle the outstanding account. Your operational records remain preserved while access is restricted.</span></InlineAlert>}
            </Panel>
          )}

          <div className="admin-page__side">
            <Panel title="Account status" compact>
              <p><strong>{access?.access_state || "Unknown"}</strong></p>
              <p className="admin-muted">{access?.lock_reason || "No account-level billing lock is active."}</p>
              {returnTo && access?.has_access && <Button type="button" size="sm" onClick={() => navigate(returnTo, { replace: true })}>Return to workspace</Button>}
            </Panel>
            <Panel title="Payment data protection" compact>
              <p className="admin-muted">Hosted Paystack/Stripe checkout and M-PESA STK keep sensitive authentication data away from AMO Portal. The portal retains only the invoice, opaque provider/transaction references and minimized settlement evidence required for reconciliation.</p>
            </Panel>
            <Panel title="Payment authority" compact>
              <p className="admin-muted">{canSubscribe ? "You may accept or cancel recurring module contracts for this AMO." : canPay ? "You may settle existing invoices but cannot bind the AMO to a new recurring contract." : "Commercial details are restricted. Contact an AMO administrator or finance billing user."}</p>
            </Panel>
          </div>
        </div>

        {canViewBillingDetails && !isSuperuser && (
          <>
            <div style={{ height: 18 }} />
            <Panel title="Subscribed modules" subtitle="Capabilities currently enabled for this AMO and their paid service periods.">
              {activeModules.length === 0 ? <p className="admin-muted">No self-service module subscription is currently recorded.</p> : (
                <div style={{ display: "grid", gridTemplateColumns: "repeat(auto-fit, minmax(250px, 1fr))", gap: 12 }}>
                  {activeModules.map((module) => (
                    <div key={module.code} style={{ border: "1px solid var(--border-color, #d8dde6)", borderRadius: 10, padding: 14 }}>
                      <strong>{module.name}</strong>
                      <p className="admin-muted" style={{ margin: "6px 0" }}>{module.description}</p>
                      <p style={{ margin: "6px 0" }}>{module.subscription_status || "ACTIVE"}{module.effective_to ? ` · through ${dateLabel(module.effective_to)}` : ""}</p>
                      {module.bundle_parent && <p className="admin-muted">Included through {module.bundle_parent}</p>}
                      {module.cancel_at_period_end && <p className="admin-muted">Cancellation scheduled; no further renewal will be generated.</p>}
                      {canSubscribe && module.is_root_contract && module.auto_renew && !module.cancel_at_period_end && <Button type="button" size="sm" variant="secondary" onClick={() => { setCancelModule(module); setCancelReason(""); }}>Cancel at period end</Button>}
                    </div>
                  ))}
                </div>
              )}
            </Panel>

            <div style={{ height: 18 }} />
            <Panel title="Add platform modules" subtitle="Choose only the capabilities your organisation needs. Technical dependencies and bundle contents are enforced before checkout.">
              {!catalog && !loading && <p className="admin-muted">The module catalog is unavailable.</p>}
              {catalog && availableModules.length === 0 && <p className="admin-muted">No additional customer-selectable modules are currently available.</p>}
              {catalog && availableModules.length > 0 && (
                <div style={{ display: "grid", gridTemplateColumns: "repeat(auto-fit, minmax(280px, 1fr))", gap: 14 }}>
                  {availableModules.map((module) => (
                    <div key={module.code} style={{ border: "1px solid var(--border-color, #d8dde6)", borderRadius: 12, padding: 16, display: "grid", gap: 10 }}>
                      <div><strong>{module.name}</strong><p className="admin-muted" style={{ margin: "6px 0 0" }}>{module.description}</p></div>
                      <div className="admin-muted">{module.kind.replace(/_/g, " ")}{module.included_modules?.length ? ` · includes ${module.included_modules.join(", ")}` : ""}</div>
                      {!!module.missing_dependencies?.length && <InlineAlert tone="warning" title="Requires other modules"><span>{module.missing_dependencies.join(", ")}</span></InlineAlert>}
                      {module.tenant_offer_expired && <InlineAlert tone="warning" title="Commercial offer expired"><span>Ask your platform administrator to issue updated terms.</span></InlineAlert>}
                      {module.prices?.length ? module.prices.map((price) => (
                        <div key={`${module.code}-${price.id}`} style={{ display: "flex", alignItems: "center", justifyContent: "space-between", gap: 10 }}>
                          <span>{money(price.amount_cents + Math.round(price.amount_cents * (price.tax_rate_bps || 0) / 10000), price.currency)} · {price.billing_term.replace(/_/g, " ").toLowerCase()}</span>
                          {canSubscribe && module.can_subscribe && <Button type="button" size="sm" onClick={() => { setCheckout({ module, price }); setTermsAccepted(false); }}>Select</Button>}
                        </div>
                      )) : <span className="admin-muted">No purchasable price is currently configured.</span>}
                    </div>
                  ))}
                </div>
              )}
            </Panel>
          </>
        )}

        {checkout && catalog?.terms && canSubscribe && (
          <>
            <div style={{ height: 18 }} />
            <Panel title={`Confirm ${checkout.module.name}`} subtitle="Review the full commercial terms before creating the invoice.">
              <div style={{ display: "grid", gridTemplateColumns: "repeat(auto-fit, minmax(190px, 1fr))", gap: 12, marginBottom: 16 }}>
                <div><span className="admin-muted">Subtotal</span><div><strong>{money(checkout.price.amount_cents, checkout.price.currency)}</strong></div></div>
                <div><span className="admin-muted">Tax</span><div><strong>{money(selectedTax, checkout.price.currency)}</strong></div></div>
                <div><span className="admin-muted">Total due now</span><div><strong>{money(selectedTotal, checkout.price.currency)}</strong></div></div>
                <div><span className="admin-muted">Renews</span><div><strong>{checkout.price.billing_term.replace(/_/g, " ").toLowerCase()}</strong></div></div>
              </div>
              <ul className="admin-muted" style={{ paddingLeft: 18 }}><li>{catalog.terms.recurring_billing}</li><li>{catalog.terms.price_disclosure}</li><li>{catalog.terms.non_payment}</li><li>{catalog.terms.cancellation}</li><li>{catalog.terms.records}</li></ul>
              <label style={{ display: "flex", gap: 10, alignItems: "flex-start", margin: "16px 0" }}><input type="checkbox" checked={termsAccepted} onChange={(event) => setTermsAccepted(event.target.checked)} /><span>I am authorised to bind this AMO and accept the displayed recurring price, tax and renewal interval under terms version <strong>{catalog.terms.version}</strong>.</span></label>
              <div className="form-actions"><Button type="button" disabled={ordering || !termsAccepted} onClick={() => void orderModule()}>{ordering ? "Creating order…" : "Create invoice"}</Button><Button type="button" variant="ghost" disabled={ordering} onClick={() => { setCheckout(null); setTermsAccepted(false); }}>Cancel</Button></div>
            </Panel>
          </>
        )}

        {cancelModule && canSubscribe && (
          <>
            <div style={{ height: 18 }} />
            <Panel title={`Cancel ${cancelModule.name} at period end`} subtitle="This stops future renewal; it does not erase records or cut off an already-paid period.">
              <div className="form-row"><label htmlFor="module-cancel-reason">Reason</label><textarea id="module-cancel-reason" value={cancelReason} onChange={(event) => setCancelReason(event.target.value)} placeholder="Commercial reason for the audit trail" /></div>
              <p className="admin-muted">Current paid access ends {dateLabel(cancelModule.effective_to)}. Included bundle capabilities must be cancelled through their parent contract.</p>
              <div className="form-actions"><Button type="button" disabled={cancelling || !cancelReason.trim()} onClick={() => void confirmCancellation()}>{cancelling ? "Recording…" : "Confirm cancellation"}</Button><Button type="button" variant="ghost" disabled={cancelling} onClick={() => setCancelModule(null)}>Keep subscription</Button></div>
            </Panel>
          </>
        )}
      </div>
    </DepartmentLayout>
  );
};

export default AdminBillingPage;
