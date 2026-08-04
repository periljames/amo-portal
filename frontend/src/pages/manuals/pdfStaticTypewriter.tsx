import {
  useCallback,
  useEffect,
  useMemo,
  useRef,
  useState,
  type ChangeEvent as ReactChangeEvent,
  type CSSProperties,
  type MouseEvent as ReactMouseEvent,
  type PointerEvent as ReactPointerEvent,
  type ReactNode,
} from "react";
import { Download, FilePenLine, GripHorizontal, LoaderCircle, Maximize2, Trash2, X } from "lucide-react";

import { getCachedUser } from "../../services/auth";
import {
  createPdfStaticOverlay,
  type PdfReaderCapabilities,
  type PdfStaticOverlayItem,
  type PdfStaticOverlaySchemaField,
} from "../../services/pdfReader";
import { downloadBlob } from "../../services/publications";
import "./pdfStaticTypewriter.css";

type Identity = { tenant: string; manualId: string; revisionId: string };

type UsePdfStaticTypewriterArgs = {
  identity: Identity | null;
  capabilities: PdfReaderCapabilities | null;
  currentPage: number;
  title: string;
};

type DragState = {
  id: string;
  pointerId: number;
  startX: number;
  startY: number;
  originX: number;
  originY: number;
  layerWidth: number;
  layerHeight: number;
};

type ResizeState = {
  id: string;
  pointerId: number;
  startX: number;
  startY: number;
  originWidth: number;
  originHeight: number;
  layerWidth: number;
  layerHeight: number;
};

type StaticTypewriterController = {
  available: boolean;
  controls: ReactNode;
  renderPageOverlay: (pageNumber: number) => ReactNode;
};

const DRAFT_PREFIX = "amo-pdf-static-overlay:v1";

function clamp(value: number, minimum: number, maximum: number): number {
  return Math.min(maximum, Math.max(minimum, value));
}

function draftKey(identity: Identity): string {
  const userId = String(getCachedUser()?.id || "anonymous");
  return [
    DRAFT_PREFIX,
    encodeURIComponent(userId),
    encodeURIComponent(identity.tenant.toLowerCase()),
    encodeURIComponent(identity.manualId),
    encodeURIComponent(identity.revisionId),
  ].join(":");
}

function schemaItems(fields: PdfStaticOverlaySchemaField[] = []): PdfStaticOverlayItem[] {
  return fields
    .map((field, index) => ({
      id: String(field.id || field.name || `schema-field-${index}`),
      name: String(field.name || field.id || `field-${index}`),
      page: Math.max(1, Number(field.page || 1)),
      x: clamp(Number(field.x || 0), 0, 0.995),
      y: clamp(Number(field.y || 0), 0, 0.995),
      width: clamp(Number(field.width || 0.2), 0.005, 1),
      height: clamp(Number(field.height || 0.04), 0.005, 1),
      text: String(field.default_value || ""),
      font_size: clamp(Number(field.font_size || 10), 6, 24),
      multiline: field.multiline ?? true,
      align: field.align || "left",
    }))
    .filter((field) => field.x + field.width <= 1.001 && field.y + field.height <= 1.001);
}

function newIdentifier(): string {
  if (typeof crypto !== "undefined" && typeof crypto.randomUUID === "function") return crypto.randomUUID();
  return `overlay-${Date.now()}-${Math.random().toString(36).slice(2)}`;
}

function overlayStyle(item: PdfStaticOverlayItem): CSSProperties {
  return {
    left: `${item.x * 100}%`,
    top: `${item.y * 100}%`,
    width: `${item.width * 100}%`,
    height: `${item.height * 100}%`,
  };
}

