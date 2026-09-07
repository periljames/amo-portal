import React, { useEffect, useMemo, useState } from "react";
import { useSearchParams } from "react-router-dom";

import {
  platformApi,
  type SaaSProvider,
  type SaaSProviderSetupField,
  type SupportTicket,
} from "../../services/platformControl";
import {
  DataTable,
  EmptyState,
  ErrorState,
  PlatformShell,
  StatusBadge,
} from "./components/PlatformShared";
import ResendEmailConfigPanel from "./components/ResendEmailConfigPanel";
import { usePlatformData } from "./components/usePlatformData";

type IntegrationTab = "email" | "providers" | "jobs" | "webhooks" | "support";

const TABS: Array<{ id: IntegrationTab; label: string; mark: string }> = [
  { id: "email", label: "Email delivery", mark: "EM" },
  { id: "providers", label: "Provider registry", mark: "PR" },
  { id: "jobs", label: "Integration queue", mark: "JQ" },
  { id: "webhooks", label: "API keys & webhooks", mark: "API" },
  { id: "support", label: "Support center", mark: "SP" },
];

function coerceField(value: string): string | number | boolean {
  const clean = value.trim();
  if (clean === "true") return true;
  if (clean === "false") return false;
  if (/^-?\d+$/.test(clean)) return Number(clean);
  return value;
}

function normalizeTab(value: string | null): IntegrationTab {
  return TABS.some((tab) => tab.id === value) ? value as IntegrationTab : "email";
}

