import React, { useMemo } from "react";
import { useNavigate, useParams } from "react-router-dom";
import { useQueries, useQuery } from "@tanstack/react-query";
import QualityAuditsSectionLayout from "./qualityAudits/QualityAuditsSectionLayout";
import { getContext } from "../services/auth";
import { getApiBaseUrl } from "../services/config";
import { qmsListAudits, qmsListCars, qmsListCarAttachments, type CARAttachmentOut } from "../services/qms";

type EvidenceRow = {
  id: string;
  filename: string;
  contentType: string;
  sizeBytes: number | null;
  source: "CAR" | "AUDIT_REPORT" | "AUDIT_CHECKLIST";
  sourceLabel: string;
  reviewUrl: string;
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
  const params = useParams<{ amoCode?: string }>();
  const ctx = getContext();
  const navigate = useNavigate();
  const amoCode = params.amoCode ?? ctx.amoCode ?? "UNKNOWN";
  const department = ctx.department ?? "quality";

  const cars = useQuery({ queryKey: ["qms-cars", "evidence"], queryFn: () => qmsListCars({}) });
  const audits = useQuery({ queryKey: ["qms-audits", "evidence"], queryFn: () => qmsListAudits({ domain: "AMO" }) });

  const attachmentQueries = useQueries({
    queries: (cars.data ?? []).map((car) => ({
      queryKey: ["car-attachments", car.id],
      queryFn: () => qmsListCarAttachments(car.id),
      staleTime: 60_000,
    })),
  });

  const evidenceRows = useMemo(() => {
    const rows: EvidenceRow[] = [];

    (cars.data ?? []).forEach((car, idx) => {
      const attachments = attachmentQueries[idx]?.data ?? [];
      attachments.forEach((file: CARAttachmentOut) => {
        rows.push({
          id: file.id,
          filename: file.filename,
          contentType: asContentType(file.filename, file.content_type),
          sizeBytes: file.size_bytes,
          source: "CAR",
          sourceLabel: `${car.car_number} · ${car.title}`,
          reviewUrl: file.download_url,
        });
      });
    });

    (audits.data ?? []).forEach((audit) => {
      if (audit.report_file_ref) {
        rows.push({
          id: `audit-report-${audit.id}`,
          filename: `${audit.audit_ref}-report.pdf`,
          contentType: "application/pdf",
          sizeBytes: null,
          source: "AUDIT_REPORT",
          sourceLabel: `${audit.audit_ref} · ${audit.title}`,
          reviewUrl: `${getApiBaseUrl()}/quality/audits/${audit.id}/report`,
        });
      }
      if (audit.checklist_file_ref) {
        rows.push({
          id: `audit-checklist-${audit.id}`,
          filename: `${audit.audit_ref}-checklist.pdf`,
          contentType: "application/pdf",
          sizeBytes: null,
          source: "AUDIT_CHECKLIST",
          sourceLabel: `${audit.audit_ref} · ${audit.title}`,
          reviewUrl: `${getApiBaseUrl()}/quality/audits/${audit.id}/checklist`,
        });
      }
    });

    return rows.sort((a, b) => a.filename.localeCompare(b.filename));
  }, [attachmentQueries, audits.data, cars.data]);

  return (
    <QualityAuditsSectionLayout title="Evidence Library" subtitle="Inline review for audit evidence, reports, and checklists.">
      <div className="qms-card" style={{ marginBottom: 12 }}>
        <p style={{ margin: 0 }}>
          Open evidence inline (PDF/image), add reviewer markers, and export a reviewed copy log for audit traceability.
        </p>
      </div>

      <div className="qms-card">
        <table className="table">
          <thead>
            <tr>
              <th>File</th>
              <th>Type</th>
              <th>Source</th>
              <th>Size</th>
              <th>Actions</th>
            </tr>
          </thead>
          <tbody>
            {evidenceRows.map((file) => (
              <tr key={file.id}>
                <td><strong>{file.filename}</strong></td>
                <td>{file.contentType}</td>
                <td>{file.sourceLabel}</td>
                <td>{fmtBytes(file.sizeBytes)}</td>
                <td>
                  <button
                    type="button"
                    className="secondary-chip-btn"
                    onClick={() =>
                      navigate(
                        `/maintenance/${amoCode}/${department}/qms/evidence/${file.id}?name=${encodeURIComponent(file.filename)}&mime=${encodeURIComponent(file.contentType)}&url=${encodeURIComponent(file.reviewUrl)}&source=${encodeURIComponent(file.sourceLabel)}`
                      )
                    }
                  >
                    Open viewer
                  </button>
                </td>
              </tr>
            ))}
            {evidenceRows.length === 0 && (
              <tr>
                <td colSpan={5}>No evidence uploaded yet.</td>
              </tr>
            )}
          </tbody>
        </table>
      </div>
    </QualityAuditsSectionLayout>
  );
};

export default QualityEvidenceLibraryPage;
