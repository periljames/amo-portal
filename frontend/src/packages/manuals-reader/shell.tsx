import React, { useEffect, useMemo, useState } from "react";
import { Link, useNavigate } from "react-router-dom";
import {
  ArrowLeft,
  Bell,
  ClipboardPlus,
  Clock3,
  Focus,
  Headset,
  HelpCircle,
  Home,
  ListChecks,
  ListOrdered,
  Maximize,
  Minimize,
  PanelLeft,
  PanelRight,
  Search,
  Settings,
  Wrench,
  X,
  ZoomIn,
  ZoomOut,
} from "lucide-react";
import AdminButton from "../../components/UI/Admin/Button";
import Badge from "../../components/UI/Admin/Badge";
import { useTenantBranding } from "./branding";

const PORTAL_URL = (import.meta as any).env?.VITE_PORTAL_URL as string | undefined;

export type ReaderActionId =
  | "notifications"
  | "change-request"
  | "delta"
  | "task"
  | "history"
  | "order-list"
  | "support"
  | "help"
  | "home"
  | "account";

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
  onActionClick?: (action: ReaderActionId) => void;
  activeAction?: ReaderActionId | null;
  children: React.ReactNode;
};

export function ManualsReaderShell(props: Props) {
  const navigate = useNavigate();
  const branding = useTenantBranding();
  const [isFullscreen, setIsFullscreen] = useState(false);
  const [focusMode, setFocusMode] = useState(localStorage.getItem("manuals.focusMode") === "1");
  const [headerCollapsed, setHeaderCollapsed] = useState(localStorage.getItem("manuals.headerCollapsed") === "1");
  const [hint, setHint] = useState(false);

  const exitTarget = useMemo(() => {
    if (props.mode === "embedded") return props.fallbackPath || `/t/${props.tenantSlug}/manuals`;
    if (PORTAL_URL) return `${PORTAL_URL}/t/${props.tenantSlug}/manuals`;
    return "/";
  }, [props.mode, props.tenantSlug, props.fallbackPath]);

  useEffect(() => {
    localStorage.setItem("manuals.focusMode", focusMode ? "1" : "0");
    document.body.dataset.manualReaderFocus = focusMode ? "1" : "0";
  }, [focusMode]);

  useEffect(() => {
    localStorage.setItem("manuals.headerCollapsed", headerCollapsed ? "1" : "0");
  }, [headerCollapsed]);

  useEffect(() => {
    const onChange = () => setIsFullscreen(Boolean(document.fullscreenElement));
    document.addEventListener("fullscreenchange", onChange);
    return () => document.removeEventListener("fullscreenchange", onChange);
  }, []);

  const toggleFullscreen = async () => {
    const el = document.getElementById("manuals-reader-root");
    if (!document.fullscreenElement && el) {
      await el.requestFullscreen();
      setFocusMode(true);
      setHint(true);
      setTimeout(() => setHint(false), 3000);
      return;
    }
    if (document.fullscreenElement) await document.exitFullscreen();
  };

  const goBack = () => {
    if (typeof window !== "undefined" && window.history.length > 1) return navigate(-1);
    navigate(exitTarget);
  };

  const actions: Array<{ id: ReaderActionId; label: string; icon: any }> = [
    { id: "notifications", label: "Notifications", icon: Bell },
    { id: "change-request", label: "Change Request", icon: ClipboardPlus },
    { id: "delta", label: "Manual Delta", icon: Wrench },
    { id: "task", label: "Task Panel", icon: ListChecks },
    { id: "history", label: "History", icon: Clock3 },
    { id: "order-list", label: "Order List", icon: ListOrdered },
    { id: "support", label: "Support", icon: Headset },
    { id: "help", label: "Help", icon: HelpCircle },
    { id: "home", label: "Home", icon: Home },
    { id: "account", label: "Account", icon: Settings },
  ];

  return (
    <div id="manuals-reader-root" className="manual-reader-root">
      <header className={`manual-reader-topbar ${headerCollapsed ? "collapsed" : ""}`}>
        <div className="manual-reader-topbar-cluster">
          <AdminButton variant="ghost" size="sm" onClick={goBack} title="Back to Portal">
            <ArrowLeft size={14} /> Back to Portal
          </AdminButton>
          {branding.logoUrl ? <img src={branding.logoUrl} alt="tenant logo" className="manual-reader-brand-logo" /> : null}
          <Link to={`/t/${props.tenantSlug}/manuals`} className="manual-reader-brand-name">{branding.preferredName}</Link>
          {props.manualLabel ? <span className="manual-reader-manual-chip" title={props.manualLabel}>{props.manualLabel}</span> : null}
        </div>

        <div className="manual-reader-topbar-search">
          <Search size={14} />
          <input
            id="manual-reader-search" className="manual-reader-search-input"
            value={props.searchValue || ""}
            onChange={(e) => props.onSearchChange?.(e.target.value)}
            placeholder="Search publications… (Ctrl/Cmd+K)"
            aria-label="Global publication search"
          />
          <span className="manual-reader-location-label">{props.locationLabel || "Document"}</span>
        </div>

        <div className="manual-reader-topbar-cluster">
          {props.missingMetaFields?.length ? (
            <span title={`Missing fields: ${props.missingMetaFields.join(", ")}`}><Badge tone="warning" size="sm" className="cursor-help">Metadata incomplete</Badge></span>
          ) : (
            <Badge tone="info" size="sm">{props.statusBadge || "Loading"}</Badge>
          )}
          <span className="manual-reader-meta-pill">{props.revMeta || "Rev metadata"}</span>
          {(["continuous", "paged-1", "paged-2", "paged-3"] as const).map((layout) => (
            <button key={layout} className="manual-reader-icon-btn" onClick={() => props.onLayoutChange?.(layout)} title={`Layout ${layout}`}>
              {layout === "continuous" ? "Cont" : layout.replace("paged-", "")}
            </button>
          ))}
          <button className="manual-reader-icon-btn" onClick={() => props.onZoomOut?.()} title="Zoom out"><ZoomOut size={14} /></button>
          <button className="manual-reader-icon-btn" onClick={() => props.onZoomReset?.()} title="Reset zoom">100%</button>
          <button className="manual-reader-icon-btn" onClick={() => props.onZoomIn?.()} title="Zoom in"><ZoomIn size={14} /></button>
          <button className="manual-reader-icon-btn" onClick={() => setFocusMode((v) => !v)} title="Focus mode"><Focus size={14} /></button>
          <button className="manual-reader-icon-btn" onClick={() => setHeaderCollapsed((v) => !v)} title={headerCollapsed ? "Expand header" : "Collapse header"}>
            {headerCollapsed ? "Expand" : "Collapse"}
          </button>
          <button className="manual-reader-icon-btn" onClick={toggleFullscreen} title="Fullscreen">{isFullscreen ? <Minimize size={14} /> : <Maximize size={14} />}</button>
          <button className="manual-reader-icon-btn" onClick={props.onToggleToc} title="Toggle hierarchy" aria-label="Toggle hierarchy"><PanelLeft size={14} /></button>
          <button className="manual-reader-icon-btn" onClick={props.onToggleInspector} title="Toggle contextual panel" aria-label="Toggle contextual panel"><PanelRight size={14} /></button>
          <span className="manual-reader-action-separator" />
          {actions.map((action, idx) => {
            const Icon = action.icon;
            const active = props.activeAction === action.id;
            return (
              <React.Fragment key={action.id}>
                {idx > 0 ? <span className="manual-reader-action-separator" /> : null}
                <button
                  className={`manual-reader-icon-btn utility ${active ? "active" : ""}`}
                  onClick={() => props.onActionClick?.(action.id)}
                  title={action.label}
                  aria-label={action.label}
                >
                  <Icon size={14} />
                </button>
              </React.Fragment>
            );
          })}
          {props.mode === "standalone" && typeof window !== "undefined" && (window as any).opener ? (
            <button className="manual-reader-icon-btn" onClick={() => window.close()} title="Close window"><X size={14} /></button>
          ) : null}
        </div>
      </header>

      {hint ? <div className="manual-reader-fullscreen-hint">Esc to exit fullscreen</div> : null}
      <main className="manual-reader-main">{props.children}</main>
    </div>
  );
}
