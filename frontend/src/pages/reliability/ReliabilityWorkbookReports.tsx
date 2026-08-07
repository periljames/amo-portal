import React, { useCallback, useEffect, useMemo, useState } from "react";

import {
  createReportLayout,
  listReportLayouts,
  listReportSnapshots,
  readReportHtml,
  renderWorkbookReport,
  seedDefaultReportLayouts,
} from "./reliabilityWorkbookParityApi";
import {
  activeReportSections,
  defaultReportSections,
  downloadText,
  moveSection,
} from "./reliabilityWorkbookParityModel";
import type {
  ReportLayout,
  ReportSection,
  ReportSnapshot,
} from "./reliabilityWorkbookParityTypes";

function monthsAgo(months: number): string {
  const value = new Date();
  value.setMonth(value.getMonth() - months);
  return value.toISOString().slice(0, 10);
}
function today(): string { return new Date().toISOString().slice(0, 10); }

export function ReliabilityWorkbookReports(): React.ReactElement {
  const [layouts, setLayouts] = useState<ReportLayout[]>([]);
  const [snapshots, setSnapshots] = useState<ReportSnapshot[]>([]);
  const [selectedLayoutId, setSelectedLayoutId] = useState<number | null>(null);
  const [periodStart, setPeriodStart] = useState(monthsAgo(1));
  const [periodEnd, setPeriodEnd] = useState(today());
  const [aircraftText, setAircraftText] = useState("");
  const [previewHtml, setPreviewHtml] = useState("");
  const [previewSnapshot, setPreviewSnapshot] = useState<ReportSnapshot | null>(null);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [notice, setNotice] = useState<string | null>(null);
  const [layoutDraft, setLayoutDraft] = useState({
    code: "OPERATOR-RP",
    name: "Operator Reliability Programme Report",
    aircraftFamily: "OPERATOR",
    orientation: "portrait",
    paperSize: "A4",
  });
  const [sections, setSections] = useState<ReportSection[]>(() => defaultReportSections());

  const load = useCallback(async () => {
    setError(null);
    try {
      const [layoutRows, snapshotRows] = await Promise.all([listReportLayouts(), listReportSnapshots(100)]);
      setLayouts(layoutRows);
      setSnapshots(snapshotRows);
      setSelectedLayoutId((current) => current || layoutRows.find((row) => row.active)?.id || layoutRows[0]?.id || null);
    } catch (caught: unknown) {
      setError(caught instanceof Error ? caught.message : "Reliability report configuration could not be loaded.");
    }
  }, []);
  useEffect(() => { void load(); }, [load]);

  const activeLayouts = useMemo(() => layouts.filter((layout) => layout.active), [layouts]);
  const selectedLayout = layouts.find((layout) => layout.id === selectedLayoutId) || null;

  const seed = async () => {
    setLoading(true);
    setError(null);
    try {
      const rows = await seedDefaultReportLayouts();
      setNotice(`${rows.length} C208B, DHC8 and operator layouts are available.`);
      await load();
    } catch (caught: unknown) {
      setError(caught instanceof Error ? caught.message : "Default report layouts could not be seeded.");
    } finally { setLoading(false); }
  };

  const saveLayout = async (event: React.FormEvent) => {
    event.preventDefault();
    const included = activeReportSections(sections);
    if (!included.length) { setError("Include at least one report section."); return; }
    setLoading(true);
    setError(null);
    try {
      const created = await createReportLayout({
        code: layoutDraft.code.trim().toUpperCase().replaceAll(" ", "-"),
        name: layoutDraft.name.trim(),
        aircraft_family: layoutDraft.aircraftFamily.trim().toUpperCase(),
        sections: included,
        page_settings: { paper_size: layoutDraft.paperSize, orientation: layoutDraft.orientation, margins_mm: 12 },
      });
      setNotice(`${created.name} revision ${created.revision} is active.`);
      await load();
      setSelectedLayoutId(created.id);
    } catch (caught: unknown) {
      setError(caught instanceof Error ? caught.message : "The report layout could not be saved.");
    } finally { setLoading(false); }
  };

  const render = async (event: React.FormEvent) => {
    event.preventDefault();
    if (!selectedLayoutId) { setError("Select a report layout."); return; }
    setLoading(true);
    setError(null);
    try {
      const snapshot = await renderWorkbookReport({
        layout_id: selectedLayoutId,
        period_start: periodStart,
        period_end: periodEnd,
        aircraft: aircraftText.split(",").map((item) => item.trim()).filter(Boolean),
      });
      const html = await readReportHtml(snapshot.id);
      setPreviewSnapshot({ ...snapshot, layout_name: selectedLayout?.name });
      setPreviewHtml(html);
      setNotice(`Report snapshot ${snapshot.id} was retained with SHA-256 ${snapshot.sha256_hash.slice(0, 12)}…`);
      await load();
    } catch (caught: unknown) {
      setError(caught instanceof Error ? caught.message : "The controlled report could not be rendered.");
    } finally { setLoading(false); }
  };

  const openSnapshot = async (snapshot: ReportSnapshot) => {
    setLoading(true);
    setError(null);
    try {
      setPreviewHtml(await readReportHtml(snapshot.id));
      setPreviewSnapshot(snapshot);
    } catch (caught: unknown) {
      setError(caught instanceof Error ? caught.message : "The retained report could not be opened.");
    } finally { setLoading(false); }
  };

  const downloadSnapshot = async (snapshot: ReportSnapshot) => {
    try {
      const html = previewSnapshot?.id === snapshot.id && previewHtml ? previewHtml : await readReportHtml(snapshot.id);
      downloadText(`reliability-${snapshot.layout_code}-${snapshot.period_start}-${snapshot.period_end}.html`, html, "text/html;charset=utf-8");
    } catch (caught: unknown) {
      setError(caught instanceof Error ? caught.message : "The retained report could not be downloaded.");
    }
  };

  return <div className="rel-wp__reports-grid">
    <section className="rel-wp__panel">
      <div className="rel-wp__section-heading"><div><p className="rel-wp__eyebrow">Configurable programme output</p><h2>Report layouts</h2></div><button type="button" className="btn btn-primary" onClick={() => void seed()} disabled={loading}>Seed defaults</button></div>
      {notice && <div className="rel-wp__notice" role="status">{notice}</div>}
      {error && <div className="rel-wp__error" role="alert">{error}</div>}
      <div className="rel-wp__layout-cards">{activeLayouts.map((layout) => <button type="button" key={layout.id} className={selectedLayoutId === layout.id ? "is-active" : ""} onClick={() => setSelectedLayoutId(layout.id)}><span>{layout.code}</span><strong>{layout.name}</strong><small>{layout.aircraft_family} · Rev {layout.revision} · {layout.sections.length} sections</small></button>)}</div>
    </section>

    <section className="rel-wp__panel">
      <div className="rel-wp__section-heading"><div><p className="rel-wp__eyebrow">Controlled generation</p><h2>Render retained report</h2></div>{selectedLayout && <span>{selectedLayout.code}</span>}</div>
      <form className="rel-wp__form" onSubmit={render}>
        <div className="rel-wp__form-grid">
          <label>Layout<select required value={selectedLayoutId ?? ""} onChange={(event) => setSelectedLayoutId(event.target.value ? Number(event.target.value) : null)}><option value="">Select…</option>{activeLayouts.map((layout) => <option key={layout.id} value={layout.id}>{layout.name} — Rev {layout.revision}</option>)}</select></label>
          <label>Period start<input type="date" required value={periodStart} onChange={(event) => setPeriodStart(event.target.value)} /></label>
          <label>Period end<input type="date" required value={periodEnd} onChange={(event) => setPeriodEnd(event.target.value)} /></label>
          <label className="rel-wp__span-2">Aircraft filter<input value={aircraftText} onChange={(event) => setAircraftText(event.target.value)} placeholder="Comma-separated; blank includes the fleet" /></label>
        </div>
        <div className="rel-wp__form-actions"><button type="submit" className="btn btn-primary" disabled={loading}>{loading ? "Rendering…" : "Render and retain snapshot"}</button></div>
      </form>
    </section>

    <section className="rel-wp__panel rel-wp__layout-builder">
      <div className="rel-wp__section-heading"><div><p className="rel-wp__eyebrow">Operator-specific programme</p><h2>Layout builder</h2></div><span>Versioned on save</span></div>
      <form className="rel-wp__form" onSubmit={saveLayout}>
        <div className="rel-wp__form-grid">
          <label>Layout code<input required value={layoutDraft.code} onChange={(event) => setLayoutDraft({ ...layoutDraft, code: event.target.value })} /></label>
          <label>Layout name<input required value={layoutDraft.name} onChange={(event) => setLayoutDraft({ ...layoutDraft, name: event.target.value })} /></label>
          <label>Aircraft family<input required value={layoutDraft.aircraftFamily} onChange={(event) => setLayoutDraft({ ...layoutDraft, aircraftFamily: event.target.value })} /></label>
          <label>Paper size<select value={layoutDraft.paperSize} onChange={(event) => setLayoutDraft({ ...layoutDraft, paperSize: event.target.value })}><option>A4</option><option>LETTER</option></select></label>
          <label>Orientation<select value={layoutDraft.orientation} onChange={(event) => setLayoutDraft({ ...layoutDraft, orientation: event.target.value })}><option value="portrait">Portrait</option><option value="landscape">Landscape</option></select></label>
        </div>
        <div className="rel-wp__section-builder">{sections.map((section, index) => <div key={section.code} className={section.include === false ? "is-disabled" : ""}>
          <label className="rel-wp__checkbox"><input type="checkbox" checked={section.include !== false} onChange={(event) => setSections((current) => current.map((item, itemIndex) => itemIndex === index ? { ...item, include: event.target.checked } : item))} />Include</label>
          <span>{section.kind.replaceAll("_", " ")}</span>
          <input aria-label={`${section.code} section title`} value={section.title} onChange={(event) => setSections((current) => current.map((item, itemIndex) => itemIndex === index ? { ...item, title: event.target.value } : item))} />
          <div><button type="button" disabled={index === 0} onClick={() => setSections((current) => moveSection(current, index, -1))}>↑</button><button type="button" disabled={index === sections.length - 1} onClick={() => setSections((current) => moveSection(current, index, 1))}>↓</button></div>
        </div>)}</div>
        <div className="rel-wp__form-actions"><button type="submit" className="btn btn-primary" disabled={loading}>Save new layout revision</button><button type="button" className="btn btn-secondary" onClick={() => setSections(defaultReportSections())}>Reset sections</button></div>
      </form>
    </section>

    <section className="rel-wp__panel rel-wp__report-preview">
      <div className="rel-wp__section-heading"><div><p className="rel-wp__eyebrow">HTML preview</p><h2>{previewSnapshot?.layout_name || previewSnapshot?.layout_code || "No report selected"}</h2></div>{previewSnapshot && <button type="button" className="btn btn-secondary" onClick={() => void downloadSnapshot(previewSnapshot)}>Download HTML</button>}</div>
      {previewHtml ? <iframe title="Reliability report preview" srcDoc={previewHtml} sandbox="allow-same-origin" /> : <div className="rel-wp__preview-empty">Render a report or open a retained snapshot to preview the controlled output.</div>}
    </section>

    <section className="rel-wp__panel rel-wp__span-all">
      <div className="rel-wp__section-heading"><div><p className="rel-wp__eyebrow">Immutable outputs</p><h2>Retained report snapshots</h2></div><button type="button" className="btn btn-secondary" onClick={() => void load()}>Refresh</button></div>
      <div className="rel-wp__table-wrap"><table className="rel-wp__table"><thead><tr><th>Generated</th><th>Layout</th><th>Period</th><th>Aircraft</th><th>SHA-256</th><th>Output</th></tr></thead><tbody>{snapshots.map((snapshot) => <tr key={snapshot.id}><td>{new Date(snapshot.generated_at).toLocaleString()}</td><td>{snapshot.layout_name || snapshot.layout_code}</td><td>{snapshot.period_start} – {snapshot.period_end}</td><td>{snapshot.aircraft?.join(", ") || "Fleet"}</td><td><code>{snapshot.sha256_hash.slice(0, 16)}…</code></td><td><div className="rel-wp__row-actions"><button type="button" onClick={() => void openSnapshot(snapshot)}>Preview</button><button type="button" onClick={() => void downloadSnapshot(snapshot)}>Download</button></div></td></tr>)}{snapshots.length === 0 && <tr><td colSpan={6}>No controlled report snapshots have been generated.</td></tr>}</tbody></table></div>
    </section>
  </div>;
}
