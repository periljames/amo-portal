import React, { useCallback, useEffect, useMemo, useState } from "react";
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

type CheckoutSelection = {
  module: CommercialModule;
  price: ModulePrice;
};

const sleep = (ms: number) => new Promise((resolve) => window.setTimeout(resolve, ms));

function money(cents: number, currency = "USD") {
  try {
    return new Intl.NumberFormat(undefined, {
      style: "currency",
      currency,
      maximumFractionDigits: 2,
    }).format((Number(cents || 0)) / 100);
  } catch {
    return `${currency} ${(Number(cents || 0) / 100).toFixed(2)}`;
  }
}

function dateLabel(value?: string | null) {
  if (!value) return "—";
  const date = new Date(value);
  return Number.isNaN(date.getTime()) ? String(value) : date.toLocaleDateString();
}

function roleValue(user: ReturnType<typeof getCachedUser>) {
  const role = user?.role as unknown;
  if (role && typeof role === "object" && "value" in (role as Record<string, unknown>)) {
    return String((role as Record<string, unknown>).value || "").toUpperCase();
  }
  return String(role || "").toUpperCase();
}

function invoiceCommercial(invoice: Invoice): Record<string, unknown> {
  if (!invoice.description) return {};
  try {
    const value = JSON.parse(invoice.description) as unknown;
    return value && typeof value === "object" ? value as Record<string, unknown> : {};
  } catch {
    return {};
  }
}

function invoiceLabel(invoice: Invoice) {
  const commercial = invoiceCommercial(invoice);
  return String(
    commercial.module_name
    || commercial.module_code
    || commercial.description
    || invoice.description
    || "Platform subscription",
  ).replace(/_/g, " ");
}

function providerLabel(provider: PaymentProvider) {
  return provider === "paystack" ? "Paystack" : "M-PESA";
}

