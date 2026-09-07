import React, { useCallback, useEffect, useMemo, useState } from "react";
import { Link, useParams } from "react-router-dom";

import DepartmentLayout from "../components/Layout/DepartmentLayout";
import TenantEmailPreferencesPanel from "../components/notifications/TenantEmailPreferencesPanel";
import { aiApi, type AIFeature, type AIHealth, type AIModel, type AISettings } from "../services/ai";
import { getCachedUser } from "../services/auth";
import { getApiBaseUrl } from "../services/config";
import {
  checkoutUrlFromJob,
  SaaSJobTimeoutError,
  saasSettingsApi,
  type SaaSAdminInvoice,
  type SaaSAdminJob,
  type SaaSSetupSummary,
} from "../services/saasSettings";
import "../styles/adminSaaSSettings.css";

type Tab = "providers" | "modules" | "billing" | "pipeline" | "readiness";

type UrlParams = { amoCode?: string };

function coerceField(value: string): string | number | boolean {
  const clean = value.trim();
  if (clean === "true") return true;
  if (clean === "false") return false;
  if (/^-?\d+$/.test(clean)) return Number(clean);
  return clean;
}

function statusTone(value: string): string {
  const normalized = value.toUpperCase();
  if (["HEALTHY", "CONNECTED", "CONFIGURED", "SUCCEEDED", "ENABLED", "FISCALIZED", "PAID"].includes(normalized)) return "good";
  if (["FAILED", "DEAD", "UNHEALTHY", "RECONCILIATION_REQUIRED", "SUSPENDED"].includes(normalized)) return "bad";
  return "warn";
}

function Status({ value }: { value: string }) {
  return <span className={`saas-admin__status saas-admin__status--${statusTone(value)}`}>{value.replaceAll("_", " ")}</span>;
}

function formatMoney(amountCents: number, currency: string): string {
  try {
    return new Intl.NumberFormat(undefined, { style: "currency", currency }).format(amountCents / 100);
  } catch {
    return `${currency} ${(amountCents / 100).toFixed(2)}`;
  }
}

function formatTime(value?: string | null): string {
  if (!value) return "—";
  const date = new Date(value);
  return Number.isNaN(date.getTime()) ? "—" : date.toLocaleString();
}

const FIELD_HINTS: Record<string, string> = {
  api_base_url: "Absolute HTTPS provider API base URL",
  success_url: "Portal URL used after a successful checkout",
  cancel_url: "Portal URL used after a cancelled checkout",
  callback_url: "Public HTTPS callback registered with the provider",
  endpoint: "Certified provider or integrator HTTPS endpoint",
  certified: "Set true only after formal provider/regulator testing",
  environment: "sandbox or production",
  model: "Server-side model identifier",
  default_model: "Tenant default model is governed in the AI plan below",
  lightweight_model: "Tenant lightweight model is governed in the AI plan below",
  embedding_model: "Tenant embedding model is governed in the AI plan below",
  project: "Optional provider project identifier",
  organization: "Optional provider organization identifier",
  use_tls: "true for STARTTLS",
  use_ssl: "true for implicit TLS",
  allow_self_signed: "Keep false in production",
};