export default function PlatformIntegrationsPage() {
  const [searchParams, setSearchParams] = useSearchParams();
  const tab = normalizeTab(searchParams.get("tab"));
  const [keyName, setKeyName] = useState("Platform API key");
  const [webhookUrl, setWebhookUrl] = useState("");
  const [rawKey, setRawKey] = useState<string | null>(null);
  const [tenantScope, setTenantScope] = useState("");
  const [selectedProvider, setSelectedProvider] = useState<string>("");
  const [configDraft, setConfigDraft] = useState<Record<string, string>>({});
  const [secretDraft, setSecretDraft] = useState<Record<string, string>>({});
  const [providerNotice, setProviderNotice] = useState<string | null>(null);
  const [providerError, setProviderError] = useState<string | null>(null);
  const [providerBusy, setProviderBusy] = useState(false);
  const [ticketTitle, setTicketTitle] = useState("");
  const [ticketDescription, setTicketDescription] = useState("");
  const [ticketTenant, setTicketTenant] = useState("");
  const [ticketPriority, setTicketPriority] = useState("NORMAL");
  const [selectedTicketId, setSelectedTicketId] = useState<string | null>(() => searchParams.get("ticket"));
  const [ticketMessage, setTicketMessage] = useState("");
  const [messageVisibility, setMessageVisibility] = useState("PUBLIC");
  const [ticketStatusDraft, setTicketStatusDraft] = useState("OPEN");
  const [ticketPriorityDraft, setTicketPriorityDraft] = useState("NORMAL");
  const [ticketResolution, setTicketResolution] = useState("");
  const [actionNotice, setActionNotice] = useState<string | null>(null);
  const [actionError, setActionError] = useState<string | null>(null);

  const summary = usePlatformData(() => platformApi.saasCapabilities(), [], { pollMs: 15_000 });
  const providers = usePlatformData(
    () => platformApi.saasProviders(tenantScope.trim() || null),
    [tenantScope],
    { pollMs: 20_000 },
  );
  const tenants = usePlatformData(
    () => (tab === "providers" || tab === "support")
      ? platformApi.tenants({ data_mode: "REAL", limit: 250 })
      : Promise.resolve({ items: [] }),
    [tab],
  );
  const jobs = usePlatformData(
    () => tab === "jobs" ? platformApi.saasJobs({ limit: 80 }) : Promise.resolve({ items: [] }),
    [tab],
    { pollMs: 10_000 },
  );
  const keys = usePlatformData(
    () => tab === "webhooks" ? platformApi.apiKeys() : Promise.resolve({ items: [] }),
    [tab],
  );
  const hooks = usePlatformData(
    () => tab === "webhooks" ? platformApi.webhooks() : Promise.resolve({ items: [] }),
    [tab],
  );
  const tickets = usePlatformData(
    () => tab === "support" ? platformApi.saasSupportTickets({ limit: 80 }) : Promise.resolve({ items: [] }),
    [tab],
    { pollMs: 10_000 },
  );
  const ticketDetail = usePlatformData(
    () => tab === "support" && selectedTicketId ? platformApi.saasSupportTicket(selectedTicketId) : Promise.resolve(null),
    [tab, selectedTicketId],
    { pollMs: 10_000 },
  );

  const provider = useMemo(
    () => providers.data?.items?.find((item) => item.provider === selectedProvider) ?? null,
    [providers.data?.items, selectedProvider],
  );
  const providerList = useMemo(() => providers.data?.items ?? [], [providers.data?.items]);
  const nonEmailProviders = useMemo(
    () => providerList.filter((item) => item.category !== "EMAIL"),
    [providerList],
  );
  const emailProvider = useMemo(
    () => providerList.find((item) => item.provider.toLowerCase() === "resend") ?? null,
    [providerList],
  );
  const selectedTicket = ticketDetail.data as SupportTicket | null;
  const queue = (summary.data?.queue ?? {}) as Record<string, unknown>;
  const counts = (summary.data?.counts ?? {}) as Record<string, unknown>;
  const configuredProviders = providerList.filter((item) => item.status !== "NOT_CONFIGURED").length;

  useEffect(() => {
    const ticketFromUrl = searchParams.get("ticket");
    if (ticketFromUrl && ticketFromUrl !== selectedTicketId) setSelectedTicketId(ticketFromUrl);
  }, [searchParams, selectedTicketId]);

  useEffect(() => {
    if (!selectedTicket) return;
    setTicketStatusDraft(selectedTicket.status || "OPEN");
    setTicketPriorityDraft(selectedTicket.priority || "NORMAL");
    setTicketResolution(selectedTicket.resolution || "");
  }, [selectedTicket]);

  useEffect(() => {
    if (tab !== "providers" || selectedProvider || !nonEmailProviders.length) return;
    beginProviderEdit(nonEmailProviders[0]);
  }, [nonEmailProviders, selectedProvider, tab]);

  const setTab = (nextTab: IntegrationTab) => {
    const next = new URLSearchParams(searchParams);
    next.set("tab", nextTab);
    if (nextTab !== "support") next.delete("ticket");
    setSearchParams(next, { replace: true });
  };

  const selectTicket = (ticketId: string) => {
    setSelectedTicketId(ticketId);
    const next = new URLSearchParams(searchParams);
    next.set("tab", "support");
    next.set("ticket", ticketId);
    setSearchParams(next, { replace: true });
  };

  const beginProviderEdit = (item: SaaSProvider) => {
    const next: Record<string, string> = {};
    const fields = item.setup?.fields?.filter((field) => field.source === "config") ??
      item.config_fields.map((name) => ({ name, default: null }));
    fields.forEach((field) => {
      const value = item.config?.[field.name] ?? field.default;
      next[field.name] = value === undefined || value === null ? "" : String(value);
    });
    setSelectedProvider(item.provider);
    setConfigDraft(next);
    setSecretDraft({});
    setProviderNotice(null);
    setProviderError(null);
  };

  const changeTenantScope = (value: string) => {
    setTenantScope(value);
    setSelectedProvider("");
    setConfigDraft({});
    setSecretDraft({});
    setProviderNotice(null);
    setProviderError(null);
  };

  const waitForProviderJob = async (jobId: string) => {
    for (let attempt = 0; attempt < 45; attempt += 1) {
      const job = await platformApi.saasJob(jobId);
      if (["SUCCEEDED", "FAILED", "DEAD_LETTER", "CANCELLED"].includes(job.status)) return job;
      setProviderNotice(`Verifying connection… ${job.status.toLowerCase().replaceAll("_", " ")}`);
      await new Promise((resolve) => window.setTimeout(resolve, 1000));
    }
    return null;
  };

  const saveProvider = async (verify = false) => {
    if (!provider) return;
    setProviderError(null);
    setProviderNotice(null);
    const config = Object.fromEntries(
      Object.entries(configDraft)
        .filter(([, value]) => value.trim() !== "")
        .map(([key, value]) => [key, coerceField(value)]),
    );
    const secret = Object.fromEntries(
      Object.entries(secretDraft).filter(([, value]) => value.trim() !== ""),
    );
    const missing = (provider.setup?.fields ?? []).filter((field) => {
      if (!field.required) return false;
      if (field.source === "secret") {
        const scopedSecretStored = provider.has_secret && (!tenantScope || provider.tenant_id === tenantScope);
        return !scopedSecretStored && !String(secretDraft[field.name] ?? "").trim();
      }
      return !String(configDraft[field.name] ?? "").trim();
    });
    if (missing.length) {
      setProviderError(`Complete the required field${missing.length === 1 ? "" : "s"}: ${missing.map((field) => field.label).join(", ")}.`);
      return;
    }
    setProviderBusy(true);
    try {
      await platformApi.updateSaasProvider(
        provider.provider,
        {
          config,
          ...(Object.keys(secret).length ? { secret } : {}),
          enabled: true,
          reason: "Platform provider configuration updated from the superuser console",
        },
        tenantScope.trim() || null,
      );
      if (verify) {
        const queued = await platformApi.testSaasProvider(provider.provider, tenantScope.trim() || null);
        setProviderNotice("Configuration saved. Verifying the live connection…");
        const completed = await waitForProviderJob(queued.id);
        if (!completed) setProviderNotice(`Health check ${queued.id} is still running. Track it in the integration queue.`);
        else if (completed.status === "SUCCEEDED") setProviderNotice("Configuration saved and the provider connection is healthy.");
        else throw new Error(completed.last_error || `Provider verification ${completed.status.toLowerCase()}.`);
      } else {
        setProviderNotice("Configuration saved. Encrypted credentials remain server-side.");
      }
      setSecretDraft({});
      providers.reload();
      summary.reload();
    } catch (error) {
      setProviderError(error instanceof Error ? error.message : String(error));
    } finally {
      setProviderBusy(false);
    }
  };

  const testProvider = async () => {
    if (!provider) return;
    setProviderError(null);
    setProviderBusy(true);
    try {
      const job = await platformApi.testSaasProvider(provider.provider, tenantScope.trim() || null);
      setProviderNotice("Verifying the live provider connection…");
      const completed = await waitForProviderJob(job.id);
      if (!completed) setProviderNotice(`Health check ${job.id} is still running. Track it in the integration queue.`);
      else if (completed.status === "SUCCEEDED") setProviderNotice("Provider connection is healthy.");
      else throw new Error(completed.last_error || `Provider verification ${completed.status.toLowerCase()}.`);
      summary.reload();
    } catch (error) {
      setProviderError(error instanceof Error ? error.message : String(error));
    } finally {
      setProviderBusy(false);
    }
  };

  const runAction = async (action: () => Promise<unknown>, success: string) => {
    setActionError(null);
    setActionNotice(null);
    try {
      await action();
      setActionNotice(success);
    } catch (error) {
      setActionError(error instanceof Error ? error.message : String(error));
    }
  };

  const createTicket = async () => {
    if (!ticketTitle.trim() || !ticketDescription.trim()) return;
    await runAction(async () => {
      const created = await platformApi.createSupportTicket({
        tenant_id: ticketTenant.trim() || null,
        title: ticketTitle.trim(),
        description: ticketDescription.trim(),
        priority: ticketPriority,
        category: "GENERAL",
      });
      setTicketTitle("");
      setTicketDescription("");
      tickets.reload();
      summary.reload();
      selectTicket(created.id);
    }, "Support ticket opened.");
  };

  const updateTicket = async () => {
    if (!selectedTicketId) return;
    await runAction(
      () => platformApi.updateSupportTicket(selectedTicketId, {
        status: ticketStatusDraft,
        priority: ticketPriorityDraft,
        resolution: ticketResolution,
        reason: "Support ticket updated from the superadmin console",
      }).then(() => {
        ticketDetail.reload();
        tickets.reload();
        summary.reload();
      }),
      "Ticket state updated.",
    );
  };

  const sendTicketMessage = async () => {
    if (!selectedTicketId || !ticketMessage.trim()) return;
    await runAction(
      () => platformApi.addSupportMessage(selectedTicketId, ticketMessage.trim(), messageVisibility).then(() => {
        setTicketMessage("");
        ticketDetail.reload();
        tickets.reload();
      }),
      messageVisibility === "INTERNAL" ? "Internal support note added." : "Reply sent.",
    );
  };

  const setupFields: SaaSProviderSetupField[] = provider?.setup?.fields ?? [
    ...(provider?.secret_fields ?? []).map((name) => ({ name, label: name.replaceAll("_", " "), source: "secret" as const, control: "password" as const, required: false, advanced: false, options: [] })),
    ...(provider?.config_fields ?? []).map((name) => ({ name, label: name.replaceAll("_", " "), source: "config" as const, control: "text" as const, required: false, advanced: false, options: [] })),
  ];
  const providerUsesInheritedSecret = Boolean(tenantScope && provider?.has_secret && provider.tenant_id !== tenantScope);

  const renderProviderField = (field: SaaSProviderSetupField) => {
    const source = field.source === "secret" ? secretDraft : configDraft;
    const change = (value: string) => field.source === "secret"
      ? setSecretDraft((current) => ({ ...current, [field.name]: value }))
      : setConfigDraft((current) => ({ ...current, [field.name]: value }));
    const value = source[field.name] ?? "";
    const placeholder = field.source === "secret" && provider?.has_secret && !providerUsesInheritedSecret
      ? "Stored securely — leave blank to keep it"
      : field.required ? "Required" : "Optional";
    return (
      <label key={`${field.source}:${field.name}`} className="platform-provider-field">
        <span>{field.label}{field.required ? <em>Required</em> : null}</span>
        {field.control === "select" ? (
          <select value={value} onChange={(event) => change(event.target.value)}>
            {!field.required ? <option value="">Not set</option> : null}
            {field.options.map((option) => <option key={option.value} value={option.value}>{option.label}</option>)}
          </select>
        ) : field.control === "toggle" ? (
          <select value={value || "false"} onChange={(event) => change(event.target.value)}>
            <option value="false">No</option><option value="true">Yes</option>
          </select>
        ) : (
          <input
            type={field.control === "password" ? "password" : field.control === "number" ? "number" : field.control === "url" ? "url" : "text"}
            autoComplete={field.control === "password" ? "new-password" : undefined}
            value={value}
            onChange={(event) => change(event.target.value)}
            placeholder={placeholder}
          />
        )}
      </label>
    );
  };

  return (
    <PlatformShell
      title="Integrations, API & Support"
      subtitle="Providers, email, jobs, webhooks and support"
      actions={<button className="platform-btn" onClick={() => { providers.reload(); summary.reload(); if (tab === "jobs") jobs.reload(); if (tab === "support") tickets.reload(); }}>Refresh workspace</button>}
    >
      {summary.error ? <ErrorState error={summary.error} retry={summary.reload} /> : null}
      {actionError ? <div className="platform-error">{actionError}</div> : null}
      {actionNotice ? <p><StatusBadge value="SUCCEEDED" /> {actionNotice}</p> : null}

      <section className="platform-summary-strip" aria-label="Integration health summary">
        <div><span>Queue</span><strong>{String(queue.queue_depth ?? 0)}</strong><small>durable jobs</small></div>
        <div><span>Support</span><strong>{String(counts.open_support_tickets ?? 0)}</strong><small>open tickets</small></div>
        <div><span>Providers</span><strong>{configuredProviders}/{providerList.length}</strong><small>configured</small></div>
        <div><span>Email</span><strong>{emailProvider?.status ?? "Not configured"}</strong><small>{emailProvider?.last_latency_ms != null ? `${emailProvider.last_latency_ms} ms` : "Resend"}</small></div>
      </section>

      <nav className="platform-tabs" aria-label="Integration workspace sections">
        {TABS.map((item) => <button key={item.id} className={tab === item.id ? "active" : undefined} onClick={() => setTab(item.id)}><span>{item.mark}</span>{item.label}</button>)}
      </nav>

      {tab === "email" ? (
        <section>
          <ResendEmailConfigPanel />
        </section>
      ) : null}

      {tab === "providers" ? (
        <section className="platform-provider-workspace">
          <aside className="platform-card platform-provider-catalog">
            <div className="platform-section-title"><div><h2>Providers</h2><p>Select a service to configure.</p></div><StatusBadge value={tenantScope ? "TENANT_OVERRIDE" : "PLATFORM"} /></div>
            <label className="platform-scope-select"><span>Configuration scope</span>
              <select value={tenantScope} onChange={(event) => changeTenantScope(event.target.value)}>
                <option value="">Platform default</option>
                {(tenants.data?.items ?? []).map((tenant) => <option key={tenant.id} value={tenant.id}>{tenant.name} · {tenant.amo_code}</option>)}
              </select>
              <small>Tenant overrides inherit the platform provider until explicitly saved.</small>
            </label>
            {providers.error ? <ErrorState error={providers.error} retry={providers.reload} /> : null}
            <div className="platform-list">
              {nonEmailProviders.length ? nonEmailProviders.map((item) => (
                <button
                  className={`platform-list-row${provider?.provider === item.provider ? " active" : ""}`}
                  key={`${item.provider}:${item.tenant_id ?? "platform"}`}
                  onClick={() => beginProviderEdit(item)}
                >
                  <span className="platform-list-row__icon">{item.provider.slice(0, 2).toUpperCase()}</span>
                  <span className="platform-list-row__copy"><strong>{item.display_name}</strong><small>{item.category} · {item.last_latency_ms != null ? `${item.last_latency_ms} ms` : "not checked"}</small></span>
                  <StatusBadge value={item.status} />
                </button>
              )) : <EmptyState label="No provider definitions were returned." />}
            </div>
          </aside>

          <div className="platform-card platform-provider-editor">
            <div className="platform-section-title">
              <div><h2>{provider?.display_name ?? "Provider setup"}</h2><p>{provider?.setup?.summary || provider?.description || "Select a provider to configure it."}</p></div>
              {provider ? <StatusBadge value={provider.status} /> : null}
            </div>
            {provider ? (
              <>
                <div className="platform-provider-security">
                  <span className={`platform-status-dot ${provider.has_secret && !providerUsesInheritedSecret ? "live" : "offline"}`} />
                  <span><strong>{providerUsesInheritedSecret ? "Tenant credential required" : provider.has_secret ? "Encrypted credential stored" : "Credential required"}</strong><small>{providerUsesInheritedSecret ? "This tenant currently inherits the platform provider. Saving an override requires its own credential." : provider.has_secret ? `Fingerprint ${provider.secret_fingerprint ?? "available"}` : "Secrets are encrypted before database storage and never returned."}</small></span>
                </div>
                {provider.provider === "openai" ? <div className="platform-inline-note">The API key is the only credential you need. Model dropdowns and defaults below are governed by the backend allowlist.</div> : null}
                <div className="platform-provider-fields">
                  {setupFields.filter((field) => !field.advanced).map(renderProviderField)}
                </div>
                {setupFields.some((field) => field.advanced) ? (
                  <details className="platform-provider-advanced">
                    <summary>Advanced connection settings</summary>
                    <p>Change these only for a proxy, project, or organization-specific deployment.</p>
                    <div className="platform-provider-fields">{setupFields.filter((field) => field.advanced).map(renderProviderField)}</div>
                  </details>
                ) : null}
                {providerError ? <div className="platform-error">{providerError}</div> : null}
                {providerNotice ? <div className="platform-inline-note"><StatusBadge value={providerBusy ? "PENDING" : "SUCCEEDED"} /> {providerNotice}</div> : null}
                <div className="platform-actions platform-provider-actions">
                  <button className="platform-btn primary" onClick={() => saveProvider(true)} disabled={providerBusy}>{providerBusy ? "Working…" : "Save & verify"}</button>
                  <button className="platform-btn" onClick={() => saveProvider(false)} disabled={providerBusy}>Save only</button>
                  {provider.has_secret ? <button className="platform-btn" onClick={testProvider} disabled={providerBusy}>Verify existing</button> : null}
                </div>
              </>
            ) : <EmptyState label="Select a provider from the registry." />}
          </div>
        </section>
      ) : null}

      {tab === "jobs" ? (
        <section className="platform-card">
          <div className="platform-section-title"><div><h2>Integration queue</h2><p>Live state for provider checks, payments, AI, email and fiscalization jobs.</p></div><button className="platform-btn" onClick={jobs.reload}>Refresh queue</button></div>
          {jobs.error ? <ErrorState error={jobs.error} retry={jobs.reload} /> : jobs.data?.items?.length ? (
            <DataTable><thead><tr><th>Created</th><th>Queue</th><th>Job</th><th>Tenant</th><th>Status</th><th>Attempts</th><th>Last error</th><th>Control</th></tr></thead><tbody>{jobs.data.items.map((job) => (
              <tr key={job.id}><td>{job.created_at ? new Date(job.created_at).toLocaleString() : "-"}</td><td>{job.queue_name}</td><td><strong>{job.job_type}</strong><br /><small>{job.id}</small></td><td>{job.tenant_id ?? "Platform"}</td><td><StatusBadge value={job.status} /></td><td>{job.attempt_count}/{job.max_attempts}</td><td>{job.last_error ?? "-"}</td><td><div className="platform-actions">{["FAILED", "DEAD_LETTER"].includes(job.status) ? <button className="platform-btn" onClick={() => runAction(() => platformApi.retrySaasJob(job.id).then(jobs.reload), "Job queued for retry.")}>Retry</button> : null}{["PENDING", "QUEUED", "RETRY"].includes(job.status) ? <button className="platform-btn danger" onClick={() => runAction(() => platformApi.cancelSaasJob(job.id, "Cancelled from the superadmin console").then(jobs.reload), "Job cancelled.")}>Cancel</button> : null}</div></td></tr>
            ))}</tbody></DataTable>
          ) : <EmptyState label="No SaaS jobs are recorded." />}
        </section>
      ) : null}

      {tab === "webhooks" ? (
        <section className="platform-two">
          <div className="platform-card">
            <div className="platform-section-title"><div><h2>Platform API keys</h2><p>Issue narrowly-scoped credentials and revoke them immediately when no longer required.</p></div></div>
            {rawKey ? <div className="platform-error"><div><strong>Copy this key now. It will not be shown again.</strong><p><code>{rawKey}</code></p></div><button className="platform-btn" onClick={() => navigator.clipboard.writeText(rawKey)}>Copy</button></div> : null}
            <div className="platform-toolbar"><input value={keyName} onChange={(event) => setKeyName(event.target.value)} /><button className="platform-btn primary" onClick={() => runAction(() => platformApi.createApiKey({ name: keyName, scopes: ["platform.read"] }).then((result) => { setRawKey(String(result.raw_key ?? "")); keys.reload(); }), "API key issued.")}>Issue key</button></div>
            {keys.data?.items?.length ? <DataTable><thead><tr><th>Name</th><th>Prefix</th><th>Status</th><th>Last used</th><th /></tr></thead><tbody>{keys.data.items.map((item) => { const key = item as Record<string, unknown>; return <tr key={String(key.id)}><td><strong>{String(key.name)}</strong></td><td>{String(key.key_prefix)}</td><td><StatusBadge value={key.status} /></td><td>{key.last_used_at ? new Date(String(key.last_used_at)).toLocaleString() : "Never"}</td><td><button className="platform-btn danger" onClick={() => runAction(() => platformApi.revokeApiKey(String(key.id), "Platform key revoked").then(keys.reload), "API key revoked.")}>Revoke</button></td></tr>; })}</tbody></DataTable> : <EmptyState label="No API keys." />}
          </div>

          <div className="platform-card">
            <div className="platform-section-title"><div><h2>Outbound webhooks</h2><p>Register platform events and review current delivery state.</p></div></div>
            <div className="platform-toolbar"><input placeholder="https://example.com/webhook" value={webhookUrl} onChange={(event) => setWebhookUrl(event.target.value)} /><button className="platform-btn primary" disabled={!webhookUrl.trim()} onClick={() => runAction(() => platformApi.createWebhook({ name: "Global webhook", event_type: "platform.event", target_url: webhookUrl }).then(() => { setWebhookUrl(""); hooks.reload(); }), "Webhook configured.")}>Configure</button></div>
            <div className="platform-list">{hooks.data?.items?.length ? hooks.data.items.map((item) => { const hook = item as Record<string, unknown>; return <div className="platform-list-row" key={String(hook.id)}><span className="platform-list-row__icon">WH</span><span className="platform-list-row__copy"><strong>{String(hook.name)}</strong><small>{String(hook.target_url)} · {String(hook.event_type)}</small></span><StatusBadge value={hook.status} /></div>; }) : <EmptyState label="No webhooks configured." />}</div>
          </div>
        </section>
      ) : null}

      {tab === "support" ? (
        <section className="platform-three">
          <div className="platform-card">
            <div className="platform-section-title"><div><h2>Support queue</h2><p>Tenant and platform tickets ordered by latest activity.</p></div><button className="platform-btn" onClick={tickets.reload}>Refresh</button></div>
            {tickets.error ? <ErrorState error={tickets.error} retry={tickets.reload} /> : null}
            <div className="platform-list" style={{ maxHeight: "58vh", overflow: "auto" }}>
              {tickets.data?.items?.length ? tickets.data.items.map((ticket) => <button className="platform-list-row" key={ticket.id} onClick={() => selectTicket(ticket.id)}><span className="platform-list-row__icon">{ticket.priority.slice(0, 2)}</span><span className="platform-list-row__copy"><strong>{ticket.title}</strong><small>{ticket.external_id} · {ticket.tenant_id ?? "Platform"}</small></span><StatusBadge value={ticket.status} /></button>) : <EmptyState label="No support tickets." />}
            </div>
          </div>

          <div className="platform-card">
            <div className="platform-section-title"><div><h2>Ticket workspace</h2><p>Reply, add internal notes, assign priority and close the issue.</p></div>{selectedTicket ? <StatusBadge value={selectedTicket.status} /> : null}</div>
            {ticketDetail.error ? <ErrorState error={ticketDetail.error} retry={ticketDetail.reload} /> : null}
            {selectedTicket ? <>
              <p><strong>{selectedTicket.title}</strong><br /><small>{selectedTicket.external_id} · Tenant {selectedTicket.tenant_id ?? "Platform"}{selectedTicket.sla_due_at ? ` · SLA ${new Date(selectedTicket.sla_due_at).toLocaleString()}` : ""}</small></p>
              <div className="platform-form" style={{ gridTemplateColumns: "1fr 1fr" }}><label><span>Status</span><select value={ticketStatusDraft} onChange={(event) => setTicketStatusDraft(event.target.value)}><option>OPEN</option><option>PENDING</option><option>IN_PROGRESS</option><option>RESOLVED</option><option>CLOSED</option></select></label><label><span>Priority</span><select value={ticketPriorityDraft} onChange={(event) => setTicketPriorityDraft(event.target.value)}><option>LOW</option><option>NORMAL</option><option>HIGH</option><option>URGENT</option><option>CRITICAL</option></select></label></div>
              <label style={{ display: "grid", gap: 4, marginTop: 8 }}><span>Resolution / handover note</span><textarea value={ticketResolution} onChange={(event) => setTicketResolution(event.target.value)} /></label>
              <button className="platform-btn" style={{ marginTop: 8 }} onClick={updateTicket}>Save ticket state</button>
              <div style={{ maxHeight: "29vh", overflow: "auto", marginTop: 10 }}>{(selectedTicket.messages ?? []).map((message) => <article className="platform-message" key={message.id}><header><span>{message.author_type} · {message.visibility}</span><span>{new Date(message.created_at).toLocaleString()}</span></header><p>{message.body}</p></article>)}</div>
              <textarea placeholder="Reply or add an internal support note" value={ticketMessage} onChange={(event) => setTicketMessage(event.target.value)} />
              <div className="platform-actions" style={{ marginTop: 7 }}><select value={messageVisibility} onChange={(event) => setMessageVisibility(event.target.value)}><option value="PUBLIC">Public reply</option><option value="INTERNAL">Internal note</option></select><button className="platform-btn primary" onClick={sendTicketMessage}>Send</button><button className="platform-btn" onClick={() => selectedTicketId && runAction(() => platformApi.requestAiSupportReply(selectedTicketId).then(() => { setTab("jobs"); }), "AI support draft queued.")}>Queue AI draft</button></div>
            </> : <EmptyState label="Select a ticket to open the support workspace." />}
          </div>

          <div className="platform-card">
            <div className="platform-section-title"><div><h2>Open a ticket</h2><p>Create a platform issue or act on behalf of a tenant.</p></div></div>
            <div className="platform-form"><label><span>Tenant (optional)</span><select value={ticketTenant} onChange={(event) => setTicketTenant(event.target.value)}><option value="">Platform issue</option>{(tenants.data?.items ?? []).map((tenant) => <option key={tenant.id} value={tenant.id}>{tenant.name} · {tenant.amo_code}</option>)}</select></label><label><span>Priority</span><select value={ticketPriority} onChange={(event) => setTicketPriority(event.target.value)}><option>LOW</option><option>NORMAL</option><option>HIGH</option><option>URGENT</option><option>CRITICAL</option></select></label><label><span>Title</span><input value={ticketTitle} onChange={(event) => setTicketTitle(event.target.value)} /></label><label><span>Description</span><textarea value={ticketDescription} onChange={(event) => setTicketDescription(event.target.value)} /></label><button className="platform-btn primary" disabled={!ticketTitle.trim() || !ticketDescription.trim()} onClick={createTicket}>Open support ticket</button></div>
          </div>
        </section>
      ) : null}
    </PlatformShell>
  );
}
