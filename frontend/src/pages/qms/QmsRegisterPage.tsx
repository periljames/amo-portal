import React, { useCallback, useEffect, useMemo, useRef, useState } from "react";
import { AlertTriangle, ArrowRight, CheckCircle2, Clock3, HelpCircle, RefreshCw, Search, ShieldCheck, X } from "lucide-react";
import { Link, Navigate, useLocation, useNavigate, useSearchParams } from "react-router-dom";

import { hasQmsRolePermission, isPlatformSuperuser } from "../../app/routeGuards";
import DepartmentLayout from "../../components/Layout/DepartmentLayout";
import PageHeader from "../../components/shared/PageHeader";
import { apiRequest, qmsPath } from "../../services/apiClient";
import { getCachedUser } from "../../services/auth";
import type { QmsSourceError } from "../../types/qms";
import {
  classifyQmsPath,
  qmsBasePath,
  qmsModulePath,
  type QmsModuleRoute,
} from "./routes/qmsRouteRegistry";
import "../../styles/qms-register.css";

type LoadState = "idle" | "loading" | "ready" | "error";
type QmsRow = Record<string, unknown>;

type QmsRegisterResponse = {
  module?: string;
  view?: string;
  table?: string;
  items?: QmsRow[];
  columns?: string[];
  limit?: number;
  offset?: number;
  next_offset?: number | null;
  has_more?: boolean;
  table_missing?: boolean;
  warning?: string | null;
  source_errors?: QmsSourceError[];
  trace_id?: string | null;
  elapsed_ms?: number | null;
  applied_filters?: Record<string, string>;
};

const PAGE_SIZES = [15, 30, 50] as const;
const CONTROLLED_NEW_VIEWS = new Set(["new"]);
const SEARCH_DEBOUNCE_MS = 350;
const TECHNICAL_COLUMNS = new Set([
  "id",
  "uuid",
  "record_id",
  "amo_id",
  "tenant_id",
  "user_id",
  "owner_user_id",
  "assigned_to_user_id",
  "created_by_user_id",
  "updated_by_user_id",
  "payload",
  "raw_payload",
]);

function friendlyError(error: unknown): string {
  if (error instanceof Error && error.message.trim()) return error.message;
  return "Unable to load this Quality workspace.";
}

function humanise(value: unknown): string {
  return String(value ?? "")
    .replaceAll("_", " ")
    .replaceAll("-", " ")
    .replace(/\b\w/g, (character) => character.toUpperCase());
}

function formatValue(value: unknown): string {
  if (value == null || value === "") return "—";
  if (typeof value === "boolean") return value ? "Yes" : "No";
  if (typeof value === "number") return Intl.NumberFormat().format(value);
  if (typeof value === "object") {
    try {
      const serialised = JSON.stringify(value);
      return serialised.length > 100 ? `${serialised.slice(0, 97)}…` : serialised;
    } catch {
      return String(value);
    }
  }
  const raw = String(value);
  const parsed = /^\d{4}-\d{2}-\d{2}(?:T|$)/.test(raw) ? new Date(raw) : null;
  if (parsed && !Number.isNaN(parsed.getTime())) return parsed.toLocaleString();
  return raw.length > 130 ? `${raw.slice(0, 127)}…` : raw;
}

function rowId(row: QmsRow): string | null {
  const value = row.id ?? row.uuid ?? row.record_id;
  return value == null ? null : String(value);
}

function statusTone(value: unknown): string {
  const status = String(value || "").toUpperCase();
  if (["CLOSED", "COMPLETE", "COMPLETED", "ACTIVE", "APPROVED", "IMPLEMENTED"].includes(status)) return "positive";
  if (["OVERDUE", "REJECTED", "CANCELLED", "FAILED", "CRITICAL", "MAJOR"].includes(status)) return "danger";
  if (["DRAFT", "PENDING", "PENDING_APPROVAL", "OPEN", "IN_PROGRESS", "AWAITING_AUDITEE", "AWAITING_QUALITY_REVIEW"].includes(status)) return "warning";
  return "neutral";
}

