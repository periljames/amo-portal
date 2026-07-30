import { useEffect, useMemo, useState, type CSSProperties } from "react";
import { Link2, List, X } from "lucide-react";

import {
  getPublicationReferences,
  type DocumentationIndexState,
  type DocumentationReference,
} from "../../services/documentation";
import LinkedDocumentationPanel from "./LinkedDocumentationPanel";
import PdfReaderCore, {
  type PdfReaderNavigationRequest,
  type PdfReaderOutlineItem,
} from "./PdfReaderCore";
import "./publicationReaderZoom.css";

export type PdfOutlineItem = PdfReaderOutlineItem;

type PublicationPdfLayoutViewerProps = {
  fileUrl: string;
  title: string;
  uncontrolled?: boolean;
  navigationRequest?: PdfReaderNavigationRequest | null;
  initialPage?: number;
  initialZoom?: number;
  references?: DocumentationReference[];
  activeReferenceId?: string | null;
  onReferenceClick?: (reference: DocumentationReference) => void;
  onPageChange?: (pageNumber: number) => void;
  onZoomChange?: (zoomPercent: number) => void;
  onAcroFormDetected?: (hasAcroForm: boolean) => void;
  onOutlineReady?: (items: PdfOutlineItem[]) => void;
};

type SourceIdentity = { tenant: string; manualId: string; revisionId: string };

function clamp(value: number, minimum: number, maximum: number): number {
  return Math.min(maximum, Math.max(minimum, value));
}

