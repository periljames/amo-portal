// src/pages/UpsellPage.tsx
import React, { useEffect, useMemo, useRef, useState } from "react";
import { useLocation, useNavigate, useParams } from "react-router-dom";
import PricingCard from "../components/UI/PricingCard";
import PricingToggle from "../components/UI/PricingToggle";
import LockedRouteModal from "../components/UI/LockedRouteModal";
import Button from "../components/UI/Button";
import { useAnalytics } from "../hooks/useAnalytics";
import { fetchCatalog, fetchSubscription, startTrial } from "../services/billing";
import type { BillingTerm, CatalogSKU, Subscription } from "../types/billing";

type UrlParams = { amoCode?: string };

type ProductDefinition = {
  id: "ops" | "suite" | "enterprise";
  name: string;
  skuPrefix: string;
  description: string;
  badge?: string;
  features: string[];
};

type ProductView = {
  id: ProductDefinition["id"];
  name: string;
  description: string;
  badge?: string;
  features: string[];
  priceLabel: string;
  termLabel: string;
  deltaLabel: string | null;
  trialLabel: string | null;
  selectedSku?: CatalogSKU;
};

const TERM_MONTHS: Record<BillingTerm, number> = {
  MONTHLY: 1,
  ANNUAL: 12,
  BI_ANNUAL: 24,
};

const TERM_LABEL: Record<BillingTerm, string> = {
  MONTHLY: "Billed monthly",
  ANNUAL: "Billed annually",
  BI_ANNUAL: "Billed bi-annually",
};

const PRODUCTS: ProductDefinition[] = [
  {
    id: "ops",
    name: "Ops Essentials",
    skuPrefix: "OPS",
    description: "Unlock digital work orders, CRS, and operational discipline.",
    features: [
      "CRS workflows with auto population",
      "Work order + fleet registry sync",
      "Stores & procurement visibility",
      "Usage dashboards for AMO leads",
      "Quality-friendly audit trails",
    ],
  },
  {
    id: "suite",
    name: "Maintenance Suite",
    skuPrefix: "SUITE",
    description: "Reliability, QMS, safety, and training – bundled for busy AMOs.",
    badge: "Most popular",
    features: [
      "Safety + reliability trackers with KPIs",
      "QMS manuals, revisions, and approvals",
      "Training matrix with licence reminders",
      "Task-level risk & compliance guardrails",
      "Priority support with onboarding",
    ],
  },
  {
    id: "enterprise",
    name: "Enterprise",
    skuPrefix: "ENTERPRISE",
    description: "For large fleets needing controls, SSO, and tailored success.",
    badge: "For complex ops",
    features: [
      "Custom SSO and delegated admin",
      "Advanced audit exports and API access",
      "Multi-amo tenancy with rollups",
      "Dedicated TAM + launch playbooks",
      "Premium support with runbooks",
    ],
  },
];

function formatMoney(amountCents: number, currency: string): string {
  const amount = amountCents / 100;
  return new Intl.NumberFormat("en-US", {
    style: "currency",
    currency: currency || "USD",
    minimumFractionDigits: 0,
    maximumFractionDigits: 0,
  }).format(amount);
}

function findSkuForTerm(
  catalog: CatalogSKU[],
  prefix: string,
  term: BillingTerm
): CatalogSKU | undefined {
  return catalog.find(
    (sku) =>
      sku.term === term && sku.code.toUpperCase().includes(prefix.toUpperCase())
  );
}

function formatCountdown(iso?: string | null): string | null {
  if (!iso) return null;
  const target = new Date(iso).getTime();
  const now = Date.now();
  const diff = target - now;
  if (diff <= 0) return "0d";
  const days = Math.floor(diff / (1000 * 60 * 60 * 24));
  const hours = Math.floor((diff % (1000 * 60 * 60 * 24)) / (1000 * 60 * 60));
  if (days > 0) return `${days}d ${hours}h`;
  const minutes = Math.floor((diff % (1000 * 60 * 60)) / (1000 * 60));
  if (hours > 0) return `${hours}h ${minutes}m`;
  return `${minutes}m`;
}

