import React, { useCallback, useEffect, useMemo, useState } from "react";

import {
  listReliabilityCalculationRuns,
  listReliabilityMetricDefinitions,
  type ReliabilityCalculationRun,
  type ReliabilityMetricDefinition,
} from "../../services/reliability";
import type { CalculationFormula } from "./reliabilityAnalyticsTypes";
import "./ReliabilityCalculationEvidence.css";

type FormulaSnapshot = CalculationFormula & {
  snapshot_provenance?: {
    mode?: string;
    source?: string;
    migration?: string;
  };
};

type PersistedCalculationRun = ReliabilityCalculationRun & {
  revision: number;
  formula_snapshot_json?: FormulaSnapshot;
  formula_snapshot_hash?: string;
};

type PersistedMetricDefinition = ReliabilityMetricDefinition & {
  formula_latex?: string;
  formula_mathml?: string;
  formula_expression_json?: Record<string, unknown>;
  formula_unit?: string;
  formula_precision?: number;
  formula_rounding_mode?: string;
  denominator_policy?: string;
  formula_source_fields_json?: string[];
};

function displayDate(value?: string | null): string {
  if (!value) return "—";
  const parsed = new Date(value);
  return Number.isNaN(parsed.getTime()) ? value : parsed.toLocaleString();
}

