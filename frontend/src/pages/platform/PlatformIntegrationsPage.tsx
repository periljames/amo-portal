import React, { useEffect, useMemo, useState } from "react";
import { useSearchParams } from "react-router-dom";

import type { PlatformDataMode } from "../../services/commercialControl";
import { platformApi, type SaaSProvider, type SupportTicket } from "../../services/platformControl";
import { phase4Api, type WebhookDelivery } from "../../services/platformPhase4";
import { DataTable, EmptyState, ErrorState, MetricCard, PlatformShell, StatusBadge } from "./components/PlatformShared";
import ResendEmailConfigPanel from "./components/ResendEmailConfigPanel";
import { usePlatformData } from "./components/usePlatformData";
import "../../styles/platform-commercial-control.css";

type IntegrationTab = "email" | "providers" | "jobs" | "webhooks" | "support";
const TABS: Array<{ id: IntegrationTab; label: string }> = [
  { id: "email", label: "Email delivery" },
  { id: "providers", label: "Provider registry" },
  { id: "jobs", label: "Integration queue" },
  { id: "webhooks", label: "API keys & webhooks" },
  { id: "support", label: "Support center" },
];

function normalizeTab(value: string | null): IntegrationTab {
  return TABS.some((tab) => tab.id === value) ? value as IntegrationTab : "email";
}

function coerce(value: string): string | number | boolean {
  const clean = value.trim();
  if (clean === "true") return true;
  if (clean === "false") return false;
  if (/^-?\d+(\.\d+)?$/.test(clean)) return Number(clean);
  return value;
}

