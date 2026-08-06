import { useEffect, useMemo, useRef, useState } from "react";

import {
  getPdfReaderCapabilities,
  type PdfReaderCapabilities,
} from "../../services/pdfReader";
import {
  cachePdfCapabilities,
  clearCachedPdfCapabilities,
  readCachedPdfCapabilities,
} from "./pdfCapabilityCache";
import {
  warmPdfSourceCache,
} from "./pdfSourceCache";
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
  unsupported_reason: null,
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
 * Resolve the immutable, script-safe source before mounting PDF.js.
 *
 * Cached capability metadata makes revisits immediate. A cold visit performs one
 * capability request and then mounts exactly one PDF source. Live revalidation
 * may update permissions, but it never replaces the mounted source unless the
 * immutable checksum itself changed.
 */
export default function PdfReaderCore(props: PdfReaderCoreProps) {
  const suppliedCapabilities = props.capabilities;
  const externallyManaged = suppliedCapabilities !== undefined;
  const identity = useMemo(() => ({
    tenant: props.identity.tenant,
    manualId: props.identity.manualId,
    revisionId: props.identity.revisionId,
    userId: props.identity.userId,
  }), [
    props.identity.manualId,
    props.identity.revisionId,
    props.identity.tenant,
    props.identity.userId,
  ]);
  const cachedAtMount = useRef<PdfReaderCapabilities | null>(
    suppliedCapabilities || readCachedPdfCapabilities(identity),
  );
  const [capabilities, setCapabilities] = useState<PdfReaderCapabilities | null>(
    cachedAtMount.current,
  );
  const [sourceResolutionError, setSourceResolutionError] = useState("");
  const mountedSourceRef = useRef<string | null>(
    cachedAtMount.current
      ? cachedAtMount.current.reader_pdf_url || props.fileUrl
      : null,
  );

  useEffect(() => {
    if (externallyManaged) {
      const next = suppliedCapabilities || READ_ONLY_FALLBACK;
      setCapabilities(next);
      setSourceResolutionError("");
      mountedSourceRef.current = next.reader_pdf_url || props.fileUrl;
      if (suppliedCapabilities?.source_sha256) {
        cachePdfCapabilities(identity, suppliedCapabilities);
      }
      return;
    }

    let active = true;
    getPdfReaderCapabilities(identity.tenant, identity.manualId, identity.revisionId)
      .then((next) => {
        if (!active) return;
        const previous = cachedAtMount.current;
        const checksumChanged = Boolean(
          previous?.source_sha256
            && previous.source_sha256 !== next.source_sha256,
        );
        if (checksumChanged) clearCachedPdfCapabilities(identity);
        cachePdfCapabilities(identity, next);

        if (!mountedSourceRef.current || checksumChanged) {
          mountedSourceRef.current = next.reader_pdf_url || props.fileUrl;
        } else {
          const liveSource = next.reader_pdf_url || props.fileUrl;
          if (liveSource !== mountedSourceRef.current) {
            setSourceResolutionError(
              "The controlled reader source policy changed. Reopen this publication to apply the new immutable reader source.",
            );
          }
        }
        cachedAtMount.current = next;
        setCapabilities(next);
      })
      .catch((error) => {
        if (!active) return;
        if (!mountedSourceRef.current) mountedSourceRef.current = props.fileUrl;
        setCapabilities(readOnlyFallback(error));
        setSourceResolutionError(
          error instanceof Error ? error.message : "PDF processing is unavailable",
        );
      });

    return () => {
      active = false;
    };
  }, [
    externallyManaged,
    identity,
    props.fileUrl,
    suppliedCapabilities,
  ]);

  const stableSource = mountedSourceRef.current;
  const sourceKey = capabilities?.source_sha256 || "read-only";

  useEffect(() => {
    if (!stableSource || !capabilities?.source_sha256) return;
    const timer = window.setTimeout(() => {
      void warmPdfSourceCache(identity, capabilities.source_sha256, stableSource);
    }, 1200);
    return () => window.clearTimeout(timer);
  }, [capabilities?.source_sha256, identity, stableSource]);

  if (!capabilities || !stableSource) {
    return (
      <section className="pdfv2-reader" data-pdf-source-state="resolving">
        <div className="pdfv2-loading" role="status">
          Preparing controlled document…
        </div>
      </section>
    );
  }

  return (
    <>
      {sourceResolutionError ? (
        <div className="pdfv2-notice" role="status">
          {sourceResolutionError}
        </div>
      ) : null}
      <PdfReaderCoreV2
        {...props}
        key={`${identity.tenant}:${identity.manualId}:${identity.revisionId}:${sourceKey}`}
        identity={identity}
        fileUrl={stableSource}
        originalDownloadUrl={props.originalDownloadUrl || props.fileUrl}
        capabilities={capabilities}
      />
    </>
  );
}

export type {
  PdfReaderCoreProps,
  PdfReaderNavigationRequest,
  PdfReaderOutlineItem,
};
