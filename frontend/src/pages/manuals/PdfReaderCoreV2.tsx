import { useCallback, useEffect, useMemo, useRef, useState, type CSSProperties, type FC, type ReactNode } from "react";
import { AlertTriangle, CheckCircle2, ChevronLeft, ChevronRight, Download, FilePenLine, LoaderCircle, Minus, MoreHorizontal, Plus, Search, Trash2, X } from "lucide-react";
import { Document, Page, pdfjs } from "react-pdf";
import type { DocumentationRecord } from "../../services/documentation";
import { flattenPdfWorkingCopy, getPdfReaderCapabilities, submitPdfWorkingCopy, type PdfReaderCapabilities } from "../../services/pdfReader";
import { downloadBlob, fetchPublicationBlob, publicationPdfSource } from "../../services/publications";
import { PDF_DOCUMENT_OPTIONS, pdfDevicePixelRatio } from "./pdfReaderConfig";
import { clampPdfValue, copyPdfBytes, highlightPdfText, outputPdfFilename, safePdfFilename, resolvePdfReaderScrollRoot, searchPdfDocument, type PdfSearchOptions, type PdfSearchResult } from "./pdfReaderEngine";
import { deletePdfWorkingCopy, readPdfWorkingCopy, savePdfWorkingCopy, type PdfWorkingCopyIdentity, type StoredPdfWorkingCopy } from "./pdfWorkingCopyStore";
import "react-pdf/dist/Page/AnnotationLayer.css";
import "react-pdf/dist/Page/TextLayer.css";
import "./pdfReaderEngineV2.css";

pdfjs.GlobalWorkerOptions.workerSrc = new URL("pdfjs-dist/build/pdf.worker.min.mjs", import.meta.url).toString();
const PdfDocument = Document as unknown as FC<any>;
const PdfPage = Page as unknown as FC<any>;

type PdfDocumentHandle = { numPages: number; getOutline?: () => Promise<any[] | null>; getDestination?: (name: string) => Promise<any[] | null>; getPageIndex?: (value: unknown) => Promise<number>; getFieldObjects?: () => Promise<Record<string, Array<Record<string, unknown>>> | null>; hasJSActions?: () => Promise<boolean>; saveDocument?: () => Promise<Uint8Array>; annotationStorage?: { onSetModified?: () => void; onResetModified?: () => void } };
export type PdfReaderOutlineItem = { id: string; title: string; page: number; level: number };
export type PdfReaderNavigationRequest = { page: number; token: number };
export type PdfReaderCoreProps = { fileUrl: string; originalDownloadUrl?: string; title: string; filename?: string | null; identity: PdfWorkingCopyIdentity; uncontrolled?: boolean; initialPage?: number; initialZoom?: number; navigationRequest?: PdfReaderNavigationRequest | null; capabilities?: PdfReaderCapabilities | null; compact?: boolean; renderPageOverlay?: (pageNumber: number) => ReactNode; onPageChange?: (pageNumber: number) => void; onZoomChange?: (zoomPercent: number) => void; onAcroFormDetected?: (hasAcroForm: boolean) => void; onOutlineReady?: (items: PdfReaderOutlineItem[]) => void; onDirtyChange?: (dirty: boolean) => void; onSubmitWorkingCopy?: (file: File) => Promise<DocumentationRecord>; onRecordCreated?: (record: DocumentationRecord) => void };

const READ_ONLY: PdfReaderCapabilities = { renderer: "PDF.js", processor: "PDFium", processor_version: "checking", source_sha256: "", page_count: 0, has_acroform: false, has_javascript: false, is_dynamic_xfa: false, encrypted: false, unsupported_reason: null, can_fill: false, can_save_draft: false, can_download_original: true, can_download_working: false, can_flatten: false, can_submit: false };
const uniquePages = (values: Iterable<number>) => [...new Set(values)].filter((value) => Number.isInteger(value) && value > 0).sort((a, b) => a - b);
const nearbyPages = (page: number, count: number, radius = 2) => new Set(Array.from({ length: radius * 2 + 1 }, (_, index) => page - radius + index).filter((value) => value >= 1 && value <= count));

