import React, { useEffect, useMemo, useState } from "react";
import { Link, useLocation, useParams, useSearchParams } from "react-router-dom";
import DepartmentLayout from "../components/Layout/DepartmentLayout";
import PageHeader from "../components/shared/PageHeader";
import SectionCard from "../components/shared/SectionCard";
import DataTableShell from "../components/shared/DataTableShell";
import AvionicsTabs from "../components/production/AvionicsTabs";
import { getCachedUser, getContext } from "../services/auth";
import {
  fetchAirworthiness,
  fetchDeferrals,
  fetchMaintenanceRecords,
  fetchPacks,
  fetchReconciliation,
  fetchSettings,
  fetchTechnicalAircraft,
  fetchTechnicalDashboard,
  fetchTraceability,
  updateSettings,
} from "../services/technicalRecords";
import { createUsage, listComponents, listMaintenanceStatus, listUsage, updateUsage, usageSummary, type UsageRow } from "../services/production";
import { canEditFeature, canViewFeature, formatCapabilitiesForUi, type ModuleFeature } from "../utils/roleAccess";
import "../styles/production-workspace.css";
import "../styles/technical-records.css";

type RecordTab = {
  label: string;
  suffix: string;
  feature: ModuleFeature;
};

type DirtyUsageRow = Partial<UsageRow> & {
  id?: number;
  _new?: boolean;
  date: string;
  techlog_no: string;
  block_hours: number;
  cycles: number;
};

type EditableUsageField = Exclude<keyof DirtyUsageRow, "_new">;

const RECORD_TABS: RecordTab[] = [
  { label: "Dashboard", suffix: "", feature: "production.records.dashboard" },
  { label: "Aircraft", suffix: "aircraft", feature: "production.records.aircraft" },
  { label: "Logbooks", suffix: "logbooks", feature: "production.records.logbooks" },
  { label: "Deferrals", suffix: "deferrals", feature: "production.records.deferrals" },
  { label: "Maintenance Records", suffix: "maintenance-records", feature: "production.records.maintenance-records" },
  { label: "Airworthiness", suffix: "airworthiness", feature: "production.records.airworthiness" },
  { label: "LLP & Components", suffix: "llp", feature: "production.records.llp-components" },
  { label: "Reconciliation", suffix: "reconciliation", feature: "production.records.reconciliation" },
  { label: "Traceability", suffix: "traceability", feature: "production.records.traceability" },
  { label: "Inspection Packs", suffix: "packs", feature: "production.records.packs" },
  { label: "Settings", suffix: "settings", feature: "production.records.settings" },
];

const AIRCRAFT_DETAIL_TABS = [
  { id: "utilisation", label: "Hours & Cycles" },
  { id: "maintenance", label: "Maintenance Status" },
  { id: "components", label: "Components" },
  { id: "airworthiness", label: "Airworthiness" },
  { id: "logbooks", label: "Logbooks" },
] as const;

type AircraftDetailTab = (typeof AIRCRAFT_DETAIL_TABS)[number]["id"];

function recordsPath(amoCode: string, suffix = ""): string {
  const normalized = suffix.replace(/^\/+/, "");
  const base = `/maintenance/${amoCode}/production/records`;
  return normalized ? `${base}/${normalized}` : base;
}

function formatDate(value?: string | null): string {
  if (!value) return "-";
  const date = new Date(value);
  if (Number.isNaN(date.getTime())) return value;
  return new Intl.DateTimeFormat(undefined, { year: "numeric", month: "short", day: "numeric" }).format(date);
}

function formatDateTime(value?: string | null): string {
  if (!value) return "-";
  const date = new Date(value);
  if (Number.isNaN(date.getTime())) return value;
  return new Intl.DateTimeFormat(undefined, {
    year: "numeric",
    month: "short",
    day: "numeric",
    hour: "numeric",
    minute: "2-digit",
  }).format(date);
}

function formatNumber(value?: number | null, digits = 1): string {
  if (value == null || Number.isNaN(Number(value))) return "-";
  return Number(value).toLocaleString(undefined, {
    minimumFractionDigits: digits,
    maximumFractionDigits: digits,
  });
}

function formatInteger(value?: number | null): string {
  if (value == null || Number.isNaN(Number(value))) return "-";
  return Number(value).toLocaleString(undefined, { maximumFractionDigits: 0 });
}

function normalizeStatusTone(value?: string | null): string {
  const normalized = `${value || ""}`.toLowerCase();
  if (normalized.includes("overdue") || normalized.includes("blocked") || normalized.includes("attention") || normalized.includes("open")) {
    return "status-pill status-pill--warn";
  }
  if (normalized.includes("resolved") || normalized.includes("closed") || normalized.includes("ok") || normalized.includes("ready") || normalized.includes("complied")) {
    return "status-pill status-pill--ok";
  }
  return "status-pill";
}

function dayKey(d: Date) {
  return d.toISOString().slice(0, 10);
}

function parseClipboard(text: string): string[][] {
  return text.trim().split(/\r?\n/).map((row) => row.split("\t"));
}

const Shell: React.FC<{
  title: string;
  subtitle: string;
  feature: ModuleFeature;
  actions?: React.ReactNode;
  children?: React.ReactNode;
}> = ({ title, subtitle, feature, actions, children }) => {
  const { amoCode } = useParams<{ amoCode?: string }>();
  const location = useLocation();
  const ctx = getContext();
  const currentUser = getCachedUser();
  const tenant = amoCode || ctx.amoSlug || ctx.amoCode || "system";
  const tabs = useMemo(
    () => RECORD_TABS.filter((tab) => canViewFeature(currentUser, tab.feature, ctx.department)),
    [currentUser, ctx.department]
  );
  const activeSuffix = useMemo(() => {
    const parts = location.pathname.split("/").filter(Boolean);
    const recordsIndex = parts.indexOf("records");
    if (recordsIndex < 0) return "";
    return parts.slice(recordsIndex + 1, recordsIndex + 2)[0] || "";
  }, [location.pathname]);

  if (!canViewFeature(currentUser, feature, ctx.department)) {
    return (
      <DepartmentLayout amoCode={tenant} activeDepartment="production">
        <div className="page technical-records-page">
          <PageHeader
            eyebrow="Production / Technical Records"
            title={title}
            subtitle="This surface is hidden for the current role."
          />
          <SectionCard title="Role visibility" subtitle="Technical records pages are limited to supervisory, certifying, records, and dependent planning roles.">
            <p className="text-muted">
              Current role scope: {formatCapabilitiesForUi(currentUser, ctx.department).join(" · ") || "Unassigned"}
            </p>
          </SectionCard>
        </div>
      </DepartmentLayout>
    );
  }

  return (
    <DepartmentLayout amoCode={tenant} activeDepartment="production">
      <div className="page technical-records-page">
        <PageHeader
          eyebrow="Production / Technical Records"
          title={title}
          subtitle={subtitle}
          meta={<span className="technical-records-page__meta">Active role scope: {formatCapabilitiesForUi(currentUser, ctx.department).join(" · ") || "Unassigned"}</span>}
          actions={actions}
        />

        <div className="production-workspace__tabs-wrap technical-records-page__tabs-wrap">
          <AvionicsTabs
            tabs={tabs.map((tab) => ({ id: tab.suffix, label: tab.label }))}
            value={activeSuffix}
            onChange={(value) => {
              window.location.assign(recordsPath(tenant, value));
            }}
            ariaLabel="Technical records navigation"
          />
        </div>

        {children}
      </div>
    </DepartmentLayout>
  );
};

