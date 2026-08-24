import React, { useEffect, useMemo, useState } from "react";
import { Link, useParams, useSearchParams } from "react-router-dom";
import { Document, Page, pdfjs } from "react-pdf";
import { ArrowLeft, FileText, Link2 } from "lucide-react";
import { authHeaders, getContext } from "../services/auth";
import QualityAuditsSectionLayout from "./qualityAudits/QualityAuditsSectionLayout";
import "./qualityAudits/quality-evidence-viewer.css";

pdfjs.GlobalWorkerOptions.workerSrc = new URL("pdfjs-dist/build/pdf.worker.min.mjs", import.meta.url).toString();

type ReviewMarker = {
  id: string;
  page: number;
  note: string;
  reference: string;
  xPct?: number;
  yPct?: number;
  createdAt: string;
};

const PdfPage = Page as unknown as React.FC<any>;

const QualityEvidenceViewerPage: React.FC = () => {
  const params = useParams<{ evidenceId?: string; amoCode?: string }>();
  const [searchParams] = useSearchParams();
  const ctx = getContext();
  const amoCode = params.amoCode ?? ctx.amoCode ?? "UNKNOWN";
  const evidenceId = params.evidenceId ?? "unknown";
  const fileName = searchParams.get("name") ?? `evidence-${evidenceId}`;
  const mime = searchParams.get("mime") ?? "application/octet-stream";
  const fileUrl = searchParams.get("url") ?? "";
  const source = searchParams.get("source") ?? "Unknown";
  const auditRef = searchParams.get("auditRef") ?? searchParams.get("audit") ?? "";
  const findingRef = searchParams.get("findingRef") ?? searchParams.get("finding") ?? "";

  const [resolvedUrl, setResolvedUrl] = useState<string>("");
  const [pageCount, setPageCount] = useState(1);
  const [pageNumber, setPageNumber] = useState(1);
  const [zoom, setZoom] = useState(1);
  const [note, setNote] = useState("");
  const [reference, setReference] = useState("");
  const [clickPoint, setClickPoint] = useState<{ xPct: number; yPct: number } | null>(null);
  const [markers, setMarkers] = useState<ReviewMarker[]>([]);

  const reviewKey = `qms-evidence-review-${evidenceId}`;
  const vaultHref = `/maintenance/${amoCode}/quality/evidence-vault`;
  const registerHref = `/maintenance/${amoCode}/quality/audits/register?tab=findings`;

  useEffect(() => {
    if (!fileUrl) return;
    let cancelled = false;
    let objectUrl = "";

    const load = async () => {
      try {
        const res = await fetch(fileUrl, {
          headers: authHeaders(),
          credentials: "include",
        });
        if (!res.ok) throw new Error("Unable to open file for inline review.");
        const blob = await res.blob();
        objectUrl = URL.createObjectURL(blob);
        if (!cancelled) setResolvedUrl(objectUrl);
      } catch {
        if (!cancelled) {
          setResolvedUrl(fileUrl);
        }
      }
    };

    void load();
    return () => {
      cancelled = true;
      if (objectUrl) URL.revokeObjectURL(objectUrl);
    };
  }, [fileUrl]);

  useEffect(() => {
    const raw = window.localStorage.getItem(reviewKey);
    if (!raw) return;
    try {
      const parsed = JSON.parse(raw) as ReviewMarker[];
      setMarkers(parsed);
    } catch {
      setMarkers([]);
    }
  }, [reviewKey]);

  const isPdf = mime.includes("pdf") || fileName.toLowerCase().endsWith(".pdf");
  const isImage = mime.startsWith("image/");
  const isWord =
    mime.includes("word") || fileName.toLowerCase().endsWith(".doc") || fileName.toLowerCase().endsWith(".docx");

  const sortedMarkers = useMemo(
    () => [...markers].sort((a, b) => (a.page - b.page) || a.createdAt.localeCompare(b.createdAt)),
    [markers]
  );

  const saveMarkers = (next: ReviewMarker[]) => {
    setMarkers(next);
    window.localStorage.setItem(reviewKey, JSON.stringify(next));
  };

  const addMarker = () => {
    if (!note.trim()) return;
    const next: ReviewMarker[] = [
      ...markers,
      {
        id: crypto.randomUUID(),
        page: pageNumber,
        note: note.trim(),
        reference: reference.trim(),
        xPct: clickPoint?.xPct,
        yPct: clickPoint?.yPct,
        createdAt: new Date().toISOString(),
      },
    ];
    saveMarkers(next);
    setNote("");
    setReference("");
    setClickPoint(null);
  };

  const exportReviewCopy = () => {
    const payload = {
      evidenceId,
      fileName,
      mime,
      source,
      auditRef: auditRef || undefined,
      findingRef: findingRef || undefined,
      reviewedAt: new Date().toISOString(),
      markers: sortedMarkers,
    };
    const blob = new Blob([JSON.stringify(payload, null, 2)], { type: "application/json" });
    const url = URL.createObjectURL(blob);
    const a = document.createElement("a");
    a.href = url;
    a.download = `${fileName.replace(/\.[^/.]+$/, "")}.review.json`;
    document.body.appendChild(a);
    a.click();
    document.body.removeChild(a);
    URL.revokeObjectURL(url);
  };

  return (
    <QualityAuditsSectionLayout
      title="Evidence Viewer"
      subtitle="Inline review with local markup — return to vault or register without leaving Assurance."
    >
      <div className="qa-evidence-viewer">
        <div className="qa-evidence-viewer__meta">
          <div className="qa-evidence-viewer__identity">
            <FileText size={16} aria-hidden />
            <div>
              <strong title={fileName}>{fileName}</strong>
              <small title={`${source}${mime ? ` · ${mime}` : ""} · ${evidenceId}`}>
                {source}
                {mime ? ` · ${mime}` : ""}
                {` · ${evidenceId}`}
              </small>
            </div>
          </div>
          <div className="qa-evidence-viewer__links">
            <Link to={vaultHref}>
              <ArrowLeft size={13} /> Evidence vault
            </Link>
            <Link to={registerHref}>Register</Link>
            {auditRef ? (
              <span className="qa-evidence-viewer__chip" title={`Audit ${auditRef}`}>
                <Link2 size={12} /> Audit {auditRef}
              </span>
            ) : null}
            {findingRef ? <span className="qa-evidence-viewer__chip" title={`Finding ${findingRef}`}>Finding {findingRef}</span> : null}
            {!auditRef && !findingRef ? (
              <span className="qa-evidence-viewer__chip qa-evidence-viewer__chip--muted">No audit/finding link in URL</span>
            ) : null}
          </div>
        </div>

        <div className="qa-evidence-viewer__grid">
          <section className="qa-evidence-viewer__preview" aria-label="Evidence preview">
            <div className="qa-evidence-viewer__toolbar">
              {isPdf ? (
                <>
                  <button type="button" className="secondary-chip-btn" onClick={() => setPageNumber((p) => Math.max(1, p - 1))}>
                    Prev
                  </button>
                  <button type="button" className="secondary-chip-btn" onClick={() => setPageNumber((p) => Math.min(pageCount, p + 1))}>
                    Next
                  </button>
                  <button type="button" className="secondary-chip-btn" onClick={() => setZoom((z) => Math.max(0.6, z - 0.1))}>
                    −
                  </button>
                  <button type="button" className="secondary-chip-btn" onClick={() => setZoom((z) => Math.min(2, z + 0.1))}>
                    +
                  </button>
                  <span className="text-muted">
                    Page {pageNumber}/{pageCount}
                  </span>
                </>
              ) : null}
              <a className="secondary-chip-btn" href={fileUrl || resolvedUrl} target="_blank" rel="noreferrer">
                Open original
              </a>
            </div>

            {isPdf && resolvedUrl ? (
              <div
                className="qa-evidence-viewer__canvas"
                onClick={(e) => {
                  const rect = (e.currentTarget as HTMLDivElement).getBoundingClientRect();
                  const xPct = ((e.clientX - rect.left) / rect.width) * 100;
                  const yPct = ((e.clientY - rect.top) / rect.height) * 100;
                  setClickPoint({ xPct: Number(xPct.toFixed(2)), yPct: Number(yPct.toFixed(2)) });
                }}
              >
                <Document file={resolvedUrl} onLoadSuccess={(doc) => setPageCount(doc.numPages)}>
                  <PdfPage pageNumber={pageNumber} width={Math.floor(900 * zoom)} renderTextLayer renderAnnotationLayer />
                </Document>
              </div>
            ) : isImage && resolvedUrl ? (
              <img className="qa-evidence-viewer__image" src={resolvedUrl} alt={fileName} />
            ) : isWord ? (
              <div className="qa-evidence-viewer__empty">
                <p>Word files do not render inline here. Capture markup references, then open the original for full content.</p>
              </div>
            ) : (
              <div className="qa-evidence-viewer__empty">
                <p>Inline preview unavailable for this file type. Use Open original.</p>
              </div>
            )}
          </section>

          <aside className="qa-evidence-viewer__side" aria-label="Reviewer markup">
            <header>
              <strong>Reviewer markup</strong>
              <small>Local only — not saved to the server</small>
            </header>
            <label className="qms-field">
              Page / section reference
              <input className="input" value={reference} onChange={(e) => setReference(e.target.value)} placeholder="Page 4, paragraph 2" />
            </label>
            <label className="qms-field">
              Review note
              <textarea rows={3} value={note} onChange={(e) => setNote(e.target.value)} placeholder="Finding, requirement, impact" />
            </label>
            <p className="text-muted">
              {clickPoint
                ? `Selected point: X ${clickPoint.xPct}% · Y ${clickPoint.yPct}%`
                : "Optional: click the PDF preview to capture a point marker."}
            </p>
            <div className="qa-evidence-viewer__side-actions">
              <button type="button" className="btn btn-primary" onClick={addMarker}>
                Add markup
              </button>
              <button type="button" className="secondary-chip-btn" onClick={exportReviewCopy}>
                Export reviewed copy
              </button>
            </div>
            <div className="qa-evidence-viewer__markers">
              {sortedMarkers.map((marker) => (
                <article key={marker.id}>
                  <strong>Page {marker.page}</strong>
                  <p>{marker.note}</p>
                  {marker.reference ? <small>Ref: {marker.reference}</small> : null}
                  {typeof marker.xPct === "number" && typeof marker.yPct === "number" ? (
                    <small>
                      Point: {marker.xPct}%, {marker.yPct}%
                    </small>
                  ) : null}
                  <button type="button" className="secondary-chip-btn" onClick={() => saveMarkers(markers.filter((item) => item.id !== marker.id))}>
                    Remove
                  </button>
                </article>
              ))}
              {sortedMarkers.length === 0 ? <p className="text-muted">No markup yet.</p> : null}
            </div>
          </aside>
        </div>
      </div>
    </QualityAuditsSectionLayout>
  );
};

export default QualityEvidenceViewerPage;
