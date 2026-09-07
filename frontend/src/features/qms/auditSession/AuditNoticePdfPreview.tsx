import React, { useEffect, useRef, useState } from "react";
import { Document, Page, pdfjs } from "react-pdf";

pdfjs.GlobalWorkerOptions.workerSrc = new URL("pdfjs-dist/build/pdf.worker.min.mjs", import.meta.url).toString();

type Props = {
  url: string;
  title: string;
};

const AuditNoticePdfPreview: React.FC<Props> = ({ url, title }) => {
  const hostRef = useRef<HTMLDivElement | null>(null);
  const [pageCount, setPageCount] = useState(0);
  const [pageWidth, setPageWidth] = useState(760);

  useEffect(() => {
    const host = hostRef.current;
    if (!host) return;
    const updateWidth = () => setPageWidth(Math.max(280, Math.min(900, host.clientWidth - 28)));
    updateWidth();
    const observer = new ResizeObserver(updateWidth);
    observer.observe(host);
    return () => observer.disconnect();
  }, []);

  return (
    <div ref={hostRef} className="qms-audit-notice-pdf" aria-label={title}>
      <Document
        key={url}
        file={url}
        loading={<p>Loading the controlled PDF…</p>}
        error={<p role="alert">The controlled PDF could not be rendered. Download it to inspect the stored file.</p>}
        onLoadSuccess={({ numPages }) => setPageCount(numPages)}
      >
        {Array.from({ length: pageCount }, (_, index) => (
          <Page
            key={`notice-page-${index + 1}`}
            pageNumber={index + 1}
            width={pageWidth}
            renderAnnotationLayer={false}
            renderTextLayer={false}
          />
        ))}
      </Document>
    </div>
  );
};

export default AuditNoticePdfPreview;