function deriveColumns(rows: QmsRow[], responseColumns: string[] | undefined): string[] {
  const preferred = [
    "reference", "audit_ref", "car_number", "finding_ref", "doc_code", "title", "name", "message",
    "status", "severity", "owner_name", "assigned_to_name", "responsible_personnel", "department_name",
    "due_date", "target_date", "created_at", "updated_at",
  ];
  const seen = new Set<string>();
  const candidates = [...preferred, ...(responseColumns || []), ...rows.flatMap((row) => Object.keys(row))];
  return candidates.filter((column) => {
    if (seen.has(column) || TECHNICAL_COLUMNS.has(column) || column.endsWith("_id")) return false;
    seen.add(column);
    return rows.some((row) => row[column] != null && row[column] !== "");
  }).slice(0, 7);
}

function viewLabel(view: string): string {
  if (view === "assigned-to-me") return "Assigned to me";
  if (view === "executive-dashboard") return "Executive dashboard";
  return humanise(view);
}

function routeContext(pathname: string): { amoCode: string; module: QmsModuleRoute; view: string } | null {
  const classified = classifyQmsPath(pathname);
  if (classified.kind !== "known" || !classified.amoCode || !classified.module) return null;
  const relative = (classified.relativePath || "").split("/").filter(Boolean);
  return {
    amoCode: classified.amoCode,
    module: classified.module,
    view: relative[1] || classified.module.defaultView,
  };
}

function recordRoute(amoCode: string, module: QmsModuleRoute, id: string): string {
  if (module.id === "evidence-vault") {
    return `${qmsBasePath(amoCode)}/${module.segment}/${encodeURIComponent(id)}`;
  }
  return `${qmsBasePath(amoCode)}/${module.segment}/${encodeURIComponent(id)}/overview`;
}

function firstValue(row: QmsRow, keys: string[]): unknown {
  for (const key of keys) {
    const value = row[key];
    if (value != null && value !== "") return value;
  }
  return null;
}

function taskTitle(row: QmsRow): string {
  const value = firstValue(row, ["title", "name", "message", "subject", "reference", "audit_ref", "car_number", "finding_ref", "doc_code"]);
  return value == null ? "Quality assignment" : String(value);
}

function taskReference(row: QmsRow): string | null {
  const value = firstValue(row, ["reference", "audit_ref", "car_number", "finding_ref", "doc_code", "case_ref", "mission_ref"]);
  return value == null ? null : String(value);
}

function taskKind(row: QmsRow): string {
  const value = firstValue(row, ["assignment_type", "task_type", "event_type", "type", "category", "module", "source_type"]);
  return value == null ? "Quality work" : humanise(value);
}

function taskDue(row: QmsRow): unknown {
  return firstValue(row, ["due_date", "target_date", "planned_date", "scheduled_for", "review_date", "created_at"]);
}

function taskRoute(row: QmsRow): string | null {
  const value = firstValue(row, ["route", "source_route", "link", "href"]);
  if (typeof value !== "string") return null;
  const trimmed = value.trim();
  return trimmed.startsWith("/") ? trimmed : null;
}

function taskDueTone(value: unknown, status: unknown): "danger" | "warning" | "neutral" {
  const state = String(status || "").toUpperCase();
  if (["CLOSED", "COMPLETE", "COMPLETED", "CANCELLED"].includes(state)) return "neutral";
  if (typeof value !== "string") return statusTone(status) === "danger" ? "danger" : "neutral";
  const parsed = new Date(value);
  if (Number.isNaN(parsed.getTime())) return statusTone(status) === "danger" ? "danger" : "neutral";
  const now = new Date();
  const days = (parsed.getTime() - now.getTime()) / 86_400_000;
  if (days < 0) return "danger";
  if (days <= 7) return "warning";
  return "neutral";
}