export function usePdfStaticTypewriter({
  identity,
  capabilities,
  currentPage,
  title,
}: UsePdfStaticTypewriterArgs): StaticTypewriterController {
  const [active, setActive] = useState(false);
  const [items, setItems] = useState<PdfStaticOverlayItem[]>([]);
  const [busy, setBusy] = useState<"" | "PAGES" | "FULL">("");
  const [error, setError] = useState("");
  const dragRef = useRef<DragState | null>(null);
  const resizeRef = useRef<ResizeState | null>(null);

  const schema = useMemo(
    () => capabilities?.overlay_schema?.fields || [],
    [capabilities?.overlay_schema?.fields],
  );
  const canConfigure = Boolean(capabilities?.can_configure_overlay);
  const available = Boolean(
    identity
    && capabilities?.can_overlay_fill
    && (!capabilities.has_acroform || schema.length > 0),
  );

  useEffect(() => {
    if (!identity || !capabilities?.source_sha256 || !available) {
      setItems([]);
      setActive(false);
      return;
    }
    const defaults = schemaItems(schema);
    try {
      const raw = window.localStorage.getItem(draftKey(identity));
      if (!raw) {
        setItems(defaults);
        return;
      }
      const parsed = JSON.parse(raw) as { source_sha256?: string; items?: PdfStaticOverlayItem[] };
      if (String(parsed.source_sha256 || "").toLowerCase() !== capabilities.source_sha256.toLowerCase()) {
        window.localStorage.removeItem(draftKey(identity));
        setItems(defaults);
        return;
      }
      const stored = Array.isArray(parsed.items) ? parsed.items : [];
      if (!defaults.length) {
        setItems(stored);
        return;
      }
      const byId = new Map(stored.map((item) => [item.id, item]));
      const defaultIds = new Set(defaults.map((item) => item.id));
      const restoredDefaults = defaults.map((item) => ({
        ...item,
        text: byId.get(item.id)?.text || item.text,
      }));
      const freeFields = canConfigure ? stored.filter((item) => !defaultIds.has(item.id)) : [];
      setItems([...restoredDefaults, ...freeFields]);
    } catch {
      setItems(defaults);
    }
  }, [available, canConfigure, capabilities?.source_sha256, identity, schema]);

  useEffect(() => {
    if (!identity || !capabilities?.source_sha256 || !available) return;
    const timer = window.setTimeout(() => {
      try {
        window.localStorage.setItem(draftKey(identity), JSON.stringify({
          source_sha256: capabilities.source_sha256,
          items,
          saved_at: new Date().toISOString(),
        }));
      } catch {
        // The download path remains available when browser storage is unavailable.
      }
    }, 250);
    return () => window.clearTimeout(timer);
  }, [available, capabilities?.source_sha256, identity, items]);

  const updateItem = useCallback((id: string, update: Partial<PdfStaticOverlayItem>) => {
    setItems((current) => current.map((item) => item.id === id ? { ...item, ...update } : item));
  }, []);

  const removeItem = useCallback((id: string) => {
    setItems((current) => current.filter((item) => item.id !== id));
  }, []);

  const addAt = useCallback((event: ReactPointerEvent<HTMLDivElement>, pageNumber: number) => {
    if (!active || !canConfigure || event.target !== event.currentTarget) return;
    const rect = event.currentTarget.getBoundingClientRect();
    const x = clamp((event.clientX - rect.left) / Math.max(1, rect.width), 0, 0.95);
    const y = clamp((event.clientY - rect.top) / Math.max(1, rect.height), 0, 0.96);
    const width = Math.min(0.45, Math.max(0.1, 0.985 - x));
    const height = Math.min(0.12, Math.max(0.04, 0.99 - y));
    const id = newIdentifier();
    setItems((current) => [...current, {
      id,
      name: `free-text-${current.length + 1}`,
      page: pageNumber,
      x,
      y,
      width,
      height,
      text: "",
      font_size: 10,
      multiline: true,
      align: "left",
    }]);
    window.requestAnimationFrame(() => {
      document.querySelector<HTMLTextAreaElement>(`textarea[data-static-overlay-id="${CSS.escape(id)}"]`)?.focus();
    });
  }, [active, canConfigure]);

  const beginDrag = useCallback((event: ReactPointerEvent<HTMLButtonElement>, item: PdfStaticOverlayItem) => {
    if (!canConfigure) return;
    event.preventDefault();
    event.stopPropagation();
    const layer = event.currentTarget.closest<HTMLElement>(".pdf-static-typewriter-layer");
    if (!layer) return;
    const rect = layer.getBoundingClientRect();
    dragRef.current = {
      id: item.id,
      pointerId: event.pointerId,
      startX: event.clientX,
      startY: event.clientY,
      originX: item.x,
      originY: item.y,
      layerWidth: Math.max(1, rect.width),
      layerHeight: Math.max(1, rect.height),
    };
    event.currentTarget.setPointerCapture(event.pointerId);
  }, [canConfigure]);

  const moveDrag = useCallback((event: ReactPointerEvent<HTMLButtonElement>, item: PdfStaticOverlayItem) => {
    const drag = dragRef.current;
    if (!drag || drag.id !== item.id || drag.pointerId !== event.pointerId) return;
    const x = clamp(drag.originX + (event.clientX - drag.startX) / drag.layerWidth, 0, 1 - item.width);
    const y = clamp(drag.originY + (event.clientY - drag.startY) / drag.layerHeight, 0, 1 - item.height);
    updateItem(item.id, { x, y });
  }, [updateItem]);

  const endDrag = useCallback((event: ReactPointerEvent<HTMLButtonElement>) => {
    if (dragRef.current?.pointerId === event.pointerId) dragRef.current = null;
    if (event.currentTarget.hasPointerCapture(event.pointerId)) event.currentTarget.releasePointerCapture(event.pointerId);
  }, []);

  const beginResize = useCallback((event: ReactPointerEvent<HTMLButtonElement>, item: PdfStaticOverlayItem) => {
    if (!canConfigure) return;
    event.preventDefault();
    event.stopPropagation();
    const layer = event.currentTarget.closest<HTMLElement>(".pdf-static-typewriter-layer");
    if (!layer) return;
    const rect = layer.getBoundingClientRect();
    resizeRef.current = {
      id: item.id,
      pointerId: event.pointerId,
      startX: event.clientX,
      startY: event.clientY,
      originWidth: item.width,
      originHeight: item.height,
      layerWidth: Math.max(1, rect.width),
      layerHeight: Math.max(1, rect.height),
    };
    event.currentTarget.setPointerCapture(event.pointerId);
  }, [canConfigure]);

  const moveResize = useCallback((event: ReactPointerEvent<HTMLButtonElement>, item: PdfStaticOverlayItem) => {
    const resize = resizeRef.current;
    if (!resize || resize.id !== item.id || resize.pointerId !== event.pointerId) return;
    const width = clamp(
      resize.originWidth + (event.clientX - resize.startX) / resize.layerWidth,
      0.04,
      1 - item.x,
    );
    const height = clamp(
      resize.originHeight + (event.clientY - resize.startY) / resize.layerHeight,
      0.025,
      1 - item.y,
    );
    updateItem(item.id, { width, height });
  }, [updateItem]);

  const endResize = useCallback((event: ReactPointerEvent<HTMLButtonElement>) => {
    if (resizeRef.current?.pointerId === event.pointerId) resizeRef.current = null;
    if (event.currentTarget.hasPointerCapture(event.pointerId)) event.currentTarget.releasePointerCapture(event.pointerId);
  }, []);

  const download = useCallback(async (completedOnly: boolean) => {
    if (!identity) return;
    const populated = items.filter((item) => item.text.trim());
    if (!populated.length) {
      setError("Type at least one value onto the PDF before downloading it.");
      return;
    }
    setBusy(completedOnly ? "PAGES" : "FULL");
    setError("");
    try {
      const result = await createPdfStaticOverlay(
        identity.tenant,
        identity.manualId,
        identity.revisionId,
        populated,
        completedOnly,
      );
      downloadBlob(result.blob, result.filename || `${title}_${completedOnly ? "FILLED_PAGES" : "FILLED_COPY"}.pdf`);
    } catch (caught) {
      setError(caught instanceof Error ? caught.message : "The filled PDF could not be generated.");
    } finally {
      setBusy("");
    }
  }, [identity, items, title]);

  const clearPage = useCallback(() => {
    const schemaIds = new Set(schema.map((field, index) => String(field.id || field.name || `schema-field-${index}`)));
    setItems((current) => current
      .filter((item) => item.page !== currentPage || schemaIds.has(item.id))
      .map((item) => item.page === currentPage ? { ...item, text: "" } : item));
  }, [currentPage, schema]);

  const controls = available ? <div className={`pdf-static-typewriter-controls ${active ? "is-active" : ""}`}>
    <button type="button" className="pdf-static-typewriter-primary" onClick={() => { setActive((value) => !value); setError(""); }}>
      <FilePenLine size={15} /> {active ? "Finish typing" : canConfigure ? "Type on PDF" : "Fill form"}
    </button>
    <span>{active
      ? canConfigure
        ? "Click a blank line or box to add text. Drag the top handle to move it and the corner handle to resize it."
        : "Complete the highlighted fields directly on the controlled page."
      : items.some((item) => item.text.trim())
        ? `${items.filter((item) => item.text.trim()).length} filled field(s) saved locally`
        : "This page is a flattened form. Use the typewriter to complete it."}</span>
    <div>
      <button type="button" disabled={Boolean(busy)} onClick={() => void download(true)}>
        {busy === "PAGES" ? <LoaderCircle className="is-spinning" size={14} /> : <Download size={14} />} Filled pages
      </button>
      <button type="button" disabled={Boolean(busy)} onClick={() => void download(false)}>
        {busy === "FULL" ? <LoaderCircle className="is-spinning" size={14} /> : <Download size={14} />} Full filled PDF
      </button>
      <button type="button" disabled={Boolean(busy) || !items.some((item) => item.page === currentPage)} onClick={clearPage}><Trash2 size={14} /> Clear page</button>
    </div>
    {error ? <strong role="alert">{error}</strong> : null}
  </div> : null;

  const renderPageOverlay = useCallback((pageNumber: number): ReactNode => {
    if (!available) return null;
    const pageItems = items.filter((item) => item.page === pageNumber);
    const interactive = active || pageItems.some((item) => item.text.trim());
    return <div
      className={`pdf-static-typewriter-layer ${active ? "is-editing" : ""} ${canConfigure ? "can-configure" : "is-schema-only"}`}
      data-page={pageNumber}
      aria-hidden={!interactive}
      onPointerDown={(event: ReactPointerEvent<HTMLDivElement>) => addAt(event, pageNumber)}
    >
      {pageItems.map((item) => <div key={item.id} className={`pdf-static-typewriter-field ${item.text.trim() ? "has-value" : ""}`} style={overlayStyle(item)}>
        {active ? <>
          {canConfigure ? <button
            type="button"
            className="pdf-static-typewriter-drag"
            aria-label="Move typed field"
            onPointerDown={(event: ReactPointerEvent<HTMLButtonElement>) => beginDrag(event, item)}
            onPointerMove={(event: ReactPointerEvent<HTMLButtonElement>) => moveDrag(event, item)}
            onPointerUp={endDrag}
            onPointerCancel={endDrag}
          ><GripHorizontal size={12} /></button> : null}
          <textarea
            data-static-overlay-id={item.id}
            value={item.text}
            aria-label={item.name || "PDF form field"}
            spellCheck
            onPointerDown={(event: ReactPointerEvent<HTMLTextAreaElement>) => event.stopPropagation()}
            onChange={(event: ReactChangeEvent<HTMLTextAreaElement>) => updateItem(item.id, { text: event.target.value })}
          />
          {canConfigure ? <>
            <button
              type="button"
              className="pdf-static-typewriter-resize"
              aria-label="Resize typed field"
              onPointerDown={(event: ReactPointerEvent<HTMLButtonElement>) => beginResize(event, item)}
              onPointerMove={(event: ReactPointerEvent<HTMLButtonElement>) => moveResize(event, item)}
              onPointerUp={endResize}
              onPointerCancel={endResize}
            ><Maximize2 size={11} /></button>
            <button type="button" className="pdf-static-typewriter-remove" aria-label="Remove typed field" onClick={(event: ReactMouseEvent<HTMLButtonElement>) => { event.stopPropagation(); removeItem(item.id); }}><X size={11} /></button>
          </> : null}
        </> : item.text.trim() ? <span>{item.text}</span> : null}
      </div>)}
    </div>;
  }, [active, addAt, available, beginDrag, beginResize, canConfigure, endDrag, endResize, items, moveDrag, moveResize, removeItem, updateItem]);

  return { available, controls, renderPageOverlay };
}
