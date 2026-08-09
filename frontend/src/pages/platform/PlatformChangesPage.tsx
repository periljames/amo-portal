import React, { useMemo, useState } from "react";

import { platformOperationsApi } from "../../services/platformOperations";
import { DataTable, EmptyState, ErrorState, MetricCard, PlatformShell, StatusBadge } from "./components/PlatformShared";
import { usePlatformData } from "./components/usePlatformData";

const CHANGE_KINDS = ["DEPLOYMENT", "FEATURE_FLAG", "MAINTENANCE", "INCIDENT", "CONFIGURATION", "MIGRATION"] as const;
type ChangeKind = (typeof CHANGE_KINDS)[number];

function when(value: unknown) {
  return value ? new Date(String(value)).toLocaleString() : "—";
}

function toIso(localValue: string): string | null {
  if (!localValue) return null;
  const date = new Date(localValue);
  return Number.isFinite(date.getTime()) ? date.toISOString() : null;
}

export default function PlatformChangesPage() {
  const [kindFilter, setKindFilter] = useState("");
  const changes = usePlatformData(() => platformOperationsApi.changeMarkers(kindFilter || undefined), [kindFilter]);
  const snapshot = usePlatformData(() => platformOperationsApi.snapshot(), []);
  const [actionError, setActionError] = useState<string | null>(null);
  const [notice, setNotice] = useState<string | null>(null);
  const [changeForm, setChangeForm] = useState({
    kind: "CONFIGURATION" as ChangeKind,
    title: "",
    reference: "",
    note: "",
  });
  const [maintenanceForm, setMaintenanceForm] = useState({
    title: "",
    starts_at: "",
    ends_at: "",
    description: "",
  });
  const items = changes.data?.items || [];
  const maintenance = snapshot.data?.changes?.maintenance || [];
  const deployments = items.filter((item: any) => item.kind === "DEPLOYMENT");
  const flags = items.filter((item: any) => item.kind === "FEATURE_FLAG");

  const newestChange = useMemo(() => items[0] || null, [items]);

  const recordChange = async () => {
    const title = changeForm.title.trim();
    if (!title) {
      setActionError("A change title is required.");
      return;
    }
    setActionError(null);
    setNotice(null);
    try {
      await platformOperationsApi.createChangeMarker({
        kind: changeForm.kind,
        title,
        reference: changeForm.reference.trim() || undefined,
        details: changeForm.note.trim() ? { note: changeForm.note.trim() } : undefined,
      });
      setChangeForm((current) => ({ ...current, title: "", reference: "", note: "" }));
      setNotice("Change marker recorded in the Platform audit timeline.");
      await Promise.all([changes.reload(), snapshot.reload()]);
    } catch (error) {
      setActionError(error instanceof Error ? error.message : String(error));
    }
  };

  const scheduleMaintenance = async () => {
    const title = maintenanceForm.title.trim();
    const startsAt = toIso(maintenanceForm.starts_at);
    const endsAt = toIso(maintenanceForm.ends_at);
    if (!title || !startsAt || !endsAt) {
      setActionError("Maintenance title, start, and end are required and must be valid dates.");
      return;
    }
    if (new Date(endsAt).getTime() <= new Date(startsAt).getTime()) {
      setActionError("Maintenance end time must be later than the start time.");
      return;
    }
    setActionError(null);
    setNotice(null);
    try {
      await platformOperationsApi.scheduleMaintenance({
        title,
        starts_at: startsAt,
        ends_at: endsAt,
        description: maintenanceForm.description.trim() || undefined,
      });
      setMaintenanceForm({ title: "", starts_at: "", ends_at: "", description: "" });
      setNotice("Maintenance window scheduled and added to the change-management context.");
      await Promise.all([snapshot.reload(), changes.reload()]);
    } catch (error) {
      setActionError(error instanceof Error ? error.message : String(error));
    }
  };

  return (
    <PlatformShell
      title="Change Management"
      subtitle="Audit-oriented workspace for deployments, feature flags, migrations, maintenance windows and incident-linked platform changes."
      actions={<button className="platform-btn" onClick={() => { void changes.reload(); void snapshot.reload(); }}>Refresh workspace</button>}
    >
      {changes.error ? <ErrorState error={changes.error} retry={changes.reload} /> : null}
      {snapshot.error ? <ErrorState error={snapshot.error} retry={snapshot.reload} /> : null}
      {actionError ? <div className="platform-error">{actionError}</div> : null}
      {notice ? <p><StatusBadge value="SUCCEEDED" /> {notice}</p> : null}

      <section className="platform-grid">
        <MetricCard label="Recorded changes" value={items.length} caption={kindFilter ? `${kindFilter} filter` : "Latest bounded history"} />
        <MetricCard label="Deployments" value={deployments.length} caption="Includes automation-owned markers" tone="green" />
        <MetricCard label="Feature-flag changes" value={flags.length} />
        <MetricCard label="Maintenance windows" value={maintenance.length} tone="amber" />
      </section>

      <section className="platform-two">
        <div className="platform-card">
          <div className="platform-section-title"><div><h2>Record governed change</h2><p>Create a bounded audit marker with an operator-facing reference and note.</p></div><StatusBadge value={changeForm.kind} /></div>
          <div className="platform-form">
            <label>Change kind<select value={changeForm.kind} onChange={(event) => setChangeForm({ ...changeForm, kind: event.target.value as ChangeKind })}>{CHANGE_KINDS.map((kind) => <option key={kind} value={kind}>{kind.replaceAll("_", " ")}</option>)}</select></label>
            <label>Title<input value={changeForm.title} maxLength={255} onChange={(event) => setChangeForm({ ...changeForm, title: event.target.value })} placeholder="What changed?" /></label>
            <label>Reference<input value={changeForm.reference} maxLength={255} onChange={(event) => setChangeForm({ ...changeForm, reference: event.target.value })} placeholder="PR, commit, release, ticket or flag" /></label>
            <label>Operator note<textarea value={changeForm.note} maxLength={512} onChange={(event) => setChangeForm({ ...changeForm, note: event.target.value })} placeholder="Purpose, scope or rollback context" /></label>
            <button className="platform-btn primary" disabled={!changeForm.title.trim()} onClick={() => void recordChange()}>Record change</button>
          </div>
        </div>

        <div className="platform-card">
          <div className="platform-section-title"><div><h2>Schedule maintenance</h2><p>Define the operational window explicitly; dates are stored as ISO timestamps.</p></div><StatusBadge value="MAINTENANCE" /></div>
          <div className="platform-form">
            <label>Window title<input value={maintenanceForm.title} maxLength={255} onChange={(event) => setMaintenanceForm({ ...maintenanceForm, title: event.target.value })} placeholder="Database maintenance" /></label>
            <label>Starts<input type="datetime-local" value={maintenanceForm.starts_at} onChange={(event) => setMaintenanceForm({ ...maintenanceForm, starts_at: event.target.value })} /></label>
            <label>Ends<input type="datetime-local" value={maintenanceForm.ends_at} onChange={(event) => setMaintenanceForm({ ...maintenanceForm, ends_at: event.target.value })} /></label>
            <label>Description<textarea value={maintenanceForm.description} onChange={(event) => setMaintenanceForm({ ...maintenanceForm, description: event.target.value })} placeholder="Expected impact, operator note, or execution scope" /></label>
            <button className="platform-btn primary" disabled={!maintenanceForm.title.trim() || !maintenanceForm.starts_at || !maintenanceForm.ends_at} onClick={() => void scheduleMaintenance()}>Schedule maintenance</button>
          </div>
        </div>
      </section>

      <section className="platform-card">
        <div className="platform-section-title">
          <div><h2>Change timeline</h2><p>Filter the bounded audit history without hiding the authoritative actor or occurrence time.</p></div>
          {newestChange ? <small>Latest: {when(newestChange.occurred_at)}</small> : null}
        </div>
        <div className="platform-toolbar">
          <select value={kindFilter} onChange={(event) => setKindFilter(event.target.value)}><option value="">All change kinds</option>{CHANGE_KINDS.map((kind) => <option key={kind} value={kind}>{kind.replaceAll("_", " ")}</option>)}</select>
          {kindFilter ? <button className="platform-btn" onClick={() => setKindFilter("")}>Clear filter</button> : null}
        </div>
        {items.length ? (
          <DataTable>
            <thead><tr><th>Kind</th><th>Reference</th><th>Title</th><th>Context</th><th>Actor</th><th>Occurred</th></tr></thead>
            <tbody>{items.map((item: any) => <tr key={item.id}><td><StatusBadge value={item.kind} /></td><td>{item.reference || "—"}</td><td>{item.title}</td><td>{item.details?.note || Object.entries(item.details || {}).map(([key, value]) => `${key}: ${String(value)}`).join(" · ") || "—"}</td><td>{item.actor_user_id || "automation/system"}</td><td>{when(item.occurred_at)}</td></tr>)}</tbody>
          </DataTable>
        ) : <EmptyState label="No change markers match the current filter." />}
      </section>

      <section className="platform-card">
        <h2>Maintenance windows</h2>
        {maintenance.length ? (
          <DataTable>
            <thead><tr><th>Window</th><th>Status</th><th>Impact</th><th>Starts</th><th>Ends</th><th>Description</th></tr></thead>
            <tbody>{maintenance.map((item: any) => <tr key={item.id}><td>{item.title}</td><td><StatusBadge value={item.status} /></td><td>{item.impact_level || "—"}</td><td>{when(item.starts_at)}</td><td>{when(item.ends_at)}</td><td>{item.description || "—"}</td></tr>)}</tbody>
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
