import React, { useCallback, useEffect, useMemo, useRef, useState } from "react";

import { platformApi } from "../../../services/platformControl";
import { resendEmailApi, type ResendStatus } from "../../../services/resendEmail";
import { StatusBadge } from "./PlatformShared";
import { PLATFORM_CONSOLE_LIVE_EVENT } from "./usePlatformRealtime";

const PRODUCTION_CONFIRMATION = "ENABLE RESEND PRODUCTION";
const RESEND_API_URL = "https://api.resend.com";

type EmailPanelTab = "configuration" | "templates" | "verification";

type Draft = {
  api_base_url: string;
  from_email: string;
  from_name: string;
  reply_to: string;
  sending_mode: "DISABLED" | "SANDBOX" | "PRODUCTION";
  sandbox_recipient: string;
  health_check_recipient: string;
  per_minute_limit: string;
  daily_limit: string;
  template_map_json: string;
};

const defaults: Draft = {
  api_base_url: RESEND_API_URL,
  from_email: "onboarding@resend.dev",
  from_name: "AMO Portal",
  reply_to: "",
  sending_mode: "DISABLED",
  sandbox_recipient: "",
  health_check_recipient: "",
  per_minute_limit: "10",
  daily_limit: "500",
  template_map_json: "{}",
};

function readDraft(status: ResendStatus): Draft {
  const config = status.config ?? {};
  return {
    api_base_url: RESEND_API_URL,
    from_email: String(config.from_email ?? defaults.from_email),
    from_name: String(config.from_name ?? defaults.from_name),
    reply_to: String(config.reply_to ?? ""),
    sending_mode: String(config.sending_mode ?? "DISABLED").toUpperCase() as Draft["sending_mode"],
    sandbox_recipient: String(config.sandbox_recipient ?? ""),
    health_check_recipient: String(config.health_check_recipient ?? ""),
    per_minute_limit: String(config.per_minute_limit ?? "10"),
    daily_limit: String(config.daily_limit ?? "500"),
    template_map_json: String(config.template_map_json ?? "{}"),
  };
}

