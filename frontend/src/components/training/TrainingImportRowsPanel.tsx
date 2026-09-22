import React, { useEffect, useRef, useState } from "react";
import { listTrainingWorkbookImportRows } from "../../services/trainingWorkbookImport";
import type { TrainingWorkbookImportJob, TrainingWorkbookImportRowPage } from "../../types/trainingWorkbookImport";
import { copyTextToClipboard } from "../../utils/clipboard";

export type ImportOutcome = "CREATE" | "UPDATE" | "UNCHANGED" | "REVIEW" | "SKIPPED" | "FAILED";
export const decisionLabels: Record<string, string> = {
  CREATE_ACCOUNT: "Create inactive account for onboarding",
  LINK_EXISTING_ACCOUNT: "Link existing account",
  PROFILE_ONLY: "Keep personnel record without portal access",
  SKIP: "Skip this row",
  KEEP_EXISTING_EMAIL: "Keep existing email",
};

export function issueGuidance(code?: string | null): string {
  if (code?.includes("PERSON_ROLE")) return "Check PersonID and RoleGroup against People and tblRoleGroups, then upload the corrected workbook.";
  if (code?.includes("TRAINING")) return "Check the person, course and completion date. Remove repeated entries, then upload the corrected workbook.";
  if (code?.includes("IDENTITY") || code?.includes("PERSON") || code?.includes("ACCOUNT")) {
    return "Review the personnel identity and email before selecting a decision.";
  }
  return "Correct the source row and upload again, or recheck after updating the personnel or course catalogue.";
}

function CopyChip({ value, label }: { value?: string | null; label?: string }) {
  const [copied, setCopied] = useState(false);
  if (!value) return null;
  return (
    <button
      type="button"
      className="training-import-copy-chip"
      title={`Copy ${label || value}`}
      onClick={() => {
        void copyTextToClipboard(value).then((ok) => {
          if (!ok) return;
          setCopied(true);
          window.setTimeout(() => setCopied(false), 1600);
        });
      }}
    >
      {copied ? "Copied" : label || value}
    </button>
  );
}

