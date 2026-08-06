import { useEffect, useMemo, useRef, useState } from "react";

import { getPdfReaderCapabilities, type PdfReaderCapabilities } from "../../services/pdfReader";
import { getPdfReaderPerformanceProfile } from "../../services/pdfPerformance";
import PdfReaderCoreV3, {
  type PdfReaderCoreProps,
  type PdfReaderNavigationRequest,
  type PdfReaderOutlineItem,
} from "./PdfReaderCoreV3";
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

const CACHE_LOOKUP_BUDGET_MS = 140;

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
    source_sha256: "",
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
    page_count: source?.page_count || 0,
    reader_pdf_url: source?.reader_pdf_url || null,
    source_has_javascript: source?.source_has_javascript,
    javascript_policy: source?.javascript_policy,
    unsupported_reason: `${detail}. The document remains available in read-only mode.`,
  };
}

function wait(milliseconds: number): Promise<null> {
  return new Promise((resolve) => window.setTimeout(() => resolve(null), milliseconds));
}

/**
 * Resolve the immutable source before PDF.js mounts. Cached capability metadata
 * may select the already-sanitized source URL, but only the live capability
 * response can authorize form execution or local draft custody.
 */
export default function PdfReaderCore(props: PdfReaderCoreProps) {
  const suppliedCapabilities = props.capabilities;
  const externallyManaged = suppliedCapabilities !== undefined;
  const profile = useMemo(() => getPdfReaderPerformanceProfile(), []);
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
  const cachedCapabilities = useMemo(
    () => suppliedCapabilities || readCachedPdfCapabilities(identity),
    [identity, suppliedCapabilities],
  );

  const [capabilities, setCapabilities] = useState<PdfReaderCapabilities>(
    cachedCapabilities ? cachedReadOnly(cachedCapabilities) : READ_ONLY_FALLBACK,
  );
  const [readerFileUrl, setReaderFileUrl] = useState<string | null>(null);
  const [readerKey, setReaderKey] = useState("");
  const [preparationError, setPreparationError] = useState("");
  const objectUrlRef = useRef<string | null>(null);
  const sourceMountedRef = useRef(false);
  const generationRef = useRef(0);

  useEffect(() => {
    const generation = generationRef.current + 1;
    generationRef.current = generation;
    let active = true;

    const revokeObjectUrl = () => {
      if (!objectUrlRef.current) return;
      URL.revokeObjectURL(objectUrlRef.current);
      objectUrlRef.current = null;
    };

    const chooseSource = async (
      resolved: PdfReaderCapabilities,
      allowCachedBytes: boolean,
    ): Promise<{ url: string; key: string }> => {
      const remoteUrl = resolved.reader_pdf_url || props.fileUrl;
      const fingerprint = resolved.source_sha256;
      if (!allowCachedBytes || !fingerprint) {
        return { url: remoteUrl, key: `${remoteUrl}:${fingerprint || "unverified"}` };
      }

      const cachedBytes = await Promise.race([
        readCachedPdfSource(identity, fingerprint, remoteUrl),
        wait(CACHE_LOOKUP_BUDGET_MS),
      ]);
      if (!cachedBytes) {
        return { url: remoteUrl, key: `${remoteUrl}:${fingerprint}` };
      }

      const localUrl = URL.createObjectURL(new Blob([cachedBytes], { type: "application/pdf" }));
      revokeObjectUrl();
      objectUrlRef.current = localUrl;
      return { url: localUrl, key: `${remoteUrl}:${fingerprint}:cached` };
    };

    const mount = async (
      resolved: PdfReaderCapabilities,
      allowCachedBytes: boolean,
    ): Promise<void> => {
      const selected = await chooseSource(resolved, allowCachedBytes);
      if (!active || generationRef.current !== generation) {
        if (selected.url.startsWith("blob:")) URL.revokeObjectURL(selected.url);
        return;
      }
      sourceMountedRef.current = true;
      setReaderFileUrl(selected.url);
      setReaderKey(selected.key);
    };

    const run = async () => {
      setPreparationError("");

      if (externallyManaged) {
        const resolved = suppliedCapabilities || READ_ONLY_FALLBACK;
        setCapabilities(resolved);
        if (resolved.source_sha256) cachePdfCapabilities(identity, resolved);
        await mount(resolved, Boolean(resolved.source_sha256));
        return;
      }

      const cached = cachedCapabilities;
      if (cached) {
        // The cached source identity selects the same immutable reader bytes
        // immediately. It remains read-only until the live response confirms
        // the current checksum and permissions.
        await mount(cached, true);
        if (!active || generationRef.current !== generation) return;
        setCapabilities(cachedReadOnly(cached));
      }

      try {
        const live = await getPdfReaderCapabilities(
          identity.tenant,
          identity.manualId,
          identity.revisionId,
        );
        if (!active || generationRef.current !== generation) return;

        const sourceChanged = Boolean(
          cached?.source_sha256
          && cached.source_sha256.toLowerCase() !== live.source_sha256.toLowerCase(),
        );
        const cachedReaderUrl = cached?.reader_pdf_url || props.fileUrl;
        const liveReaderUrl = live.reader_pdf_url || props.fileUrl;
        const sourceUrlChanged = Boolean(cached && cachedReaderUrl !== liveReaderUrl);

        if (sourceChanged) {
          clearCachedPdfCapabilities(identity);
          await deleteCachedPdfSource(
            identity,
            cached!.source_sha256,
            cachedReaderUrl,
          ).catch(() => undefined);
        }

        cachePdfCapabilities(identity, live);
        setCapabilities(live);

        if (!cached || sourceChanged || sourceUrlChanged || !sourceMountedRef.current) {
          // First visits wait for this authoritative result, so PDF.js still
          // mounts once. A reload is permitted only if an immutable source
          // changed or cached metadata selected a different derivative.
          await mount(live, true);
        }

        const finalRemoteUrl = live.reader_pdf_url || props.fileUrl;
        window.setTimeout(() => {
          if (!active || generationRef.current !== generation) return;
          void warmPdfSourceCache(
            identity,
            live.source_sha256,
            finalRemoteUrl,
          );
        }, profile.mode === "constrained" ? 1_500 : 120);
      } catch (error) {
        if (!active || generationRef.current !== generation) return;
        const fallback = readOnlyFallback(error, cached);
        setCapabilities(fallback);
        setPreparationError(fallback.unsupported_reason || "");
        if (!sourceMountedRef.current) await mount(fallback, false);
      }
    };

    void run();

    return () => {
      active = false;
    };
  }, [
    cachedCapabilities,
    externallyManaged,
    identity,
    profile.mode,
    props.fileUrl,
    suppliedCapabilities,
  ]);

  useEffect(() => () => {
    if (objectUrlRef.current) URL.revokeObjectURL(objectUrlRef.current);
  }, []);

  if (!readerFileUrl) {
    return (
      <section className="pdfv3-reader" data-pdf-bootstrap="resolving">
        <div className="pdfv3-document-loading" role="status">
          Preparing controlled document…
        </div>
      </section>
    );
  }

  return (
    <>
      {preparationError ? (
        <div className="pdfv3-error" role="alert">{preparationError}</div>
      ) : null}
      <PdfReaderCoreV3
        {...props}
        key={readerKey}
        identity={identity}
        fileUrl={readerFileUrl}
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
