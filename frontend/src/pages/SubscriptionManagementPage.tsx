import React, { useEffect, useMemo, useState } from "react";
import { useNavigate, useParams } from "react-router-dom";
import DepartmentLayout from "../components/Layout/DepartmentLayout";
import { getCachedUser } from "../services/auth";
import {
  addPaymentMethod,
  cancelSubscription,
  fetchCatalog,
  fetchEntitlements,
  fetchInvoices,
  fetchPaymentMethods,
  fetchSubscription,
  fetchUsageMeters,
  purchaseSubscription,
  removePaymentMethod,
  startTrial,
} from "../services/billing";
import type {
  CatalogSKU,
  Invoice,
  PaymentMethod,
  ResolvedEntitlement,
  Subscription,
  UsageMeter,
} from "../types/billing";

type UrlParams = {
  amoCode?: string;
};

type PaymentFormState = {
  provider: PaymentMethod["provider"];
  displayName: string;
  externalRef: string;
  cardLast4: string;
  expMonth: string;
  expYear: string;
  isDefault: boolean;
};

const formatMoney = (amountCents: number, currency = "USD"): string => {
  return new Intl.NumberFormat("en-US", {
    style: "currency",
    currency,
    minimumFractionDigits: 0,
    maximumFractionDigits: 0,
  }).format(amountCents / 100);
};

const formatDate = (value?: string | null): string => {
  if (!value) return "—";
  const d = new Date(value);
  return d.toLocaleDateString("en-US", {
    month: "short",
    day: "numeric",
    year: "numeric",
  });
};

function lowercaseMatch(value: string, term: string): boolean {
  return value.toLowerCase().includes(term.toLowerCase());
}

