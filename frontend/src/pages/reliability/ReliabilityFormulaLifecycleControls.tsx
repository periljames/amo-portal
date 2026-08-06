import React, { useCallback, useEffect, useState } from "react";

import {
  getReliabilityCapabilities,
  listReliabilityMetricDefinitions,
  listReliabilityProgrammeVersions,
  listReliabilityThresholdVersions,
  runDueReliabilityCalculations,
  transitionReliabilityProgrammeVersion,
  transitionReliabilityThresholdVersion,
  type ReliabilityCapabilitySnapshot,
  type ReliabilityMetricDefinition,
  type ReliabilityProgrammeVersion,
  type ReliabilityThresholdVersion,
} from "../../services/reliability";
import "./ReliabilityFormulaLifecycleControls.css";

const EMPTY_CAPABILITIES: ReliabilityCapabilitySnapshot = { capabilities: [], superuser: false };

function can(snapshot: ReliabilityCapabilitySnapshot, capability: string): boolean {
  return snapshot.superuser || snapshot.capabilities.includes(capability);
}

function message(error: unknown): string {
  return error instanceof Error ? error.message : "The governed lifecycle action failed.";
}

function statusClass(value: string): string {
  return `reliability-v2__status reliability-v2__status--${value.toLowerCase().replaceAll("_", "-")}`;
}