export default function TrainingImportRowsPanel({
  job,
  outcome,
  decisions,
  onDecision,
  support = false,
  canManage = true,
  scrollToken = 0,
}: {
  job: TrainingWorkbookImportJob;
  outcome: ImportOutcome;
  decisions: Record<string, string>;
  onDecision: (id: string, value: string) => void;
  support?: boolean;
  canManage?: boolean;
  scrollToken?: number;
}) {
  const [page, setPage] = useState<TrainingWorkbookImportRowPage | null>(null);
  const [query, setQuery] = useState("");
  const [sheet, setSheet] = useState("");
  const [offset, setOffset] = useState(0);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState("");
  const panel = useRef<HTMLElement>(null);
  const limit = 50;
  const operationalSheets = job.sheets.filter((item) => item.is_operational && item.total_rows > 0);

  useEffect(() => {
    setOffset(0);
    setQuery("");
    setSheet("");
  }, [job.id, outcome]);

  useEffect(() => {
    let active = true;
    setLoading(true);
    const timer = window.setTimeout(() => {
      void listTrainingWorkbookImportRows(job.id, { outcome, q: query, sheet, limit, offset }, support)
        .then((result) => {
          if (active) {
            setPage(result);
            setError("");
          }
        })
        .catch((err: unknown) => {
          if (active) setError(err instanceof Error ? err.message : "Could not load rows.");
        })
        .finally(() => {
          if (active) setLoading(false);
        });
    }, query ? 250 : 0);
    return () => {
      active = false;
      window.clearTimeout(timer);
    };
  }, [job.id, job.status, outcome, query, sheet, offset, support]);

  useEffect(() => {
    const node = panel.current;
    const shell = node?.closest(".training-import-shell") as HTMLElement | null;
    if (!node || !shell) return;
    const frame = window.requestAnimationFrame(() => {
      const delta = node.getBoundingClientRect().top - shell.getBoundingClientRect().top - 8;
      if (Math.abs(delta) > 24) {
        shell.scrollTo({ top: Math.max(0, shell.scrollTop + delta), behavior: "smooth" });
      }
    });
    return () => window.cancelAnimationFrame(frame);
  }, [outcome, job.id, scrollToken, page?.total]);

  return (
    <section
      ref={panel}
      className="training-import-section training-import-results"
      role="tabpanel"
      id="import-results"
      aria-label={`${outcome.toLowerCase()} rows`}
      aria-busy={loading}
    >
      <div className="training-import-section__header">
        <div>
          <h4>
            {outcome === "REVIEW"
              ? "Personnel and conflict review"
              : `${outcome.charAt(0)}${outcome.slice(1).toLowerCase()} records`}
          </h4>
          <p>
            {outcome === "FAILED"
              ? "These rows were not imported. Each issue identifies the source row to correct."
              : outcome === "REVIEW"
                ? "Resolve each decision before committing. New accounts remain inactive until onboarding."
                : "Records matching this outcome, across operational worksheets only."}
          </p>
        </div>
      </div>
      <div className="training-import-filterbar">
        <label>
          <input
            aria-label="Search import rows"
            placeholder="Search name, code or issue"
            value={query}
            onChange={(event) => {
              setQuery(event.target.value);
              setOffset(0);
            }}
          />
        </label>
        <select
          aria-label="Filter by worksheet"
          value={sheet}
          onChange={(event) => {
            setSheet(event.target.value);
            setOffset(0);
          }}
        >
          <option value="">All operational sheets</option>
          {operationalSheets.map((item) => (
            <option key={item.id} value={item.sheet_name}>
              {item.sheet_name}
            </option>
          ))}
        </select>
      </div>
      {error ? <p role="alert">{error}</p> : null}
      {loading ? (
        <p role="status">Loading records…</p>
      ) : (
        <>
          <div className="training-import-table-wrap">
            <table className="training-import-table">
              <thead>
                <tr>
                  <th>Workbook row</th>
                  <th>Record</th>
                  <th>{outcome === "FAILED" ? "Issue and next step" : "Details"}</th>
                  {outcome === "REVIEW" ? <th>Decision</th> : null}
                </tr>
              </thead>
              <tbody>
                {page?.items.map((row) => (
                  <tr key={row.id}>
                    <td>
                      <strong>{row.sheet_name}</strong>
                      <small>Row {row.source_row}</small>
                    </td>
                    <td>
                      <strong>{row.display_label || row.source_key || "Record"}</strong>
                      <div className="training-import-code-row">
                        <CopyChip value={row.source_key} label={row.source_key || undefined} />
                      </div>
                    </td>
                    <td>
                      <div className="training-import-issue-block">
                        {row.issue_code ? <CopyChip value={row.issue_code} label={row.issue_code} /> : null}
                        <span>{row.issue_message || row.proposed_action.toLowerCase()}</span>
                        {outcome === "FAILED" ? <small>{issueGuidance(row.issue_code)}</small> : null}
                      </div>
                    </td>
                    {outcome === "REVIEW" ? (
                      <td>
                        <select
                          aria-label={`Decision for ${row.display_label || row.source_key || row.source_row}`}
                          value={decisions[row.id] ?? row.decision ?? ""}
                          disabled={!canManage || !["PREVIEW_READY", "REVIEW_REQUIRED", "FAILED"].includes(job.status)}
                          onChange={(event) => onDecision(row.id, event.target.value)}
                        >
                          <option value="">Select decision</option>
                          {row.decision_options.map((value) => (
                            <option key={value} value={value}>
                              {decisionLabels[value] || value.replaceAll("_", " ").toLowerCase()}
                            </option>
                          ))}
                        </select>
                      </td>
                    ) : null}
                  </tr>
                ))}
              </tbody>
            </table>
            {page?.items.length === 0 ? <p className="training-import-empty">No matching records.</p> : null}
          </div>
          <div className="training-import-pagination">
            <span>
              {page?.total ? `${offset + 1}–${Math.min(offset + limit, page.total)} of ${page.total.toLocaleString()}` : "0 records"}
            </span>
            <button type="button" className="secondary-chip-btn" disabled={offset === 0} onClick={() => setOffset(Math.max(0, offset - limit))}>
              Previous
            </button>
            <button
              type="button"
              className="secondary-chip-btn"
              disabled={!page || offset + limit >= page.total}
              onClick={() => setOffset(offset + limit)}
            >
              Next
            </button>
          </div>
        </>
      )}
    </section>
  );
}
