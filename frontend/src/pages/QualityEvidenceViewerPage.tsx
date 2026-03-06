import React, { useEffect, useMemo, useState } from "react";
import { useParams, useSearchParams } from "react-router-dom";
import { Document, Page, pdfjs } from "react-pdf";
import { authHeaders } from "../services/auth";
import QualityAuditsSectionLayout from "./qualityAudits/QualityAuditsSectionLayout";

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
  const params = useParams<{ evidenceId?: string }>();
  const [searchParams] = useSearchParams();
  const evidenceId = params.evidenceId ?? "unknown";
  const fileName = searchParams.get("name") ?? `evidence-${evidenceId}`;
  const mime = searchParams.get("mime") ?? "application/octet-stream";
  const fileUrl = searchParams.get("url") ?? "";
  const source = searchParams.get("source") ?? "Unknown";

  const [resolvedUrl, setResolvedUrl] = useState<string>("");
  const [pageCount, setPageCount] = useState(1);
  const [pageNumber, setPageNumber] = useState(1);
  const [zoom, setZoom] = useState(1);
  const [note, setNote] = useState("");
  const [reference, setReference] = useState("");
  const [clickPoint, setClickPoint] = useState<{ xPct: number; yPct: number } | null>(null);
  const [markers, setMarkers] = useState<ReviewMarker[]>([]);

  const reviewKey = `qms-evidence-review-${evidenceId}`;

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
    <QualityAuditsSectionLayout title="Evidence Viewer" subtitle="Review evidence inline, mark references, and export a reviewed copy log.">
      <div className="qms-grid" style={{ gridTemplateColumns: "2fr 1fr" }}>
        <div className="qms-card">
          <div className="qms-header__actions" style={{ marginBottom: 8 }}>
            <span className="qms-pill">{fileName}</span>
            <span className="qms-pill">{source}</span>
            {isPdf ? (
              <>
                <button type="button" className="secondary-chip-btn" onClick={() => setPageNumber((p) => Math.max(1, p - 1))}>Prev page</button>
                <button type="button" className="secondary-chip-btn" onClick={() => setPageNumber((p) => Math.min(pageCount, p + 1))}>Next page</button>
                <button type="button" className="secondary-chip-btn" onClick={() => setZoom((z) => Math.max(0.6, z - 0.1))}>-</button>
                <button type="button" className="secondary-chip-btn" onClick={() => setZoom((z) => Math.min(2, z + 0.1))}>+</button>
                <span className="text-muted">Page {pageNumber}/{pageCount}</span>
              </>
            ) : null}
            <a className="secondary-chip-btn" href={fileUrl || resolvedUrl} target="_blank" rel="noreferrer">Open original</a>
          </div>

          {isPdf && resolvedUrl ? (
            <div
              style={{ overflow: "auto", border: "1px solid var(--line)", borderRadius: 8, padding: 8 }}
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
            <img src={resolvedUrl} alt={fileName} style={{ maxWidth: "100%", borderRadius: 8, border: "1px solid var(--line)" }} />
          ) : isWord ? (
            <div className="qms-card" style={{ margin: 0 }}>
              <p>
                Word files do not have full inline rendering in this secure viewer yet. Use reviewer markers to record page/section references,
                then open original for full content check.
              </p>
            </div>
          ) : (
            <p>Inline preview unavailable for this file type. Use “Open original”.</p>
          )}
        </div>

        <div className="qms-card">
          <h3 style={{ marginTop: 0 }}>Reviewer Markup</h3>
          <p className="text-muted">Capture the exact issue/reference for closeout traceability.</p>
          <label className="qms-field">
            Page/section reference
            <input className="input" value={reference} onChange={(e) => setReference(e.target.value)} placeholder="Page 4, paragraph 2" />
          </label>
          <label className="qms-field">
            Review note
            <textarea rows={3} value={note} onChange={(e) => setNote(e.target.value)} placeholder="State finding, expected requirement, and impact." />
          </label>
          {clickPoint ? (
            <p className="text-muted">Selected point: X {clickPoint.xPct}% · Y {clickPoint.yPct}%</p>
          ) : (
            <p className="text-muted">Optional: click inside PDF preview to capture a point marker.</p>
          )}
          <div className="qms-header__actions">
            <button type="button" className="btn btn-primary" onClick={addMarker}>Add markup</button>
            <button type="button" className="secondary-chip-btn" onClick={exportReviewCopy}>Export reviewed copy</button>
          </div>

          <div style={{ marginTop: 12 }}>
            {sortedMarkers.map((marker) => (
              <div key={marker.id} className="qms-dashboard-card" style={{ marginBottom: 8 }}>
                <strong>Page {marker.page}</strong>
                <p style={{ margin: "4px 0" }}>{marker.note}</p>
                {marker.reference ? <p className="text-muted" style={{ margin: 0 }}>Ref: {marker.reference}</p> : null}
                {typeof marker.xPct === "number" && typeof marker.yPct === "number" ? (
                  <p className="text-muted" style={{ margin: 0 }}>Point: {marker.xPct}%, {marker.yPct}%</p>
                ) : null}
                <button
                  type="button"
                  className="secondary-chip-btn"
                  onClick={() => saveMarkers(markers.filter((item) => item.id !== marker.id))}
                >
                  Remove
                </button>
              </div>
            ))}
            {sortedMarkers.length === 0 ? <p className="text-muted">No markup yet.</p> : null}
          </div>
        </div>
      </div>
    </QualityAuditsSectionLayout>
  );
};

export default QualityEvidenceViewerPage;