function sourceIdentity(fileUrl: string): SourceIdentity | null {
  const path = fileUrl.split("?", 1)[0];
  const match = path.match(/\/manuals\/t\/([^/]+)\/([^/]+)\/rev\/([^/]+)\//i);
  if (!match) return null;
  try {
    return {
      tenant: decodeURIComponent(match[1]),
      manualId: decodeURIComponent(match[2]),
      revisionId: decodeURIComponent(match[3]),
    };
  } catch {
    return null;
  }
}

function hotspotStyle(reference: DocumentationReference): CSSProperties | null {
  const box = reference.source?.bbox || {};
  const x = Number(box.x);
  const y = Number(box.y);
  const width = Number(box.width);
  const height = Number(box.height);
  if (![x, y, width, height].every(Number.isFinite) || width <= 0 || height <= 0) return null;
  return {
    left: `${clamp(x, 0, 1) * 100}%`,
    top: `${clamp(y, 0, 1) * 100}%`,
    width: `${clamp(width, 0.004, 1) * 100}%`,
    height: `${clamp(height, 0.006, 1) * 100}%`,
  };
}

function indexing(index?: DocumentationIndexState | null): boolean {
  return ["PENDING", "RUNNING"].includes(String(index?.status || "").toUpperCase());
}

function humanize(value: unknown, fallback = "Pending review"): string {
  const text = String(value ?? "").trim();
  return text ? text.replaceAll("_", " ") : fallback;
}

export default function PublicationPdfLayoutViewer({
  fileUrl,
  title,
  uncontrolled = false,
  navigationRequest,
  initialPage = 1,
  initialZoom = 100,
  references = [],
  activeReferenceId,
  onReferenceClick,
  onPageChange,
  onZoomChange,
  onAcroFormDetected,
  onOutlineReady,
}: PublicationPdfLayoutViewerProps) {
  const identity = useMemo(() => sourceIdentity(fileUrl), [fileUrl]);
  const [automaticReferences, setAutomaticReferences] = useState<DocumentationReference[]>([]);
  const [indexState, setIndexState] = useState<DocumentationIndexState | null>(null);
  const [currentPage, setCurrentPage] = useState(Math.max(1, initialPage));
  const [selectedReferenceId, setSelectedReferenceId] = useState<string | null>(activeReferenceId || null);
  const [referenceListOpen, setReferenceListOpen] = useState(false);

  useEffect(() => {
    if (!identity || references.length) return;
    let active = true;
    let timer = 0;
    const load = () => {
      getPublicationReferences(identity.tenant, identity.manualId, identity.revisionId)
        .then((response) => {
          if (!active) return;
          setAutomaticReferences(response.items || []);
          setIndexState(response.index || null);
          if (indexing(response.index)) timer = window.setTimeout(load, 1400);
        })
        .catch(() => { if (active) timer = window.setTimeout(load, 3500); });
    };
    load();
    return () => { active = false; if (timer) window.clearTimeout(timer); };
  }, [identity, references.length]);

  useEffect(() => { setSelectedReferenceId(activeReferenceId || null); }, [activeReferenceId]);

  const allReferences = references.length ? references : automaticReferences;
  const referencesByPage = useMemo(() => {
    const grouped = new Map<number, DocumentationReference[]>();
    for (const reference of allReferences) {
      const page = Number(reference.source?.page_number || 0);
      if (!page) continue;
      grouped.set(page, [...(grouped.get(page) || []), reference]);
    }
    return grouped;
  }, [allReferences]);
  const selectedReference = allReferences.find((reference) => reference.id === (activeReferenceId || selectedReferenceId)) || null;
  const currentReferences = referencesByPage.get(currentPage) || [];

  const openReference = (reference: DocumentationReference) => {
    if (!reference.target) return;
    setSelectedReferenceId(reference.id);
    setReferenceListOpen(false);
    onReferenceClick?.(reference);
  };

  if (!identity) {
    return <div className="publication-native-pdf__error" role="alert">The controlled PDF source could not be identified.</div>;
  }

  return (
    <div className={`publication-linked-layout ${selectedReference ? "has-selection" : ""}`}>
      <div className="publication-native-pdf">
        {indexing(indexState) ? <div className="pdf-engine-notice">Indexing linked documents…</div> : null}
        {currentReferences.length ? <div className="publication-page-links-control">
          <button type="button" className="publication-page-links-button" onClick={() => setReferenceListOpen((value) => !value)}><Link2 size={14} /> {currentReferences.length} linked</button>
          {referenceListOpen ? <div className="publication-page-links-popover">
            <header><strong>Linked items on page {currentPage}</strong><button type="button" onClick={() => setReferenceListOpen(false)} aria-label="Close linked items"><X size={14} /></button></header>
            {currentReferences.map((reference) => <button type="button" key={reference.id} disabled={!reference.target} onClick={() => openReference(reference)}>
              <List size={14} /><span><strong>{reference.raw_token}</strong><small>{reference.target ? `${reference.target.code} · ${reference.target.title}` : `${humanize(reference.status)} · awaiting Document Control`}</small></span>
            </button>)}
          </div> : null}
        </div> : null}
        <PdfReaderCore
          fileUrl={fileUrl}
          originalDownloadUrl={fileUrl}
          title={title}
          filename={`${title}.pdf`}
          identity={identity}
          uncontrolled={uncontrolled}
          navigationRequest={navigationRequest}
          initialPage={initialPage}
          initialZoom={initialZoom}
          onPageChange={(pageNumber) => { setCurrentPage(pageNumber); onPageChange?.(pageNumber); }}
          onZoomChange={onZoomChange}
          onAcroFormDetected={onAcroFormDetected}
          onOutlineReady={onOutlineReady}
          renderPageOverlay={(pageNumber) => <>{(referencesByPage.get(pageNumber) || []).map((reference) => {
            const style = hotspotStyle(reference);
            if (!style || !reference.target) return null;
            return <button
              type="button"
              key={reference.id}
              className={`publication-reference-hotspot ${(activeReferenceId || selectedReferenceId) === reference.id ? "active" : ""}`}
              style={style}
              aria-label={`${reference.raw_token}: open ${reference.target.code}`}
              onClick={() => openReference(reference)}
            />;
          })}</>}
        />
      </div>
      {selectedReference ? <LinkedDocumentationPanel tenant={identity.tenant} referenceId={selectedReference.id} onClose={() => setSelectedReferenceId(null)} /> : null}
    </div>
  );
}
