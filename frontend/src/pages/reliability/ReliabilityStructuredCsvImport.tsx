import React, { useMemo, useState } from "react";

import { apiRequest } from "../../services/apiClient";
import { authHeaders } from "../../services/auth";
import { getApiBaseUrl } from "../../services/config";
import type { WorkbookDatasetCode, WorkbookFieldDefinition, WorkbookImportCommitResult, WorkbookImportPreview } from "./reliabilityWorkbookParityTypes";
import { DATASET_ORDER } from "./reliabilityWorkbookParityTypes";

const ROOT = "/reliability/workbook-parity";

async function downloadTemplate(datasetCode: WorkbookDatasetCode): Promise<void> {
  const response = await fetch(`${getApiBaseUrl()}${ROOT}/imports/csv-template?dataset_code=${encodeURIComponent(datasetCode)}`, {
    headers: authHeaders({ Accept: "text/csv" }),
  });
  if (!response.ok) throw new Error(`CSV template could not be downloaded (${response.status}).`);
  const blob = await response.blob();
  const url = URL.createObjectURL(blob);
  const anchor = document.createElement("a");
  anchor.href = url;
  anchor.download = `reliability-${datasetCode.toLowerCase()}-template.csv`;
  anchor.click();
  window.setTimeout(() => URL.revokeObjectURL(url), 0);
}

async function previewCsv(input: { file: File; datasetCode: WorkbookDatasetCode; delimiter: string }): Promise<WorkbookImportPreview> {
  const body = new FormData();
  body.set("dataset_code", input.datasetCode);
  body.set("header_row", "1");
  if (input.delimiter) body.set("delimiter", input.delimiter);
  body.set("source", input.file, input.file.name);
  return apiRequest<WorkbookImportPreview>(`${ROOT}/imports/csv-preview`, { method: "POST", body, timeoutMs: 120_000 });
}

async function commitCsv(batchId: number): Promise<WorkbookImportCommitResult> {
  return apiRequest<WorkbookImportCommitResult>(`${ROOT}/imports/${batchId}/commit`, {
    method: "POST",
    body: JSON.stringify({ chunk_size: 100 }),
    timeoutMs: 120_000,
  });
}

