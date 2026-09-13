import React from "react";
export type QmsSourceWarning = { source: string; message: string; type: string };

/** Shared source honesty; operational pages retain their own metrics and layout. */
export function SourceHealthNotice({ warnings, asOf }: { warnings: QmsSourceWarning[]; asOf?: string }) {
  return <div className="qms-source-health">
    {asOf ? <small>As of <time dateTime={asOf}>{new Date(asOf).toLocaleString()}</time></small> : null}
    {warnings.length ? <details className="assurance-source-warnings" open>
      <summary>{warnings.length} source warning{warnings.length === 1 ? "" : "s"}</summary>
      <p role="status">Available records are shown. Missing data is not evidence of no exposure.</p>
      <ul>{warnings.map((warning, index) => <li key={`${warning.source}-${index}`}><strong>{warning.source.replaceAll("_", " ")}</strong>: {warning.message}</li>)}</ul>
    </details> : null}
  </div>;
}