export default function AdminSaaSSettingsPage() {
  const { amoCode = "" } = useParams<UrlParams>();
  const currentUser = useMemo(() => getCachedUser(), []);
  const isSuperuser = Boolean(currentUser?.is_superuser);
  const initialTenantScope = useMemo(
    () => new URLSearchParams(window.location.search).get("tenant_id") || "",
    [],
  );
  const [tenantScope, setTenantScope] = useState(initialTenantScope);
  const [tab, setTab] = useState<Tab>("providers");
  const [setup, setSetup] = useState<SaaSSetupSummary | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [notice, setNotice] = useState<string | null>(null);
  const [checkoutLink, setCheckoutLink] = useState<string | null>(null);
  const [selectedProviderCode, setSelectedProviderCode] = useState<string | null>(null);
  const [configDraft, setConfigDraft] = useState<Record<string, string>>({});
  const [secretDraft, setSecretDraft] = useState<Record<string, string>>({});
  const [changeReason, setChangeReason] = useState("Provider configuration updated by an authorised administrator");
  const [providerEnabled, setProviderEnabled] = useState(true);
  const [clearSecret, setClearSecret] = useState(false);
  const [busyAction, setBusyAction] = useState<string | null>(null);
  const [aiSettings, setAISettings] = useState<AISettings | null>(null);
  const [aiHealth, setAIHealth] = useState<AIHealth | null>(null);
  const [aiModels, setAIModels] = useState<AIModel[]>([]);
  const [aiFeatures, setAIFeatures] = useState<AIFeature[]>([]);
  const [aiReason, setAIReason] = useState("Tenant AI plan updated by an authorised administrator");

  const effectiveTenantId = isSuperuser ? tenantScope.trim() || null : null;
  const canLoadTenantAI = !isSuperuser || Boolean(effectiveTenantId);

  const load = useCallback(async () => {
    setLoading(true);
    setError(null);
    try {
      const data = await saasSettingsApi.setup(effectiveTenantId);
      setSetup(data);
      setSelectedProviderCode((current) => current && data.providers.some((row) => row.provider === current)
        ? current
        : data.providers[0]?.provider ?? null);
      if (!canLoadTenantAI) {
        setAISettings(null);
        setAIHealth(null);
        setAIModels([]);
        setAIFeatures([]);
        return;
      }
      try {
        const aiData = await Promise.all([
          aiApi.settings(effectiveTenantId),
          aiApi.health(effectiveTenantId),
          aiApi.models(effectiveTenantId),
        ]);
        setAISettings(aiData[0]);
        setAIHealth(aiData[1]);
        setAIModels(aiData[2].items);
        setAIFeatures(aiData[2].features);
      } catch (aiLoadError) {
        setAISettings(null);
        setAIHealth(null);
        setAIModels([]);
        setAIFeatures([]);
        const detail = aiLoadError instanceof Error ? aiLoadError.message : String(aiLoadError);
        setError(`Integration settings loaded, but tenant AI controls are unavailable: ${detail}`);
      }
    } catch (loadError) {
      setError(loadError instanceof Error ? loadError.message : String(loadError));
    } finally {
      setLoading(false);
    }
  }, [canLoadTenantAI, effectiveTenantId]);

  useEffect(() => {
    setCheckoutLink(null);
    void load();
  }, [load]);

  const provider = useMemo(
    () => setup?.providers.find((row) => row.provider === selectedProviderCode) ?? null,
    [selectedProviderCode, setup?.providers],
  );

  useEffect(() => {
    if (!provider) return;
    const next: Record<string, string> = {};
    provider.config_fields.forEach((field) => {
      const value = provider.config?.[field];
      next[field] = value === undefined || value === null ? "" : String(value);
    });
    setConfigDraft(next);
    setSecretDraft({});
    setProviderEnabled(provider.status !== "DISABLED");
    setClearSecret(false);
  }, [provider]);

  const run = async (key: string, action: () => Promise<unknown>, success: string) => {
    setBusyAction(key);
    setError(null);
    setNotice(null);
    try {
      await action();
      await load();
      setNotice(success);
    } catch (actionError) {
      setError(actionError instanceof Error ? actionError.message : String(actionError));
    } finally {
      setBusyAction(null);
    }
  };

  const saveProvider = async () => {
    if (!provider) return;
    if (!changeReason.trim()) {
      setError("A configuration-change reason is required.");
      return;
    }
    const config = Object.fromEntries(
      Object.entries(configDraft)
        .filter(([, value]) => value.trim() !== "")
        .map(([key, value]) => [key, coerceField(value)]),
    );
    const secret = Object.fromEntries(
      Object.entries(secretDraft).filter(([, value]) => value.trim() !== ""),
    );
    if (
      setup?.scope === "TENANT"
      && provider.scope === "PLATFORM"
      && provider.has_secret
      && !clearSecret
      && Object.keys(secret).length === 0
    ) {
      setError(
        "This tenant currently inherits a platform credential. Enter tenant-specific secret values before creating an override, or leave the inherited provider unchanged.",
      );
      return;
    }
    await run(
      `save:${provider.provider}`,
      () => saasSettingsApi.updateProvider(
        provider.provider,
        {
          config,
          enabled: providerEnabled,
          reason: changeReason.trim(),
          ...(Object.keys(secret).length ? { secret } : {}),
          ...(clearSecret ? { secret: {}, clear_secret: true } : {}),
        },
        effectiveTenantId,
      ),
      `${provider.display_name} configuration saved. Stored secrets remain encrypted and are not returned to the browser.`,
    );
  };

  const testProvider = async () => {
    if (!provider) return;
    if (provider.provider === "openai") {
      await run(
        "test:openai",
        () => aiApi.test(aiSettings?.default_model, effectiveTenantId),
        "OpenAI connectivity verified server-side. Token usage and latency were recorded for this tenant.",
      );
      return;
    }
    await run(
      `test:${provider.provider}`,
      () => saasSettingsApi.testProvider(provider.provider, effectiveTenantId),
      `${provider.display_name} health check queued in the backend pipeline.`,
    );
  };

  const updateAINumber = (field: keyof Pick<AISettings, "monthly_token_allowance" | "monthly_request_allowance" | "max_input_tokens_per_request" | "max_output_tokens_per_request">, value: string) => {
    const numeric = Math.max(0, Number.parseInt(value || "0", 10) || 0);
    setAISettings((current) => current ? { ...current, [field]: numeric } : current);
  };

  const saveAISettings = async () => {
    if (!aiSettings) return;
    if (!aiReason.trim()) {
      setError("An AI plan change reason is required.");
      return;
    }
    const settingsPayload = {
      enabled: aiSettings.enabled,
      provider: aiSettings.provider,
      default_model: aiSettings.default_model,
      lightweight_model: aiSettings.lightweight_model,
      embedding_model: aiSettings.embedding_model,
      plan_type: aiSettings.plan_type,
      monthly_token_allowance: aiSettings.monthly_token_allowance,
      monthly_request_allowance: aiSettings.monthly_request_allowance,
      max_input_tokens_per_request: aiSettings.max_input_tokens_per_request,
      max_output_tokens_per_request: aiSettings.max_output_tokens_per_request,
      usage_limits: aiSettings.usage_limits,
      enabled_features: aiSettings.enabled_features,
      allow_external_document_context: aiSettings.allow_external_document_context,
    };
    await run(
      "save:ai-settings",
      () => aiApi.updateSettings({ ...settingsPayload, reason: aiReason.trim() }, effectiveTenantId),
      "Tenant AI plan saved. Model selection and usage limits now apply to backend AI workflows.",
    );
  };

  const toggleAIFeature = (code: string, enabled: boolean) => {
    setAISettings((current) => {
      if (!current) return current;
      const next = enabled
        ? Array.from(new Set([...current.enabled_features, code]))
        : current.enabled_features.filter((item) => item !== code);
      return { ...current, enabled_features: next };
    });
  };

  const checkout = async (priceId: string) => {
    const key = `checkout:${priceId}`;
    setBusyAction(key);
    setError(null);
    setNotice("Creating a secure Stripe checkout session in the backend pipeline…");
    setCheckoutLink(null);
    setTab("pipeline");
    try {
      const queued = await saasSettingsApi.checkout(priceId, effectiveTenantId);
      const completed = await saasSettingsApi.waitForJob(queued.id, effectiveTenantId);
      await load();
      if (completed.status.toUpperCase() !== "SUCCEEDED") {
        throw new Error(completed.last_error || `Stripe checkout job ended with status ${completed.status}.`);
      }
      const url = checkoutUrlFromJob(completed);
      if (!url) {
        throw new Error("Stripe checkout completed without a valid HTTPS checkout URL.");
      }
      setCheckoutLink(url);
      setNotice("Stripe checkout is ready. Redirecting now; use the link below if navigation is blocked.");
      window.location.assign(url);
    } catch (actionError) {
      await load();
      if (actionError instanceof SaaSJobTimeoutError) {
        setNotice(actionError.message);
        setTab("pipeline");
      } else {
        setError(actionError instanceof Error ? actionError.message : String(actionError));
      }
    } finally {
      setBusyAction(null);
    }
  };

  const fiscalize = async (invoice: SaaSAdminInvoice, providerCode: "etims_oscu" | "etims_vscu") => run(
    `fiscalize:${invoice.id}`,
    () => saasSettingsApi.fiscalize(invoice.id, providerCode, effectiveTenantId),
    `${invoice.invoice_number} queued for ${providerCode.toUpperCase()} fiscalization.`,
  );

  const webhookUrl = useMemo(() => {
    const path = setup?.links.stripe_webhook_path || "/platform/saas/webhooks/stripe";
    return `${getApiBaseUrl().replace(/\/$/, "")}${path.startsWith("/") ? path : `/${path}`}`;
  }, [setup?.links.stripe_webhook_path]);

  const copyWebhook = async () => {
    await navigator.clipboard.writeText(webhookUrl);
    setNotice("Stripe webhook URL copied.");
  };

  const tenantLabel = setup?.tenant?.name || (setup?.scope === "PLATFORM" ? "Platform defaults" : amoCode);
  const jobs: SaaSAdminJob[] = setup?.jobs ?? [];
  const chatModels = aiModels.filter((item) => item.purpose !== "embedding");
  const embeddingModels = aiModels.filter((item) => item.purpose === "embedding");
  const providerConfigFields = provider?.provider === "openai"
    ? provider.config_fields.filter((field) => !["model", "default_model", "lightweight_model", "embedding_model"].includes(field))
    : provider?.config_fields ?? [];

  return (
    <DepartmentLayout amoCode={amoCode} activeDepartment="admin">
      <div className="saas-admin">
        <header className="saas-admin__header">
          <div>
            <p className="saas-admin__eyebrow">Administration / Integrations</p>
            <h1>Integrations & automation setup</h1>
            <p>
              Configure encrypted provider credentials, validate connections, review modules, start authorised billing actions,
              and follow every background operation through the durable backend pipeline.
            </p>
          </div>
          <div className="saas-admin__header-actions">
            <button type="button" onClick={() => void load()} disabled={loading}>Refresh</button>
            {setup?.links.platform_integrations_path ? <Link to={setup.links.platform_integrations_path}>Global integrations</Link> : null}
            {setup?.links.platform_billing_path ? <Link to={setup.links.platform_billing_path}>Global billing</Link> : null}
          </div>
        </header>

        {isSuperuser ? (
          <section className="saas-admin__scope">
            <label>
              <span>Superadmin scope</span>
              <input
                value={tenantScope}
                onChange={(event) => setTenantScope(event.target.value)}
                placeholder="Leave blank for platform defaults, or enter tenant ID"
              />
            </label>
            <button type="button" onClick={() => void load()}>Load scope</button>
            <small>AMO administrators cannot change this scope; the backend always binds them to their own tenant.</small>
          </section>
        ) : null}

        <section className="saas-admin__summary">
          <div><span>Scope</span><strong>{tenantLabel || "—"}</strong></div>
          <div><span>Providers configured</span><strong>{setup?.provider_readiness.configured ?? 0}/{setup?.provider_readiness.catalog_total ?? 0}</strong></div>
          <div><span>Queue depth</span><strong>{String(setup?.queue.queue_depth ?? 0)}</strong></div>
          <div><span>Unhealthy providers</span><strong>{setup?.provider_readiness.unhealthy ?? 0}</strong></div>
        </section>

        {!isSuperuser ? <TenantEmailPreferencesPanel /> : null}

        {error ? <div className="saas-admin__alert saas-admin__alert--error" role="alert">{error}</div> : null}
        {notice ? <div className="saas-admin__alert saas-admin__alert--success" role="status">{notice}</div> : null}
        {checkoutLink ? (
          <div className="saas-admin__alert saas-admin__alert--success" role="status">
            <a href={checkoutLink}>Continue to secure Stripe checkout</a>
          </div>
        ) : null}
        {loading ? <div className="saas-admin__loading">Loading current backend configuration…</div> : null}

        <nav className="saas-admin__tabs" aria-label="SaaS administration sections">
          {(["providers", "modules", "billing", "pipeline", "readiness"] as Tab[]).map((item) => (
            <button key={item} type="button" className={tab === item ? "active" : ""} onClick={() => setTab(item)}>
              {item === "providers" ? "Providers" : item === "pipeline" ? "Backend pipeline" : item[0].toUpperCase() + item.slice(1)}
            </button>
          ))}
        </nav>

        {tab === "providers" ? (
          <div className="saas-admin__provider-layout">
            <aside className="saas-admin__provider-list">
              {(setup?.providers ?? []).map((item) => (
                <button
                  type="button"
                  key={item.provider}
                  className={selectedProviderCode === item.provider ? "active" : ""}
                  onClick={() => setSelectedProviderCode(item.provider)}
                >
                  <span><strong>{item.display_name}</strong><small>{item.category} · {item.scope}</small></span>
                  <Status value={item.status} />
                </button>
              ))}
            </aside>

            <section className="saas-admin__card">
              {provider ? (
                <>
                  <div className="saas-admin__card-heading">
                    <div>
                      <h2>{provider.display_name}</h2>
                      <p>{provider.description}</p>
                    </div>
                    <Status value={provider.status} />
                  </div>
                  {setup?.scope === "TENANT" && provider.scope === "PLATFORM" ? (
                    <div className="saas-admin__alert">
                      This tenant currently inherits the platform default. Saving creates a tenant-specific override; if the platform default contains a secret, enter new tenant credentials before saving.
                    </div>
                  ) : null}
                  <div className="saas-admin__secret-state">
                    <strong>{provider.has_secret ? "Encrypted secret stored" : "No secret stored"}</strong>
                    <span>{provider.secret_fingerprint || "Secret values are never returned to the frontend."}</span>
                  </div>
                  <div className="saas-admin__form-grid">
                    {providerConfigFields.map((field) => (
                      <label key={field}>
                        <span>{field.replaceAll("_", " ")}</span>
                        <input
                          value={configDraft[field] ?? ""}
                          onChange={(event) => setConfigDraft((current) => ({ ...current, [field]: event.target.value }))}
                          placeholder={FIELD_HINTS[field] || field}
                        />
                        {FIELD_HINTS[field] ? <small>{FIELD_HINTS[field]}</small> : null}
                      </label>
                    ))}
                    {provider.secret_fields.map((field) => (
                      <label key={field}>
                        <span>{field.replaceAll("_", " ")}</span>
                        <input
                          type="password"
                          autoComplete="new-password"
                          value={secretDraft[field] ?? ""}
                          onChange={(event) => setSecretDraft((current) => ({ ...current, [field]: event.target.value }))}
                          placeholder={provider.scope === "PLATFORM" && setup?.scope === "TENANT"
                            ? "Required to create a tenant-specific override"
                            : provider.has_secret
                              ? "Leave blank to preserve encrypted value"
                              : field}
                        />
                      </label>
                    ))}
                    <label className="saas-admin__wide">
                      <span>Audit reason</span>
                      <input value={changeReason} onChange={(event) => setChangeReason(event.target.value)} />
                    </label>
                  </div>
                  <div className="saas-admin__checks">
                    <label><input type="checkbox" checked={providerEnabled} onChange={(event) => setProviderEnabled(event.target.checked)} /> Provider enabled</label>
                    <label><input type="checkbox" checked={clearSecret} onChange={(event) => setClearSecret(event.target.checked)} /> Clear stored secret</label>
                  </div>
                  {provider.provider === "openai" ? (
                    <section className="saas-admin__ai-plan" aria-labelledby="tenant-ai-plan-heading">
                      <div className="saas-admin__card-heading">
                        <div>
                          <h3 id="tenant-ai-plan-heading">Tenant AI plan & model policy</h3>
                          <p>
                            The API key above is encrypted server-side and never returned. This policy controls which backend workflows may use it and records usage for the selected tenant.
                          </p>
                        </div>
                        <Status value={aiHealth?.connection_status || (canLoadTenantAI ? "NOT CONFIGURED" : "SELECT TENANT")} />
                      </div>
                      {!canLoadTenantAI ? (
                        <div className="saas-admin__alert">Select a tenant scope to configure its AI plan. Platform credentials remain available as inherited, write-only defaults.</div>
                      ) : aiSettings ? (
                        <>
                          <div className="saas-admin__ai-usage">
                            <div><span>Credential source</span><strong>{aiHealth?.credential_source || "—"}</strong></div>
                            <div><span>Requests this month</span><strong>{aiSettings.monthly_usage?.requests ?? 0}{aiSettings.monthly_request_allowance ? ` / ${aiSettings.monthly_request_allowance}` : " / unlimited"}</strong></div>
                            <div><span>Tokens this month</span><strong>{aiSettings.monthly_usage?.tokens ?? 0}{aiSettings.monthly_token_allowance ? ` / ${aiSettings.monthly_token_allowance}` : " / unlimited"}</strong></div>
                          </div>
                          <div className="saas-admin__form-grid">
                            <label>
                              <span>Plan type</span>
                              <input value={aiSettings.plan_type} onChange={(event) => setAISettings({ ...aiSettings, plan_type: event.target.value.toUpperCase() })} placeholder="DEVELOPMENT, STANDARD or ENTERPRISE" />
                            </label>
                            <label>
                              <span>Default model</span>
                              <select value={aiSettings.default_model} onChange={(event) => setAISettings({ ...aiSettings, default_model: event.target.value })}>
                                {chatModels.map((item) => <option key={item.model} value={item.model}>{item.model} · {item.purpose}</option>)}
                              </select>
                            </label>
                            <label>
                              <span>Lightweight model</span>
                              <select value={aiSettings.lightweight_model} onChange={(event) => setAISettings({ ...aiSettings, lightweight_model: event.target.value })}>
                                {chatModels.map((item) => <option key={item.model} value={item.model}>{item.model} · {item.purpose}</option>)}
                              </select>
                            </label>
                            <label>
                              <span>Embedding model</span>
                              <select value={aiSettings.embedding_model} onChange={(event) => setAISettings({ ...aiSettings, embedding_model: event.target.value })}>
                                {embeddingModels.map((item) => <option key={item.model} value={item.model}>{item.model}</option>)}
                              </select>
                            </label>
                            <label>
                              <span>Monthly token allowance</span>
                              <input type="number" min="0" value={aiSettings.monthly_token_allowance} onChange={(event) => updateAINumber("monthly_token_allowance", event.target.value)} />
                              <small>0 means unlimited; set the commercial plan allowance here.</small>
                            </label>
                            <label>
                              <span>Monthly request allowance</span>
                              <input type="number" min="0" value={aiSettings.monthly_request_allowance} onChange={(event) => updateAINumber("monthly_request_allowance", event.target.value)} />
                              <small>0 means unlimited.</small>
                            </label>
                            <label>
                              <span>Maximum input tokens per request</span>
                              <input type="number" min="0" value={aiSettings.max_input_tokens_per_request} onChange={(event) => updateAINumber("max_input_tokens_per_request", event.target.value)} />
                              <small>0 delegates the ceiling to the selected provider/model.</small>
                            </label>
                            <label>
                              <span>Maximum output tokens per request</span>
                              <input type="number" min="0" value={aiSettings.max_output_tokens_per_request} onChange={(event) => updateAINumber("max_output_tokens_per_request", event.target.value)} />
                              <small>0 delegates the ceiling to the selected provider/model.</small>
                            </label>
                            <label className="saas-admin__wide">
                              <span>AI policy audit reason</span>
                              <input value={aiReason} onChange={(event) => setAIReason(event.target.value)} />
                            </label>
                          </div>
                          <fieldset className="saas-admin__feature-grid">
                            <legend>Enabled governed workflows</legend>
                            {aiFeatures.map((feature) => (
                              <label key={feature.code}>
                                <input
                                  type="checkbox"
                                  checked={aiSettings.enabled_features.includes(feature.code)}
                                  onChange={(event) => toggleAIFeature(feature.code, event.target.checked)}
                                />
                                <span><strong>{feature.label}</strong><small>{feature.context_kind.replaceAll("_", " ")}</small></span>
                              </label>
                            ))}
                          </fieldset>
                          <div className="saas-admin__checks saas-admin__checks--stacked">
                            <label><input type="checkbox" checked={aiSettings.enabled} onChange={(event) => setAISettings({ ...aiSettings, enabled: event.target.checked })} /> Enable AI for this tenant</label>
                            <label>
                              <input type="checkbox" checked={aiSettings.allow_external_document_context} onChange={(event) => setAISettings({ ...aiSettings, allow_external_document_context: event.target.checked })} />
                              Permit authorised controlled-document excerpts to be sent to the configured provider
                            </label>
                          </div>
                          <div className="saas-admin__actions">
                            <button type="button" className="primary" onClick={() => void saveAISettings()} disabled={busyAction !== null}>
                              {busyAction === "save:ai-settings" ? "Saving AI plan…" : "Save tenant AI plan"}
                            </button>
                          </div>
                        </>
                      ) : <div className="saas-admin__alert">AI settings could not be loaded for this tenant.</div>}
                    </section>
                  ) : null}
                  <div className="saas-admin__actions">
                    <button type="button" className="primary" onClick={() => void saveProvider()} disabled={busyAction !== null}>
                      {busyAction === `save:${provider.provider}` ? "Saving…" : "Save encrypted configuration"}
                    </button>
                    <button type="button" onClick={() => void testProvider()} disabled={busyAction !== null}>
                      {busyAction === `test:${provider.provider}`
                        ? provider.provider === "openai" ? "Testing…" : "Queueing…"
                        : provider.provider === "openai" ? "Test AI connection now" : "Queue backend health check"}
                    </button>
                  </div>
                  {provider.last_health_detail ? <p className="saas-admin__health-detail">Last check: {provider.last_health_detail} {provider.last_latency_ms != null ? `(${provider.last_latency_ms} ms)` : ""}</p> : null}
                </>
              ) : <p>Select a provider.</p>}
            </section>
          </div>
        ) : null}

        {tab === "modules" ? (
          <section className="saas-admin__card">
            <div className="saas-admin__card-heading"><div><h2>Module subscriptions and plans</h2><p>Tenant administrators can purchase configured plans; only superadmins can directly change global pricing or force module state.</p></div></div>
            <div className="saas-admin__table-wrap">
              <table><thead><tr><th>Module</th><th>Current state</th><th>Plan</th><th>Available price</th><th>Action</th></tr></thead><tbody>
                {(setup?.module_prices ?? []).map((price) => {
                  const module = setup?.modules.find((row) => row.module_code === price.module_code);
                  return (
                    <tr key={price.id}>
                      <td><strong>{price.module_code}</strong><small>{price.billing_term}</small></td>
                      <td><Status value={module?.status || "NOT SUBSCRIBED"} /></td>
                      <td>{price.plan_code}</td>
                      <td>{formatMoney(price.amount_cents, price.currency)}</td>
                      <td>
                        {setup?.permissions.start_tenant_checkout ? (
                          <button type="button" onClick={() => void checkout(price.id)} disabled={busyAction !== null || !price.external_price_ref}>
                            {busyAction === `checkout:${price.id}` ? "Preparing checkout…" : price.external_price_ref ? "Start Stripe checkout" : "Stripe price not configured"}
                          </button>
                        ) : <span>Superadmin pricing control</span>}
                      </td>
                    </tr>
                  );
                })}
              </tbody></table>
            </div>
          </section>
        ) : null}

        {tab === "billing" ? (
          <section className="saas-admin__card">
            <div className="saas-admin__card-heading"><div><h2>Invoices and fiscalization</h2><p>Only invoices belonging to the selected tenant are returned. Uncertain eTIMS outcomes remain blocked for reconciliation.</p></div></div>
            <div className="saas-admin__table-wrap">
              <table><thead><tr><th>Invoice</th><th>Issued</th><th>Amount</th><th>Status</th><th>Fiscalization</th><th>Action</th></tr></thead><tbody>
                {(setup?.invoices ?? []).map((invoice) => (
                  <tr key={invoice.id}>
                    <td><strong>{invoice.invoice_number}</strong><small>{invoice.description || invoice.id}</small></td>
                    <td>{formatTime(invoice.issued_at)}</td>
                    <td>{formatMoney(invoice.amount_cents, invoice.currency)}</td>
                    <td><Status value={invoice.status} /></td>
                    <td><Status value={invoice.fiscalization?.status || "NOT SUBMITTED"} />{invoice.fiscalization?.last_error ? <small>{invoice.fiscalization.last_error}</small> : null}</td>
                    <td>
                      <select
                        aria-label={`Fiscalization provider for ${invoice.invoice_number}`}
                        defaultValue="etims_oscu"
                        id={`fiscal-provider-${invoice.id}`}
                      ><option value="etims_oscu">OSCU</option><option value="etims_vscu">VSCU</option></select>
                      <button
                        type="button"
                        disabled={busyAction !== null || invoice.fiscalization?.status === "FISCALIZED" || invoice.fiscalization?.status === "RECONCILIATION_REQUIRED"}
                        onClick={() => {
                          const element = document.getElementById(`fiscal-provider-${invoice.id}`) as HTMLSelectElement | null;
                          void fiscalize(invoice, (element?.value || "etims_oscu") as "etims_oscu" | "etims_vscu");
                        }}
                      >{busyAction === `fiscalize:${invoice.id}` ? "Queueing…" : "Queue eTIMS"}</button>
                    </td>
                  </tr>
                ))}
              </tbody></table>
            </div>
          </section>
        ) : null}

        {tab === "pipeline" ? (
          <section className="saas-admin__card">
            <div className="saas-admin__card-heading"><div><h2>Durable backend pipeline</h2><p>Provider health, billing, AI and fiscalization actions are processed asynchronously with leases, retries and audit events.</p></div><button type="button" onClick={() => void load()}>Refresh</button></div>
            <div className="saas-admin__table-wrap">
              <table><thead><tr><th>Created</th><th>Job</th><th>Queue</th><th>Status</th><th>Attempts</th><th>Worker/error/action</th></tr></thead><tbody>
                {jobs.map((job) => {
                  const jobCheckoutUrl = checkoutUrlFromJob(job);
                  return (
                    <tr key={job.id}>
                      <td>{formatTime(job.created_at)}</td>
                      <td><strong>{job.job_type}</strong><small>{job.id}</small></td>
                      <td>{job.queue_name}</td>
                      <td><Status value={job.status} /></td>
                      <td>{job.attempt_count}/{job.max_attempts}</td>
                      <td>
                        {job.last_error || job.locked_by || "—"}
                        {jobCheckoutUrl ? <small><a href={jobCheckoutUrl}>Open secure Stripe checkout</a></small> : null}
                      </td>
                    </tr>
                  );
                })}
              </tbody></table>
            </div>
          </section>
        ) : null}

        {tab === "readiness" ? (
          <div className="saas-admin__readiness-grid">
            <section className="saas-admin__card">
              <h2>Deployment-managed requirements</h2>
              <p>These values are intentionally not editable in the browser. They protect encryption, database access and broker service identities.</p>
              {(setup?.deployment_readiness ?? []).map((item) => (
                <div className="saas-admin__readiness-row" key={item.key}>
                  <div><strong>{item.label}</strong><small>{item.key}</small></div>
                  <Status value={item.configured ? "CONFIGURED" : "MISSING"} />
                </div>
              ))}
            </section>
            <section className="saas-admin__card">
              <h2>Provider callback setup</h2>
              <p>Register this public HTTPS URL as the Stripe webhook destination. Tenant-scoped and platform endpoint secrets are verified server-side.</p>
              <code>{webhookUrl}</code>
              <div className="saas-admin__actions"><button type="button" onClick={() => void copyWebhook()}>Copy webhook URL</button></div>
              <h3>Access boundaries</h3>
              <ul>
                <li>AMO admins: own tenant credentials, health checks, modules, invoices and tenant jobs.</li>
                <li>Superadmins: platform defaults, all tenants, global prices, API keys and infrastructure operations.</li>
                <li>Provider secrets: encrypted server-side and never read back into the form.</li>
              </ul>
            </section>
          </div>
        ) : null}
      </div>
    </DepartmentLayout>
  );
}
