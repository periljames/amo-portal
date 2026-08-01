import React from "react";
import { Activity, AlertTriangle } from "lucide-react";

import type { QmsOperationalDashboardResponse } from "../../../types/qms";
import { qmsTimestampLabel } from "../qmsOverviewModel";

type Props = {
  dashboard: QmsOperationalDashboardResponse;
  authorized: boolean;
};

const QmsDiagnosticsDrawer: React.FC<Props> = ({ dashboard, authorized }) => {
  if (!authorized) return null;
  const errors = dashboard.source_health.errors || [];

  return (
    <details className="qms-diagnostics">
      <summary><Activity size={15} aria-hidden="true" /> Support diagnostics</summary>
      <div className="qms-diagnostics__content">
        <dl className="qms-diagnostics__meta">
          <div><dt>Contract</dt><dd>{dashboard.contract}</dd></div>
          <div><dt>Generated</dt><dd>{qmsTimestampLabel(dashboard.data_freshness?.generated_at || dashboard.as_of)}</dd></div>
          <div><dt>Counter source</dt><dd>{dashboard.data_freshness?.counter_source || "Unavailable"}</dd></div>
          <div><dt>Trace ID</dt><dd><code>{dashboard.trace_id || "Unavailable"}</code></dd></div>
          <div><dt>Backend duration</dt><dd>{dashboard.elapsed_ms == null ? "Unavailable" : `${dashboard.elapsed_ms} ms`}</dd></div>
          <div><dt>Source state</dt><dd>{dashboard.source_health.status}</dd></div>
        </dl>

        {dashboard.period_comparisons?.note ? <p className="qms-diagnostics__note">{dashboard.period_comparisons.note}</p> : null}

        {errors.length ? (
          <div className="qms-diagnostics__errors">
            <strong><AlertTriangle size={15} aria-hidden="true" /> Source errors</strong>
            <ul>
              {errors.map((error, index) => (
                <li key={`${error.label}-${index}`}><b>{error.label}</b>: {error.message}</li>
              ))}
            </ul>
          </div>
        ) : <p className="qms-diagnostics__healthy">No source errors were returned.</p>}
      </div>
    </details>
  );
};

export default QmsDiagnosticsDrawer;
