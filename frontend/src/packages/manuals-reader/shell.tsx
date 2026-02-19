import React, { useEffect, useMemo, useState } from "react";
import { Link, useNavigate } from "react-router-dom";
import {
  ArrowLeft,
  Focus,
  Maximize,
  Minimize,
  PanelLeft,
  PanelRight,
  Search,
  ZoomIn,
  ZoomOut,
  LayoutPanelTop,
} from "lucide-react";
import { useTenantBranding } from "./branding";

const PORTAL_URL = (import.meta as any).env?.VITE_PORTAL_URL as string | undefined;

type Props = {
  tenantSlug: string;
  mode: "embedded" | "standalone";
  manualLabel?: string;
  statusBadge?: string;
  revMeta?: string;
  locationLabel?: string;
  missingMetaFields?: string[];
  fallbackPath?: string;
  searchValue?: string;
  onSearchChange?: (value: string) => void;
  onToggleToc?: () => void;
  onToggleInspector?: () => void;
  onLayoutChange?: (v: "continuous" | "paged-1" | "paged-2" | "paged-3") => void;
  onZoomIn?: () => void;
  onZoomOut?: () => void;
  onZoomReset?: () => void;
  children: React.ReactNode;
};

export function ManualsReaderShell(props: Props) {
  const navigate = useNavigate();
  const branding = useTenantBranding();
  const [isFullscreen, setIsFullscreen] = useState(false);
  const [focusMode, setFocusMode] = useState(localStorage.getItem("manuals.focusMode") === "1");
  const [hint, setHint] = useState(false);

  const exitTarget = useMemo(() => {
    if (props.mode === "embedded") {
      return props.fallbackPath || `/t/${props.tenantSlug}/manuals`;
    }
    if (PORTAL_URL) return `${PORTAL_URL}/t/${props.tenantSlug}/manuals`;
    return "/";
  }, [props.mode, props.tenantSlug, props.fallbackPath]);

  useEffect(() => {
    localStorage.setItem("manuals.focusMode", focusMode ? "1" : "0");
  }, [focusMode]);

  const toggleFullscreen = async () => {
    const el = document.getElementById("manuals-reader-root");
    if (!document.fullscreenElement && el) {
      await el.requestFullscreen();
      setIsFullscreen(true);
      setFocusMode(true);
      setHint(true);
      setTimeout(() => setHint(false), 3000);
      return;
    }
    await document.exitFullscreen();
    setIsFullscreen(false);
  };

  const goBack = () => {
    if (typeof window !== "undefined" && window.history.length > 1) {
      navigate(-1);
      return;
    }
    navigate(exitTarget);
  };

  return (
    <div id="manuals-reader-root" className="h-screen" style={{ background: "var(--tenant-bg)" }}>
      <header
        className="sticky top-0 z-40 flex h-16 items-center justify-between gap-3 border-b px-3"
        style={{
          background: "color-mix(in srgb, var(--paper) 86%, transparent)",
          color: "var(--ink)",
          backdropFilter: "blur(10px)",
        }}
      >
        <div className="flex min-w-0 items-center gap-2">
          <button className="rounded border px-2 py-1 text-xs inline-flex items-center gap-1 min-h-9" onClick={goBack} title="Back to Portal">
            <ArrowLeft size={14} /> Back to Portal
          </button>
          {props.mode === "standalone" && typeof window !== "undefined" && (window as any).opener ? (
            <button className="rounded border px-2 py-1 text-xs min-h-9" onClick={() => window.close()}>Close</button>
          ) : null}
          {branding.logoUrl ? <img src={branding.logoUrl} alt="tenant logo" className="h-7 w-7 rounded object-cover" /> : null}
          <Link to={`/t/${props.tenantSlug}/manuals`} className="truncate text-sm font-semibold" style={{ color: "var(--ink)" }}>
            {branding.preferredName}
          </Link>
          {props.manualLabel ? <span className="hidden md:inline rounded border px-2 py-1 text-xs truncate max-w-56">{props.manualLabel}</span> : null}
        </div>

        <div className="hidden lg:flex items-center gap-2 text-xs min-w-0 flex-1 justify-center px-3" style={{ color: "color-mix(in srgb, var(--ink) 70%, transparent)" }}>
          <Search size={14} />
          <input
            className="w-full max-w-sm rounded border px-2 py-1 text-xs"
            value={props.searchValue || ""}
            onChange={(e) => props.onSearchChange?.(e.target.value)}
            placeholder="Search document (Ctrl/Cmd+K)"
            title="Search document"
          />
          <span className="truncate">{props.locationLabel || "Document"}</span>
        </div>

        <div className="flex items-center gap-1">
          {props.missingMetaFields?.length ? (
            <span className="hidden sm:inline rounded border border-amber-400 bg-amber-50 px-2 py-1 text-xs text-amber-700" title={`Missing: ${props.missingMetaFields.join(", ")}`}>Metadata missing</span>
          ) : (
            <span className="hidden sm:inline rounded px-2 py-1 text-xs" style={{ background: "var(--tenant-accent)", color: "white" }}>{props.statusBadge || "Loading"}</span>
          )}
          <span className="hidden md:inline text-xs" style={{ color: "color-mix(in srgb, var(--ink) 70%, transparent)" }}>{props.revMeta || "Rev metadata"}</span>
          {(["continuous", "paged-1", "paged-2", "paged-3"] as const).map((layout) => (
            <button key={layout} className="hidden xl:inline rounded border px-2 py-1 text-xs min-h-9" onClick={() => props.onLayoutChange?.(layout)} title={`Layout ${layout}`}>
              <LayoutPanelTop size={12} className="inline mr-1" />
              {layout === "continuous" ? "Cont" : layout.replace("paged-", "")}
            </button>
          ))}
          <button className="rounded border p-2 min-h-9 min-w-9" onClick={() => props.onZoomOut?.()} title="Zoom out"><ZoomOut size={14} /></button>
          <button className="rounded border p-2 min-h-9" onClick={() => props.onZoomReset?.()} title="Reset zoom">100%</button>
          <button className="rounded border p-2 min-h-9 min-w-9" onClick={() => props.onZoomIn?.()} title="Zoom in"><ZoomIn size={14} /></button>
          <button className="rounded border p-2 min-h-9 min-w-9" onClick={() => setFocusMode((v) => !v)} title="Focus mode"><Focus size={14} /></button>
          <button className="rounded border p-2 min-h-9 min-w-9" onClick={toggleFullscreen} title="Fullscreen">{isFullscreen ? <Minimize size={14} /> : <Maximize size={14} />}</button>
          <button className="rounded border p-2 min-h-9 min-w-9" onClick={props.onToggleToc} title="Toggle table of contents"><PanelLeft size={14} /></button>
          <button className="rounded border p-2 min-h-9 min-w-9" onClick={props.onToggleInspector} title="Toggle inspector"><PanelRight size={14} /></button>
        </div>
      </header>

      {hint ? <div className="fixed right-3 top-20 z-50 rounded bg-black/80 px-3 py-1 text-xs text-white">Esc to exit fullscreen</div> : null}
      <main className={focusMode ? "h-[calc(100vh-4rem)]" : "h-[calc(100vh-4rem)]"}>{props.children}</main>
    </div>
  );
}
