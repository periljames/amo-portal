import React, { useMemo, useState } from "react";
import { useNavigate, useParams } from "react-router-dom";
import { useQuery } from "@tanstack/react-query";
import { Copy, Download, Eye, FileText, Files, Filter, Link2 } from "lucide-react";
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
  const cellPadding = density === "compact" ? "px-3 py-2 text-xs" : "px-4 py-3 text-sm";
  const controlHeight = density === "compact" ? "h-8 text-xs" : "h-10 text-sm";
  const textBehavior = wrapText ? "whitespace-normal break-words" : "truncate whitespace-nowrap";

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
      <div className="space-y-3">
        <div className="grid gap-3 lg:grid-cols-[minmax(0,1fr)_auto] lg:items-center">
          <div className="flex min-w-0 items-center gap-2 rounded-2xl border border-slate-800 bg-slate-900/70 px-3 py-2">
            <Filter className="h-4 w-4 text-slate-500" />
            <input
              value={quickFilter}
              onChange={(event) => setQuickFilter(event.target.value)}
              placeholder="Filter by reference, evidence title, audit, file name, or type"
              className="w-full bg-transparent text-sm text-slate-100 outline-none placeholder:text-slate-500"
            />
          </div>
          <SpreadsheetToolbar
            density={density}
            onDensityChange={setDensity}
            wrapText={wrapText}
            onWrapTextChange={setWrapText}
            showFilters={showFilters}
            onShowFiltersChange={setShowFilters}
          />
        </div>

        <div className="rounded-3xl border border-slate-800 bg-slate-900/70 shadow-[0_20px_60px_rgba(2,6,23,0.18)]">
          <div className="flex items-center justify-between border-b border-slate-800 px-4 py-3">
            <div>
              <h2 className="text-base font-semibold text-slate-50">Evidence browser</h2>
              <p className="text-sm text-slate-400">Human-friendly audit references first, raw filenames demoted to secondary metadata.</p>
            </div>
            <div className="rounded-full border border-slate-800 bg-slate-950 px-3 py-1 text-xs text-slate-400">{filteredRows.length} files</div>
          </div>

          <div className="hidden overflow-auto lg:block">
            <table className="min-w-full table-fixed text-left text-slate-200">
              <thead className="sticky top-0 z-10 bg-slate-950/95 text-[11px] uppercase tracking-[0.18em] text-slate-500">
                <tr>
                  <th className={`${cellPadding} w-[10rem]`}>Ref</th>
                  <th className={cellPadding}>Title / Evidence</th>
                  <th className={`${cellPadding} w-[14rem]`}>Audit</th>
                  <th className={`${cellPadding} w-[9rem]`}>Type</th>
                  <th className={`${cellPadding} w-[8rem]`}>Size</th>
                  <th className={`${cellPadding} w-[11rem]`}>Updated</th>
                  <th className={`${cellPadding} w-[17rem]`}>Actions</th>
                </tr>
                {showFilters ? (
                  <tr className="border-t border-slate-800/80 bg-slate-950/90">
                    {[
                      ["ref", "Reference"],
                      [null, null],
                      ["audit", "Audit / source"],
                      ["type", "Type"],
                    ].map(([key, placeholder], index) => (
                      <th key={`${key}-${index}`} className={cellPadding}>
                        {key ? (
                          <input
                            value={headerFilters[key as keyof typeof headerFilters]}
                            onChange={(event) => setHeaderFilters((current) => ({ ...current, [key]: event.target.value }))}
                            placeholder={placeholder || ""}
                            className={`w-full rounded-xl border border-slate-800 bg-slate-900 px-3 text-slate-100 placeholder:text-slate-500 ${controlHeight}`}
                          />
                        ) : null}
                      </th>
                    ))}
                    <th className={cellPadding} />
                    <th className={cellPadding} />
                    <th className={cellPadding} />
                  </tr>
                ) : null}
              </thead>
              <tbody>
                {loading ? (
                  <tr><td colSpan={7} className="px-4 py-10 text-center text-sm text-slate-500">Loading evidence library…</td></tr>
                ) : filteredRows.length === 0 ? (
                  <tr><td colSpan={7} className="px-4 py-10 text-center text-sm text-slate-500">No evidence uploaded yet.</td></tr>
                ) : filteredRows.map((file) => (
                  <tr key={file.id} className="border-t border-slate-800/80 align-top hover:bg-slate-800/30">
                    <td className={`${cellPadding} text-cyan-300`}>{file.ref}</td>
                    <td className={cellPadding}>
                      <div className={`font-medium text-slate-100 ${textBehavior}`}>{file.title}</div>
                      <div className={`mt-1 text-slate-500 ${textBehavior}`}>{file.filename}</div>
                    </td>
                    <td className={cellPadding}>
                      <div className={`font-medium text-slate-200 ${textBehavior}`}>{file.auditTitle}</div>
                      <div className={`mt-1 text-slate-500 ${textBehavior}`}>{file.source}</div>
                    </td>
                    <td className={cellPadding}><span className="inline-flex rounded-full border border-slate-800 bg-slate-950 px-2.5 py-1 text-xs text-slate-200">{file.type}</span></td>
                    <td className={cellPadding}>{fmtBytes(file.sizeBytes)}</td>
                    <td className={cellPadding}>{file.updatedLabel}</td>
                    <td className={cellPadding}>
                      <div className="flex flex-wrap gap-2">
                        <button type="button" aria-label={`Open viewer for ${file.title}`} onClick={() => openViewer(file)} className="inline-flex items-center gap-2 rounded-xl border border-slate-800 bg-slate-950 px-3 py-2 text-xs font-medium text-slate-200 transition hover:border-slate-700"><Eye className="h-3.5 w-3.5" /> Open Viewer</button>
                        <a aria-label={`Download ${file.title}`} href={file.reviewUrl} target="_blank" rel="noreferrer" className="inline-flex items-center gap-2 rounded-xl border border-slate-800 bg-slate-950 px-3 py-2 text-xs font-medium text-slate-200 transition hover:border-slate-700"><Download className="h-3.5 w-3.5" /> Download</a>
                        <button type="button" aria-label={`Copy link for ${file.title}`} onClick={() => void copyLink(file)} className="inline-flex items-center gap-2 rounded-xl border border-slate-800 bg-slate-950 px-3 py-2 text-xs font-medium text-slate-200 transition hover:border-slate-700"><Link2 className="h-3.5 w-3.5" /> Copy Link</button>
                        {file.auditId ? <button type="button" aria-label={`View audit for ${file.title}`} onClick={() => navigate(`/maintenance/${amoCode}/${department}/qms/audits/${file.auditId}`)} className="inline-flex items-center gap-2 rounded-xl border border-slate-800 bg-slate-950 px-3 py-2 text-xs font-medium text-slate-200 transition hover:border-slate-700"><FileText className="h-3.5 w-3.5" /> View Audit</button> : null}
                      </div>
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>

          <div className="grid gap-3 p-3 lg:hidden">
            {loading ? <div className="rounded-2xl border border-slate-800 bg-slate-950 px-4 py-8 text-center text-sm text-slate-500">Loading evidence library…</div> : null}
            {!loading && filteredRows.length === 0 ? <div className="rounded-2xl border border-slate-800 bg-slate-950 px-4 py-8 text-center text-sm text-slate-500">No evidence uploaded yet.</div> : null}
            {!loading && filteredRows.map((file) => (
              <article key={file.id} className="rounded-2xl border border-slate-800 bg-slate-950 p-4">
                <div className="flex items-start justify-between gap-3">
                  <div>
                    <p className="text-xs uppercase tracking-[0.18em] text-cyan-300">{file.ref}</p>
                    <h3 className="mt-1 text-sm font-semibold text-slate-100">{file.title}</h3>
                  </div>
                  <span className="inline-flex rounded-full border border-slate-800 bg-slate-900 px-2.5 py-1 text-xs text-slate-200">{file.type}</span>
                </div>
                <p className="mt-3 text-sm text-slate-300">{file.auditTitle}</p>
                <div className="mt-2 text-xs text-slate-500">{file.filename}</div>
                <div className="mt-3 flex flex-wrap gap-2 text-xs text-slate-400">
                  <span>{fmtBytes(file.sizeBytes)}</span>
                  <span>•</span>
                  <span>{file.updatedLabel}</span>
                </div>
                <div className="mt-4 flex flex-wrap gap-2">
                  <button type="button" onClick={() => openViewer(file)} className="inline-flex items-center gap-2 rounded-xl bg-cyan-500 px-3 py-2 text-xs font-medium text-slate-950"><Eye className="h-3.5 w-3.5" /> Open</button>
                  <a href={file.reviewUrl} target="_blank" rel="noreferrer" className="inline-flex items-center gap-2 rounded-xl border border-slate-800 px-3 py-2 text-xs text-slate-200"><Download className="h-3.5 w-3.5" /> Download</a>
                  {file.auditId ? <button type="button" onClick={() => navigate(`/maintenance/${amoCode}/${department}/qms/audits/${file.auditId}`)} className="inline-flex items-center gap-2 rounded-xl border border-slate-800 px-3 py-2 text-xs text-slate-200"><Files className="h-3.5 w-3.5" /> Audit</button> : null}
                  <button type="button" onClick={() => void copyLink(file)} className="inline-flex items-center gap-2 rounded-xl border border-slate-800 px-3 py-2 text-xs text-slate-200"><Copy className="h-3.5 w-3.5" /> Link</button>
                </div>
              </article>
            ))}
          </div>
        </div>
      </div>
    </QualityAuditsSectionLayout>
  );
};

export default QualityEvidenceLibraryPage;
