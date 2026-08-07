import React, { useEffect, useMemo, useState } from "react";
import { Link, useLocation, useParams } from "react-router-dom";
import DepartmentLayout from "../../components/Layout/DepartmentLayout";
import { getCachedUser, getContext } from "../../services/auth";
import {
  getContentRevision,
  listContentPacks,
  listContentRevisions,
  listOemCurrentness,
  previewOemWorkbook,
  type ContentPack,
  type ContentRevision,
  type ContentRevisionDetail,
  type ContentTask,
  type OemCurrentness,
  type OemWorkbookPreview,
} from "../../services/oemMpd";
import { canViewFeature, formatCapabilitiesForUi, type ModuleFeature } from "../../utils/roleAccess";
import "../../styles/planning-production-phase1.css";
import "../../styles/oem-mpd-baseline.css";


type PlanningTab = { label: string; path: string; feature: ModuleFeature };

const planningTabs: PlanningTab[] = [
  { label: "Dashboard", path: "dashboard", feature: "planning.dashboard" },
  { label: "Utilisation", path: "utilisation-monitoring", feature: "planning.utilisation-monitoring" },
  { label: "Forecast", path: "forecast-due-list", feature: "planning.forecast-due-list" },
  { label: "AMP", path: "amp", feature: "planning.amp" },
  { label: "Task Library", path: "task-library", feature: "planning.task-library" },
  { label: "AD/SB/EO", path: "ad-sb-eo-control", feature: "planning.ad-sb-eo-control" },
  { label: "Work Packages", path: "work-packages", feature: "planning.work-packages" },
  { label: "Work Orders", path: "work-orders", feature: "planning.work-orders" },
  { label: "Deferments", path: "deferments", feature: "planning.deferments" },
  { label: "NR Review", path: "non-routine-review", feature: "planning.non-routine-review" },
  { label: "Watchlists", path: "watchlists", feature: "planning.watchlists" },
  { label: "Publication Review", path: "publication-review", feature: "planning.publication-review" },
  { label: "Compliance", path: "compliance-actions", feature: "planning.compliance-actions" },
];

function fmtDate(value?: string | null): string {
  if (!value) return "—";
  const date = new Date(`${value}T00:00:00`);
  if (Number.isNaN(date.getTime())) return value;
  return new Intl.DateTimeFormat(undefined, { day: "2-digit", month: "short", year: "numeric" }).format(date);
}

function sourceStatusLabel(status: OemCurrentness["currentness_status"]): string {
  return status.replace(/_/g, " ").toLowerCase().replace(/\b\w/g, (value) => value.toUpperCase());
}

function statusClass(status: string): string {
  const normalized = status.toUpperCase();
  if (normalized === "CURRENT" || normalized === "PUBLISHED") return "badge badge--success";
  if (normalized.includes("REQUIRED") || normalized.includes("CANDIDATE") || normalized.includes("TEMPORARY")) return "badge badge--warning";
  if (normalized === "SUPERSEDED" || normalized === "WITHDRAWN" || normalized === "REJECTED") return "badge badge--muted";
  return "badge badge--info";
}

function intervalText(task: ContentTask): string {
  if (task.raw_interval_text) return task.raw_interval_text;
  const value = task.intervals_json;
  if (value?.schema === "MPD_INTERVAL_V1" && Array.isArray(value.groups)) {
    return value.groups.map((group) => {
      const row = group as { phase?: string; mode?: string; limits?: Array<{ counter?: string; value?: unknown }>; reference?: string };
      if (row.mode === "OPPORTUNITY") return row.reference ? `Opportunity · ${row.reference}` : "Opportunity";
      const limits = (row.limits ?? []).map((limit) => `${String(limit.value ?? "—")} ${limit.counter ?? ""}`.trim());
      const separator = row.mode === "WHICHEVER_FIRST" ? " or " : row.mode === "ALL_DUE" ? " + " : " / ";
      const phase = row.phase && row.phase !== "INTERVAL" ? `${row.phase.replace(/_/g, " ")}: ` : "";
      return `${phase}${limits.join(separator)}`;
    }).join(" · ");
  }
  return JSON.stringify(value);
}

function sourceAuthorityText(task: ContentTask): string {
  if (!task.source_requirements_json.length) return "—";
  return task.source_requirements_json.map((item) => {
    const authority = String(item.authority ?? "Source");
    const taskNumber = item.task_number ? ` ${String(item.task_number)}` : "";
    const classification = item.classification ? ` (${String(item.classification)})` : "";
    return `${authority}${taskNumber}${classification}`;
  }).join(" · ");
}

