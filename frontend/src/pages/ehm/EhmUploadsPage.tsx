// src/pages/ehm/EhmUploadsPage.tsx
import React, { useEffect, useMemo, useState } from "react";
import { useParams } from "react-router-dom";
import DepartmentLayout from "../../components/Layout/DepartmentLayout";
import { demoTrendUploads } from "../../demo/ehmDemoData";
import { useEhmDemoMode } from "../../hooks/useEhmDemoMode";
import {
  listEhmLogs,
  uploadEhmLog,
  type EhmLog,
} from "../../services/ehm";
import { decodeAmoCertFromUrl } from "../../utils/amo";
import "../../styles/ehm.css";

const EhmUploadsPage: React.FC = () => {
  const params = useParams<{ amoCode?: string }>();
  const amoSlug = params.amoCode ?? "UNKNOWN";
  const amoDisplay = amoSlug !== "UNKNOWN" ? decodeAmoCertFromUrl(amoSlug) : "AMO";

  const [search, setSearch] = useState("");
  const [statusFilter, setStatusFilter] = useState("all");
  const [logs, setLogs] = useState<EhmLog[]>([]);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [uploading, setUploading] = useState(false);
  const [uploadError, setUploadError] = useState<string | null>(null);
  const [uploadSuccess, setUploadSuccess] = useState<string | null>(null);
  const [aircraftSerial, setAircraftSerial] = useState("");
  const [enginePosition, setEnginePosition] = useState("");
  const [engineSerial, setEngineSerial] = useState("");
  const [source, setSource] = useState("");
  const [notes, setNotes] = useState("");
  const [file, setFile] = useState<File | null>(null);

  const { isDemoMode, canToggleDemo, setDemoMode } = useEhmDemoMode();

  useEffect(() => {
    if (isDemoMode) return;
    setLoading(true);
    setError(null);
    listEhmLogs({ limit: 50 })
      .then((rows) => {
        setLogs(rows);
      })
      .catch((err) => {
        setError(err?.message || "Unable to load uploads.");
        setLogs([]);
      })
      .finally(() => setLoading(false));
  }, [isDemoMode]);

  const uploads = useMemo(() => demoTrendUploads, []);

  const liveUploads = useMemo(() => {
    return [...logs]
      .sort((a, b) => (b.created_at || "").localeCompare(a.created_at || ""))
      .slice(0, 10)
      .map((log) => ({
        id: log.id,
        aircraft: log.aircraft_serial_number ?? "—",
        registration: "—",
        enginePosition: log.engine_position,
        engineSerial: log.engine_serial_number ?? "—",
        uploadedAt: log.created_at,
        parseStatus: log.parse_status,
        records: log.parsed_record_count,
        source: log.source ?? "EHM",
      }));
  }, [logs]);

  const activeUploads = useMemo(() => {
    if (!isDemoMode) return liveUploads;
    return uploads.map((upload) => ({
      id: upload.id,
      aircraft: upload.aircraft,
      registration: upload.registration,
      enginePosition: upload.enginePosition,
      engineSerial: upload.engineSerial,
      uploadedAt: upload.uploadedAt,
      parseStatus: upload.trendStatus === "Trend Shift" ? "FAILED" : "PARSED",
      records: upload.points,
      source: upload.source,
    }));
  }, [isDemoMode, liveUploads, uploads]);

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
        statusFilter === "all" || upload.parseStatus.toLowerCase().includes(statusFilter);
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
          <button
            className="btn"
            type="button"
            disabled={uploading}
            onClick={() => {
              setUploadError(null);
              setUploadSuccess(null);
              if (!file) {
                setUploadError("Select a .log file to upload.");
                return;
              }
              if (!aircraftSerial.trim() || !enginePosition.trim()) {
                setUploadError("Aircraft serial and engine position are required.");
                return;
              }
              setUploading(true);
              uploadEhmLog({
                file,
                aircraft_serial_number: aircraftSerial.trim(),
                engine_position: enginePosition.trim(),
                engine_serial_number: engineSerial.trim() || null,
                source: source.trim() || null,
                notes: notes.trim() || null,
              })
                .then(() => {
                  setUploadSuccess("Upload queued for parsing.");
                  setFile(null);
                  setNotes("");
                  return listEhmLogs({ limit: 50 });
                })
                .then((rows) => setLogs(rows))
                .catch((err) => {
                  setUploadError(err?.message || "Upload failed.");
                })
                .finally(() => setUploading(false));
            }}
          >
            {uploading ? "Uploading…" : "Upload EHM log"}
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
              Aircraft
              <input
                type="text"
                placeholder="Aircraft serial"
                value={aircraftSerial}
                onChange={(event) => setAircraftSerial(event.target.value)}
              />
            </label>
            <label className="ehm-control">
              Engine position
              <input
                type="text"
                placeholder="LH / RH"
                value={enginePosition}
                onChange={(event) => setEnginePosition(event.target.value)}
              />
            </label>
            <label className="ehm-control">
              Engine serial
              <input
                type="text"
                placeholder="Optional serial"
                value={engineSerial}
                onChange={(event) => setEngineSerial(event.target.value)}
              />
            </label>
            <label className="ehm-control">
              Source
              <input
                type="text"
                placeholder="Source system"
                value={source}
                onChange={(event) => setSource(event.target.value)}
              />
            </label>
            <label className="ehm-control">
              Notes
              <input
                type="text"
                placeholder="Optional notes"
                value={notes}
                onChange={(event) => setNotes(event.target.value)}
              />
            </label>
            <label className="ehm-control">
              Log file
              <input
                type="file"
                accept=".log"
                onChange={(event) => setFile(event.target.files?.[0] ?? null)}
              />
            </label>
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
                <option value="parsed">Parsed</option>
                <option value="pending">Pending</option>
                <option value="failed">Failed</option>
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
                <th>Records</th>
                <th>Last upload</th>
                <th>Status</th>
                <th>Source</th>
              </tr>
            </thead>
            <tbody>
              {uploadSuccess && (
                <tr>
                  <td colSpan={9} className="ehm-muted">
                    {uploadSuccess}
                  </td>
                </tr>
              )}
              {uploadError && (
                <tr>
                  <td colSpan={9} className="ehm-muted">
                    {uploadError}
                  </td>
                </tr>
              )}
              {loading && (
                <tr>
                  <td colSpan={9} className="ehm-muted">
                    Loading uploads…
                  </td>
                </tr>
              )}
              {error && (
                <tr>
                  <td colSpan={9} className="ehm-muted">
                    {error}
                  </td>
                </tr>
              )}
              {filteredUploads.map((upload) => {
                const statusClass =
                  upload.parseStatus === "FAILED"
                    ? "badge--danger"
                    : upload.parseStatus === "PARSED"
                    ? "badge--success"
                    : "badge--warning";
                return (
                  <tr key={upload.id}>
                    <td>{upload.aircraft}</td>
                    <td>{upload.registration}</td>
                    <td>{upload.enginePosition}</td>
                    <td>{upload.engineSerial}</td>
                    <td>{upload.records}</td>
                    <td>{upload.uploadedAt}</td>
                    <td>
                      <span className={`badge ${statusClass}`}>{upload.parseStatus}</span>
                    </td>
                    <td>{upload.source}</td>
                  </tr>
                );
              })}
              {!loading && !error && filteredUploads.length === 0 && (
                <tr>
                  <td colSpan={9} className="ehm-muted">
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
