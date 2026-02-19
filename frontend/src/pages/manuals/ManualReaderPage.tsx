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

type InspectorTab = "compliance" | "ack" | "export";

function chunk<T>(arr: T[], size: number): T[][] {
  const out: T[][] = [];
  for (let i = 0; i < arr.length; i += size) out.push(arr.slice(i, i + size));
  return out;
}

export default function ManualReaderPage() {
  const { tenant, manualId, revId, amoCode, department } = useManualRouteContext();
  const [payload, setPayload] = useState<ManualReadPayload | null>(null);
  const [workflowStatus, setWorkflowStatus] = useState<string>("Loading");
  const [diffSummary, setDiffSummary] = useState<Record<string, number>>({});
  const [search, setSearch] = useState("");
  const [activeSection, setActiveSection] = useState<string>("");
  const [ackComment, setAckComment] = useState("");
  const [controlled, setControlled] = useState(false);
  const [watermarkOn, setWatermarkOn] = useState(true);
  const [tocOpen, setTocOpen] = useState(true);
  const [inspectorOpen, setInspectorOpen] = useState(true);
  const [inspectorTab, setInspectorTab] = useState<InspectorTab>("compliance");
  const [layout, setLayout] = useState<"continuous" | "paged-1" | "paged-2" | "paged-3">((localStorage.getItem("manuals.layout") as any) || "continuous");
  const [zoom, setZoom] = useState(Number(localStorage.getItem("manuals.zoom") || "100"));
  const sectionRefs = useRef<Record<string, HTMLElement | null>>({});
  const pagedParentRef = useRef<HTMLDivElement | null>(null);
  const [lastEventId, setLastEventId] = useState(localStorage.getItem("manuals.lastEventId") || "");

  const user = getCachedUser();
  const canDisableWatermark =
    !!user?.is_amo_admin ||
    !!user?.is_superuser ||
    ["QUALITY_MANAGER", "AMO_ADMIN", "SUPERUSER", "LIBRARY"].includes((user as any)?.role || "");

  const refreshReaderState = () => {
    if (!tenant || !manualId || !revId) return;
    getRevisionRead(tenant, manualId, revId).then(setPayload).catch(() => setPayload(null));
    getRevisionWorkflow(tenant, manualId, revId)
      .then((v) => setWorkflowStatus(v.status || "Metadata missing"))
      .catch(() => setWorkflowStatus("Metadata missing"));
    getRevisionDiff(tenant, manualId, revId).then((v) => setDiffSummary(v.summary_json || {})).catch(() => setDiffSummary({}));
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
        const best = entries.filter((e) => e.isIntersecting).sort((a, b) => b.intersectionRatio - a.intersectionRatio)[0];
        if (!best?.target?.id) return;
        const anchor = best.target.id;
        setActiveSection(anchor);
        localStorage.setItem(`manuals.position.${revId}`, anchor);
        window.history.replaceState({}, "", `${window.location.pathname}#${anchor}`);
      },
      { rootMargin: "-10% 0px -70% 0px", threshold: [0.2, 0.5, 0.8] },
    );

    Object.values(sectionRefs.current).forEach((el) => el && obs.observe(el));
    return () => obs.disconnect();
  }, [payload?.sections, revId]);

  useEffect(() => {
    const savedAnchor = localStorage.getItem(`manuals.position.${revId || ""}`);
    if (savedAnchor) setTimeout(() => document.getElementById(savedAnchor)?.scrollIntoView({ block: "start" }), 150);
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
        const evt = JSON.parse(event.data || "{}");
        const entityId = evt?.entity_id || evt?.entityId;
        const entityType = evt?.entity_type || evt?.entityType;
        if ((entityType || "").includes("manual") || entityId === revId || entityId === manualId) refreshReaderState();
      } catch {
        // ignore malformed events
      }
    };

    source.addEventListener("reset", () => {
      localStorage.removeItem("manuals.lastEventId");
      setLastEventId("");
      refreshReaderState();
    });

    source.onerror = () => source.close();
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
  const missingMetaFields = useMemo(() => {
    const missing: string[] = [];
    if (!workflowStatus || workflowStatus === "Metadata missing") missing.push("workflow status");
    if (!revId) missing.push("revision id");
    return missing;
  }, [workflowStatus, revId]);

  const isLoading = workflowStatus === "Loading" && !payload;
  const noContent = !isLoading && (!payload?.sections?.length || !payload?.blocks?.length);

  const viewer = layout === "continuous" ? (
    <main className="manual-reader-pane p-4 overflow-auto min-h-0" style={{ transform: `scale(${zoom / 100})`, transformOrigin: "top center" }}>
      {(payload?.sections || []).map((section) => (
        <section key={section.id} id={section.anchor_slug} ref={(el) => { sectionRefs.current[section.id] = el; }} className="mb-8 scroll-mt-24">
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
    <main ref={pagedParentRef} className="manual-reader-pane p-3 overflow-auto min-h-0">
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

  const fallbackPath = amoCode && department ? `/maintenance/${amoCode}/${department}/qms/documents` : `/t/${tenant}/manuals`;

  return (
    <TenantBrandingProvider tenantSlug={tenant}>
      <ManualsReaderShell
        tenantSlug={tenant}
        mode={window.location.search.includes("standalone=1") ? "standalone" : "embedded"}
        manualLabel={manualId ? `Manual ${manualId}` : "Manual"}
        statusBadge={workflowStatus}
        revMeta={`Rev ${revId || "n/a"}`}
        locationLabel={activeSection || "Reader"}
        missingMetaFields={missingMetaFields.length ? missingMetaFields : undefined}
        fallbackPath={fallbackPath}
        searchValue={search}
        onSearchChange={setSearch}
        onToggleToc={() => setTocOpen((v) => !v)}
        onToggleInspector={() => setInspectorOpen((v) => !v)}
        onLayoutChange={(next) => {
          if ((next === "paged-2" || next === "paged-3") && window.innerWidth < 1280) {
            setLayout("continuous");
            return;
          }
          setLayout(next);
        }}
        onZoomIn={() => setZoom((z) => Math.min(200, z + 10))}
        onZoomOut={() => setZoom((z) => Math.max(60, z - 10))}
        onZoomReset={() => setZoom(100)}
      >
        <div className="manual-reader-workspace px-3 py-3 lg:px-4">
          {tocOpen ? (
            <aside className="manual-reader-toc p-3 min-h-0 overflow-auto">
              <h3 className="mb-2 font-medium">Table of Contents</h3>
              {isLoading ? <div className="manual-skeleton h-24" /> : null}
              {!isLoading && !(payload?.sections || []).length ? <p className="text-xs text-slate-500">No headings found.</p> : null}
              <div className="max-h-[70vh] space-y-1 overflow-auto text-sm">
                {(payload?.sections || []).map((s) => (
                  <a key={s.id} href={`#${s.anchor_slug}`} className={`block rounded px-2 py-1 ${activeSection === s.anchor_slug ? "bg-slate-100 font-medium" : ""}`} style={{ paddingLeft: `${s.level * 10}px` }}>{s.heading}</a>
                ))}
              </div>
            </aside>
          ) : null}

          <section className="manual-reader-viewer min-h-0 overflow-hidden">
            {isLoading ? <div className="manual-skeleton h-full" /> : noContent ? <div className="manual-empty">No pages/sections available. Upload or reprocess revision.</div> : viewer}
          </section>

          {inspectorOpen ? (
            <aside className="manual-reader-aside p-3 min-h-0 overflow-auto space-y-3">
              <div className="flex gap-1 rounded border p-1 text-xs">
                <button className={`flex-1 rounded px-2 py-1 ${inspectorTab === "compliance" ? "bg-slate-100" : ""}`} onClick={() => setInspectorTab("compliance")}>Revision</button>
                <button className={`flex-1 rounded px-2 py-1 ${inspectorTab === "ack" ? "bg-slate-100" : ""}`} onClick={() => setInspectorTab("ack")}>Ack</button>
                <button className={`flex-1 rounded px-2 py-1 ${inspectorTab === "export" ? "bg-slate-100" : ""}`} onClick={() => setInspectorTab("export")}>Export</button>
              </div>

              {inspectorTab === "compliance" ? (
                <div className="rounded border p-2 text-sm">
                  <div>Changed sections: {diffSummary.changed_sections || 0}</div>
                  <div>Changed blocks: {diffSummary.changed_blocks || 0}</div>
                  <div>Added: {diffSummary.added || 0} · Removed: {diffSummary.removed || 0}</div>
                </div>
              ) : null}

              {inspectorTab === "ack" ? (
                <div className="space-y-2 rounded border p-2 text-sm">
                  <h4 className="font-medium">Acknowledgement</h4>
                  <p className="text-xs">I acknowledge receipt and review of this revision.</p>
                  <textarea className="w-full rounded border p-2 text-xs" rows={3} value={ackComment} onChange={(e) => setAckComment(e.target.value)} placeholder="Optional comment" />
                  <button className="rounded bg-slate-900 px-3 py-1 text-xs text-white" onClick={() => tenant && manualId && revId && acknowledgeRevision(tenant, manualId, revId, `I acknowledge receipt and review of this revision.${ackComment ? ` Note: ${ackComment}` : ""}`)}>Acknowledge Revision</button>
                </div>
              ) : null}

              {inspectorTab === "export" ? (
                <div className="space-y-2 rounded border p-2 text-sm">
                  <h4 className="font-medium">Print / Export</h4>
                  <label className="manual-switch-row"><span>Uncontrolled watermark</span><button className={`manual-switch ${watermarkOn ? "on" : "off"}`} disabled={controlled || !canDisableWatermark} onClick={() => setWatermarkOn((v) => !v)} type="button" /></label>
                  <label className="manual-switch-row"><span>Controlled hard copy</span><button className={`manual-switch ${controlled ? "on" : "off"}`} disabled={!canDisableWatermark} onClick={() => { const next = !controlled; setControlled(next); if (next) setWatermarkOn(false); }} type="button" /></label>
                  {!canDisableWatermark ? <p className="text-[11px] text-amber-700">Only authorized roles can disable watermark or issue controlled copies.</p> : null}
                  {controlled ? (
                    <div className="space-y-1">
                      <input className="w-full rounded border px-2 py-1 text-xs" placeholder="Controlled Copy No" />
                      <input className="w-full rounded border px-2 py-1 text-xs" placeholder="Recipient" />
                      <input className="w-full rounded border px-2 py-1 text-xs" placeholder="Purpose" />
                    </div>
                  ) : null}
                  <button className="rounded bg-sky-700 px-3 py-1 text-xs text-white" onClick={() => tenant && manualId && revId && createRevisionExport(tenant, manualId, revId, { controlled_bool: controlled, watermark_uncontrolled_bool: watermarkOn, version_label: `rev-${revId}` })}>Generate PDF Artifact</button>
                </div>
              ) : null}
            </aside>
          ) : null}
        </div>
      </ManualsReaderShell>
    </TenantBrandingProvider>
  );
}
