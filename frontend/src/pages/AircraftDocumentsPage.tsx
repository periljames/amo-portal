// src/pages/AircraftDocumentsPage.tsx
import React, { useEffect, useMemo, useState } from "react";
import { useParams } from "react-router-dom";

import DepartmentLayout from "../components/Layout/DepartmentLayout";
import {
  listAircraft,
  listAircraftDocuments,
  downloadAircraftDocumentFile,
  downloadAircraftDocumentsZip,
} from "../services/fleet";
import type { AircraftDocument, AircraftRead, TransferProgress } from "../services/fleet";

type UrlParams = {
  amoCode?: string;
  department?: string;
};

type DownloadState = {
  documentId?: number;
  bundle?: boolean;
  progress: TransferProgress;
};

type ValidityNotice = {
  title: string;
  body: string;
};

const AircraftDocumentsPage: React.FC = () => {
  const { amoCode } = useParams<UrlParams>();
  const [aircraft, setAircraft] = useState<AircraftRead[]>([]);
  const [aircraftLoading, setAircraftLoading] = useState(false);
  const [aircraftError, setAircraftError] = useState<string | null>(null);
  const [selectedAircraft, setSelectedAircraft] = useState<string>("");
  const [documents, setDocuments] = useState<AircraftDocument[]>([]);
  const [documentsLoading, setDocumentsLoading] = useState(false);
  const [documentsError, setDocumentsError] = useState<string | null>(null);
  const [downloadProgress, setDownloadProgress] = useState<DownloadState | null>(null);
  const [selectedDocumentIds, setSelectedDocumentIds] = useState<Set<number>>(new Set());
  const [defaultsInitialized, setDefaultsInitialized] = useState(false);
  const [validityNotice, setValidityNotice] = useState<ValidityNotice | null>(null);

  const hasSelection = useMemo(() => selectedAircraft.trim().length > 0, [selectedAircraft]);
  const documentsByType = useMemo(() => {
    return documents.reduce<Record<string, AircraftDocument[]>>((acc, doc) => {
      const key = doc.document_type;
      if (!acc[key]) acc[key] = [];
      acc[key].push(doc);
      return acc;
    }, {});
  }, [documents]);

  const currentByType = useMemo(() => {
    const map = new Map<string, AircraftDocument | null>();
    Object.entries(documentsByType).forEach(([type, docs]) => {
      const currentDocs = docs.filter((doc) => doc.status === "CURRENT");
      const sorted = [...(currentDocs.length ? currentDocs : docs)].sort((a, b) => {
        const aTime = a.expires_on ? new Date(a.expires_on).getTime() : 0;
        const bTime = b.expires_on ? new Date(b.expires_on).getTime() : 0;
        return bTime - aTime;
      });
      map.set(type, sorted[0] || null);
    });
    return map;
  }, [documentsByType]);

  const typesMissingCurrent = useMemo(() => {
    const missing = new Set<string>();
    currentByType.forEach((doc, type) => {
      if (!doc || doc.status !== "CURRENT") {
        missing.add(type);
      }
    });
    return missing;
  }, [currentByType]);

  useEffect(() => {
    const loadAircraft = async () => {
      setAircraftLoading(true);
      setAircraftError(null);
      try {
        const data = await listAircraft({ is_active: true });
        setAircraft(data);
        if (!selectedAircraft && data.length > 0) {
          setSelectedAircraft(data[0].serial_number);
        }
      } catch (e: any) {
        console.error("Failed to load aircraft", e);
        setAircraftError(e?.message || "Could not load aircraft.");
      } finally {
        setAircraftLoading(false);
      }
    };
    loadAircraft();
  }, []);

  useEffect(() => {
    if (!hasSelection) {
      setDocuments([]);
      return;
    }
    const loadDocuments = async () => {
      setDocumentsLoading(true);
      setDocumentsError(null);
      try {
        const data = await listAircraftDocuments(selectedAircraft);
        setDocuments(data);
        setDefaultsInitialized(false);
        setSelectedDocumentIds(new Set());
      } catch (e: any) {
        console.error("Failed to load documents", e);
        setDocumentsError(e?.message || "Could not load aircraft documents.");
      } finally {
        setDocumentsLoading(false);
      }
    };
    loadDocuments();
  }, [hasSelection, selectedAircraft]);

  useEffect(() => {
    if (documents.length === 0 || defaultsInitialized) return;
    const defaults = new Set<number>();
    currentByType.forEach((doc) => {
      if (doc) defaults.add(doc.id);
    });
    setSelectedDocumentIds(defaults);
    setDefaultsInitialized(true);
  }, [documents.length, currentByType, defaultsInitialized]);

  const handleDownload = async (doc: AircraftDocument) => {
    setDocumentsError(null);
    setDownloadProgress(null);
    try {
      const blob = await downloadAircraftDocumentFile(doc.id, (progress) =>
        setDownloadProgress({ documentId: doc.id, progress })
      );
      const url = window.URL.createObjectURL(blob);
      const link = document.createElement("a");
      link.href = url;
      link.download = doc.file_original_name || `aircraft_document_${doc.id}`;
      link.click();
      window.URL.revokeObjectURL(url);
    } catch (e: any) {
      console.error("Failed to download document evidence", e);
      setDocumentsError(e?.message || "Could not download evidence.");
    } finally {
      setDownloadProgress(null);
    }
  };

  const handleDownloadSelected = async () => {
    const ids = Array.from(selectedDocumentIds);
    if (ids.length === 0) {
      setDocumentsError("Select at least one document to download.");
      return;
    }
    if (ids.length === 1) {
      const doc = documents.find((d) => d.id === ids[0]);
      if (doc) {
        await handleDownload(doc);
      }
      return;
    }
    setDocumentsError(null);
    setDownloadProgress(null);
    try {
      const blob = await downloadAircraftDocumentsZip(ids, (progress) =>
        setDownloadProgress({ bundle: true, progress })
      );
      const url = window.URL.createObjectURL(blob);
      const link = document.createElement("a");
      link.href = url;
      link.download = `${selectedAircraft || "aircraft"}_documents.zip`;
      link.click();
      window.URL.revokeObjectURL(url);
    } catch (e: any) {
      console.error("Failed to download document bundle", e);
      setDocumentsError(e?.message || "Could not download documents.");
    } finally {
      setDownloadProgress(null);
    }
  };

  const toggleSelection = (doc: AircraftDocument) => {
    setSelectedDocumentIds((prev) => {
      const next = new Set(prev);
      if (next.has(doc.id)) {
        next.delete(doc.id);
      } else {
        next.add(doc.id);
        if (typesMissingCurrent.has(doc.document_type)) {
          const issued = doc.issued_on ? new Date(doc.issued_on).toLocaleDateString() : "—";
          const expires = doc.expires_on ? new Date(doc.expires_on).toLocaleDateString() : "—";
          setValidityNotice({
            title: "Document validity warning",
            body: `${doc.document_type.replace(/_/g, " ")} is expired or has no current record. Validity: ${issued} → ${expires}.`,
          });
        }
      }
      return next;
    });
  };

  const formatSpeed = (progress: TransferProgress) => {
    const mbps = progress.megaBytesPerSecond;
    const mbits = progress.megaBitsPerSecond;
    const mbpsLabel = Number.isFinite(mbps) ? mbps.toFixed(2) : "0.00";
    const mbitsLabel = Number.isFinite(mbits) ? mbits.toFixed(2) : "0.00";
    return `${mbpsLabel} MB/s • ${mbitsLabel} Mb/s`;
  };

  return (
    <DepartmentLayout
      amoCode={amoCode ?? "UNKNOWN"}
      activeDepartment="planning"
    >
      <header className="page-header">
        <h1 className="page-header__title">Aircraft Documents</h1>
        <p className="page-header__subtitle">
          Review and download evidence for aircraft certificates and compliance documents.
        </p>
      </header>

      <section className="page-section">
        <div className="card card--form" style={{ padding: 16 }}>
          <h2 style={{ marginTop: 0 }}>Select aircraft</h2>
          {aircraftLoading && <p>Loading aircraft…</p>}
          {aircraftError && <div className="alert alert-error">{aircraftError}</div>}
          {!aircraftLoading && !aircraftError && (
            <div className="form-row">
              <label htmlFor="aircraftSelect">Aircraft</label>
              <select
                id="aircraftSelect"
                value={selectedAircraft}
                onChange={(e) => setSelectedAircraft(e.target.value)}
                disabled={aircraft.length === 0}
              >
                {aircraft.map((ac) => (
                  <option key={ac.serial_number} value={ac.serial_number}>
                    {ac.serial_number} {ac.registration ? `(${ac.registration})` : ""}
                  </option>
                ))}
              </select>
            </div>
          )}
        </div>
      </section>

      <section className="page-section">
        <div className="card card--form" style={{ padding: 16 }}>
          <h2 style={{ marginTop: 0 }}>Document evidence</h2>
          {documentsLoading && <p>Loading documents…</p>}
          {documentsError && <div className="alert alert-error">{documentsError}</div>}
          {validityNotice && (
            <div className="card card--warning" style={{ marginBottom: 12 }}>
              <p style={{ margin: 0, fontWeight: 600 }}>{validityNotice.title}</p>
              <p style={{ marginTop: 6, marginBottom: 0 }}>{validityNotice.body}</p>
              <button
                type="button"
                className="secondary-chip-btn"
                style={{ marginTop: 8 }}
                onClick={() => setValidityNotice(null)}
              >
                Dismiss
              </button>
            </div>
          )}
          {!documentsLoading && !documentsError && (
            <div className="table-responsive">
              <table className="table table-striped table-compact">
                <thead>
                  <tr>
                    <th />
                    <th>Type</th>
                    <th>Authority</th>
                    <th>Status</th>
                    <th>Expires</th>
                    <th>Evidence</th>
                    <th />
                  </tr>
                </thead>
                <tbody>
                  {documents.map((doc) => {
                    const isDownloading = downloadProgress?.documentId === doc.id;
                    const isSelected = selectedDocumentIds.has(doc.id);
                    const missingCurrent = typesMissingCurrent.has(doc.document_type);
                    return (
                      <tr key={doc.id}>
                        <td>
                          <input
                            type="checkbox"
                            checked={isSelected}
                            onChange={() => toggleSelection(doc)}
                          />
                        </td>
                        <td>{doc.document_type.replace(/_/g, " ")}</td>
                        <td>{doc.authority}</td>
                        <td>{doc.status}</td>
                        <td>{doc.expires_on ? new Date(doc.expires_on).toLocaleDateString() : "—"}</td>
                        <td>
                          {doc.file_original_name || "No evidence uploaded"}
                          {missingCurrent && (
                            <span style={{ marginLeft: 8 }} className="badge badge--warning">
                              Expired / no current
                            </span>
                          )}
                        </td>
                        <td>
                          <button
                            type="button"
                            className="secondary-chip-btn"
                            onClick={() => handleDownload(doc)}
                            disabled={!doc.file_storage_path}
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
                  {documents.length === 0 && (
                    <tr>
                      <td colSpan={7} className="text-center text-muted">
                        No documents found for this aircraft.
                      </td>
                    </tr>
                  )}
                </tbody>
              </table>
              <div style={{ display: "flex", gap: 8, marginTop: 12, flexWrap: "wrap" }}>
                <button
                  type="button"
                  className="btn btn-primary"
                  onClick={handleDownloadSelected}
                  disabled={selectedDocumentIds.size === 0}
                >
                  Download selected
                </button>
                <button
                  type="button"
                  className="btn btn-secondary"
                  onClick={() => setSelectedDocumentIds(new Set())}
                >
                  Clear selection
                </button>
                <button
                  type="button"
                  className="btn btn-secondary"
                  onClick={() => {
                    const defaults = new Set<number>();
                    currentByType.forEach((doc) => {
                      if (doc) defaults.add(doc.id);
                    });
                    setSelectedDocumentIds(defaults);
                  }}
                >
                  Select current
                </button>
                {downloadProgress?.bundle && (
                  <div style={{ marginLeft: "auto", minWidth: 220 }}>
                    {downloadProgress.progress.percent !== undefined && (
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
              </div>
            </div>
          )}
        </div>
      </section>
    </DepartmentLayout>
  );
};

export default AircraftDocumentsPage;
