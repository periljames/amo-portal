import { useEffect, useRef, useState } from "react";
import { useQuery, useQueryClient } from "@tanstack/react-query";
import { Link, Navigate, useLocation, useSearchParams } from "react-router-dom";
import DepartmentLayout from "../../components/Layout/DepartmentLayout";
import QmsSectionTabs from "../../components/QMS/QmsSectionTabs";
import { hasQmsRolePermission } from "../../app/routeGuards";
import { apiRequest, qmsPath } from "../../services/apiClient";
import { getCachedUser } from "../../services/auth";
import { apiBlob } from "../../services/typedApi";
import { saveDownloadedFile } from "../../utils/downloads";
import type { ReviewMember, ReviewRecord } from "../../services/qmsManagementReview";
import { classifyQmsPath, qmsModulePath } from "./routes/qmsRouteRegistry";
import "./qms-management-review.css";

type RegisterField = { key: string; label: string; type: "text" | "textarea" | "number" | "date" | "select" | "equipment" | "provider"; required: boolean; options: string[] };
type EquipmentReport = { equipment_total: number; active: number; active_within_due_date: number; active_overdue: number; active_missing_due_date: number; out_of_service: number; open_tolerance_cases: number; retained_calibrations: number; passed: number; failed: number };
type RegisterData = { items: ReviewRecord[]; total: number; offset: number; limit: number; label: string; source: string; fields: RegisterField[]; statuses: string[];
  members: ReviewMember[]; providers?: { id: number; title: string }[]; parties?: string[]; equipment: { id: string; title: string }[]; status_counts: { status: string; count: number }[]; risk_matrix: number[][] | null; unassessed: number; immutable: boolean;
  risk_history?: { record_id: string; title: string; at: string; by: string; status: string; assessment: { likelihood: number; consequence: number; rating: string; risk_score: number } }[]; equipment_report?: EquipmentReport | null };
type Draft = { submission_id?: string; title: string; description: string; status: string; owner_user_id: string; due_date: string | null; fields: Record<string, string | number> };
const permission: Record<string, string> = { system: "qms.risk", risk: "qms.risk", "equipment-calibration": "qms.equipment", "external-interface": "qms.external", suppliers: "qms.supplier" };
const friendly = (error: unknown) => error instanceof Error ? error.message : "The request could not be completed. Your unsaved changes remain available.";
const dateLabel = (value: string | null | undefined) => value ? new Date(`${value.slice(0, 10)}T12:00:00`).toLocaleDateString("en-GB", { day: "2-digit", month: "short", year: "numeric" }).toUpperCase() : "Not set";
const display = (status: string) => status.replaceAll("_", " ").toLowerCase().replace(/^./, letter => letter.toUpperCase());
const fullName = (m: ReviewMember) => `${m.first_name || ""} ${m.last_name || ""}`.trim() || m.email;

