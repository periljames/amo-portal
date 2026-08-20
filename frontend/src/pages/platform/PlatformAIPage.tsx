import React, { useEffect, useState } from "react";

import { aiControlApi, type AIPlaygroundResult, type AITenantPolicy } from "../../services/aiControl";
import { platformApi } from "../../services/platformControl";
import { MetricCard, PlatformShell, StatusBadge } from "./components/PlatformShared";
import { usePlatformData } from "./components/usePlatformData";

const usd = (micros?: number | null) => `$${(Number(micros || 0) / 1_000_000).toFixed(6)}`;
const errorText = (error: unknown) => error instanceof Error ? error.message : String(error);
const defaultModel: Record<string, string> = {
  STANDARD: "gpt-5.6-luna",
  ADVANCED: "gpt-5.6-terra",
  PROFESSIONAL: "gpt-5.6-sol",
};

type AIStatusPayload = {
  provider?: { status?: string; scope?: string; display_name?: string } | null;
  tenant_policy?: { tenant_id?: string } | null;
};

export default function PlatformAIPage() {
  const tenants = usePlatformData(() => platformApi.tenants({ limit: 200 }), [], { pollMs: 60_000 });
  const catalog = usePlatformData(() => aiControlApi.catalog(), [], { pollMs: 60_000 });
  const [tenantId, setTenantId] = useState("");
  const policy = usePlatformData(() => tenantId ? aiControlApi.policy(tenantId) : Promise.resolve(null), [tenantId]);
  const usage = usePlatformData(() => tenantId ? aiControlApi.usage(tenantId) : Promise.resolve(null), [tenantId]);
  const status = usePlatformData(() => aiControlApi.status(tenantId || null), [tenantId], { pollMs: 20_000 });

  const [model, setModel] = useState("gpt-5.6-luna");
  const [prompt, setPrompt] = useState("Explain what you can safely help an AMO administrator test in this portal. Do not claim you changed any records.");
  const [tenantMetering, setTenantMetering] = useState(false);
  const [result, setResult] = useState<AIPlaygroundResult | null>(null);
  const [runError, setRunError] = useState<string | null>(null);
  const [running, setRunning] = useState(false);

  const [enabled, setEnabled] = useState(false);
  const [plan, setPlan] = useState("STANDARD");
  const [budgetUsd, setBudgetUsd] = useState("0");
  const [allowDocs, setAllowDocs] = useState(false);
  const [policyError, setPolicyError] = useState<string | null>(null);
  const [policyNotice, setPolicyNotice] = useState<string | null>(null);

  // usePlatformData deliberately retains its previous value while a new request
  // is loading. Never treat that retained value as belonging to the newly
  // selected tenant: require the server-returned tenant_id to match first.
  const currentPolicy = tenantId && policy.data?.tenant_id === tenantId
    ? policy.data as AITenantPolicy
    : null;
  const currentUsage = tenantId && usage.data?.tenant_id === tenantId ? usage.data : null;
  const statusData = status.data as AIStatusPayload | null;
  const statusMatchesTenant = !tenantId || statusData?.tenant_policy?.tenant_id === tenantId;
  const provider = statusMatchesTenant ? statusData?.provider ?? null : null;
  const models = catalog.data?.models ?? [];

  useEffect(() => {
    // A tenant switch is a security boundary. Clear all tenant-derived controls,
    // metering intent and result state before the next tenant policy arrives.
    setTenantMetering(false);
    setResult(null);
    setRunError(null);
    setPolicyError(null);
    setPolicyNotice(null);
    setEnabled(false);
    setPlan("STANDARD");
    setModel("gpt-5.6-luna");
    setBudgetUsd("0");
    setAllowDocs(false);
  }, [tenantId]);

  useEffect(() => {
    if (!currentPolicy) return;
    setEnabled(currentPolicy.enabled);
    setPlan(currentPolicy.plan_code);
    setModel(currentPolicy.model);
    setBudgetUsd(String(currentPolicy.monthly_budget_microusd / 1_000_000));
    setAllowDocs(currentPolicy.allow_external_documents);
  }, [currentPolicy]);

  const savePolicy = async () => {
    if (!tenantId) return;
    if (!currentPolicy || policy.loading) {
      setPolicyError("Wait for the selected tenant AI policy to finish loading before making changes.");
      return;
    }
    setPolicyError(null);
    setPolicyNotice(null);
    try {
      const updated = await aiControlApi.updatePolicy(tenantId, {
        enabled,
        plan_code: plan,
        model: defaultModel[plan],
        monthly_budget_microusd: Math.max(0, Math.round(Number(budgetUsd || 0) * 1_000_000)),
        hard_limit: true,
        allow_external_documents: allowDocs,
        markup_bps: 0,
        reason: "AI policy updated from superadmin AI Control Centre",
      });
      if (updated.policy.tenant_id !== tenantId) {
        throw new Error("Tenant scope mismatch while saving AI policy. No cross-tenant result was accepted.");
      }
      setModel(defaultModel[plan]);
      setPolicyNotice("Tenant AI policy saved and audited.");
      policy.reload();
      usage.reload();
    } catch (error) {
      setPolicyError(errorText(error));
    }
  };

  const runTest = async () => {
    if (tenantMetering && (!tenantId || !currentPolicy?.enabled)) {
      setRunError("Tenant-metered testing requires the selected tenant to have AI enabled.");
      return;
    }
    setRunning(true);
    setRunError(null);
    setResult(null);
    try {
      const next = await aiControlApi.playground({
        prompt,
        // Platform tests remain platform-only. A tenant identifier is sent only
        // when the administrator explicitly enables tenant metering.
        tenant_id: tenantMetering ? tenantId : null,
        model,
        charge_tenant: tenantMetering,
        feature_code: "platform.playground",
      });
      if (tenantMetering && next.tenant_id !== tenantId) {
        throw new Error("Tenant scope mismatch in AI response. The result was discarded.");
      }
      setResult(next);
      if (tenantMetering) usage.reload();
    } catch (error) {
      setRunError(errorText(error));
    } finally {
      setRunning(false);
    }
  };

  return (
    <PlatformShell title="AI Control Centre" subtitle="Live OpenAI testing, tenant entitlements and auditable token/cost metering from the superadmin portal.">
      <section className="platform-grid">
        <MetricCard label="Provider" value={provider?.display_name ?? "OpenAI"} caption={provider?.scope ? `${provider.scope} credential` : "Configure in Provider Registry"} mark="AI" />
        <MetricCard label="Health" value={<StatusBadge value={provider?.status ?? "NOT_CONFIGURED"} />} caption="Server-side credential only" mark="HC" />
        <MetricCard label="Tenant requests" value={currentUsage?.requests ?? 0} caption={tenantId && currentUsage ? currentUsage.month : "Select tenant"} mark="RQ" />
        <MetricCard label="Measured usage" value={usd(currentUsage?.customer_charge_microusd)} caption="Current selected tenant month" mark="$" />
      </section>

      <section className="platform-two">
        <div className="platform-card">
          <div className="platform-section-title"><div><h2>Live admin test</h2><p>Default mode is platform-only test usage. Tenant ID and billing are sent only after the explicit metering switch is enabled.</p></div><StatusBadge value={tenantMetering ? "TENANT_METERED" : "PLATFORM_TEST"} /></div>
          <div className="platform-form" style={{ gridTemplateColumns: "1fr 1fr" }}>
            <label><span>Tenant policy scope</span><select value={tenantId} onChange={(event) => setTenantId(event.target.value)}><option value="">Platform only</option>{(tenants.data?.items ?? []).map((tenant) => <option key={tenant.id} value={tenant.id}>{tenant.name} · {tenant.amo_code}</option>)}</select></label>
            <label><span>Model</span><select value={model} onChange={(event) => setModel(event.target.value)}>{models.map((item) => <option key={item.model} value={item.model}>{item.display_name} · {item.tier}</option>)}</select></label>
          </div>
          <label style={{ display: "grid", gap: 5, marginTop: 10 }}><span>Prompt</span><textarea rows={8} value={prompt} onChange={(event) => setPrompt(event.target.value)} /></label>
          <div className="platform-actions" style={{ marginTop: 10 }}><label style={{ display: "flex", gap: 8, alignItems: "center" }}><input type="checkbox" checked={tenantMetering} disabled={!tenantId || policy.loading || !currentPolicy?.enabled} onChange={(event) => setTenantMetering(event.target.checked)} />Record against selected tenant</label><button className="platform-btn primary" disabled={running || !prompt.trim() || (tenantMetering && !currentPolicy?.enabled)} onClick={runTest}>{running ? "Running…" : "Run live AI test"}</button></div>
          {runError ? <div className="platform-error">{runError}</div> : null}
          {result ? <div className="platform-card" style={{ marginTop: 12 }}><div className="platform-section-title"><div><h3>Response</h3><p>{result.model} · {result.latency_ms} ms · provider cost {usd(result.provider_cost_microusd)}</p></div><StatusBadge value="SUCCEEDED" /></div><div style={{ whiteSpace: "pre-wrap" }}>{result.text}</div><p><small>Input {result.usage.input_tokens.toLocaleString()} · cached {result.usage.cached_input_tokens.toLocaleString()} · output {result.usage.output_tokens.toLocaleString()} tokens</small></p></div> : null}
        </div>

        <div className="platform-card">
          <div className="platform-section-title"><div><h2>Tenant policy</h2><p>Disabled by default. Controlled-document AI requires separate permission.</p></div><StatusBadge value={currentPolicy?.status ?? (tenantId && policy.loading ? "LOADING" : "NO_TENANT")} /></div>
          {!tenantId ? <p>Select a tenant to manage AI access.</p> : !currentPolicy ? <p>Loading the selected tenant AI policy…</p> : <><div className="platform-form" style={{ gridTemplateColumns: "1fr 1fr" }}><label><span>Plan</span><select value={plan} onChange={(event) => setPlan(event.target.value)}><option value="STANDARD">Standard · Luna</option><option value="ADVANCED">Advanced · Terra</option><option value="PROFESSIONAL">Professional · Sol</option></select></label><label><span>Monthly limit (USD)</span><input inputMode="decimal" value={budgetUsd} onChange={(event) => setBudgetUsd(event.target.value)} /></label></div><div className="platform-stack" style={{ marginTop: 10 }}><label style={{ display: "flex", gap: 8 }}><input type="checkbox" checked={enabled} onChange={(event) => setEnabled(event.target.checked)} />Enable tenant AI</label><label style={{ display: "flex", gap: 8 }}><input type="checkbox" checked={allowDocs} onChange={(event) => setAllowDocs(event.target.checked)} />Allow authorised document excerpts to external AI</label></div><button className="platform-btn primary" style={{ marginTop: 12 }} disabled={policy.loading} onClick={savePolicy}>Save policy</button>{policyNotice ? <p>{policyNotice}</p> : null}{policyError ? <div className="platform-error">{policyError}</div> : null}</>}
          {currentUsage ? <div className="platform-list" style={{ marginTop: 14 }}><div className="platform-list-row"><strong>Input tokens</strong><span>{currentUsage.input_tokens.toLocaleString()}</span></div><div className="platform-list-row"><strong>Output tokens</strong><span>{currentUsage.output_tokens.toLocaleString()}</span></div><div className="platform-list-row"><strong>Provider cost</strong><span>{usd(currentUsage.provider_cost_microusd)}</span></div><div className="platform-list-row"><strong>Metered amount</strong><span>{usd(currentUsage.customer_charge_microusd)}</span></div></div> : null}
        </div>
      </section>

      <section className="platform-card"><div className="platform-section-title"><div><h2>Approved model catalogue</h2><p>Unknown models fail closed until an audited rate snapshot exists.</p></div></div><div style={{ overflowX: "auto" }}><table className="platform-table"><thead><tr><th>Tier</th><th>Model</th><th>Input / 1M</th><th>Cached / 1M</th><th>Output / 1M</th><th>Effective</th></tr></thead><tbody>{models.map((item) => <tr key={item.model}><td>{item.tier}</td><td>{item.display_name}</td><td>{usd(item.input_microusd_per_million)}</td><td>{usd(item.cached_input_microusd_per_million)}</td><td>{usd(item.output_microusd_per_million)}</td><td>{item.effective_from}</td></tr>)}</tbody></table></div></section>
    </PlatformShell>
  );
}
