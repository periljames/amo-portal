import React from "react";

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
};

export default function PlatformSecurityPage() {
  const summaryQuery = usePlatformData(() => platformApi.securitySummary(), []);
  const alertsQuery = usePlatformData(() => platformApi.securityAlerts(), []);
  const auditQuery = usePlatformData(() => platformApi.auditLog(), []);
  const summary = (summaryQuery.data ?? {}) as SecuritySummary;
  const alerts = (alertsQuery.data?.items ?? []) as SecurityAlert[];
  const auditRecords = (auditQuery.data?.items ?? []) as AuditRecord[];

  return (
    <PlatformShell title="Security & Compliance" subtitle="Failed logins, suspicious access, privileged actions, support sessions and compliance alerts.">
      {summaryQuery.error ? <ErrorState error={summaryQuery.error} retry={summaryQuery.reload} /> : null}
      <section className="platform-grid">
        <MetricCard label="Open alerts" value={summary.open_alerts ?? 0} />
        <MetricCard label="Critical alerts" value={summary.critical_alerts ?? 0} />
        <MetricCard label="Disabled users" value={summary.disabled_users ?? 0} />
        <MetricCard label="Locked users" value={summary.locked_users ?? 0} />
        <MetricCard label="MFA coverage" value={summary.mfa_coverage_percent ?? "Not measured"} />
      </section>
      <section className="platform-two">
        <div className="platform-card">
          <h2>Security alerts</h2>
          {alerts.length ? <DataTable><thead><tr><th>Alert</th><th>Severity</th><th>Status</th><th>Action</th></tr></thead><tbody>{alerts.map((alert) => <tr key={alert.id}><td>{alert.title ?? "Security alert"}<br /><small>{alert.category ?? "GENERAL"}</small></td><td><StatusBadge value={alert.severity} /></td><td><StatusBadge value={alert.status} /></td><td><button className="platform-btn" onClick={() => platformApi.acknowledgeAlert(alert.id).then(alertsQuery.reload)}>Acknowledge</button></td></tr>)}</tbody></DataTable> : <EmptyState label="No security alerts." />}
        </div>
        <div className="platform-card">
          <h2>Privileged audit log</h2>
          {auditRecords.length ? auditRecords.slice(0, 10).map((record) => <p key={record.id}><strong>{record.action ?? "Platform action"}</strong><br /><small>{record.created_at ?? "-"} · {record.reason || "No reason"}</small></p>) : <EmptyState label="No platform audit records yet." />}
        </div>
      </section>
    </PlatformShell>
  );
}
