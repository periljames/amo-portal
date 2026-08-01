import React, { useState } from "react";

import type { PlatformDataMode } from "../../services/commercialControl";
import { platformApi, type PlatformCommandJob } from "../../services/platformControl";
import { phase4Api } from "../../services/platformPhase4";
import { DataTable, EmptyState, ErrorState, MetricCard, PlatformShell, StatusBadge } from "./components/PlatformShared";
import { usePlatformData } from "./components/usePlatformData";
import "../../styles/platform-commercial-control.css";

type InfrastructureSummary = {
  status?: string;
  workers?: number;
  latest_snapshot?: {
    captured_at?: string;
    cpu_percent?: number;
    memory_percent?: number;
    db_connections_active?: number;
    db_connections_max?: number;
    api_requests_per_minute?: number;
    api_error_rate?: number;
    api_p95_latency_ms?: number;
  } | null;
};

type FeatureFlag = {
  id: string;
  key: string;
  name: string;
  description?: string | null;
  scope?: string;
  tenant_id?: string | null;
  plan_code?: string | null;
  enabled: boolean;
  updated_at?: string;
};

type MaintenanceWindow = {
  id: string;
  status?: string;
  title?: string;
  description?: string | null;
  starts_at?: string | null;
  ends_at?: string | null;
  impact_level?: string;
};

