import React, { useMemo, useState } from "react";
import { useNavigate, useParams } from "react-router-dom";
import { useQuery } from "@tanstack/react-query";
import { Download, Eye, FileText, Filter, Link2 } from "lucide-react";
import SpreadsheetToolbar from "../components/shared/SpreadsheetToolbar";
import { useDensityPreference } from "../hooks/useDensityPreference";
import QualityAuditsSectionLayout from "./qualityAudits/QualityAuditsSectionLayout";
import { getContext } from "../services/auth";
import { getApiBaseUrl } from "../services/config";
import { qmsListAudits, qmsListCars, qmsListCarAttachmentsBulk, qmsListFindingsBulk, type CARAttachmentOut } from "../services/qms";

type EvidenceRow = {
  id: string;
  ref: string;
  title: string;
  auditTitle: string;
  auditId?: string;
  type: string;
  sizeBytes: number | null;
  updatedLabel: string;
  filename: string;
  reviewUrl: string;
  mime: string;
  source: string;
};

const fmtBytes = (value: number | null): string => {
  if (!value || value <= 0) return "—";
  if (value < 1024) return `${value} B`;
  if (value < 1024 * 1024) return `${(value / 1024).toFixed(1)} KB`;
  return `${(value / (1024 * 1024)).toFixed(1)} MB`;
};

const asContentType = (fileName: string, contentType?: string | null): string => {
  if (contentType) return contentType;
  const lower = fileName.toLowerCase();
  if (lower.endsWith(".pdf")) return "application/pdf";
  if (lower.endsWith(".docx")) return "application/vnd.openxmlformats-officedocument.wordprocessingml.document";
  if (lower.endsWith(".doc")) return "application/msword";
  if (lower.endsWith(".png")) return "image/png";
  if (lower.endsWith(".jpg") || lower.endsWith(".jpeg")) return "image/jpeg";
  return "application/octet-stream";
};