export default function PlatformIntegrationsPage() {
  const [searchParams, setSearchParams] = useSearchParams();
  const tab = normalizeTab(searchParams.get("tab"));
  const dataMode = (searchParams.get("mode") === "DEMO" ? "DEMO" : "REAL") as PlatformDataMode;
  const tenantId = searchParams.get("tenant") || "";
  const [notice, setNotice] = useState<string | null>(null);
  const [actionError, setActionError] = useState<string | null>(null);
  const [reason, setReason] = useState("Platform integration administration");
  const [selectedProviderCode, setSelectedProviderCode] = useState("");
  const [configDraft, setConfigDraft] = useState<Record<string, string>>({});
  const [secretDraft, setSecretDraft] = useState<Record<string, string>>({});
  const [keyForm, setKeyForm] = useState({ name: "Platform API key", scopes: "platform.read", expires_at: "" });
  const [rawKey, setRawKey] = useState<string | null>(null);
  const [webhookForm, setWebhookForm] = useState({ name: "Platform events", event_type: "platform.event", target_url: "", secret: "", is_global: true });
  const [selectedWebhookId, setSelectedWebhookId] = useState<string | null>(null);
  const [deliveries, setDeliveries] = useState<WebhookDelivery[]>([]);
  const [ticketForm, setTicketForm] = useState({ title: "", description: "", priority: "NORMAL", category: "GENERAL" });
  const [selectedTicketId, setSelectedTicketId] = useState<string | null>(searchParams.get("ticket"));
  const [ticketMessage, setTicketMessage] = useState("");
  const [ticketStatus, setTicketStatus] = useState("OPEN");
  const [ticketResolution, setTicketResolution] = useState("");

  const capabilities = usePlatformData(() => platformApi.saasCapabilities(), [], { pollMs: 20_000 });
  const tenants = usePlatformData(() => phase4Api.tenantOptions(dataMode), [dataMode], { pollMs: 30_000 });
  const providers = usePlatformData(() => platformApi.saasProviders(tenantId || null), [tenantId], { pollMs: 20_000 });
  const jobs = usePlatformData(() => tab === "jobs" ? platformApi.saasJobs({ tenant_id: tenantId || undefined, limit: 100 }) : Promise.resolve({ items: [] }), [tab, tenantId], { pollMs: 10_000 });
  const keys = usePlatformData(() => tab === "webhooks" ? platformApi.apiKeys() : Promise.resolve({ items: [] }), [tab], { pollMs: 20_000 });
  const hooks = usePlatformData(() => tab === "webhooks" ? platformApi.webhooks() : Promise.resolve({ items: [] }), [tab], { pollMs: 15_000 });
  const tickets = usePlatformData(() => tab === "support" ? platformApi.saasSupportTickets({ tenant_id: tenantId || undefined, limit: 100 }) : Promise.resolve({ items: [] }), [tab, tenantId], { pollMs: 10_000 });
  const ticketDetail = usePlatformData(() => tab === "support" && selectedTicketId ? platformApi.saasSupportTicket(selectedTicketId) : Promise.resolve(null), [tab, selectedTicketId], { pollMs: 10_000 });

  const providerList = providers.data?.items || [];
  const provider = useMemo(() => providerList.find((item) => item.provider === selectedProviderCode) || null, [providerList, selectedProviderCode]);
  const selectedTicket = ticketDetail.data as SupportTicket | null;
  const capabilityCounts = (capabilities.data?.counts || {}) as Record<string, unknown>;
  const queue = (capabilities.data?.queue || {}) as Record<string, unknown>;

  useEffect(() => {
    if (!selectedProviderCode && providerList.length) setSelectedProviderCode(providerList[0].provider);
  }, [providerList, selectedProviderCode]);

  useEffect(() => {
    if (!provider) return;
    const config: Record<string, string> = {};
    provider.config_fields.forEach((field) => { config[field] = provider.config?.[field] == null ? "" : String(provider.config[field]); });
    setConfigDraft(config);
    setSecretDraft({});
  }, [provider]);

  useEffect(() => {
    if (!selectedTicket) return;
    setTicketStatus(selectedTicket.status || "OPEN");
    setTicketResolution(selectedTicket.resolution || "");
  }, [selectedTicket]);

  const setQuery = (patch: Record<string, string | null>) => {
    const next = new URLSearchParams(searchParams);
    Object.entries(patch).forEach(([key, value]) => value ? next.set(key, value) : next.delete(key));
    setSearchParams(next, { replace: true });
  };

  const refresh = () => { capabilities.reload(); tenants.reload(); providers.reload(); keys.reload(); hooks.reload(); jobs.reload(); tickets.reload(); ticketDetail.reload(); };
  const run = async (operation: () => Promise<unknown>, success: string) => {
    setNotice(null); setActionError(null);
    try { await operation(); setNotice(success); refresh(); }
    catch (error) { setActionError(error instanceof Error ? error.message : String(error)); }
  };

  const saveProvider = () => {
    if (!provider) return;
    const config = Object.fromEntries(Object.entries(configDraft).filter(([, value]) => value.trim() !== "").map(([key, value]) => [key, coerce(value)]));
    const secret = Object.fromEntries(Object.entries(secretDraft).filter(([, value]) => value.trim() !== ""));
    return run(() => platformApi.updateSaasProvider(provider.provider, { config, ...(Object.keys(secret).length ? { secret } : {}), enabled: true, reason }, tenantId || null), "Provider configuration saved; secrets remain server-side.");
  };

  const createKey = async () => {
    const result = await platformApi.createApiKey({ name: keyForm.name, scopes: keyForm.scopes.split(",").map((scope) => scope.trim()).filter(Boolean), expires_at: keyForm.expires_at ? new Date(keyForm.expires_at).toISOString() : null, reason });
    setRawKey(String(result.raw_key || ""));
    keys.reload();
  };

  const createWebhook = () => run(() => platformApi.createWebhook({ ...webhookForm, tenant_id: webhookForm.is_global ? null : tenantId || null, reason }), "Webhook created.");
  const inspectWebhook = async (id: string) => {
    setSelectedWebhookId(id);
    try { const result = await phase4Api.webhookDeliveries(id); setDeliveries(result.items); }
    catch (error) { setActionError(error instanceof Error ? error.message : String(error)); }
  };

  const createTicket = async () => {
    if (!ticketForm.title.trim() || !ticketForm.description.trim()) return;
    let createdId = "";
    await run(async () => {
      const created = await platformApi.createSupportTicket({ tenant_id: tenantId || null, ...ticketForm });
      createdId = created.id;
      setTicketForm({ title: "", description: "", priority: "NORMAL", category: "GENERAL" });
    }, "Support ticket opened.");
    if (createdId) { setSelectedTicketId(createdId); setQuery({ tab: "support", ticket: createdId }); }
  };

  const saveTicket = () => selectedTicketId && run(() => platformApi.updateSupportTicket(selectedTicketId, { status: ticketStatus, resolution: ticketResolution, reason }), "Ticket updated.");
  const addMessage = () => selectedTicketId && ticketMessage.trim() && run(async () => { await platformApi.addSupportMessage(selectedTicketId, ticketMessage.trim(), "PUBLIC"); setTicketMessage(""); }, "Reply added.");

  return (
    <PlatformShell title="Integrations, API & Support" subtitle="Tenant-scoped providers, encrypted secrets, durable jobs, API scopes, webhook deliveries and support cases." actions={<><div className="platform-mode-switch">{(["REAL", "DEMO"] as PlatformDataMode[]).map((mode) => <button key={mode} className={dataMode === mode ? "active" : ""} onClick={() => setQuery({ mode, tenant: null })}>{mode}</button>)}</div><button className="platform-btn" onClick={refresh}>Refresh</button></>}>
      {capabilities.error ? <ErrorState error={capabilities.error} retry={capabilities.reload} /> : null}
      {actionError ? <div className="platform-error">{actionError}</div> : null}
      {notice ? <div className="platform-inline-success">{notice}</div> : null}
      <section className="platform-grid"><MetricCard label="Queue depth" value={String(queue.queue_depth ?? 0)} tone="blue" mark="JQ" /><MetricCard label="Providers" value={providerList.length} tone="green" mark="PR" /><MetricCard label="Open tickets" value={String(capabilityCounts.open_support_tickets ?? 0)} tone="purple" mark="SP" /><MetricCard label="Fiscalization queue" value={String(capabilityCounts.pending_fiscalizations ?? 0)} tone="amber" mark="TX" /></section>
      <section className="platform-card"><div className="platform-tabs">{TABS.map((item) => <button key={item.id} className={tab === item.id ? "active" : ""} onClick={() => setQuery({ tab: item.id, ticket: item.id === "support" ? selectedTicketId : null })}>{item.label}</button>)}</div><div className="platform-toolbar"><select value={tenantId} onChange={(event) => { setSelectedProviderCode(""); setQuery({ tenant: event.target.value || null }); }}><option value="">Platform scope / all {dataMode.toLowerCase()} tenants</option>{(tenants.data?.items || []).map((tenant) => <option key={tenant.id} value={tenant.id}>{tenant.name} · {tenant.amo_code}</option>)}</select><input value={reason} onChange={(event) => setReason(event.target.value)} placeholder="Reason for privileged changes" /></div></section>

      {tab === "email" ? <ResendEmailConfigPanel /> : null}

      {tab === "providers" ? <section className="platform-commercial-layout"><div className="platform-card"><h2>Provider registry</h2><div className="platform-commercial-list">{providerList.map((item: SaaSProvider) => <button key={`${item.provider}:${item.tenant_id || "platform"}`} className={`platform-commercial-list__item ${selectedProviderCode === item.provider ? "active" : ""}`} onClick={() => setSelectedProviderCode(item.provider)}><span><strong>{item.display_name}</strong><small>{item.category} · {item.scope}</small></span><StatusBadge value={item.status} /></button>)}</div></div><aside className="platform-card platform-commercial-sidebar"><h2>Provider configuration</h2>{provider ? <div className="platform-stack-form"><div className="platform-subtle-panel"><strong>{provider.display_name}</strong><p>{provider.description || provider.category}</p><StatusBadge value={provider.status} /></div>{provider.config_fields.map((field) => <label key={field}><span>{field.replaceAll("_", " ")}</span><input value={configDraft[field] || ""} onChange={(event) => setConfigDraft({ ...configDraft, [field]: event.target.value })} /></label>)}{provider.secret_fields.map((field) => <label key={field}><span>{field.replaceAll("_", " ")} {provider.has_secret ? "· configured" : ""}</span><input type="password" value={secretDraft[field] || ""} onChange={(event) => setSecretDraft({ ...secretDraft, [field]: event.target.value })} placeholder="Leave blank to preserve current secret" /></label>)}<div className="platform-actions"><button className="platform-btn primary" onClick={saveProvider}>Save provider</button><button className="platform-btn" onClick={() => run(() => platformApi.testSaasProvider(provider.provider, tenantId || null), "Provider health check queued.")}>Test health</button></div></div> : <EmptyState label="Select a provider." />}</aside></section> : null}

      {tab === "jobs" ? <section className="platform-card"><div className="platform-section-title"><div><h2>Durable integration queue</h2><p>Inspect retries, errors, correlation IDs and tenant scope.</p></div></div>{jobs.data?.items.length ? <DataTable><thead><tr><th>Job</th><th>Queue</th><th>Tenant</th><th>Attempts</th><th>Status</th><th>Error</th><th>Actions</th></tr></thead><tbody>{jobs.data.items.map((job) => <tr key={job.id}><td><strong>{job.job_type}</strong><br /><small>{job.id}</small></td><td>{job.queue_name}</td><td>{job.tenant_id || "Platform"}</td><td>{job.attempt_count}/{job.max_attempts}</td><td><StatusBadge value={job.status} /></td><td>{job.last_error || "—"}</td><td><div className="platform-actions"><button className="platform-btn" onClick={() => run(() => platformApi.retrySaasJob(job.id), "Job queued for retry.")}>Retry</button><button className="platform-btn danger" onClick={() => run(() => platformApi.cancelSaasJob(job.id, reason), "Job cancelled.")}>Cancel</button></div></td></tr>)}</tbody></DataTable> : <EmptyState label="No jobs in the current queue scope." />}</section> : null}

      {tab === "webhooks" ? <section className="platform-commercial-section-grid"><div className="platform-card"><h2>API keys</h2><div className="platform-stack-form"><label><span>Name</span><input value={keyForm.name} onChange={(event) => setKeyForm({ ...keyForm, name: event.target.value })} /></label><label><span>Scopes, comma separated</span><input value={keyForm.scopes} onChange={(event) => setKeyForm({ ...keyForm, scopes: event.target.value })} placeholder="platform.read, platform.write" /></label><label><span>Expires</span><input type="datetime-local" value={keyForm.expires_at} onChange={(event) => setKeyForm({ ...keyForm, expires_at: event.target.value })} /></label><button className="platform-btn primary" onClick={createKey}>Create API key</button>{rawKey ? <div className="platform-inline-warning"><strong>Copy once:</strong><br /><code>{rawKey}</code></div> : null}</div>{keys.data?.items.length ? <DataTable><thead><tr><th>Key</th><th>Scopes</th><th>Status</th><th>Last used</th><th>Action</th></tr></thead><tbody>{keys.data.items.map((key) => <tr key={String(key.id)}><td>{String(key.name)}<br /><small>{String(key.key_prefix)}</small></td><td>{JSON.stringify(key.scopes_json || [])}</td><td><StatusBadge value={String(key.status)} /></td><td>{key.last_used_at ? new Date(String(key.last_used_at)).toLocaleString() : "Never"}</td><td><button className="platform-btn danger" onClick={() => run(() => platformApi.revokeApiKey(String(key.id), reason), "API key revoked.")}>Revoke</button></td></tr>)}</tbody></DataTable> : null}</div><div className="platform-card"><h2>Webhook endpoints</h2><div className="platform-stack-form"><label><span>Name</span><input value={webhookForm.name} onChange={(event) => setWebhookForm({ ...webhookForm, name: event.target.value })} /></label><label><span>Event type</span><select value={webhookForm.event_type} onChange={(event) => setWebhookForm({ ...webhookForm, event_type: event.target.value })}><option>platform.event</option><option>tenant.subscription.updated</option><option>invoice.created</option><option>invoice.paid</option><option>support.ticket.updated</option><option>security.alert.created</option></select></label><label><span>Target URL</span><input value={webhookForm.target_url} onChange={(event) => setWebhookForm({ ...webhookForm, target_url: event.target.value })} /></label><label><span>Signing secret</span><input type="password" value={webhookForm.secret} onChange={(event) => setWebhookForm({ ...webhookForm, secret: event.target.value })} /></label><label><span><input type="checkbox" checked={webhookForm.is_global} onChange={(event) => setWebhookForm({ ...webhookForm, is_global: event.target.checked })} /> Global webhook</span></label><button className="platform-btn primary" disabled={!webhookForm.is_global && !tenantId} onClick={createWebhook}>Create webhook</button></div>{hooks.data?.items.length ? <div className="platform-stack" style={{ marginTop: 14 }}>{hooks.data.items.map((hook) => <div className="platform-subtle-panel" key={String(hook.id)}><div className="platform-section-title"><div><strong>{String(hook.name)}</strong><p>{String(hook.event_type)} · {String(hook.target_url)}</p></div><StatusBadge value={String(hook.status)} /></div><div className="platform-actions"><button className="platform-btn" onClick={() => inspectWebhook(String(hook.id))}>Deliveries</button><button className="platform-btn" onClick={() => run(() => phase4Api.updateWebhook(String(hook.id), String(hook.status) === "PAUSED" ? "ACTIVE" : "PAUSED", reason), "Webhook state updated.")}>{String(hook.status) === "PAUSED" ? "Resume" : "Pause"}</button></div>{selectedWebhookId === String(hook.id) ? <DataTable><thead><tr><th>Created</th><th>Event</th><th>HTTP</th><th>Duration</th><th>Attempts</th><th>Result</th></tr></thead><tbody>{deliveries.map((delivery) => <tr key={delivery.id}><td>{new Date(delivery.created_at).toLocaleString()}</td><td>{delivery.event_type}</td><td>{delivery.status_code ?? "—"}</td><td>{delivery.duration_ms ?? "—"} ms</td><td>{delivery.attempt_count}</td><td><StatusBadge value={delivery.success ? "SUCCEEDED" : "FAILED"} /> {delivery.error_detail}</td></tr>)}</tbody></DataTable> : null}</div>)}</div> : null}</div></section> : null}

      {tab === "support" ? <section className="platform-commercial-layout"><div className="platform-card"><h2>Support queue</h2><div className="platform-stack-form"><label><span>Title</span><input value={ticketForm.title} onChange={(event) => setTicketForm({ ...ticketForm, title: event.target.value })} /></label><label><span>Description</span><textarea value={ticketForm.description} onChange={(event) => setTicketForm({ ...ticketForm, description: event.target.value })} /></label><label><span>Priority</span><select value={ticketForm.priority} onChange={(event) => setTicketForm({ ...ticketForm, priority: event.target.value })}><option>LOW</option><option>NORMAL</option><option>HIGH</option><option>URGENT</option><option>CRITICAL</option></select></label><button className="platform-btn primary" onClick={createTicket}>Open ticket</button></div><div className="platform-commercial-list" style={{ marginTop: 14 }}>{(tickets.data?.items || []).map((ticket) => <button key={ticket.id} className={`platform-commercial-list__item ${selectedTicketId === ticket.id ? "active" : ""}`} onClick={() => { setSelectedTicketId(ticket.id); setQuery({ tab: "support", ticket: ticket.id }); }}><span><strong>{ticket.title}</strong><small>{ticket.tenant_id || "Platform"} · {ticket.priority}</small></span><StatusBadge value={ticket.status} /></button>)}</div></div><aside className="platform-card platform-commercial-sidebar"><h2>Ticket detail</h2>{selectedTicket ? <div className="platform-stack-form"><div className="platform-subtle-panel"><strong>{selectedTicket.title}</strong><p>{selectedTicket.description}</p><StatusBadge value={selectedTicket.status} /></div><label><span>Status</span><select value={ticketStatus} onChange={(event) => setTicketStatus(event.target.value)}><option>OPEN</option><option>PENDING</option><option>IN_PROGRESS</option><option>RESOLVED</option><option>CLOSED</option></select></label><label><span>Resolution</span><textarea value={ticketResolution} onChange={(event) => setTicketResolution(event.target.value)} /></label><button className="platform-btn" onClick={saveTicket}>Save ticket</button><h3>Conversation</h3>{selectedTicket.messages?.map((message) => <div className="platform-subtle-panel" key={message.id}><strong>{message.author_type}</strong><p>{message.body}</p><small>{new Date(message.created_at).toLocaleString()} · {message.visibility}</small></div>)}<label><span>Reply</span><textarea value={ticketMessage} onChange={(event) => setTicketMessage(event.target.value)} /></label><div className="platform-actions"><button className="platform-btn primary" onClick={addMessage}>Send reply</button><button className="platform-btn" onClick={() => run(() => platformApi.requestAiSupportReply(selectedTicket.id), "AI support draft queued.")}>Draft with AI</button></div></div> : <EmptyState label="Select a support ticket." />}</aside></section> : null}
    </PlatformShell>
  );
}
