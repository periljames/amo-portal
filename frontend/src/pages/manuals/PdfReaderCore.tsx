import { useEffect, useMemo, useRef, useState } from "react";

import { getPdfReaderCapabilities, type PdfReaderCapabilities } from "../../services/pdfReader";
import "./pdfReaderOperationalFixes.css";
import PdfReaderCoreV2, {
  type PdfReaderCoreProps,
  type PdfReaderNavigationRequest,
  type PdfReaderOutlineItem,
} from "./PdfReaderCoreV2";
import {
  cachePdfCapabilities,
  clearCachedPdfCapabilities,
  readCachedPdfCapabilities,
} from "./pdfCapabilityCache";
import {
  deleteCachedPdfSource,
  readCachedPdfSource,
  warmPdfSourceCache,
} from "./pdfSourceCache";

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

function cachedReadOnly(capabilities: PdfReaderCapabilities): PdfReaderCapabilities {
  return {
    ...capabilities,
    has_acroform: false,
    can_fill: false,
    can_save_draft: false,
    can_download_working: false,
    can_flatten: false,
    can_submit: false,
    unsupported_reason: null,
  };
}

function readOnlyFallback(
  error: unknown,
  source?: PdfReaderCapabilities | null,
): PdfReaderCapabilities {
  const detail = error instanceof Error && error.message.trim()
    ? error.message.trim()
    : "PDF form capabilities could not be verified";
  return {
    ...READ_ONLY_FALLBACK,
    source_sha256: source?.source_sha256 || "",
    page_count: source?.page_count || 0,
    reader_pdf_url: source?.reader_pdf_url || null,
    source_has_javascript: source?.source_has_javascript,
    javascript_policy: source?.javascript_policy,
    unsupported_reason: `${detail}. The document remains available in read-only mode.`,
  };
}

function scheduleIdle(task: () => void): () => void {
  if (typeof window === "undefined") return () => undefined;
  const browser = window as typeof window & {
    requestIdleCallback?: (callback: () => void, options?: { timeout?: number }) => number;
    cancelIdleCallback?: (handle: number) => void;
  };
  if (browser.requestIdleCallback) {
    const handle = browser.requestIdleCallback(task, { timeout: 2500 });
    return () => browser.cancelIdleCallback?.(handle);
  }
  const handle = window.setTimeout(task, 1800);
  return () => window.clearTimeout(handle);
}

/**
 * Paint the immutable PDF immediately. A cached source and cached capability
 * fingerprint may be used for the initial read-only frame, while the live
 * capability request revalidates form permissions without remounting PDF.js.
 */
export default function PdfReaderCore(props: PdfReaderCoreProps) {
  const suppliedCapabilities = props.capabilities;
  const externallyManaged = suppliedCapabilities !== undefined;
  const identityKey = useMemo(() => [
    props.identity.tenant.toLowerCase(),
    props.identity.manualId,
    props.identity.revisionId,
  ].join(":"), [props.identity.manualId, props.identity.revisionId, props.identity.tenant]);
  const initialCachedCapabilities = useMemo(
    () => suppliedCapabilities || readCachedPdfCapabilities(props.identity),
    [identityKey, suppliedCapabilities],
  );
  const mayHydrateSourceCache = useRef(Boolean(initialCachedCapabilities?.source_sha256));
  const initialCacheFingerprint = useRef(initialCachedCapabilities?.source_sha256 || "");
  const [resolvedCapabilities, setResolvedCapabilities] = useState<PdfReaderCapabilities>(
    initialCachedCapabilities ? cachedReadOnly(initialCachedCapabilities) : READ_ONLY_FALLBACK,
  );
  const [cachedPdfBytes, setCachedPdfBytes] = useState<ArrayBuffer | null>(null);
  const [sourceCachePending, setSourceCachePending] = useState(Boolean(initialCachedCapabilities?.source_sha256));

  useEffect(() => {
    if (externallyManaged) {
      const next = suppliedCapabilities || READ_ONLY_FALLBACK;
      setResolvedCapabilities(next);
      if (suppliedCapabilities?.source_sha256) cachePdfCapabilities(props.identity, suppliedCapabilities);
      setSourceCachePending(Boolean(suppliedCapabilities?.source_sha256));
      mayHydrateSourceCache.current = Boolean(suppliedCapabilities?.source_sha256);
      initialCacheFingerprint.current = suppliedCapabilities?.source_sha256 || "";
      return;
    }

    let active = true;
    getPdfReaderCapabilities(
      props.identity.tenant,
      props.identity.manualId,
      props.identity.revisionId,
    )
      .then((capabilities) => {
        if (!active) return;
        const previous = initialCachedCapabilities;
        const sourceChanged = Boolean(
          previous?.source_sha256
          && previous.source_sha256 !== capabilities.source_sha256,
        );
        if (sourceChanged) {
          clearCachedPdfCapabilities(props.identity);
          setCachedPdfBytes(null);
          setSourceCachePending(false);
          void deleteCachedPdfSource(
            props.identity,
            previous!.source_sha256,
            previous!.reader_pdf_url || props.fileUrl,
          );
        }
        cachePdfCapabilities(props.identity, capabilities);
        setResolvedCapabilities(capabilities);
      })
      .catch((error) => {
        if (!active) return;
        setResolvedCapabilities(readOnlyFallback(error, initialCachedCapabilities));
      });

    return () => {
      active = false;
    };
  }, [
    externallyManaged,
    identityKey,
    initialCachedCapabilities,
    props.fileUrl,
    props.identity,
    suppliedCapabilities,
  ]);

  const readerFileUrl = resolvedCapabilities.reader_pdf_url || props.fileUrl;

  useEffect(() => {
    if (!mayHydrateSourceCache.current) return;
    const fingerprint = initialCacheFingerprint.current;
    if (!fingerprint) {
      setSourceCachePending(false);
      mayHydrateSourceCache.current = false;
      return;
    }
    let active = true;
    readCachedPdfSource(props.identity, fingerprint, readerFileUrl)
      .then((bytes) => {
        if (!active) return;
        if (bytes) setCachedPdfBytes(bytes);
      })
      .finally(() => {
        if (!active) return;
        mayHydrateSourceCache.current = false;
        setSourceCachePending(false);
      });
    return () => { active = false; };
  }, [identityKey, props.identity, readerFileUrl]);

  useEffect(() => {
    const fingerprint = resolvedCapabilities.source_sha256;
    if (!fingerprint || cachedPdfBytes || sourceCachePending) return;
    const expectedBytes = readerFileUrl === props.fileUrl ? props.sourceSizeBytes : undefined;
    return scheduleIdle(() => {
      void warmPdfSourceCache(
        props.identity,
        fingerprint,
        readerFileUrl,
        expectedBytes,
      );
    });
  }, [
    cachedPdfBytes,
    identityKey,
    props.fileUrl,
    props.identity,
    props.sourceSizeBytes,
    readerFileUrl,
    resolvedCapabilities.source_sha256,
    sourceCachePending,
  ]);

  if (sourceCachePending) {
    return <section className="pdfv2-reader" data-pdf-source-cache="checking">
      <div className="pdfv2-loading" role="status">Opening cached document…</div>
    </section>;
  }

  return <PdfReaderCoreV2
    {...props}
    key={identityKey}
    fileUrl={readerFileUrl}
    originalDownloadUrl={props.originalDownloadUrl || props.fileUrl}
    capabilities={resolvedCapabilities}
    fileData={cachedPdfBytes}
  />;
}

export type {
  PdfReaderCoreProps,
  PdfReaderNavigationRequest,
  PdfReaderOutlineItem,
};
