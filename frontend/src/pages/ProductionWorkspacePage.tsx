import React, { useEffect, useMemo, useState } from "react";
import { Link, useNavigate, useParams, useSearchParams } from "react-router-dom";
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

const GridWrap: React.FC<{ children: React.ReactNode }> = ({ children }) => (
  <div style={{ overflow: "auto", border: "1px solid var(--border,#d4d4d8)", borderRadius: 8, maxHeight: "60vh" }}>{children}</div>
);

const thStyle: React.CSSProperties = { position: "sticky", top: 0, background: "#f8fafc", zIndex: 2, whiteSpace: "nowrap" };
const stickyLeft: React.CSSProperties = { position: "sticky", left: 0, background: "#fff", zIndex: 1 };

function parseClipboard(text: string): string[][] {
  return text
    .trim()
    .split(/\r?\n/)
    .map((r) => r.split("\t"));
}

const ProductionWorkspacePage: React.FC = () => {
  const canEdit = canEditProduction();
  const { tailId } = useParams<{ tailId?: string }>();
  const [search, setSearch] = useSearchParams();
  const navigate = useNavigate();
  const tab = (search.get("tab") as TabKey) || "fleet";

  const [fleet, setFleet] = useState<any[]>([]);
  const [summary, setSummary] = useState<Record<string, any>>({});
  const [selectedTail, setSelectedTail] = useState<string | null>(tailId || null);
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
      const chosen = tailId || selectedTail || rows[0]?.serial_number || null;
      setSelectedTail(chosen);
      const map: Record<string, any> = {};
      await Promise.all(rows.map(async (r) => {
        try {
          map[r.serial_number] = await usageSummary(r.serial_number);
        } catch {
          map[r.serial_number] = null;
        }
      }));
      setSummary(map);
    });
  }, [tailId]);

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
    const refreshed = await listUsage(selectedTail);
    setUsageRows(refreshed);
  };

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

  const onPasteAt = async (e: React.ClipboardEvent<HTMLInputElement>, startIndex: number, col: "date" | "techlog_no" | "block_hours" | "cycles") => {
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

  return (
    <div className="page">
      <h1>Production Workspace</h1>
      <p>Worksheet-like tabs and grids mapped to existing fleet/records endpoints.</p>
      <div style={{ display: "flex", gap: 8, flexWrap: "wrap", marginBottom: 12 }}>
        {TABS.map((t) => (
          <button key={t.key} type="button" onClick={() => switchTab(t.key)} className={`btn ${tab === t.key ? "btn-primary" : "btn-ghost"}`}>{t.label}</button>
        ))}
      </div>

      {tab === "fleet" && (
        <>
          <h2>Fleet Hours Summary</h2>
          <GridWrap>
            <table className="table">
              <thead>
                <tr>
                  <th style={{ ...thStyle, ...stickyLeft }}>Tail</th><th style={thStyle}>Aircraft Type</th><th style={thStyle}>Station</th><th style={thStyle}>Status</th><th style={thStyle}>TTAF</th><th style={thStyle}>TCA</th><th style={thStyle}>Last Update Date</th><th style={thStyle}>7-day daily avg (Hours)</th><th style={thStyle}>7-day daily avg (Cycles)</th><th style={thStyle}>Missing update flag</th>
                </tr>
              </thead>
              <tbody>
                {fleet.map((ac) => {
                  const s = summary[ac.serial_number];
                  const last = usageRows.filter((u) => u && selectedTail === ac.serial_number).at(-1);
                  const miss = !last || (Date.now() - new Date(last.date).getTime()) / (1000 * 3600 * 24) > 1;
                  return (
                    <tr key={ac.serial_number} onClick={() => { setSelectedTail(ac.serial_number); navigate(`/production/fleet/${ac.serial_number}?tab=fleet`); }}>
                      <td style={stickyLeft}>{ac.registration || ac.serial_number}</td><td>{ac.model || ""}</td><td>{ac.home_base || ""}</td><td>{ac.status || ""}</td><td>{s?.total_hours ?? ""}</td><td>{s?.total_cycles ?? ""}</td><td>{last?.date || ""}</td><td>{s?.seven_day_daily_average_hours ?? ""}</td><td>{""}</td><td>{miss ? "Missing" : "OK"}</td>
                    </tr>
                  );
                })}
              </tbody>
            </table>
          </GridWrap>

          <h3 style={{ marginTop: 16 }}>Tail Daily Utilisation ({selectedTail || "-"})</h3>
          <GridWrap>
            <table className="table">
              <thead><tr><th style={{ ...thStyle, ...stickyLeft }}>Date</th><th style={thStyle}>Techlog No</th><th style={thStyle}>Hours</th><th style={thStyle}>Cycles</th><th style={thStyle}>Hours to MX</th><th style={thStyle}>Days to MX</th><th style={thStyle}>TTAF</th><th style={thStyle}>TCA</th><th style={thStyle}>TTESN</th><th style={thStyle}>TCESN</th><th style={thStyle}>TTSOH</th><th style={thStyle}>TTSHSI</th></tr></thead>
              <tbody>
                {mergedUsage.map((row, idx) => (
                  <tr key={row.id}>
                    {(["date", "techlog_no", "block_hours", "cycles"] as const).map((f, cidx) => (
                      <td key={f} style={f === "date" ? stickyLeft : undefined}>
                        <input value={String((row as any)[f] ?? "")} onPaste={(e)=>onPasteAt(e, idx, f)} onChange={(e)=>onDirty({ id: row.id > 0 ? row.id : undefined, date: f==="date"?e.target.value:String(row.date), techlog_no: f==="techlog_no"?e.target.value:String(row.techlog_no), block_hours: f==="block_hours"?Number(e.target.value):Number(row.block_hours||0), cycles: f==="cycles"?Number(e.target.value):Number(row.cycles||0) })} disabled={!canEdit} style={{ minWidth: cidx===0?120:90 }} />
                      </td>
                    ))}
                    <td>{row.hours_to_mx ?? ""}</td><td>{row.days_to_mx ?? ""}</td><td>{row.ttaf_after ?? ""}</td><td>{row.tca_after ?? ""}</td><td>{row.ttesn_after ?? ""}</td><td>{row.tcesn_after ?? ""}</td><td>{row.ttsoh_after ?? ""}</td><td>{row.ttshsi_after ?? ""}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          </GridWrap>
          <div style={{ display: "flex", gap: 8, marginTop: 8 }}>
            {canEdit && <button className="btn btn-primary" onClick={saveBatch}>Save Changes</button>}
            {canEdit && <button className="btn btn-ghost" onClick={() => setDirtyRows((d) => [...d, { _new: true, date: new Date().toISOString().slice(0,10), techlog_no: "NIL", block_hours: 0, cycles: 0 }])}>Add Row</button>}
          </div>
        </>
      )}

      {tab === "logbooks" && <div><h2>Logbooks</h2><p>Technical log view reuses existing data linkage (WO/CRS/evidence). Tail: {selectedTail || "-"}.</p><p>Open deferrals linked context rows: {deferrals.length}</p><ul><li>Airframe Logbook</li><li>Engine Logbook</li><li>Propeller Logbook</li></ul></div>}

      {tab === "compliance" && (
        <div>
          <h2>Compliance (AD/SB)</h2>
          <GridWrap><table className="table"><thead><tr><th style={{...thStyle,...stickyLeft}}>Reference</th><th style={thStyle}>Description</th><th style={thStyle}>Applicable scope</th><th style={thStyle}>Next due</th><th style={thStyle}>Status</th><th style={thStyle}>Evidence present</th></tr></thead><tbody>{[...ads,...sbs].map((r:any)=><tr key={`${r.item_type}-${r.id}`}><td style={stickyLeft}>{r.reference}</td><td>{r.description || ""}</td><td>{JSON.stringify(r.applicability_json || {})}</td><td>{r.next_due_date || ""}</td><td>{r.status}</td><td>{(r.evidence_asset_ids?.length||0)>0?"Yes":"No"}</td></tr>)}</tbody></table></GridWrap>
        </div>
      )}

      {tab === "inspections" && (
        <div>
          <h2>Inspections & Hard Time</h2>
          <GridWrap><table className="table"><thead><tr><th style={{...thStyle,...stickyLeft}}>Item/Task</th><th style={thStyle}>Reference</th><th style={thStyle}>Interval type</th><th style={thStyle}>Interval value</th><th style={thStyle}>Last done</th><th style={thStyle}>Next due</th><th style={thStyle}>Status</th><th style={thStyle}>Linked WO</th><th style={thStyle}>Evidence</th></tr></thead><tbody>{mxStatus.map((s:any)=><tr key={s.id}><td style={stickyLeft}>{s.program_item?.description || s.program_item_id}</td><td>{s.program_item?.task_code || ""}</td><td>{s.interval_type || ""}</td><td>{s.interval_value || ""}</td><td>{s.last_done_date || ""}</td><td>{s.next_due_date || s.next_due_hours || s.next_due_cycles || ""}</td><td>{s.status || ""}</td><td>{s.linked_wo_id || ""}</td><td>{s.evidence_present ? "Yes" : ""}</td></tr>)}</tbody></table></GridWrap>
        </div>
      )}

      {tab === "mods" && <div><h2>Modifications</h2><p>Read-only register placeholder. Link to canonical record source when available.</p></div>}

      {tab === "components" && (
        <div>
          <h2>Components (OC/CM)</h2>
          <GridWrap><table className="table"><thead><tr><th style={{...thStyle,...stickyLeft}}>ATA</th><th style={thStyle}>Description</th><th style={thStyle}>Position</th><th style={thStyle}>Part Number</th><th style={thStyle}>Serial Number</th><th style={thStyle}>Date of Installation</th><th style={thStyle}>Condition</th><th style={thStyle}>Release Certificate</th><th style={thStyle}>Installation WO</th></tr></thead><tbody>{components.map((c:any)=><tr key={c.id}><td style={stickyLeft}>{c.ata || ""}</td><td>{c.description || ""}</td><td>{c.position || ""}</td><td>{c.part_number || ""}</td><td>{c.serial_number || ""}</td><td>{c.installed_at || ""}</td><td>{c.condition || ""}</td><td>{c.release_certificate || ""}</td><td>{c.work_order_id || ""}</td></tr>)}</tbody></table></GridWrap>
        </div>
      )}

      {tab === "missing" && (
        <div>
          <h2>Missing/Backfill</h2>
          <p>Missing dates for selected tail: {selectedTail || "-"}</p>
          <GridWrap><table className="table"><thead><tr><th style={{...thStyle,...stickyLeft}}>Missing Date</th><th style={thStyle}>Backfill Hours</th><th style={thStyle}>Backfill Cycles</th><th style={thStyle}>Techlog</th></tr></thead><tbody>{missingDates.map((d)=><tr key={d}><td style={stickyLeft}>{d}</td><td><input defaultValue={0} onChange={(e)=>onDirty({ date:d, techlog_no:"NIL", block_hours:Number(e.target.value), cycles:0 })} disabled={!canEdit}/></td><td><input defaultValue={0} onChange={(e)=>onDirty({ date:d, techlog_no:"NIL", block_hours:0, cycles:Number(e.target.value) })} disabled={!canEdit}/></td><td><input defaultValue="NIL" onChange={(e)=>onDirty({ date:d, techlog_no:e.target.value, block_hours:0, cycles:0 })} disabled={!canEdit}/></td></tr>)}</tbody></table></GridWrap>
          <p>Conflict/exceptions queue: {exceptions.filter((x:any)=>String(x.ex_type||"").toLowerCase().includes("conflict")).length}</p>
          {canEdit && <button className="btn btn-primary" onClick={saveBatch}>Save Backfill</button>}
        </div>
      )}

      {messages.length > 0 && <div style={{ marginTop: 12 }}><h3>Batch Save Results</h3><ul>{messages.map((m, i) => <li key={i}>{m}</li>)}</ul></div>}

      <div style={{ marginTop: 18 }}>
        <Link to="/production/fleet">Open Fleet route</Link>
      </div>
    </div>
  );
};

export default ProductionWorkspacePage;