const EmptyState: React.FC<{ title: string; body: string }> = ({ title, body }) => (
  <SectionCard title={title} subtitle={body} variant="subtle">
    <p className="text-muted">No records found yet.</p>
  </SectionCard>
);

const TechnicalStatGrid: React.FC<{ items: Array<{ label: string; value: string | number; helper?: string }> }> = ({ items }) => (
  <section className="page-section">
    <div className="page-section__grid technical-records-stats">
      {items.map((item) => (
        <article key={item.label} className="metric-card technical-records-stats__card">
          <div className="metric-card__label">{item.label}</div>
          <div className="metric-card__value">{item.value}</div>
          {item.helper ? <div className="technical-records-stats__helper">{item.helper}</div> : null}
        </article>
      ))}
    </div>
  </section>
);

export const TechnicalRecordsDashboardPage: React.FC = () => {
  const { amoCode } = useParams<{ amoCode?: string }>();
  const tenant = amoCode || getContext().amoSlug || getContext().amoCode || "system";
  const [tiles, setTiles] = useState<Array<{ key: string; label: string; count: number }>>([]);
  const [aircraft, setAircraft] = useState<any[]>([]);

  useEffect(() => {
    fetchTechnicalDashboard().then((x) => setTiles(x.tiles || [])).catch(() => setTiles([]));
    fetchTechnicalAircraft().then(setAircraft).catch(() => setAircraft([]));
  }, []);

  const healthyCount = aircraft.filter((row) => `${row.record_health || ""}`.toLowerCase() === "ok").length;

  return (
    <Shell
      title="Technical Records Dashboard"
      subtitle="Fleet record health, reconciliation, and evidence readiness."
      feature="production.records.dashboard"
    >
      <TechnicalStatGrid
        items={tiles.map((tile) => ({ label: tile.label, value: tile.count }))}
      />

      <section className="page-section page-section__grid technical-records-dashboard-grid">
        <SectionCard title="Fleet record health" subtitle="Current record condition by aircraft" className="technical-records-dashboard-grid__wide">
          <div className="technical-records-dashboard-grid__summary-row">
            <div className="technical-records-summary-pill">
              <strong>{aircraft.length}</strong>
              <span>Total aircraft</span>
            </div>
            <div className="technical-records-summary-pill">
              <strong>{healthyCount}</strong>
              <span>Healthy records</span>
            </div>
            <div className="technical-records-summary-pill">
              <strong>{Math.max(aircraft.length - healthyCount, 0)}</strong>
              <span>Need attention</span>
            </div>
          </div>
          <div className="table-wrapper">
            <table className="table table-row--compact table-striped">
              <thead>
                <tr>
                  <th>Aircraft</th>
                  <th>Type</th>
                  <th>Status</th>
                  <th>Hours</th>
                  <th>Cycles</th>
                  <th>Last update</th>
                  <th />
                </tr>
              </thead>
              <tbody>
                {aircraft.slice(0, 8).map((row) => (
                  <tr key={row.tail_id}>
                    <td>{row.tail}</td>
                    <td>{row.type || "-"}</td>
                    <td><span className={normalizeStatusTone(row.record_health)}>{row.record_health || "Unknown"}</span></td>
                    <td>{formatNumber(row.current_hours)}</td>
                    <td>{formatInteger(row.current_cycles)}</td>
                    <td>{formatDate(row.last_update_date)}</td>
                    <td>
                      <Link className="btn btn-secondary" to={recordsPath(tenant, `aircraft/${row.tail_id}`)}>Open</Link>
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        </SectionCard>

        <SectionCard title="Quick actions" subtitle="Common record-control entry points">
          <div className="technical-records-quick-links">
            <Link to={recordsPath(tenant, "aircraft")} className="technical-records-quick-link">Aircraft records</Link>
            <Link to={recordsPath(tenant, "reconciliation")} className="technical-records-quick-link">Reconciliation queue</Link>
            <Link to={recordsPath(tenant, "traceability")} className="technical-records-quick-link">Traceability map</Link>
            <Link to={recordsPath(tenant, "packs")} className="technical-records-quick-link">Inspection packs</Link>
          </div>
        </SectionCard>
      </section>
    </Shell>
  );
};

export const AircraftRecordsPage: React.FC = () => {
  const { amoCode } = useParams<{ amoCode?: string }>();
  const tenant = amoCode || getContext().amoSlug || getContext().amoCode || "system";
  const [rows, setRows] = useState<any[]>([]);
  const [query, setQuery] = useState("");

  useEffect(() => {
    fetchTechnicalAircraft().then(setRows).catch(() => setRows([]));
  }, []);

  const filtered = useMemo(() => {
    const needle = query.trim().toLowerCase();
    if (!needle) return rows;
    return rows.filter((row) => JSON.stringify(row).toLowerCase().includes(needle));
  }, [query, rows]);

  return (
    <Shell
      title="Aircraft Records"
      subtitle="Tail-level record control, hours, and current airworthiness data."
      feature="production.records.aircraft"
      actions={<input className="input technical-records-search" value={query} onChange={(e) => setQuery(e.target.value)} placeholder="Search tail, type, operator" />}
    >
      <SectionCard title="Aircraft register" subtitle="Choose a tail to manage hours, record health, maintenance status, and components.">
        <DataTableShell title="Fleet technical records">
          <div className="table-wrapper">
            <table className="table table-row--compact table-striped">
              <thead>
                <tr>
                  <th>Tail</th>
                  <th>Tail ID</th>
                  <th>Type</th>
                  <th>Operator</th>
                  <th>Status</th>
                  <th>Record health</th>
                  <th>Hours</th>
                  <th>Cycles</th>
                  <th>Last update</th>
                </tr>
              </thead>
              <tbody>
                {filtered.map((row) => (
                  <tr key={row.tail_id}>
                    <td><Link to={recordsPath(tenant, `aircraft/${row.tail_id}`)}>{row.tail}</Link></td>
                    <td>{row.tail_id}</td>
                    <td>{row.type || "-"}</td>
                    <td>{row.operator || "-"}</td>
                    <td>{row.status || "-"}</td>
                    <td><span className={normalizeStatusTone(row.record_health)}>{row.record_health || "Unknown"}</span></td>
                    <td>{formatNumber(row.current_hours)}</td>
                    <td>{formatInteger(row.current_cycles)}</td>
                    <td>{formatDate(row.last_update_date)}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        </DataTableShell>
      </SectionCard>
    </Shell>
  );
};

function AircraftUsageEditor({ tailId }: { tailId: string }) {
  const currentUser = getCachedUser();
  const ctx = getContext();
  const canEdit = canEditFeature(currentUser, "production.records.aircraft", ctx.department);
  const [rows, setRows] = useState<UsageRow[]>([]);
  const [draftRows, setDraftRows] = useState<DirtyUsageRow[]>([]);
  const [summary, setSummary] = useState<any>(null);
  const [messages, setMessages] = useState<string[]>([]);
  const [saving, setSaving] = useState(false);

  const load = async () => {
    const [usage, nextSummary] = await Promise.all([
      listUsage(tailId).catch(() => []),
      usageSummary(tailId).catch(() => null),
    ]);
    setRows((usage || []).sort((a, b) => String(b.date).localeCompare(String(a.date))));
    setSummary(nextSummary);
  };

  useEffect(() => {
    void load();
  }, [tailId]);

  const mergedRows = useMemo(() => {
    const existing = rows.map((row) => ({ ...row }));
    draftRows.forEach((draft) => {
      if (draft.id && draft.id > 0) {
        const idx = existing.findIndex((row) => row.id === draft.id);
        if (idx >= 0) existing[idx] = { ...existing[idx], ...draft } as UsageRow;
      } else {
        existing.unshift({
          ...(draft as UsageRow),
          id: draft.id || -Math.floor(Math.random() * 1000000),
          aircraft_serial_number: tailId,
          updated_at: new Date().toISOString(),
          created_at: new Date().toISOString(),
          verification_status: "PENDING",
        });
      }
    });
    return existing.sort((a, b) => String(b.date).localeCompare(String(a.date)));
  }, [draftRows, rows, tailId]);

  const updateDraft = (row: DirtyUsageRow) => {
    setDraftRows((prev) => {
      const key = row.id ? `id:${row.id}` : `new:${row.date}:${row.techlog_no}`;
      const next = [...prev];
      const idx = next.findIndex((item) => (item.id ? `id:${item.id}` : `new:${item.date}:${item.techlog_no}`) === key);
      if (idx >= 0) next[idx] = { ...next[idx], ...row };
      else next.push(row);
      return next;
    });
  };

  const addRow = () => {
    const today = dayKey(new Date());
    updateDraft({
      id: undefined,
      _new: true,
      date: today,
      techlog_no: "NIL",
      block_hours: 0,
      cycles: 0,
      note: "",
    });
  };

  const saveBatch = async () => {
    if (!draftRows.length) return;
    setSaving(true);
    const nextMessages: string[] = [];
    try {
      for (const draft of draftRows) {
        if (draft.id && draft.id > 0) {
          const source = rows.find((row) => row.id === draft.id);
          if (!source) continue;
          await updateUsage(draft.id, {
            date: draft.date,
            techlog_no: draft.techlog_no,
            block_hours: Number(draft.block_hours || 0),
            cycles: Number(draft.cycles || 0),
            ttaf_after: draft.ttaf_after,
            tca_after: draft.tca_after,
            ttesn_after: draft.ttesn_after,
            tcesn_after: draft.tcesn_after,
            ttsoh_after: draft.ttsoh_after,
            ttshsi_after: draft.ttshsi_after,
            tcsoh_after: draft.tcsoh_after,
            pttsn_after: draft.pttsn_after,
            hours_to_mx: draft.hours_to_mx,
            days_to_mx: draft.days_to_mx,
            note: draft.note,
            last_seen_updated_at: source.updated_at,
          });
          nextMessages.push(`Updated techlog ${draft.techlog_no} for ${draft.date}.`);
        } else {
          await createUsage(tailId, {
            date: draft.date,
            techlog_no: draft.techlog_no,
            block_hours: Number(draft.block_hours || 0),
            cycles: Number(draft.cycles || 0),
            ttaf_after: draft.ttaf_after,
            tca_after: draft.tca_after,
            ttesn_after: draft.ttesn_after,
            tcesn_after: draft.tcesn_after,
            ttsoh_after: draft.ttsoh_after,
            ttshsi_after: draft.ttshsi_after,
            tcsoh_after: draft.tcsoh_after,
            pttsn_after: draft.pttsn_after,
            hours_to_mx: draft.hours_to_mx,
            days_to_mx: draft.days_to_mx,
            note: draft.note,
          });
          nextMessages.push(`Created techlog ${draft.techlog_no} for ${draft.date}.`);
        }
      }
      setMessages(nextMessages);
      setDraftRows([]);
      await load();
    } catch (error: any) {
      setMessages([error?.message || "Failed to save hours and cycles."]);
    } finally {
      setSaving(false);
    }
  };

  const onPasteAt = (
    e: React.ClipboardEvent<HTMLInputElement>,
    startIndex: number,
    col: "date" | "techlog_no" | "block_hours" | "cycles"
  ) => {
    if (!canEdit) return;
    const text = e.clipboardData.getData("text/plain");
    if (!text.includes("\t") && !text.includes("\n")) return;
    e.preventDefault();
    const matrix = parseClipboard(text);
    const columns: Array<"date" | "techlog_no" | "block_hours" | "cycles"> = ["date", "techlog_no", "block_hours", "cycles"];
    matrix.forEach((rowValues, rowIndex) => {
      const row = mergedRows[startIndex + rowIndex];
      if (!row) return;
      const draft: DirtyUsageRow = {
        id: row.id > 0 ? row.id : undefined,
        date: String(row.date).slice(0, 10),
        techlog_no: row.techlog_no,
        block_hours: Number(row.block_hours || 0),
        cycles: Number(row.cycles || 0),
      };
      const startColumn = columns.indexOf(col);
      rowValues.forEach((value, columnIndex) => {
        const key = columns[startColumn + columnIndex];
        if (!key) return;
        (draft as any)[key] = key === "block_hours" || key === "cycles" ? Number(value) : value;
      });
      updateDraft(draft);
    });
  };

  const statItems = [
    { label: "Total hours", value: formatNumber(summary?.total_hours), helper: "Fleet total" },
    { label: "Total cycles", value: formatInteger(summary?.total_cycles), helper: "Fleet total" },
    { label: "7-day daily avg", value: formatNumber(summary?.seven_day_daily_average_hours), helper: "Hours / day" },
    { label: "Next due task", value: summary?.next_due_task_code || "-", helper: summary?.next_due_date ? `Due ${formatDate(summary.next_due_date)}` : "No due item" },
  ];

  return (
    <>
      <TechnicalStatGrid items={statItems} />
      <SectionCard
        title="Hours and cycles worksheet"
        subtitle="Workbook-style utilisation capture aligned to the uploaded hours sheet."
        actions={canEdit ? <div className="technical-records-inline-actions"><button className="btn btn-secondary" type="button" onClick={addRow}>Add row</button><button className="btn" type="button" onClick={saveBatch} disabled={saving || draftRows.length === 0}>{saving ? "Saving..." : `Save ${draftRows.length || ""}`.trim()}</button></div> : null}
      >
        <DataTableShell title="Daily techlog usage register">
          <div className="table-wrapper">
            <table className="table table-row--compact production-grid technical-records-hours-grid">
              <thead>
                <tr>
                  <th className="production-grid__sticky">DATE</th>
                  <th>TECHLOG NO</th>
                  <th>HOURS</th>
                  <th>CYCLES</th>
                  <th>HOURS TO MX</th>
                  <th>DAYS TO MX</th>
                  <th>TTAF</th>
                  <th>TCA</th>
                  <th>TTESN</th>
                  <th>TCESN</th>
                  <th>TTSOH</th>
                  <th>TTSHSI</th>
                  <th>TCSOH</th>
                  <th>PTTSN</th>
                  <th>NOTE</th>
                </tr>
              </thead>
              <tbody>
                {mergedRows.map((row, index) => {
                  const editable = canEdit;
                  const current = row as UsageRow & DirtyUsageRow;
                  const bind = (key: EditableUsageField, parser: (value: string) => unknown = (value) => value) => {
                    const rawValue = current[key];
                    const safeValue = typeof rawValue === "boolean" ? "" : rawValue ?? "";
                    return {
                      value: safeValue as string | number | readonly string[] | undefined,
                      onChange: (e: React.ChangeEvent<HTMLInputElement>) => {
                        updateDraft({
                          id: current.id > 0 ? current.id : undefined,
                          _new: current.id <= 0,
                          date: String(current.date).slice(0, 10),
                          techlog_no: current.techlog_no,
                          block_hours: Number(current.block_hours || 0),
                          cycles: Number(current.cycles || 0),
                          ...(key === "note" ? { note: String(parser(e.target.value) ?? "") } : { [key]: parser(e.target.value) }),
                        } as DirtyUsageRow);
                      },
                    };
                  };
                  return (
                    <tr key={`${row.id}-${index}`}>
                      <td className="production-grid__sticky">
                        <input className="input" type="date" disabled={!editable} {...bind("date")} onPaste={(e) => onPasteAt(e, index, "date")} />
                      </td>
                      <td><input className="input" disabled={!editable} {...bind("techlog_no")} onPaste={(e) => onPasteAt(e, index, "techlog_no")} /></td>
                      <td><input className="input" type="number" step="0.1" disabled={!editable} {...bind("block_hours", Number)} onPaste={(e) => onPasteAt(e, index, "block_hours")} /></td>
                      <td><input className="input" type="number" step="1" disabled={!editable} {...bind("cycles", Number)} onPaste={(e) => onPasteAt(e, index, "cycles")} /></td>
                      <td><input className="input" type="number" step="0.1" disabled={!editable} {...bind("hours_to_mx", Number)} /></td>
                      <td><input className="input" type="number" step="1" disabled={!editable} {...bind("days_to_mx", Number)} /></td>
                      <td><input className="input" type="number" step="0.1" disabled={!editable} {...bind("ttaf_after", Number)} /></td>
                      <td><input className="input" type="number" step="1" disabled={!editable} {...bind("tca_after", Number)} /></td>
                      <td><input className="input" type="number" step="0.1" disabled={!editable} {...bind("ttesn_after", Number)} /></td>
                      <td><input className="input" type="number" step="1" disabled={!editable} {...bind("tcesn_after", Number)} /></td>
                      <td><input className="input" type="number" step="0.1" disabled={!editable} {...bind("ttsoh_after", Number)} /></td>
                      <td><input className="input" type="number" step="0.1" disabled={!editable} {...bind("ttshsi_after", Number)} /></td>
                      <td><input className="input" type="number" step="1" disabled={!editable} {...bind("tcsoh_after", Number)} /></td>
                      <td><input className="input" type="number" step="0.1" disabled={!editable} {...bind("pttsn_after", Number)} /></td>
                      <td><input className="input" disabled={!editable} {...bind("note")} /></td>
                    </tr>
                  );
                })}
              </tbody>
            </table>
          </div>
        </DataTableShell>
        {messages.length ? <div className="technical-records-messages">{messages.map((message, idx) => <div key={`${message}-${idx}`}>{message}</div>)}</div> : null}
      </SectionCard>
    </>
  );
}

export const AircraftRecordDetailPage: React.FC = () => {
  const { tailId, amoCode } = useParams<{ tailId?: string; amoCode?: string }>();
  const tenant = amoCode || getContext().amoSlug || getContext().amoCode || "system";
  const [searchParams, setSearchParams] = useSearchParams();
  const currentTab = (searchParams.get("tab") as AircraftDetailTab | null) || "utilisation";
  const [deferrals, setDeferrals] = useState<any[]>([]);
  const [maintenanceStatus, setMaintenanceStatus] = useState<any[]>([]);
  const [components, setComponents] = useState<any[]>([]);
  const [ads, setAds] = useState<any[]>([]);
  const [sbs, setSbs] = useState<any[]>([]);

  useEffect(() => {
    if (!tailId) return;
    fetchDeferrals().then((rows) => setDeferrals((rows || []).filter((row: any) => row.tail_id === tailId))).catch(() => setDeferrals([]));
    listMaintenanceStatus(tailId).then(setMaintenanceStatus).catch(() => setMaintenanceStatus([]));
    listComponents(tailId).then(setComponents).catch(() => setComponents([]));
    fetchAirworthiness("ad").then(setAds).catch(() => setAds([]));
    fetchAirworthiness("sb").then(setSbs).catch(() => setSbs([]));
  }, [tailId]);

  if (!tailId) {
    return <Shell title="Aircraft record" subtitle="Select an aircraft first." feature="production.records.aircraft"><EmptyState title="No aircraft selected" body="Choose a tail from the aircraft records register." /></Shell>;
  }

  const statItems = [
    { label: "Open deferrals", value: deferrals.length, helper: "Tail specific" },
    { label: "Maintenance items", value: maintenanceStatus.length, helper: "Programme rows" },
    { label: "Installed components", value: components.length, helper: "Tail configuration" },
    { label: "Airworthiness refs", value: ads.length + sbs.length, helper: "AD + SB register size" },
  ];

  return (
    <Shell
      title={`Aircraft ${tailId}`}
      subtitle="Tail record control with workbook-like utilisation tracking and linked maintenance evidence."
      feature="production.records.aircraft"
      actions={<Link className="btn btn-secondary" to={recordsPath(tenant, "aircraft")}>Back to aircraft</Link>}
    >
      <TechnicalStatGrid items={statItems} />

      <div className="production-workspace__tabs-wrap technical-records-page__tabs-wrap">
        <AvionicsTabs
          tabs={AIRCRAFT_DETAIL_TABS.map((tab) => ({ id: tab.id, label: tab.label }))}
          value={currentTab}
          onChange={(value) => {
            const next = new URLSearchParams(searchParams);
            next.set("tab", value);
            setSearchParams(next);
          }}
          ariaLabel="Aircraft technical record detail tabs"
        />
      </div>

      {currentTab === "utilisation" ? <AircraftUsageEditor tailId={tailId} /> : null}

      {currentTab === "maintenance" ? (
        <section className="page-section page-section__grid technical-records-dashboard-grid">
          <SectionCard title="Maintenance status" subtitle="Current planned and due maintenance lines" className="technical-records-dashboard-grid__wide">
            <div className="table-wrapper">
              <table className="table table-row--compact table-striped">
                <thead>
                  <tr>
                    <th>Task</th>
                    <th>Description</th>
                    <th>Status</th>
                    <th>Due date</th>
                    <th>Remaining hours</th>
                    <th>Remaining cycles</th>
                  </tr>
                </thead>
                <tbody>
                  {maintenanceStatus.map((item: any, idx) => (
                    <tr key={`${item.program_item_id || idx}`}>
                      <td>{item.task_code || item.program_item_id || "-"}</td>
                      <td>{item.description || "-"}</td>
                      <td><span className={normalizeStatusTone(item.status)}>{item.status || "-"}</span></td>
                      <td>{formatDate(item.next_due_date)}</td>
                      <td>{formatNumber(item.hours_remaining)}</td>
                      <td>{formatInteger(item.cycles_remaining)}</td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          </SectionCard>
          <SectionCard title="Open deferrals" subtitle="Tail-level deferred defects">
            <div className="table-wrapper">
              <table className="table table-row--compact table-striped">
                <thead><tr><th>Defect</th><th>Type</th><th>Status</th><th>Expiry</th><th>WO</th></tr></thead>
                <tbody>
                  {deferrals.map((row) => (
                    <tr key={row.id}>
                      <td><Link to={recordsPath(tenant, `deferrals/${row.id}`)}>{row.defect_ref}</Link></td>
                      <td>{row.deferral_type || "-"}</td>
                      <td><span className={normalizeStatusTone(row.status)}>{row.status || "-"}</span></td>
                      <td>{formatDateTime(row.expiry_at)}</td>
                      <td>{row.linked_wo_id || "-"}</td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          </SectionCard>
        </section>
      ) : null}

      {currentTab === "components" ? (
        <SectionCard title="Installed components" subtitle="Installed engines, propellers, and controlled serialized items.">
          <div className="table-wrapper">
            <table className="table table-row--compact table-striped">
              <thead>
                <tr>
                  <th>Position</th>
                  <th>Part number</th>
                  <th>Serial number</th>
                  <th>Description</th>
                  <th>ATA</th>
                  <th>Hours</th>
                  <th>Cycles</th>
                </tr>
              </thead>
              <tbody>
                {components.map((component: any) => (
                  <tr key={component.id}>
                    <td>{component.position || "-"}</td>
                    <td>{component.part_number || "-"}</td>
                    <td>{component.serial_number || "-"}</td>
                    <td>{component.description || component.part_name || "-"}</td>
                    <td>{component.ata || "-"}</td>
                    <td>{formatNumber(component.hours_since_new ?? component.total_hours)}</td>
                    <td>{formatInteger(component.cycles_since_new ?? component.total_cycles)}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        </SectionCard>
      ) : null}

      {currentTab === "airworthiness" ? (
        <section className="page-section page-section__grid technical-records-dashboard-grid">
          <SectionCard title="Airworthiness directives" subtitle="Open AD register entries available to records users" className="technical-records-dashboard-grid__wide">
            <div className="table-wrapper">
              <table className="table table-row--compact table-striped">
                <thead><tr><th>Reference</th><th>Status</th><th>Next due date</th><th>Next due hours</th><th>Next due cycles</th></tr></thead>
                <tbody>
                  {ads.slice(0, 20).map((item: any) => (
                    <tr key={`ad-${item.id}`}>
                      <td>{item.reference}</td>
                      <td><span className={normalizeStatusTone(item.status)}>{item.status}</span></td>
                      <td>{formatDate(item.next_due_date)}</td>
                      <td>{formatNumber(item.next_due_hours)}</td>
                      <td>{formatInteger(item.next_due_cycles)}</td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          </SectionCard>
          <SectionCard title="Service bulletins" subtitle="SB register entries available to records users">
            <div className="table-wrapper">
              <table className="table table-row--compact table-striped">
                <thead><tr><th>Reference</th><th>Status</th><th>Next due date</th></tr></thead>
                <tbody>
                  {sbs.slice(0, 20).map((item: any) => (
                    <tr key={`sb-${item.id}`}>
                      <td>{item.reference}</td>
                      <td><span className={normalizeStatusTone(item.status)}>{item.status}</span></td>
                      <td>{formatDate(item.next_due_date)}</td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          </SectionCard>
        </section>
      ) : null}

      {currentTab === "logbooks" ? (
        <SectionCard title="Logbook view" subtitle="This tail already shares the canonical production records register.">
          <p className="text-muted">
            Airframe, engine, and propeller logbook surfaces are aligned to this aircraft record. The current backend does not yet expose a dedicated logbook list endpoint in this module, so this page keeps the user inside the same technical-records workspace while the detail register is expanded.
          </p>
          <div className="technical-records-quick-links">
            <Link to={recordsPath(tenant, "maintenance-records")}>Open maintenance records</Link>
            <Link to={recordsPath(tenant, "deferrals")}>Open deferrals</Link>
            <Link to={recordsPath(tenant, "traceability")}>Open traceability</Link>
          </div>
        </SectionCard>
      ) : null}
    </Shell>
  );
};

export const LogbooksPage: React.FC = () => {
  const { amoCode } = useParams<{ amoCode?: string }>();
  const tenant = amoCode || getContext().amoSlug || getContext().amoCode || "system";
  const [rows, setRows] = useState<any[]>([]);

  useEffect(() => {
    fetchTechnicalAircraft().then(setRows).catch(() => setRows([]));
  }, []);

  return (
    <Shell title="Logbooks" subtitle="Jump to a tail and review its linked records, utilisation, and maintenance context." feature="production.records.logbooks">
      <SectionCard title="Aircraft jump list" subtitle="Use the aircraft detail page for the current canonical logbook view.">
        <div className="technical-records-quick-links">
          {rows.map((row) => (
            <Link key={row.tail_id} to={recordsPath(tenant, `aircraft/${row.tail_id}?tab=logbooks`)}>{row.tail}</Link>
          ))}
        </div>
      </SectionCard>
    </Shell>
  );
};

export const LogbookByTailPage: React.FC = () => {
  const { tailId, amoCode } = useParams<{ tailId?: string; amoCode?: string }>();
  const tenant = amoCode || getContext().amoSlug || getContext().amoCode || "system";
  return (
    <Shell title={`Logbook ${tailId || "-"}`} subtitle="Redirected aircraft logbook context." feature="production.records.logbooks">
      <SectionCard title="Continue in aircraft record view" subtitle="The logbook surface is currently anchored within the aircraft detail page.">
        <Link className="btn" to={recordsPath(tenant, `aircraft/${tailId}?tab=logbooks`)}>Open aircraft logbook context</Link>
      </SectionCard>
    </Shell>
  );
};

export const DeferralsPage: React.FC = () => {
  const { amoCode } = useParams<{ amoCode?: string }>();
  const tenant = amoCode || getContext().amoSlug || getContext().amoCode || "system";
  const [rows, setRows] = useState<any[]>([]);

  useEffect(() => {
    fetchDeferrals().then(setRows).catch(() => setRows([]));
  }, []);

  return (
    <Shell title="Deferrals Register" subtitle="Controlled view of open and closed deferred defects with expiry trace." feature="production.records.deferrals">
      <SectionCard title="Deferrals" subtitle="Expiry and work-order linkage are visible here for records and supervisory roles.">
        <div className="table-wrapper">
          <table className="table table-row--compact table-striped">
            <thead><tr><th>Defect</th><th>Tail</th><th>Type</th><th>Status</th><th>Deferred</th><th>Expiry</th><th>WO</th></tr></thead>
            <tbody>
              {rows.map((row) => (
                <tr key={row.id}>
                  <td><Link to={recordsPath(tenant, `deferrals/${row.id}`)}>{row.defect_ref}</Link></td>
                  <td>{row.tail_id}</td>
                  <td>{row.deferral_type || "-"}</td>
                  <td><span className={normalizeStatusTone(row.status)}>{row.status}</span></td>
                  <td>{formatDateTime(row.deferred_at)}</td>
                  <td>{formatDateTime(row.expiry_at)}</td>
                  <td>{row.linked_wo_id || "-"}</td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      </SectionCard>
    </Shell>
  );
};

export const DeferralDetailPage: React.FC = () => {
  const { deferralId } = useParams<{ deferralId?: string }>();
  const [item, setItem] = useState<any>(null);

  useEffect(() => {
    fetchDeferrals().then((rows) => setItem((rows || []).find((row: any) => String(row.id) === String(deferralId)) || null)).catch(() => setItem(null));
  }, [deferralId]);

  return (
    <Shell title={`Deferral ${deferralId || "-"}`} subtitle="Deferral detail and trace information." feature="production.records.deferrals">
      {!item ? <EmptyState title="Deferral not loaded" body="The selected deferral could not be found." /> : (
        <section className="page-section page-section__grid technical-records-dashboard-grid">
          <SectionCard title="Deferral detail" subtitle="Core metadata">
            <dl className="technical-records-definition-list">
              <div><dt>Defect reference</dt><dd>{item.defect_ref}</dd></div>
              <div><dt>Tail</dt><dd>{item.tail_id}</dd></div>
              <div><dt>Type</dt><dd>{item.deferral_type}</dd></div>
              <div><dt>Status</dt><dd>{item.status}</dd></div>
              <div><dt>Deferred at</dt><dd>{formatDateTime(item.deferred_at)}</dd></div>
              <div><dt>Expiry</dt><dd>{formatDateTime(item.expiry_at)}</dd></div>
            </dl>
          </SectionCard>
          <SectionCard title="Trace" subtitle="Linked execution and release references">
            <dl className="technical-records-definition-list">
              <div><dt>Work order</dt><dd>{item.linked_wo_id || "-"}</dd></div>
              <div><dt>CRS</dt><dd>{item.linked_crs_id || "-"}</dd></div>
            </dl>
          </SectionCard>
        </section>
      )}
    </Shell>
  );
};

export const MaintenanceRecordsPage: React.FC = () => {
  const { amoCode } = useParams<{ amoCode?: string }>();
  const tenant = amoCode || getContext().amoSlug || getContext().amoCode || "system";
  const [rows, setRows] = useState<any[]>([]);

  useEffect(() => {
    fetchMaintenanceRecords().then(setRows).catch(() => setRows([]));
  }, []);

  return (
    <Shell title="Maintenance Records" subtitle="Closed maintenance events held by the technical records function." feature="production.records.maintenance-records">
      <SectionCard title="Maintenance event register" subtitle="Each record ties execution, evidence, and certifying outcome together.">
        <div className="table-wrapper">
          <table className="table table-row--compact table-striped">
            <thead><tr><th>Description</th><th>Tail</th><th>Performed</th><th>Outcome</th><th>WO</th><th>Evidence</th></tr></thead>
            <tbody>
              {rows.map((row) => (
                <tr key={row.id}>
                  <td><Link to={recordsPath(tenant, `maintenance-records/${row.id}`)}>{row.description}</Link></td>
                  <td>{row.tail_id}</td>
                  <td>{formatDateTime(row.performed_at)}</td>
                  <td>{row.outcome}</td>
                  <td>{row.linked_wo_id || "-"}</td>
                  <td>{(row.evidence_asset_ids || []).length}</td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      </SectionCard>
    </Shell>
  );
};

export const MaintenanceRecordDetailPage: React.FC = () => {
  const { recordId } = useParams<{ recordId?: string }>();
  const [item, setItem] = useState<any>(null);

  useEffect(() => {
    fetchMaintenanceRecords().then((rows) => setItem((rows || []).find((row: any) => String(row.id) === String(recordId)) || null)).catch(() => setItem(null));
  }, [recordId]);

  return (
    <Shell title={`Maintenance Record ${recordId || "-"}`} subtitle="Detailed maintenance event record." feature="production.records.maintenance-records">
      {!item ? <EmptyState title="Record not loaded" body="The selected maintenance record could not be found." /> : (
        <section className="page-section page-section__grid technical-records-dashboard-grid">
          <SectionCard title="Record detail" subtitle="Maintenance event snapshot" className="technical-records-dashboard-grid__wide">
            <dl className="technical-records-definition-list">
              <div><dt>Description</dt><dd>{item.description}</dd></div>
              <div><dt>Tail</dt><dd>{item.tail_id}</dd></div>
              <div><dt>Performed</dt><dd>{formatDateTime(item.performed_at)}</dd></div>
              <div><dt>Outcome</dt><dd>{item.outcome}</dd></div>
              <div><dt>Reference data</dt><dd>{item.reference_data_text}</dd></div>
              <div><dt>Work order</dt><dd>{item.linked_wo_id || "-"}</dd></div>
              <div><dt>Work package</dt><dd>{item.linked_wp_id || "-"}</dd></div>
            </dl>
          </SectionCard>
          <SectionCard title="Evidence" subtitle="Stored evidence IDs currently linked to this record">
            <div className="technical-records-chip-list">
              {(item.evidence_asset_ids || []).length ? (item.evidence_asset_ids || []).map((evidence: string) => <span key={evidence} className="technical-records-chip">{evidence}</span>) : <span className="text-muted">No evidence linked.</span>}
            </div>
          </SectionCard>
        </section>
      )}
    </Shell>
  );
};

export const AirworthinessPage: React.FC = () => {
  const { amoCode } = useParams<{ amoCode?: string }>();
  const tenant = amoCode || getContext().amoSlug || getContext().amoCode || "system";
  return (
    <Shell title="Airworthiness Control" subtitle="AD and SB register access from the technical records surface." feature="production.records.airworthiness">
      <section className="page-section page-section__grid technical-records-dashboard-grid">
        <SectionCard title="Airworthiness directives" subtitle="Review the AD register and linked due items.">
          <Link className="btn" to={recordsPath(tenant, "airworthiness/ad")}>Open AD register</Link>
        </SectionCard>
        <SectionCard title="Service bulletins" subtitle="Review the SB register and linked due items.">
          <Link className="btn" to={recordsPath(tenant, "airworthiness/sb")}>Open SB register</Link>
        </SectionCard>
      </section>
    </Shell>
  );
};

const AirworthinessRegisterPage: React.FC<{ type: "ad" | "sb" }> = ({ type }) => {
  const [rows, setRows] = useState<any[]>([]);

  useEffect(() => {
    fetchAirworthiness(type).then(setRows).catch(() => setRows([]));
  }, [type]);

  return (
    <Shell title={`${type.toUpperCase()} Register`} subtitle={`Technical records view of ${type.toUpperCase()} applicability and due control.`} feature="production.records.airworthiness">
      <SectionCard title={`${type.toUpperCase()} register`} subtitle="Controlled reference list">
        <div className="table-wrapper">
          <table className="table table-row--compact table-striped">
            <thead><tr><th>Reference</th><th>Status</th><th>Next due date</th><th>Next due hours</th><th>Next due cycles</th></tr></thead>
            <tbody>
              {rows.map((row) => (
                <tr key={row.id}>
                  <td>{row.reference}</td>
                  <td><span className={normalizeStatusTone(row.status)}>{row.status}</span></td>
                  <td>{formatDate(row.next_due_date)}</td>
                  <td>{formatNumber(row.next_due_hours)}</td>
                  <td>{formatInteger(row.next_due_cycles)}</td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      </SectionCard>
    </Shell>
  );
};

export const ADRegisterPage: React.FC = () => <AirworthinessRegisterPage type="ad" />;
export const SBRegisterPage: React.FC = () => <AirworthinessRegisterPage type="sb" />;
export const ADDetailPage: React.FC = () => <Shell title="Airworthiness Directive" subtitle="Directive detail page." feature="production.records.airworthiness"><EmptyState title="Detail page pending" body="The current register already exposes the core due-control data." /></Shell>;
export const SBDetailPage: React.FC = () => <Shell title="Service Bulletin" subtitle="Bulletin detail page." feature="production.records.airworthiness"><EmptyState title="Detail page pending" body="The current register already exposes the core due-control data." /></Shell>;

export const LLPPage: React.FC = () => {
  const { amoCode } = useParams<{ amoCode?: string }>();
  const tenant = amoCode || getContext().amoSlug || getContext().amoCode || "system";
  const [rows, setRows] = useState<any[]>([]);

  useEffect(() => {
    fetchTechnicalAircraft().then(setRows).catch(() => setRows([]));
  }, []);

  return (
    <Shell title="LLP Register" subtitle="Jump to a tail to inspect components and life-controlled items." feature="production.records.llp-components">
      <SectionCard title="LLP and component control" subtitle="The current backend exposes these through aircraft component history and tail-level component listings.">
        <div className="technical-records-quick-links">
          {rows.map((row) => <Link key={row.tail_id} to={recordsPath(tenant, `aircraft/${row.tail_id}?tab=components`)}>{row.tail}</Link>)}
        </div>
      </SectionCard>
    </Shell>
  );
};

export const ComponentsPage: React.FC = () => <LLPPage />;

export const ReconciliationPage: React.FC = () => {
  const [rows, setRows] = useState<any[]>([]);

  useEffect(() => {
    fetchReconciliation().then(setRows).catch(() => setRows([]));
  }, []);

  return (
    <Shell title="Reconciliation & Exceptions" subtitle="Data quality queue for technical records mismatches and corrections." feature="production.records.reconciliation">
      <SectionCard title="Exception queue" subtitle="Resolve record mismatches before release and archive activities.">
        <div className="table-wrapper">
          <table className="table table-row--compact table-striped">
            <thead><tr><th>Type</th><th>Object</th><th>Summary</th><th>Status</th><th>Created</th></tr></thead>
            <tbody>
              {rows.map((row) => (
                <tr key={row.id}>
                  <td>{row.ex_type}</td>
                  <td>{row.object_type} · {row.object_id}</td>
                  <td>{row.summary}</td>
                  <td><span className={normalizeStatusTone(row.status)}>{row.status}</span></td>
                  <td>{formatDateTime(row.created_at)}</td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      </SectionCard>
    </Shell>
  );
};

export const TraceabilityPage: React.FC = () => {
  const [data, setData] = useState<any>(null);

  useEffect(() => {
    fetchTraceability().then(setData).catch(() => setData(null));
  }, []);

  const workOrders = data?.work_orders || [];
  const crsRows = data?.crs || [];
  const records = data?.records || [];

  return (
    <Shell title="Traceability" subtitle="Cross-reference work orders, CRS, and maintenance records in one view." feature="production.records.traceability">
      <TechnicalStatGrid items={[
        { label: "Work orders", value: workOrders.length, helper: "In current result set" },
        { label: "CRS", value: crsRows.length, helper: "Joined through work orders" },
        { label: "Maintenance records", value: records.length, helper: "Linked record events" },
      ]} />
      <section className="page-section page-section__grid technical-records-dashboard-grid">
        <SectionCard title="Work orders" subtitle="Execution anchors" className="technical-records-dashboard-grid__wide">
          <div className="table-wrapper"><table className="table table-row--compact table-striped"><thead><tr><th>WO</th><th>Tail</th><th>Status</th></tr></thead><tbody>{workOrders.map((row: any) => <tr key={row.id}><td>{row.wo_number}</td><td>{row.tail_id}</td><td>{row.status}</td></tr>)}</tbody></table></div>
        </SectionCard>
        <SectionCard title="CRS" subtitle="Release trace">
          <div className="table-wrapper"><table className="table table-row--compact table-striped"><thead><tr><th>CRS</th><th>Tail</th><th>WO</th><th>Issue</th></tr></thead><tbody>{crsRows.map((row: any) => <tr key={row.id}><td>{row.crs_number}</td><td>{row.tail_id}</td><td>{row.work_order_id}</td><td>{formatDate(row.issue_date)}</td></tr>)}</tbody></table></div>
        </SectionCard>
        <SectionCard title="Maintenance records" subtitle="Record evidence trail">
          <div className="table-wrapper"><table className="table table-row--compact table-striped"><thead><tr><th>ID</th><th>Tail</th><th>WO</th><th>Performed</th></tr></thead><tbody>{records.map((row: any) => <tr key={row.id}><td>{row.id}</td><td>{row.tail_id}</td><td>{row.linked_wo_id || "-"}</td><td>{formatDateTime(row.performed_at)}</td></tr>)}</tbody></table></div>
        </SectionCard>
      </section>
    </Shell>
  );
};

export const PacksPage: React.FC = () => {
  const [data, setData] = useState<any>(null);
  const [packType, setPackType] = useState("tail");

  useEffect(() => {
    fetchPacks(packType).then(setData).catch(() => setData(null));
  }, [packType]);

  return (
    <Shell title="Inspection Packs" subtitle="Bundle and retention controls for technical-record evidence packs." feature="production.records.packs">
      <SectionCard
        title="Pack preview"
        subtitle="Preview current pack settings before bundle generation is expanded."
        actions={
          <select className="input technical-records-select" value={packType} onChange={(e) => setPackType(e.target.value)}>
            <option value="tail">Tail pack</option>
            <option value="wo">Work order pack</option>
            <option value="audit">Audit pack</option>
          </select>
        }
      >
        {!data ? (
          <p className="text-muted">Loading pack metadata…</p>
        ) : (
          <div className="technical-records-pack-grid">
            <div className="technical-records-pack-card"><strong>Pack type</strong><span>{data.pack_type}</span></div>
            <div className="technical-records-pack-card"><strong>Retention</strong><span>{data.retention_years} years</span></div>
            <div className="technical-records-pack-card"><strong>Mode</strong><span>{data.mode}</span></div>
            <div className="technical-records-pack-card technical-records-pack-card--wide"><strong>Message</strong><span>{data.message}</span></div>
          </div>
        )}
      </SectionCard>
    </Shell>
  );
};

export const TechnicalRecordsSettingsPage: React.FC = () => {
  const currentUser = getCachedUser();
  const ctx = getContext();
  const editable = canEditFeature(currentUser, "production.records.settings", ctx.department);
  const [settings, setSettings] = useState<any>(null);
  const [saving, setSaving] = useState(false);
  const [message, setMessage] = useState<string | null>(null);

  useEffect(() => {
    fetchSettings().then(setSettings).catch(() => setSettings(null));
  }, []);

  const save = async () => {
    if (!editable || !settings) return;
    setSaving(true);
    setMessage(null);
    try {
      const updated = await updateSettings(settings);
      setSettings(updated);
      setMessage("Technical records defaults saved.");
    } catch (error: any) {
      setMessage(error?.message || "Failed to save technical records defaults.");
    } finally {
      setSaving(false);
    }
  };

  return (
    <Shell
      title="Technical Records Settings"
      subtitle="Retention, manual-entry, and control defaults for the technical records workspace."
      feature="production.records.settings"
      actions={editable ? <button className="btn" type="button" onClick={save} disabled={saving || !settings}>{saving ? "Saving..." : "Save defaults"}</button> : null}
    >
      {!settings ? (
        <EmptyState title="Settings unavailable" body="The technical records settings payload could not be loaded." />
      ) : (
        <section className="page-section page-section__grid technical-records-dashboard-grid">
          <SectionCard title="Control defaults" subtitle="Applies to the technical records module" className="technical-records-dashboard-grid__wide">
            <div className="technical-records-form-grid">
              <label className="technical-records-toggle">
                <input type="checkbox" checked={!!settings.utilisation_manual_only} disabled={!editable} onChange={(e) => setSettings((prev: any) => ({ ...prev, utilisation_manual_only: e.target.checked }))} />
                <span>
                  <strong>Manual utilisation only</strong>
                  <small>Restrict hours and cycles capture to manual controlled entries.</small>
                </span>
              </label>
              <label className="technical-records-toggle">
                <input type="checkbox" checked={!!settings.ad_sb_use_hours_cycles} disabled={!editable} onChange={(e) => setSettings((prev: any) => ({ ...prev, ad_sb_use_hours_cycles: e.target.checked }))} />
                <span>
                  <strong>Use hours / cycles on AD-SB control</strong>
                  <small>Expose non-calendar due controls in the records review surface.</small>
                </span>
              </label>
              <label className="technical-records-toggle">
                <input type="checkbox" checked={!!settings.allow_manual_maintenance_records} disabled={!editable} onChange={(e) => setSettings((prev: any) => ({ ...prev, allow_manual_maintenance_records: e.target.checked }))} />
                <span>
                  <strong>Allow manual maintenance records</strong>
                  <small>Permit direct record creation when no linked work order exists.</small>
                </span>
              </label>
              <label className="technical-records-number-field">
                <span>Record retention (years)</span>
                <input className="input" type="number" min={1} max={25} disabled={!editable} value={settings.record_retention_years ?? 5} onChange={(e) => setSettings((prev: any) => ({ ...prev, record_retention_years: Number(e.target.value || 5) }))} />
              </label>
            </div>
            {message ? <div className="technical-records-messages"><div>{message}</div></div> : null}
          </SectionCard>
          <SectionCard title="Access note" subtitle="Why this page is restricted">
            <p className="text-muted">
              Settings are limited to supervisory or admin users because these defaults change how records are created, retained, and reconciled across the AMO.
            </p>
          </SectionCard>
        </section>
      )}
    </Shell>
  );
};