export function ReliabilityCalculationEvidence(): React.ReactElement {
  const [runs, setRuns] = useState<PersistedCalculationRun[]>([]);
  const [metrics, setMetrics] = useState<PersistedMetricDefinition[]>([]);
  const [selectedRunId, setSelectedRunId] = useState("");
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  const load = useCallback(async () => {
    setLoading(true);
    setError(null);
    try {
      const [runRows, metricRows] = await Promise.all([
        listReliabilityCalculationRuns(),
        listReliabilityMetricDefinitions(),
      ]);
      const governedRuns = runRows as PersistedCalculationRun[];
      setRuns(governedRuns);
      setMetrics(metricRows as PersistedMetricDefinition[]);
      setSelectedRunId((current) => current || governedRuns[0]?.id || "");
    } catch (caught: unknown) {
      setError(caught instanceof Error ? caught.message : "Calculation evidence could not be loaded.");
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => { void load(); }, [load]);

  const selectedRun = runs.find((run) => run.id === selectedRunId) || null;
  const selectedMetric = selectedRun ? metrics.find((metric) => metric.id === selectedRun.metric_definition_id) || null : null;
  const snapshot = selectedRun?.formula_snapshot_json;
  const reconstructed = snapshot?.snapshot_provenance?.mode === "MIGRATION_BACKFILL";
  const formulaHashMatches = useMemo(() => {
    if (!selectedRun?.formula_snapshot_hash || !selectedRun.source_lineage_json) return null;
    const lineageHash = selectedRun.source_lineage_json.formula_snapshot_hash;
    return typeof lineageHash === "string" ? lineageHash === selectedRun.formula_snapshot_hash : null;
  }, [selectedRun]);

  return (
    <section className="reliability-calculation-evidence" aria-labelledby="reliability-calculation-evidence-heading">
      <div className="reliability-formula-admin__heading">
        <div>
          <p className="reliability-v2__eyebrow">Immutable evidence</p>
          <h2 id="reliability-calculation-evidence-heading">Calculation formula snapshots</h2>
          <p>New executions retain the exact equation used. Historical rows migrated from the earlier schema are explicitly identified as controlled reconstructions from their metric definition and recorded formula version.</p>
        </div>
        <button type="button" className="btn btn-secondary" onClick={() => void load()} disabled={loading}>Refresh evidence</button>
      </div>

      {loading && <div className="reliability-v2__loading" role="status">Loading calculation snapshots…</div>}
      {error && <div className="reliability-v2__error" role="alert">{error}</div>}

      {!loading && runs.length > 0 && (
        <div className="reliability-calculation-evidence__layout">
          <div className="reliability-calculation-evidence__register">
            <label className="reliability-calculation-evidence__select">
              <span>Calculation run</span>
              <select value={selectedRunId} onChange={(event) => setSelectedRunId(event.target.value)}>
                {runs.map((run) => {
                  const metric = metrics.find((item) => item.id === run.metric_definition_id);
                  const mode = run.formula_snapshot_json?.snapshot_provenance?.mode === "MIGRATION_BACKFILL" ? " · reconstructed" : "";
                  return <option value={run.id} key={run.id}>{metric?.code || run.metric_definition_id} · {run.period_end} · r{run.revision}{mode}</option>;
                })}
              </select>
            </label>
            <div className="reliability-v2__table-wrap"><table className="reliability-v2__table"><thead><tr><th>Run</th><th>Period</th><th>Scope</th><th>Value</th><th>Formula</th><th>Snapshot hash</th></tr></thead><tbody>
              {runs.map((run) => {
                const metric = metrics.find((item) => item.id === run.metric_definition_id);
                const historical = run.formula_snapshot_json?.snapshot_provenance?.mode === "MIGRATION_BACKFILL";
                return <tr key={run.id} className={run.id === selectedRunId ? "is-selected" : ""} onClick={() => setSelectedRunId(run.id)}><td><button type="button" className="reliability-calculation-evidence__row-button" onClick={() => setSelectedRunId(run.id)}><strong>{metric?.code || run.metric_definition_id}</strong><small>{displayDate(run.created_at)}</small></button></td><td>{run.period_start} – {run.period_end}<small>Revision {run.revision}</small></td><td>{run.scope_type}<small>{run.scope_id}</small></td><td>{run.value ?? "—"}<small>{run.status}</small></td><td>v{run.formula_version}<small>{historical ? "Controlled reconstruction" : "Exact execution snapshot"}</small><small>{run.formula_snapshot_json?.unit || metric?.formula_unit || "—"}</small></td><td><code>{run.formula_snapshot_hash?.slice(0, 18) || "Missing"}</code></td></tr>;
              })}
            </tbody></table></div>
          </div>

          {selectedRun && (
            <article className="reliability-calculation-evidence__snapshot">
              <header>
                <div><p className="reliability-v2__eyebrow">Selected execution</p><h3>{snapshot?.name || selectedMetric?.name || "Calculation formula"}</h3><code>{snapshot?.code || selectedMetric?.code} · v{snapshot?.version || selectedRun.formula_version}</code></div>
                <span className={`reliability-calculation-evidence__integrity reliability-calculation-evidence__integrity--${formulaHashMatches === false ? "invalid" : reconstructed ? "reconstructed" : "valid"}`}>{formulaHashMatches === false ? "Hash mismatch" : reconstructed ? "Historical reconstruction" : "Exact snapshot retained"}</span>
              </header>

              {reconstructed && <div className="reliability-formula-admin__message" role="note">This run predates formula-snapshot storage. Its equation was reconstructed during migration from the controlled metric definition and the formula version recorded on the run; it is not represented as a contemporaneous snapshot.</div>}
              {snapshot?.mathml ? <div className="reliability-formula__math" dangerouslySetInnerHTML={{ __html: snapshot.mathml }} /> : <div className="reliability-analytics__empty"><strong>No formula snapshot</strong><span>This historical record requires migration backfill.</span></div>}
              <pre className="reliability-formula__latex">{snapshot?.latex || selectedMetric?.formula_latex || "No LaTeX retained"}</pre>

              <dl className="reliability-formula__definition">
                <div><dt>Numerator</dt><dd>{selectedRun.numerator ?? "—"}<small>{snapshot?.numerator_label}</small></dd></div>
                <div><dt>Denominator</dt><dd>{selectedRun.denominator ?? "—"}<small>{snapshot?.denominator_label || "Not applicable"}</small></dd></div>
                <div><dt>Calculated value</dt><dd>{selectedRun.value ?? "Withheld"}<small>{snapshot?.unit || selectedMetric?.formula_unit}</small></dd></div>
                <div><dt>Confidence interval</dt><dd>{selectedRun.confidence_lower ?? "—"} – {selectedRun.confidence_upper ?? "—"}<small>Sample size {selectedRun.sample_size}</small></dd></div>
                <div><dt>Precision</dt><dd>{snapshot?.precision ?? selectedMetric?.formula_precision ?? "—"}<small>{snapshot?.rounding_mode || selectedMetric?.formula_rounding_mode}</small></dd></div>
                <div><dt>Source cutoff</dt><dd>{displayDate(selectedRun.source_cutoff_at)}</dd></div>
              </dl>

              <div className="reliability-formula__method"><h4>Methodology</h4><p>{snapshot?.methodology || selectedMetric?.description || "—"}</p><h4>Denominator policy</h4><p>{snapshot?.denominator_policy || selectedMetric?.denominator_policy || "—"}</p></div>

              <details className="reliability-formula__details" open><summary>Formula snapshot identity</summary><dl className="reliability-calculation-evidence__hashes"><div><dt>Formula snapshot SHA-256</dt><dd><code>{selectedRun.formula_snapshot_hash || "Missing"}</code></dd></div><div><dt>Result SHA-256</dt><dd><code>{selectedRun.result_hash}</code></dd></div></dl></details>
              <details className="reliability-formula__details"><summary>Machine-readable expression</summary><pre>{JSON.stringify(snapshot?.expression || selectedMetric?.formula_expression_json || {}, null, 2)}</pre></details>
              <details className="reliability-formula__details"><summary>Source lineage</summary><pre>{JSON.stringify(selectedRun.source_lineage_json, null, 2)}</pre></details>
            </article>
          )}
        </div>
      )}

      {!loading && runs.length === 0 && <div className="reliability-analytics__empty"><strong>No calculation executions</strong><span>Run a governed metric calculation to create immutable formula evidence.</span></div>}
    </section>
  );
}
