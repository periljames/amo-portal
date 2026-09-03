import React, { useEffect, useMemo, useState } from "react";
import { useSearchParams } from "react-router-dom";

import {
  platformApi,
  type SaaSProvider,
  type SupportTicket,
} from "../../services/platformControl";
import {
  DataTable,
  EmptyState,
  ErrorState,
  MetricCard,
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
  const providerList = providers.data?.items ?? [];
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
  // eslint-disable-next-line react-hooks/exhaustive-deps
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
    item.config_fields.forEach((field) => {
      const value = item.config?.[field];
      next[field] = value === undefined || value === null ? "" : String(value);
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

  const saveProvider = async () => {
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
      setProviderNotice("Provider configuration saved. Secret values remain server-side and will not be returned.");
      setSecretDraft({});
      providers.reload();
      summary.reload();
    } catch (error) {
      setProviderError(error instanceof Error ? error.message : String(error));
    }
  };

  const testProvider = async () => {
    if (!provider) return;
    setProviderError(null);
    try {
      const job = await platformApi.testSaasProvider(provider.provider, tenantScope.trim() || null);
      setProviderNotice(`Health check queued as ${job.id}.`);
      summary.reload();
    } catch (error) {
      setProviderError(error instanceof Error ? error.message : String(error));
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

  const providerRail = (
    <div className="platform-stack">
      <section className="platform-card">
        <div className="platform-section-title"><div><h2>Provider integrations</h2><p>Platform-wide external services and their latest health state.</p></div></div>
        <div className="platform-list">
          {providerList.length ? providerList.slice(0, 8).map((item) => (
            <button className="platform-list-row" key={`${item.provider}:${item.tenant_id ?? "platform"}`} onClick={() => { if (item.category === "EMAIL") setTab("email"); else { beginProviderEdit(item); setTab("providers"); } }}>
              <span className="platform-list-row__icon">{item.provider.slice(0, 2).toUpperCase()}</span>
              <span className="platform-list-row__copy"><strong>{item.display_name}</strong><small>{item.description || item.category}</small></span>
              <StatusBadge value={item.status} />
            </button>
          )) : <EmptyState label="No provider definitions returned." />}
        </div>
      </section>
      <section className="platform-card">
        <div className="platform-section-title"><div><h2>Quick actions</h2><p>Common support and integration tasks.</p></div></div>
        <div className="platform-quick-grid">
          <button className="platform-quick-action" onClick={() => setTab("support")}><span>SP</span><span><strong>Create support ticket</strong><small>Open on behalf of a tenant</small></span></button>
          <button className="platform-quick-action" onClick={() => setTab("providers")}><span>PR</span><span><strong>Configure provider</strong><small>Payments, tax or AI</small></span></button>
          <button className="platform-quick-action" onClick={() => setTab("email")}><span>EM</span><span><strong>Test email delivery</strong><small>Verify current Resend setup</small></span></button>
          <button className="platform-quick-action" onClick={() => setTab("jobs")}><span>JQ</span><span><strong>View integration queue</strong><small>Inspect retries and failures</small></span></button>
        </div>
      </section>
    </div>
  );

  return (
    <PlatformShell
      title="Integrations, API & Support"
      subtitle="Providers, email, jobs, webhooks and support"
      actions={<button className="platform-btn" onClick={() => { providers.reload(); summary.reload(); if (tab === "jobs") jobs.reload(); if (tab === "support") tickets.reload(); }}>Refresh workspace</button>}
    >
      {summary.error ? <ErrorState error={summary.error} retry={summary.reload} /> : null}
      {actionError ? <div className="platform-error">{actionError}</div> : null}
      {actionNotice ? <p><StatusBadge value="SUCCEEDED" /> {actionNotice}</p> : null}

      <section className="platform-grid">
        <MetricCard label="Queue depth" value={String(queue.queue_depth ?? 0)} caption="Durable PostgreSQL jobs" tone="blue" mark="JQ" />
        <MetricCard label="Open support tickets" value={String(counts.open_support_tickets ?? 0)} caption="Across all tenants" tone="purple" mark="SP" />
        <MetricCard label="Pending fiscalizations" value={String(counts.pending_fiscalizations ?? 0)} caption="Awaiting tax adapter action" tone="amber" mark="TX" />
        <MetricCard label="Configured providers" value={configuredProviders} caption={`${providerList.length} registered integrations`} tone="green" mark="PR" />
        <MetricCard label="Email health" value={emailProvider?.status ?? "Not configured"} caption={emailProvider?.last_latency_ms != null ? `${emailProvider.last_latency_ms} ms last latency` : "Resend delivery service"} tone={emailProvider?.status === "HEALTHY" ? "green" : "amber"} mark="EM" />
      </section>

      <nav className="platform-tabs" aria-label="Integration workspace sections">
        {TABS.map((item) => <button key={item.id} className={tab === item.id ? "active" : undefined} onClick={() => setTab(item.id)}><span>{item.mark}</span>{item.label}</button>)}
      </nav>

      {tab === "email" ? (
        <section className="platform-two">
          <ResendEmailConfigPanel />
          {providerRail}
        </section>
      ) : null}

      {tab === "providers" ? (
        <section className="platform-two">
          <div className="platform-card">
            <div className="platform-section-title"><div><h2>Provider registry</h2><p>Use a tenant ID only when configuring a deliberate tenant-specific override.</p></div><StatusBadge value={tenantScope ? "TENANT_OVERRIDE" : "PLATFORM"} /></div>
            <div className="platform-toolbar">
              <input placeholder="Tenant ID for optional override" value={tenantScope} onChange={(event) => changeTenantScope(event.target.value)} />
              <button className="platform-btn" onClick={providers.reload}>Load scope</button>
            </div>
            {providers.error ? <ErrorState error={providers.error} retry={providers.reload} /> : null}
            <div className="platform-list">
              {nonEmailProviders.length ? nonEmailProviders.map((item) => (
                <button className="platform-list-row" key={`${item.provider}:${item.tenant_id ?? "platform"}`} onClick={() => beginProviderEdit(item)}>
                  <span className="platform-list-row__icon">{item.provider.slice(0, 2).toUpperCase()}</span>
                  <span className="platform-list-row__copy"><strong>{item.display_name}</strong><small>{item.description || item.category} · {item.last_latency_ms != null ? `${item.last_latency_ms} ms` : "not checked"}</small></span>
                  <StatusBadge value={item.status} />
                </button>
              )) : <EmptyState label="No non-email provider definitions were returned." />}
            </div>
          </div>

          <div className="platform-card platform-sticky-card">
            <div className="platform-section-title"><div><h2>{provider?.display_name ?? "Provider configuration"}</h2><p>{provider?.description || "Select a provider to manage its server-side configuration."}</p></div>{provider ? <StatusBadge value={provider.status} /> : null}</div>
            {provider ? (
              <>
                <p><small>{provider.has_secret ? `Encrypted secret stored · ${provider.secret_fingerprint ?? "fingerprinted"}` : "No provider secret is stored"}</small></p>
                <div className="platform-form">
                  {provider.config_fields.map((field) => <label key={field}><span>{field.replaceAll("_", " ")}</span><input value={configDraft[field] ?? ""} onChange={(event) => setConfigDraft((current) => ({ ...current, [field]: event.target.value }))} placeholder={field} /></label>)}
                  {provider.secret_fields.map((field) => <label key={field}><span>{field.replaceAll("_", " ")}</span><input type="password" autoComplete="new-password" value={secretDraft[field] ?? ""} onChange={(event) => setSecretDraft((current) => ({ ...current, [field]: event.target.value }))} placeholder={provider.has_secret ? "Leave blank to preserve stored value" : field} /></label>)}
                </div>
                {providerError ? <div className="platform-error">{providerError}</div> : null}
                {providerNotice ? <p><StatusBadge value="PENDING" /> {providerNotice}</p> : null}
                <div className="platform-actions" style={{ marginTop: 11 }}><button className="platform-btn primary" onClick={saveProvider}>Save configuration</button><button className="platform-btn" onClick={testProvider}>Queue health check</button></div>
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
            <div className="platform-form"><label><span>Tenant ID (optional)</span><input value={ticketTenant} onChange={(event) => setTicketTenant(event.target.value)} /></label><label><span>Priority</span><select value={ticketPriority} onChange={(event) => setTicketPriority(event.target.value)}><option>LOW</option><option>NORMAL</option><option>HIGH</option><option>URGENT</option><option>CRITICAL</option></select></label><label><span>Title</span><input value={ticketTitle} onChange={(event) => setTicketTitle(event.target.value)} /></label><label><span>Description</span><textarea value={ticketDescription} onChange={(event) => setTicketDescription(event.target.value)} /></label><button className="platform-btn primary" disabled={!ticketTitle.trim() || !ticketDescription.trim()} onClick={createTicket}>Open support ticket</button></div>
          </div>
        </section>
      ) : null}
    </PlatformShell>
  );
}