export function ReliabilityFormulaLifecycleControls(): React.ReactElement {
  const [versions, setVersions] = useState<ReliabilityProgrammeVersion[]>([]);
  const [metrics, setMetrics] = useState<ReliabilityMetricDefinition[]>([]);
  const [thresholds, setThresholds] = useState<ReliabilityThresholdVersion[]>([]);
  const [capabilities, setCapabilities] = useState<ReliabilityCapabilitySnapshot>(EMPTY_CAPABILITIES);
  const [programmeVersionId, setProgrammeVersionId] = useState("");
  const [programmeTarget, setProgrammeTarget] = useState("IN_REVIEW");
  const [thresholdId, setThresholdId] = useState("");
  const [thresholdTarget, setThresholdTarget] = useState("APPROVED");
  const [working, setWorking] = useState(false);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [notice, setNotice] = useState<string | null>(null);

  const load = useCallback(async () => {
    setLoading(true);
    setError(null);
    try {
      const [versionRows, metricRows, thresholdRows, capabilityRows] = await Promise.all([
        listReliabilityProgrammeVersions(),
        listReliabilityMetricDefinitions(),
        listReliabilityThresholdVersions(),
        getReliabilityCapabilities(),
      ]);
      setVersions(versionRows);
      setMetrics(metricRows);
      setThresholds(thresholdRows);
      setCapabilities(capabilityRows);
      setProgrammeVersionId((current) => current || versionRows[0]?.id || "");
      setThresholdId((current) => current || thresholdRows[0]?.id || "");
    } catch (caught: unknown) {
      setError(message(caught));
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => { void load(); }, [load]);

  const transitionProgramme = async (event: React.FormEvent<HTMLFormElement>) => {
    event.preventDefault();
    const rationale = String(new FormData(event.currentTarget).get("rationale") || "").trim();
    if (!programmeVersionId || !rationale) return;
    setWorking(true);
    setError(null);
    setNotice(null);
    try {
      const updated = await transitionReliabilityProgrammeVersion(programmeVersionId, programmeTarget, rationale);
      setVersions((current) => current.map((row) => row.id === updated.id ? updated : row));
      setNotice(`Programme version ${updated.revision} transitioned to ${updated.status}.`);
      event.currentTarget.reset();
    } catch (caught: unknown) {
      setError(message(caught));
    } finally {
      setWorking(false);
    }
  };

  const transitionThreshold = async (event: React.FormEvent<HTMLFormElement>) => {
    event.preventDefault();
    const rationale = String(new FormData(event.currentTarget).get("rationale") || "").trim();
    if (!thresholdId || !rationale) return;
    setWorking(true);
    setError(null);
    setNotice(null);
    try {
      const updated = await transitionReliabilityThresholdVersion(thresholdId, thresholdTarget, rationale);
      setThresholds((current) => current.map((row) => row.id === updated.id ? updated : row));
      setNotice(`Threshold version ${updated.version} transitioned to ${updated.status}.`);
      event.currentTarget.reset();
    } catch (caught: unknown) {
      setError(message(caught));
    } finally {
      setWorking(false);
    }
  };

  const runDue = async () => {
    setWorking(true);
    setError(null);
    setNotice(null);
    try {
      const runs = await runDueReliabilityCalculations();
      setNotice(`${runs.length} due governed calculation${runs.length === 1 ? "" : "s"} executed.`);
    } catch (caught: unknown) {
      setError(message(caught));
    } finally {
      setWorking(false);
    }
  };

  const programmeNeedsApprovalCapability = ["APPROVED", "EFFECTIVE"].includes(programmeTarget);
  const thresholdNeedsApprovalCapability = ["APPROVED", "EFFECTIVE"].includes(thresholdTarget);
  const canTransitionProgramme = can(capabilities, "reliability.programme.manage")
    && (!programmeNeedsApprovalCapability || can(capabilities, "reliability.programme.approve"));
  const canTransitionThreshold = can(capabilities, "reliability.metric.manage")
    && (!thresholdNeedsApprovalCapability || can(capabilities, "reliability.programme.approve"));

  return (
    <section className="reliability-formula-lifecycle" aria-labelledby="reliability-formula-lifecycle-heading">
      <div className="reliability-formula-admin__heading">
        <div>
          <p className="reliability-v2__eyebrow">Approval and effectivity</p>
          <h2 id="reliability-formula-lifecycle-heading">Formula lifecycle control</h2>
          <p>Move programme and threshold versions through the exact API lifecycle with a retained rationale and capability-gated approval.</p>
        </div>
        <div className="reliability-v2__actions">
          <button type="button" className="btn btn-secondary" onClick={() => void load()} disabled={loading || working}>Refresh lifecycle</button>
          <button type="button" className="btn btn-primary" onClick={() => void runDue()} disabled={working || !can(capabilities, "reliability.metric.manage")}>Run due calculations</button>
        </div>
      </div>

      {loading && <div className="reliability-v2__loading" role="status">Loading formula lifecycle records…</div>}
      {error && <div className="reliability-v2__error" role="alert">{error}</div>}
      {notice && <div className="reliability-formula-admin__message" role="status">{notice}</div>}

      {!loading && (
        <div className="reliability-formula-lifecycle__forms">
          <form className="reliability-formula-admin__form" onSubmit={(event) => void transitionProgramme(event)}>
            <h3>Transition programme version</h3>
            <label>Programme version<select value={programmeVersionId} onChange={(event) => setProgrammeVersionId(event.target.value)} required><option value="">Select version</option>{versions.map((version) => <option key={version.id} value={version.id}>{version.revision} · {version.status}</option>)}</select></label>
            <label>Target status<select value={programmeTarget} onChange={(event) => setProgrammeTarget(event.target.value)}><option>IN_REVIEW</option><option>APPROVED</option><option>EFFECTIVE</option><option>SUPERSEDED</option><option>REJECTED</option></select></label>
            <label>Transition rationale<textarea name="rationale" rows={4} required minLength={5} /></label>
            <button className="btn btn-primary" disabled={working || !canTransitionProgramme}>Apply programme transition</button>
            {!can(capabilities, "reliability.programme.manage") && <small>Required capability: reliability.programme.manage</small>}
            {programmeNeedsApprovalCapability && !can(capabilities, "reliability.programme.approve") && <small>Approval targets also require: reliability.programme.approve</small>}
          </form>

          <form className="reliability-formula-admin__form" onSubmit={(event) => void transitionThreshold(event)}>
            <h3>Transition threshold version</h3>
            <label>Threshold version<select value={thresholdId} onChange={(event) => setThresholdId(event.target.value)} required><option value="">Select threshold</option>{thresholds.map((threshold) => { const metric = metrics.find((row) => row.id === threshold.metric_definition_id); return <option key={threshold.id} value={threshold.id}>{metric?.code || threshold.metric_definition_id} · {threshold.version} · {threshold.status}</option>; })}</select></label>
            <label>Target status<select value={thresholdTarget} onChange={(event) => setThresholdTarget(event.target.value)}><option>APPROVED</option><option>EFFECTIVE</option><option>SUPERSEDED</option><option>REJECTED</option></select></label>
            <label>Approval or transition rationale<textarea name="rationale" rows={4} required minLength={5} /></label>
            <button className="btn btn-primary" disabled={working || !canTransitionThreshold}>Apply threshold transition</button>
            {!can(capabilities, "reliability.metric.manage") && <small>Required capability: reliability.metric.manage</small>}
            {thresholdNeedsApprovalCapability && !can(capabilities, "reliability.programme.approve") && <small>Approval targets also require: reliability.programme.approve</small>}
          </form>
        </div>
      )}

      {!loading && (
        <div className="reliability-formula-admin__register">
          <h3>Programme and threshold effectivity register</h3>
          <div className="reliability-v2__table-wrap"><table className="reliability-v2__table"><thead><tr><th>Controlled object</th><th>Version</th><th>Status</th><th>Effective period</th><th>Approval</th></tr></thead><tbody>
            {versions.map((version) => <tr key={`programme-${version.id}`}><td>Programme version<small>{version.programme_id}</small></td><td>{version.revision}</td><td><span className={statusClass(version.status)}>{version.status}</span></td><td>{version.effective_from || "—"}<small>to {version.effective_to || "open"}</small></td><td>{version.approved_by_user_id || "Not approved"}<small>{version.approved_at || "—"}</small></td></tr>)}
            {thresholds.map((threshold) => { const metric = metrics.find((row) => row.id === threshold.metric_definition_id); return <tr key={`threshold-${threshold.id}`}><td>Threshold<small>{metric?.code || threshold.metric_definition_id}</small></td><td>{threshold.version}</td><td><span className={statusClass(threshold.status)}>{threshold.status}</span></td><td>{threshold.effective_from || "—"}<small>to {threshold.effective_to || "open"}</small></td><td>{threshold.approved_by_user_id || "Not approved"}<small>{threshold.approved_at || "—"}</small></td></tr>; })}
            {!versions.length && !thresholds.length && <tr><td colSpan={5}>No controlled programme or threshold versions are available.</td></tr>}
          </tbody></table></div>
        </div>
      )}
    </section>
  );
}