export default function QmsControlledRegisterPage() {
  const location = useLocation();
  const queryClient = useQueryClient();
  const context = classifyQmsPath(location.pathname);
  const amoCode = context.amoCode || "";
  const module = context.module!;
  const [params, setParams] = useSearchParams();
  const segment = context.relativePath?.split("/")[1] || module.defaultView;
  const recordRoute = !module.validViews.includes(segment);
  const view = recordRoute ? params.get("source_view") || module.defaultView : segment;
  const recordId = recordRoute ? segment : params.get("record") || "";
  const query = params.get("q") || "";
  const status = params.get("status") || "";
  const offset = Math.max(0, Number(params.get("offset")) || 0);
  const [revision, setRevision] = useState(0);
  const [creating, setCreating] = useState(false);
  const [message, setMessage] = useState("");
  const [downloadError, setDownloadError] = useState("");
  const [downloading, setDownloading] = useState(false);
  const [historyPage, setHistoryPage] = useState(0);
  useEffect(() => setHistoryPage(0), [view, query, status]);
  const canManage = hasQmsRolePermission(`${permission[module.id]}.manage`);
  const canExport = hasQmsRolePermission("qms.reports.export");
  const endpoint = qmsPath(amoCode, `/register-workspace/${module.segment}/${view}`);
  const filter = new URLSearchParams({ q: query, status, offset: String(offset) });
  const list = useQuery<RegisterData>({ queryKey: ["controlled-register", amoCode, module.id, view, query, status, offset, revision],
    placeholderData: (previous, previousQuery) => previousQuery?.queryKey[1] === amoCode && previousQuery.queryKey[2] === module.id && previousQuery.queryKey[3] === view ? previous : undefined,
    queryFn: ({ signal }) => apiRequest<RegisterData>(`${endpoint}?${filter}`, { signal, cacheTtlMs: 0 }) });
  const detail = useQuery({ queryKey: ["controlled-register-record", amoCode, module.id, view, recordId, revision], enabled: !!recordId,
    queryFn: ({ signal }) => apiRequest<ReviewRecord>(`${endpoint}/${encodeURIComponent(recordId)}`, { signal, cacheTtlMs: 0 }) });
  useEffect(() => { if (detail.data && location.hash === "#register-record") document.getElementById("register-record")?.scrollIntoView({ block: "start" }); }, [detail.data, location.hash]);
  useEffect(() => { setCreating(false); setMessage(""); }, [location.pathname]);
  const update = (values: Record<string, string | null>) => {
    const next = new URLSearchParams(params);
    for (const [key, value] of Object.entries(values)) { if (!value) next.delete(key); else next.set(key, value); }
    setParams(next, { replace: true });
  };
  if (recordRoute) return <Navigate to={`${qmsModulePath(amoCode, module.id, view)}?record=${encodeURIComponent(recordId)}`} replace />;
  const data = list.data;
  const person = (id: string) => { const member = data?.members.find(m => m.id === id); return member ? fullName(member) : "Former / unavailable member"; };
  const saved = (row: ReviewRecord) => { queryClient.setQueryData(["controlled-register-record", amoCode, module.id, view, row.id, revision + 1], row); setMessage(`Saved: ${row.title}.`); setCreating(false); update({ record: row.id }); setRevision(r => r + 1); };
  return <DepartmentLayout amoCode={amoCode} activeDepartment="quality"><section className="qms-review" aria-label="Quality control register">
    <header className="qms-review__heading"><div><h1>{module.id === "external-interface" ? data?.label || "External interface" : module.label}</h1><p>{data?.label || "Loading register"} · Maintain attributable records and evidence-backed follow-up.</p></div><div className="qms-review__buttons">
      {canManage && data && <button className="qms-review__primary" onClick={() => { setCreating(true); update({ record: null }); }}>Add {data.source === "calibrations" ? "calibration" : "record"}</button>}
      <button onClick={() => setRevision(r => r + 1)} disabled={list.isFetching}>Refresh</button>
      <button disabled={!canExport || !data || downloading} onClick={async () => { setDownloading(true); setDownloadError(""); try {
        const result = await apiBlob(`${endpoint}/export?${new URLSearchParams({ q: query, status })}`); saveDownloadedFile(result.blob, result.filename || `QMS-${module.id}-${view}.csv`);
      } catch (e) { setDownloadError(friendly(e)); } finally { setDownloading(false); } }}>{downloading ? "Preparing…" : "Download complete CSV"}</button>
    </div></header>
    <QmsSectionTabs amoCode={amoCode} />
    {message && <p role="status" className="qms-review__success">{message}</p>}{downloadError && <p role="alert">{downloadError}</p>}
    {list.isPending && <p role="status">Loading register records…</p>}
    {list.isError && <div role="alert" className="qms-review__error">{friendly(list.error)} <button onClick={() => void list.refetch()}>Retry register</button></div>}
    {data && <>
      <section className="qms-review__stats" aria-label="Register status totals"><button onClick={() => update({ status: null, offset: null })}>All matching records <strong>{data.total}</strong></button>{data.status_counts.map(item => <button key={item.status} onClick={() => update({ status: item.status, offset: null })}><strong>{item.count}</strong><span>{display(item.status)}</span></button>)}</section>
      {module.id === "equipment-calibration" && view === "reports" && <section className="qms-review__section"><h2>Calibration assurance report</h2>
        <p>Tenant-wide recorded equipment status and due dates, plus all retained completed calibrations. These totals are independent of the history filters below. A future due date alone does not verify certificate evidence or serviceability.</p>
        {data.equipment_report ? <><div className="qms-review__stats" aria-label="Calibration report summary">{([
          ["active_overdue", "Active equipment overdue"], ["out_of_service", "Out of service"], ["open_tolerance_cases", "Open tolerance cases"], ["retained_calibrations", "Retained calibrations"],
        ] as [keyof EquipmentReport, string][]).map(([key, text]) => <div key={key}><strong>{data.equipment_report![key]}</strong><span>{text}</span></div>)}</div>
          <div className="qms-review__table"><table aria-label="Calibration report measures"><thead><tr><th>Recorded measure</th><th>Count</th></tr></thead><tbody>{([
            ["equipment_total", "Equipment inventory records"], ["active", "Active equipment"], ["active_within_due_date", "Active equipment within due date"], ["active_missing_due_date", "Active equipment missing a due date"], ["passed", "Recorded calibration passes"], ["failed", "Recorded calibration failures"],
          ] as [keyof EquipmentReport, string][]).map(([key, text]) => <tr key={key}><th>{text}</th><td>{data.equipment_report![key]}</td></tr>)}<tr><th>Retained results without PASS / FAIL classification</th><td>{data.equipment_report.retained_calibrations - data.equipment_report.passed - data.equipment_report.failed}</td></tr></tbody></table></div>
          <p><Link to={qmsModulePath(amoCode, "equipment-calibration", "overdue")}>Inspect overdue equipment</Link> · <Link to={qmsModulePath(amoCode, "equipment-calibration", "out-of-tolerance")}>Inspect tolerance cases</Link></p>
        </> : <p role="alert">The calibration report source is unavailable. Refresh after the API is ready; historical rows alone are not this report.</p>}
      </section>}
      {module.id === "risk" && view === "risk-matrix" && data.risk_matrix && <section className="qms-review__section"><h2>Assessed risk matrix</h2><p>Each cell counts open risks at the recorded likelihood and consequence, on a 1–5 scale. Risk levels are explicitly assessed by the owner; this matrix does not certify acceptability.</p>
        <p>Consequence →</p><div className="qms-review__table qms-review__matrix"><table aria-label="Risk likelihood and consequence matrix"><thead><tr><th>Likelihood ↓</th>{[1, 2, 3, 4, 5].map(n => <th key={n}>{n}</th>)}</tr></thead><tbody>{[5, 4, 3, 2, 1].map(l => <tr key={l}><th>{l}</th>{data.risk_matrix![l - 1].map((count, c) => <td key={c} title={`Likelihood ${l}, consequence ${c + 1}`}>{count}</td>)}</tr>)}</tbody></table></div><p>{data.unassessed} open risk(s) lack a complete assessment and are excluded from the matrix.</p></section>}
      {view === "trends" && <section className="qms-review__section"><h2>Risk assessment history</h2><p>Each row is an assessment retained when a risk was created or revised. Earlier exposure is not inferred for records without assessment history. Downloads include every retained assessment matching the filters.</p>
        {!data.risk_history?.length ? <p>No assessment revisions have been recorded yet.</p> : <><div className="qms-review__table"><table><thead><tr><th>Recorded</th><th>Risk</th><th>Assessor</th><th>Likelihood</th><th>Consequence</th><th>Level / score</th></tr></thead><tbody>{data.risk_history.slice(historyPage * 30, (historyPage + 1) * 30).map((event, index) => <tr key={`${event.record_id}:${event.at}:${index}`}><td>{new Date(event.at).toLocaleString()}</td><td><Link to={`${qmsModulePath(amoCode, "risk", "register")}?record=${event.record_id}`}>{event.title}</Link></td><td>{person(event.by)}</td><td>{event.assessment.likelihood}</td><td>{event.assessment.consequence}</td><td>{event.assessment.rating} / {event.assessment.risk_score}</td></tr>)}</tbody></table></div><nav aria-label="Register pages"><button disabled={!historyPage} onClick={() => setHistoryPage(p => p - 1)}>Previous assessments</button><span>{data.risk_history.length} retained assessments</span><button disabled={(historyPage + 1) * 30 >= data.risk_history.length} onClick={() => setHistoryPage(p => p + 1)}>Next assessments</button></nav></>}
      </section>}
      {creating && canManage && <RegisterEditor key={`new-${view}`} draftScope={endpoint} data={data} onCancel={() => setCreating(false)} onSave={async body => saved(await apiRequest<ReviewRecord>(endpoint, { method: "POST", body: JSON.stringify(body) }))} />}
      {recordId && detail.isPending && <p role="status">Loading record…</p>}
      {recordId && detail.isError && <p role="alert">{friendly(detail.error)} <button onClick={() => void detail.refetch()}>Retry record</button></p>}
      {recordId && detail.data && <section id="register-record"><RegisterEditor key={`${detail.data.id}:${detail.data.version}:${revision}`} data={data} record={detail.data} readOnly={!canManage || data.immutable} onCancel={() => update({ record: null })} onSave={async body => saved(await apiRequest<ReviewRecord>(`${endpoint}/${recordId}`, { method: "PUT", body: JSON.stringify({ ...body, expected_version: detail.data!.version }) }))} /></section>}
      <section className="qms-review__section"><div className="qms-review__heading"><h2>{data.label}</h2><div className="qms-review__buttons"><label>Search this register<input type="search" value={query} onChange={e => update({ q: e.target.value, offset: null })} /></label><label>Filter status<select value={status} onChange={e => update({ status: e.target.value, offset: null })}><option value="">All statuses</option>{data.statuses.map(s => <option key={s} value={s}>{display(s)}</option>)}</select></label></div></div>
        {!data.items.length ? <p>No records match this view.{canManage && <> <button onClick={() => setCreating(true)}>Add the first record</button></>}</p> : <div className="qms-review__table"><table><thead><tr><th>Title / reference</th>{["external-interface", "suppliers"].includes(module.id) && <th>External party / classification</th>}<th>Status</th><th>{module.id === "equipment-calibration" ? "Next calibration / review" : "Due / review date"}</th><th>Owner</th><th>Action</th></tr></thead><tbody>{data.items.map(row => <tr key={row.id}><td>{row.title}{["external-interface", "suppliers"].includes(module.id) && <small>{String((row.payload as Record<string, unknown>).external_reference || "No external reference supplied")}</small>}{module.id === "risk" && row.payload && <small className="qms-register__rating">{String((row.payload as Record<string, unknown>).rating || "Not assessed")}</small>}</td>{["external-interface", "suppliers"].includes(module.id) && <td>{String((row.payload as Record<string, unknown>).party || data.providers?.find(p => String(p.id) === String((row.payload as Record<string, unknown>).provider_id))?.title || "Not recorded")}{["regulator-findings", "provider-findings"].includes(data.source) && <small>{display(String((row.payload as Record<string, unknown>).finding_origin || (data.source === "provider-findings" ? "PROVIDER_OVERSIGHT" : "REGULATORY_AUTHORITY")))} · {display(String((row.payload as Record<string, unknown>).finding_level || "Level not recorded"))}</small>}</td>}<td>{display(row.status)}</td><td>{dateLabel(row.due_date)}</td><td>{person(row.owner_user_id)}</td><td><Link to={`?${new URLSearchParams({ ...Object.fromEntries(params), record: row.id })}#register-record`} onClick={() => setCreating(false)}>Open record</Link></td></tr>)}</tbody></table></div>}
        <nav aria-label="Register pages"><button disabled={!offset} onClick={() => update({ offset: String(Math.max(0, offset - 30)) })}>Previous</button><span>{data.total ? `${offset + 1}–${Math.min(offset + 30, data.total)} of ${data.total}` : "0 records"}</span><button disabled={offset + 30 >= data.total} onClick={() => update({ offset: String(offset + 30) })}>Next</button></nav>
      </section>
    </>}
  </section></DepartmentLayout>;
}