async function outlineItems(pdf: PdfDocumentHandle): Promise<PdfReaderOutlineItem[]> {
  const source = await pdf.getOutline?.().catch(() => null);
  if (!Array.isArray(source)) return [];
  const rows: PdfReaderOutlineItem[] = [];
  const visit = async (items: any[], level: number, prefix: string) => {
    for (let index = 0; index < items.length; index += 1) {
      const item = items[index];
      let destination = item?.dest;
      if (typeof destination === "string") destination = await pdf.getDestination?.(destination).catch(() => null);
      const reference = Array.isArray(destination) ? destination[0] : null;
      let page = typeof reference === "number" ? reference + 1 : 0;
      if (!page && reference && pdf.getPageIndex) page = (await pdf.getPageIndex(reference).catch(() => -1)) + 1;
      const id = `${prefix}-${index}`;
      if (page > 0) rows.push({ id, title: String(item?.title || `Page ${page}`), page, level });
      if (item?.items?.length) await visit(item.items, level + 1, id);
    }
  };
  await visit(source, 1, "outline");
  return rows;
}

function detectedFormPages(fields: Record<string, Array<Record<string, unknown>>> | null, pageCount: number): number[] {
  const pages = new Set<number>();
  Object.values(fields || {}).flat().forEach((field) => {
    const raw = Number(field.page ?? field.pageIndex ?? field.page_number);
    if (!Number.isFinite(raw)) return;
    const page = raw >= 0 && raw < pageCount ? raw + 1 : raw;
    if (page >= 1 && page <= pageCount) pages.add(page);
  });
  return uniquePages(pages);
}