const SubscriptionManagementPage: React.FC = () => {
  const { amoCode } = useParams<UrlParams>();
  const navigate = useNavigate();

  const currentUser = useMemo(() => getCachedUser(), []);
  const isTenantAdmin = !!currentUser?.is_superuser || !!currentUser?.is_amo_admin;

  const [catalog, setCatalog] = useState<CatalogSKU[]>([]);
  const [subscription, setSubscription] = useState<Subscription | null>(null);
  const [entitlements, setEntitlements] = useState<ResolvedEntitlement[]>([]);
  const [usageMeters, setUsageMeters] = useState<UsageMeter[]>([]);
  const [paymentMethods, setPaymentMethods] = useState<PaymentMethod[]>([]);
  const [invoices, setInvoices] = useState<Invoice[]>([]);

  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [notice, setNotice] = useState<string | null>(null);
  const [scaCue, setScaCue] = useState<string | null>(null);

  const [changePlanOpen, setChangePlanOpen] = useState(false);
  const [cancelModalOpen, setCancelModalOpen] = useState(false);
  const [paymentModalOpen, setPaymentModalOpen] = useState(false);
  const [selectedSkuId, setSelectedSkuId] = useState<string>("");
  const [selectedPaymentMethodId, setSelectedPaymentMethodId] = useState<
    string | undefined
  >(undefined);

  const [paymentForm, setPaymentForm] = useState<PaymentFormState>({
    provider: "STRIPE",
    displayName: "",
    externalRef: "",
    cardLast4: "",
    expMonth: "",
    expYear: "",
    isDefault: true,
  });

  const [processingPayment, setProcessingPayment] = useState(false);
  const [removingPaymentId, setRemovingPaymentId] = useState<string | null>(null);

  useEffect(() => {
    if (!currentUser) return;
    if (isTenantAdmin) return;

    if (amoCode) {
      navigate(`/maintenance/${amoCode}/admin/overview`, { replace: true });
      return;
    }
    navigate("/login", { replace: true });
  }, [amoCode, currentUser, isTenantAdmin, navigate]);

  const loadBillingData = async () => {
    setLoading(true);
    setError(null);
    try {
      const [
        catalogData,
        subscriptionData,
        entitlementsData,
        metersData,
        paymentData,
        invoiceData,
      ] = await Promise.all([
        fetchCatalog(),
        fetchSubscription(),
        fetchEntitlements(),
        fetchUsageMeters(),
        fetchPaymentMethods(),
        fetchInvoices(),
      ]);

      setCatalog(catalogData);
      setSubscription(subscriptionData);
      setEntitlements(entitlementsData);
      setUsageMeters(metersData);
      setPaymentMethods(paymentData);
      setInvoices(invoiceData);
      setSelectedPaymentMethodId(
        paymentData.find((pm) => pm.is_default)?.id || paymentData[0]?.id
      );

      if (subscriptionData && subscriptionData.sku_id) {
        const altSku =
          catalogData.find((sku) => sku.id !== subscriptionData.sku_id) ||
          catalogData[0];
        setSelectedSkuId(altSku?.id || "");
      } else if (catalogData[0]) {
        setSelectedSkuId(catalogData[0].id);
      }
    } catch (err: any) {
      console.error("Failed to load billing data", err);
      setError(err?.message || "Unable to load billing data.");
    } finally {
      setLoading(false);
    }
  };

  useEffect(() => {
    loadBillingData();
  }, []);

  const currentSku = useMemo(
    () => catalog.find((sku) => sku.id === subscription?.sku_id),
    [catalog, subscription?.sku_id]
  );

  const targetSku = useMemo(
    () =>
      catalog.find(
        (sku) => sku.id === selectedSkuId || sku.code === selectedSkuId
      ),
    [catalog, selectedSkuId]
  );

  const selectedPaymentMethod = useMemo(
    () =>
      paymentMethods.find((pm) => pm.id === selectedPaymentMethodId) ||
      paymentMethods.find((pm) => pm.is_default),
    [paymentMethods, selectedPaymentMethodId]
  );

  const seatEntitlement = useMemo(
    () =>
      entitlements.find(
        (e) =>
          lowercaseMatch(e.key, "seat") ||
          lowercaseMatch(e.key, "user") ||
          lowercaseMatch(e.key, "member")
      ),
    [entitlements]
  );

  const seatUsage = useMemo(
    () =>
      usageMeters.find(
        (m) =>
          lowercaseMatch(m.meter_key, "seat") ||
          lowercaseMatch(m.meter_key, "user") ||
          lowercaseMatch(m.meter_key, "member")
      )?.used_units || 0,
    [usageMeters]
  );

  const usageLimits: Record<string, number | null> = useMemo(() => {
    const limits: Record<string, number | null> = {};
    entitlements.forEach((ent) => {
      limits[ent.key] = ent.is_unlimited ? null : ent.limit ?? null;
    });
    return limits;
  }, [entitlements]);

  const trialDaysRemaining = useMemo(() => {
    if (!subscription?.trial_ends_at) return null;
    const end = new Date(subscription.trial_ends_at).getTime();
    const now = Date.now();
    return Math.max(0, Math.ceil((end - now) / (1000 * 60 * 60 * 24)));
  }, [subscription?.trial_ends_at]);

  const prorationPreview = useMemo(() => {
    if (!targetSku) return null;
    if (!subscription || !currentSku) {
      return {
        label: "New purchase",
        creditCents: 0,
        chargeCents: targetSku.amount_cents,
        currency: targetSku.currency,
        remainingDays: null,
        totalDays: null,
      };
    }

    const now = Date.now();
    const start = new Date(subscription.current_period_start).getTime();
    const end = subscription.current_period_end
      ? new Date(subscription.current_period_end).getTime()
      : start;

    const totalMs = Math.max(end - start, 1);
    const remainingMs = Math.max(end - now, 0);
    const remainingRatio = Math.min(1, remainingMs / totalMs);
    const credit = Math.round((currentSku.amount_cents || 0) * remainingRatio);
    const charge = Math.max(targetSku.amount_cents - credit, 0);

    return {
      label: "Proration preview",
      creditCents: credit,
      chargeCents: charge,
      currency: targetSku.currency,
      remainingDays: Math.round(remainingMs / (1000 * 60 * 60 * 24)),
      totalDays: Math.round(totalMs / (1000 * 60 * 60 * 24)),
    };
  }, [targetSku, subscription, currentSku]);

  const needsSca =
    selectedPaymentMethod &&
    selectedPaymentMethod.provider !== "OFFLINE" &&
    selectedPaymentMethod.provider !== "MANUAL";

  const handlePurchase = async () => {
    if (!targetSku) {
      setError("Please choose a plan or module to continue.");
      return;
    }
    setProcessingPayment(true);
    setError(null);
    setNotice(null);
    setScaCue(
      needsSca
        ? "Security step: expect an SCA/3DS prompt from your bank to approve this change."
        : null
    );
    try {
      const updated = await purchaseSubscription(
        targetSku.code,
        targetSku.amount_cents,
        targetSku.currency,
        "PLAN_CHANGE"
      );
      setSubscription(updated);
      setNotice("Plan updated successfully. New entitlements are now active.");
      setChangePlanOpen(false);
      await loadBillingData();
    } catch (err: any) {
      setError(err?.message || "Unable to change the plan right now.");
    } finally {
      setProcessingPayment(false);
    }
  };

  const handleCancelPlan = async () => {
    if (!subscription) return;
    setProcessingPayment(true);
    setError(null);
    setNotice(null);
    setScaCue(
      subscription.current_period_end
        ? "Cancellation scheduled; access remains until the current period ends."
        : null
    );
    try {
      const effectiveDate = subscription.current_period_end
        ? new Date(subscription.current_period_end)
        : new Date();
      const updated = await cancelSubscription(effectiveDate);
      setSubscription(updated);
      setNotice("Cancellation recorded. You can renew or upgrade at any time.");
      setCancelModalOpen(false);
      await loadBillingData();
    } catch (err: any) {
      setError(err?.message || "Could not cancel the subscription.");
    } finally {
      setProcessingPayment(false);
    }
  };

  const handleStartTrial = async () => {
    if (!targetSku) return;
    setProcessingPayment(true);
    setError(null);
    setNotice(null);
    try {
      const trial = await startTrial(targetSku.code);
      setSubscription(trial);
      setNotice("Trial activated. Enjoy your evaluation period!");
      await loadBillingData();
    } catch (err: any) {
      setError(err?.message || "Unable to start a trial right now.");
    } finally {
      setProcessingPayment(false);
    }
  };

  const handleAddPaymentMethod = async (e: React.FormEvent) => {
    e.preventDefault();
    if (!currentUser?.amo_id) {
      setError("Missing AMO context for this user.");
      return;
    }

    setProcessingPayment(true);
    setError(null);
    setNotice(null);
    try {
      const created = await addPaymentMethod({
        amo_id: currentUser.amo_id,
        provider: paymentForm.provider,
        external_ref: paymentForm.externalRef.trim() || "psp-token",
        display_name: paymentForm.displayName.trim() || "Payment method",
        card_last4: paymentForm.cardLast4.trim() || undefined,
        card_exp_month: paymentForm.expMonth ? Number(paymentForm.expMonth) : undefined,
        card_exp_year: paymentForm.expYear ? Number(paymentForm.expYear) : undefined,
        is_default: paymentForm.isDefault,
      });
      setPaymentMethods((prev) => [created, ...prev]);
      setSelectedPaymentMethodId(created.id);
      setPaymentModalOpen(false);
      setNotice("Payment method saved and ready for billing.");
    } catch (err: any) {
      setError(err?.message || "Could not add the payment method.");
    } finally {
      setProcessingPayment(false);
    }
  };

  const handleRemovePaymentMethod = async (id: string) => {
    setRemovingPaymentId(id);
    setError(null);
    setNotice(null);
    try {
      await removePaymentMethod(id);
      setPaymentMethods((prev) => prev.filter((pm) => pm.id !== id));
      if (selectedPaymentMethodId === id) {
        setSelectedPaymentMethodId(
          paymentMethods.find((pm) => pm.id !== id)?.id || undefined
        );
      }
    } catch (err: any) {
      setError(err?.message || "Unable to remove the payment method.");
    } finally {
      setRemovingPaymentId(null);
    }
  };

  const usageMeterRows = useMemo(() => {
    return usageMeters.map((meter) => {
      const limit = usageLimits[meter.meter_key] ?? null;
      const remaining = limit !== null ? Math.max(limit - meter.used_units, 0) : null;
      const percent =
        limit !== null && limit > 0
          ? Math.min(100, Math.round((meter.used_units / limit) * 100))
          : null;
      return { meter, limit, remaining, percent };
    });
  }, [usageMeters, usageLimits]);

  if (currentUser && !isTenantAdmin) {
    return null;
  }

  const showTrialCta =
    !subscription ||
    subscription.status === "CANCELLED" ||
    subscription.status === "EXPIRED";

  return (
    <DepartmentLayout amoCode={amoCode ?? "UNKNOWN"} activeDepartment="admin-billing">
      <header className="page-header">
        <h1 className="page-header__title">Subscription & Billing</h1>
        <p className="page-header__subtitle">
          Manage plan changes, entitlements, payment methods, and compliance-friendly
          billing records.
        </p>
      </header>

      <div className="page-layout">
        {error && (
          <div className="card card--error">
            <strong>Something went wrong:</strong> {error}
          </div>
        )}
        {notice && (
          <div className="card card--success">
            <strong>Updated:</strong> {notice}
          </div>
        )}
        {scaCue && (
          <div className="card card--warning">
            <strong>Security check:</strong> {scaCue}
          </div>
        )}

        <section className="page-section subscription-grid">
          <div className="card card--form">
            <div className="card-header">
              <div>
                <p className="text-muted" style={{ margin: 0 }}>
                  Current plan
                </p>
                <h3 style={{ margin: "6px 0" }}>
                  {currentSku?.name || "No active subscription"}
                </h3>
                <p className="text-muted" style={{ margin: 0 }}>
                  {subscription
                    ? `${subscription.status} · ${currentSku?.term || subscription.term}`
                    : "Select a plan to unlock billing controls"}
                </p>
              </div>
              <div className="page-section__actions">
                <button
                  className="btn btn-primary"
                  onClick={() => setChangePlanOpen(true)}
                  disabled={loading || processingPayment}
                >
                  Upgrade / Downgrade
                </button>
                <button
                  className="btn btn-secondary"
                  onClick={() => setCancelModalOpen(true)}
                  disabled={!subscription || processingPayment}
                >
                  Cancel plan
                </button>
              </div>
            </div>
            <div className="summary-stats">
              <div className="summary-stat">
                <p className="text-muted">Renewal / period end</p>
                <strong>{formatDate(subscription?.current_period_end)}</strong>
              </div>
              <div className="summary-stat">
                <p className="text-muted">Trial status</p>
                <strong>
                  {subscription?.status === "TRIALING"
                    ? `${trialDaysRemaining ?? 0} days left`
                    : showTrialCta
                    ? "No trial in progress"
                    : "Active"}
                </strong>
              </div>
              <div className="summary-stat">
                <p className="text-muted">Seat allocation</p>
                <strong>
                  {seatEntitlement?.is_unlimited
                    ? `${seatUsage} used · unlimited`
                    : seatEntitlement?.limit
                    ? `${seatUsage}/${seatEntitlement.limit}`
                    : `${seatUsage} seats tracked`}
                </strong>
              </div>
              <div className="summary-stat">
                <p className="text-muted">Default payment method</p>
                <strong>
                  {selectedPaymentMethod
                    ? selectedPaymentMethod.display_name ||
                      selectedPaymentMethod.external_ref
                    : "Add a payment method"}
                </strong>
              </div>
            </div>
            {showTrialCta && (
              <div className="info-banner info-banner--soft">
                <div>
                  <strong>Trial or reactivation</strong>
                  <p className="text-muted" style={{ margin: 0 }}>
                    Start a trial or repurchase to regain entitlements. Buttons lock
                    during processing for idempotency.
                  </p>
                </div>
                <button
                  className="btn btn-primary"
                  onClick={handleStartTrial}
                  disabled={!targetSku || processingPayment}
                >
                  Start trial
                </button>
              </div>
            )}
          </div>

          <div className="card">
            <div className="card-header">
              <h3 style={{ margin: 0 }}>Entitlements</h3>
              <span className="badge">
                {entitlements.length ? `${entitlements.length} keys` : "No entitlements"}
              </span>
            </div>
            <div className="entitlement-grid">
              {entitlements.length === 0 && (
                <p className="text-muted">No entitlements are active for this tenant.</p>
              )}
              {entitlements.map((entitlement) => (
                <div key={entitlement.key} className="entitlement-chip">
                  <div>
                    <strong>{entitlement.key}</strong>
                    <p className="text-muted" style={{ margin: 0 }}>
                      {entitlement.is_unlimited
                        ? "Unlimited"
                        : entitlement.limit ?? "Not set"}{" "}
                      · {entitlement.license_term.toLowerCase()}
                    </p>
                  </div>
                  <span
                    className={
                      entitlement.license_status === "ACTIVE"
                        ? "badge badge--success"
                        : "badge"
                    }
                  >
                    {entitlement.license_status.toLowerCase()}
                  </span>
                </div>
              ))}
            </div>
          </div>

          <div className="card">
            <div className="card-header">
              <h3 style={{ margin: 0 }}>Usage meters</h3>
              <span className="badge">
                {usageMeters.length ? `${usageMeters.length} meters` : "No meters yet"}
              </span>
            </div>
            <div className="usage-grid">
              {usageMeters.length === 0 && (
                <p className="text-muted">No usage has been recorded yet.</p>
              )}
              {usageMeterRows.map(({ meter, limit, remaining, percent }) => (
                <div key={meter.id} className="usage-meter">
                  <div className="usage-meter__row">
                    <div>
                      <strong>{meter.meter_key}</strong>
                      <p className="text-muted" style={{ margin: 0 }}>
                        {limit !== null
                          ? `${meter.used_units}/${limit} used`
                          : `${meter.used_units} used`}
                      </p>
                    </div>
                    <span className="badge">
                      {percent !== null ? `${percent}%` : "Uncapped"}
                    </span>
                  </div>
                  <div className="usage-meter__bar">
                    <span
                      style={{
                        width: `${percent ?? 100}%`,
                      }}
                    />
                  </div>
                  {remaining !== null && (
                    <p className="text-muted" style={{ margin: "4px 0 0" }}>
                      {remaining} units remaining before renewal
                    </p>
                  )}
                </div>
              ))}
            </div>
          </div>

          <div className="card">
            <div className="card-header">
              <h3 style={{ margin: 0 }}>Payment methods</h3>
              <button
                className="btn btn-primary"
                onClick={() => setPaymentModalOpen(true)}
                disabled={processingPayment}
              >
                Add payment method
              </button>
            </div>
            <div className="payment-methods">
              {paymentMethods.length === 0 && (
                <p className="text-muted">
                  No payment methods on file. Add one to enable billing.
                </p>
              )}
              {paymentMethods.map((method) => (
                <div key={method.id} className="payment-method">
                  <div>
                    <strong>{method.display_name || method.external_ref}</strong>
                    <p className="text-muted" style={{ margin: 0 }}>
                      {method.provider} ·{" "}
                      {method.card_last4 ? `•••• ${method.card_last4}` : "Tokenized"} · exp{" "}
                      {method.card_exp_month || "—"}/{method.card_exp_year || "—"}
                    </p>
                  </div>
                  <div className="page-section__actions">
                    {method.is_default && <span className="badge">Default</span>}
                    <button
                      className="btn btn-secondary"
                      onClick={() => setSelectedPaymentMethodId(method.id)}
                      disabled={processingPayment}
                    >
                      Use for checkout
                    </button>
                    <button
                      className="btn btn-secondary"
                      onClick={() => handleRemovePaymentMethod(method.id)}
                      disabled={removingPaymentId === method.id || processingPayment}
                    >
                      {removingPaymentId === method.id ? "Removing..." : "Remove"}
                    </button>
                  </div>
                </div>
              ))}
            </div>
          </div>

          <div className="card">
            <div className="card-header">
              <h3 style={{ margin: 0 }}>Invoices</h3>
              <span className="badge">
                {invoices.length ? `${invoices.length} invoices` : "No invoices yet"}
              </span>
            </div>
            <div className="table-responsive">
              <table className="table">
                <thead>
                  <tr>
                    <th>Description</th>
                    <th>Status</th>
                    <th>Amount</th>
                    <th>Issued</th>
                    <th>Due</th>
                  </tr>
                </thead>
                <tbody>
                  {invoices.length === 0 && (
                    <tr>
                      <td colSpan={5} className="text-muted">
                        No invoices generated yet.
                      </td>
                    </tr>
                  )}
                  {invoices.map((invoice) => (
                    <tr key={invoice.id}>
                      <td>{invoice.description || "Invoice"}</td>
                      <td>
                        <span
                          className={
                            invoice.status === "PAID"
                              ? "badge badge--success"
                              : "badge"
                          }
                        >
                          {invoice.status.toLowerCase()}
                        </span>
                      </td>
                      <td>{formatMoney(invoice.amount_cents, invoice.currency)}</td>
                      <td>{formatDate(invoice.issued_at)}</td>
                      <td>{formatDate(invoice.due_at)}</td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          </div>
        </section>
      </div>

      {changePlanOpen && (
        <div className="upsell-modal__backdrop" role="dialog" aria-modal="true">
          <div className="upsell-modal">
            <div className="upsell-modal__header">
              <div>
                <p className="upsell-modal__eyebrow">Upgrade / Downgrade</p>
                <h3 className="upsell-modal__title">Change your subscription</h3>
                <p className="upsell-modal__subtitle">
                  Buttons are locked while processing to keep payments idempotent. If SCA
                  is required, you will see a 3DS prompt from your bank.
                </p>
              </div>
              <button
                className="upsell-modal__close"
                onClick={() => setChangePlanOpen(false)}
                aria-label="Close"
                disabled={processingPayment}
              >
                ×
              </button>
            </div>
            <div className="modal-field">
              <label htmlFor="plan-select">Select a plan or module</label>
              <select
                id="plan-select"
                value={selectedSkuId}
                onChange={(e) => setSelectedSkuId(e.target.value)}
                disabled={processingPayment}
              >
                {catalog.map((sku) => (
                  <option key={sku.id} value={sku.id}>
                    {sku.name} · {formatMoney(sku.amount_cents, sku.currency)} ·{" "}
                    {sku.term.toLowerCase()}
                  </option>
                ))}
              </select>
            </div>
            <div className="modal-field">
              <label htmlFor="payment-select">Payment method</label>
              <select
                id="payment-select"
                value={selectedPaymentMethod?.id || ""}
                onChange={(e) => setSelectedPaymentMethodId(e.target.value)}
                disabled={processingPayment || paymentMethods.length === 0}
              >
                {paymentMethods.map((pm) => (
                  <option key={pm.id} value={pm.id}>
                    {pm.display_name || pm.external_ref} ({pm.provider})
                  </option>
                ))}
                {paymentMethods.length === 0 && (
                  <option value="">No payment methods available</option>
                )}
              </select>
            </div>
            {prorationPreview && (
              <div className="info-banner">
                <div>
                  <strong>{prorationPreview.label}</strong>
                  <p className="text-muted" style={{ margin: 0 }}>
                    Remaining time:{" "}
                    {prorationPreview.remainingDays !== null
                      ? `${prorationPreview.remainingDays} of ${prorationPreview.totalDays} days`
                      : "N/A"}
                  </p>
                </div>
                <div className="proration-values">
                  <span>
                    Credit: {formatMoney(prorationPreview.creditCents, prorationPreview.currency)}
                  </span>
                  <span>
                    New charge:{" "}
                    {formatMoney(prorationPreview.chargeCents, prorationPreview.currency)}
                  </span>
                </div>
              </div>
            )}
            <div className="upsell-modal__actions">
              <button
                className="btn btn-secondary"
                onClick={() => setChangePlanOpen(false)}
                disabled={processingPayment}
              >
                Close
              </button>
              <button
                className="btn btn-primary"
                onClick={handlePurchase}
                disabled={processingPayment || !targetSku}
              >
                {processingPayment ? "Processing…" : "Confirm change"}
              </button>
            </div>
          </div>
        </div>
      )}

      {cancelModalOpen && (
        <div className="upsell-modal__backdrop" role="dialog" aria-modal="true">
          <div className="upsell-modal">
            <div className="upsell-modal__header">
              <div>
                <p className="upsell-modal__eyebrow">Remove modules</p>
                <h3 className="upsell-modal__title">Confirm cancellation</h3>
                <p className="upsell-modal__subtitle">
                  Access remains until the end of the current period. Billing actions are
                  idempotent and buttons stay locked while we process the request.
                </p>
              </div>
              <button
                className="upsell-modal__close"
                onClick={() => setCancelModalOpen(false)}
                aria-label="Close"
                disabled={processingPayment}
              >
                ×
              </button>
            </div>
            <div className="upsell-modal__actions">
              <button
                className="btn btn-secondary"
                onClick={() => setCancelModalOpen(false)}
                disabled={processingPayment}
              >
                Keep plan
              </button>
              <button
                className="btn btn-primary"
                onClick={handleCancelPlan}
                disabled={processingPayment || !subscription}
              >
                {processingPayment ? "Processing…" : "Cancel at period end"}
              </button>
            </div>
          </div>
        </div>
      )}

      {paymentModalOpen && (
        <div className="upsell-modal__backdrop" role="dialog" aria-modal="true">
          <div className="upsell-modal">
            <div className="upsell-modal__header">
              <div>
                <p className="upsell-modal__eyebrow">Payment method</p>
                <h3 className="upsell-modal__title">Add a payment method</h3>
                <p className="upsell-modal__subtitle">
                  We surface 3DS / SCA cues whenever the provider requires it and lock the
                  submit button while tokenization runs.
                </p>
              </div>
              <button
                className="upsell-modal__close"
                onClick={() => setPaymentModalOpen(false)}
                aria-label="Close"
                disabled={processingPayment}
              >
                ×
              </button>
            </div>
            <form className="payment-form" onSubmit={handleAddPaymentMethod}>
              <div className="modal-field">
                <label htmlFor="provider">Provider</label>
                <select
                  id="provider"
                  value={paymentForm.provider}
                  onChange={(e) =>
                    setPaymentForm((prev) => ({
                      ...prev,
                      provider: e.target.value as PaymentFormState["provider"],
                    }))
                  }
                  disabled={processingPayment}
                >
                  <option value="STRIPE">Stripe (SCA)</option>
                  <option value="PSP">PSP</option>
                  <option value="OFFLINE">Offline</option>
                  <option value="MANUAL">Manual</option>
                </select>
              </div>
              <div className="modal-field">
                <label htmlFor="displayName">Label</label>
                <input
                  id="displayName"
                  type="text"
                  value={paymentForm.displayName}
                  onChange={(e) =>
                    setPaymentForm((prev) => ({ ...prev, displayName: e.target.value }))
                  }
                  placeholder="Corporate card"
                  disabled={processingPayment}
                />
              </div>
              <div className="modal-field">
                <label htmlFor="externalRef">Payment token / reference</label>
                <input
                  id="externalRef"
                  type="text"
                  value={paymentForm.externalRef}
                  onChange={(e) =>
                    setPaymentForm((prev) => ({ ...prev, externalRef: e.target.value }))
                  }
                  placeholder="psp_123 or vault token"
                  disabled={processingPayment}
                  required
                />
              </div>
              <div className="modal-field modal-field--inline">
                <div>
                  <label htmlFor="last4">Card last 4</label>
                  <input
                    id="last4"
                    type="text"
                    value={paymentForm.cardLast4}
                    onChange={(e) =>
                      setPaymentForm((prev) => ({ ...prev, cardLast4: e.target.value }))
                    }
                    maxLength={4}
                    placeholder="1234"
                    disabled={processingPayment}
                  />
                </div>
                <div>
                  <label htmlFor="expMonth">Exp. month</label>
                  <input
                    id="expMonth"
                    type="text"
                    value={paymentForm.expMonth}
                    onChange={(e) =>
                      setPaymentForm((prev) => ({ ...prev, expMonth: e.target.value }))
                    }
                    maxLength={2}
                    placeholder="09"
                    disabled={processingPayment}
                  />
                </div>
                <div>
                  <label htmlFor="expYear">Exp. year</label>
                  <input
                    id="expYear"
                    type="text"
                    value={paymentForm.expYear}
                    onChange={(e) =>
                      setPaymentForm((prev) => ({ ...prev, expYear: e.target.value }))
                    }
                    maxLength={4}
                    placeholder="2027"
                    disabled={processingPayment}
                  />
                </div>
              </div>
              <label className="checkbox-field">
                <input
                  type="checkbox"
                  checked={paymentForm.isDefault}
                  onChange={(e) =>
                    setPaymentForm((prev) => ({
                      ...prev,
                      isDefault: e.target.checked,
                    }))
                  }
                  disabled={processingPayment}
                />
                Set as default for renewals
              </label>
              <div className="upsell-modal__actions">
                <button
                  type="button"
                  className="btn btn-secondary"
                  onClick={() => setPaymentModalOpen(false)}
                  disabled={processingPayment}
                >
                  Close
                </button>
                <button
                  type="submit"
                  className="btn btn-primary"
                  disabled={processingPayment}
                >
                  {processingPayment ? "Saving…" : "Save payment method"}
                </button>
              </div>
            </form>
          </div>
        </div>
      )}
    </DepartmentLayout>
  );
};

export default SubscriptionManagementPage;
