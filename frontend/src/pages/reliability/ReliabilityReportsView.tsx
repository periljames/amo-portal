import React, { useEffect, useMemo, useRef, useState } from "react";

import {
  createReliabilityReport,
  downloadFracasEvidencePack,
  downloadReliabilityReport,
  listReliabilityReports,
  type ReliabilityReportRead,
  type TransferProgress,
} from "../../services/reliability";
import { saveDownloadedFile } from "../../utils/downloads";

type DownloadState = { reportId: number; progress: TransferProgress };

const ReliabilityReportsView: React.FC = () => {
  const [reports, setReports] = useState<ReliabilityReportRead[]>([]);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [windowStart, setWindowStart] = useState("");
  const [windowEnd, setWindowEnd] = useState("");
  const [creating, setCreating] = useState(false);
  const [downloadProgress, setDownloadProgress] = useState<DownloadState | null>(null);
  const [fracasCaseId, setFracasCaseId] = useState("");
  const [fracasExporting, setFracasExporting] = useState(false);
  const loadingRef = useRef(false);
  const hasPending = useMemo(() => reports.some((report) => report.status === "PENDING"), [reports]);

  useEffect(() => {
    const today = new Date();
    const start = new Date(today);
    start.setDate(today.getDate() - 30);
    setWindowStart(start.toISOString().slice(0, 10));
    setWindowEnd(today.toISOString().slice(0, 10));
  }, []);

  const loadReports = async (force = false) => {
    if (loadingRef.current) return;
    loadingRef.current = true;
    setLoading(true);
    setError(null);
    try {
      setReports(await listReliabilityReports({ force }));
    } catch (caught: unknown) {
      setError(caught instanceof Error ? caught.message : "Could not load reliability reports.");
    } finally {
      loadingRef.current = false;
      setLoading(false);
    }
  };

  useEffect(() => { void loadReports(true); }, []);
  useEffect(() => {
    if (!hasPending) return;
    const interval = window.setInterval(() => { void loadReports(true); }, 8000);
    return () => window.clearInterval(interval);
  }, [hasPending]);

  const generate = async () => {
    if (!windowStart || !windowEnd) {
      setError("Choose both a start and end date.");
      return;
    }
    setCreating(true);
    setError(null);
    try {
      await createReliabilityReport(windowStart, windowEnd);
      await loadReports(true);
    } catch (caught: unknown) {
      setError(caught instanceof Error ? caught.message : "Could not generate the reliability report.");
    } finally {
      setCreating(false);
    }
  };

  const download = async (report: ReliabilityReportRead) => {
    setError(null);
    try {
      const file = await downloadReliabilityReport(report.id, (progress) => setDownloadProgress({ reportId: report.id, progress }));
      saveDownloadedFile(file);
    } catch (caught: unknown) {
      setError(caught instanceof Error ? caught.message : "Could not download the reliability report.");
    } finally {
      setDownloadProgress(null);
    }
  };

  const exportFracas = async () => {
    const caseId = Number(fracasCaseId);
    if (!Number.isInteger(caseId) || caseId <= 0) {
      setError("Enter a valid FRACAS case ID.");
      return;
    }
    setFracasExporting(true);
    setError(null);
    try {
      saveDownloadedFile(await downloadFracasEvidencePack(caseId));
    } catch (caught: unknown) {
      setError(caught instanceof Error ? caught.message : "Could not export the FRACAS evidence pack.");
    } finally {
      setFracasExporting(false);
    }
  };

  return <>
    {error && <div className="reliability-v2__error" role="alert">{error}</div>}
    <div className="reliability-v2__split">
      <section className="reliability-v2__section">
        <p className="reliability-v2__eyebrow">Controlled output</p>
        <h2>Generate reliability report</h2>
        <div className="reliability-v2__form-grid">
          <label><span>Window start</span><input type="date" value={windowStart} onChange={(event) => setWindowStart(event.target.value)} /></label>
          <label><span>Window end</span><input type="date" value={windowEnd} onChange={(event) => setWindowEnd(event.target.value)} /></label>
        </div>
        <button type="button" className="btn btn-primary" onClick={() => void generate()} disabled={creating}>{creating ? "Generating…" : "Generate controlled report"}</button>
        {hasPending && <p className="reliability-v2__lead">A report is being generated. This register refreshes automatically.</p>}
      </section>
      <section className="reliability-v2__section">
        <p className="reliability-v2__eyebrow">Case evidence</p>
        <h2>FRACAS evidence pack</h2>
        <label className="reliability-v2__single-field"><span>Case ID</span><input type="number" value={fracasCaseId} onChange={(event) => setFracasCaseId(event.target.value)} /></label>
        <button type="button" className="btn btn-secondary" onClick={() => void exportFracas()} disabled={fracasExporting}>{fracasExporting ? "Exporting…" : "Export evidence pack"}</button>
      </section>
    </div>
    <section className="reliability-v2__section">
      <div className="reliability-v2__section-heading"><div><p className="reliability-v2__eyebrow">Retained outputs</p><h2>Report register</h2></div><span>{reports.length} reports</span></div>
      {loading ? <p>Loading reports…</p> : <div className="reliability-v2__table-wrap"><table className="reliability-v2__table"><thead><tr><th>ID</th><th>Window</th><th>Status</th><th>Created</th><th>Output</th></tr></thead><tbody>
        {reports.map((report) => <tr key={report.id}><td>{report.id}</td><td>{report.window_start} → {report.window_end}</td><td>{report.status}</td><td>{new Date(report.created_at).toLocaleString()}</td><td><button type="button" className="btn btn-secondary" disabled={report.status !== "READY"} onClick={() => void download(report)}>Download</button>{downloadProgress?.reportId === report.id && <small>{downloadProgress.progress.percent?.toFixed(0) ?? 0}%</small>}</td></tr>)}
        {reports.length === 0 && <tr><td colSpan={5}>No reports have been generated.</td></tr>}
      </tbody></table></div>}
    </section>
  </>;
};

export default ReliabilityReportsView;
