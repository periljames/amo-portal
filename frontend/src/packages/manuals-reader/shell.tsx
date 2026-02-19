import React, { useEffect, useMemo, useState } from "react";
import { Link, useNavigate } from "react-router-dom";
import { ArrowLeft, Focus, Maximize, Minimize, PanelLeft, PanelRight, Search, ZoomIn, ZoomOut } from "lucide-react";
import { useTenantBranding } from "./branding";

const PORTAL_URL = (import.meta as any).env?.VITE_PORTAL_URL as string | undefined;

type Props = {
  tenantSlug: string;
  mode: "embedded" | "standalone";
  manualLabel?: string;
  statusBadge?: string;
  revMeta?: string;
  locationLabel?: string;
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
    if (props.mode === "embedded") return `/t/${props.tenantSlug}/manuals`;
    if (PORTAL_URL) return `${PORTAL_URL}/t/${props.tenantSlug}/manuals`;
    return "/";
  }, [props.mode, props.tenantSlug]);

  useEffect(() => {
    localStorage.setItem("manuals.focusMode", focusMode ? "1" : "0");
  }, [focusMode]);

  const toggleFullscreen = async () => {
    const el = document.getElementById("manuals-reader-root");
    if (!document.fullscreenElement && el) {
      await el.requestFullscreen();
      setIsFullscreen(true);
      setHint(true);
      setTimeout(() => setHint(false), 3000);
      return;
    }
    await document.exitFullscreen();
    setIsFullscreen(false);
  };

  return (
    <div id="manuals-reader-root" className="min-h-screen" style={{ background: "var(--tenant-bg)" }}>
      <header className="sticky top-0 z-40 flex h-16 items-center justify-between gap-3 border-b px-3" style={{ background: "color-mix(in srgb, var(--paper) 86%, transparent)", color: "var(--ink)", backdropFilter: "blur(10px)" }}>
        <div className="flex items-center gap-2 min-w-0">
          <button className="rounded border px-2 py-1 text-xs inline-flex items-center gap-1" onClick={() => navigate(exitTarget)}>
            <ArrowLeft size={14} /> Back to Portal
          </button>
          {props.mode === "standalone" && typeof window !== "undefined" && (window as any).opener ? (
            <button className="rounded border px-2 py-1 text-xs" onClick={() => window.close()}>Close</button>
          ) : null}
          {branding.logoUrl ? <img src={branding.logoUrl} alt="tenant logo" className="h-7 w-7 rounded object-cover" /> : null}
          <Link to={`/t/${props.tenantSlug}/manuals`} className="truncate text-sm font-semibold" style={{ color: "var(--ink)" }}>
            {branding.preferredName}
          </Link>
          {props.manualLabel ? <span className="hidden md:inline rounded border px-2 py-1 text-xs">{props.manualLabel}</span> : null}
        </div>

        <div className="hidden lg:flex items-center gap-2 text-xs" style={{ color: "color-mix(in srgb, var(--ink) 70%, transparent)" }}>
          <Search size={14} />
          <span>{props.locationLabel || "Document"}</span>
        </div>

        <div className="flex items-center gap-1">
          <span className="hidden sm:inline rounded px-2 py-1 text-xs" style={{ background: "var(--tenant-accent)", color: "white" }}>{props.statusBadge || "Draft"}</span>
          <span className="hidden md:inline text-xs" style={{ color: "color-mix(in srgb, var(--ink) 70%, transparent)" }}>{props.revMeta || "Rev"}</span>
          {(["continuous", "paged-1", "paged-2", "paged-3"] as const).map((layout) => (
            <button key={layout} className="hidden xl:inline rounded border px-2 py-1 text-xs" onClick={() => props.onLayoutChange?.(layout)}>{layout.replace("paged-", "").replace("continuous", "Cont")}</button>
          ))}
          <button className="rounded border p-1" onClick={() => props.onZoomOut?.()}><ZoomOut size={14} /></button>
          <button className="rounded border p-1" onClick={() => props.onZoomReset?.()}>100%</button>
          <button className="rounded border p-1" onClick={() => props.onZoomIn?.()}><ZoomIn size={14} /></button>
          <button className="rounded border p-1" onClick={() => setFocusMode((v) => !v)}><Focus size={14} /></button>
          <button className="rounded border p-1" onClick={toggleFullscreen}>{isFullscreen ? <Minimize size={14} /> : <Maximize size={14} />}</button>
          <button className="rounded border p-1" onClick={props.onToggleToc}><PanelLeft size={14} /></button>
          <button className="rounded border p-1" onClick={props.onToggleInspector}><PanelRight size={14} /></button>
        </div>
      </header>

      {hint ? <div className="fixed right-3 top-20 z-50 rounded bg-black/80 px-3 py-1 text-xs text-white">Esc to exit fullscreen</div> : null}
      <main className={focusMode ? "pb-4" : "py-2"}>{props.children}</main>
    </div>
  );
}
