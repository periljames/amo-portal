import React, { useCallback, useEffect, useMemo, useState } from "react";

import { platformApi } from "../../../services/platformControl";
import { resendEmailApi, type ResendStatus } from "../../../services/resendEmail";
import { StatusBadge } from "./PlatformShared";

const PRODUCTION_CONFIRMATION = "ENABLE RESEND PRODUCTION";
const RESEND_API_URL = "https://api.resend.com";

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
  const [status, setStatus] = useState<ResendStatus | null>(null);
  const [draft, setDraft] = useState<Draft>(defaults);
  const [apiKey, setApiKey] = useState("");
  const [webhookSecret, setWebhookSecret] = useState("");
  const [productionConfirmation, setProductionConfirmation] = useState("");
  const [testRecipient, setTestRecipient] = useState("");
  const [busy, setBusy] = useState<string | null>(null);
  const [notice, setNotice] = useState<string | null>(null);
  const [error, setError] = useState<string | null>(null);

  const load = useCallback(async () => {
    const next = await resendEmailApi.status();
    setStatus(next);
    setDraft(readDraft(next));
    setTestRecipient(String(next.config?.health_check_recipient ?? next.config?.sandbox_recipient ?? ""));
  }, []);

  useEffect(() => {
    load().catch((caught) => setError(caught instanceof Error ? caught.message : String(caught)));
  }, [load]);

  const healthIsStale = useMemo(() => {
    if (status?.status !== "HEALTHY" || !status.last_checked_at) return true;
    return Date.now() - new Date(status.last_checked_at).getTime() > 24 * 60 * 60 * 1000;
  }, [status?.last_checked_at, status?.status]);

  const setField = (field: keyof Draft, value: string) => {
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
      await load();
      setNotice("Configuration saved. Automatic email stays blocked until one explicit test email is accepted with the current settings.");
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
      await load();
      setNotice(`Resend accepted the explicit test email. Message ID: ${String(result.result?.message_id ?? result.id)}. The current configuration is now delivery-ready.`);
    } catch (caught) {
      setError(caught instanceof Error ? caught.message : String(caught));
    } finally {
      setBusy(null);
    }
  };

  return (
    <section className="platform-card" style={{ marginBottom: 16 }}>
      <div className="platform-actions" style={{ justifyContent: "space-between", alignItems: "flex-start" }}>
        <div>
          <h2 style={{ marginTop: 0 }}>Resend email delivery</h2>
          <p>
            The API key is encrypted by the backend. The browser receives only a fingerprint. Saving any replacement
            key or configuration invalidates delivery readiness so stale settings cannot authorize email.
          </p>
        </div>
        <StatusBadge value={status?.status ?? "NOT_CONFIGURED"} />
      </div>

      <div className="platform-grid" style={{ marginBottom: 14 }}>
        <div><small>Stored secret</small><br /><strong>{status?.has_secret ? status.secret_fingerprint ?? "Yes" : "No"}</strong></div>
        <div><small>Last check</small><br /><strong>{status?.last_checked_at ? new Date(status.last_checked_at).toLocaleString() : "Never"}</strong></div>
        <div><small>Latency</small><br /><strong>{status?.last_latency_ms != null ? `${status.last_latency_ms} ms` : "-"}</strong></div>
        <div><small>Sending mode</small><br /><strong>{draft.sending_mode}</strong></div>
      </div>

      {status?.status === "AUTHENTICATED" ? (
        <div className="platform-error">The API key authenticated successfully, but automatic email remains blocked until one explicit test email is accepted.</div>
      ) : healthIsStale && status?.has_secret ? (
        <div className="platform-error">Automatic email is blocked because the current Resend configuration is not delivery-ready or its successful test is stale.</div>
      ) : null}
      {status?.last_health_detail ? <p><small>{status.last_health_detail}</small></p> : null}

      <div className="platform-form" style={{ gridTemplateColumns: "repeat(auto-fit, minmax(240px, 1fr))" }}>
        <label>
          <span>Resend API key</span>
          <input type="password" autoComplete="new-password" value={apiKey} onChange={(event) => setApiKey(event.target.value)} placeholder={status?.has_secret ? "Leave blank to preserve the encrypted key" : "re_xxxxxxxxx"} />
        </label>
        <label>
          <span>Webhook signing secret</span>
          <input type="password" autoComplete="new-password" value={webhookSecret} onChange={(event) => setWebhookSecret(event.target.value)} placeholder="Optional: whsec_xxxxxxxxx" />
        </label>
        <label>
          <span>Sending mode</span>
          <select value={draft.sending_mode} onChange={(event) => setField("sending_mode", event.target.value as Draft["sending_mode"])}>
            <option value="DISABLED">Disabled — store configuration only</option>
            <option value="SANDBOX">Sandbox — reroute all portal mail</option>
            <option value="PRODUCTION">Production — deliver to actual recipients</option>
          </select>
        </label>
        <label>
          <span>API endpoint</span>
          <input value={RESEND_API_URL} readOnly aria-readonly="true" title="Pinned to prevent API-key exfiltration" />
        </label>
        <label>
          <span>From email</span>
          <input value={draft.from_email} onChange={(event) => setField("from_email", event.target.value)} placeholder="notifications@notify.example.com" />
        </label>
        <label>
          <span>From name</span>
          <input value={draft.from_name} onChange={(event) => setField("from_name", event.target.value)} />
        </label>
        <label>
          <span>Reply-to</span>
          <input value={draft.reply_to} onChange={(event) => setField("reply_to", event.target.value)} />
        </label>
        <label>
          <span>Sandbox recipient</span>
          <input value={draft.sandbox_recipient} onChange={(event) => setField("sandbox_recipient", event.target.value)} placeholder="All non-production mail is rerouted here" />
        </label>
        <label>
          <span>Explicit test recipient</span>
          <input value={draft.health_check_recipient} onChange={(event) => { setField("health_check_recipient", event.target.value); setTestRecipient(event.target.value); }} />
        </label>
        <label>
          <span>Maximum per minute</span>
          <input type="number" min="1" max="60" value={draft.per_minute_limit} onChange={(event) => setField("per_minute_limit", event.target.value)} />
        </label>
        <label>
          <span>Maximum per UTC day</span>
          <input type="number" min="1" max="100000" value={draft.daily_limit} onChange={(event) => setField("daily_limit", event.target.value)} />
        </label>
      </div>

      <label style={{ display: "block", marginTop: 12 }}>
        <span>Published Resend template mapping (JSON)</span>
        <textarea rows={6} value={draft.template_map_json} onChange={(event) => setField("template_map_json", event.target.value)} placeholder={'{"finding-issued":"template-alias-or-id"}'} />
      </label>
      {status?.template_keys?.length ? <small>Recommended keys: {status.template_keys.join(", ")}</small> : null}

      {draft.sending_mode === "PRODUCTION" ? (
        <label style={{ display: "block", marginTop: 12 }}>
          <span>Production activation phrase</span>
          <input value={productionConfirmation} onChange={(event) => setProductionConfirmation(event.target.value)} placeholder={PRODUCTION_CONFIRMATION} />
          <small>Production mode is also rejected unless the backend deployment environment is production and the sender uses a custom domain.</small>
        </label>
      ) : null}

      {error ? <div className="platform-error">{error}</div> : null}
      {notice ? <p><StatusBadge value="PENDING" /> {notice}</p> : null}

      <div className="platform-actions" style={{ marginTop: 14 }}>
        <button className="platform-btn primary" disabled={Boolean(busy)} onClick={save}>{busy === "save" ? "Saving…" : "Save Resend configuration"}</button>
        <button className="platform-btn" disabled={Boolean(busy) || !status?.has_secret} onClick={checkHealth}>{busy === "health" ? "Checking…" : "Queue API authentication check"}</button>
      </div>

      <div className="platform-form" style={{ gridTemplateColumns: "1fr auto", marginTop: 14 }}>
        <input value={testRecipient} onChange={(event) => setTestRecipient(event.target.value)} placeholder="Single explicit test recipient" />
        <button className="platform-btn" disabled={Boolean(busy) || !status?.has_secret} onClick={sendTest}>{busy === "test" ? "Sending…" : "Send one test email"}</button>
      </div>
      <small>The API check sends nothing. The explicit test sends one rate-deduplicated message and is the only action that marks the current configuration delivery-ready.</small>
    </section>
  );
}
