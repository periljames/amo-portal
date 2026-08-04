import { useEffect, useMemo, useState } from "react";

import { getPdfReaderCapabilities, type PdfReaderCapabilities } from "../../services/pdfReader";
import "./pdfReaderOperationalFixes.css";
import PdfReaderCoreV2, {
  type PdfReaderCoreProps,
  type PdfReaderNavigationRequest,
  type PdfReaderOutlineItem,
} from "./PdfReaderCoreV2";

const READ_ONLY_FALLBACK: PdfReaderCapabilities = {
  renderer: "PDF.js",
  processor: "PDFium",
  processor_version: "unavailable",
  source_sha256: "",
  page_count: 0,
  has_acroform: false,
  has_javascript: false,
  is_dynamic_xfa: false,
  encrypted: false,
  unsupported_reason: "PDF form capabilities could not be verified. The document is open in read-only mode.",
  can_fill: false,
  can_save_draft: false,
  can_download_original: true,
  can_download_working: false,
  can_flatten: false,
  can_submit: false,
};

function readOnlyFallback(error: unknown): PdfReaderCapabilities {
  const detail = error instanceof Error && error.message.trim()
    ? error.message.trim()
    : "PDF form capabilities could not be verified";
  return {
    ...READ_ONLY_FALLBACK,
    unsupported_reason: `${detail}. The document remains available in read-only mode.`,
  };
}

/**
 * Resolve the immutable-source capability contract before PDF.js paints a page.
 * Scripted sources receive a server-generated, script-disabled reader derivative;
 * the exact controlled original remains the download source.
 */
export default function PdfReaderCore(props: PdfReaderCoreProps) {
  const suppliedCapabilities = props.capabilities;
  const externallyManaged = suppliedCapabilities !== undefined;
  const [resolvedCapabilities, setResolvedCapabilities] = useState<PdfReaderCapabilities | null>(
    suppliedCapabilities ?? null,
  );

  useEffect(() => {
    if (externallyManaged) {
      setResolvedCapabilities(suppliedCapabilities ?? null);
      return;
    }

    let active = true;
    setResolvedCapabilities(null);
    getPdfReaderCapabilities(
      props.identity.tenant,
      props.identity.manualId,
      props.identity.revisionId,
    )
      .then((capabilities) => {
        if (!active) return;
        setResolvedCapabilities(capabilities);
      })
      .catch((error) => {
        if (!active) return;
        setResolvedCapabilities(readOnlyFallback(error));
      });

    return () => {
      active = false;
    };
  }, [
    externallyManaged,
    props.identity.manualId,
    props.identity.revisionId,
    props.identity.tenant,
    suppliedCapabilities,
  ]);

  const readerModeKey = useMemo(() => {
    if (!resolvedCapabilities) return "capabilities-pending";
    const mode = resolvedCapabilities.can_fill && resolvedCapabilities.has_acroform ? "acroform" : "read-only";
    return [
      props.identity.tenant.toLowerCase(),
      props.identity.manualId,
      props.identity.revisionId,
      resolvedCapabilities.source_sha256 || "unverified",
      resolvedCapabilities.javascript_policy || "NONE",
      mode,
    ].join(":");
  }, [
    props.identity.manualId,
    props.identity.revisionId,
    props.identity.tenant,
    resolvedCapabilities,
  ]);

  if (!resolvedCapabilities) {
    return <section className="pdfv2-reader" data-pdf-capability-state="pending">
      <div className="pdfv2-loading" role="status">Checking PDF fields and permissions…</div>
    </section>;
  }

  const readerFileUrl = resolvedCapabilities.reader_pdf_url || props.fileUrl;
  return <PdfReaderCoreV2
    {...props}
    key={readerModeKey}
    fileUrl={readerFileUrl}
    originalDownloadUrl={props.originalDownloadUrl || props.fileUrl}
    capabilities={resolvedCapabilities}
  />;
}

export type {
  PdfReaderCoreProps,
  PdfReaderNavigationRequest,
  PdfReaderOutlineItem,
};
