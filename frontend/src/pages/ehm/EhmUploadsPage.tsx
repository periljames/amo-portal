// src/pages/ehm/EhmUploadsPage.tsx
import React, { useEffect, useMemo, useState } from "react";
import { useParams } from "react-router-dom";
import DepartmentLayout from "../../components/Layout/DepartmentLayout";
import { demoTrendUploads } from "../../demo/ehmDemoData";
import { useEhmDemoMode } from "../../hooks/useEhmDemoMode";
import {
  listEngineSnapshots,
  listEngineTrendStatus,
  type EngineSnapshot,
  type EngineTrendStatus,
} from "../../services/ehm";
import { decodeAmoCertFromUrl } from "../../utils/amo";
import "../../styles/ehm.css";

const EhmUploadsPage: React.FC = () => {
  const params = useParams<{ amoCode?: string }>();
  const amoSlug = params.amoCode ?? "UNKNOWN";
  const amoDisplay = amoSlug !== "UNKNOWN" ? decodeAmoCertFromUrl(amoSlug) : "AMO";

  const [search, setSearch] = useState("");
  const [statusFilter, setStatusFilter] = useState("all");
  const [snapshots, setSnapshots] = useState<EngineSnapshot[]>([]);
  const [statusRows, setStatusRows] = useState<EngineTrendStatus[]>([]);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const { isDemoMode, canToggleDemo, setDemoMode } = useEhmDemoMode();

  useEffect(() => {
    if (isDemoMode) return;
    setLoading(true);
    setError(null);
    Promise.all([listEngineSnapshots(), listEngineTrendStatus()])
      .then(([snapshotRows, statusData]) => {
        setSnapshots(snapshotRows);
        setStatusRows(statusData);
      })
      .catch((err) => {
        setError(err?.message || "Unable to load uploads.");
        setSnapshots([]);
        setStatusRows([]);
      })
      .finally(() => setLoading(false));
  }, [isDemoMode]);

  const uploads = useMemo(() => demoTrendUploads, []);

  const liveUploads = useMemo(() => {
    const statusMap = new Map(
      statusRows.map((row) => [
        `${row.aircraft_serial_number}-${row.engine_position}-${row.engine_serial_number ?? ""}`,
        row,
      ])
    );

    return [...snapshots]
      .sort((a, b) => (b.flight_date || "").localeCompare(a.flight_date || ""))
      .slice(0, 10)
      .map((snapshot) => {
        const key = `${snapshot.aircraft_serial_number}-${snapshot.engine_position}-${snapshot.engine_serial_number ?? ""}`;
        const status = statusMap.get(key);
        return {
          id: snapshot.id,
          aircraft: snapshot.aircraft_serial_number,
          registration: "—",
          enginePosition: snapshot.engine_position,
          engineSerial: snapshot.engine_serial_number ?? "—",
          uploadedAt: snapshot.flight_date,
          lastTrend: status?.last_trend_date ?? snapshot.flight_date,
          trendStatus: status?.current_status ?? "Trend Normal",
          reviewStatus: status?.last_review_date ? "Reviewed" : "Pending",
          source: snapshot.data_source ?? "API",
          points: 1,
        };
      });
  }, [snapshots, statusRows]);

  const activeUploads = isDemoMode ? uploads : liveUploads;

  const handleDownloadCsv = () => {
    if (!isDemoMode) {
      return;
    }
    const headers = [
      "Aircraft",
      "Reg",
      "Engine",
      "Serial",
      "Points",
      "Last Upload",
      "Last Trend",
      "Status",
      "Review",
      "Source",
    ];
    const rows = uploads.map((upload) => [
      upload.aircraft,
      upload.registration,
      upload.enginePosition,
      upload.engineSerial,
      upload.points,
      upload.uploadedAt,
      upload.lastTrend,
      upload.trendStatus,
      upload.reviewStatus,
      upload.source,
    ]);
    const content = [headers, ...rows].map((line) => line.join(",")).join("\n");
    const blob = new Blob([content], { type: "text/csv;charset=utf-8;" });
    const link = document.createElement("a");
    link.href = URL.createObjectURL(blob);
    link.download = "ehm-uploads-demo.csv";
    link.click();
    URL.revokeObjectURL(link.href);
  };

  const filteredUploads = useMemo(() => {
    const query = search.trim().toLowerCase();
    return activeUploads.filter((upload) => {
      const matchesQuery =
        !query ||
        upload.aircraft.toLowerCase().includes(query) ||
        upload.registration.toLowerCase().includes(query) ||
        upload.engineSerial.toLowerCase().includes(query);
      const matchesStatus =
        statusFilter === "all" || upload.trendStatus.toLowerCase().includes(statusFilter);
      return matchesQuery && matchesStatus;
    });
  }, [search, statusFilter, activeUploads]);

  return (
    <DepartmentLayout amoCode={amoSlug} activeDepartment="reliability">
      <header className="ehm-hero ehm-hero--compact">
        <div>
          <p className="ehm-eyebrow">Engine Health Monitoring</p>
          <h1>Uploads & Reviews · {amoDisplay}</h1>
          <p className="ehm-subtitle">
            Track the last 10 uploads, ensure review completion, and trace data sources.
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
            Upload trend file
          </button>
          <button className="btn btn-secondary" type="button">
            Queue review
          </button>
        </div>
      </header>

      <section className="ehm-surface">
        <div className="ehm-surface__header">
          <div>
            <h2>Recent uploads</h2>
            <p className="ehm-muted">Showing latest 10 snapshot batches.</p>
          </div>
          <div className="ehm-toolbar">
            <label className="ehm-control">
              Search
              <input
                type="text"
                placeholder="Search aircraft, reg, engine serial"
                value={search}
                onChange={(event) => setSearch(event.target.value)}
              />
            </label>
            <label className="ehm-control">
              Status
              <select
                value={statusFilter}
                onChange={(event) => setStatusFilter(event.target.value)}
              >
                <option value="all">All</option>
                <option value="normal">Trend Normal</option>
                <option value="shift">Trend Shift</option>
              </select>
            </label>
            <button
              className="btn btn-secondary"
              type="button"
              onClick={handleDownloadCsv}
            >
              Download CSV
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
                <th>Points</th>
                <th>Last upload</th>
                <th>Last trend</th>
                <th>Status</th>
                <th>Review</th>
                <th>Source</th>
              </tr>
            </thead>
            <tbody>
              {loading && (
                <tr>
                  <td colSpan={10} className="ehm-muted">
                    Loading uploads…
                  </td>
                </tr>
              )}
              {error && (
                <tr>
                  <td colSpan={10} className="ehm-muted">
                    {error}
                  </td>
                </tr>
              )}
              {filteredUploads.map((upload) => {
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
                    <td>{upload.points}</td>
                    <td>{upload.uploadedAt}</td>
                    <td>{upload.lastTrend}</td>
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
              {!loading && !error && filteredUploads.length === 0 && (
                <tr>
                  <td colSpan={10} className="ehm-muted">
                    No uploads match your filters.
                  </td>
                </tr>
              )}
            </tbody>
          </table>
        </div>
      </section>
    </DepartmentLayout>
  );
};

export default EhmUploadsPage;
