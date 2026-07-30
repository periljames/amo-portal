export type PdfSearchOptions = {
  caseSensitive?: boolean;
  wholeWord?: boolean;
};

export type PdfSearchResult = {
  id: string;
  page: number;
  ordinal: number;
  start: number;
  length: number;
  snippet: string;
};

export type PdfReaderShortcut =
  | "SEARCH"
  | "ZOOM_IN"
  | "ZOOM_OUT"
  | "RESET_ZOOM"
  | "NEXT_PAGE"
  | "PREVIOUS_PAGE"
  | "FIRST_PAGE"
  | "LAST_PAGE";

export type SearchablePdfDocument = {
  numPages: number;
  getPage: (pageNumber: number) => Promise<{
    getTextContent: () => Promise<{ items: Array<{ str?: string }> }>;
  }>;
};

const WORD_CHARACTER = /[\p{L}\p{N}_]/u;

export function clampPdfValue(value: number, minimum: number, maximum: number): number {
  return Math.min(maximum, Math.max(minimum, value));
}

export function safePdfFilename(value: string, fallback: string): string {
  const source = (value || fallback).split(/[\\/]+/).pop() || fallback;
  const cleaned = source.replace(/[^A-Za-z0-9._-]+/g, "_").replace(/^\.+/, "") || fallback;
  return cleaned.toLowerCase().endsWith(".pdf") ? cleaned : `${cleaned}.pdf`;
}

export function outputPdfFilename(value: string, mode: "WORKING_COPY" | "FLATTENED"): string {
  const safe = safePdfFilename(value, "controlled-document.pdf");
  const stem = safe.replace(/\.pdf$/i, "");
  return `${stem}_${mode}.pdf`;
}

export function copyPdfBytes(bytes: Uint8Array): ArrayBuffer {
  const copy = new Uint8Array(bytes.byteLength);
  copy.set(bytes);
  return copy.buffer;
}

export function isPdfWorkingCopyGenerationCurrent(
  persistedGeneration: number,
  currentGeneration: number,
): boolean {
  return persistedGeneration === currentGeneration;
}

export function isPdfTextEntryTarget(target: EventTarget | null): boolean {
  if (typeof HTMLElement === "undefined" || !(target instanceof HTMLElement)) return false;
  const tag = target.tagName.toLowerCase();
  return tag === "input" || tag === "textarea" || tag === "select" || target.isContentEditable;
}

export function pdfReaderShortcut(event: Pick<KeyboardEvent, "key" | "ctrlKey" | "metaKey" | "altKey" | "shiftKey" | "target">): PdfReaderShortcut | null {
  if (event.altKey || isPdfTextEntryTarget(event.target)) return null;
  const command = event.ctrlKey || event.metaKey;
  const key = event.key.toLowerCase();
  if (command && key === "f") return "SEARCH";
  if (command && (key === "+" || key === "=")) return "ZOOM_IN";
  if (command && key === "-") return "ZOOM_OUT";
  if (command && key === "0") return "RESET_ZOOM";
  if (!command && key === "pagedown") return "NEXT_PAGE";
  if (!command && key === "pageup") return "PREVIOUS_PAGE";
  if (!command && key === "home") return "FIRST_PAGE";
  if (!command && key === "end") return "LAST_PAGE";
  return null;
}

function boundaryMatches(text: string, start: number, length: number): boolean {
  const before = start > 0 ? text[start - 1] : "";
  const after = start + length < text.length ? text[start + length] : "";
  return (!before || !WORD_CHARACTER.test(before)) && (!after || !WORD_CHARACTER.test(after));
}

function snippetFor(text: string, start: number, length: number): string {
  const from = Math.max(0, start - 52);
  const to = Math.min(text.length, start + length + 72);
  return `${from > 0 ? "…" : ""}${text.slice(from, to).replace(/\s+/g, " ").trim()}${to < text.length ? "…" : ""}`;
}

export async function searchPdfDocument(
  document: SearchablePdfDocument,
  rawQuery: string,
  options: PdfSearchOptions,
  signal: AbortSignal,
  onProgress?: (completedPages: number, totalPages: number) => void,
): Promise<PdfSearchResult[]> {
  const query = rawQuery.trim();
  if (query.length < 2) return [];
  const totalPages = Math.max(0, Number(document.numPages || 0));
  if (!totalPages) return [];
  const needle = options.caseSensitive ? query : query.toLocaleLowerCase();
  const resultsByPage = new Map<number, PdfSearchResult[]>();
  let nextPage = 1;
  let completed = 0;

  const searchPage = async (pageNumber: number): Promise<void> => {
    if (signal.aborted) throw new DOMException("PDF search cancelled", "AbortError");
    const page = await document.getPage(pageNumber);
    const textContent = await page.getTextContent();
    const text = textContent.items.map((item) => String(item?.str || "")).join(" ");
    const haystack = options.caseSensitive ? text : text.toLocaleLowerCase();
    const pageResults: PdfSearchResult[] = [];
    let cursor = 0;
    let ordinal = 1;
    while (cursor <= haystack.length - needle.length) {
      if (signal.aborted) throw new DOMException("PDF search cancelled", "AbortError");
      const match = haystack.indexOf(needle, cursor);
      if (match < 0) break;
      if (!options.wholeWord || boundaryMatches(text, match, query.length)) {
        pageResults.push({
          id: `${pageNumber}:${match}:${query.length}`,
          page: pageNumber,
          ordinal,
          start: match,
          length: query.length,
          snippet: snippetFor(text, match, query.length),
        });
        ordinal += 1;
      }
      cursor = match + Math.max(1, needle.length);
    }
    resultsByPage.set(pageNumber, pageResults);
    completed += 1;
    onProgress?.(completed, totalPages);
  };

  const worker = async (): Promise<void> => {
    while (true) {
      if (signal.aborted) throw new DOMException("PDF search cancelled", "AbortError");
      const pageNumber = nextPage;
      nextPage += 1;
      if (pageNumber > totalPages) return;
      await searchPage(pageNumber);
    }
  };

  await Promise.all(Array.from({ length: Math.min(4, totalPages) }, () => worker()));
  return Array.from({ length: totalPages }, (_, index) => resultsByPage.get(index + 1) || []).flat();
}

export function highlightPdfText(text: string, query: string, options: PdfSearchOptions, active = false): string {
  const needle = query.trim();
  if (needle.length < 2) return text;
  const source = options.caseSensitive ? text : text.toLocaleLowerCase();
  const matchNeedle = options.caseSensitive ? needle : needle.toLocaleLowerCase();
  let cursor = 0;
  let output = "";
  while (cursor < text.length) {
    const match = source.indexOf(matchNeedle, cursor);
    if (match < 0) {
      output += escapeHtml(text.slice(cursor));
      break;
    }
    if (options.wholeWord && !boundaryMatches(text, match, needle.length)) {
      output += escapeHtml(text.slice(cursor, match + needle.length));
      cursor = match + needle.length;
      continue;
    }
    output += escapeHtml(text.slice(cursor, match));
    output += `<mark class="pdf-engine-search-mark${active ? " is-active" : ""}">${escapeHtml(text.slice(match, match + needle.length))}</mark>`;
    cursor = match + needle.length;
  }
  return output;
}

function escapeHtml(value: string): string {
  return value
    .replaceAll("&", "&amp;")
    .replaceAll("<", "&lt;")
    .replaceAll(">", "&gt;")
    .replaceAll('"', "&quot;")
    .replaceAll("'", "&#039;");
}
