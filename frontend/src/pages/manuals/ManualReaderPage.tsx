import { useEffect, useMemo, useRef, useState } from "react";
import { Upload, RefreshCcw, ScanLine, FileText, Loader2 } from "lucide-react";
import { useVirtualizer } from "@tanstack/react-virtual";
import {
  acknowledgeRevision,
  createRevisionExport,
  generateOutline,
  getProcessingStatus,
  getRevisionDiff,
  getRevisionRead,
  getRevisionWorkflow,
  runOcr,
  runProcessor,
  type ManualReadPayload,
  type ManualProcessingStatus,
} from "../../services/manuals";
import { authHeaders } from "../../services/auth";
import { getApiBaseUrl } from "../../services/config";
import { useManualRouteContext } from "./context";
import "./manualReader.css";
import { ManualsReaderShell, TenantBrandingProvider } from "../../packages/manuals-reader";

function chunk<T>(arr: T[], size: number): T[][] {
  const out: T[][] = [];
  for (let i = 0; i < arr.length; i += size) out.push(arr.slice(i, i + size));
  return out;
}

export default function ManualReaderPage() {
  const { tenant, manualId, revId, amoCode } = useManualRouteContext();
  const [payload, setPayload] = useState<ManualReadPayload | null>(null);
  const [workflowStatus, setWorkflowStatus] = useState("Loading");
  const [diffSummary, setDiffSummary] = useState<Record<string, number>>({});
  const [search, setSearch] = useState("");
  const [activeSection, setActiveSection] = useState("");
  const [layout, setLayout] = useState<"continuous" | "paged-1" | "paged-2" | "paged-3">((localStorage.getItem("manuals.layout") as any) || "continuous");
  const [zoom, setZoom] = useState(Number(localStorage.getItem("manuals.zoom") || "100"));
  const [tocOpen, setTocOpen] = useState(true);
  const [inspectorOpen, setInspectorOpen] = useState(true);
  const [tab, setTab] = useState<"revision" | "ack" | "export">("revision");
  const [ackChecked, setAckChecked] = useState(false);
  const [ackComment, setAckComment] = useState("");
  const [controlled, setControlled] = useState(false);
  const [watermarkOn, setWatermarkOn] = useState(true);
  const [processing, setProcessing] = useState<ManualProcessingStatus | null>(null);
  const [busy, setBusy] = useState<"processor" | "ocr" | "outline" | null>(null);
  const [uploadName, setUploadName] = useState("");
  const [integrityCompromised, setIntegrityCompromised] = useState(false);

  const sectionRefs = useRef<Record<string, HTMLElement | null>>({});
  const pagedParentRef = useRef<HTMLDivElement | null>(null);

  const refresh = () => {
    if (!tenant || !manualId || !revId) return;
    getRevisionRead(tenant, manualId, revId).then(setPayload).catch(() => setPayload(null));
    getRevisionWorkflow(tenant, manualId, revId).then((v) => setWorkflowStatus(v.status || "Metadata incomplete")).catch(() => setWorkflowStatus("Metadata incomplete"));
    getRevisionDiff(tenant, manualId, revId).then((v) => setDiffSummary(v.summary_json || {})).catch(() => setDiffSummary({}));
    getProcessingStatus(tenant, manualId, revId).then(setProcessing).catch(() => setProcessing(null));
  };

  useEffect(() => { refresh(); }, [tenant, manualId, revId]);

  useEffect(() => {
    if (!manualId || !revId) {
      setIntegrityCompromised(false);
      return;
    }

    let alive = true;
    const controller = new AbortController();

    (async () => {
      try {
        const response = await fetch(`${getApiBaseUrl()}/quality/qms/documents/${manualId}/revisions/${revId}/open`, {
          method: "GET",
          headers: {
            ...authHeaders(),
            Range: "bytes=0-0",
          },
          signal: controller.signal,
        });
        const integrity = (response.headers.get("X-Document-Integrity") || "").toLowerCase();
        if (alive) setIntegrityCompromised(integrity === "compromised");
      } catch {
        if (alive) setIntegrityCompromised(false);
      } finally {
        controller.abort();
      }
    })();

    return () => {
      alive = false;
      controller.abort();
    };
  }, [manualId, revId]);

  useEffect(() => { localStorage.setItem("manuals.layout", layout); localStorage.setItem("manuals.zoom", String(zoom)); }, [layout, zoom]);

  useEffect(() => {
    const onKey = (e: KeyboardEvent) => {
      if ((e.metaKey || e.ctrlKey) && e.key.toLowerCase() === "k") { e.preventDefault(); document.getElementById("manual-reader-search")?.focus(); }
      if (e.key === "[") setTocOpen((v) => !v);
      if (e.key === "]") setInspectorOpen((v) => !v);
    };
    window.addEventListener("keydown", onKey);
    return () => window.removeEventListener("keydown", onKey);
  }, []);

  useEffect(() => {
    const obs = new IntersectionObserver((entries) => {
      const top = entries.find((e) => e.isIntersecting);
      if (top?.target?.id) setActiveSection(top.target.id);
    }, { rootMargin: "-10% 0px -75% 0px", threshold: [0.2] });
    Object.values(sectionRefs.current).forEach((el) => el && obs.observe(el));
    return () => obs.disconnect();
  }, [payload?.sections]);

  useEffect(() => {
    const source = new EventSource(new URL("/api/events", window.location.origin));
    source.onmessage = (event) => {
      try {
        const v = JSON.parse(event.data || "{}");
        const type = String(v.entity_type || v.entityType || "");
        const entityId = String(v.entity_id || v.entityId || "");
        if (type.includes("manual") || entityId === manualId || entityId === revId) refresh();
      } catch {}
    };
    source.addEventListener("reset", () => refresh());
    return () => source.close();
  }, [manualId, revId]);

  const blocksBySection = useMemo(() => {
    const grouped: Record<string, ManualReadPayload["blocks"]> = {};
    (payload?.blocks || []).forEach((b) => ((grouped[b.section_id] = grouped[b.section_id] || []).push(b)));
    return grouped;
  }, [payload?.blocks]);

  const filteredSections = useMemo(
    () => (payload?.sections || []).filter((s) => s.heading.toLowerCase().includes(search.toLowerCase()) || (blocksBySection[s.id] || []).some((b) => b.text.toLowerCase().includes(search.toLowerCase()))),
    [payload?.sections, blocksBySection, search],
  );

  const pages = useMemo(() => chunk(filteredSections.map((section) => ({ section, blocks: blocksBySection[section.id] || [] })), 1), [filteredSections, blocksBySection]);
  const columns = layout === "paged-3" ? 3 : layout === "paged-2" ? 2 : 1;
  const rows = useMemo(() => chunk(pages, columns), [pages, columns]);
  const virtualizer = useVirtualizer({ count: rows.length, getScrollElement: () => pagedParentRef.current, estimateSize: () => 930, overscan: 3 });

  const missingMetaFields = [!revId && "revision id", !workflowStatus && "workflow status"].filter(Boolean) as string[];
  const noContent = !filteredSections.length;

  const run = async (kind: "processor" | "ocr" | "outline") => {
    if (!tenant || !manualId || !revId) return;
    setBusy(kind);
    try {
      if (kind === "processor") await runProcessor(tenant, manualId, revId);
      if (kind === "ocr") await runOcr(tenant, manualId, revId);
      if (kind === "outline") await generateOutline(tenant, manualId, revId);
      refresh();
    } finally {
      setBusy(null);
    }
  };

  const viewer = layout === "continuous" ? (
    <div className="manual-reader-pane">
      {filteredSections.map((s) => (
        <article key={s.id} id={s.anchor_slug} ref={(el) => { sectionRefs.current[s.anchor_slug] = el; }} className="manual-reader-section">
          <h2>{s.heading}</h2>
          {(blocksBySection[s.id] || []).map((b, i) => <div key={`${s.id}-${i}`} className="manual-reader-content" dangerouslySetInnerHTML={{ __html: b.html }} />)}
        </article>
      ))}
    </div>
  ) : (
    <div ref={pagedParentRef} className="manual-reader-pane overflow-auto">
      <div style={{ height: `${virtualizer.getTotalSize()}px`, position: "relative" }}>
        {virtualizer.getVirtualItems().map((row) => (
          <div key={row.key} style={{ position: "absolute", top: 0, left: 0, width: "100%", transform: `translateY(${row.start}px)` }}>
            <div className="manual-paged-grid" style={{ gridTemplateColumns: `repeat(${columns}, minmax(0,1fr))` }}>
              {(rows[row.index] || []).map((page, idx) => (
                <section key={`p-${row.index}-${idx}`} className="manual-page">
                  {(page || []).map((entry) => (
                    <div key={entry.section.id} className="manual-reader-content"><h3>{entry.section.heading}</h3>{entry.blocks.map((b, i) => <div key={`${entry.section.id}-${i}`} dangerouslySetInnerHTML={{ __html: b.html }} />)}</div>
                  ))}
                </section>
              ))}
            </div>
          </div>
        ))}
      </div>
    </div>
  );

  const fallbackPath = amoCode ? `/maintenance/${amoCode}/manuals` : `/t/${tenant || ""}/manuals`;

  return (
    <TenantBrandingProvider tenantSlug={tenant || "default"}>
      <ManualsReaderShell
        tenantSlug={tenant || "default"}
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
        onLayoutChange={(next) => setLayout(next)}
        onZoomIn={() => setZoom((z) => Math.min(220, z + 10))}
        onZoomOut={() => setZoom((z) => Math.max(60, z - 10))}
        onZoomReset={() => setZoom(100)}
      >
        {integrityCompromised ? (
          <div className="manual-card" style={{ borderColor: "var(--danger, #d9534f)", background: "rgba(217, 83, 79, 0.12)", marginBottom: 12 }}>
            <strong>CRITICAL: DOCUMENT INTEGRITY COMPROMISED</strong>
            <p>This revision hash does not match the immutable record. Stop use and notify Quality Management immediately.</p>
          </div>
        ) : null}
        <div className="manual-reader-workspace">
          {tocOpen ? (
            <aside className="manual-reader-toc">
              <div className="manual-panel-title">TOC</div>
              {!filteredSections.length ? (
                <div className="manual-panel-empty">
                  <p>No headings found.</p>
                  <button className="manual-reader-icon-btn" onClick={() => run("outline")} disabled={busy === "outline"}>{busy === "outline" ? <Loader2 size={14} className="animate-spin" /> : "Generate outline"}</button>
                </div>
              ) : (
                filteredSections.map((s) => <a key={s.id} href={`#${s.anchor_slug}`} className={`manual-toc-item ${activeSection === s.anchor_slug ? "active" : ""}`} style={{ paddingLeft: `${s.level * 12}px` }}>{s.heading}</a>)
              )}
            </aside>
          ) : null}

          <section className="manual-reader-viewer" style={{ transform: `scale(${zoom / 100})`, transformOrigin: "top center" }}>
            {noContent ? (
              <div className="manual-empty-hub">
                <h2>This revision has no rendered content yet</h2>
                <p>Upload a source document, run processing, or use OCR for scanned PDFs.</p>
                <div className="manual-empty-actions">
                  <label className="manual-reader-icon-btn"><Upload size={14} /> Upload Document<input type="file" accept=".pdf,.docx" hidden onChange={(e) => setUploadName(e.target.files?.[0]?.name || "")} /></label>
                  <button className="manual-reader-icon-btn" onClick={() => run("processor")} disabled={busy !== null}>{busy === "processor" ? <Loader2 size={14} className="animate-spin" /> : <RefreshCcw size={14} />} Run Processor</button>
                  <button className="manual-reader-icon-btn" onClick={() => run("ocr")} disabled={busy !== null}>{busy === "ocr" ? <Loader2 size={14} className="animate-spin" /> : <ScanLine size={14} />} Run OCR</button>
                  <a className="manual-reader-icon-btn" href="#processor-logs"><FileText size={14} /> View logs</a>
                </div>
                {uploadName ? <p className="manual-upload-caption">Selected: {uploadName}</p> : null}
                {processing ? <p className="manual-upload-caption">Status: {processing.stage} · Last run by {processing.actor_id || "system"}</p> : null}
              </div>
            ) : viewer}
          </section>

          {inspectorOpen ? (
            <aside className="manual-reader-aside">
              <div className="manual-tabs">
                {(["revision", "ack", "export"] as const).map((t) => <button key={t} className={`manual-tab ${tab === t ? "active" : ""}`} onClick={() => setTab(t)}>{t.toUpperCase()}</button>)}
              </div>

              {tab === "revision" ? <div className="manual-card"><p>Changed sections: {diffSummary.changed_sections || 0}</p><p>Changed blocks: {diffSummary.changed_blocks || 0}</p><p>Added {diffSummary.added || 0} · Removed {diffSummary.removed || 0}</p></div> : null}

              {tab === "ack" ? (
                <div className="manual-card">
                  <p>I acknowledge receipt and review of this revision.</p>
                  <label className="manual-check"><input type="checkbox" checked={ackChecked} onChange={(e) => setAckChecked(e.target.checked)} /> I acknowledge the transmittal requirement.</label>
                  <textarea className="manual-textarea" rows={3} placeholder="Optional comment" value={ackComment} onChange={(e) => setAckComment(e.target.value)} />
                  <button className="manual-reader-icon-btn" disabled={!ackChecked} onClick={() => tenant && manualId && revId && acknowledgeRevision(tenant, manualId, revId, `I acknowledge receipt and review.${ackComment ? ` Note: ${ackComment}` : ""}`)}>Acknowledge</button>
                </div>
              ) : null}

              {tab === "export" ? (
                <div className="manual-card">
                  <label className="manual-switch-row"><span>UNCONTROLLED watermark</span><input type="checkbox" checked={watermarkOn} disabled={controlled} onChange={(e) => setWatermarkOn(e.target.checked)} /></label>
                  <label className="manual-switch-row"><span>Controlled hard copy</span><input type="checkbox" checked={controlled} onChange={(e) => { const next = e.target.checked; setControlled(next); if (next) setWatermarkOn(false); }} /></label>
                  {controlled ? <><input className="manual-input" placeholder="Manual Copy No" /><input className="manual-input" placeholder="Copy Holder" /><input className="manual-input" placeholder="Purpose" /></> : null}
                  <button className="manual-reader-icon-btn" onClick={() => tenant && manualId && revId && createRevisionExport(tenant, manualId, revId, { controlled_bool: controlled, watermark_uncontrolled_bool: watermarkOn, version_label: `rev-${revId}` })}>Generate PDF Artifact</button>
                </div>
              ) : null}
            </aside>
          ) : null}
        </div>
      </ManualsReaderShell>
    </TenantBrandingProvider>
  );
}