export function ReliabilityStructuredCsvImport({ catalog }: { catalog: WorkbookFieldDefinition[] }): React.ReactElement {
  const [datasetCode, setDatasetCode] = useState<WorkbookDatasetCode>("AU");
  const [delimiter, setDelimiter] = useState("");
  const [file, setFile] = useState<File | null>(null);
  const [preview, setPreview] = useState<WorkbookImportPreview | null>(null);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [notice, setNotice] = useState<string | null>(null);
  const definition = useMemo(() => catalog.find((item) => item.code === datasetCode), [catalog, datasetCode]);

  const audit = async (event: React.FormEvent) => {
    event.preventDefault();
    if (!file) {
      setError("Select a CSV or TSV file before previewing the controlled intake.");
      return;
    }
    setLoading(true);
    setError(null);
    setNotice(null);
    try {
      const result = await previewCsv({ file, datasetCode, delimiter });
      setPreview(result);
      setNotice(`${result.valid_rows} row(s) passed validation and ${result.invalid_rows} require correction. Nothing authoritative has been approved yet.`);
    } catch (caught: unknown) {
      setError(caught instanceof Error ? caught.message : "The structured CSV could not be previewed.");
    } finally {
      setLoading(false);
    }
  };

  const commit = async () => {
    if (!preview) return;
    setLoading(true);
    setError(null);
    try {
      const result = await commitCsv(preview.id);
      setPreview((current) => current ? { ...current, ...result } : current);
      setNotice(`${result.processed} row(s) were committed as controlled DRAFT records. Quality approval remains separate.`);
    } catch (caught: unknown) {
      setError(caught instanceof Error ? caught.message : "The CSV rows could not be committed.");
    } finally {
      setLoading(false);
    }
  };

  return <section className="rel-wp__panel rel-wp__span-all" aria-labelledby="reliability-csv-import-heading">
    <div className="rel-wp__section-heading">
      <div>
        <p className="rel-wp__eyebrow">Preferred structured intake</p>
        <h2 id="reliability-csv-import-heading">Structured CSV / TSV import</h2>
        <p>Use one canonical template for any of the 16 Reliability domains. The portal validates every row, retains hashes and creates drafts only—no spreadsheet formulas, macros or hidden-sheet behaviour.</p>
      </div>
      <span>UTF-8 · 25 MiB · 10,000 rows</span>
    </div>
    {error && <div className="rel-wp__error" role="alert">{error}</div>}
    {notice && <div className="rel-wp__notice" role="status">{notice}</div>}
    <form className="rel-wp__form" onSubmit={audit}>
      <div className="rel-wp__form-grid">
        <label>Reliability domain<select value={datasetCode} onChange={(event) => { setDatasetCode(event.target.value as WorkbookDatasetCode); setPreview(null); }}>
          {DATASET_ORDER.map((code) => <option key={code} value={code}>{code} — {catalog.find((item) => item.code === code)?.name || code}</option>)}
        </select></label>
        <label>Delimiter<select value={delimiter} onChange={(event) => setDelimiter(event.target.value)}><option value="">Auto detect</option><option value="comma">Comma</option><option value="semicolon">Semicolon</option><option value="tab">Tab</option><option value="pipe">Pipe</option></select></label>
        <label className="rel-wp__span-2">CSV / TSV file<input type="file" accept=".csv,.tsv,text/csv,text/tab-separated-values" onChange={(event) => { setFile(event.target.files?.[0] || null); setPreview(null); }} /><small>Use UTF-8. Dates should use ISO YYYY-MM-DD. Decimal values remain exact strings until governed conversion.</small></label>
      </div>
      <div className="rel-wp__form-actions">
        <button type="button" className="btn btn-secondary" onClick={() => void downloadTemplate(datasetCode).catch((caught: unknown) => setError(caught instanceof Error ? caught.message : "Template download failed."))}>Download {datasetCode} template</button>
        <button type="submit" className="btn btn-primary" disabled={loading}>{loading ? "Auditing…" : "Audit and preview CSV"}</button>
      </div>
    </form>
    <div className="rel-wp__source-provenance">
      <strong>{definition?.name || datasetCode}</strong>
      <span> Required fields: {definition?.fields.filter((field) => field.required).map((field) => field.label).join(", ") || "See template"}</span>
    </div>
    {preview && <>
      <div className="rel-wp__metric-strip rel-wp__metric-strip--compact">
        <div><span>Total rows</span><strong>{preview.total_rows}</strong></div>
        <div><span>Valid queue</span><strong>{preview.valid_rows}</strong></div>
        <div><span>Invalid</span><strong>{preview.invalid_rows}</strong></div>
        <div><span>Committed drafts</span><strong>{preview.committed_rows}</strong></div>
      </div>
      <dl className="rel-wp__provenance">
        <div><dt>Source SHA-256</dt><dd><code>{preview.source_hash}</code></dd></div>
        <div><dt>Header mapping</dt><dd>{Object.entries(preview.header_map).map(([column, field]) => `${column}→${field}`).join(" · ")}</dd></div>
      </dl>
      <div className="rel-wp__form-actions"><button type="button" className="btn btn-primary" disabled={loading || preview.valid_rows === 0} onClick={() => void commit()}>Commit next 100 controlled drafts</button></div>
      <div className="rel-wp__table-wrap"><table className="rel-wp__table" aria-label="Structured CSV preview"><thead><tr><th>Row</th><th>Status</th><th>Aircraft</th><th>Date</th><th>Reference</th><th>Errors</th><th>Row SHA-256</th></tr></thead><tbody>
        {preview.preview_rows.map((row) => {
          const mapped = row.mapped_values as Record<string, unknown>;
          return <tr key={row.id}><td>{row.row_number}</td><td>{row.status}</td><td>{String(mapped.aircraft_serial_number || "Fleet")}</td><td>{String(mapped.event_date || "—")}</td><td>{String(mapped.reference_code || "—")}</td><td>{row.errors.join(" ") || "—"}</td><td><code>{row.row_source_hash.slice(0, 16)}…</code></td></tr>;
        })}
      </tbody></table></div>
    </>}
  </section>;
}
