import { useEffect, useMemo, useRef, useState } from "react";
import { getCachedUser } from "../../services/auth";
import { useVirtualizer } from "@tanstack/react-virtual";
import {
  acknowledgeRevision,
  createRevisionExport,
  getRevisionDiff,
  getRevisionRead,
  getRevisionWorkflow,
  type ManualReadPayload,
} from "../../services/manuals";
import { useManualRouteContext } from "./context";
import "./manualReader.css";
import { ManualsReaderShell, TenantBrandingProvider } from "../../packages/manuals-reader";

function chunk<T>(arr: T[], size: number): T[][] {
  const out: T[][] = [];
  for (let i = 0; i < arr.length; i += size) out.push(arr.slice(i, i + size));
  return out;
}

export default function ManualReaderPage() {
  const { tenant, manualId, revId } = useManualRouteContext();
  const [payload, setPayload] = useState<ManualReadPayload | null>(null);
  const [workflowStatus, setWorkflowStatus] = useState<string>("-");
  const [diffSummary, setDiffSummary] = useState<Record<string, number>>({});
  const [search, setSearch] = useState("");
  const [activeSection, setActiveSection] = useState<string>("");
  const [ackText, setAckText] = useState("I acknowledge receipt and review of this revision.");
  const [controlled, setControlled] = useState(false);
  const [watermarkOn, setWatermarkOn] = useState(true);
  const [tocOpen, setTocOpen] = useState(true);
  const [inspectorOpen, setInspectorOpen] = useState(true);
  const [layout, setLayout] = useState<"continuous" | "paged-1" | "paged-2" | "paged-3">((localStorage.getItem("manuals.layout") as any) || "continuous");
  const [zoom, setZoom] = useState(Number(localStorage.getItem("manuals.zoom") || "100"));
  const sectionRefs = useRef<Record<string, HTMLElement | null>>({});
  const pagedParentRef = useRef<HTMLDivElement | null>(null);
  const [lastEventId, setLastEventId] = useState(localStorage.getItem("manuals.lastEventId") || "");
  const canDisableWatermark = !!getCachedUser()?.is_amo_admin || !!getCachedUser()?.is_superuser || ["QUALITY_MANAGER", "AMO_ADMIN", "SUPERUSER", "LIBRARY"].includes((getCachedUser() as any)?.role || "");

  const refreshReaderState = () => {
    if (!tenant || !manualId || !revId) return;
    getRevisionRead(tenant, manualId, revId).then(setPayload).catch(() => undefined);
    getRevisionWorkflow(tenant, manualId, revId).then((v) => setWorkflowStatus(v.status)).catch(() => undefined);
    getRevisionDiff(tenant, manualId, revId).then((v) => setDiffSummary(v.summary_json || {})).catch(() => undefined);
  };

  useEffect(() => {
    if (!tenant || !manualId || !revId) return;
    refreshReaderState();
  }, [tenant, manualId, revId]);

  useEffect(() => {
    localStorage.setItem("manuals.layout", layout);
    localStorage.setItem("manuals.zoom", String(zoom));
  }, [layout, zoom]);

  useEffect(() => {
    const obs = new IntersectionObserver(
      (entries) => {
        const best = entries
          .filter((e) => e.isIntersecting)
          .sort((a, b) => b.intersectionRatio - a.intersectionRatio)[0];
        if (!best?.target?.id) return;
        const anchor = best.target.id;
        setActiveSection(anchor);
        localStorage.setItem(`manuals.position.${revId}`, anchor);
        window.history.replaceState({}, "", `${window.location.pathname}#${anchor}`);
      },
      { rootMargin: "-10% 0px -70% 0px", threshold: [0.2, 0.5, 0.8] },
    );

    Object.values(sectionRefs.current).forEach((el) => {
      if (el) obs.observe(el);
    });
    return () => obs.disconnect();
  }, [payload?.sections, revId]);

  useEffect(() => {
    const savedAnchor = localStorage.getItem(`manuals.position.${revId || ""}`);
    if (savedAnchor) {
      setTimeout(() => document.getElementById(savedAnchor)?.scrollIntoView({ block: "start" }), 150);
    }
  }, [revId]);

  useEffect(() => {
    if (!tenant || !manualId || !revId) return;
    const streamUrl = new URL(`/api/events`, window.location.origin);
    if (lastEventId) streamUrl.searchParams.set("lastEventId", lastEventId);
    const source = new EventSource(streamUrl.toString());

    source.onmessage = (event) => {
      if (event.lastEventId) {
        setLastEventId(event.lastEventId);
        localStorage.setItem("manuals.lastEventId", event.lastEventId);
      }
      try {
        const payload = JSON.parse(event.data || "{}");
        const entityId = payload?.entity_id || payload?.entityId;
        const entityType = payload?.entity_type || payload?.entityType;
        if ((entityType || "").includes("manual") || entityId === revId || entityId === manualId) {
          refreshReaderState();
        }
      } catch {
        // ignore malformed event payload
      }
    };

    source.addEventListener("reset", () => {
      localStorage.removeItem("manuals.lastEventId");
      setLastEventId("");
      refreshReaderState();
    });

    source.onerror = () => {
      source.close();
    };

    return () => source.close();
  }, [tenant, manualId, revId]);

  const blocksBySection = useMemo(() => {
    const grouped: Record<string, ManualReadPayload["blocks"]> = {};
    (payload?.blocks || []).forEach((block) => {
      grouped[block.section_id] = grouped[block.section_id] || [];
      grouped[block.section_id].push(block);
    });
    return grouped;
  }, [payload?.blocks]);

  const flatPages = useMemo(() => {
    const source = (payload?.sections || []).map((section) => ({
      section,
      blocks: (blocksBySection[section.id] || []).filter((b) => !search || b.text.toLowerCase().includes(search.toLowerCase())),
    }));
    return chunk(source, 1);
  }, [payload?.sections, blocksBySection, search]);

  const columns = layout === "paged-3" ? 3 : layout === "paged-2" ? 2 : 1;
  const rows = useMemo(() => chunk(flatPages, columns), [flatPages, columns]);

  const rowVirtualizer = useVirtualizer({
    count: layout === "continuous" ? 0 : rows.length,
    getScrollElement: () => pagedParentRef.current,
    estimateSize: () => 860,
    overscan: 2,
  });

  const changedBlocks = Number(diffSummary.changed_blocks || 0);
  const isPublished = !payload?.not_published;

  const viewer = layout === "continuous" ? (
    <main className="manual-reader-pane p-4" style={{ transform: `scale(${zoom / 100})`, transformOrigin: "top center" }}>
      {(payload?.sections || []).map((section) => (
        <section
          key={section.id}
          id={section.anchor_slug}
          ref={(el) => {
            sectionRefs.current[section.id] = el;
          }}
          className="mb-8 scroll-mt-24"
        >
          <h2 className="mb-3 text-lg font-semibold">{section.heading}</h2>
          <div className="space-y-2">
            {(blocksBySection[section.id] || []).map((block, idx) => {
              if (search && !block.text.toLowerCase().includes(search.toLowerCase())) return null;
              const showChangeBar = changedBlocks > 0 && idx < changedBlocks;
              return (
                <article key={`${block.change_hash}-${idx}`} className={`manual-reader-content rounded border p-2 text-sm ${showChangeBar ? "border-l-4 border-l-sky-500" : ""}`}>
                  <div dangerouslySetInnerHTML={{ __html: block.html || `<p>${block.text}</p>` }} />
                </article>
              );
            })}
          </div>
        </section>
      ))}
    </main>
  ) : (
    <main ref={pagedParentRef} className="manual-reader-pane p-3 overflow-auto" style={{ height: "calc(100vh - 12rem)" }}>
      <div style={{ height: `${rowVirtualizer.getTotalSize()}px`, position: "relative" }}>
        {rowVirtualizer.getVirtualItems().map((vr) => {
          const row = rows[vr.index] || [];
          return (
            <div key={vr.key} style={{ position: "absolute", top: 0, left: 0, width: "100%", transform: `translateY(${vr.start}px)` }}>
              <div className="manual-paged-grid" style={{ gridTemplateColumns: `repeat(${columns}, minmax(0, 1fr))` }}>
                {row.map((page, pageIdx) => (
                  <article key={`${vr.index}-${pageIdx}`} className="manual-page" style={{ transform: `scale(${zoom / 100})`, transformOrigin: "top center" }}>
                    <div className="manual-page-header">{manualId} · Rev {revId}</div>
                    {page.map((entry) => (
                      <section key={entry.section.id} id={entry.section.anchor_slug} className="mb-3">
                        <h3 className="font-semibold text-sm mb-1">{entry.section.heading}</h3>
                        {entry.blocks.map((block, idx) => (
                          <div key={`${block.change_hash}-${idx}`} className="manual-reader-content text-xs mb-1" dangerouslySetInnerHTML={{ __html: block.html || `<p>${block.text}</p>` }} />
                        ))}
                      </section>
                    ))}
                    <div className="manual-page-footer">Page {vr.index * columns + pageIdx + 1}</div>
                  </article>
                ))}
              </div>
            </div>
          );
        })}
      </div>
    </main>
  );

  return (
    <TenantBrandingProvider tenantSlug={tenant}>
    <ManualsReaderShell
      tenantSlug={tenant}
      mode={window.location.search.includes("standalone=1") ? "standalone" : "embedded"}
      manualLabel={manualId ? `Manual ${manualId}` : "Manual"}
      statusBadge={workflowStatus}
      revMeta={`Rev ${revId || "-"}`}
      locationLabel={activeSection || "Reader"}
      onToggleToc={() => setTocOpen((v) => !v)}
      onToggleInspector={() => setInspectorOpen((v) => !v)}
      onLayoutChange={setLayout}
      onZoomIn={() => setZoom((z) => Math.min(200, z + 10))}
      onZoomOut={() => setZoom((z) => Math.max(60, z - 10))}
      onZoomReset={() => setZoom(100)}
    >
      <div className="px-4 lg:px-6">
        <div className="rounded border bg-slate-50 p-3 text-sm mb-3">
          <b>Current Revision Status:</b> {workflowStatus} · <b>Revision:</b> {revId} ·{" "}
          {isPublished ? <span className="font-semibold text-emerald-700">PUBLISHED</span> : <span className="font-semibold text-amber-700">NOT PUBLISHED</span>}
        </div>

        <div className="manual-reader-layout">
          {tocOpen ? (
            <aside className="manual-reader-toc p-3 h-fit xl:sticky xl:top-20">
              <h3 className="mb-2 font-medium">Table of Contents</h3>
              <input className="mb-2 w-full rounded border px-2 py-1 text-sm" value={search} onChange={(e) => setSearch(e.target.value)} placeholder="Search in manual" />
              <div className="max-h-[70vh] space-y-1 overflow-auto text-sm">
                {(payload?.sections || []).map((s) => (
                  <a key={s.id} href={`#${s.anchor_slug}`} className={`block rounded px-2 py-1 ${activeSection === s.anchor_slug ? "bg-slate-100 font-medium" : ""}`} style={{ paddingLeft: `${s.level * 10}px` }}>{s.heading}</a>
                ))}
              </div>
            </aside>
          ) : null}

          {viewer}

          {inspectorOpen ? (
            <aside className="manual-reader-aside p-3 h-fit xl:sticky xl:top-20 space-y-3">
              <h3 className="font-medium">Revision / Compliance</h3>
              <div className="rounded border p-2 text-sm">
                <div>Changed sections: {diffSummary.changed_sections || 0}</div>
                <div>Changed blocks: {diffSummary.changed_blocks || 0}</div>
                <div>Added: {diffSummary.added || 0} · Removed: {diffSummary.removed || 0}</div>
              </div>
              <div className="space-y-2 rounded border p-2 text-sm">
                <h4 className="font-medium">Acknowledgement</h4>
                <textarea className="w-full rounded border p-2 text-xs" rows={3} value={ackText} onChange={(e) => setAckText(e.target.value)} />
                <button className="rounded bg-slate-900 px-3 py-1 text-xs text-white" onClick={() => tenant && manualId && revId && acknowledgeRevision(tenant, manualId, revId, ackText)}>Acknowledge Revision</button>
              </div>
              <div className="space-y-2 rounded border p-2 text-sm">
                <h4 className="font-medium">Print / Export</h4>
                <label className="flex items-center justify-between text-xs"><span>Uncontrolled watermark</span><input type="checkbox" checked={watermarkOn} disabled={controlled || !canDisableWatermark} onChange={(e) => setWatermarkOn(e.target.checked)} /></label>
                <label className="flex items-center justify-between text-xs"><span>Controlled hard copy</span><input type="checkbox" disabled={!canDisableWatermark} checked={controlled} onChange={(e) => { const checked = e.target.checked; setControlled(checked); if (checked) setWatermarkOn(false); }} /></label>{!canDisableWatermark ? <p className="text-[11px] text-amber-700">Only authorized roles can disable watermark or issue controlled copies.</p> : null}
                {controlled ? (
                  <div className="space-y-1">
                    <input className="w-full rounded border px-2 py-1 text-xs" placeholder="Controlled Copy No" />
                    <input className="w-full rounded border px-2 py-1 text-xs" placeholder="Recipient" />
                    <input className="w-full rounded border px-2 py-1 text-xs" placeholder="Purpose" />
                  </div>
                ) : null}
                <button className="rounded bg-sky-700 px-3 py-1 text-xs text-white" onClick={() => tenant && manualId && revId && createRevisionExport(tenant, manualId, revId, { controlled_bool: controlled, watermark_uncontrolled_bool: watermarkOn, version_label: `rev-${revId}` })}>Generate PDF Artifact</button>
              </div>
            </aside>
          ) : null}
        </div>
      </div>
    </ManualsReaderShell>
    </TenantBrandingProvider>
  );
}
