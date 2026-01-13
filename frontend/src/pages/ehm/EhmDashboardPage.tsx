// src/pages/ehm/EhmDashboardPage.tsx
import React, { useEffect, useMemo, useState } from "react";
import { useNavigate, useParams } from "react-router-dom";
import DepartmentLayout from "../../components/Layout/DepartmentLayout";
import { demoTrendStatus, demoTrendUploads } from "../../demo/ehmDemoData";
import { useEhmDemoMode } from "../../hooks/useEhmDemoMode";
import { listEngineTrendStatus, type EngineTrendStatus } from "../../services/ehm";
import { decodeAmoCertFromUrl } from "../../utils/amo";
import "../../styles/ehm.css";

const EhmDashboardPage: React.FC = () => {
  const params = useParams<{ amoCode?: string }>();
  const navigate = useNavigate();
  const amoSlug = params.amoCode ?? "UNKNOWN";
  const amoDisplay = amoSlug !== "UNKNOWN" ? decodeAmoCertFromUrl(amoSlug) : "AMO";

  const [selectedProgram, setSelectedProgram] = useState("EHM-DEMO6");
  const [selectedPhase, setSelectedPhase] = useState("cruise");
  const [statusRows, setStatusRows] = useState<EngineTrendStatus[]>([]);
  const [statusLoading, setStatusLoading] = useState(false);
  const [statusError, setStatusError] = useState<string | null>(null);

  const { isDemoMode, canToggleDemo, setDemoMode } = useEhmDemoMode();

  useEffect(() => {
    if (isDemoMode) return;
    setStatusLoading(true);
    setStatusError(null);
    listEngineTrendStatus()
      .then((rows) => setStatusRows(rows))
      .catch((err) => {
        setStatusError(err?.message || "Unable to load trend status.");
        setStatusRows([]);
      })
      .finally(() => setStatusLoading(false));
  }, [isDemoMode]);

  const formatDate = (value: string | null) => {
    if (!value) return "—";
    const d = new Date(value);
    if (Number.isNaN(d.getTime())) return value;
    return d.toLocaleDateString();
  };

  const handleExportFleetSummary = () => {
    if (!isDemoMode) {
      return;
    }
    const headers = [
      "Aircraft",
      "Engine Position",
      "Engine Serial",
      "Last Upload",
      "Last Trend",
      "Status",
      "Review",
    ];
    const rows = demoTrendStatus.map((row) => [
      row.aircraft_serial_number,
      row.engine_position,
      row.engine_serial_number ?? "",
      row.last_upload_date ?? "",
      row.last_trend_date ?? "",
      row.current_status ?? "",
      row.last_review_date ? "Reviewed" : "Pending",
    ]);
    const content = [headers, ...rows].map((line) => line.join(",")).join("\n");
    const blob = new Blob([content], { type: "text/csv;charset=utf-8;" });
    const link = document.createElement("a");
    link.href = URL.createObjectURL(blob);
    link.download = "ehm-fleet-summary-demo.csv";
    link.click();
    URL.revokeObjectURL(link.href);
  };

  const trendUploads = useMemo(() => demoTrendUploads, []);

  const liveUploads = useMemo(() => {
    return [...statusRows]
      .filter((row) => row.last_upload_date)
      .sort((a, b) => (b.last_upload_date || "").localeCompare(a.last_upload_date || ""))
      .slice(0, 10)
      .map((row) => ({
        id: row.id,
        aircraft: row.aircraft_serial_number,
        registration: "—",
        enginePosition: row.engine_position,
        engineSerial: row.engine_serial_number ?? "—",
        uploadedAt: row.last_upload_date ?? "—",
        lastTrend: row.last_trend_date ?? "—",
        trendStatus: row.current_status ?? "Trend Normal",
        reviewStatus: row.last_review_date ? "Reviewed" : "Pending",
        source: "API",
      }));
  }, [statusRows]);

  const activeUploads = isDemoMode ? trendUploads : liveUploads;
  const demoEngines = demoTrendStatus.length;
  const totalEngines = isDemoMode ? demoEngines : statusRows.length;
  const healthyEngines = isDemoMode
    ? demoTrendStatus.filter((row) => row.current_status === "Trend Normal").length
    : statusRows.filter((row) => row.current_status === "Trend Normal").length;
  const shiftEngines = isDemoMode
    ? demoTrendStatus.filter((row) => row.current_status === "Trend Shift").length
    : statusRows.filter((row) => row.current_status === "Trend Shift").length;
  const pendingReviews = isDemoMode
    ? demoTrendStatus.filter((row) => row.current_status === "Trend Shift" && !row.last_review_date)
        .length
    : statusRows.filter((row) => row.current_status === "Trend Shift" && !row.last_review_date)
        .length;

  return (
    <DepartmentLayout amoCode={amoSlug} activeDepartment="ehm">
      <header className="ehm-hero">
        <div>
          <p className="ehm-eyebrow">Engine Health Monitoring</p>
          <h1>EHM Dashboard · {amoDisplay}</h1>
          <p className="ehm-subtitle">
            Fleet trend health, review workflow, and CAMP-ready summaries with consistent
            capture rules.
          </p>
        </div>
        <div className="ehm-hero__actions">
          {canToggleDemo && (
            <label className="ehm-toggle">
              <input
                type="checkbox"
                checked={isDemoMode}
                onChange={(event) => setDemoMode(event.target.checked)}
              />
              Demo mode
            </label>
          )}
          <button className="btn" type="button">
            Submit trend data
          </button>
          <button className="btn btn-secondary" type="button">
            Run trend review
          </button>
          <button className="btn btn-secondary" type="button" onClick={handleExportFleetSummary}>
            Export fleet summary
          </button>
        </div>
      </header>

      <section className="ehm-grid">
        <div className="ehm-stat">
          <p className="ehm-stat__label">Healthy engines</p>
          <p className="ehm-stat__value">{healthyEngines}</p>
          <p className="ehm-stat__meta">Trend Normal · 7-day baseline</p>
        </div>
        <div className="ehm-stat">
          <p className="ehm-stat__label">Trend shifts</p>
          <p className="ehm-stat__value">{shiftEngines}</p>
          <p className="ehm-stat__meta">{pendingReviews} pending reviews</p>
        </div>
        <div className="ehm-stat">
          <p className="ehm-stat__label">Capture completeness</p>
          <p className="ehm-stat__value">{totalEngines ? "—" : "0"}</p>
          <p className="ehm-stat__meta">
            {isDemoMode ? "94% valid · last 24h" : "Awaiting metric validation feed"}
          </p>
        </div>
        <div className="ehm-stat">
          <p className="ehm-stat__label">Pending reviews</p>
          <p className="ehm-stat__value">{pendingReviews}</p>
          <p className="ehm-stat__meta">Awaiting sign-off</p>
        </div>
      </section>

      <section className="ehm-surface">
        <div className="ehm-surface__header">
          <div>
            <h2>Fleet overview</h2>
            <p className="ehm-muted">
              Last 10 uploads by engine position with current trend status.
            </p>
          </div>
          <div className="ehm-toolbar">
            <label className="ehm-control">
              Program
              <select
                value={selectedProgram}
                onChange={(event) => setSelectedProgram(event.target.value)}
              >
                <option value="EHM-DEMO6">EHM-DEMO6</option>
                <option value="EHM-DEMO4">EHM-DEMO4</option>
                <option value="EHM-PW150A">EHM-PW150A</option>
                <option value="EHM-PW307A">EHM-PW307A</option>
              </select>
            </label>
            <label className="ehm-control">
              Phase
              <select
                value={selectedPhase}
                onChange={(event) => setSelectedPhase(event.target.value)}
              >
                <option value="cruise">Cruise</option>
                <option value="climb">Climb</option>
                <option value="takeoff">Takeoff</option>
              </select>
            </label>
            <button
              className="btn btn-secondary"
              type="button"
              onClick={() => navigate(`/maintenance/${amoSlug}/ehm/trends`)}
            >
              View trend graphs
            </button>
          </div>
        </div>
        <div className="ehm-table">
          <table>
            <thead>
              <tr>
                <th>Aircraft</th>
                <th>Reg</th>
                <th>Engine</th>
                <th>Serial</th>
                <th>Last upload</th>
                <th>Last trend</th>
                <th>Status</th>
                <th>Review</th>
                <th>Source</th>
              </tr>
            </thead>
            <tbody>
              {statusLoading && (
                <tr>
                  <td colSpan={9} className="ehm-muted">
                    Loading latest uploads…
                  </td>
                </tr>
              )}
              {statusError && (
                <tr>
                  <td colSpan={9} className="ehm-muted">
                    {statusError}
                  </td>
                </tr>
              )}
              {!statusLoading && !statusError && activeUploads.length === 0 && (
                <tr>
                  <td colSpan={9} className="ehm-muted">
                    No recent uploads found.
                  </td>
                </tr>
              )}
              {activeUploads.map((upload) => {
                const statusClass =
                  upload.trendStatus === "Trend Shift" ? "badge--danger" : "badge--success";
                const reviewClass =
                  upload.reviewStatus === "Pending" ? "badge--warning" : "badge--success";
                return (
                  <tr key={upload.id}>
                    <td>{upload.aircraft}</td>
                    <td>{upload.registration}</td>
                    <td>{upload.enginePosition}</td>
                    <td>{upload.engineSerial}</td>
                    <td>{formatDate(upload.uploadedAt)}</td>
                    <td>{formatDate(upload.lastTrend)}</td>
                    <td>
                      <span className={`badge ${statusClass}`}>{upload.trendStatus}</span>
                    </td>
                    <td>
                      <span className={`badge ${reviewClass}`}>{upload.reviewStatus}</span>
                    </td>
                    <td>{upload.source}</td>
                  </tr>
                );
              })}
            </tbody>
          </table>
        </div>
      </section>
    </DepartmentLayout>
  );
};

export default EhmDashboardPage;
