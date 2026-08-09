import React, { useState } from "react";

import { platformOperationsApi } from "../../services/platformOperations";
import { DataTable, EmptyState, ErrorState, MetricCard, PlatformShell, StatusBadge } from "./components/PlatformShared";
import { usePlatformData } from "./components/usePlatformData";

function when(value: unknown) {
  return value ? new Date(String(value)).toLocaleString() : "—";
}

export default function PlatformChangesPage() {
  const changes = usePlatformData(() => platformOperationsApi.changeMarkers(), []);
  const snapshot = usePlatformData(() => platformOperationsApi.snapshot(), []);
  const [actionError, setActionError] = useState<string | null>(null);
  const items = changes.data?.items || [];
  const maintenance = snapshot.data?.changes?.maintenance || [];
  const deployments = items.filter((item: any) => item.kind === "DEPLOYMENT");
  const flags = items.filter((item: any) => item.kind === "FEATURE_FLAG");

  const recordChange = async () => {
    const kind = (window.prompt("Change kind: DEPLOYMENT, FEATURE_FLAG, MAINTENANCE, INCIDENT, CONFIGURATION or MIGRATION", "DEPLOYMENT") || "").trim().toUpperCase();
    const title = (window.prompt("Change title") || "").trim();
    if (!kind || !title) return;
    const reference = (window.prompt("Reference: PR, commit, release, ticket or flag") || "").trim() || undefined;
    setActionError(null);
    try {
      await platformOperationsApi.createChangeMarker({ kind, title, reference });
      await changes.reload();
    } catch (error) {
      setActionError(error instanceof Error ? error.message : String(error));
    }
  };

  const scheduleMaintenance = async () => {
    const title = (window.prompt("Maintenance title") || "").trim();
    if (!title) return;
    const startsAt = (window.prompt("Start date/time (ISO 8601)") || "").trim();
    const endsAt = (window.prompt("End date/time (ISO 8601)") || "").trim();
    if (!startsAt || !endsAt) return;
    const description = (window.prompt("Description / operator note") || "").trim() || undefined;
    setActionError(null);
    try {
      await platformOperationsApi.scheduleMaintenance({ title, starts_at: startsAt, ends_at: endsAt, description });
      await Promise.all([snapshot.reload(), changes.reload()]);
    } catch (error) {
      setActionError(error instanceof Error ? error.message : String(error));
    }
  };

  return (
    <PlatformShell
      title="Change Management"
      subtitle="One audit-oriented workspace for deployments, feature flags, migrations, maintenance windows and incident-linked platform changes."
      actions={<><button className="platform-btn" onClick={scheduleMaintenance}>Schedule maintenance</button><button className="platform-btn primary" onClick={recordChange}>Record change</button></>}
    >
      {changes.error ? <ErrorState error={changes.error} retry={changes.reload} /> : null}
      {snapshot.error ? <ErrorState error={snapshot.error} retry={snapshot.reload} /> : null}
      {actionError ? <div className="platform-error">{actionError}</div> : null}

      <section className="platform-grid">
        <MetricCard label="Recorded changes" value={items.length} caption="Latest bounded history" />
        <MetricCard label="Deployments" value={deployments.length} caption="Includes automation-owned markers" tone="green" />
        <MetricCard label="Feature-flag changes" value={flags.length} />
        <MetricCard label="Maintenance windows" value={maintenance.length} tone="amber" />
      </section>

      <section className="platform-card">
        <h2>Change timeline</h2>
        {items.length ? (
          <DataTable>
            <thead><tr><th>Kind</th><th>Reference</th><th>Title</th><th>Actor</th><th>Occurred</th></tr></thead>
            <tbody>{items.map((item: any) => <tr key={item.id}><td><StatusBadge value={item.kind} /></td><td>{item.reference || "—"}</td><td>{item.title}</td><td>{item.actor_user_id || "automation/system"}</td><td>{when(item.occurred_at)}</td></tr>)}</tbody>
          </DataTable>
        ) : <EmptyState label="No change markers have been recorded yet." />}
      </section>

      <section className="platform-card">
        <h2>Maintenance windows</h2>
        {maintenance.length ? (
          <DataTable>
            <thead><tr><th>Window</th><th>Status</th><th>Impact</th><th>Starts</th><th>Ends</th></tr></thead>
            <tbody>{maintenance.map((item: any) => <tr key={item.id}><td>{item.title}</td><td><StatusBadge value={item.status} /></td><td>{item.impact_level || "—"}</td><td>{when(item.starts_at)}</td><td>{when(item.ends_at)}</td></tr>)}</tbody>
          </DataTable>
        ) : <EmptyState label="No maintenance windows are currently recorded." />}
      </section>

      <section className="platform-card">
        <h2>Operating contract</h2>
        <p>Deployment automation records successful deployment markers. Manual markers require an authenticated Platform superuser. High-risk tenant side effects remain durable jobs with approval/fencing controls; this workspace records change context and does not bypass those controls.</p>
      </section>
    </PlatformShell>
  );
}