const OemBaselinePage: React.FC = () => {
  const { amoCode } = useParams();
  const location = useLocation();
  const user = getCachedUser();
  const context = getContext();
  const [series, setSeries] = useState("400");
  const [packs, setPacks] = useState<ContentPack[]>([]);
  const [currentness, setCurrentness] = useState<OemCurrentness[]>([]);
  const [selectedPackId, setSelectedPackId] = useState("");
  const [revisions, setRevisions] = useState<ContentRevision[]>([]);
  const [selectedRevisionId, setSelectedRevisionId] = useState("");
  const [detail, setDetail] = useState<ContentRevisionDetail | null>(null);
  const [search, setSearch] = useState("");
  const [section, setSection] = useState("ALL");
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [preview, setPreview] = useState<OemWorkbookPreview | null>(null);
  const [previewing, setPreviewing] = useState(false);

  const tabs = planningTabs.filter((tab) => canViewFeature(user, tab.feature, context.department));
  const contributor = Boolean((user as { is_superuser?: boolean; is_amo_admin?: boolean } | null)?.is_superuser
    || (user as { is_superuser?: boolean; is_amo_admin?: boolean } | null)?.is_amo_admin);

  useEffect(() => {
    let active = true;
    setLoading(true);
    setError(null);
    Promise.all([
      listContentPacks({ family: "DHC-8", series }),
      listOemCurrentness({ family: "DHC-8", series }),
    ]).then(([packRows, sourceRows]) => {
      if (!active) return;
      setPacks(packRows);
      setCurrentness(sourceRows);
      setSelectedPackId((existing) => packRows.some((row) => row.id === existing) ? existing : (packRows[0]?.id ?? ""));
    }).catch((requestError: unknown) => {
      if (active) setError(requestError instanceof Error ? requestError.message : "OEM baseline could not be loaded.");
    }).finally(() => {
      if (active) setLoading(false);
    });
    return () => { active = false; };
  }, [series]);

  useEffect(() => {
    let active = true;
    setDetail(null);
    if (!selectedPackId) {
      setRevisions([]);
      setSelectedRevisionId("");
      return () => { active = false; };
    }
    listContentRevisions(selectedPackId).then((rows) => {
      if (!active) return;
      setRevisions(rows);
      const published = rows.find((row) => row.status === "PUBLISHED");
      setSelectedRevisionId((existing) => rows.some((row) => row.id === existing) ? existing : (published?.id ?? rows[0]?.id ?? ""));
    }).catch((requestError: unknown) => {
      if (active) setError(requestError instanceof Error ? requestError.message : "Content revisions could not be loaded.");
    });
    return () => { active = false; };
  }, [selectedPackId]);

  useEffect(() => {
    let active = true;
    if (!selectedRevisionId) {
      setDetail(null);
      return () => { active = false; };
    }
    getContentRevision(selectedRevisionId).then((row) => {
      if (active) setDetail(row);
    }).catch((requestError: unknown) => {
      if (active) setError(requestError instanceof Error ? requestError.message : "Content revision could not be loaded.");
    });
    return () => { active = false; };
  }, [selectedRevisionId]);

  const sections = useMemo(() => {
    const values = new Set((detail?.tasks ?? []).map((task) => task.programme_section).filter(Boolean) as string[]);
    return ["ALL", ...Array.from(values).sort()];
  }, [detail]);

  const visibleTasks = useMemo(() => {
    const needle = search.trim().toLowerCase();
    return (detail?.tasks ?? []).filter((task) => {
      if (section !== "ALL" && task.programme_section !== section) return false;
      if (!needle) return true;
      return [
        task.task_code,
        task.title,
        task.ata_chapter,
        task.task_type,
        task.raw_effectivity_text,
        task.task_card_number,
        task.amm_reference,
        task.source_reference,
      ].some((value) => value?.toLowerCase().includes(needle));
    });
  }, [detail, search, section]);

  const selectedPack = packs.find((row) => row.id === selectedPackId) ?? null;
  const selectedRevision = revisions.find((row) => row.id === selectedRevisionId) ?? null;

  async function inspectWorkbook(file: File | null) {
    if (!file) return;
    setPreviewing(true);
    setError(null);
    try {
      setPreview(await previewOemWorkbook(file));
    } catch (requestError) {
      setError(requestError instanceof Error ? requestError.message : "Workbook could not be inspected.");
      setPreview(null);
    } finally {
      setPreviewing(false);
    }
  }

  if (!canViewFeature(user, "planning.task-library", context.department)) {
    return (
      <DepartmentLayout amoCode={amoCode || "UNKNOWN"} activeDepartment="planning">
        <div className="page planning-production-page"><header className="page-header"><h1>OEM Maintenance Baseline</h1></header><section className="card">This source library is not available to the current role assignment.</section></div>
      </DepartmentLayout>
    );
  }

  return (
    <DepartmentLayout amoCode={amoCode || "UNKNOWN"} activeDepartment="planning">
      <div className="page planning-production-page planning-phase-one oem-baseline-page">
        <header className="page-header planning-phase-one__header">
          <div>
            <p className="planning-phase-one__eyebrow">Maintenance Planning · Controlled OEM Data</p>
            <h1>OEM Maintenance Baseline</h1>
            <p className="page-header__subtitle">Revision-controlled MPD/MPM requirements, effectivity, source evidence and technical-data currentness. Tenant AMP deviations are intentionally handled in a separate controlled layer.</p>
            <p className="text-muted planning-phase-one__scope">{formatCapabilitiesForUi(user, context.department).join(" · ") || "Unassigned role scope"}</p>
          </div>
          <div className="oem-baseline__series" aria-label="Dash 8 series selector">
            {["100", "200", "300", "400"].map((value) => <button key={value} className={series === value ? "btn btn-primary" : "btn btn-secondary"} onClick={() => setSeries(value)}>Series {value}</button>)}
          </div>
        </header>

        <nav className="planning-phase-one__tabs" aria-label="Planning pages">
          {tabs.map((tab) => {
            const target = `/maintenance/${amoCode}/planning/${tab.path}`;
            const active = location.pathname === target || location.pathname.startsWith(`${target}/`);
            return <Link key={target} className={active ? "is-active" : ""} to={target}>{tab.label}</Link>;
          })}
        </nav>

        {error ? <div className="alert alert--danger">{error}</div> : null}
        {loading ? <div className="card">Loading controlled OEM baseline…</div> : null}

        <section className="oem-baseline__currentness">
          {currentness.length ? currentness.map((row) => (
            <article className="card oem-source-card" key={row.publication.id}>
              <div className="oem-source-card__top"><div><strong>{row.publication.publication_code}</strong><span>{row.publication.title}</span></div><span className={statusClass(row.currentness_status)}>{sourceStatusLabel(row.currentness_status)}</span></div>
              <dl>
                <div><dt>Series</dt><dd>{row.publication.series || "Family"}</dd></div>
                <div><dt>Current revision</dt><dd>{row.current_revision?.revision_code || "Not established"}</dd></div>
                <div><dt>Effective</dt><dd>{fmtDate(row.current_revision?.effective_date)}</dd></div>
                <div><dt>Active TRs</dt><dd>{row.active_temporary_revisions.length}</dd></div>
              </dl>
              {row.newest_candidate ? <p className="oem-source-card__notice">Candidate revision {row.newest_candidate.revision_code} requires controlled review.</p> : null}
              {row.active_temporary_revisions.length ? <p className="oem-source-card__notice">Baseline includes {row.active_temporary_revisions.map((tr) => tr.temporary_revision_code).join(", ")}.</p> : null}
            </article>
          )) : <article className="card oem-source-card"><strong>No OEM publication baseline registered for Series {series}</strong><p>Source files can be inspected and candidate publication revisions registered without changing an operational programme.</p></article>}
        </section>

        {contributor ? (
          <section className="card oem-source-intake">
            <div><h2>Controlled source intake</h2><p>Inspect a candidate OEM XLS/XLSX/XLSM source before it is mapped. Macros are not executed and an unmapped workbook cannot materialize engineering content.</p></div>
            <label className="btn btn-secondary oem-source-intake__file">{previewing ? "Inspecting…" : "Inspect source workbook"}<input type="file" accept=".xls,.xlsx,.xlsm" disabled={previewing} onChange={(event) => void inspectWorkbook(event.currentTarget.files?.[0] ?? null)} /></label>
            {preview ? (
              <div className="oem-source-preview">
                <div className="oem-source-preview__summary"><strong>{preview.filename}</strong><span>{preview.detected_profile} · {preview.profile_confidence} confidence · {(preview.size_bytes / 1024 / 1024).toFixed(2)} MB</span><code>{preview.checksum_sha256}</code></div>
                {preview.warnings.map((warning) => <div className="alert alert--warning" key={warning}>{warning}</div>)}
                <div className="table-wrapper"><table className="table planning-table"><thead><tr><th>Sheet</th><th>State</th><th>Rows</th><th>Columns</th></tr></thead><tbody>{preview.sheets.map((sheet) => <tr key={sheet.name}><td>{sheet.name}</td><td>{sheet.state}</td><td>{sheet.row_count.toLocaleString()}</td><td>{sheet.column_count.toLocaleString()}</td></tr>)}</tbody></table></div>
              </div>
            ) : null}
          </section>
        ) : null}

        <section className="card oem-baseline__controls">
          <div><label htmlFor="oem-pack">Source pack</label><select id="oem-pack" value={selectedPackId} onChange={(event) => setSelectedPackId(event.target.value)}><option value="">Select source pack</option>{packs.map((pack) => <option key={pack.id} value={pack.id}>{pack.code}</option>)}</select></div>
          <div><label htmlFor="oem-revision">Content revision</label><select id="oem-revision" value={selectedRevisionId} onChange={(event) => setSelectedRevisionId(event.target.value)}><option value="">Select revision</option>{revisions.map((revision) => <option key={revision.id} value={revision.id}>{revision.revision_code} · {revision.status}</option>)}</select></div>
          <div className="oem-baseline__identity"><span>Selected baseline</span><strong>{selectedPack?.series ? `DHC-8 Series ${selectedPack.series}` : selectedPack?.family || "—"}</strong><small>{selectedRevision ? `${selectedRevision.revision_code} · ${selectedRevision.status}` : "No content revision selected"}</small></div>
        </section>

        {detail ? (
          <>
            <section className="card oem-baseline__statement">
              <div className="planning-panel__header"><div><h2>Source baseline statement</h2><p>The exact controlled material used to construct this content revision.</p></div><span className={statusClass(detail.status)}>{detail.status}</span></div>
              <div className="oem-baseline__hash"><span>Content hash</span><code>{detail.content_hash || "Draft hash unavailable"}</code></div>
              <div className="table-wrapper"><table className="table planning-table"><thead><tr><th>Source</th><th>Revision</th><th>Effective</th><th>Authority</th><th>Page / section</th><th>SHA-256</th></tr></thead><tbody>{detail.sources.map((source) => <tr key={source.id}><td><strong>{source.reference}</strong><small>{source.source_type}</small></td><td>{source.source_revision}</td><td>{fmtDate(source.effective_date)}</td><td>{source.authority}</td><td>{source.source_page_ref || "—"}</td><td><code className="oem-baseline__short-hash" title={source.checksum_sha256}>{source.checksum_sha256.slice(0, 12)}…</code></td></tr>)}</tbody></table></div>
            </section>

            <section className="card oem-baseline__task-library">
              <div className="planning-panel__header"><div><h2>Canonical OEM requirements</h2><p>{visibleTasks.length.toLocaleString()} of {detail.tasks.length.toLocaleString()} task(s) in the loaded revision.</p></div></div>
              <div className="oem-baseline__filters"><input value={search} onChange={(event) => setSearch(event.target.value)} placeholder="Search task, ATA, task card, effectivity or source…" /><select value={section} onChange={(event) => setSection(event.target.value)}>{sections.map((value) => <option value={value} key={value}>{value === "ALL" ? "All programme sections" : value.replace(/_/g, " ")}</option>)}</select></div>
              <div className="table-wrapper oem-baseline__table-wrap"><table className="table table-striped planning-table oem-baseline__task-table"><thead><tr><th>Task</th><th>ATA</th><th>Type</th><th>Interval</th><th>Effectivity</th><th>Source authority</th><th>Procedure</th><th>Source</th></tr></thead><tbody>{visibleTasks.map((task) => <tr key={task.id}><td><strong>{task.task_code}</strong><small>{task.title}</small></td><td>{task.ata_chapter || "—"}</td><td>{task.task_type || "—"}</td><td>{intervalText(task)}</td><td className="oem-baseline__effectivity">{task.raw_effectivity_text || "Machine-controlled expression"}</td><td>{sourceAuthorityText(task)}</td><td><span>{task.task_card_number || "—"}</span><small>{task.amm_reference || ""}</small></td><td><span>{task.source_reference}</span><small>{task.source_page_ref || ""}</small></td></tr>)}</tbody></table></div>
            </section>

            <section className="card">
              <div className="planning-panel__header"><div><h2>Controlled supporting resources</h2><p>Access, cross-reference, component-tracking, packaging and other non-task MPD data.</p></div><strong>{detail.resources.length.toLocaleString()}</strong></div>
              {detail.resources.length ? <div className="table-wrapper"><table className="table planning-table"><thead><tr><th>Kind</th><th>Code</th><th>Title</th><th>Source</th></tr></thead><tbody>{detail.resources.slice(0, 500).map((resource) => <tr key={resource.id}><td>{resource.resource_kind}</td><td>{resource.resource_code}</td><td>{resource.title}</td><td>{resource.source_reference} · {resource.source_page_ref || resource.source_revision}</td></tr>)}</tbody></table></div> : <p className="text-muted">No supporting resources have been materialized in this revision.</p>}
            </section>
          </>
        ) : !loading ? <section className="card"><strong>No published OEM content revision selected.</strong><p className="text-muted">A source can be registered and reviewed without becoming operational. Tasks appear here only after a governed content-pack revision is created.</p></section> : null}
      </div>
    </DepartmentLayout>
  );
};

export { OemBaselinePage };
export default OemBaselinePage;