const QualityEvidenceLibraryPage: React.FC = () => {
  const params = useParams<{ amoCode?: string; department?: string }>();
  const ctx = getContext();
  const navigate = useNavigate();
  const amoCode = params.amoCode ?? ctx.amoCode ?? "UNKNOWN";
  const department = params.department ?? ctx.department ?? "quality";
  const [wrapText, setWrapText] = useState(false);
  const [showFilters, setShowFilters] = useState(true);
  const [quickFilter, setQuickFilter] = useState("");
  const [headerFilters, setHeaderFilters] = useState({ ref: "", type: "", audit: "" });
  const { density, setDensity } = useDensityPreference("evidence-library", "compact");

  const cars = useQuery({ queryKey: ["qms-cars", "evidence"], queryFn: () => qmsListCars({}), staleTime: 60_000 });
  const audits = useQuery({ queryKey: ["qms-audits", "evidence"], queryFn: () => qmsListAudits({ domain: "AMO" }), staleTime: 60_000 });

  const findings = useQuery({
    queryKey: ["qms-findings", "evidence", amoCode],
    queryFn: () => qmsListFindingsBulk({ domain: "AMO" }),
    staleTime: 60_000,
  });

  const attachments = useQuery({
    queryKey: ["car-attachments", "bulk", amoCode],
    queryFn: () => qmsListCarAttachmentsBulk({ car_ids: (cars.data ?? []).map((car) => car.id) }),
    enabled: (cars.data?.length ?? 0) > 0,
    staleTime: 60_000,
  });

  const evidenceRows = useMemo(() => {
    const rows: EvidenceRow[] = [];
    const auditByFindingId = new Map<string, { auditId: string; auditRef: string; auditTitle: string }>();

    const auditById = new Map((audits.data ?? []).map((audit) => [audit.id, audit]));
    (findings.data ?? []).forEach((finding) => {
      const audit = auditById.get(finding.audit_id);
      if (audit) {
        auditByFindingId.set(finding.id, { auditId: audit.id, auditRef: audit.audit_ref, auditTitle: audit.title });
      }
    });

    const attachmentsByCar = new Map<string, CARAttachmentOut[]>();
    (attachments.data ?? []).forEach((attachment) => {
      const bucket = attachmentsByCar.get(attachment.car_id) ?? [];
      bucket.push(attachment);
      attachmentsByCar.set(attachment.car_id, bucket);
    });

    (cars.data ?? []).forEach((car) => {
      const auditContext = car.finding_id ? auditByFindingId.get(car.finding_id) : undefined;
      const carAttachments = attachmentsByCar.get(car.id) ?? [];
      carAttachments.forEach((file: CARAttachmentOut) => {
        rows.push({
          id: file.id,
          ref: auditContext?.auditRef || car.car_number,
          title: car.title,
          auditTitle: auditContext?.auditTitle || `CAR ${car.car_number}`,
          auditId: auditContext?.auditId,
          type: "CAR evidence",
          sizeBytes: file.size_bytes,
          updatedLabel: file.uploaded_at ? new Date(file.uploaded_at).toLocaleString() : "—",
          filename: file.filename,
          reviewUrl: file.download_url,
          mime: asContentType(file.filename, file.content_type),
          source: `${car.car_number} · ${car.title}`,
        });
      });
    });

    (audits.data ?? []).forEach((audit) => {
      if (audit.report_file_ref) {
        rows.push({
          id: `audit-report-${audit.id}`,
          ref: audit.audit_ref,
          title: `${audit.title} report`,
          auditTitle: audit.title,
          auditId: audit.id,
          type: "Audit report",
          sizeBytes: null,
          updatedLabel: audit.actual_end || audit.planned_end || audit.created_at,
          filename: `${audit.audit_ref}-report.pdf`,
          reviewUrl: `${getApiBaseUrl()}/quality/audits/${audit.id}/report`,
          mime: "application/pdf",
          source: `${audit.audit_ref} report`,
        });
      }
      if (audit.checklist_file_ref) {
        rows.push({
          id: `audit-checklist-${audit.id}`,
          ref: audit.audit_ref,
          title: `${audit.title} checklist`,
          auditTitle: audit.title,
          auditId: audit.id,
          type: "Checklist",
          sizeBytes: null,
          updatedLabel: audit.planned_end || audit.created_at,
          filename: `${audit.audit_ref}-checklist.pdf`,
          reviewUrl: `${getApiBaseUrl()}/quality/audits/${audit.id}/checklist`,
          mime: "application/pdf",
          source: `${audit.audit_ref} checklist`,
        });
      }
    });

    return rows.sort((a, b) => a.ref.localeCompare(b.ref) || a.title.localeCompare(b.title));
  }, [attachments.data, audits.data, cars.data, findings.data]);

  const filteredRows = useMemo(() => {
    const q = quickFilter.trim().toLowerCase();
    return evidenceRows.filter((row) => {
      if (q && !`${row.ref} ${row.title} ${row.auditTitle} ${row.type} ${row.filename}`.toLowerCase().includes(q)) return false;
      if (headerFilters.ref && !row.ref.toLowerCase().includes(headerFilters.ref.toLowerCase())) return false;
      if (headerFilters.type && !row.type.toLowerCase().includes(headerFilters.type.toLowerCase())) return false;
      if (headerFilters.audit && !`${row.auditTitle} ${row.source}`.toLowerCase().includes(headerFilters.audit.toLowerCase())) return false;
      return true;
    });
  }, [evidenceRows, headerFilters, quickFilter]);

  const loading = cars.isLoading || audits.isLoading || findings.isLoading || attachments.isLoading;

  const openViewer = (file: EvidenceRow) => {
    navigate(`/maintenance/${amoCode}/${department}/qms/evidence/${file.id}?name=${encodeURIComponent(file.filename)}&mime=${encodeURIComponent(file.mime)}&url=${encodeURIComponent(file.reviewUrl)}&source=${encodeURIComponent(file.source)}`);
  };

  const copyLink = async (file: EvidenceRow) => {
    if (navigator.clipboard?.writeText) {
      await navigator.clipboard.writeText(file.reviewUrl);
    }
  };

  return (
    <QualityAuditsSectionLayout title="Evidence Library" subtitle="Evidence browser with audit-first hierarchy, compact scanning, and reviewer actions.">
      <div className="audit-workspace">
        <div className="audit-workspace__toolbar-row">
          <label className="audit-search" aria-label="Filter evidence rows">
            <Filter size={15} />
            <input
              value={quickFilter}
              onChange={(event) => setQuickFilter(event.target.value)}
              placeholder="Filter by reference, evidence title, audit, file name, or type"
            />
          </label>
          <SpreadsheetToolbar
            density={density}
            onDensityChange={setDensity}
            wrapText={wrapText}
            onWrapTextChange={setWrapText}
            showFilters={showFilters}
            onShowFiltersChange={setShowFilters}
          />
        </div>

        <div className="audit-panel">
          <div className="audit-panel__header">
            <div>
              <h2 className="audit-panel__title">Evidence browser</h2>
              <p className="audit-panel__subtitle">Human-friendly audit references first, raw filenames demoted to secondary metadata.</p>
            </div>
            <span className="qms-pill">{filteredRows.length} files</span>
          </div>
          <div className="table-wrapper">
            <table className={`table ${density === "compact" ? "table-row--compact" : "table-row--comfortable"} ${wrapText ? "table--wrap" : ""}`}>
              <thead>
                <tr>
                  <th>Ref</th>
                  <th>Title / Evidence</th>
                  <th>Audit</th>
                  <th>Type</th>
                  <th>Size</th>
                  <th>Updated</th>
                  <th>Actions</th>
                </tr>
                {showFilters ? (
                  <tr>
                    <th><input className="input" placeholder="Reference" value={headerFilters.ref} onChange={(event) => setHeaderFilters((current) => ({ ...current, ref: event.target.value }))} /></th>
                    <th />
                    <th><input className="input" placeholder="Audit / source" value={headerFilters.audit} onChange={(event) => setHeaderFilters((current) => ({ ...current, audit: event.target.value }))} /></th>
                    <th><input className="input" placeholder="Type" value={headerFilters.type} onChange={(event) => setHeaderFilters((current) => ({ ...current, type: event.target.value }))} /></th>
                    <th />
                    <th />
                    <th />
                  </tr>
                ) : null}
              </thead>
              <tbody>
                {loading ? (
                  <tr><td colSpan={7}>Loading evidence library…</td></tr>
                ) : filteredRows.length === 0 ? (
                  <tr><td colSpan={7}>No evidence uploaded yet.</td></tr>
                ) : filteredRows.map((file) => (
                  <tr key={file.id}>
                    <td>{file.ref}</td>
                    <td>
                      <strong>{file.title}</strong>
                      <div className="text-muted">{file.filename}</div>
                    </td>
                    <td>
                      <div>{file.auditTitle}</div>
                      <div className="text-muted">{file.source}</div>
                    </td>
                    <td><span className="qms-pill">{file.type}</span></td>
                    <td>{fmtBytes(file.sizeBytes)}</td>
                    <td>{file.updatedLabel}</td>
                    <td>
                      <div className="audit-chip-list">
                        <button type="button" aria-label={`Open viewer for ${file.title}`} onClick={() => openViewer(file)} className="secondary-chip-btn"><Eye size={14} /> Open</button>
                        <a aria-label={`Download ${file.title}`} href={file.reviewUrl} target="_blank" rel="noreferrer" className="secondary-chip-btn"><Download size={14} /> Download</a>
                        <button type="button" aria-label={`Copy link for ${file.title}`} onClick={() => void copyLink(file)} className="secondary-chip-btn"><Link2 size={14} /> Copy</button>
                        {file.auditId ? <button type="button" aria-label={`View audit for ${file.title}`} onClick={() => navigate(`/maintenance/${amoCode}/${department}/qms/audits/${file.auditId}`)} className="secondary-chip-btn"><FileText size={14} /> Audit</button> : null}
                      </div>
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        </div>
      </div>
    </QualityAuditsSectionLayout>
  );
};

export default QualityEvidenceLibraryPage;