export default function PdfReaderCoreV2(props: PdfReaderCoreProps) {
  const { fileUrl, originalDownloadUrl, title, filename, identity, uncontrolled = false, initialPage = 1, initialZoom = 100, navigationRequest, capabilities: suppliedCapabilities, compact = false, renderPageOverlay, onPageChange, onZoomChange, onAcroFormDetected, onOutlineReady, onDirtyChange, onSubmitWorkingCopy, onRecordCreated } = props;
  const hostRef = useRef<HTMLDivElement | null>(null);
  const pageRefs = useRef(new Map<number, HTMLDivElement>());
  const pdfRef = useRef<PdfDocumentHandle | null>(null);
  const serializing = useRef<Promise<Uint8Array> | null>(null);
  const autosaveTimer = useRef<number | null>(null);
  const editedRef = useRef(new Set<number>());
  const dirtyRef = useRef(false);
  const searchInput = useRef<HTMLInputElement | null>(null);

  const [capabilities, setCapabilities] = useState<PdfReaderCapabilities>(suppliedCapabilities || READ_ONLY);
  const [capabilityError, setCapabilityError] = useState("");
  const [draft, setDraft] = useState<StoredPdfWorkingCopy | null>(null);
  const [pageCount, setPageCount] = useState(0);
  const [currentPage, setCurrentPage] = useState(Math.max(1, initialPage));
  const [pageInput, setPageInput] = useState(String(Math.max(1, initialPage)));
  const [pageRatios, setPageRatios] = useState<Record<number, number>>({});
  const [rendered, setRendered] = useState(new Set([Math.max(1, initialPage)]));
  const [hostSize, setHostSize] = useState({ width: 960, height: 720 });
  const [zoom, setZoom] = useState(clampPdfValue(initialZoom, 50, 250));
  const [fitMode, setFitMode] = useState<"WIDTH" | "PAGE" | "CUSTOM">("WIDTH");
  const [fieldCount, setFieldCount] = useState(0);
  const [formPages, setFormPages] = useState<number[]>([]);
  const [editedPages, setEditedPages] = useState<number[]>([]);
  const [dirty, setDirty] = useState(false);
  const [draftState, setDraftState] = useState<"" | "SAVING" | "SAVED" | "ERROR">("");
  const [loadError, setLoadError] = useState("");
  const [actionError, setActionError] = useState("");
  const [busy, setBusy] = useState<"" | "ORIGINAL" | "WORKING" | "FLATTEN" | "SUBMIT">("");
  const [record, setRecord] = useState<DocumentationRecord | null>(null);
  const [searchOpen, setSearchOpen] = useState(false);
  const [query, setQuery] = useState("");
  const [searchOptions, setSearchOptions] = useState<PdfSearchOptions>({ caseSensitive: false, wholeWord: false });
  const [searchResults, setSearchResults] = useState<PdfSearchResult[]>([]);
  const [searchIndex, setSearchIndex] = useState(-1);
  const [searchBusy, setSearchBusy] = useState(false);

  const source = useMemo(() => publicationPdfSource(fileUrl), [fileUrl]);
  const readerFile = useMemo(() => draft ? { data: new Uint8Array(draft.bytes.slice(0)) } : source, [draft, source]);
  const outputName = safePdfFilename(filename || "", `${title}.pdf`);
  const safeForm = Boolean(capabilities.can_fill && fieldCount > 0 && !capabilities.has_javascript && !capabilities.is_dynamic_xfa && !capabilities.encrypted);
  const availableWidth = Math.max(260, Math.min(1600, hostSize.width - (compact ? 16 : 36)));
  const ratio = pageRatios[currentPage] || 1.414;
  const pageWidth = Math.round(fitMode === "PAGE" ? Math.max(230, Math.min(availableWidth, (hostSize.height - 74) / ratio)) : fitMode === "CUSTOM" ? availableWidth * (zoom / 100) : availableWidth);

  const setDirtyState = useCallback((value: boolean) => { dirtyRef.current = value; setDirty(value); onDirtyChange?.(value); }, [onDirtyChange]);
  const setEdited = useCallback((values: Iterable<number>) => { const pages = uniquePages(values); editedRef.current = new Set(pages); setEditedPages(pages); }, []);

  useEffect(() => {
    if (suppliedCapabilities) { setCapabilities(suppliedCapabilities); return; }
    let active = true;
    getPdfReaderCapabilities(identity.tenant, identity.manualId, identity.revisionId).then((value) => active && setCapabilities(value)).catch((error) => { if (active) { setCapabilities(READ_ONLY); setCapabilityError(error instanceof Error ? error.message : "PDF processing is unavailable"); } });
    return () => { active = false; };
  }, [identity.manualId, identity.revisionId, identity.tenant, suppliedCapabilities]);

  useEffect(() => {
    if (!capabilities.source_sha256) return;
    let active = true;
    readPdfWorkingCopy(identity).then((value) => { if (active && value) { setDraft(value); setEdited(value.editedPages || []); setDirtyState(true); } }).catch(() => undefined);
    return () => { active = false; };
  }, [capabilities.source_sha256, identity, setDirtyState, setEdited]);

  useEffect(() => {
    const host = hostRef.current;
    if (!host) return;
    const update = () => { const root = resolvePdfReaderScrollRoot(host); setHostSize({ width: Math.max(300, host.clientWidth), height: Math.max(420, (root?.clientHeight || window.innerHeight) - 94) }); };
    update();
    const observer = typeof ResizeObserver === "undefined" ? null : new ResizeObserver(update);
    observer?.observe(host); window.addEventListener("resize", update);
    return () => { observer?.disconnect(); window.removeEventListener("resize", update); };
  }, []);

  useEffect(() => { onZoomChange?.(fitMode === "CUSTOM" ? zoom : Math.round(pageWidth / availableWidth * 100)); }, [availableWidth, fitMode, onZoomChange, pageWidth, zoom]);

  const serialize = useCallback(async () => {
    if (!pdfRef.current?.saveDocument) throw new Error("This PDF cannot be saved as a working copy");
    if (!serializing.current) serializing.current = pdfRef.current.saveDocument().finally(() => { serializing.current = null; });
    return serializing.current;
  }, []);

  const persistDraft = useCallback(async () => {
    if (!capabilities.can_save_draft || !dirtyRef.current) return;
    setDraftState("SAVING");
    try { const bytes = await serialize(); await savePdfWorkingCopy(identity, outputPdfFilename(outputName, "WORKING_COPY"), copyPdfBytes(bytes), capabilities.source_sha256, [...editedRef.current]); setDirtyState(false); setDraftState("SAVED"); }
    catch { setDraftState("ERROR"); }
  }, [capabilities.can_save_draft, capabilities.source_sha256, identity, outputName, serialize, setDirtyState]);

  const markEdited = useCallback((page: number) => {
    setEdited(new Set([...editedRef.current, page])); setDirtyState(true); setDraftState("");
    if (autosaveTimer.current) window.clearTimeout(autosaveTimer.current);
    if (capabilities.can_save_draft) autosaveTimer.current = window.setTimeout(() => void persistDraft(), 800);
  }, [capabilities.can_save_draft, persistDraft, setDirtyState, setEdited]);

  useEffect(() => () => { if (autosaveTimer.current) window.clearTimeout(autosaveTimer.current); }, []);

  const jump = useCallback((requested: number, behavior: ScrollBehavior = "smooth") => {
    if (!pageCount) return;
    const page = clampPdfValue(requested, 1, pageCount);
    setRendered((values) => new Set([...values, ...nearbyPages(page, pageCount)])); setCurrentPage(page); setPageInput(String(page)); onPageChange?.(page);
    requestAnimationFrame(() => requestAnimationFrame(() => { const host = hostRef.current; const element = pageRefs.current.get(page); if (!host || !element) return; const root = resolvePdfReaderScrollRoot(host); const top = element.getBoundingClientRect().top - (root?.getBoundingClientRect().top || 0) - 92; if (root) root.scrollTo({ top: Math.max(0, root.scrollTop + top), behavior }); else window.scrollBy({ top, behavior }); }));
  }, [onPageChange, pageCount]);

  useEffect(() => { if (navigationRequest?.page && pageCount) jump(navigationRequest.page); }, [jump, navigationRequest, pageCount]);

  useEffect(() => {
    if (!pageCount || typeof IntersectionObserver === "undefined" || !hostRef.current) return;
    const root = resolvePdfReaderScrollRoot(hostRef.current);
    const observer = new IntersectionObserver((entries) => {
      const visible = entries.filter((entry) => entry.isIntersecting);
      if (!visible.length) return;
      setRendered((values) => { const next = new Set(values); visible.forEach((entry) => nearbyPages(Number((entry.target as HTMLElement).dataset.pageNumber || 1), pageCount).forEach((page) => next.add(page))); return next; });
      const page = Number((visible.sort((a, b) => Math.abs(a.boundingClientRect.top - 120) - Math.abs(b.boundingClientRect.top - 120))[0].target as HTMLElement).dataset.pageNumber || 1);
      if (page !== currentPage) { setCurrentPage(page); setPageInput(String(page)); onPageChange?.(page); }
    }, { root, rootMargin: "600px 0px", threshold: [0.01, 0.25] });
    pageRefs.current.forEach((element) => observer.observe(element));
    return () => observer.disconnect();
  }, [currentPage, onPageChange, pageCount, pageWidth]);

  const loadDocument = useCallback((pdf: PdfDocumentHandle) => {
    pdfRef.current = pdf; const count = Math.max(1, Number(pdf.numPages || 1)); const restored = clampPdfValue(initialPage, 1, count);
    setPageCount(count); setCurrentPage(restored); setPageInput(String(restored)); setRendered(nearbyPages(restored, count)); setLoadError(""); onPageChange?.(restored);
    if (pdf.annotationStorage) pdf.annotationStorage.onSetModified = () => markEdited(currentPage);
    Promise.all([pdf.getFieldObjects?.().catch(() => null) || null, pdf.hasJSActions?.().catch(() => false) || false, outlineItems(pdf)]).then(([fields, scripts, outline]) => {
      const countFields = Object.values(fields || {}).flat().length; const pages = detectedFormPages(fields, count);
      setFieldCount(countFields); setFormPages(pages); onAcroFormDetected?.(countFields > 0); onOutlineReady?.(outline);
      if (scripts && countFields) setActionError("Scripted PDF actions are disabled; fields are read-only.");
    }).catch(() => undefined);
  }, [currentPage, initialPage, markEdited, onAcroFormDetected, onOutlineReady, onPageChange]);

  const workingFile = useCallback(async () => new File([copyPdfBytes(await serialize())], outputPdfFilename(outputName, "WORKING_COPY"), { type: "application/pdf" }), [outputName, serialize]);
  const perform = async (kind: typeof busy, action: () => Promise<void>) => { setBusy(kind); setActionError(""); try { await action(); } catch (error) { setActionError(error instanceof Error ? error.message : "The PDF action failed"); } finally { setBusy(""); } };
  const downloadOriginal = () => perform("ORIGINAL", async () => { const result = await fetchPublicationBlob(originalDownloadUrl || fileUrl); downloadBlob(result.blob, result.filename || outputName); });
  const downloadWorking = () => perform("WORKING", async () => { const file = await workingFile(); downloadBlob(file, file.name); });
  const downloadCompleted = () => perform("FLATTEN", async () => { const file = await workingFile(); const result = await flattenPdfWorkingCopy(identity.tenant, identity.manualId, identity.revisionId, file, editedPages.length ? editedPages : formPages); downloadBlob(result.blob, result.filename); });
  const submit = () => perform("SUBMIT", async () => { if (!window.confirm("Submit this completed PDF as an immutable controlled record?")) return; const file = await workingFile(); const created = onSubmitWorkingCopy ? await onSubmitWorkingCopy(file) : await submitPdfWorkingCopy(identity.tenant, identity.manualId, identity.revisionId, file, { completed_page_numbers: editedPages.length ? editedPages : formPages }); setRecord(created); setDirtyState(false); setEdited([]); await deletePdfWorkingCopy(identity).catch(() => undefined); setDraft(null); onRecordCreated?.(created); });
  const discard = async () => { if (dirty && !window.confirm("Discard the working copy?")) return; await deletePdfWorkingCopy(identity).catch(() => undefined); setDraft(null); setDirtyState(false); setEdited([]); setDraftState(""); };

  const runSearch = async () => { if (!pdfRef.current || query.trim().length < 2) return; setSearchBusy(true); try { const rows = await searchPdfDocument(pdfRef.current as any, query.trim(), searchOptions); setSearchResults(rows); setSearchIndex(rows.length ? 0 : -1); if (rows[0]) jump(rows[0].page); } finally { setSearchBusy(false); } };
  const moveSearch = (step: number) => { if (!searchResults.length) return; const index = (searchIndex + step + searchResults.length) % searchResults.length; setSearchIndex(index); jump(searchResults[index].page); };
  const pages = useMemo(() => Array.from({ length: pageCount }, (_, index) => index + 1), [pageCount]);
  const activeResult = searchResults[searchIndex];

  return <section ref={hostRef} className={`pdfv2-reader ${compact ? "is-compact" : ""} ${uncontrolled ? "is-uncontrolled" : ""} ${safeForm ? "is-form-active" : ""}`}>
    <header className="pdfv2-toolbar"><div className="pdfv2-pages"><button onClick={() => jump(currentPage - 1)} disabled={currentPage <= 1}><ChevronLeft size={17} /></button><input value={pageInput} inputMode="numeric" onChange={(event) => setPageInput(event.target.value.replace(/\D+/g, ""))} onBlur={() => jump(Number(pageInput || currentPage))} onKeyDown={(event) => { if (event.key === "Enter") jump(Number(pageInput || currentPage)); }} /><span>/ {pageCount || "—"}</span><button onClick={() => jump(currentPage + 1)} disabled={!pageCount || currentPage >= pageCount}><ChevronRight size={17} /></button></div>
      <div className="pdfv2-zoom"><button onClick={() => { setFitMode("CUSTOM"); setZoom((value) => clampPdfValue(value - 10, 50, 250)); }}><Minus size={17} /></button><button onClick={() => { setFitMode("CUSTOM"); setZoom(100); }}>{fitMode === "WIDTH" ? "Fit width" : fitMode === "PAGE" ? "Fit page" : `${zoom}%`}</button><button onClick={() => { setFitMode("CUSTOM"); setZoom((value) => clampPdfValue(value + 10, 50, 250)); }}><Plus size={17} /></button></div>
      <div className="pdfv2-actions"><button className={searchOpen ? "active" : ""} onClick={() => { setSearchOpen((value) => !value); requestAnimationFrame(() => searchInput.current?.focus()); }}><Search size={16} /><span>Search</span></button>{safeForm ? <span className="pdfv2-form-state"><FilePenLine size={15} /> Form active{editedPages.length ? ` · ${editedPages.length} changed` : ""}</span> : null}<details className="pdfv2-menu"><summary><Download size={16} /><span>Download</span></summary><div><button disabled={Boolean(busy) || !capabilities.can_download_original} onClick={() => void downloadOriginal()}>Original PDF</button><button disabled={Boolean(busy) || !capabilities.can_download_working || !pdfRef.current?.saveDocument} onClick={() => void downloadWorking()}>Editable PDF</button><button disabled={Boolean(busy) || !capabilities.can_flatten || !safeForm || !pdfRef.current?.saveDocument} onClick={() => void downloadCompleted()}>Completed form pages{editedPages.length ? ` (${editedPages.length})` : ""}</button></div></details><details className="pdfv2-menu"><summary><MoreHorizontal size={18} /></summary><div>{capabilities.can_submit ? <button disabled={Boolean(busy)} onClick={() => void submit()}>Submit retained record</button> : null}{draft || dirty ? <button onClick={() => void discard()}><Trash2 size={14} /> Discard working copy</button> : null}</div></details></div></header>
    {searchOpen ? <div className="pdfv2-search"><Search size={16} /><input ref={searchInput} value={query} onChange={(event) => setQuery(event.target.value)} onKeyDown={(event) => { if (event.key === "Enter") void runSearch(); }} placeholder="Search this PDF" /><label><input type="checkbox" checked={Boolean(searchOptions.caseSensitive)} onChange={(event) => setSearchOptions((value) => ({ ...value, caseSensitive: event.target.checked }))} /> Aa</label><button disabled={searchBusy || query.trim().length < 2} onClick={() => void runSearch()}>{searchBusy ? <LoaderCircle className="is-spinning" size={15} /> : "Find"}</button><span>{searchResults.length ? `${searchIndex + 1}/${searchResults.length}` : ""}</span><button disabled={!searchResults.length} onClick={() => moveSearch(-1)}><ChevronLeft size={16} /></button><button disabled={!searchResults.length} onClick={() => moveSearch(1)}><ChevronRight size={16} /></button><button onClick={() => setSearchOpen(false)}><X size={16} /></button></div> : null}
    {capabilityError ? <div className="pdfv2-notice"><AlertTriangle size={16} />{capabilityError}</div> : null}{capabilities.unsupported_reason && !safeForm ? <div className="pdfv2-notice"><AlertTriangle size={16} />{capabilities.unsupported_reason}</div> : null}{safeForm ? <div className="pdfv2-notice pdfv2-notice--form"><FilePenLine size={16} />Fields are active. Completed-page download excludes unchanged manual pages.<small>{draftState === "SAVING" ? "Saving…" : draftState === "SAVED" ? "Saved" : draftState === "ERROR" ? "Save failed" : ""}</small></div> : null}{actionError ? <div className="pdfv2-error"><AlertTriangle size={17} />{actionError}</div> : null}{record ? <div className="pdfv2-success"><CheckCircle2 size={17} />Record {record.record_number} created.<a href={record.download_url}>Open</a></div> : null}
    <div className="pdfv2-viewport" onInput={(event) => safeForm && markEdited(Number((event.target as HTMLElement).closest("[data-page-number]")?.getAttribute("data-page-number") || currentPage))} onChange={(event) => safeForm && markEdited(Number((event.target as HTMLElement).closest("[data-page-number]")?.getAttribute("data-page-number") || currentPage))}>
      {loadError ? <div className="pdfv2-error"><AlertTriangle size={18} />{loadError}</div> : null}<PdfDocument file={readerFile} options={PDF_DOCUMENT_OPTIONS} onLoadSuccess={loadDocument} onLoadError={(error: unknown) => setLoadError(error instanceof Error ? error.message : "The PDF could not be opened")} loading={<div className="pdfv2-loading"><LoaderCircle className="is-spinning" size={20} />Opening document…</div>}><div className="pdfv2-pages-list">{pages.map((page) => { const pageRatio = pageRatios[page] || 1.414; const style = { "--pdfv2-page-width": `${pageWidth}px`, "--pdfv2-page-height": `${Math.round(pageWidth * pageRatio)}px` } as CSSProperties; return <div key={page} ref={(element) => { if (element) pageRefs.current.set(page, element); else pageRefs.current.delete(page); }} className={`pdfv2-page ${page === currentPage ? "is-current" : ""}`} data-page-number={page} style={style}>{uncontrolled ? <span className="pdfv2-watermark">UNCONTROLLED DRAFT</span> : null}{rendered.has(page) ? <PdfPage pageNumber={page} width={pageWidth} renderMode="canvas" renderTextLayer renderAnnotationLayer renderForms={safeForm} devicePixelRatio={pdfDevicePixelRatio()} customTextRenderer={({ str }: { str: string }) => highlightPdfText(str, query, searchOptions, activeResult?.page === page)} loading={<div className="pdfv2-placeholder">Rendering page {page}…</div>} error={<div className="pdfv2-placeholder">Page {page} could not be rendered.</div>} onGetAnnotationsSuccess={(annotations: any[]) => { if (annotations.some((item) => item?.subtype === "Widget" || item?.fieldType)) { setFieldCount((value) => Math.max(1, value)); setFormPages((values) => uniquePages([...values, page])); onAcroFormDetected?.(true); } }} onLoadSuccess={(loaded: any) => { const width = Number(loaded?.originalWidth || loaded?.view?.[2] || 1); const height = Number(loaded?.originalHeight || loaded?.view?.[3] || width * 1.414); setPageRatios((values) => ({ ...values, [page]: height / width })); }} /> : <div className="pdfv2-placeholder pdfv2-placeholder--queued">Page {page}</div>}{renderPageOverlay?.(page)}</div>; })}</div></PdfDocument>
    </div>
  </section>;
}
