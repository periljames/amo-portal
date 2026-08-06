import { useEffect, useMemo, useRef, useState } from "react";
import { LoaderCircle } from "lucide-react";

import { getPdfReaderCapabilities, type PdfReaderCapabilities } from "../../services/pdfReader";
import { getPdfReaderPerformanceProfile, type PdfReaderPerformanceProfile } from "../../services/pdfPerformance";
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

type ReaderBootstrap = {
  capabilities: PdfReaderCapabilities;
  sourceUrl: string;
  objectUrl: string | null;
  liveVerified: boolean;
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

function readOnlyFallback(error: unknown, source?: PdfReaderCapabilities | null): PdfReaderCapabilities {
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

function sourceUrlFor(capabilities: PdfReaderCapabilities | null | undefined, fallback: string): string {
  return String(capabilities?.reader_pdf_url || fallback);
}

function sameControlledSource(
  cached: PdfReaderCapabilities,
  live: PdfReaderCapabilities,
  fallbackUrl: string,
): boolean {
  return cached.source_sha256.toLowerCase() === live.source_sha256.toLowerCase()
    && sourceUrlFor(cached, fallbackUrl) === sourceUrlFor(live, fallbackUrl);
}

async function cachedSourceWithin(
  identity: PdfReaderCoreProps["identity"],
  sourceSha256: string,
  sourceUrl: string,
  timeoutMs: number,
): Promise<ArrayBuffer | null> {
  let timer = 0;
  const timeout = new Promise<null>((resolve) => {
    timer = window.setTimeout(() => resolve(null), timeoutMs);
  });
  try {
    return await Promise.race([
      readCachedPdfSource(identity, sourceSha256, sourceUrl),
      timeout,
    ]);
  } finally {
    if (timer) window.clearTimeout(timer);
  }
}

function scheduleSourceWarm(profile: PdfReaderPerformanceProfile, task: () => void): () => void {
  if (typeof window === "undefined") return () => undefined;
  const delay = profile.mode === "burst" ? 1200 : profile.mode === "balanced" ? 2400 : 5000;
  const handle = window.setTimeout(task, delay);
  return () => window.clearTimeout(handle);
}

/**
 * Resolve one immutable reader source before PDF.js mounts. Cached capability
 * metadata may accelerate the first frame, but it never authorizes editing.
 * The live response upgrades permissions only when it confirms the same source
 * and the same script-disabled reader URL, preventing the destructive
 * read-only -> sanitized source replacement seen in the production video.
 */
export default function PdfReaderCore(props: PdfReaderCoreProps) {
  const suppliedCapabilities = props.capabilities;
  const externallyManaged = suppliedCapabilities !== undefined;
  const performanceProfile = useMemo(() => getPdfReaderPerformanceProfile(), []);
  const readerIdentity = useMemo(() => ({
    tenant: props.identity.tenant,
    manualId: props.identity.manualId,
    revisionId: props.identity.revisionId,
    userId: props.identity.userId,
  }), [props.identity.manualId, props.identity.revisionId, props.identity.tenant, props.identity.userId]);
  const identityKey = useMemo(() => [
    readerIdentity.tenant.toLowerCase(),
    readerIdentity.manualId,
    readerIdentity.revisionId,
  ].join(":"), [readerIdentity]);
  const cachedCapabilities = useMemo(
    () => suppliedCapabilities || readCachedPdfCapabilities(readerIdentity),
    [readerIdentity, suppliedCapabilities],
  );
  const bootstrapGeneration = useRef(0);
  const [bootstrap, setBootstrap] = useState<ReaderBootstrap | null>(null);

  useEffect(() => {
    const generation = bootstrapGeneration.current + 1;
    bootstrapGeneration.current = generation;
    let active = true;
    let objectUrl: string | null = null;

    const publish = (value: ReaderBootstrap) => {
      if (!active || bootstrapGeneration.current !== generation) {
        if (value.objectUrl) URL.revokeObjectURL(value.objectUrl);
        return;
      }
      objectUrl = value.objectUrl;
      setBootstrap((current) => {
        if (current?.objectUrl && current.objectUrl !== value.objectUrl) URL.revokeObjectURL(current.objectUrl);
        return value;
      });
    };

    const start = async () => {
      if (externallyManaged) {
        const capabilities = suppliedCapabilities || READ_ONLY_FALLBACK;
        const sourceUrl = sourceUrlFor(capabilities, props.fileUrl);
        const bytes = capabilities.source_sha256
          ? await cachedSourceWithin(readerIdentity, capabilities.source_sha256, sourceUrl, 250)
          : null;
        const local = bytes ? URL.createObjectURL(new Blob([bytes], { type: "application/pdf" })) : null;
        if (capabilities.source_sha256) cachePdfCapabilities(readerIdentity, capabilities);
        publish({ capabilities, sourceUrl, objectUrl: local, liveVerified: true });
        return;
      }

      const livePromise = getPdfReaderCapabilities(
        readerIdentity.tenant,
        readerIdentity.manualId,
        readerIdentity.revisionId,
      );

      if (!cachedCapabilities?.source_sha256) {
        try {
          const live = await livePromise;
          if (!active) return;
          cachePdfCapabilities(readerIdentity, live);
          const sourceUrl = sourceUrlFor(live, props.fileUrl);
          const bytes = await cachedSourceWithin(readerIdentity, live.source_sha256, sourceUrl, 250);
          const local = bytes ? URL.createObjectURL(new Blob([bytes], { type: "application/pdf" })) : null;
          publish({ capabilities: live, sourceUrl, objectUrl: local, liveVerified: true });
        } catch (error) {
          publish({
            capabilities: readOnlyFallback(error),
            sourceUrl: props.fileUrl,
            objectUrl: null,
            liveVerified: false,
          });
        }
        return;
      }

      const cachedSourceUrl = sourceUrlFor(cachedCapabilities, props.fileUrl);
      const [cachedBytes, quickLive] = await Promise.all([
        cachedSourceWithin(readerIdentity, cachedCapabilities.source_sha256, cachedSourceUrl, 250),
        Promise.race([
          livePromise.then((value) => value as PdfReaderCapabilities | null).catch(() => null),
          new Promise<null>((resolve) => window.setTimeout(() => resolve(null), 250)),
        ]),
      ]);
      if (!active) return;

      const initialCapabilities = quickLive && sameControlledSource(cachedCapabilities, quickLive, props.fileUrl)
        ? quickLive
        : cachedReadOnly(cachedCapabilities);
      if (quickLive) cachePdfCapabilities(readerIdentity, quickLive);
      const initialSourceUrl = sourceUrlFor(quickLive || cachedCapabilities, props.fileUrl);
      const local = cachedBytes && initialSourceUrl === cachedSourceUrl
        ? URL.createObjectURL(new Blob([cachedBytes], { type: "application/pdf" }))
        : null;
      publish({
        capabilities: initialCapabilities,
        sourceUrl: initialSourceUrl,
        objectUrl: local,
        liveVerified: Boolean(quickLive && sameControlledSource(cachedCapabilities, quickLive, props.fileUrl)),
      });

      try {
        const live = quickLive || await livePromise;
        if (!active) return;
        cachePdfCapabilities(readerIdentity, live);
        if (!sameControlledSource(cachedCapabilities, live, props.fileUrl)) {
          clearCachedPdfCapabilities(readerIdentity);
          void deleteCachedPdfSource(
            readerIdentity,
            cachedCapabilities.source_sha256,
            cachedSourceUrl,
          );
          setBootstrap((current) => current ? {
            ...current,
            capabilities: readOnlyFallback(
              new Error("The controlled reader source changed while this document was opening; reopen the document to load the verified source"),
              live,
            ),
            liveVerified: false,
          } : current);
          return;
        }
        setBootstrap((current) => current ? {
          ...current,
          capabilities: live,
          liveVerified: true,
        } : current);
      } catch (error) {
        if (!active) return;
        setBootstrap((current) => current ? {
          ...current,
          capabilities: readOnlyFallback(error, cachedCapabilities),
          liveVerified: false,
        } : current);
      }
    };

    void start();
    return () => {
      active = false;
      if (objectUrl) URL.revokeObjectURL(objectUrl);
    };
  }, [
    cachedCapabilities,
    externallyManaged,
    props.fileUrl,
    readerIdentity,
    suppliedCapabilities,
  ]);

  useEffect(() => {
    if (!bootstrap?.liveVerified || !bootstrap.capabilities.source_sha256 || bootstrap.objectUrl) return;
    return scheduleSourceWarm(performanceProfile, () => {
      void warmPdfSourceCache(
        readerIdentity,
        bootstrap.capabilities.source_sha256,
        bootstrap.sourceUrl,
      );
    });
  }, [bootstrap, performanceProfile, readerIdentity]);

  if (!bootstrap) {
    return <section className="pdfv2-reader pdfv2-reader--booting" data-pdf-source-state="resolving">
      <div className="pdfv2-loading" role="status"><LoaderCircle className="is-spinning" size={19} />Preparing controlled document…</div>
    </section>;
  }

  return <PdfReaderCoreV2
    {...props}
    key={identityKey}
    identity={readerIdentity}
    fileUrl={bootstrap.objectUrl || bootstrap.sourceUrl}
    originalDownloadUrl={props.originalDownloadUrl || props.fileUrl}
    capabilities={bootstrap.capabilities}
  />;
}

export type {
  PdfReaderCoreProps,
  PdfReaderNavigationRequest,
  PdfReaderOutlineItem,
};
