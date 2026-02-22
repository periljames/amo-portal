import React, { useEffect, useMemo, useState } from "react";
import { Link, useNavigate, useParams, useSearchParams } from "react-router-dom";
import DepartmentLayout from "../components/Layout/DepartmentLayout";
import PageHeader from "../components/shared/PageHeader";
import SectionCard from "../components/shared/SectionCard";
import DataTableShell from "../components/shared/DataTableShell";
import { getContext } from "../services/auth";
import {
  canEditProduction,
  createUsage,
  listAD,
  listComponents,
  listDeferrals,
  listFleetAircraft,
  listMaintenanceStatus,
  listReconciliation,
  listSB,
  listUsage,
  updateUsage,
  usageSummary,
  type UsageRow,
} from "../services/production";
import "../styles/production-workspace.css";

type TabKey = "fleet" | "logbooks" | "compliance" | "inspections" | "mods" | "components" | "missing";
const TABS: Array<{ key: TabKey; label: string }> = [
  { key: "fleet", label: "Fleet Hours" },
  { key: "logbooks", label: "Logbooks" },
  { key: "compliance", label: "Compliance (AD/SB)" },
  { key: "inspections", label: "Inspections & Hard Time" },
  { key: "mods", label: "Modifications" },
  { key: "components", label: "Components (OC/CM)" },
  { key: "missing", label: "Missing/Backfill" },
];

type DirtyRow = Partial<UsageRow> & { id?: number; _new?: boolean; date: string; techlog_no: string; block_hours: number; cycles: number };

function dayKey(d: Date) {
  return d.toISOString().slice(0, 10);
}

function parseClipboard(text: string): string[][] {
  return text.trim().split(/\r?\n/).map((r) => r.split("\t"));
}

