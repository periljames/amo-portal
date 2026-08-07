export type PdfScaleMode = "AUTO" | "ACTUAL" | "PAGE" | "WIDTH" | "CUSTOM";

export const PDF_ZOOM_STEPS = [50, 75, 100, 125, 150, 200, 300, 400] as const;

export function clampPdfZoom(value: number): number {
  return Math.min(400, Math.max(50, Math.round(value)));
}

export function pdfPageWidth({
  mode,
  zoom,
  availableWidth,
  availableHeight,
  pageRatio,
  actualWidth,
}: {
  mode: PdfScaleMode;
  zoom: number;
  availableWidth: number;
  availableHeight: number;
  pageRatio: number;
  actualWidth: number;
}): number {
  const safeWidth = Math.max(230, availableWidth);
  const safeHeight = Math.max(260, availableHeight);
  const safeRatio = pageRatio > 0 ? pageRatio : 1.414;
  const safeActual = Math.max(230, actualWidth || 612);
  const fitPage = Math.max(230, Math.min(safeWidth, safeHeight / safeRatio));

  if (mode === "PAGE") return Math.round(fitPage);
  if (mode === "WIDTH") return Math.round(safeWidth);
  if (mode === "ACTUAL") return Math.round(safeActual);
  if (mode === "CUSTOM") return Math.round(safeActual * (clampPdfZoom(zoom) / 100));

  return Math.round(safeActual <= safeWidth && safeActual * safeRatio <= safeHeight
    ? safeActual
    : fitPage);
}

export function pdfScaleLabel(mode: PdfScaleMode, zoom: number): string {
  if (mode === "AUTO") return "Automatic Zoom";
  if (mode === "ACTUAL") return "Actual Size";
  if (mode === "PAGE") return "Page Fit";
  if (mode === "WIDTH") return "Page Width";
  return `${clampPdfZoom(zoom)}%`;
}

export function parsePdfScaleValue(value: string): { mode: PdfScaleMode; zoom?: number } {
  if (value === "AUTO") return { mode: "AUTO" };
  if (value === "ACTUAL") return { mode: "ACTUAL" };
  if (value === "PAGE") return { mode: "PAGE" };
  if (value === "WIDTH") return { mode: "WIDTH" };
  const zoom = Number(value);
  return Number.isFinite(zoom)
    ? { mode: "CUSTOM", zoom: clampPdfZoom(zoom) }
    : { mode: "AUTO" };
}
