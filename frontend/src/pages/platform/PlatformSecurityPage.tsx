import React, { useState } from "react";
import { useSearchParams } from "react-router-dom";

import type { PlatformDataMode } from "../../services/commercialControl";
import { platformApi } from "../../services/platformControl";
import { phase4Api, type DetailedAuditRecord, type DetailedSecurityAlert } from "../../services/platformPhase4";
import { DataTable, EmptyState, ErrorState, MetricCard, PlatformShell, StatusBadge } from "./components/PlatformShared";
import { usePlatformData } from "./components/usePlatformData";
import "../../styles/platform-commercial-control.css";

type SecuritySummary = {
  open_alerts?: number;
  critical_alerts?: number;
  disabled_users?: number;
  locked_users?: number;
  mfa_coverage_percent?: number | string;
};

export default function PlatformSecurityPage() {
  const [searchParams, setSearchParams] = useSearchParams();
  const tab = searchParams.get("tab") === "audit" ? "audit" : "alerts";
  const dataMode = (searchParams.get("mode") === "DEMO" ? "DEMO" : "REAL") as PlatformDataMode;
  const q = searchParams.get("q") || "";
  const tenantId = searchParams.get("tenant") || "";
  const severity = searchParams.get("severity") || "";
  const status = searchParams.get("status") || "";
  const [selectedAlert, setSelectedAlert] = useState<DetailedSecurityAlert | null>(null);
  const [selectedAudit, setSelectedAudit] = useState<DetailedAuditRecord | null>(null);
  const [reason, setReason] = useState("Security alert reviewed and resolved");
  const [notice, setNotice] = useState<string | null>(null);
  const [actionError, setActionError] = useState<string | null>(null);

  const summaryQuery = usePlatformData(() => platformApi.securitySummary(), [], { pollMs: 15_000 });
  const tenants = usePlatformData(() => phase4Api.tenantOptions(dataMode), [dataMode], { pollMs: 30_000 });
  const alertsQuery = usePlatformData(
    () => tab === "alerts" ? phase4Api.securityAlerts({ q, tenant_id: tenantId || undefined, severity: severity || undefined, status: status || undefined, limit: 150 }) : Promise.resolve({ items: [] }),
    [tab, q, tenantId, severity, status, dataMode],
    { pollMs: 10_000 },
  );
  const auditQuery = usePlatformData(
    () => tab === "audit" ? phase4Api.securityAudit({ q, tenant_id: tenantId || undefined, limit: 150 }) : Promise.resolve({ items: [] }),
    [tab, q, tenantId, dataMode],
    { pollMs: 10_000 },
  );

  const summary = (summaryQuery.data ?? {}) as SecuritySummary;
  const alerts = alertsQuery.data?.items ?? [];
  const auditRecords = auditQuery.data?.items ?? [];

  const setFilters = (patch: Record<string, string | null>) => {
    const params = new URLSearchParams(searchParams);
    Object.entries(patch).forEach(([key, value]) => value ? params.set(key, value) : params.delete(key));
    setSearchParams(params, { replace: true });
  };

  const resolveAlert = async () => {
    if (!selectedAlert) return;
    setActionError(null); setNotice(null);
    try {
      const resolved = await phase4Api.resolveSecurityAlert(selectedAlert.id, reason);
      setSelectedAlert(resolved);
      setNotice("Security alert resolved with evidence and reason retained.");
      alertsQuery.reload(); summaryQuery.reload();
    } catch (error) {
      setActionError(error instanceof Error ? error.message : String(error));
    }
  };

  return (
    <PlatformShell
      title="Security & Compliance"
      subtitle="Investigate alert evidence, source context, tenant scope and privileged actions without discarding the audit trail."
      actions={<><div className="platform-mode-switch">{(["REAL", "DEMO"] as PlatformDataMode[]).map((mode) => <button key={mode} className={dataMode === mode ? "active" : ""} onClick={() => setFilters({ mode, tenant: null })}>{mode}</button>)}</div><button className="platform-btn" onClick={() => { summaryQuery.reload(); alertsQuery.reload(); auditQuery.reload(); }}>Refresh</button></>}
    >
      {summaryQuery.error ? <ErrorState error={summaryQuery.error} retry={summaryQuery.reload} /> : null}
      {actionError ? <div className="platform-error">{actionError}</div> : null}
      {notice ? <div className="platform-inline-success">{notice}</div> : null}
      <section className="platform-grid">
        <MetricCard label="Open alerts" value={summary.open_alerts ?? 0} tone="amber" mark="AL" />
        <MetricCard label="Critical alerts" value={summary.critical_alerts ?? 0} tone="red" mark="CR" />
        <MetricCard label="Disabled users" value={summary.disabled_users ?? 0} tone="purple" mark="DU" />
        <MetricCard label="Locked users" value={summary.locked_users ?? 0} tone="amber" mark="LU" />
        <MetricCard label="MFA coverage" value={summary.mfa_coverage_percent ?? "Not measured"} tone="green" mark="MF" />
      </section>

      <section className="platform-card">
        <nav className="platform-tabs" aria-label="Security workspace sections"><button className={tab === "alerts" ? "active" : undefined} onClick={() => setFilters({ tab: null })}>Security alerts</button><button className={tab === "audit" ? "active" : undefined} onClick={() => setFilters({ tab: "audit" })}>Privileged audit log</button></nav>
        <div className="platform-toolbar"><input placeholder="Search title, action, reason, IP or entity" value={q} onChange={(event) => setFilters({ q: event.target.value || null })} /><select value={tenantId} onChange={(event) => setFilters({ tenant: event.target.value || null })}><option value="">Platform + {dataMode.toLowerCase()} tenants</option>{(tenants.data?.items || []).map((tenant) => <option key={tenant.id} value={tenant.id}>{tenant.name} · {tenant.amo_code}</option>)}</select>{tab === "alerts" ? <><select value={severity} onChange={(event) => setFilters({ severity: event.target.value || null })}><option value="">All severities</option><option>CRITICAL</option><option>HIGH</option><option>MEDIUM</option><option>LOW</option><option>INFO</option></select><select value={status} onChange={(event) => setFilters({ status: event.target.value || null })}><option value="">All states</option><option>OPEN</option><option>ACKNOWLEDGED</option><option>RESOLVED</option></select></> : null}</div>
      </section>

      {tab === "alerts" ? (
        <section className="platform-commercial-layout">
          <div className="platform-card"><div className="platform-section-title"><div><h2>Security alerts</h2><p>Open a record to inspect description, source and evidence.</p></div><StatusBadge value={`${alertsQuery.data?.total ?? alerts.length} MATCHED`} /></div>{alertsQuery.error ? <ErrorState error={alertsQuery.error} retry={alertsQuery.reload} /> : alerts.length ? <DataTable><thead><tr><th>Alert</th><th>Tenant</th><th>Category</th><th>Severity</th><th>Status</th><th>Created</th><th>Open</th></tr></thead><tbody>{alerts.map((alert) => <tr key={alert.id}><td><strong>{alert.title}</strong><br /><small>{alert.source_ip || "No source IP"}</small></td><td>{alert.tenant_name || alert.tenant_id || "Platform"}</td><td>{alert.category}</td><td><StatusBadge value={alert.severity} /></td><td><StatusBadge value={alert.status} /></td><td>{new Date(alert.created_at).toLocaleString()}</td><td><button className="platform-btn" onClick={() => setSelectedAlert(alert)}>Investigate</button></td></tr>)}</tbody></DataTable> : <EmptyState label="No security alerts match the filters." />}</div>
          <aside className="platform-card platform-commercial-sidebar"><h2>Investigation detail</h2>{selectedAlert ? <div className="platform-stack-form"><div className="platform-subtle-panel"><strong>{selectedAlert.title}</strong><p>{selectedAlert.description || "No description supplied."}</p><div className="platform-actions"><StatusBadge value={selectedAlert.severity} /><StatusBadge value={selectedAlert.status} /></div></div><label><span>Tenant</span><input readOnly value={selectedAlert.tenant_name || selectedAlert.tenant_id || "Platform"} /></label><label><span>Source IP</span><input readOnly value={selectedAlert.source_ip || "Not recorded"} /></label><label><span>User agent</span><textarea readOnly value={selectedAlert.user_agent || "Not recorded"} /></label><label><span>Evidence</span><textarea readOnly rows={8} value={JSON.stringify(selectedAlert.evidence || {}, null, 2)} /></label>{selectedAlert.status !== "RESOLVED" ? <><label><span>Resolution reason</span><textarea value={reason} onChange={(event) => setReason(event.target.value)} /></label><button className="platform-btn primary" onClick={resolveAlert}>Resolve alert</button></> : <div className="platform-inline-success">Resolved {selectedAlert.resolved_at ? new Date(selectedAlert.resolved_at).toLocaleString() : ""}</div>}</div> : <EmptyState label="Select Investigate to inspect an alert." />}</aside>
        </section>
      ) : (
        <section className="platform-commercial-layout">
          <div className="platform-card"><div className="platform-section-title"><div><h2>Privileged audit log</h2><p>Reasons, actor, tenant, entity and request context.</p></div><StatusBadge value={`${auditQuery.data?.total ?? auditRecords.length} MATCHED`} /></div>{auditQuery.error ? <ErrorState error={auditQuery.error} retry={auditQuery.reload} /> : auditRecords.length ? <DataTable><thead><tr><th>Created</th><th>Action</th><th>Module</th><th>Tenant</th><th>Entity</th><th>Reason</th><th>Open</th></tr></thead><tbody>{auditRecords.map((record) => <tr key={record.id}><td>{new Date(record.created_at).toLocaleString()}</td><td><strong>{record.action}</strong></td><td>{record.module}</td><td>{record.tenant_id || "Platform"}</td><td>{record.entity_type || "—"}<br /><small>{record.entity_id}</small></td><td>{record.reason || "No reason recorded"}</td><td><button className="platform-btn" onClick={() => setSelectedAudit(record)}>Inspect</button></td></tr>)}</tbody></DataTable> : <EmptyState label="No audit records match the filters." />}</div>
          <aside className="platform-card platform-commercial-sidebar"><h2>Audit evidence</h2>{selectedAudit ? <div className="platform-stack-form"><div className="platform-subtle-panel"><strong>{selectedAudit.action}</strong><p>{selectedAudit.reason || "No reason recorded."}</p></div><label><span>Actor</span><input readOnly value={selectedAudit.actor_user_id || "System"} /></label><label><span>Tenant</span><input readOnly value={selectedAudit.tenant_id || "Platform"} /></label><label><span>IP address</span><input readOnly value={selectedAudit.ip_address || "Not recorded"} /></label><label><span>User agent</span><textarea readOnly value={selectedAudit.user_agent || "Not recorded"} /></label><label><span>Details</span><textarea readOnly rows={10} value={JSON.stringify(selectedAudit.details || {}, null, 2)} /></label></div> : <EmptyState label="Select Inspect to view audit evidence." />}</aside>
        </section>
      )}
    </PlatformShell>
  );
}