const ProductionWorkspacePage: React.FC = () => {
  const canEdit = canEditProduction();
  const params = useParams<{ amoCode?: string; department?: string; tailId?: string }>();
  const context = getContext();
  const navigate = useNavigate();
  const [search, setSearch] = useSearchParams();
  const tab = ((search.get("tab") as TabKey) || "fleet") as TabKey;
  const amoCode = params.amoCode || context.amoSlug || "system";

  const [fleet, setFleet] = useState<any[]>([]);
  const [summary, setSummary] = useState<Record<string, any>>({});
  const [selectedTail, setSelectedTail] = useState<string | null>(params.tailId || null);
  const [usageRows, setUsageRows] = useState<UsageRow[]>([]);
  const [dirtyRows, setDirtyRows] = useState<DirtyRow[]>([]);
  const [messages, setMessages] = useState<string[]>([]);

  const [ads, setAds] = useState<any[]>([]);
  const [sbs, setSbs] = useState<any[]>([]);
  const [mxStatus, setMxStatus] = useState<any[]>([]);
  const [components, setComponents] = useState<any[]>([]);
  const [deferrals, setDeferrals] = useState<any[]>([]);
  const [exceptions, setExceptions] = useState<any[]>([]);

  useEffect(() => {
    listFleetAircraft().then(async (rows) => {
      setFleet(rows);
      const chosen = params.tailId || selectedTail || rows[0]?.serial_number || null;
      setSelectedTail(chosen);
      const map: Record<string, any> = {};
      await Promise.all(
        rows.map(async (r) => {
          try {
            map[r.serial_number] = await usageSummary(r.serial_number);
          } catch {
            map[r.serial_number] = null;
          }
        })
      );
      setSummary(map);
    });
  }, [params.tailId]);

  useEffect(() => {
    if (!selectedTail) return;
    listUsage(selectedTail).then(setUsageRows);
    listMaintenanceStatus(selectedTail).then(setMxStatus).catch(() => setMxStatus([]));
    listComponents(selectedTail).then(setComponents).catch(() => setComponents([]));
  }, [selectedTail]);

  useEffect(() => {
    listAD().then(setAds).catch(() => setAds([]));
    listSB().then(setSbs).catch(() => setSbs([]));
    listDeferrals().then(setDeferrals).catch(() => setDeferrals([]));
    listReconciliation().then(setExceptions).catch(() => setExceptions([]));
  }, []);

  const mergedUsage = useMemo(() => {
    const existing = usageRows.map((r) => ({ ...r }));
    dirtyRows.forEach((d) => {
      if (d.id) {
        const idx = existing.findIndex((x) => x.id === d.id);
        if (idx >= 0) existing[idx] = { ...existing[idx], ...d } as UsageRow;
      } else {
        existing.push({ ...(d as any), id: -Math.floor(Math.random() * 1_000_000), updated_at: new Date().toISOString() });
      }
    });
    return existing.sort((a, b) => String(a.date).localeCompare(String(b.date)));
  }, [usageRows, dirtyRows]);

  const missingDates = useMemo(() => {
    if (!mergedUsage.length) return [] as string[];
    const dates = new Set(mergedUsage.map((r) => String(r.date).slice(0, 10)));
    const min = new Date([...dates].sort()[0]);
    const max = new Date([...dates].sort().at(-1)!);
    const out: string[] = [];
    for (let d = new Date(min); d <= max; d.setDate(d.getDate() + 1)) {
      const k = dayKey(d);
      if (!dates.has(k)) out.push(k);
    }
    return out;
  }, [mergedUsage]);

  const onDirty = (row: DirtyRow) => {
    setDirtyRows((prev) => {
      const key = row.id ? `id:${row.id}` : `new:${row.date}:${row.techlog_no}`;
      const next = [...prev];
      const idx = next.findIndex((x) => (x.id ? `id:${x.id}` : `new:${x.date}:${x.techlog_no}`) === key);
      if (idx >= 0) next[idx] = { ...next[idx], ...row };
      else next.push(row);
      return next;
    });
  };

  const saveBatch = async () => {
    if (!selectedTail || dirtyRows.length === 0) return;
    const logs: string[] = [];
    for (const row of dirtyRows) {
      try {
        if (row.id && row.id > 0) {
          const original = usageRows.find((x) => x.id === row.id);
          if (!original) continue;
          await updateUsage(row.id, {
            date: row.date,
            techlog_no: row.techlog_no,
            block_hours: row.block_hours,
            cycles: row.cycles,
            note: row.note,
            last_seen_updated_at: original.updated_at,
          });
          logs.push(`Updated row ${row.id}`);
        } else {
          await createUsage(selectedTail, {
            date: row.date,
            techlog_no: row.techlog_no || "NIL",
            block_hours: Number(row.block_hours || 0),
            cycles: Number(row.cycles || 0),
            note: row.note,
          });
          logs.push(`Created ${row.date}/${row.techlog_no}`);
        }
      } catch (err: any) {
        logs.push(`Row ${row.date}/${row.techlog_no}: ${String(err?.message || err)}`);
      }
    }
    setMessages(logs);
    setDirtyRows([]);
    setUsageRows(await listUsage(selectedTail));
  };

  const onPasteAt = (e: React.ClipboardEvent<HTMLInputElement>, startIndex: number, col: "date" | "techlog_no" | "block_hours" | "cycles") => {
    if (!canEdit) return;
    const text = e.clipboardData.getData("text/plain");
    if (!text.includes("\t") && !text.includes("\n")) return;
    e.preventDefault();
    const matrix = parseClipboard(text);
    const cols: Array<"date" | "techlog_no" | "block_hours" | "cycles"> = ["date", "techlog_no", "block_hours", "cycles"];
    matrix.forEach((r, ridx) => {
      const row = mergedUsage[startIndex + ridx];
      if (!row) return;
      const draft: any = { id: row.id, date: row.date, techlog_no: row.techlog_no, block_hours: row.block_hours, cycles: row.cycles };
      const c0 = cols.indexOf(col);
      r.forEach((v, cidx) => {
        const key = cols[c0 + cidx];
        if (!key) return;
        draft[key] = key === "block_hours" || key === "cycles" ? Number(v) : v;
      });
      onDirty(draft);
    });
  };

  const switchTab = (k: TabKey) => {
    const next = new URLSearchParams(search);
    next.set("tab", k);
    setSearch(next);
  };

  const activeTabIndex = TABS.findIndex((t) => t.key === tab);

  return (
    <DepartmentLayout amoCode={amoCode} activeDepartment="production">
      <div className="page production-workspace">
        <PageHeader title="Production" subtitle="Worksheet workspace for fleet, compliance, and records views." />

        <section className="page-section">
          <div className="qms-segmented production-workspace__tabs" role="tablist" aria-label="Production worksheets">
            {TABS.map((t, idx) => (
              <button
                key={t.key}
                role="tab"
                aria-selected={tab === t.key}
                className={tab === t.key ? "is-active" : ""}
                onClick={() => switchTab(t.key)}
                onKeyDown={(e) => {
                  if (e.key !== "ArrowRight" && e.key !== "ArrowLeft") return;
                  const next = e.key === "ArrowRight" ? (idx + 1) % TABS.length : (idx - 1 + TABS.length) % TABS.length;
                  switchTab(TABS[next].key);
                }}
              >
                {t.label}
              </button>
            ))}
          </div>
        </section>

        <section className="page-section production-workspace__tab-panel" key={tab} data-tab={activeTabIndex}>
          {tab === "fleet" && (
            <SectionCard title="Fleet Hours" subtitle="Summary and tail-level daily utilisation">
              <DataTableShell title="Fleet Hours Summary Grid">
                <div className="table-wrapper">
                  <table className="table table-row--compact production-grid">
                    <thead>
                      <tr>
                        <th className="production-grid__sticky">Tail</th><th>Aircraft Type</th><th>Station</th><th>Status</th><th>TTAF</th><th>TCA</th><th>Last Update Date</th><th>7-day daily avg (Hours)</th><th>7-day daily avg (Cycles)</th><th>Missing update flag</th>
                      </tr>
                    </thead>
                    <tbody>
                      {fleet.map((ac) => {
                        const s = summary[ac.serial_number];
                        const rows = selectedTail === ac.serial_number ? mergedUsage : [];
                        const last = rows.at(-1);
                        const miss = !last || (Date.now() - new Date(last.date).getTime()) / 86400000 > 1;
                        return (
                          <tr key={ac.serial_number} onClick={() => { setSelectedTail(ac.serial_number); navigate(`/production/fleet/${ac.serial_number}?tab=fleet`); }}>
                            <td className="production-grid__sticky">{ac.registration || ac.serial_number}</td><td>{ac.model || ""}</td><td>{ac.home_base || ""}</td><td>{ac.status || ""}</td><td>{s?.total_hours ?? ""}</td><td>{s?.total_cycles ?? ""}</td><td>{last?.date || ""}</td><td>{s?.seven_day_daily_average_hours ?? ""}</td><td>{""}</td><td><span className={miss ? "status-pill status-pill--warn" : "status-pill"}>{miss ? "Missing" : "OK"}</span></td>
                          </tr>
                        );
                      })}
                    </tbody>
                  </table>
                </div>
              </DataTableShell>

              <DataTableShell title={`Tail Daily Utilisation Grid (${selectedTail || "-"})`}>
                <div className="table-wrapper">
                  <table className="table table-row--compact production-grid">
                    <thead><tr><th className="production-grid__sticky">Date</th><th>Techlog No</th><th>Hours</th><th>Cycles</th><th>Hours to MX</th><th>Days to MX</th><th>TTAF</th><th>TCA</th><th>TTESN</th><th>TCESN</th><th>TTSOH</th><th>TTSHSI</th></tr></thead>
                    <tbody>
                      {mergedUsage.map((row, idx) => (
                        <tr key={row.id}>
                          {(["date", "techlog_no", "block_hours", "cycles"] as const).map((f) => (
                            <td key={f} className={f === "date" ? "production-grid__sticky" : ""}>
                              <input
                                className="input"
                                value={String((row as any)[f] ?? "")}
                                onPaste={(e) => onPasteAt(e, idx, f)}
                                onChange={(e) => onDirty({ id: row.id > 0 ? row.id : undefined, date: f === "date" ? e.target.value : String(row.date), techlog_no: f === "techlog_no" ? e.target.value : String(row.techlog_no), block_hours: f === "block_hours" ? Number(e.target.value) : Number(row.block_hours || 0), cycles: f === "cycles" ? Number(e.target.value) : Number(row.cycles || 0) })}
                                disabled={!canEdit}
                              />
                            </td>
                          ))}
                          <td>{row.hours_to_mx ?? ""}</td><td>{row.days_to_mx ?? ""}</td><td>{row.ttaf_after ?? ""}</td><td>{row.tca_after ?? ""}</td><td>{row.ttesn_after ?? ""}</td><td>{row.tcesn_after ?? ""}</td><td>{row.ttsoh_after ?? ""}</td><td>{row.ttshsi_after ?? ""}</td>
                        </tr>
                      ))}
                    </tbody>
                  </table>
                </div>
                <div className="production-workspace__actions">
                  {canEdit && <button className="btn btn-primary" onClick={saveBatch}>Save Changes</button>}
                  {canEdit && <button className="btn btn-secondary" onClick={() => setDirtyRows((d) => [...d, { _new: true, date: new Date().toISOString().slice(0, 10), techlog_no: "NIL", block_hours: 0, cycles: 0 }])}>Add Row</button>}
                  {canEdit && <button className="btn" onClick={() => setDirtyRows([])}>Discard</button>}
                </div>
              </DataTableShell>
            </SectionCard>
          )}

          {tab === "logbooks" && <SectionCard title="Logbooks" subtitle={`Tail ${selectedTail || "-"}`}><p>Airframe, Engine, and Propeller logbook worksheet views reuse canonical records links.</p><p className="table-secondary-text">Open linked deferrals: {deferrals.length}</p></SectionCard>}

          {tab === "compliance" && <SectionCard title="Compliance (AD/SB)"><DataTableShell><div className="table-wrapper"><table className="table table-row--compact production-grid"><thead><tr><th className="production-grid__sticky">Reference</th><th>Description</th><th>Applicable scope</th><th>Next due</th><th>Status</th><th>Evidence present</th></tr></thead><tbody>{[...ads, ...sbs].map((r: any) => <tr key={`${r.item_type}-${r.id}`}><td className="production-grid__sticky">{r.reference}</td><td>{r.description || ""}</td><td>{JSON.stringify(r.applicability_json || {})}</td><td>{r.next_due_date || ""}</td><td>{r.status}</td><td>{(r.evidence_asset_ids?.length || 0) > 0 ? "Yes" : "No"}</td></tr>)}</tbody></table></div></DataTableShell></SectionCard>}

          {tab === "inspections" && <SectionCard title="Inspections & Hard Time"><DataTableShell><div className="table-wrapper"><table className="table table-row--compact production-grid"><thead><tr><th className="production-grid__sticky">Item/Task</th><th>Reference</th><th>Interval type</th><th>Interval value</th><th>Last done</th><th>Next due</th><th>Status</th><th>Linked WO</th><th>Evidence</th></tr></thead><tbody>{mxStatus.map((s: any) => <tr key={s.id}><td className="production-grid__sticky">{s.program_item?.description || s.program_item_id}</td><td>{s.program_item?.task_code || ""}</td><td>{s.interval_type || ""}</td><td>{s.interval_value || ""}</td><td>{s.last_done_date || ""}</td><td>{s.next_due_date || s.next_due_hours || s.next_due_cycles || ""}</td><td>{s.status || ""}</td><td>{s.linked_wo_id || ""}</td><td>{s.evidence_present ? "Yes" : ""}</td></tr>)}</tbody></table></div></DataTableShell></SectionCard>}

          {tab === "mods" && <SectionCard title="Modifications"><p className="table-secondary-text">Read-only worksheet; link to canonical modification register where available.</p></SectionCard>}

          {tab === "components" && <SectionCard title="Components (OC/CM)"><DataTableShell><div className="table-wrapper"><table className="table table-row--compact production-grid"><thead><tr><th className="production-grid__sticky">ATA</th><th>Description</th><th>Position</th><th>Part Number</th><th>Serial Number</th><th>Date of Installation</th><th>Condition</th><th>Release Certificate</th><th>Installation WO</th></tr></thead><tbody>{components.map((c: any) => <tr key={c.id}><td className="production-grid__sticky">{c.ata || ""}</td><td>{c.description || ""}</td><td>{c.position || ""}</td><td>{c.part_number || ""}</td><td>{c.serial_number || ""}</td><td>{c.installed_at || ""}</td><td>{c.condition || ""}</td><td>{c.release_certificate || ""}</td><td>{c.work_order_id || ""}</td></tr>)}</tbody></table></div></DataTableShell></SectionCard>}

          {tab === "missing" && <SectionCard title="Missing/Backfill" subtitle={`Selected tail: ${selectedTail || "-"}`}><DataTableShell><div className="table-wrapper"><table className="table table-row--compact production-grid"><thead><tr><th className="production-grid__sticky">Missing Date</th><th>Backfill Hours</th><th>Backfill Cycles</th><th>Techlog</th></tr></thead><tbody>{missingDates.map((d) => <tr key={d}><td className="production-grid__sticky">{d}</td><td><input className="input" defaultValue={0} onChange={(e) => onDirty({ date: d, techlog_no: "NIL", block_hours: Number(e.target.value), cycles: 0 })} disabled={!canEdit} /></td><td><input className="input" defaultValue={0} onChange={(e) => onDirty({ date: d, techlog_no: "NIL", block_hours: 0, cycles: Number(e.target.value) })} disabled={!canEdit} /></td><td><input className="input" defaultValue="NIL" onChange={(e) => onDirty({ date: d, techlog_no: e.target.value, block_hours: 0, cycles: 0 })} disabled={!canEdit} /></td></tr>)}</tbody></table></div></DataTableShell><p className="table-secondary-text">Conflict/exceptions queue: {exceptions.filter((x: any) => String(x.ex_type || "").toLowerCase().includes("conflict")).length}</p>{canEdit && <div className="production-workspace__actions"><button className="btn btn-primary" onClick={saveBatch}>Save Backfill</button></div>}</SectionCard>}

          {!!messages.length && <SectionCard title="Batch Save Results"><ul>{messages.map((m, i) => <li key={i}>{m}</li>)}</ul></SectionCard>}
        </section>

        <section className="page-section">
          <Link to="/production/fleet" className="btn btn-secondary">Open Fleet route</Link>
        </section>
      </div>
    </DepartmentLayout>
  );
};

export default ProductionWorkspacePage;
