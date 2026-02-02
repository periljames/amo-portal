// src/pages/ReliabilityReportsPage.tsx
import React, { useEffect, useMemo, useState } from "react";
import { useParams } from "react-router-dom";

import DepartmentLayout from "../components/Layout/DepartmentLayout";
import {
  createReliabilityReport,
  downloadReliabilityReport,
  listReliabilityReports,
} from "../services/reliability";
import type { ReliabilityReportRead, TransferProgress } from "../services/reliability";

type UrlParams = {
  amoCode?: string;
  department?: string;
};

type DownloadState = {
  reportId: number;
  progress: TransferProgress;
};

const ReliabilityReportsPage: React.FC = () => {
  const { amoCode } = useParams<UrlParams>();
  const [reports, setReports] = useState<ReliabilityReportRead[]>([]);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [windowStart, setWindowStart] = useState("");
  const [windowEnd, setWindowEnd] = useState("");
  const [creating, setCreating] = useState(false);
  const [downloadProgress, setDownloadProgress] = useState<DownloadState | null>(null);

  const hasPending = useMemo(
    () => reports.some((report) => report.status === "PENDING"),
    [reports]
  );

  useEffect(() => {
    const today = new Date();
    const end = today.toISOString().slice(0, 10);
    const start = new Date(today);
    start.setDate(today.getDate() - 30);
    setWindowStart(start.toISOString().slice(0, 10));
    setWindowEnd(end);
  }, []);

  const loadReports = async () => {
    setError(null);
    setLoading(true);
    try {
      const data = await listReliabilityReports();
      setReports(data);
    } catch (e: any) {
      console.error("Failed to load reliability reports", e);
      setError(e?.message || "Could not load reliability reports.");
    } finally {
      setLoading(false);
    }
  };

  useEffect(() => {
    loadReports();
  }, []);

  useEffect(() => {
    if (!hasPending) return;
    const interval = window.setInterval(() => {
      loadReports();
    }, 5000);
    return () => window.clearInterval(interval);
  }, [hasPending]);

  const handleGenerate = async () => {
    if (!windowStart || !windowEnd) {
      setError("Please choose both a start and end date.");
      return;
    }
    setCreating(true);
    setError(null);
    try {
      await createReliabilityReport(windowStart, windowEnd);
      await loadReports();
    } catch (e: any) {
      console.error("Failed to generate report", e);
      setError(e?.message || "Could not generate report.");
    } finally {
      setCreating(false);
    }
  };

  const handleDownload = async (report: ReliabilityReportRead) => {
    setError(null);
    setDownloadProgress(null);
    try {
      const blob = await downloadReliabilityReport(report.id, (progress) =>
        setDownloadProgress({ reportId: report.id, progress })
      );
      const url = window.URL.createObjectURL(blob);
      const link = document.createElement("a");
      link.href = url;
      link.download = `reliability_report_${report.id}.pdf`;
      link.click();
      window.URL.revokeObjectURL(url);
    } catch (e: any) {
      console.error("Failed to download report", e);
      setError(e?.message || "Could not download report.");
    } finally {
      setDownloadProgress(null);
    }
  };

  const formatSpeed = (progress: TransferProgress) => {
    const mbps = progress.megaBytesPerSecond;
    const mbits = progress.megaBitsPerSecond;
    const mbpsLabel = Number.isFinite(mbps) ? mbps.toFixed(2) : "0.00";
    const mbitsLabel = Number.isFinite(mbits) ? mbits.toFixed(2) : "0.00";
    return `${mbpsLabel} MB/s • ${mbitsLabel} Mb/s`;
  };

  const formatStatus = (status: ReliabilityReportRead["status"]) => {
    switch (status) {
      case "READY":
        return "Ready";
      case "FAILED":
        return "Failed";
      default:
        return "Generating";
    }
  };

  return (
    <DepartmentLayout
      amoCode={amoCode ?? "UNKNOWN"}
      activeDepartment="reliability"
    >
      <header className="page-header">
        <h1 className="page-header__title">Reliability Reports</h1>
        <p className="page-header__subtitle">
          Generate and download reliability PDFs for the selected date window.
        </p>
      </header>

      <section className="page-section">
        <div className="card card--form" style={{ padding: 16 }}>
          <h2 style={{ marginTop: 0 }}>Generate report</h2>
          {error && <div className="alert alert-error">{error}</div>}
          <div className="form-row">
            <label htmlFor="windowStart">Window start</label>
            <input
              id="windowStart"
              type="date"
              value={windowStart}
              onChange={(e) => setWindowStart(e.target.value)}
            />
          </div>
          <div className="form-row">
            <label htmlFor="windowEnd">Window end</label>
            <input
              id="windowEnd"
              type="date"
              value={windowEnd}
              onChange={(e) => setWindowEnd(e.target.value)}
            />
          </div>
          <div className="form-row" style={{ alignItems: "center" }}>
            <button
              type="button"
              className="btn btn-primary"
              onClick={handleGenerate}
              disabled={creating}
            >
              {creating ? "Generating…" : "Generate report"}
            </button>
            {creating && (
              <span className="form-hint">Report generation has started.</span>
            )}
          </div>
          {hasPending && (
            <div className="form-row">
              <div style={{ flex: 1 }}>
                <strong>Report generation in progress</strong>
                <progress style={{ width: "100%", height: 10, marginTop: 6 }} />
                <p style={{ marginTop: 6, opacity: 0.8 }}>
                  We&apos;ll refresh automatically every few seconds until the report is ready.
                </p>
              </div>
            </div>
          )}
        </div>
      </section>

      <section className="page-section">
        <div className="card card--form" style={{ padding: 16 }}>
          <h2 style={{ marginTop: 0 }}>Recent reports</h2>
          {loading && <p>Loading reports…</p>}
          {!loading && reports.length === 0 && (
            <p style={{ opacity: 0.7 }}>No reports generated yet.</p>
          )}
          {!loading && reports.length > 0 && (
            <div className="table-wrap">
              <table className="table">
                <thead>
                  <tr>
                    <th>ID</th>
                    <th>Window</th>
                    <th>Status</th>
                    <th>Created</th>
                    <th />
                  </tr>
                </thead>
                <tbody>
                  {reports.map((report) => {
                    const isDownloading = downloadProgress?.reportId === report.id;
                    return (
                      <tr key={report.id}>
                        <td>{report.id}</td>
                        <td>
                          {report.window_start} → {report.window_end}
                        </td>
                        <td>{formatStatus(report.status)}</td>
                        <td>{new Date(report.created_at).toLocaleString()}</td>
                        <td>
                          <button
                            type="button"
                            className="btn btn-secondary"
                            disabled={report.status !== "READY"}
                            onClick={() => handleDownload(report)}
                          >
                            Download
                          </button>
                          {isDownloading && (
                            <div style={{ marginTop: 8 }}>
                              {downloadProgress?.progress.percent !== undefined && (
                                <progress
                                  value={downloadProgress.progress.percent}
                                  max={100}
                                  style={{ width: "100%", height: 8 }}
                                />
                              )}
                              <p style={{ marginTop: 6, opacity: 0.8 }}>
                                {formatSpeed(downloadProgress.progress)}
                              </p>
                            </div>
                          )}
                        </td>
                      </tr>
                    );
                  })}
                </tbody>
              </table>
            </div>
          )}
        </div>
      </section>
    </DepartmentLayout>
  );
};

export default ReliabilityReportsPage;
