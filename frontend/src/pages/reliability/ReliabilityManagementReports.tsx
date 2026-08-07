import React, { useEffect, useMemo, useRef, useState } from "react";
import { useLocation, useNavigate, useParams } from "react-router-dom";

import { apiRequest } from "../../services/apiClient";
import { authHeaders } from "../../services/auth";
import { getApiBaseUrl } from "../../services/config";
import { DATASET_ORDER, type WorkbookDatasetCode } from "./reliabilityWorkbookParityTypes";

const ROOT = "/reliability/workbook-parity";

type ManagementSnapshot = {
  id: number;
  layout_code: string;
  layout_name: string;
  period_start: string;
  period_end: string;
  aircraft: string[];
  sha256_hash: string;
  generated_at: string;
  view_url: string;
  pdf_url: string;
  data_url: string;
};

type SnapshotData = {
  id: number;
  layout_code: string;
  layout_name: string;
  period_start: string;
  period_end: string;
  aircraft: string[];
  sha256_hash: string;
  generated_at: string;
};

const DOMAIN_PRESETS: Array<{ label: string; codes: WorkbookDatasetCode[] }> = [
  { label: "Full programme", codes: [...DATASET_ORDER] },
  { label: "Utilisation & operations", codes: ["AU", "AI", "FI", "PM", "OOS", "ADD"] },
  { label: "Maintenance & recurring", codes: ["PM", "SM", "STRUCTURES", "RECURRING", "ADD"] },
  { label: "Components & shop", codes: ["RM", "SR", "UR"] },
  { label: "Engineering & configuration", codes: ["SB", "AS", "STRUCTURES", "ECTM"] },
  { label: "Cost & performance", codes: ["CS", "AU", "FI", "OOS", "RM"] },
];

function iso(value: Date): string { return value.toISOString().slice(0, 10); }
function startOfMonth(value: Date): Date { return new Date(value.getFullYear(), value.getMonth(), 1); }
function endOfMonth(value: Date): Date { return new Date(value.getFullYear(), value.getMonth() + 1, 0); }
function startOfWeek(value: Date): Date { const result = new Date(value); const offset = (result.getDay() + 6) % 7; result.setDate(result.getDate() - offset); return result; }
function endOfWeek(value: Date): Date { const result = startOfWeek(value); result.setDate(result.getDate() + 6); return result; }
function today(): string { return iso(new Date()); }
function daysAgo(days: number): string { const value = new Date(); value.setDate(value.getDate() - Math.max(0, days - 1)); return iso(value); }

async function renderManagementReport(payload: Record<string, unknown>): Promise<ManagementSnapshot> {
  return apiRequest<ManagementSnapshot>(`${ROOT}/management-reports/render`, { method: "POST", body: JSON.stringify(payload), timeoutMs: 120_000 });
}
async function readHtml(id: number): Promise<string> {
  return apiRequest<string>(`${ROOT}/reports/${id}/view`, { headers: { Accept: "text/html" }, cacheTtlMs: 0 });
}
async function readSnapshotData(id: number): Promise<SnapshotData> {
  return apiRequest<SnapshotData>(`${ROOT}/reports/${id}/data`, { cacheTtlMs: 0 });
}
async function downloadPdf(id: number, filename: string): Promise<void> {
  const response = await fetch(`${getApiBaseUrl()}${ROOT}/reports/${id}/pdf`, { headers: authHeaders({ Accept: "application/pdf" }) });
  if (!response.ok) throw new Error(`Controlled PDF could not be generated (${response.status}).`);
  const blob = await response.blob();
  const url = URL.createObjectURL(blob);
  const anchor = document.createElement("a");
  anchor.href = url;
  anchor.download = filename;
  anchor.click();
  window.setTimeout(() => URL.revokeObjectURL(url), 0);
}