export default function ResendEmailConfigPanel() {
  const [panelTab, setPanelTab] = useState<EmailPanelTab>("configuration");
  const [status, setStatus] = useState<ResendStatus | null>(null);
  const [draft, setDraft] = useState<Draft>(defaults);
  const [apiKey, setApiKey] = useState("");
  const [webhookSecret, setWebhookSecret] = useState("");
  const [productionConfirmation, setProductionConfirmation] = useState("");
  const [testRecipient, setTestRecipient] = useState("");
  const [busy, setBusy] = useState<string | null>(null);
  const [notice, setNotice] = useState<string | null>(null);
  const [error, setError] = useState<string | null>(null);
  const dirtyRef = useRef(false);
  const liveRefreshRef = useRef<number | null>(null);

  const load = useCallback(async (preserveDraft = true) => {
    const next = await resendEmailApi.status();
    setStatus(next);
    if (!preserveDraft || !dirtyRef.current) {
      const nextDraft = readDraft(next);
      setDraft(nextDraft);
      setTestRecipient(String(next.config?.health_check_recipient ?? next.config?.sandbox_recipient ?? ""));
      dirtyRef.current = false;
    }
  }, []);

  useEffect(() => {
    load(false).catch((caught) => setError(caught instanceof Error ? caught.message : String(caught)));
  }, [load]);

  useEffect(() => {
    const refresh = () => {
      if (document.visibilityState !== "visible") return;
      if (liveRefreshRef.current) window.clearTimeout(liveRefreshRef.current);
      liveRefreshRef.current = window.setTimeout(() => {
        void load(true).catch(() => undefined);
      }, 300);
    };
    window.addEventListener(PLATFORM_CONSOLE_LIVE_EVENT, refresh);
    window.addEventListener("focus", refresh);
    return () => {
      window.removeEventListener(PLATFORM_CONSOLE_LIVE_EVENT, refresh);
      window.removeEventListener("focus", refresh);
      if (liveRefreshRef.current) window.clearTimeout(liveRefreshRef.current);
    };
  }, [load]);

  const healthIsStale = useMemo(() => {
    if (status?.status !== "HEALTHY" || !status.last_checked_at) return true;
    return Date.now() - new Date(status.last_checked_at).getTime() > 24 * 60 * 60 * 1000;
  }, [status?.last_checked_at, status?.status]);

  const setField = (field: keyof Draft, value: string) => {
    dirtyRef.current = true;
    setDraft((current) => ({ ...current, [field]: value }));
  };

  const save = async () => {
    setBusy("save");
    setError(null);
    setNotice(null);
    try {
      JSON.parse(draft.template_map_json || "{}");
      const secret: Record<string, string> = {};
      if (apiKey.trim()) secret.api_key = apiKey.trim();
      if (webhookSecret.trim()) secret.webhook_signing_secret = webhookSecret.trim();
      await platformApi.updateSaasProvider("resend", {
        config: {
          ...draft,
          api_base_url: RESEND_API_URL,
          per_minute_limit: Number(draft.per_minute_limit),
          daily_limit: Number(draft.daily_limit),
        },
        ...(Object.keys(secret).length ? { secret } : {}),
        enabled: true,
        production_confirmation: productionConfirmation,
        reason: "Resend email configuration updated by platform superuser",
      });
      setApiKey("");
      setWebhookSecret("");
      setProductionConfirmation("");
      dirtyRef.current = false;
      await load(false);
      setNotice("Configuration saved. Automatic email remains blocked until one explicit test email is accepted with the current settings.");
    } catch (caught) {
      setError(caught instanceof Error ? caught.message : String(caught));
    } finally {
      setBusy(null);
    }
  };

  const checkHealth = async () => {
    setBusy("health");
    setError(null);
    try {
      const job = await platformApi.testSaasProvider("resend");
      setNotice(`API authentication check queued as ${job.id}. This check sends no email and does not enable automatic delivery.`);
    } catch (caught) {
      setError(caught instanceof Error ? caught.message : String(caught));
    } finally {
      setBusy(null);
    }
  };

  const sendTest = async () => {
    if (!testRecipient.trim()) {
      setError("Enter the single recipient for the explicit test email.");
      return;
    }
    setBusy("test");
    setError(null);
    try {
      const result = await resendEmailApi.sendTest(testRecipient.trim());
      dirtyRef.current = false;
      await load(false);
      setNotice(`Resend accepted the explicit test email. Message ID: ${String(result.result?.message_id ?? result.id)}. The current configuration is now delivery-ready.`);
    } catch (caught) {
      setError(caught instanceof Error ? caught.message : String(caught));
    } finally {
      setBusy(null);
    }
  };

  return (
    <section className="platform-card">
      <div className="platform-section-title">
        <div><h2>Resend email delivery</h2><p>Encrypted platform credentials, sender policy, templates and delivery verification.</p></div>
        <StatusBadge value={status?.status ?? "NOT_CONFIGURED"} />
      </div>

      <div className="platform-health-strip">
        <div><small>Stored secret</small><strong>{status?.has_secret ? status.secret_fingerprint ?? "Yes" : "No"}</strong></div>
        <div><small>Last verified</small><strong>{status?.last_checked_at ? new Date(status.last_checked_at).toLocaleString() : "Never"}</strong></div>
        <div><small>Latency</small><strong>{status?.last_latency_ms != null ? `${status.last_latency_ms} ms` : "-"}</strong></div>
        <div><small>Sending mode</small><strong>{draft.sending_mode}</strong></div>
      </div>

      {status?.status === "AUTHENTICATED" ? <div className="platform-error">The API key authenticated, but automatic delivery remains blocked until one explicit test email is accepted.</div> : healthIsStale && status?.has_secret ? <div className="platform-error">Automatic email is blocked because this configuration is not delivery-ready or its successful test is stale.</div> : null}
      {status?.last_health_detail ? <p><small>{status.last_health_detail}</small></p> : null}

      <nav className="platform-tabs" aria-label="Resend configuration sections">
        <button className={panelTab === "configuration" ? "active" : undefined} onClick={() => setPanelTab("configuration")}>Configuration</button>
        <button className={panelTab === "templates" ? "active" : undefined} onClick={() => setPanelTab("templates")}>Templates</button>
        <button className={panelTab === "verification" ? "active" : undefined} onClick={() => setPanelTab("verification")}>Verification & test</button>
      </nav>

      {panelTab === "configuration" ? (
        <>
          <div className="platform-form">
            <label><span>Resend API key</span><input type="password" autoComplete="new-password" value={apiKey} onChange={(event) => { dirtyRef.current = true; setApiKey(event.target.value); }} placeholder={status?.has_secret ? "Leave blank to preserve encrypted key" : "re_xxxxxxxxx"} /></label>
            <label><span>Webhook signing secret</span><input type="password" autoComplete="new-password" value={webhookSecret} onChange={(event) => { dirtyRef.current = true; setWebhookSecret(event.target.value); }} placeholder="Optional: whsec_xxxxxxxxx" /></label>
            <label><span>Sending mode</span><select value={draft.sending_mode} onChange={(event) => setField("sending_mode", event.target.value as Draft["sending_mode"])}><option value="DISABLED">Disabled — configuration only</option><option value="SANDBOX">Sandbox — reroute portal mail</option><option value="PRODUCTION">Production — actual recipients</option></select></label>
            <label><span>API endpoint</span><input value={RESEND_API_URL} readOnly aria-readonly="true" title="Pinned to prevent API-key exfiltration" /></label>
            <label><span>From email</span><input value={draft.from_email} onChange={(event) => setField("from_email", event.target.value)} placeholder="notifications@example.com" /></label>
            <label><span>From name</span><input value={draft.from_name} onChange={(event) => setField("from_name", event.target.value)} /></label>
            <label><span>Reply-to</span><input value={draft.reply_to} onChange={(event) => setField("reply_to", event.target.value)} /></label>
            <label><span>Sandbox recipient</span><input value={draft.sandbox_recipient} onChange={(event) => setField("sandbox_recipient", event.target.value)} placeholder="All non-production mail routes here" /></label>
            <label><span>Maximum per minute</span><input type="number" min="1" max="60" value={draft.per_minute_limit} onChange={(event) => setField("per_minute_limit", event.target.value)} /></label>
            <label><span>Maximum per UTC day</span><input type="number" min="1" max="100000" value={draft.daily_limit} onChange={(event) => setField("daily_limit", event.target.value)} /></label>
          </div>
          <div className="platform-actions" style={{ marginTop: 11 }}><button className="platform-btn primary" disabled={Boolean(busy)} onClick={save}>{busy === "save" ? "Saving…" : "Save configuration"}</button><button className="platform-btn" disabled={Boolean(busy) || !status?.has_secret} onClick={checkHealth}>{busy === "health" ? "Checking…" : "Queue authentication check"}</button></div>
        </>
      ) : null}

      {panelTab === "templates" ? (
        <>
          <label className="platform-field-block"><span>Published Resend template mapping (JSON)</span><textarea className="platform-code-editor" value={draft.template_map_json} onChange={(event) => setField("template_map_json", event.target.value)} placeholder={'{"finding-issued":"template-alias-or-id"}'} /></label>
          {status?.template_keys?.length ? <small>Recommended keys: {status.template_keys.join(", ")}</small> : null}
          <div className="platform-actions" style={{ marginTop: 11 }}><button className="platform-btn primary" disabled={Boolean(busy)} onClick={save}>{busy === "save" ? "Saving…" : "Publish template mapping"}</button></div>
        </>
      ) : null}

      {panelTab === "verification" ? (
        <>
          <div className="platform-form">
            <label><span>Explicit test recipient</span><input value={testRecipient} onChange={(event) => { dirtyRef.current = true; setTestRecipient(event.target.value); setField("health_check_recipient", event.target.value); }} placeholder="Single recipient for the delivery test" /></label>
            {draft.sending_mode === "PRODUCTION" ? <label><span>Production activation phrase</span><input value={productionConfirmation} onChange={(event) => { dirtyRef.current = true; setProductionConfirmation(event.target.value); }} placeholder={PRODUCTION_CONFIRMATION} /></label> : null}
          </div>
          <p><small>The authentication check sends nothing. The explicit test sends one rate-deduplicated message and is the only action that marks the current configuration delivery-ready. Production also requires a verified custom sender domain and a production backend environment.</small></p>
          <div className="platform-actions"><button className="platform-btn" disabled={Boolean(busy) || !status?.has_secret} onClick={checkHealth}>{busy === "health" ? "Checking…" : "Check API authentication"}</button><button className="platform-btn primary" disabled={Boolean(busy) || !status?.has_secret || !testRecipient.trim()} onClick={sendTest}>{busy === "test" ? "Sending…" : "Send one test email"}</button>{draft.sending_mode === "PRODUCTION" ? <button className="platform-btn" disabled={Boolean(busy)} onClick={save}>Save production activation</button> : null}</div>
        </>
      ) : null}

      {error ? <div className="platform-error" style={{ marginTop: 11 }}>{error}</div> : null}
      {notice ? <p><StatusBadge value="PENDING" /> {notice}</p> : null}
    </section>
  );
}
