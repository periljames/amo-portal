import React from "react";
import { useSearchParams } from "react-router-dom";

import { platformApi } from "../../services/platformControl";
import { DataTable, EmptyState, ErrorState, MetricCard, PlatformShell, StatusBadge } from "./components/PlatformShared";
import { usePlatformData } from "./components/usePlatformData";

type SecuritySummary = {
  open_alerts?: number;
  critical_alerts?: number;
  disabled_users?: number;
  locked_users?: number;
  mfa_coverage_percent?: number | string;
};

type SecurityAlert = {
  id: string;
  title?: string;
  category?: string;
  severity?: string;
  status?: string;
};

type AuditRecord = {
  id: string;
  action?: string;
  created_at?: string;
  reason?: string | null;
  tenant_id?: string | null;
  entity_type?: string | null;
  entity_id?: string | null;
};

export default function PlatformSecurityPage() {
  const [searchParams, setSearchParams] = useSearchParams();
  const tab = searchParams.get("tab") === "audit" ? "audit" : "alerts";
  const summaryQuery = usePlatformData(() => platformApi.securitySummary(), [], { pollMs: 15_000 });
  const alertsQuery = usePlatformData(() => tab === "alerts" ? platformApi.securityAlerts() : Promise.resolve({ items: [] }), [tab], { pollMs: 10_000 });
  const auditQuery = usePlatformData(() => tab === "audit" ? platformApi.auditLog() : Promise.resolve({ items: [] }), [tab], { pollMs: 10_000 });
  const summary = (summaryQuery.data ?? {}) as SecuritySummary;
  const alerts = (alertsQuery.data?.items ?? []) as SecurityAlert[];
  const auditRecords = (auditQuery.data?.items ?? []) as AuditRecord[];

  const setTab = (next: "alerts" | "audit") => {
    const params = new URLSearchParams(searchParams);
    if (next === "audit") params.set("tab", "audit");
    else params.delete("tab");
    setSearchParams(params, { replace: true });
  };

  return (
    <PlatformShell
      title="Security & Compliance"
      subtitle="Alerts, audit log and compliance"
      actions={<button className="platform-btn" onClick={() => { summaryQuery.reload(); alertsQuery.reload(); auditQuery.reload(); }}>Refresh security data</button>}
    >
      {summaryQuery.error ? <ErrorState error={summaryQuery.error} retry={summaryQuery.reload} /> : null}
      <section className="platform-grid">
        <MetricCard label="Open alerts" value={summary.open_alerts ?? 0} tone="amber" mark="AL" />
        <MetricCard label="Critical alerts" value={summary.critical_alerts ?? 0} tone="red" mark="CR" />
        <MetricCard label="Disabled users" value={summary.disabled_users ?? 0} tone="purple" mark="DU" />
        <MetricCard label="Locked users" value={summary.locked_users ?? 0} tone="amber" mark="LU" />
        <MetricCard label="MFA coverage" value={summary.mfa_coverage_percent ?? "Not measured"} tone="green" mark="MF" />
      </section>

      <nav className="platform-tabs" aria-label="Security workspace sections">
        <button className={tab === "alerts" ? "active" : undefined} onClick={() => setTab("alerts")}>Security alerts</button>
        <button className={tab === "audit" ? "active" : undefined} onClick={() => setTab("audit")}>Privileged audit log</button>
      </nav>

      {tab === "alerts" ? (
        <section className="platform-card">
          <div className="platform-section-title"><div><h2>Security alerts</h2><p>Acknowledge reviewed alerts without removing the evidence trail.</p></div><StatusBadge value={`${alerts.length} LOADED`} /></div>
          {alertsQuery.error ? <ErrorState error={alertsQuery.error} retry={alertsQuery.reload} /> : alerts.length ? <DataTable><thead><tr><th>Alert</th><th>Category</th><th>Severity</th><th>Status</th><th>Action</th></tr></thead><tbody>{alerts.map((alert) => <tr key={alert.id}><td><strong>{alert.title ?? "Security alert"}</strong></td><td>{alert.category ?? "GENERAL"}</td><td><StatusBadge value={alert.severity} /></td><td><StatusBadge value={alert.status} /></td><td><button className="platform-btn" disabled={String(alert.status).toUpperCase() !== "OPEN"} onClick={() => platformApi.acknowledgeAlert(alert.id).then(alertsQuery.reload)}>Acknowledge</button></td></tr>)}</tbody></DataTable> : <EmptyState label="No security alerts." />}
        </section>
      ) : (
        <section className="platform-card">
          <div className="platform-section-title"><div><h2>Privileged audit log</h2><p>Platform actions, reasons, tenant scope and affected records.</p></div><button className="platform-btn" onClick={auditQuery.reload}>Refresh log</button></div>
          {auditQuery.error ? <ErrorState error={auditQuery.error} retry={auditQuery.reload} /> : auditRecords.length ? <DataTable><thead><tr><th>Created</th><th>Action</th><th>Tenant</th><th>Entity</th><th>Reason</th></tr></thead><tbody>{auditRecords.map((record) => <tr key={record.id}><td>{record.created_at ? new Date(record.created_at).toLocaleString() : "-"}</td><td><strong>{record.action ?? "Platform action"}</strong></td><td>{record.tenant_id ?? "Platform"}</td><td>{record.entity_type ?? "-"}{record.entity_id ? <><br /><small>{record.entity_id}</small></> : null}</td><td>{record.reason || "No reason recorded"}</td></tr>)}</tbody></DataTable> : <EmptyState label="No platform audit records yet." />}
        </section>
      )}
    </PlatformShell>
  );
}
