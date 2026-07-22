import React, { useEffect, useMemo, useState } from "react";

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
import { usePlatformData } from "./components/usePlatformData";

function coerceField(value: string): string | number | boolean {
  const clean = value.trim();
  if (clean === "true") return true;
  if (clean === "false") return false;
  if (/^-?\d+$/.test(clean)) return Number(clean);
  return value;
}

export default function PlatformIntegrationsPage() {
  const [keyName, setKeyName] = useState("Platform API key");
  const [webhookUrl, setWebhookUrl] = useState("");
  const [rawKey, setRawKey] = useState<string | null>(null);
  const [tenantScope, setTenantScope] = useState("");
  const [selectedProvider, setSelectedProvider] = useState<string>("stripe");
  const [configDraft, setConfigDraft] = useState<Record<string, string>>({});
  const [secretDraft, setSecretDraft] = useState<Record<string, string>>({});
  const [providerNotice, setProviderNotice] = useState<string | null>(null);
  const [providerError, setProviderError] = useState<string | null>(null);
  const [ticketTitle, setTicketTitle] = useState("");
  const [ticketDescription, setTicketDescription] = useState("");
  const [ticketTenant, setTicketTenant] = useState("");
  const [selectedTicketId, setSelectedTicketId] = useState<string | null>(null);
  const [ticketMessage, setTicketMessage] = useState("");

  const summary = usePlatformData(() => platformApi.saasCapabilities(), []);
  const providers = usePlatformData(
    () => platformApi.saasProviders(tenantScope.trim() || null),
    [tenantScope],
  );
  const jobs = usePlatformData(
    () => platformApi.saasJobs({ limit: 30 }),
    [],
  );
  const keys = usePlatformData(() => platformApi.apiKeys(), []);
  const hooks = usePlatformData(() => platformApi.webhooks(), []);
  const tickets = usePlatformData(
    () => platformApi.saasSupportTickets({ limit: 30 }),
    [],
  );
  const ticketDetail = usePlatformData(
    () => selectedTicketId ? platformApi.saasSupportTicket(selectedTicketId) : Promise.resolve(null),
    [selectedTicketId],
  );

  const provider = useMemo(
    () => providers.data?.items?.find((item) => item.provider === selectedProvider) ?? null,
    [providers.data?.items, selectedProvider],
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
    setProviderNotice(null);
    setProviderError(null);
  }, [provider?.provider, provider?.tenant_id, provider?.updated_at]);

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
      jobs.reload();
    } catch (error) {
      setProviderError(error instanceof Error ? error.message : String(error));
    }
  };

  const createTicket = async () => {
    if (!ticketTitle.trim() || !ticketDescription.trim()) return;
    await platformApi.createSupportTicket({
      tenant_id: ticketTenant.trim() || null,
      title: ticketTitle.trim(),
      description: ticketDescription.trim(),
      priority: "NORMAL",
      category: "GENERAL",
    });
    setTicketTitle("");
    setTicketDescription("");
    tickets.reload();
    summary.reload();
  };

  const selectedTicket = ticketDetail.data as SupportTicket | null;
  const queue = (summary.data?.queue ?? {}) as Record<string, unknown>;
  const counts = (summary.data?.counts ?? {}) as Record<string, unknown>;

  return (
    <PlatformShell
      title="Integrations, API & Support"
      subtitle="Encrypted provider credentials, durable background jobs, API keys, webhooks, AI support, email, payments, tax adapters and the platform help desk."
      actions={<button className="platform-btn" onClick={() => { providers.reload(); jobs.reload(); summary.reload(); }}>Refresh</button>}
    >
      {summary.error ? <ErrorState error={summary.error} retry={summary.reload} /> : null}
      <section className="platform-grid">
        <MetricCard label="Queue depth" value={String(queue.queue_depth ?? 0)} caption="Durable PostgreSQL jobs" />
        <MetricCard label="Open support tickets" value={String(counts.open_support_tickets ?? 0)} />
        <MetricCard label="Pending fiscalizations" value={String(counts.pending_fiscalizations ?? 0)} />
        <MetricCard label="Configured providers" value={providers.data?.items?.filter((item) => item.status !== "NOT_CONFIGURED").length ?? 0} />
      </section>

      <section className="platform-two">
        <div className="platform-card">
          <h2>Provider registry</h2>
          <p>Use a tenant ID only for an override. Leave it blank to configure the platform default.</p>
          <div className="platform-form" style={{ gridTemplateColumns: "1fr auto", marginBottom: 12 }}>
            <input
              placeholder="Tenant ID for optional override"
              value={tenantScope}
              onChange={(event) => setTenantScope(event.target.value)}
            />
            <button className="platform-btn" onClick={providers.reload}>Load scope</button>
          </div>
          {providers.error ? <ErrorState error={providers.error} retry={providers.reload} /> : null}
          {providers.data?.items?.length ? (
            <DataTable>
              <thead><tr><th>Provider</th><th>Category</th><th>Status</th><th>Health</th><th /></tr></thead>
              <tbody>
                {providers.data.items.map((item) => (
                  <tr key={`${item.provider}:${item.tenant_id ?? "platform"}`}>
                    <td><strong>{item.display_name}</strong><br /><small>{item.provider}</small></td>
                    <td>{item.category}</td>
                    <td><StatusBadge value={item.status} /></td>
                    <td>{item.last_latency_ms != null ? `${item.last_latency_ms} ms` : "-"}</td>
                    <td><button className="platform-btn" onClick={() => setSelectedProvider(item.provider)}>Configure</button></td>
                  </tr>
                ))}
              </tbody>
            </DataTable>
          ) : <EmptyState label="No provider definitions were returned." />}
        </div>

        <div className="platform-card">
          <h2>{provider?.display_name ?? "Provider configuration"}</h2>
          {provider ? (
            <>
              <p>{provider.description}</p>
              <p><StatusBadge value={provider.status} /> {provider.has_secret ? `Secret stored · ${provider.secret_fingerprint ?? "fingerprinted"}` : "No secret stored"}</p>
              <div className="platform-form">
                {provider.config_fields.map((field) => (
                  <label key={field}>
                    <span>{field.replaceAll("_", " ")}</span>
                    <input
                      value={configDraft[field] ?? ""}
                      onChange={(event) => setConfigDraft((current) => ({ ...current, [field]: event.target.value }))}
                      placeholder={field}
                    />
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
                      placeholder={provider.has_secret ? "Leave blank to preserve stored value" : field}
                    />
                  </label>
                ))}
              </div>
              {providerError ? <div className="platform-error">{providerError}</div> : null}
              {providerNotice ? <p><StatusBadge value="PENDING" /> {providerNotice}</p> : null}
              <div className="platform-actions">
                <button className="platform-btn primary" onClick={saveProvider}>Save configuration</button>
                <button className="platform-btn" onClick={testProvider}>Queue health check</button>
              </div>
              <small>Secrets are encrypted on the backend and are never loaded back into this form.</small>
            </>
          ) : <EmptyState label="Select a provider to configure." />}
        </div>
      </section>

      <section className="platform-card">
        <h2>Integration queue</h2>
        {jobs.data?.items?.length ? (
          <DataTable>
            <thead><tr><th>Created</th><th>Queue</th><th>Job</th><th>Tenant</th><th>Status</th><th>Attempts</th><th>Error</th></tr></thead>
            <tbody>
              {jobs.data.items.map((job) => (
                <tr key={job.id}>
                  <td>{job.created_at ? new Date(job.created_at).toLocaleString() : "-"}</td>
                  <td>{job.queue_name}</td>
                  <td>{job.job_type}<br /><small>{job.id}</small></td>
                  <td>{job.tenant_id ?? "Platform"}</td>
                  <td><StatusBadge value={job.status} /></td>
                  <td>{job.attempt_count}/{job.max_attempts}</td>
                  <td>{job.last_error ?? "-"}</td>
                </tr>
              ))}
            </tbody>
          </DataTable>
        ) : <EmptyState label="No SaaS jobs are recorded." />}
      </section>

      {rawKey ? (
        <div className="platform-error">
          <strong>Copy this API key now. It will not be shown again.</strong><br />
          <code>{rawKey}</code>
        </div>
      ) : null}

      <section className="platform-two">
        <div className="platform-card">
          <h2>Platform API keys</h2>
          <div className="platform-form" style={{ gridTemplateColumns: "1fr auto", marginBottom: 12 }}>
            <input value={keyName} onChange={(event) => setKeyName(event.target.value)} />
            <button
              className="platform-btn primary"
              onClick={() => platformApi.createApiKey({ name: keyName, scopes: ["platform.read"] }).then((result) => {
                setRawKey(String(result.raw_key ?? ""));
                keys.reload();
              })}
            >Issue key</button>
          </div>
          {keys.data?.items?.length ? (
            <DataTable>
              <thead><tr><th>Name</th><th>Prefix</th><th>Status</th><th /></tr></thead>
              <tbody>{keys.data.items.map((item) => {
                const key = item as Record<string, unknown>;
                return <tr key={String(key.id)}><td>{String(key.name)}</td><td>{String(key.key_prefix)}</td><td><StatusBadge value={key.status} /></td><td><button className="platform-btn danger" onClick={() => platformApi.revokeApiKey(String(key.id), "Platform key revoked").then(keys.reload)}>Revoke</button></td></tr>;
              })}</tbody>
            </DataTable>
          ) : <EmptyState label="No API keys." />}
        </div>

        <div className="platform-card">
          <h2>Outbound webhooks</h2>
          <div className="platform-form" style={{ marginBottom: 12 }}>
            <input placeholder="https://example.com/webhook" value={webhookUrl} onChange={(event) => setWebhookUrl(event.target.value)} />
            <button className="platform-btn primary" onClick={() => platformApi.createWebhook({ name: "Global webhook", event_type: "platform.event", target_url: webhookUrl }).then(hooks.reload)}>Configure webhook</button>
          </div>
          {hooks.data?.items?.length ? hooks.data.items.map((item) => {
            const hook = item as Record<string, unknown>;
            return <p key={String(hook.id)}><StatusBadge value={hook.status} /> {String(hook.name)}<br /><small>{String(hook.target_url)}</small></p>;
          }) : <EmptyState label="No webhooks configured." />}
        </div>
      </section>

      <section className="platform-two">
        <div className="platform-card">
          <h2>Support desk</h2>
          <div className="platform-form">
            <input placeholder="Tenant ID (optional for platform issue)" value={ticketTenant} onChange={(event) => setTicketTenant(event.target.value)} />
            <input placeholder="Ticket title" value={ticketTitle} onChange={(event) => setTicketTitle(event.target.value)} />
            <textarea placeholder="Describe the problem" value={ticketDescription} onChange={(event) => setTicketDescription(event.target.value)} />
            <button className="platform-btn primary" onClick={createTicket}>Open ticket</button>
          </div>
          {tickets.data?.items?.length ? (
            <DataTable>
              <thead><tr><th>Ticket</th><th>Tenant</th><th>Priority</th><th>Status</th></tr></thead>
              <tbody>{tickets.data.items.map((ticket) => (
                <tr key={ticket.id} onClick={() => setSelectedTicketId(ticket.id)} style={{ cursor: "pointer" }}>
                  <td><strong>{ticket.title}</strong><br /><small>{ticket.external_id}</small></td>
                  <td>{ticket.tenant_id ?? "Platform"}</td>
                  <td>{ticket.priority}</td>
                  <td><StatusBadge value={ticket.status} /></td>
                </tr>
              ))}</tbody>
            </DataTable>
          ) : <EmptyState label="No support tickets." />}
        </div>

        <div className="platform-card">
          <h2>Ticket conversation</h2>
          {selectedTicket ? (
            <>
              <p><strong>{selectedTicket.title}</strong><br /><StatusBadge value={selectedTicket.status} /> {selectedTicket.external_id}</p>
              {(selectedTicket.messages ?? []).map((message) => (
                <div key={message.id} className="platform-card" style={{ marginBottom: 8 }}>
                  <small>{message.author_type} · {new Date(message.created_at).toLocaleString()}</small>
                  <p>{message.body}</p>
                </div>
              ))}
              <textarea placeholder="Reply to the ticket" value={ticketMessage} onChange={(event) => setTicketMessage(event.target.value)} />
              <div className="platform-actions">
                <button className="platform-btn primary" onClick={() => selectedTicketId && platformApi.addSupportMessage(selectedTicketId, ticketMessage).then(() => { setTicketMessage(""); ticketDetail.reload(); tickets.reload(); })}>Send reply</button>
                <button className="platform-btn" onClick={() => selectedTicketId && platformApi.requestAiSupportReply(selectedTicketId).then(() => { jobs.reload(); })}>Queue AI draft</button>
              </div>
            </>
          ) : <EmptyState label="Select a ticket to view the conversation." />}
        </div>
      </section>
    </PlatformShell>
  );
}