export default function PlatformInfrastructurePage() {
  const [dataMode, setDataMode] = useState<PlatformDataMode>("REAL");
  const [reason, setReason] = useState("Infrastructure change approved by platform owner");
  const [notice, setNotice] = useState<string | null>(null);
  const [actionError, setActionError] = useState<string | null>(null);
  const [flagForm, setFlagForm] = useState({ key: "", name: "", description: "", scope: "GLOBAL", tenant_id: "", plan_code: "", enabled: false });
  const [windowForm, setWindowForm] = useState({ title: "", description: "", starts_at: "", ends_at: "", impact_level: "LOW" });

  const infra = usePlatformData(() => platformApi.infrastructureSummary(), [], { pollMs: 15_000 });
  const flags = usePlatformData(() => platformApi.featureFlags(), [], { pollMs: 20_000 });
  const windows = usePlatformData(() => platformApi.maintenanceWindows(), [], { pollMs: 20_000 });
  const commands = usePlatformData(() => platformApi.commands({ limit: 25 }), [], { pollMs: 15_000 });
  const capabilities = usePlatformData(() => phase4Api.infrastructureCapabilities(), [], { pollMs: 60_000 });
  const tenants = usePlatformData(() => phase4Api.tenantOptions(dataMode), [dataMode], { pollMs: 30_000 });

  const summary = (infra.data ?? {}) as InfrastructureSummary;
  const snapshot = summary.latest_snapshot ?? {};
  const featureFlags = (flags.data?.items ?? []) as FeatureFlag[];
  const maintenanceWindows = (windows.data?.items ?? []) as MaintenanceWindow[];
  const databaseFailover = capabilities.data?.database_failover as { available?: boolean; reason?: string } | undefined;

  const refresh = () => { infra.reload(); flags.reload(); windows.reload(); commands.reload(); capabilities.reload(); tenants.reload(); };
  const run = async (operation: () => Promise<unknown>, success: string) => {
    setActionError(null); setNotice(null);
    try {
      await operation();
      setNotice(success);
      refresh();
    } catch (error) {
      setActionError(error instanceof Error ? error.message : String(error));
    }
  };

  const createFlag = () => run(
    () => platformApi.createFeatureFlag({
      key: flagForm.key.trim(),
      name: flagForm.name.trim() || flagForm.key.trim(),
      description: flagForm.description.trim() || null,
      enabled: flagForm.enabled,
      scope: flagForm.scope,
      tenant_id: flagForm.scope === "TENANT" ? flagForm.tenant_id || null : null,
      plan_code: flagForm.scope === "PLAN" ? flagForm.plan_code.trim().toUpperCase() || null : null,
      reason,
    }),
    "Feature flag created with explicit scope.",
  );

  const createWindow = () => run(
    () => platformApi.createMaintenance({
      title: windowForm.title,
      description: windowForm.description || null,
      starts_at: windowForm.starts_at ? new Date(windowForm.starts_at).toISOString() : null,
      ends_at: windowForm.ends_at ? new Date(windowForm.ends_at).toISOString() : null,
      impact_level: windowForm.impact_level,
      status: "SCHEDULED",
      reason,
    }),
    "Maintenance window scheduled.",
  );

  return (
    <PlatformShell
      title="System Infrastructure"
      subtitle="Worker health, diagnostics, scoped feature flags, controlled maintenance and only those critical commands with safe runtime implementations."
      actions={<><button className="platform-btn" onClick={refresh}>Refresh</button><button className="platform-btn primary" onClick={() => run(() => platformApi.runDiagnostics("Infrastructure probe"), "Infrastructure diagnostics queued.")}>Run diagnostics</button></>}
    >
      {infra.error ? <ErrorState error={infra.error} retry={infra.reload} /> : null}
      {actionError ? <div className="platform-error">{actionError}</div> : null}
      {notice ? <div className="platform-inline-success">{notice}</div> : null}
      <section className="platform-grid">
        <MetricCard label="Status" value={<StatusBadge value={summary.status} />} mark="ST" />
        <MetricCard label="CPU" value={snapshot.cpu_percent == null ? "N/A" : `${snapshot.cpu_percent}%`} tone="blue" mark="CP" />
        <MetricCard label="RAM" value={snapshot.memory_percent == null ? "N/A" : `${snapshot.memory_percent}%`} tone="purple" mark="RM" />
        <MetricCard label="DB connections" value={snapshot.db_connections_active == null ? "N/A" : `${snapshot.db_connections_active}/${snapshot.db_connections_max ?? "?"}`} tone="green" mark="DB" />
        <MetricCard label="API RPM" value={snapshot.api_requests_per_minute ?? "N/A"} tone="blue" mark="RP" />
        <MetricCard label="Workers" value={summary.workers ?? 0} tone="green" mark="WK" />
      </section>

      <section className="platform-commercial-section-grid">
        <div className="platform-card">
          <div className="platform-section-title"><div><h2>Scoped feature flags</h2><p>Target a global rollout, a product plan or one tenant.</p></div></div>
          <div className="platform-form-grid">
            <label><span>Key</span><input value={flagForm.key} onChange={(event) => setFlagForm({ ...flagForm, key: event.target.value.toLowerCase().replaceAll("-", "_") })} /></label>
            <label><span>Name</span><input value={flagForm.name} onChange={(event) => setFlagForm({ ...flagForm, name: event.target.value })} /></label>
            <label><span>Scope</span><select value={flagForm.scope} onChange={(event) => setFlagForm({ ...flagForm, scope: event.target.value })}><option>GLOBAL</option><option>PLAN</option><option>TENANT</option></select></label>
            {flagForm.scope === "PLAN" ? <label><span>Plan code</span><input value={flagForm.plan_code} onChange={(event) => setFlagForm({ ...flagForm, plan_code: event.target.value.toUpperCase() })} /></label> : null}
            {flagForm.scope === "TENANT" ? <><label><span>Environment</span><div className="platform-mode-switch">{(["REAL", "DEMO"] as PlatformDataMode[]).map((mode) => <button type="button" key={mode} className={dataMode === mode ? "active" : ""} onClick={() => { setDataMode(mode); setFlagForm({ ...flagForm, tenant_id: "" }); }}>{mode}</button>)}</div></label><label><span>Tenant</span><select value={flagForm.tenant_id} onChange={(event) => setFlagForm({ ...flagForm, tenant_id: event.target.value })}><option value="">Select tenant</option>{(tenants.data?.items || []).map((tenant) => <option key={tenant.id} value={tenant.id}>{tenant.name} · {tenant.amo_code}</option>)}</select></label></> : null}
            <label className="span-2"><span>Description</span><textarea value={flagForm.description} onChange={(event) => setFlagForm({ ...flagForm, description: event.target.value })} /></label>
            <label><span><input type="checkbox" checked={flagForm.enabled} onChange={(event) => setFlagForm({ ...flagForm, enabled: event.target.checked })} /> Enable immediately</span></label>
          </div>
          <button className="platform-btn primary" onClick={createFlag}>Create flag</button>
          <div style={{ marginTop: 14 }}>{featureFlags.length ? <DataTable><thead><tr><th>Flag</th><th>Scope</th><th>Target</th><th>Status</th><th>Updated</th><th>Action</th></tr></thead><tbody>{featureFlags.map((flag) => <tr key={flag.id}><td><strong>{flag.name}</strong><br /><small>{flag.key}</small></td><td>{flag.scope ?? "GLOBAL"}</td><td>{flag.tenant_id || flag.plan_code || "Platform"}</td><td><StatusBadge value={flag.enabled ? "ENABLED" : "DISABLED"} /></td><td>{flag.updated_at ? new Date(flag.updated_at).toLocaleString() : "—"}</td><td><button className="platform-btn" onClick={() => run(() => platformApi.toggleFeatureFlag(flag.id, !flag.enabled), `Feature flag ${flag.enabled ? "disabled" : "enabled"}.`)}>Toggle</button></td></tr>)}</tbody></DataTable> : <EmptyState label="No feature flags yet." />}</div>
        </div>

        <div className="platform-card">
          <div className="platform-section-title"><div><h2>Maintenance control</h2><p>Schedule and explicitly transition service-impacting windows.</p></div></div>
          <div className="platform-form-grid"><label><span>Title</span><input value={windowForm.title} onChange={(event) => setWindowForm({ ...windowForm, title: event.target.value })} /></label><label><span>Impact</span><select value={windowForm.impact_level} onChange={(event) => setWindowForm({ ...windowForm, impact_level: event.target.value })}><option>LOW</option><option>MEDIUM</option><option>HIGH</option><option>CRITICAL</option></select></label><label><span>Starts</span><input type="datetime-local" value={windowForm.starts_at} onChange={(event) => setWindowForm({ ...windowForm, starts_at: event.target.value })} /></label><label><span>Ends</span><input type="datetime-local" value={windowForm.ends_at} onChange={(event) => setWindowForm({ ...windowForm, ends_at: event.target.value })} /></label><label className="span-2"><span>Description</span><textarea value={windowForm.description} onChange={(event) => setWindowForm({ ...windowForm, description: event.target.value })} /></label></div>
          <button className="platform-btn primary" onClick={createWindow}>Schedule window</button>
          <div className="platform-stack" style={{ marginTop: 14 }}>{maintenanceWindows.length ? maintenanceWindows.map((window) => <div className="platform-subtle-panel" key={window.id}><div className="platform-section-title"><div><strong>{window.title ?? "Maintenance"}</strong><p>{window.starts_at ? new Date(window.starts_at).toLocaleString() : "No start"} — {window.ends_at ? new Date(window.ends_at).toLocaleString() : "No end"}</p></div><StatusBadge value={window.status} /></div><div className="platform-actions">{window.status === "SCHEDULED" ? <button className="platform-btn" onClick={() => run(() => phase4Api.transitionMaintenance(window.id, "ACTIVE", reason), "Maintenance started.")}>Start</button> : null}{window.status === "ACTIVE" ? <button className="platform-btn" onClick={() => run(() => phase4Api.transitionMaintenance(window.id, "COMPLETED", reason), "Maintenance completed.")}>Complete</button> : null}{!['COMPLETED','CANCELLED'].includes(String(window.status)) ? <button className="platform-btn danger" onClick={() => run(() => phase4Api.transitionMaintenance(window.id, "CANCELLED", reason), "Maintenance cancelled.")}>Cancel</button> : null}</div></div>) : <EmptyState label="No maintenance windows." />}</div>
        </div>
      </section>

      <section className="platform-commercial-section-grid">
        <div className="platform-card"><h2>Critical controls</h2><label className="platform-stack-form"><span>Required reason</span><textarea value={reason} onChange={(event) => setReason(event.target.value)} /></label><div className="platform-actions"><button className="platform-btn danger" onClick={() => run(() => platformApi.resetApiTokens(reason), "Global API token reset queued.")}>Reset global API tokens</button><button className="platform-btn danger" disabled={!databaseFailover?.available} title={databaseFailover?.reason} onClick={() => databaseFailover?.available && run(() => platformApi.failoverDatabase(reason), "Database failover queued.")}>Database failover unavailable</button></div>{databaseFailover?.reason ? <div className="platform-inline-warning" style={{ marginTop: 12 }}>{databaseFailover.reason}</div> : null}</div>
        <div className="platform-card"><h2>Recent command jobs</h2>{(commands.data?.items ?? []).length ? (commands.data?.items ?? []).slice(0, 10).map((job: PlatformCommandJob) => <div className="platform-list-row" key={job.id}><span className="platform-list-row__icon">JB</span><span className="platform-list-row__copy"><strong>{job.command_name}</strong><small>{job.error_detail || job.reason || "No detail"}</small></span><StatusBadge value={job.status} /></div>) : <EmptyState label="No recent infrastructure jobs." />}</div>
      </section>
    </PlatformShell>
  );
}
