import { useMemo, useState } from "react";
import { Document, Page, pdfjs } from "react-pdf";
import { authHeaders } from "../../services/auth";
import { getApiBaseUrl } from "../../services/config";
import "react-pdf/dist/Page/AnnotationLayer.css";
import "react-pdf/dist/Page/TextLayer.css";

pdfjs.GlobalWorkerOptions.workerSrc = new URL("pdfjs-dist/build/pdf.worker.min.mjs", import.meta.url).toString();

export default function RecordPdfPreview({ tenant, recordId }: { tenant: string; recordId: string }) {
  const [pageCount, setPageCount] = useState(0);
  const [page, setPage] = useState(1);
  const [zoom, setZoom] = useState(1);
  const file = useMemo(() => ({
    url: `${getApiBaseUrl()}/doc-control/workspace/t/${encodeURIComponent(tenant.toLowerCase())}/records/${encodeURIComponent(recordId)}/content`,
    httpHeaders: Object.fromEntries(new Headers(authHeaders()).entries()),
    withCredentials: true,
  }), [tenant, recordId]);
  return <div className="records-vault__pdf">
    <div className="records-vault__pdf-controls">
      <button type="button" className="dc-button" disabled={page <= 1} onClick={() => setPage((current) => current - 1)}>Previous</button>
      <label>Page <input type="number" min={1} max={pageCount || 1} value={page} onChange={(event) => setPage(Math.max(1, Math.min(pageCount || 1, Number(event.target.value) || 1)))} /> of {pageCount || "…"}</label>
      <button type="button" className="dc-button" disabled={page >= pageCount} onClick={() => setPage((current) => current + 1)}>Next</button>
      <button type="button" className="dc-button" onClick={() => setZoom((current) => Math.max(.5, current - .25))}>−</button>
      <span>{Math.round(zoom * 100)}%</span>
      <button type="button" className="dc-button" onClick={() => setZoom((current) => Math.min(2, current + .25))}>+</button>
    </div>
    <Document file={file} loading="Loading PDF…" error="PDF preview unavailable. Download the original to view it." onLoadSuccess={({ numPages }: { numPages: number }) => setPageCount(numPages)}>
      <Page pageNumber={page} width={Math.round(680 * zoom)} renderTextLayer renderAnnotationLayer={false} />
    </Document>
  </div>;
}
