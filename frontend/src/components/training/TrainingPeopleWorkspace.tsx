import React, { useDeferredValue, useState } from "react";
import { AlertTriangle, ChevronLeft, ChevronRight, FileUp, PanelRightOpen, RefreshCw, Search, UserRound, UsersRound } from "lucide-react";
import { useQuery } from "@tanstack/react-query";
import { useNavigate, useParams } from "react-router-dom";

import { buildCanonicalRoute } from "../../app/canonicalRoutes";
import Drawer from "../shared/Drawer";
import { getTrainingSourceHealth, listPeopleCompliance } from "../../services/trainingOperating";
import type { PersonComplianceRow } from "../../types/trainingOperating";

type Props = { canManage: boolean; onOpenImport: () => void };

const PAGE_SIZE = 50;

const TrainingPeopleWorkspace: React.FC<Props> = ({ canManage, onOpenImport }) => {
  const navigate = useNavigate();
  const { amoCode = "UNKNOWN" } = useParams<{ amoCode?: string }>();
  const [search, setSearch] = useState("");
  const [active, setActive] = useState<"active" | "inactive" | "all">("active");
  const [offset, setOffset] = useState(0);
  const [selected, setSelected] = useState<PersonComplianceRow | null>(null);
  const deferredSearch = useDeferredValue(search.trim());
  const people = useQuery({
    queryKey: ["training", "people-compliance", deferredSearch, active, offset],
    queryFn: () => listPeopleCompliance({ search: deferredSearch, active: active === "all" ? undefined : active === "active", limit: PAGE_SIZE, offset }),
    placeholderData: (previous) => previous,
  });
  const health = useQuery({ queryKey: ["training", "source-health"], queryFn: getTrainingSourceHealth, staleTime: 30_000 });

  const openRecord = (row: PersonComplianceRow) => navigate(buildCanonicalRoute.qmsTrainingPerson({ amoCode, userId: row.id }));
  const openQuickView = (event: React.MouseEvent, row: PersonComplianceRow) => {
    event.stopPropagation();
    setSelected(row);
  };
  const totals = people.data?.filtered_totals || {};

  return <div className="tos-stack training-route-workspace">
    <section className="tos-card tos-route-commandbar">
      <div><p className="tos-kicker">Canonical workforce register</p><h2>People compliance</h2><p>Server-calculated obligations with the controlling requirement, completion and expiry attached to every row.</p></div>
      <button disabled={!canManage} onClick={onOpenImport}><FileUp size={16} /> Import people / history</button>
      <button aria-label="Refresh people" onClick={() => { void people.refetch(); void health.refetch(); }}><RefreshCw size={16} /></button>
    </section>

    {health.isError ? <div className="tos-banner tos-banner--error"><AlertTriangle size={17} />Source health unavailable. Compliance totals are not being presented as zero.</div> : null}
    {health.data && health.data.overall_status !== "HEALTHY" ? <section className="tos-card tos-source-health" aria-label="Source health">
      <div><AlertTriangle size={18} /><strong>Partial source availability</strong><span>Unavailable dependencies are shown as Unknown.</span></div>
      {health.data.sources.map((source) => <span key={source.source} className={`tos-source-chip is-${source.status.toLowerCase()}`} title={source.detail}>{source.source}: {source.status}</span>)}
    </section> : null}

    <section className="tos-metric-strip" aria-label="Filtered compliance totals">
      <article><span>People</span><strong>{people.isError ? "Unknown" : totals.people ?? "—"}</strong></article>
      <article><span>Overdue</span><strong>{people.isError ? "Unknown" : totals.overdue ?? "—"}</strong></article>
      <article><span>Due soon</span><strong>{people.isError ? "Unknown" : totals.due_soon ?? "—"}</strong></article>
      <article><span>Never completed</span><strong>{people.isError ? "Unknown" : totals.never_completed ?? "—"}</strong></article>
    </section>

    <section className="tos-card tos-register-card">
      <div className="tos-register-toolbar">
        <label className="tos-search-field"><Search size={17} /><span className="sr-only">Search people</span><input value={search} onChange={(event) => { setSearch(event.target.value); setOffset(0); }} placeholder="Search name, staff code, email or position" /></label>
        <label><span className="sr-only">Employment state</span><select value={active} onChange={(event) => { setActive(event.target.value as typeof active); setOffset(0); }}><option value="active">Active people</option><option value="inactive">Inactive people</option><option value="all">All people</option></select></label>
      </div>

      {people.isLoading ? <div className="tos-loading">Loading the server register…</div> : null}
      {people.isError ? <div className="tos-empty"><AlertTriangle size={24} /><strong>People source unavailable</strong><span>No false-zero register has been rendered.</span><button onClick={() => void people.refetch()}>Retry source</button></div> : null}
      {people.data && !people.data.items.length ? <div className="tos-empty"><UsersRound size={24} /><strong>No matching people</strong><span>Change the filters or import the canonical people and training history.</span>{canManage ? <button onClick={onOpenImport}><FileUp size={16} /> Import data</button> : null}</div> : null}

      {people.data?.items.length ? <>
        <div className="tos-table-wrap tos-desktop-register"><table className="tos-table tos-table--interactive"><thead><tr><th>Person</th><th>Position</th><th>Outstanding</th><th>Overdue</th><th>Due soon</th><th>Never</th><th>Next due</th><th>Next action</th></tr></thead><tbody>{people.data.items.map((row) => <tr key={row.id} tabIndex={0} title={`Open ${row.full_name}'s full training record`} onClick={() => openRecord(row)} onKeyDown={(event) => { if (event.key === "Enter") openRecord(row); }}><td><strong>{row.full_name}</strong><small>{row.staff_code || "No staff code"} · {row.email || "No email"}</small></td><td>{row.position_title || "Not assigned"}<small>{row.department || "No department"}</small></td><td>{row.outstanding}</td><td>{row.overdue}</td><td>{row.due_soon}</td><td>{row.never_completed}</td><td>{row.next_due || "—"}</td><td><div className="tos-actions"><span className={`tos-pill is-${row.status.toLowerCase()}`}>{row.status.replaceAll("_", " ")}</span><button type="button" className="tos-icon-button" title={`Quick compliance view for ${row.full_name}`} aria-label={`Quick compliance view for ${row.full_name}`} onClick={(event) => openQuickView(event, row)}><PanelRightOpen size={16} /></button></div><small>{row.next_action}</small></td></tr>)}</tbody></table></div>
        <div className="tos-mobile-register">{people.data.items.map((row) => <button className="tos-person-card" key={row.id} onClick={() => openRecord(row)}><span><UserRound size={18} /><strong>{row.full_name}</strong></span><small>{row.staff_code || "No staff code"} · {row.position_title || "Position not assigned"}</small><span><b>{row.outstanding}</b> outstanding · <b>{row.overdue}</b> overdue · <b>{row.due_soon}</b> due soon</span><em>Open full training record · {row.next_action}</em></button>)}</div>
        <footer className="tos-pagination"><span>{people.data.total ? `${offset + 1}–${Math.min(offset + PAGE_SIZE, people.data.total)} of ${people.data.total}` : "0 people"}</span><div><button aria-label="Previous page" disabled={offset === 0} onClick={() => setOffset(Math.max(0, offset - PAGE_SIZE))}><ChevronLeft size={17} /></button><button aria-label="Next page" disabled={!people.data.has_more} onClick={() => setOffset(offset + PAGE_SIZE)}><ChevronRight size={17} /></button></div></footer>
      </> : null}
    </section>
    <Drawer title={selected ? `${selected.full_name} · training dossier` : "Training dossier"} isOpen={Boolean(selected)} onClose={() => setSelected(null)} panelClassName="training-form-drawer"><div className="tos-drawer-form">{selected ? <><section className="tos-metric-strip"><article><span>Outstanding</span><strong>{selected.outstanding}</strong></article><article><span>Overdue</span><strong>{selected.overdue}</strong></article><article><span>Due soon</span><strong>{selected.due_soon}</strong></article><article><span>Never</span><strong>{selected.never_completed}</strong></article></section><div className="tos-inline-proof"><UserRound size={17} /><span>{selected.staff_code || "No staff code"} · {selected.position_title || "No position"}</span><strong>{selected.next_action}</strong></div><div className="tos-list">{(selected.provenance.obligations || []).map((item, index) => <div key={String(item.course_id || index)}><div><strong>{String(item.course_code || "COURSE")} · {String(item.course_name || "Unnamed course")}</strong><small>Completion {String(item.completion_date || "never")} · expiry {String(item.expiry_date || "not set")}</small><small>Source: {JSON.stringify(item.requirements || [])}</small></div><span className="tos-pill tos-pill--ok">{item.record_id ? "RECORDED" : "MISSING"}</span></div>)}</div></> : null}</div></Drawer>
  </div>;
};

export default TrainingPeopleWorkspace;