const UpsellPage: React.FC = () => {
  const { amoCode } = useParams<UrlParams>();
  const location = useLocation();
  const navigate = useNavigate();
  const pricingRef = useRef<HTMLDivElement>(null);
  const viewTrackedRef = useRef<string | null>(null);
  const { trackEvent } = useAnalytics();

  const [term, setTerm] = useState<BillingTerm>("ANNUAL");
  const [catalog, setCatalog] = useState<CatalogSKU[]>([]);
  const [subscription, setSubscription] = useState<Subscription | null>(null);
  const [loading, setLoading] = useState(true);
  const [trialLoading, setTrialLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [notice, setNotice] = useState<string | null>(null);
  const [lockedModalOpen, setLockedModalOpen] = useState(false);
  const [lockedFeature, setLockedFeature] = useState<string | undefined>();

  const trialCountdown = useMemo(
    () => formatCountdown(subscription?.trial_ends_at),
    [subscription?.trial_ends_at]
  );
  const graceCountdown = useMemo(
    () => formatCountdown(subscription?.trial_grace_expires_at),
    [subscription?.trial_grace_expires_at]
  );
  const isReadOnly = subscription?.is_read_only ?? false;
  const isTrialing = subscription?.status === "TRIALING";
  const isExpired = subscription?.status === "EXPIRED";

  const lockedParam = useMemo(() => {
    const params = new URLSearchParams(location.search);
    return params.get("locked");
  }, [location.search]);

  useEffect(() => {
    const viewKey = `${amoCode || "UNKNOWN"}:${location.pathname}${location.search}`;
    if (viewTrackedRef.current === viewKey) return;
    viewTrackedRef.current = viewKey;
    trackEvent("UPSELL_VIEWED", {
      amo_code: amoCode,
      locked: !!lockedParam,
      path: location.pathname,
    });
  }, [amoCode, lockedParam, location.pathname, location.search, trackEvent]);

  useEffect(() => {
    let isMounted = true;
    setLoading(true);
    setError(null);
    Promise.all([fetchCatalog(), fetchSubscription()])
      .then(([cat, sub]) => {
        if (!isMounted) return;
        setCatalog(cat);
        setSubscription(sub);
        if (!cat.length) {
          setError("No catalog entries are available yet.");
        }
      })
      .catch((err) => {
        if (!isMounted) return;
        setError(err instanceof Error ? err.message : "Failed to load catalog.");
      })
      .finally(() => {
        if (isMounted) setLoading(false);
      });
    return () => {
      isMounted = false;
    };
  }, []);

  useEffect(() => {
    if (lockedParam) {
      setLockedFeature(lockedParam.replace(/-/g, " "));
      setLockedModalOpen(true);
      trackEvent("LOCKED_ROUTE_MODAL", {
        amo_code: amoCode,
        feature: lockedParam,
        path: location.pathname,
      });
    }
  }, [amoCode, lockedParam, location.pathname, trackEvent]);

  const productViews: ProductView[] = useMemo(() => {
    return PRODUCTS.map((product) => {
      const skuForSelectedTerm =
        findSkuForTerm(catalog, product.skuPrefix, term) ||
        findSkuForTerm(catalog, product.skuPrefix, "ANNUAL") ||
        findSkuForTerm(catalog, product.skuPrefix, "MONTHLY");
      const monthlySku = findSkuForTerm(catalog, product.skuPrefix, "MONTHLY");
      const activeSku = skuForSelectedTerm;

      const priceLabel = activeSku
        ? `${formatMoney(activeSku.amount_cents, activeSku.currency)} / ${
            activeSku.term === "MONTHLY"
              ? "month"
              : activeSku.term === "ANNUAL"
              ? "year"
              : "2 years"
          }`
        : "Talk to us";

      const deltaLabel =
        activeSku && monthlySku && activeSku.term !== "MONTHLY"
          ? (() => {
              const months = TERM_MONTHS[activeSku.term];
              const baseline = monthlySku.amount_cents * months;
              const savings = 1 - activeSku.amount_cents / baseline;
              if (savings > 0.005) {
                return `Save ${Math.round(savings * 100)}% vs monthly`;
              }
              return `Billed for ${months} months`;
            })()
          : null;

      const trialEligible =
        !!activeSku?.trial_days &&
        activeSku.trial_days >= 30 &&
        (!subscription ||
          subscription.status === "CANCELLED" ||
          subscription.status === "EXPIRED") &&
        !isReadOnly;

      const trialLabel = trialEligible
        ? `Eligible for ${activeSku?.trial_days || 30}-day trial`
        : null;

      return {
        id: product.id,
        name: product.name,
        description: product.description,
        badge: product.badge,
        features: product.features,
        priceLabel,
        termLabel: activeSku ? TERM_LABEL[activeSku.term] : "Flexible billing",
        deltaLabel,
        trialLabel,
        selectedSku: activeSku,
      };
    });
  }, [catalog, subscription, term]);

  const handleStartTrial = async (skuCode?: string) => {
    if (!skuCode) {
      setError("No SKU found for the selected term. Please contact support.");
      return;
    }

    trackEvent("UPSELL_TRIAL_ATTEMPT", {
      sku: skuCode,
      amo_code: amoCode,
      source: lockedParam ? "locked_route" : "upsell",
    });
    setTrialLoading(true);
    setError(null);
    setNotice(null);
    try {
      const lic = await startTrial(skuCode);
      setSubscription(lic);
      setNotice("Trial started successfully. Enjoy your 30 days on us!");
      setLockedModalOpen(false);
      trackEvent("UPSELL_TRIAL_STARTED", {
        sku: skuCode,
        amo_code: amoCode,
        status: lic.status,
      });
    } catch (err: any) {
      setError(err?.message || "Could not start trial. Please try again.");
      trackEvent("UPSELL_TRIAL_FAILED", {
        sku: skuCode,
        amo_code: amoCode,
        message: err?.message || "unknown_error",
      });
    } finally {
      setTrialLoading(false);
    }
  };

  const handleTermChange = (nextTerm: BillingTerm) => {
    setTerm(nextTerm);
    trackEvent("UPSELL_TERM_SELECTED", {
      amo_code: amoCode,
      term: nextTerm,
    });
  };

  const scrollToPricing = () => {
    pricingRef.current?.scrollIntoView({ behavior: "smooth" });
    trackEvent("UPSELL_SCROLL_TO_PRICING", {
      amo_code: amoCode,
      term,
    });
  };

  const goToBilling = (source: string) => {
    trackEvent("UPSELL_CONVERT_CLICK", {
      amo_code: amoCode,
      source,
      term,
    });
    navigate(`/maintenance/${amoCode ?? "UNKNOWN"}/admin/billing`);
  };

  return (
    <div className="upsell-page">
      <header className="upsell-hero">
        <div className="upsell-hero__copy">
          <p className="upsell-hero__eyebrow">
            {amoCode ? `AMO ${amoCode}` : "Your AMO"} · 30-day trial
          </p>
          <h1>Choose the right module for your maintenance teams</h1>
          <p>
            Unlock Ops Essentials, Maintenance Suite, or Enterprise controls. Switch
            terms at any time, view price deltas instantly, and start a 30-day trial
            without losing context.
          </p>
          <div className="upsell-hero__actions">
            <Button
              onClick={() => handleStartTrial(productViews[0]?.selectedSku?.code)}
              disabled={isReadOnly || trialLoading}
            >
              Start 30-day trial
            </Button>
            <button type="button" className="btn-secondary" onClick={scrollToPricing}>
              Compare modules
            </button>
            {isTrialing && (
              <button
                type="button"
                className="btn-secondary"
                onClick={() => goToBilling("hero-trialing")}
              >
                Convert to paid
              </button>
            )}
          </div>
          {notice && <div className="upsell-alert upsell-alert--success">{notice}</div>}
          {error && <div className="upsell-alert upsell-alert--error">{error}</div>}
          {isTrialing && trialCountdown && (
            <div className="upsell-alert upsell-alert--info">
              Trial ends in <strong>{trialCountdown}</strong>. Add a payment method to
              keep access.
            </div>
          )}
          {isExpired && (
            <div
              className={`upsell-alert ${
                isReadOnly ? "upsell-alert--error" : "upsell-alert--warning"
              }`}
            >
              Trial expired{graceCountdown ? `; grace ends in ${graceCountdown}` : "."}{" "}
              {isReadOnly ? "Workspace is read-only until billing resumes." : ""}
            </div>
          )}
        </div>
        <div className="upsell-hero__panel">
          <div className="upsell-hero__panel-inner">
            <p className="upsell-hero__panel-title">Why upgrade?</p>
            <ul>
              <li>Map pricing deltas across Monthly, Annual, and Bi-Annual terms.</li>
              <li>Keep a persistent 30-day trial before you commit.</li>
              <li>Surface upsell modals automatically when a route is locked.</li>
            </ul>
            <p className="upsell-hero__panel-footnote">
              Already subscribed? We&apos;ll surface your active term and trial eligibility
              automatically.
            </p>
          </div>
        </div>
      </header>

      <section className="pricing-toggle__section">
        <PricingToggle
          value={term}
          onChange={handleTermChange}
          subtitle="See how pricing shifts by term – we will highlight savings versus monthly."
        />
      </section>

      <section className="pricing-grid" ref={pricingRef}>
        {loading && <div className="upsell-alert">Loading catalog…</div>}
        {!loading && productViews.length === 0 && (
          <div className="upsell-alert upsell-alert--error">
            No pricing data found. Please check your connection.
          </div>
        )}

        <div className="pricing-grid__cards">
          {productViews.map((product) => (
            <PricingCard
              key={product.id}
              title={product.name}
              description={product.description}
              badge={product.badge}
              priceLabel={product.priceLabel}
              termLabel={product.termLabel}
              deltaLabel={product.deltaLabel}
              trialLabel={product.trialLabel}
              features={product.features}
              primaryLabel={
                product.trialLabel ? "Start 30-day trial" : "Talk to us"
              }
              onPrimary={() => handleStartTrial(product.selectedSku?.code)}
              secondaryLabel="View more details"
              onSecondary={scrollToPricing}
              highlight={product.id === "suite"}
              disabled={trialLoading || isReadOnly}
            />
          ))}
        </div>
      </section>

      <section className="locked-route-section">
        <div className="locked-route-section__copy">
          <p className="pricing-toggle__eyebrow">Locked routes</p>
          <h3>Show an upsell modal when a feature is locked</h3>
          <p>
            If a user navigates to a route without the right entitlement, we can raise
            an upsell modal instead of a blank screen. Trigger it via the{" "}
            <code>?locked=feature</code> query or from navigation state.
          </p>
          <div className="locked-route-section__actions">
            <Button
              onClick={() => {
                setLockedFeature("Previewed feature");
                setLockedModalOpen(true);
                trackEvent("LOCKED_ROUTE_MODAL", {
                  amo_code: amoCode,
                  feature: "preview",
                  path: location.pathname,
                });
              }}
            >
              Preview locked-route modal
            </Button>
            <button type="button" className="btn-secondary" onClick={scrollToPricing}>
              Back to pricing
            </button>
          </div>
        </div>
      </section>

      <LockedRouteModal
        open={lockedModalOpen}
        featureName={lockedFeature}
        onClose={() => setLockedModalOpen(false)}
        onViewPlans={scrollToPricing}
        onStartTrial={() => handleStartTrial(productViews[0]?.selectedSku?.code)}
      />
    </div>
  );
};

export default UpsellPage;