const AdminBillingPage: React.FC = () => {
  const { amoCode } = useParams<UrlParams>();
  const navigate = useNavigate();
  const location = useLocation();
  const currentUser = useMemo(() => getCachedUser(), []);
  const role = roleValue(currentUser);
  const isSuperuser = Boolean(currentUser?.is_superuser);
  const canSubscribe = !isSuperuser && (Boolean(currentUser?.is_amo_admin) || ["AMO_ADMIN", "FINANCE_MANAGER"].includes(role));
  const canPay = !isSuperuser && (Boolean(currentUser?.is_amo_admin) || ["AMO_ADMIN", "FINANCE_MANAGER", "ACCOUNTS_OFFICER"].includes(role));

  const [access, setAccess] = useState<BillingAccessStatus | null>(null);
  const [invoices, setInvoices] = useState<Invoice[]>([]);
  const [catalog, setCatalog] = useState<SelfServiceCatalog | null>(null);
  const [loading, setLoading] = useState(true);
  const [refreshing, setRefreshing] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [notice, setNotice] = useState<string | null>(null);
  const [checkout, setCheckout] = useState<CheckoutSelection | null>(null);
  const [acceptedTerms, setAcceptedTerms] = useState(false);
  const [creatingOrder, setCreatingOrder] = useState(false);
  const [paymentInvoiceId, setPaymentInvoiceId] = useState<string | null>(null);
  const [provider, setProvider] = useState<PaymentProvider>("paystack");
  const [phone, setPhone] = useState("");
  const [paying, setPaying] = useState(false);

  const query = useMemo(() => new URLSearchParams(location.search), [location.search]);
  const returnTo = query.get("returnTo") || (location.state as { from?: string } | null)?.from || null;
  const paymentRequired = query.get("reason") === "payment_required" || Boolean(access?.redirect_to_billing && !access?.has_access);

  const load = useCallback(async (quiet = false) => {
    if (quiet) setRefreshing(true);
    else setLoading(true);
    setError(null);
    try {
      const [nextAccess, nextInvoices] = await Promise.all([
        fetchBillingAccessStatus(),
        fetchInvoices(),
      ]);
      setAccess(nextAccess);
      setInvoices(nextInvoices);
      if (!isSuperuser) {
        const nextCatalog = await fetchSelfServiceModuleCatalog();
        setCatalog(nextCatalog);
      }
      return nextAccess;
    } catch (err: any) {
      setError(err?.message || "Unable to load billing information.");
      return null;
    } finally {
      setLoading(false);
      setRefreshing(false);
    }
  }, [isSuperuser]);

  useEffect(() => {
    void load();
  }, [load]);

  const pendingInvoices = useMemo(
    () => invoices.filter((invoice) => String(invoice.status).toUpperCase() === "PENDING"),
    [invoices],
  );

  const outstandingByCurrency = useMemo(() => {
    const totals = new Map<string, number>();
    for (const invoice of pendingInvoices) {
      const currency = String(invoice.currency || "USD").toUpperCase();
      totals.set(currency, (totals.get(currency) || 0) + Number(invoice.total_cents ?? invoice.amount_cents ?? 0));
    }
    return Array.from(totals.entries()).sort(([a], [b]) => a.localeCompare(b));
  }, [pendingInvoices]);

  const activeModules = useMemo(
    () => catalog?.items.filter((module) => module.is_active_for_tenant) ?? [],
    [catalog],
  );
  const availableModules = useMemo(
    () => catalog?.items.filter((module) => !module.is_active_for_tenant) ?? [],
    [catalog],
  );

  const downloadInvoice = async (invoice: Invoice) => {
    setError(null);
    try {
      saveDownloadedFile(await fetchInvoiceDocument(invoice.id, "pdf"));
    } catch (err: any) {
      setError(err?.message || "Unable to download invoice PDF.");
    }
  };

  const createOrder = async () => {
    if (!checkout || !catalog?.terms) return;
    if (!acceptedTerms) {
      setError("You must expressly accept the displayed recurring billing terms before subscribing.");
      return;
    }
    setCreatingOrder(true);
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
      setPaymentInvoiceId(invoice.id);
      setNotice("Subscription order created. Payment must be verified before the module is activated.");
      setCheckout(null);
      setAcceptedTerms(false);
      await load(true);
    } catch (err: any) {
      setError(err?.message || "Unable to create the module subscription order.");
    } finally {
      setCreatingOrder(false);
    }
  };

  const waitForPaymentJob = async (jobId: string) => {
    for (let attempt = 0; attempt < 30; attempt += 1) {
      const job = await fetchTenantPaymentJob(jobId);
      const state = String(job.status || "").toUpperCase();
      if (state === "SUCCEEDED") return job;
      if (["FAILED", "DEAD", "CANCELLED"].includes(state)) {
        throw new Error(job.last_error || "Payment request could not be completed.");
      }
      await sleep(700);
    }
    return null;
  };

  const waitForSettlement = async (invoiceId: string) => {
    for (let attempt = 0; attempt < 45; attempt += 1) {
      await sleep(1200);
      const next = await load(true);
      const current = (await fetchInvoices()).find((row) => row.id === invoiceId);
      if (current && String(current.status).toUpperCase() === "PAID") {
        if (returnTo && next?.has_access) {
          navigate(returnTo, { replace: true });
        }
        return true;
      }
    }
    return false;
  };

  const payInvoice = async (invoiceId: string) => {
    if (!canPay) {
      setError("Your account may view billing but is not authorised to initiate payments.");
      return;
    }
    if (provider === "mpesa_daraja" && !phone.trim()) {
      setError("Enter the Kenyan mobile number that should receive the M-PESA STK prompt.");
      return;
    }
    setPaying(true);
    setPaymentInvoiceId(invoiceId);
    setError(null);
    setNotice(null);
    try {
      const accepted = await initiateTenantInvoicePayment(invoiceId, {
        provider,
        phone: provider === "mpesa_daraja" ? phone.trim() : undefined,
      });
      const job = await waitForPaymentJob(accepted.id);
      if (job?.result && provider === "paystack") {
        const authorizationUrl = String(job.result.authorization_url || "").trim();
        if (!authorizationUrl) throw new Error("Paystack checkout was created without an authorization URL.");
        window.location.assign(authorizationUrl);
        return;
      }
      if (provider === "mpesa_daraja") {
        setNotice("M-PESA request sent. Approve the STK prompt on the selected phone. Access restores only after Safaricom settlement is verified.");
        const settled = await waitForSettlement(invoiceId);
        if (!settled) {
          setNotice("Payment is still pending verification. You can refresh this page after completing the STK prompt; access will restore automatically when settlement is confirmed.");
        }
      } else if (!job) {
        setNotice("Payment initialization is still processing. Refresh Billing before retrying; duplicate payment requests are idempotency-protected.");
      }
    } catch (err: any) {
      setError(err?.message || "Unable to initiate payment.");
    } finally {
      setPaying(false);
    }
  };

  const selectedTax = checkout ? Math.round(checkout.price.amount_cents * Number(checkout.price.tax_rate_bps || 0) / 10_000) : 0;
  const selectedTotal = checkout ? checkout.price.amount_cents + selectedTax : 0;

  return (
    <DepartmentLayout amoCode={amoCode ?? "UNKNOWN"} activeDepartment="admin-billing">
      <div className="admin-page admin-billing">
        <PageHeader
          title="Billing & subscriptions"
          subtitle="Invoices, payments, subscribed modules and available platform capabilities for this AMO."
          actions={
            <Button type="button" size="sm" variant="secondary" disabled={refreshing} onClick={() => void load(true)}>
              {refreshing ? "Refreshing…" : "Refresh"}
            </Button>
          }
        />

        {paymentRequired && (
          <InlineAlert tone="danger" title="Payment required to restore platform access">
            <span>{access?.lock_reason || "This account has an overdue billing obligation."} Billing and invoice records remain available so an authorised user can settle the account.</span>
          </InlineAlert>
        )}
        {error && <InlineAlert tone="danger" title="Billing action failed"><span>{error}</span></InlineAlert>}
        {notice && <InlineAlert tone="info" title="Billing update"><span>{notice}</span></InlineAlert>}

        <div className="admin-summary-strip">
          <div className="admin-summary-item">
            <span className="admin-summary-item__label">Access</span>
            <span className="admin-summary-item__value">{access?.access_state || (loading ? "Loading…" : "Unknown")}</span>
          </div>
          <div className="admin-summary-item">
            <span className="admin-summary-item__label">Subscribed modules</span>
            <span className="admin-summary-item__value">{activeModules.length}</span>
          </div>
          <div className="admin-summary-item">
            <span className="admin-summary-item__label">Open invoices</span>
            <span className="admin-summary-item__value">{pendingInvoices.length}</span>
          </div>
          <div className="admin-summary-item">
            <span className="admin-summary-item__label">Outstanding</span>
            <span className="admin-summary-item__value">
              {outstandingByCurrency.length ? outstandingByCurrency.map(([currency, cents]) => money(cents, currency)).join(" · ") : "None"}
            </span>
          </div>
        </div>

        <div className="admin-page__grid">
          <Panel
            title={paymentRequired ? "Settle outstanding billing" : "Invoices & payments"}
            subtitle="Only verified provider settlement changes invoice or access state."
          >
            {loading && <p className="admin-muted">Loading billing records…</p>}
            {!loading && invoices.length === 0 && <p className="admin-muted">No invoices have been issued to this AMO.</p>}
            {!loading && invoices.length > 0 && (
              <Table>
                <thead>
                  <tr>
                    <th>Invoice</th>
                    <th>For</th>
                    <th>Status</th>
                    <th>Due</th>
                    <th>Total</th>
                    <th>Actions</th>
                  </tr>
                </thead>
                <tbody>
                  {invoices.map((invoice) => (
                    <tr key={invoice.id} style={access?.actionable_invoice_id === invoice.id ? { fontWeight: 700 } : undefined}>
                      <td>{invoice.invoice_number || invoice.id.slice(-8).toUpperCase()}</td>
                      <td>{invoiceLabel(invoice)}</td>
                      <td>{invoice.status}</td>
                      <td>{dateLabel(invoice.due_at)}</td>
                      <td>{money(invoice.total_cents ?? invoice.amount_cents, invoice.currency)}</td>
                      <td>
                        <div className="page-section__actions">
                          <Button type="button" size="sm" variant="secondary" onClick={() => navigate(`/maintenance/${amoCode}/admin/invoices/${invoice.id}`)}>
                            View
                          </Button>
                          <Button type="button" size="sm" variant="secondary" onClick={() => void downloadInvoice(invoice)}>
                            PDF
                          </Button>
                          {String(invoice.status).toUpperCase() === "PENDING" && canPay && (
                            <Button type="button" size="sm" onClick={() => setPaymentInvoiceId(invoice.id)}>
                              Pay
                            </Button>
                          )}
                        </div>
                      </td>
                    </tr>
                  ))}
                </tbody>
              </Table>
            )}

            {paymentInvoiceId && pendingInvoices.some((row) => row.id === paymentInvoiceId) && (
              <div style={{ marginTop: 18, paddingTop: 16, borderTop: "1px solid var(--border-color, #d8dde6)" }}>
                <h3 style={{ marginTop: 0 }}>Process payment</h3>
                <p className="admin-muted">Choose the payment rail. The portal does not mark the invoice paid until the provider confirms the settlement.</p>
                <div className="form-row">
                  <label htmlFor="billing-provider">Payment method</label>
                  <select id="billing-provider" value={provider} onChange={(event) => setProvider(event.target.value as PaymentProvider)}>
                    <option value="paystack">Paystack — card/bank checkout</option>
                    <option value="mpesa_daraja">M-PESA — STK Push</option>
                  </select>
                </div>
                {provider === "mpesa_daraja" && (
                  <div className="form-row">
                    <label htmlFor="billing-phone">M-PESA mobile number</label>
                    <input id="billing-phone" value={phone} onChange={(event) => setPhone(event.target.value)} placeholder="07XX XXX XXX" inputMode="tel" />
                  </div>
                )}
                <div className="form-actions">
                  <Button type="button" disabled={paying} onClick={() => void payInvoice(paymentInvoiceId)}>
                    {paying ? "Starting payment…" : `Continue with ${providerLabel(provider)}`}
                  </Button>
                  <Button type="button" variant="ghost" disabled={paying} onClick={() => setPaymentInvoiceId(null)}>Cancel</Button>
                </div>
              </div>
            )}
          </Panel>

          <div className="admin-page__side">
            <Panel title="Account status" compact>
              <p><strong>{access?.access_state || "Unknown"}</strong></p>
              <p className="admin-muted">{access?.lock_reason || "No account-level billing lock is active."}</p>
              {returnTo && access?.has_access && (
                <Button type="button" size="sm" onClick={() => navigate(returnTo, { replace: true })}>Return to workspace</Button>
              )}
            </Panel>
            <Panel title="Payment authority" compact>
              <p className="admin-muted">
                {canSubscribe
                  ? "You may accept recurring module subscriptions for this AMO."
                  : canPay
                    ? "You may settle existing invoices but cannot create a new recurring module contract."
                    : "Billing is visible for transparency; an AMO administrator or authorised finance user must make changes."}
              </p>
            </Panel>
          </div>
        </div>

        {!isSuperuser && (
          <>
            <div style={{ height: 18 }} />
            <Panel title="Subscribed modules" subtitle="Capabilities currently enabled for this AMO.">
              {activeModules.length === 0 ? (
                <p className="admin-muted">No self-service module subscription is currently recorded.</p>
              ) : (
                <div style={{ display: "grid", gridTemplateColumns: "repeat(auto-fit, minmax(240px, 1fr))", gap: 12 }}>
                  {activeModules.map((module) => (
                    <div key={module.code} style={{ border: "1px solid var(--border-color, #d8dde6)", borderRadius: 10, padding: 14 }}>
                      <strong>{module.name}</strong>
                      <p className="admin-muted" style={{ marginBottom: 8 }}>{module.description}</p>
                      <span>{module.subscription_status || "ACTIVE"}</span>
                    </div>
                  ))}
                </div>
              )}
            </Panel>

            <div style={{ height: 18 }} />
            <Panel title="Add platform modules" subtitle="Choose only the capabilities your organisation needs. Technical dependencies are enforced before checkout.">
              {!catalog && !loading && <p className="admin-muted">The module catalog is unavailable.</p>}
              {catalog && availableModules.length === 0 && <p className="admin-muted">No additional customer-selectable modules are currently available.</p>}
              {catalog && availableModules.length > 0 && (
                <div style={{ display: "grid", gridTemplateColumns: "repeat(auto-fit, minmax(280px, 1fr))", gap: 14 }}>
                  {availableModules.map((module) => (
                    <div key={module.code} style={{ border: "1px solid var(--border-color, #d8dde6)", borderRadius: 12, padding: 16, display: "grid", gap: 10 }}>
                      <div>
                        <span className="admin-muted" style={{ textTransform: "uppercase", fontSize: 11 }}>{module.kind.replace(/_/g, " ")}</span>
                        <h3 style={{ margin: "4px 0 6px" }}>{module.name}</h3>
                        <p className="admin-muted" style={{ margin: 0 }}>{module.description}</p>
                      </div>
                      {module.included_modules.length > 0 && <div><strong>Includes:</strong> {module.included_modules.join(", ").replace(/_/g, " ")}</div>}
                      {module.hard_requires.length > 0 && <div><strong>Requires:</strong> {module.hard_requires.join(", ").replace(/_/g, " ")}</div>}
                      {(module.missing_dependencies?.length || 0) > 0 && (
                        <InlineAlert tone="warning" title="Dependency required">
                          <span>Activate {module.missing_dependencies?.join(", ").replace(/_/g, " ")} first, or choose a bundle that includes them.</span>
                        </InlineAlert>
                      )}
                      {(module.prices || []).length === 0 ? (
                        <p className="admin-muted">No customer price has been published for this module.</p>
                      ) : (
                        <div style={{ display: "grid", gap: 8 }}>
                          {(module.prices || []).map((price) => {
                            const tax = Math.round(price.amount_cents * Number(price.tax_rate_bps || 0) / 10_000);
                            return (
                              <div key={`${module.code}-${price.id}`} style={{ display: "flex", justifyContent: "space-between", gap: 10, alignItems: "center" }}>
                                <div>
                                  <strong>{money(price.amount_cents + tax, price.currency)}</strong>
                                  <div className="admin-muted">{price.billing_term.replace(/_/g, " ").toLowerCase()} · tax {price.tax_rate_bps ? `${(price.tax_rate_bps / 100).toFixed(2)}%` : "0%"}{price.tenant_override ? " · negotiated rate" : ""}</div>
                                </div>
                                {canSubscribe && (
                                  <Button type="button" size="sm" disabled={!module.can_subscribe} onClick={() => { setCheckout({ module, price }); setAcceptedTerms(false); }}>
                                    Subscribe
                                  </Button>
                                )}
                              </div>
                            );
                          })}
                        </div>
                      )}
                    </div>
                  ))}
                </div>
              )}
            </Panel>
          </>
        )}

        {checkout && catalog?.terms && (
          <div style={{ height: 18 }} />
          <Panel title={`Confirm ${checkout.module.name}`} subtitle="Review the complete commercial terms before creating the invoice.">
            <div style={{ display: "grid", gridTemplateColumns: "repeat(auto-fit, minmax(190px, 1fr))", gap: 12, marginBottom: 16 }}>
              <div><span className="admin-muted">Subtotal</span><div><strong>{money(checkout.price.amount_cents, checkout.price.currency)}</strong></div></div>
              <div><span className="admin-muted">Tax</span><div><strong>{money(selectedTax, checkout.price.currency)}</strong></div></div>
              <div><span className="admin-muted">Total due now</span><div><strong>{money(selectedTotal, checkout.price.currency)}</strong></div></div>
              <div><span className="admin-muted">Renews</span><div><strong>{checkout.price.billing_term.replace(/_/g, " ").toLowerCase()}</strong></div></div>
            </div>
            <ul className="admin-muted" style={{ paddingLeft: 18 }}>
              <li>{catalog.terms.recurring_billing}</li>
              <li>{catalog.terms.non_payment}</li>
              <li>{catalog.terms.cancellation}</li>
              <li>{catalog.terms.records}</li>
            </ul>
            <label style={{ display: "flex", alignItems: "flex-start", gap: 10, marginTop: 14 }}>
              <input type="checkbox" checked={acceptedTerms} onChange={(event) => setAcceptedTerms(event.target.checked)} />
              <span>I am authorised to bind this AMO and expressly accept the displayed price, tax, renewal interval and recurring billing terms (version {catalog.terms.version}).</span>
            </label>
            <div className="form-actions" style={{ marginTop: 14 }}>
              <Button type="button" disabled={!acceptedTerms || creatingOrder} onClick={() => void createOrder()}>
                {creatingOrder ? "Creating invoice…" : "Create invoice & continue to payment"}
              </Button>
              <Button type="button" variant="ghost" disabled={creatingOrder} onClick={() => { setCheckout(null); setAcceptedTerms(false); }}>Cancel</Button>
            </div>
          </Panel>
        )}
      </div>
    </DepartmentLayout>
  );
};

export default AdminBillingPage;