const QmsRegisterPage: React.FC = () => {
  const location = useLocation();
  const navigate = useNavigate();
  const context = useMemo(() => routeContext(location.pathname), [location.pathname]);
  const [searchParams, setSearchParams] = useSearchParams();
  const abortRef = useRef<AbortController | null>(null);
  const [state, setState] = useState<LoadState>("idle");
  const [data, setData] = useState<QmsRegisterResponse | null>(null);
  const [error, setError] = useState<string | null>(null);

  const query = searchParams.get("q") || "";
  const status = searchParams.get("status") || "";
  const limit = PAGE_SIZES.includes(Number(searchParams.get("limit")) as (typeof PAGE_SIZES)[number])
    ? Number(searchParams.get("limit"))
    : 30;
  const offset = Math.max(0, Number(searchParams.get("offset") || 0));
  const controlledNew = Boolean(context && CONTROLLED_NEW_VIEWS.has(context.view));
  const [searchDraft, setSearchDraft] = useState(query);

  const updateSearch = useCallback((updates: Record<string, string | null>) => {
    const next = new URLSearchParams(searchParams);
    Object.entries(updates).forEach(([key, value]) => {
      if (value == null || value === "") next.delete(key);
      else next.set(key, value);
    });
    setSearchParams(next, { replace: true });
  }, [searchParams, setSearchParams]);

  useEffect(() => {
    setSearchDraft(query);
  }, [query]);

  useEffect(() => {
    if (searchDraft.trim() === query.trim()) return;
    const timer = window.setTimeout(() => {
      updateSearch({ q: searchDraft.trim() || null, offset: null });
    }, SEARCH_DEBOUNCE_MS);
    return () => window.clearTimeout(timer);
  }, [query, searchDraft, updateSearch]);

  const load = useCallback(async () => {
    if (!context || controlledNew) return;
    abortRef.current?.abort(new DOMException("Superseded by a newer Quality register request", "AbortError"));
    const controller = new AbortController();
    abortRef.current = controller;
    setState("loading");
    setError(null);

    const params = new URLSearchParams({ limit: String(limit), offset: String(offset) });
    if (query.trim()) params.set("q", query.trim());
    if (status) params.set("status", status);

    try {
      const response = await apiRequest<QmsRegisterResponse>(
        `${qmsPath(context.amoCode, `/${context.module.segment}/${context.view}`)}?${params.toString()}`,
        { timeoutMs: 15_000, signal: controller.signal },
      );
      if (controller.signal.aborted) return;
      setData(response);
      setState("ready");
    } catch (loadError) {
      if (controller.signal.aborted) return;
      setError(friendlyError(loadError));
      setState("error");
    }
  }, [context, controlledNew, limit, offset, query, status]);

  useEffect(() => {
    void load();
    return () => {
      abortRef.current?.abort(new DOMException("Quality register unmounted", "AbortError"));
    };
  }, [load]);

  const rows = data?.items || [];
  const columns = useMemo(() => deriveColumns(rows, data?.columns), [data?.columns, rows]);
  const currentUser = getCachedUser();
  const diagnosticsAuthorized = Boolean(currentUser?.is_amo_admin || currentUser?.role === "QUALITY_MANAGER" || currentUser?.role === "QUALITY_INSPECTOR");

  if (!context) return <Navigate to="." replace />;
  const { amoCode, module, view } = context;
  if (isPlatformSuperuser()) return <Navigate to="/platform/control" replace />;
  if (!hasQmsRolePermission(module.permission)) return <Navigate to={qmsBasePath(amoCode)} replace />;

  const responseLimit = data?.limit ?? limit;
  const responseOffset = data?.offset ?? offset;
  const page = Math.floor(responseOffset / Math.max(1, responseLimit)) + 1;
  const startRow = rows.length ? responseOffset + 1 : 0;
  const endRow = responseOffset + rows.length;
  const hasFilters = Boolean(query || status);
  const isInbox = module.id === "inbox";

  return (
    <DepartmentLayout amoCode={amoCode} activeDepartment="quality">
      <div className={`qms-register-page qms-register-page--${module.id}`}>
        <PageHeader
          compact
          eyebrow="Quality Management System"
          title={module.label}
          subtitle={isInbox
            ? `${viewLabel(view)}. Prioritise your assigned approvals, reviews, verifications and assurance work.`
            : `${viewLabel(view)} workspace. Results are server-bounded; open the governed record to investigate or act.`}
          breadcrumbs={[
            { label: "Quality", to: qmsBasePath(amoCode) },
            { label: module.navigationLabel },
            { label: viewLabel(view) },
          ]}
          actions={!controlledNew ? (
            <button type="button" className="qms-register-refresh" onClick={() => void load()} disabled={state === "loading"}>
              <RefreshCw size={16} className={state === "loading" ? "is-spinning" : ""} aria-hidden="true" /> Refresh
            </button>
          ) : null}
        />

        {controlledNew ? (
          <section className="qms-register-controlled" role="status">
            <ShieldCheck size={24} aria-hidden="true" />
            <div>
              <span>Controlled workflow</span>
              <h2>Creation belongs to the governed source workflow</h2>
              <p>{module.label} records require their approved source workflow, mandatory fields, numbering, ownership and approval controls. This register does not manufacture a reduced duplicate form.</p>
              <Link to={qmsModulePath(amoCode, module.id, module.defaultView)}>Open {viewLabel(module.defaultView)} <ArrowRight size={14} /></Link>
            </div>
          </section>
        ) : (
          <>
            <section className="qms-register-workspace" aria-label={`${module.label} ${viewLabel(view)}`}>
              <div className="qms-register-toolbar">
                <label className="qms-register-search">
                  <span>Search</span>
                  <Search size={16} aria-hidden="true" />
                  <input value={searchDraft} onChange={(event) => setSearchDraft(event.target.value)} placeholder={`Search ${module.navigationLabel.toLowerCase()}`} aria-label={`Search ${module.navigationLabel}`} />
                </label>
                <label><span>View</span><select value={view} onChange={(event) => navigate(qmsModulePath(amoCode, module.id, event.target.value))}>{module.validViews.filter((candidate) => candidate !== "new").map((candidate) => <option key={candidate} value={candidate}>{viewLabel(candidate)}</option>)}</select></label>
                <label><span>Status</span><select value={status} onChange={(event) => updateSearch({ status: event.target.value, offset: null })}><option value="">All statuses</option><option value="OPEN">Open</option><option value="IN_PROGRESS">In progress</option><option value="PENDING_REVIEW">Pending review</option><option value="CLOSED">Closed</option><option value="REJECTED">Rejected</option></select></label>
                <label><span>Rows</span><select value={limit} onChange={(event) => updateSearch({ limit: event.target.value, offset: null })}>{PAGE_SIZES.map((size) => <option key={size} value={size}>{size}</option>)}</select></label>
                <div className="qms-register-toolbar__state"><strong>Page {page}</strong><small>{rows.length ? `${startRow.toLocaleString()}–${endRow.toLocaleString()}` : "No rows"}{data?.has_more ? " · more available" : ""}</small></div>
                {hasFilters ? <button type="button" className="qms-register-clear" onClick={() => { setSearchDraft(""); updateSearch({ q: null, status: null, offset: null }); }}><X size={14} aria-hidden="true" /> Clear</button> : null}
              </div>

              {data?.warning || data?.table_missing || data?.source_errors?.length ? <div className="qms-register-warning" role="status"><AlertTriangle size={18} aria-hidden="true" /><span>{data?.warning || (data?.table_missing ? "The configured Quality data source is unavailable." : "Some source reads failed; available rows are shown.")}</span></div> : null}
              {error ? <div className="qms-register-error" role="alert"><AlertTriangle size={18} aria-hidden="true" /><div><strong>Unable to load this register</strong><p>{error}</p></div><button type="button" onClick={() => void load()}>Retry</button></div> : null}
              {state === "loading" && !data ? <div className="qms-register-loading" role="status"><RefreshCw size={18} className="is-spinning" /> Loading {module.navigationLabel.toLowerCase()}…</div> : null}
              {state !== "loading" && !error && rows.length === 0 ? <div className="qms-register-empty"><CheckCircle2 size={20} aria-hidden="true" /><div><strong>No records in this view</strong><p>No row matched the current tenant, view, status and search filters.</p></div></div> : null}

              {rows.length && isInbox ? (
                <div className="qms-register-task-list" aria-label="Quality assignments">
                  {rows.map((row, index) => {
                    const id = rowId(row) || `task-${index}`;
                    const statusValue = firstValue(row, ["status", "state", "severity"]);
                    const dueValue = taskDue(row);
                    const route = taskRoute(row);
                    const tone = taskDueTone(dueValue, statusValue);
                    const content = (
                      <>
                        <span className={`qms-register-task__marker is-${tone}`} aria-hidden="true" />
                        <span className="qms-register-task__body">
                          <span className="qms-register-task__meta"><strong>{taskKind(row)}</strong>{taskReference(row) ? <span>{taskReference(row)}</span> : null}</span>
                          <b>{taskTitle(row)}</b>
                          <small>{dueValue ? `Due / recorded ${formatValue(dueValue)}` : "No due date returned"}</small>
                        </span>
                        <span className="qms-register-task__state">{statusValue ? <span className={`qms-register-status qms-register-status--${statusTone(statusValue)}`}>{humanise(statusValue)}</span> : null}{route ? <span className="qms-register-open">Open <ArrowRight size={15} /></span> : <span className="qms-register-task__no-route">Assigned work</span>}</span>
                      </>
                    );
                    return route ? <Link key={id} to={route} className="qms-register-task">{content}</Link> : <article key={id} className="qms-register-task">{content}</article>;
                  })}
                </div>
              ) : null}

              {rows.length && !isInbox ? (
                <div className="qms-register-table-wrap">
                  <table className="qms-register-table">
                    <thead><tr>{columns.map((column) => <th key={column}>{humanise(column)}</th>)}{module.allowRecordDetails ? <th>Action</th> : null}</tr></thead>
                    <tbody>{rows.map((row, index) => {
                      const id = rowId(row) || `row-${index}`;
                      return <tr key={id}>{columns.map((column) => {
                        const value = row[column];
                        return <td key={column} data-label={humanise(column)}>{column === "status" || column === "severity" ? <span className={`qms-register-status qms-register-status--${statusTone(value)}`}>{humanise(value) || "Unknown"}</span> : formatValue(value)}</td>;
                      })}{module.allowRecordDetails ? <td data-label="Action">{rowId(row) ? <Link className="qms-register-open" to={recordRoute(amoCode, module, id)}>Open <ArrowRight size={14} /></Link> : "—"}</td> : null}</tr>;
                    })}</tbody>
                  </table>
                </div>
              ) : null}

              <footer className="qms-register-pagination">
                <button type="button" disabled={responseOffset <= 0 || state === "loading"} onClick={() => updateSearch({ offset: String(Math.max(0, responseOffset - responseLimit)) })}>Previous</button>
                <span>{rows.length ? `Showing ${startRow.toLocaleString()}–${endRow.toLocaleString()}` : "No results"}{data?.has_more ? " · additional results available" : " · end of results"}</span>
                <button type="button" disabled={!data?.has_more || state === "loading"} onClick={() => updateSearch({ offset: String(data?.next_offset ?? responseOffset + responseLimit) })}>Next</button>
              </footer>
            </section>

            <details className="qms-register-help">
              <summary><HelpCircle size={16} aria-hidden="true" /> Workflow guidance</summary>
              <div><strong>{module.label}</strong><p>{isInbox ? "Use this workspace as your personal Quality action queue. Open the authoritative source workflow to approve, review, verify or complete the work; technical record identifiers stay secondary." : "Use this workspace to find and open governed records. Creation, approval, evidence, verification and closure stay in their dedicated workflows instead of being duplicated in the register."}</p></div>
            </details>

            {diagnosticsAuthorized ? <details className="qms-register-diagnostics"><summary>Support diagnostics</summary><dl><div><dt>Source</dt><dd>{data?.table || module.segment}</dd></div><div><dt>Trace ID</dt><dd><code>{data?.trace_id || "Unavailable"}</code></dd></div><div><dt>Backend duration</dt><dd>{data?.elapsed_ms == null ? "Unavailable" : `${data.elapsed_ms} ms`}</dd></div><div><dt>Applied view</dt><dd>{data?.view || view}</dd></div></dl></details> : null}
          </>
        )}
      </div>
    </DepartmentLayout>
  );
};

export default QmsRegisterPage;
