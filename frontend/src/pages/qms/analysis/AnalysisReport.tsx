import { renderToStaticMarkup } from "react-dom/server";
import { useState } from "react";
import type { AnalysisSnapshot, AnalysisSource } from "../../../services/qmsAnalysis";
import type { QmsAssuranceCase } from "../../../services/qmsAssuranceCases";
import type { DocumentationAssistResponse } from "../../../services/documentationAssistant";
import { saveDownloadedFile } from "../../../utils/downloads";
import { AnalysisMarkdown } from "./AnalysisEditor";

type Props = { tenant: string; data: AnalysisSnapshot; selected: AnalysisSource[]; study?: QmsAssuranceCase; references: Record<string, unknown>[]; answer: DocumentationAssistResponse | null };
export function csvCell(value: unknown) {
  const text = String(value ?? "");
  return `"${(/^[\s]*[=+@\-\t\r]/.test(text) ? "'" : "") + text.replaceAll('"', '""')}"`;
}
function ReportBody({ tenant, data, selected, study, references, answer }: Props) {
  return <article className="qa-analysis-report">
    <header><p>QUALITY ASSURANCE · ANALYST WORKING REPORT</p><h1>{study?.title || "Quality assurance analysis"}</h1><p>Tenant: {tenant} · Retrieved: {new Date(data.generated_at).toLocaleString()}</p></header>
    <h2>Scope and provenance</h2><p>{data.population}</p><p>Period: {data.filters.start} to {data.filters.end} inclusive (UTC). Severity: {data.filters.severity || "All"}. Type: {data.filters.finding_type || "All"}. Requirement: {data.filters.requirement || "All"}.</p>
    <p>Metrics cover the complete filtered population. The evidence appendix contains {selected.length} analyst-selected findings, not the complete register. This is a retrieval-time working report, not an attested immutable regulatory record.</p>
    <h2>Quantitative results</h2><table><thead><tr><th>Measure</th><th>Value</th><th>Definition / denominator</th></tr></thead><tbody>
      <tr><td>Findings</td><td>{data.total}</td><td>Distinct finding records in the cohort</td></tr><tr><td>Open findings</td><td>{data.open}</td><td>No recorded closure timestamp</td></tr>
      <tr><td>Missing objective evidence</td><td>{data.missing_evidence}</td><td>Empty objective-evidence field; attachments are not evaluated</td></tr><tr><td>Missing requirement</td><td>{data.missing_requirement}</td><td>Empty recorded requirement reference</td></tr>
      <tr><td>Linked QUALITY CARs</td><td>{data.cars.total}</td><td>CAR records linked to cohort findings; several may link to one finding</td></tr><tr><td>Overdue CARs</td><td>{data.cars.overdue}</td><td>Past target closure date (else due date), excluding closed/cancelled</td></tr>
      <tr><td>On-time closure</td><td>{data.cars.measurable ? `${(data.cars.on_time / data.cars.measurable * 100).toFixed(1)}%` : "N/A"}</td><td>{data.cars.on_time} / {data.cars.measurable} closed CARs with both closure timestamp and due date. {data.cars.closed - data.cars.measurable} closed CARs excluded for missing dates.</td></tr>
    </tbody></table>
    {([["Severity", data.severity], ["Finding type", data.types], ["Requirement counts (top 30)", data.requirements], ["Monthly finding counts", data.trend]] as const).map(([title, rows]) => <section key={title}><h3>{title}</h3><table><thead><tr><th>Category / month</th><th>Count</th></tr></thead><tbody>{rows.map(row => <tr key={row.name}><td>{row.name}{"partial" in row && row.partial ? " (partial month)" : ""}</td><td>{row.count}</td></tr>)}</tbody></table></section>)}
    <p>Requirement groups beyond the top 30 contain {data.requirement_tail} findings. Counts are not normalised for audit effort or operational exposure. No causality, control limits, predicted performance or compliance score is inferred.</p>
    <h2>Qualitative analysis</h2>{study ? <><p>Assurance case {study.case_ref} · {study.status}</p>{study.investigation_entries?.map(entry => <section key={entry.id}><h3>{entry.sequence_no}. {entry.category || entry.method} · {entry.entry_type}</h3><small>{entry.method} · author {entry.created_by_user_id || "Unrecorded"} · {entry.created_at}</small><AnalysisMarkdown text={entry.statement} /><pre>{JSON.stringify(entry.evidence_references, null, 2)}</pre></section>)}</> : <p>No saved investigation selected.</p>}
    <h2>Selected finding evidence</h2>{selected.map(source => <section key={source.id}><h3>{source.reference} · {source.severity}</h3><p>{source.description}</p><p>Requirement: {source.requirement || "Unrecorded"}</p><p>Objective evidence: {source.objective_evidence || "Unrecorded"}</p><small>Finding ID {source.id} · audit {source.audit_reference} ({source.audit_id}) · created {source.created_at}</small></section>)}
    <h2>Document and attachment references</h2><pre>{JSON.stringify(references.filter(ref => ref.type !== "QMS_FINDING"), null, 2)}</pre>
    {answer && <section><h2>{answer.provider_mode === "OPENAI" ? "AI-assisted documentation suggestion — unreviewed" : "Deterministic documentation response"}</h2><p>Question: {answer.query}</p><AnalysisMarkdown text={answer.answer} /><p>{answer.warning}</p><p>Citations: {answer.citations.join(", ") || "None"}</p><pre>{JSON.stringify(answer.sources, null, 2)}</pre></section>}
    <footer>Quality principles and analyst mappings do not establish compliance. Verify the applicable controlled standard, edition, requirements and source evidence before approval.</footer>
  </article>;
}
export default function AnalysisReport(props: Props & { canExport: boolean }) {
  const name = `quality-analysis-${props.data.filters.end}`;
  const downloadHtml = async () => {
    const content = renderToStaticMarkup(<ReportBody {...props} />);
    const html = `<!doctype html><html lang="en"><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1"><title>Quality analysis</title><style>body{font:14px/1.6 system-ui;max-width:1050px;margin:32px auto;padding:0 24px;color:#17212e}table{border-collapse:collapse;width:100%;margin:20px 0}td,th{border:1px solid #ccd3dd;padding:8px;text-align:left}pre{white-space:pre-wrap;overflow-wrap:anywhere;font-size:11px}section{break-inside:avoid}footer{margin-top:32px;border-top:1px solid #ccd3dd;padding-top:16px}@media print{body{margin:0;max-width:none}}</style><body>${content}</body></html>`;
    await saveDownloadedFile(new Blob([html], { type: "text/html;charset=utf-8" }), `${name}.html`);
  };
  const downloadCsv = async () => {
    const rows: unknown[][] = [["Tenant", props.tenant], ["Retrieved UTC", props.data.generated_at], ["Population", props.data.population], ["Filters", JSON.stringify(props.data.filters)], ["Measure", "Category", "Count"]];
    for (const [measure, values] of [["Severity", props.data.severity], ["Finding type", props.data.types], ["Requirement", props.data.requirements], ["Month", props.data.trend]] as const) for (const row of values) rows.push([measure, row.name, row.count]);
    rows.push(["Requirements", "Remaining groups", props.data.requirement_tail]);
    await saveDownloadedFile(new Blob(["\ufeff" + rows.map(row => row.map(csvCell).join(",")).join("\r\n")], { type: "text/csv;charset=utf-8" }), `${name}-aggregates.csv`);
  };
  const [error, setError] = useState("");
  const run = async (action: () => Promise<unknown> | unknown) => { setError(""); try { await action(); } catch (caught) { setError(caught instanceof Error ? caught.message : "Export failed."); } };
  return <section className="qa-analysis-card"><div className="qa-analysis-actions qa-analysis-report-actions">
    <button disabled={!props.canExport} onClick={() => void run(downloadHtml)}>Download formatted report</button>
    <button disabled={!props.canExport} onClick={() => void run(downloadCsv)}>Export aggregate CSV</button>
    <button disabled={!props.canExport} onClick={() => { document.documentElement.classList.add("qa-analysis-print"); const cleanup = () => document.documentElement.classList.remove("qa-analysis-print"); window.addEventListener("afterprint", cleanup, { once: true }); window.print(); }}>Print / Save PDF</button>
    <button disabled={!props.canExport} onClick={() => void run(() => saveDownloadedFile(new Blob([JSON.stringify({ ...props, canExport: undefined }, null, 2)], { type: "application/json" }), `${name}-evidence.json`))}>Download evidence JSON</button>
  </div>{!props.canExport && <p>Report export requires qms.reports.export permission.</p>}{error && <p role="alert">{error}</p>}<ReportBody {...props} /></section>;
}
