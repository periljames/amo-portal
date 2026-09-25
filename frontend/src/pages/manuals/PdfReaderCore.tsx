import { useCallback, useEffect, useMemo, useRef, useState } from "react";

import { getPdfReaderCapabilities, type PdfReaderCapabilities } from "../../services/pdfReader";
import PdfReaderCoreV5, {
  type PdfReaderCoreProps,
  type PdfReaderNavigationRequest,
  type PdfReaderOutlineItem,
} from "./PdfReaderCoreV5";
import {
  cachePdfCapabilities,
  clearCachedPdfCapabilities,
  readCachedPdfCapabilities,
} from "./pdfCapabilityCache";
import {
  deleteCachedPdfSource,
  hasCachedPdfSource,
  readCachedPdfSource,
  readLatestCachedPdfSource,
  savePdfSourceOffline,
} from "./pdfSourceCache";
import "./pdfReaderThemeAdaptive.css";

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

/**
 * Resolve one immutable source before PDF.js mounts. Cached metadata can select
 * the same source quickly, but it never authorizes forms or draft custody until
 * the live checksum and permission response succeeds.
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
  const cachedCapabilities = useMemo(
    () => suppliedCapabilities || readCachedPdfCapabilities(identity),
    [identity, suppliedCapabilities],
  );

  const [capabilities, setCapabilities] = useState<PdfReaderCapabilities>(
    cachedCapabilities ? cachedReadOnly(cachedCapabilities) : READ_ONLY_FALLBACK,
  );
  const [readerFileUrl, setReaderFileUrl] = useState<string | null>(null);
  const [readerKey, setReaderKey] = useState("");
  const [offlineState, setOfflineState] = useState<"CHECKING" | "UNAVAILABLE" | "AVAILABLE" | "SAVING" | "ERROR">("CHECKING");
  const [offlineError, setOfflineError] = useState("");
  const [offlineDescriptor, setOfflineDescriptor] = useState<{
    sha256: string;
    url: string;
    byteLength?: number | null;
  } | null>(null);
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
      const fingerprint = resolved.reader_source_sha256 || resolved.source_sha256;
      if (fingerprint) {
        setOfflineDescriptor({
          sha256: fingerprint,
          url: remoteUrl,
          byteLength: resolved.reader_size_bytes
            || (fingerprint === resolved.source_sha256 ? props.sourceByteLength : null),
        });
      }
      if (!allowCachedBytes || !fingerprint) {
        setOfflineState("UNAVAILABLE");
        return { url: remoteUrl, key: `${remoteUrl}:${fingerprint || "unverified"}` };
      }

      // The live capability response verifies the fingerprint. Reuse that exact
      // encrypted source even on a slow-but-online connection.
      const cachedBytes = await readCachedPdfSource(identity, fingerprint, remoteUrl);
      if (!cachedBytes) {
        setOfflineState("UNAVAILABLE");
        return { url: remoteUrl, key: `${remoteUrl}:${fingerprint}` };
      }

      const localUrl = URL.createObjectURL(new Blob([cachedBytes], { type: "application/pdf" }));
      revokeObjectUrl();
      objectUrlRef.current = localUrl;
      setOfflineState("AVAILABLE");
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

    const mountLatestOffline = async (): Promise<boolean> => {
      const saved = await readLatestCachedPdfSource(identity);
      if (!saved) return false;
      const localUrl = URL.createObjectURL(new Blob([saved.bytes], { type: "application/pdf" }));
      if (!active || generationRef.current !== generation) {
        URL.revokeObjectURL(localUrl);
        return false;
      }
      revokeObjectUrl();
      objectUrlRef.current = localUrl;
      sourceMountedRef.current = true;
      setOfflineDescriptor({
        sha256: saved.sourceSha256,
        url: saved.readerUrl,
        byteLength: saved.byteLength,
      });
      setOfflineState("AVAILABLE");
      setCapabilities({
        ...READ_ONLY_FALLBACK,
        reader_pdf_url: saved.readerUrl,
        reader_source_sha256: saved.sourceSha256,
        reader_size_bytes: saved.byteLength,
        can_download_original: false,
      });
      setReaderFileUrl(localUrl);
      setReaderKey(`${saved.readerUrl}:${saved.sourceSha256}:offline-recovery`);
      return true;
    };

    const run = async () => {
      if (externallyManaged) {
        const resolved = suppliedCapabilities || READ_ONLY_FALLBACK;
        setCapabilities(resolved);
        if (resolved.source_sha256) cachePdfCapabilities(identity, resolved);
        await mount(resolved, Boolean(resolved.reader_source_sha256 || resolved.source_sha256));
        return;
      }

      const cached = cachedCapabilities;
      if (cached) {
        await mount(cached, true);
        if (!active || generationRef.current !== generation) return;
        setCapabilities(cachedReadOnly(cached));
      }

      if (!cached && navigator.onLine === false && await mountLatestOffline()) return;

      // Read-only PDF.js display does not depend on server form processing.
      // Scripting/eval/XFA are disabled in PDF_DOCUMENT_OPTIONS. Verified form
      // permissions and a sanitized replacement source arrive independently.
      if (!sourceMountedRef.current) await mount(READ_ONLY_FALLBACK, false);

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
        const cachedReaderFingerprint = cached?.reader_source_sha256 || cached?.source_sha256 || "";
        const liveReaderFingerprint = live.reader_source_sha256 || live.source_sha256;
        const readerChanged = Boolean(
          cachedReaderFingerprint
          && cachedReaderFingerprint.toLowerCase() !== liveReaderFingerprint.toLowerCase(),
        );
        const cachedReaderUrl = cached?.reader_pdf_url || props.fileUrl;
        const liveReaderUrl = live.reader_pdf_url || props.fileUrl;
        const sourceUrlChanged = Boolean(cached && cachedReaderUrl !== liveReaderUrl);

        if (sourceChanged || readerChanged) {
          clearCachedPdfCapabilities(identity);
          await deleteCachedPdfSource(
            identity,
            cachedReaderFingerprint,
            cachedReaderUrl,
          ).catch(() => undefined);
        }

        cachePdfCapabilities(identity, live);
        setCapabilities(live);

        const initialSourceChanged = !cached && liveReaderUrl !== props.fileUrl;
        if (sourceChanged || readerChanged || sourceUrlChanged || initialSourceChanged || !sourceMountedRef.current) {
          await mount(live, true);
        } else if (!cached && liveReaderFingerprint) {
          setOfflineDescriptor({ sha256: liveReaderFingerprint, url: liveReaderUrl, byteLength: live.reader_size_bytes || props.sourceByteLength });
          setOfflineState(await hasCachedPdfSource(identity, liveReaderFingerprint, liveReaderUrl) ? "AVAILABLE" : "UNAVAILABLE");
        }

      } catch (error) {
        if (!active || generationRef.current !== generation) return;
        if (!sourceMountedRef.current && await mountLatestOffline()) return;
        const fallback = readOnlyFallback(error, cached);
        setCapabilities(fallback);
        if (!sourceMountedRef.current) await mount(fallback, false);
      }
    };

    const initializationFrame = window.requestAnimationFrame(() => {
      if (!active || generationRef.current !== generation) return;
      sourceMountedRef.current = false;
      setOfflineDescriptor(null);
      setOfflineState("CHECKING");
      setOfflineError("");
      setReaderFileUrl(null);
      revokeObjectUrl();
      void run();
    });
    return () => {
      active = false;
      window.cancelAnimationFrame(initializationFrame);
    };
  }, [
    cachedCapabilities,
    externallyManaged,
    identity,
    props.fileUrl,
    props.sourceByteLength,
    suppliedCapabilities,
  ]);

  const saveOffline = useCallback(async () => {
    if (!offlineDescriptor) return;
    setOfflineState("SAVING");
    setOfflineError("");
    try {
      await savePdfSourceOffline(
        identity,
        offlineDescriptor.sha256,
        offlineDescriptor.url,
        offlineDescriptor.byteLength,
      );
      setOfflineState("AVAILABLE");
    } catch (error) {
      setOfflineState("ERROR");
      setOfflineError(error instanceof Error ? error.message : "The controlled PDF could not be saved offline.");
    }
  }, [identity, offlineDescriptor]);

  const removeOffline = useCallback(async () => {
    if (!offlineDescriptor) return;
    setOfflineError("");
    try {
      await deleteCachedPdfSource(identity, offlineDescriptor.sha256, offlineDescriptor.url);
      setOfflineState("UNAVAILABLE");
    } catch (error) {
      setOfflineState("ERROR");
      setOfflineError(error instanceof Error ? error.message : "The offline copy could not be removed.");
    }
  }, [identity, offlineDescriptor]);

  const recoverOfflineAfterLoadError = useCallback(async () => {
    if (readerFileUrl?.startsWith("blob:")) return;
    const saved = await readLatestCachedPdfSource(identity);
    if (!saved) return;
    const localUrl = URL.createObjectURL(new Blob([saved.bytes], { type: "application/pdf" }));
    if (objectUrlRef.current) URL.revokeObjectURL(objectUrlRef.current);
    objectUrlRef.current = localUrl;
    setOfflineDescriptor({
      sha256: saved.sourceSha256,
      url: saved.readerUrl,
      byteLength: saved.byteLength,
    });
    setOfflineState("AVAILABLE");
    setOfflineError("");
    setCapabilities({
      ...READ_ONLY_FALLBACK,
      reader_pdf_url: saved.readerUrl,
      reader_source_sha256: saved.sourceSha256,
      reader_size_bytes: saved.byteLength,
      can_download_original: false,
    });
    setReaderFileUrl(localUrl);
    setReaderKey(`${saved.readerUrl}:${saved.sourceSha256}:network-recovery`);
  }, [identity, readerFileUrl]);

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
    <PdfReaderCoreV5
      {...props}
      key={readerKey}
      identity={identity}
      fileUrl={readerFileUrl}
      originalDownloadUrl={props.originalDownloadUrl || props.fileUrl}
      capabilities={capabilities}
      offlineControl={{
        state: offlineState,
        error: offlineError,
        supported: Boolean(offlineDescriptor),
        onSave: saveOffline,
        onRemove: removeOffline,
      }}
      onSourceLoadError={(error) => {
        props.onSourceLoadError?.(error);
        void recoverOfflineAfterLoadError();
      }}
    />
  );
}

export type {
  PdfReaderCoreProps,
  PdfReaderNavigationRequest,
  PdfReaderOutlineItem,
};