function RegisterEditor({ data, draftScope, record, readOnly = false, onSave, onCancel }: { data: RegisterData; draftScope?: string; record?: ReviewRecord; readOnly?: boolean; onSave: (body: Draft) => Promise<void>; onCancel: () => void }) {
  const submitting = useRef(false);
  const draftKey = draftScope ? `qms-register-draft:${getCachedUser()?.id || "anonymous"}:${draftScope}` : "";
  const [body, setBody] = useState<Draft>(() => {
    if (draftKey) { try { const retained = JSON.parse(sessionStorage.getItem(draftKey) || "null"); if (retained?.submission_id && retained?.fields) return retained; } catch { /* Browser storage may be unavailable. */ } }
    return ({ submission_id: record ? undefined : crypto.randomUUID(), title: record?.title || "", description: record?.description || "", status: record?.status || data.statuses[0], owner_user_id: record?.owner_user_id || "", due_date: record?.due_date?.slice(0, 10) || null,
    fields: Object.fromEntries(data.fields.map(f => [f.key, (record?.payload as unknown as Record<string, string | number> | undefined)?.[f.key] || ""])) }); });
  useEffect(() => { if (draftKey && (body.title || body.description || Object.values(body.fields).some(Boolean))) { try { sessionStorage.setItem(draftKey, JSON.stringify(body)); } catch { /* Keep in-memory editing available. */ } } }, [draftKey, body]);
  const [error, setError] = useState(""); const [busy, setBusy] = useState(false);
  const set = (key: keyof Omit<Draft, "fields">, value: string | null) => setBody(p => ({ ...p, [key]: value }));
  const setField = (key: string, value: string) => setBody(p => ({ ...p, fields: { ...p.fields, [key]: value } }));
  return <form className="qms-review__section qms-review__form" onSubmit={async e => { e.preventDefault(); if (submitting.current) return; submitting.current = true; setBusy(true); setError(""); try { await onSave(body); if (draftKey) { try { sessionStorage.removeItem(draftKey); } catch { /* Save already succeeded. */ } } } catch (cause) { setError(friendly(cause)); } finally { submitting.current = false; setBusy(false); } }}>
    <div className="qms-review__heading"><h2>{record ? record.title : data.source === "calibrations" ? "Record a calibration" : data.source === "equipment" ? "Add equipment" : `Add ${data.label.toLowerCase()} record`}</h2><button type="button" disabled={busy} onClick={onCancel}>Close editor</button></div>
    <p>Fields marked * are required. Choose existing owners and providers from the lists. New customer names may be entered when they are not already listed. Unsaved new records are retained in this browser tab until saved.</p>
    {data.source === "regulator-findings" && <p>Retain the issuer’s classification exactly. Regulatory findings require an explicit response deadline and authority acceptance before closure; internal audit closure does not close an external finding.</p>}
    {data.immutable && record && <p>Completed calibration records are retained unchanged. Record a new calibration to supersede these results.</p>}
    {error && <p role="alert" className="qms-review__error">{error} Your entries have been retained.</p>}
    <fieldset disabled={busy || readOnly}><div className="qms-review__fields"><label>Record title *<input required minLength={3} maxLength={255} value={body.title} onChange={e => set("title", e.target.value)} /></label><label>Record status<select value={body.status} onChange={e => set("status", e.target.value)}>{data.statuses.map(s => <option key={s} value={s}>{display(s)}</option>)}</select></label>
      <label>Record owner *<select aria-label="Record owner" required value={body.owner_user_id} onChange={e => set("owner_user_id", e.target.value)}><option value="">Choose active owner</option>{data.members.map(m => <option key={m.id} value={m.id}>{fullName(m)}</option>)}</select></label>
      <label>{data.source === "equipment" || data.source === "calibrations" ? "Next calibration due" : data.source === "regulator-findings" || data.source === "provider-findings" ? "Issuer response deadline *" : "Due / review date"}<input type="date" required={["equipment", "calibrations", "certificates", "out-of-tolerance", "regulator-findings", "provider-findings"].includes(data.source)} value={body.due_date || ""} onChange={e => set("due_date", e.target.value || null)} /></label></div>
      <label>Description<textarea maxLength={12000} rows={3} value={body.description} onChange={e => set("description", e.target.value)} /></label>
      <datalist id="register-party-options">{[...new Set([...(data.parties || []), ...(data.providers || []).map(p => p.title)])].map(name => <option key={name} value={name} />)}</datalist>
      <div className="qms-review__fields">{data.fields.map(f => <label key={f.key}>{f.label}{f.required && " *"}
        {f.type === "textarea" ? <textarea required={f.required || (f.key === "completion_evidence" && body.status === "CLOSED") || (f.key === "issued_classification" && body.fields.finding_level === "OTHER") || (f.key === "closure_acceptance" && body.status === "CLOSED" && body.fields.finding_origin === "REGULATORY_AUTHORITY")} maxLength={12000} rows={3} value={body.fields[f.key] ?? ""} onChange={e => setField(f.key, e.target.value)} />
          : f.type === "select" || f.type === "equipment" || f.type === "provider" ? <select required={f.required || (f.key === "completion_evidence" && body.status === "CLOSED") || (f.key === "issued_classification" && body.fields.finding_level === "OTHER") || (f.key === "closure_acceptance" && body.status === "CLOSED" && body.fields.finding_origin === "REGULATORY_AUTHORITY")} value={body.fields[f.key] ?? ""} onChange={e => setField(f.key, e.target.value)}><option value="">Choose {f.type === "equipment" ? "equipment" : "value"}</option>{f.type === "provider" ? (data.providers || []).map(item => <option key={item.id} value={item.id}>{item.title}</option>) : f.type === "equipment" ? data.equipment.map(item => <option key={item.id} value={item.id}>{item.title}</option>) : f.options.map(value => <option key={value} value={value}>{display(value)}</option>)}</select>
          : <input type={f.type} list={f.key === "party" ? "register-party-options" : undefined} max={f.type === "date" && ["received_on", "performed_on", "issued_on", "discovered_on"].includes(f.key) ? new Date().toLocaleDateString("en-CA") : f.type === "number" ? 5 : undefined} min={f.type === "number" ? 1 : undefined} step={f.type === "number" ? 1 : undefined} maxLength={12000} required={f.required || (f.key === "completion_evidence" && body.status === "CLOSED") || (f.key === "issued_classification" && body.fields.finding_level === "OTHER") || (f.key === "closure_acceptance" && body.status === "CLOSED" && body.fields.finding_origin === "REGULATORY_AUTHORITY")} value={body.fields[f.key] ?? ""} onChange={e => setField(f.key, e.target.value)} />}
      </label>)}</div>
      {!readOnly && <button className="qms-review__primary" type="submit">{busy ? "Saving…" : record ? "Save record changes" : "Create record"}</button>}
    </fieldset>
    {record && <details><summary>Record history · version {record.version}</summary><ol>{record.payload.history?.map((h, i) => <li key={i}>{new Date(h.at).toLocaleString()} · {display(h.event)} · {h.by}</li>)}</ol></details>}
  </form>;
}