export function ReliabilityManagementReports(): React.ReactElement {
  const { amoCode = "UNKNOWN" } = useParams<{ amoCode?: string }>();
  const location = useLocation();
  const navigate = useNavigate();
  const iframeRef = useRef<HTMLIFrameElement | null>(null);
  const current = new Date();
  const [periodStart, setPeriodStart] = useState(daysAgo(30));
  const [periodEnd, setPeriodEnd] = useState(today());
  const [bucket, setBucket] = useState<"AUTO" | "DAY" | "WEEK" | "MONTH">("AUTO");
  const [reportYear, setReportYear] = useState(current.getFullYear());
  const [aircraftText, setAircraftText] = useState("");
  const [title, setTitle] = useState("");
  const [domains, setDomains] = useState<WorkbookDatasetCode[]>([...DATASET_ORDER]);
  const [includeDetails, setIncludeDetails] = useState(true);
  const [snapshot, setSnapshot] = useState<ManagementSnapshot | null>(null);
  const [previewHtml, setPreviewHtml] = useState("");
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [notice, setNotice] = useState<string | null>(null);

  const selected = useMemo(() => new Set(domains), [domains]);
  const snapshotId = Number(new URLSearchParams(location.search).get("snapshot") || 0);

  useEffect(() => {
    if (!snapshotId) return;
    let active = true;
    setLoading(true);
    setError(null);
    void Promise.all([readHtml(snapshotId), readSnapshotData(snapshotId)]).then(([reportHtml, meta]) => {
      if (!active) return;
      setPreviewHtml(reportHtml);
      setSnapshot({
        ...meta,
        view_url: `${ROOT}/reports/${snapshotId}/view`,
        pdf_url: `${ROOT}/reports/${snapshotId}/pdf`,
        data_url: `${ROOT}/reports/${snapshotId}/data`,
      });
    }).catch((caught: unknown) => {
      if (active) setError(caught instanceof Error ? caught.message : "The retained management report could not be opened.");
    }).finally(() => { if (active) setLoading(false); });
    return () => { active = false; };
  }, [snapshotId]);

  const setRange = (start: Date, end: Date, nextBucket: typeof bucket = "AUTO") => {
    setPeriodStart(iso(start));
    setPeriodEnd(iso(end));
    setBucket(nextBucket);
  };
  const quarter = (number: 1 | 2 | 3 | 4) => {
    const startMonth = (number - 1) * 3;
    setRange(new Date(reportYear, startMonth, 1), new Date(reportYear, startMonth + 3, 0), "MONTH");
  };
  const thisQuarter = () => {
    const startMonth = Math.floor(current.getMonth() / 3) * 3;
    setRange(new Date(current.getFullYear(), startMonth, 1), current, "MONTH");
  };
  const previousQuarter = () => {
    const currentStartMonth = Math.floor(current.getMonth() / 3) * 3;
    const start = new Date(current.getFullYear(), currentStartMonth - 3, 1);
    const end = new Date(current.getFullYear(), currentStartMonth, 0);
    setRange(start, end, "MONTH");
  };

  const generate = async (event: React.FormEvent) => {
    event.preventDefault();
    if (!domains.length) { setError("Select at least one Reliability domain for the report."); return; }
    setLoading(true);
    setError(null);
    setNotice(null);
    try {
      const result = await renderManagementReport({
        period_start: periodStart,
        period_end: periodEnd,
        aircraft: aircraftText.split(",").map((item) => item.trim()).filter(Boolean),
        dataset_codes: domains,
        bucket,
        title: title.trim() || null,
        include_domain_details: includeDetails,
      });
      setSnapshot(result);
      setPreviewHtml(await readHtml(result.id));
      navigate(`/maintenance/${encodeURIComponent(amoCode)}/reliability/workbook-reports?snapshot=${result.id}`, { replace: true });
      setNotice(`Snapshot ${result.id} was retained. Opening this link later reads the same retained report rather than recalculating it.`);
    } catch (caught: unknown) {
      setError(caught instanceof Error ? caught.message : "The management report could not be generated.");
    } finally { setLoading(false); }
  };

  const copyLink = async () => {
    if (!snapshot) return;
    const link = `${window.location.origin}/maintenance/${encodeURIComponent(amoCode)}/reliability/workbook-reports?snapshot=${snapshot.id}`;
    try {
      await navigator.clipboard.writeText(link);
      setNotice("Authenticated retained-report link copied.");
    } catch {
      setError(`Copy was blocked. Report link: ${link}`);
    }
  };

  return <section className="rel-wp__panel rel-wp__span-all" aria-labelledby="management-period-report-heading">
    <div className="rel-wp__section-heading">
      <div>
        <p className="rel-wp__eyebrow">Daily → weekly → monthly → quarterly</p>
        <h2 id="management-period-report-heading">Reliability management period report</h2>
        <p>Generate one retained, graph-rich report from approved Reliability evidence across any or all controlled domains. Blank aircraft scope means the fleet.</p>
      </div>
      <span>All 16 domains · retained HTML · server PDF</span>
    </div>
    {error && <div className="rel-wp__error" role="alert">{error}</div>}
    {notice && <div className="rel-wp__notice" role="status">{notice}</div>}
    <form className="rel-wp__form" onSubmit={generate}>
      <div className="rel-wp__form-grid">
        <label>Period start<input type="date" required value={periodStart} onChange={(event) => setPeriodStart(event.target.value)} /></label>
        <label>Period end<input type="date" required value={periodEnd} onChange={(event) => setPeriodEnd(event.target.value)} /></label>
        <label>Graph resolution<select value={bucket} onChange={(event) => setBucket(event.target.value as typeof bucket)}><option value="AUTO">Automatic</option><option value="DAY">Daily</option><option value="WEEK">Weekly</option><option value="MONTH">Monthly</option></select></label>
        <label>Quarter year<input type="number" min="2000" max="2100" value={reportYear} onChange={(event) => setReportYear(Number(event.target.value) || current.getFullYear())} /></label>
        <label className="rel-wp__span-2">Aircraft / fleet scope<input value={aircraftText} onChange={(event) => setAircraftText(event.target.value)} placeholder="Blank = fleet; or comma-separated aircraft serial numbers" /></label>
        <label className="rel-wp__span-2">Report title<input value={title} maxLength={180} onChange={(event) => setTitle(event.target.value)} placeholder="Optional — generated automatically when blank" /></label>
      </div>
      <div className="rel-wp__quick-ranges" aria-label="Management report quick periods">
        <button type="button" onClick={() => setRange(new Date(), new Date(), "DAY")}>Today</button>
        <button type="button" onClick={() => setRange(startOfWeek(current), current, "DAY")}>This week</button>
        <button type="button" onClick={() => { const start = startOfWeek(current); start.setDate(start.getDate() - 7); setRange(start, endOfWeek(start), "DAY"); }}>Previous week</button>
        <button type="button" onClick={() => setRange(new Date(daysAgo(7)), new Date(), "DAY")}>Last 7 days</button>
        <button type="button" onClick={() => setRange(new Date(daysAgo(30)), new Date(), "WEEK")}>Last 30 days</button>
        <button type="button" onClick={() => setRange(startOfMonth(current), current, "DAY")}>This month</button>
        <button type="button" onClick={() => { const previous = new Date(current.getFullYear(), current.getMonth() - 1, 1); setRange(previous, endOfMonth(previous), "WEEK"); }}>Previous month</button>
        <button type="button" onClick={thisQuarter}>This quarter</button>
        <button type="button" onClick={previousQuarter}>Previous quarter</button>
        <button type="button" onClick={() => setRange(new Date(current.getFullYear(), 0, 1), current, "MONTH")}>YTD</button>
        <button type="button" onClick={() => quarter(1)}>Q1</button><button type="button" onClick={() => quarter(2)}>Q2</button><button type="button" onClick={() => quarter(3)}>Q3</button><button type="button" onClick={() => quarter(4)}>Q4</button>
      </div>
      <fieldset>
        <legend>Report content preset</legend>
        <div className="rel-wp__quick-ranges">{DOMAIN_PRESETS.map((preset) => <button type="button" key={preset.label} onClick={() => setDomains(preset.codes)}>{preset.label}</button>)}</div>
      </fieldset>
      <fieldset>
        <legend>Controlled domains included</legend>
        <div className="rel-wp__domain-selector">
          <div className="rel-wp__form-actions"><button type="button" className="btn btn-secondary" onClick={() => setDomains([...DATASET_ORDER])}>All 16</button><button type="button" className="btn btn-secondary" onClick={() => setDomains([])}>Clear</button></div>
          <div className="rel-wp__domain-selector-grid">{DATASET_ORDER.map((code) => <label key={code} className="rel-wp__checkbox"><input type="checkbox" checked={selected.has(code)} onChange={(event) => setDomains((currentDomains) => event.target.checked ? [...currentDomains, code].filter((value, index, all) => all.indexOf(value) === index) : currentDomains.filter((value) => value !== code))} />{code}</label>)}</div>
        </div>
      </fieldset>
      <label className="rel-wp__checkbox"><input type="checkbox" checked={includeDetails} onChange={(event) => setIncludeDetails(event.target.checked)} />Include bounded domain detail tables in the retained report</label>
      <div className="rel-wp__form-actions"><button type="submit" className="btn btn-primary" disabled={loading}>{loading ? "Generating controlled snapshot…" : "Generate and retain management report"}</button></div>
    </form>

    {previewHtml && <div className="rel-wp__management-preview">
      <div className="rel-wp__section-heading">
        <div><p className="rel-wp__eyebrow">Retained management output</p><h3>Snapshot {snapshot?.id}</h3>{snapshot?.sha256_hash && <p><code>{snapshot.sha256_hash}</code></p>}</div>
        <div className="rel-wp__form-actions">
          <button type="button" className="btn btn-secondary" onClick={() => void copyLink()}>Copy manager link</button>
          <button type="button" className="btn btn-secondary" onClick={() => iframeRef.current?.contentWindow?.print()}>Print</button>
          <button type="button" className="btn btn-primary" disabled={!snapshot} onClick={() => snapshot && void downloadPdf(snapshot.id, `reliability-report-${snapshot.id}.pdf`).catch((caught: unknown) => setError(caught instanceof Error ? caught.message : "PDF download failed."))}>Download controlled PDF</button>
        </div>
      </div>
      <iframe ref={iframeRef} title="Retained Reliability management report" srcDoc={previewHtml} sandbox="allow-same-origin allow-modals" />
    </div>}
  </section>;
}