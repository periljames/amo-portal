import React, { useEffect, useMemo, useState } from "react";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { useNavigate, useSearchParams } from "react-router-dom";
import { Search, Info, ClipboardList, Pencil, Save, X } from "lucide-react";
import {
  Bar,
  BarChart,
  CartesianGrid,
  ResponsiveContainer,
  Tooltip,
  XAxis,
  YAxis,
} from "recharts";
import { getBrandContext } from "../../services/branding";
import {
  qmsGetDashboard,
  qmsListAudits,
  qmsListCars,
  qmsListFindingsBulk,
  qmsListAuditSchedules,
  qmsListAuditPersonnelOptions,
  qmsUpdateAuditSchedule,
  type CAROut,
  type QMSAuditOut,
  type QMSFindingOut,
  type QMSPersonOption,
} from "../../services/qms";
import { computeReadiness } from "./readiness";
import { getDueMessage } from "./dueStatus";
import FindingDrawer from "./FindingDrawer";
import { selectRelevantDueAudit } from "../../utils/auditDate";

type Props = {
  amoCode: string;
  department: string;
  scheduleId: string;
};

type WorkspaceTab = "findings" | "checklists" | "documents";

type FindingRow = {
  finding: QMSFindingOut;
  audit: QMSAuditOut;
  linkedCar: CAROut | null;
};

type TrendDatum = {
  label: string;
  value: number;
};

type ParticipantFormState = {
  lead_auditor_user_id: string;
  observer_auditor_user_id: string;
  assistant_auditor_user_id: string;
  auditee_user_id: string;
  auditee: string;
  auditee_email: string;
};

const asStatus = (finding: QMSFindingOut): "Open" | "Closed" | "Overdue" => {
  if (finding.closed_at) return "Closed";
  if (finding.target_close_date && new Date(finding.target_close_date).getTime() < Date.now()) return "Overdue";
  return "Open";
};

const riskTone = (openLevel1: number, openLevel2: number) => {
  if (openLevel1 > 0) return { label: "High", className: "qms-pill qms-pill--danger" };
  if (openLevel2 > 0) return { label: "Moderate", className: "qms-pill qms-pill--warning" };
  return { label: "Low", className: "qms-pill qms-pill--success" };
};


const findingLevelLabel = (value?: string | null): string => {
  const normalized = String(value || "").toUpperCase();
  if (normalized === "LEVEL_1") return "Level 1 · Critical";
  if (normalized === "LEVEL_2") return "Level 2 · Major";
  if (normalized === "LEVEL_3") return "Level 3 · Minor";
  if (normalized === "LEVEL_4") return "Observations";
  return value || "Unclassified";
};

const statusClassName = (status: "Open" | "Closed" | "Overdue") => {
  if (status === "Closed") return "qms-status-pill qms-status-pill--closed";
  if (status === "Overdue") return "qms-status-pill qms-status-pill--overdue";
  return "qms-status-pill qms-status-pill--open";
};


const personName = (peopleById: Map<string, QMSPersonOption>, userId?: string | null): string => {
  if (!userId) return "Unassigned";
  const person = peopleById.get(userId);
  return person ? (person.position_title ? `${person.full_name} · ${person.position_title}` : person.full_name) : userId;
};

const participantFormFromSchedule = (schedule: {
  lead_auditor_user_id?: string | null;
  observer_auditor_user_id?: string | null;
  assistant_auditor_user_id?: string | null;
  auditee_user_id?: string | null;
  auditee?: string | null;
  auditee_email?: string | null;
} | null): ParticipantFormState => ({
  lead_auditor_user_id: schedule?.lead_auditor_user_id || "",
  observer_auditor_user_id: schedule?.observer_auditor_user_id || "",
  assistant_auditor_user_id: schedule?.assistant_auditor_user_id || "",
  auditee_user_id: schedule?.auditee_user_id || "",
  auditee: schedule?.auditee || "",
  auditee_email: schedule?.auditee_email || "",
});

const TrendCard = React.memo(function TrendCard({ data, hasData }: { data: TrendDatum[]; hasData: boolean }) {
  return (
    <article className="qms-card qms-audit-detail__kpi-card">
      <div className="qms-audit-detail__kpi-title-row">
        <h4>Compliance Trend</h4>
        <span className="qms-audit-detail__tooltip" title="Trend Formula: monthly count of findings across this schedule.">
          <Info size={14} />
          Trend Formula Info
        </span>
      </div>
      <div className="qms-audit-detail__trend-wrap">
        <ResponsiveContainer width="100%" height={190}>
          <BarChart data={data}>
            <CartesianGrid strokeDasharray="3 3" stroke="var(--border-subtle)" opacity={0.35} />
            <XAxis dataKey="label" tick={{ fill: "var(--text-secondary)", fontSize: 11 }} />
            <YAxis allowDecimals={false} tick={{ fill: "var(--text-secondary)", fontSize: 11 }} />
            <Tooltip />
            <Bar
              dataKey="value"
              fill={hasData ? "var(--accent-primary)" : "var(--text-muted)"}
              opacity={hasData ? 0.9 : 0.2}
              radius={[8, 8, 0, 0]}
            />
          </BarChart>
        </ResponsiveContainer>
        {!hasData ? (
          <div className="qms-audit-detail__trend-empty-copy">
            <strong>No trend data yet. Complete first audit to generate insights.</strong>
          </div>
        ) : null}
      </div>
    </article>
  );
});

const FindingsTable = React.memo(function FindingsTable({
  filteredRows,
  selectedFindingId,
  openFinding,
  onAddFirstFinding,
}: {
  filteredRows: FindingRow[];
  selectedFindingId: string | null;
  openFinding: (findingId: string) => void;
  onAddFirstFinding: () => void;
}) {
  if (filteredRows.length === 0) {
    return (
      <div className="qms-audit-detail__empty-findings">
        <ClipboardList size={30} />
        <h4>No findings recorded</h4>
        <p>No findings match your current schedule and filter criteria.</p>
        <button type="button" className="btn" onClick={onAddFirstFinding}>+ Add First Finding</button>
      </div>
    );
  }

  return (
    <div className="qms-audit-detail__table-wrap">
      <table className="table table--wrap">
        <thead>
          <tr>
            <th>ID</th>
            <th>Clause (KCAR / ISO)</th>
            <th>Severity</th>
            <th>Status</th>
            <th>Closed Date</th>
          </tr>
        </thead>
        <tbody>
          {filteredRows.map((row) => {
            const active = selectedFindingId === row.finding.id;
            const status = asStatus(row.finding);
            return (
              <tr
                key={row.finding.id}
                className={active ? "qms-row--active qms-table__row" : "qms-table__row"}
                onClick={() => openFinding(row.finding.id)}
                onKeyDown={(event) => {
                  if (event.key === "Enter" || event.key === " ") {
                    event.preventDefault();
                    openFinding(row.finding.id);
                  }
                }}
                tabIndex={0}
                role="button"
              >
                <td>{row.finding.finding_ref ?? row.finding.id.slice(0, 8)}</td>
                <td><code>{row.finding.requirement_ref ?? "N/A"}</code></td>
                <td><span className="qms-pill">{findingLevelLabel(row.finding.level)}</span></td>
                <td><span className={statusClassName(status)}>{status}</span></td>
                <td>{row.finding.closed_at ? new Date(row.finding.closed_at).toLocaleDateString() : "—"}</td>
              </tr>
            );
          })}
        </tbody>
      </table>
    </div>
  );
});

const AuditDetailView: React.FC<Props> = ({ amoCode, department, scheduleId }) => {
  const navigate = useNavigate();
  const queryClient = useQueryClient();
  const [searchParams, setSearchParams] = useSearchParams();
  const [editingParticipants, setEditingParticipants] = useState(false);
  const [participantForm, setParticipantForm] = useState<ParticipantFormState>(participantFormFromSchedule(null));
  const [participantMessage, setParticipantMessage] = useState<string | null>(null);
  const rawWorkspaceTab = searchParams.get("tab");
  const activeTab: WorkspaceTab = rawWorkspaceTab === "checklists" || rawWorkspaceTab === "documents" ? rawWorkspaceTab : "findings";
  const severityFilter = searchParams.get("severity") || "ALL";
  const statusFilter = searchParams.get("status") || "ALL";
  const findingSearch = searchParams.get("q") || "";
  const selectedFindingId = searchParams.get("findingId");

  const schedulesQuery = useQuery({
    queryKey: ["qms-audit-schedules", amoCode],
    queryFn: () => qmsListAuditSchedules({ domain: "AMO", active: true }, { silent: true }),
    staleTime: 60_000,
  });

  const personnelQuery = useQuery({
    queryKey: ["qms-audit-personnel-options", amoCode],
    queryFn: () => qmsListAuditPersonnelOptions({ limit: 150 }),
    staleTime: 5 * 60_000,
  });

  const peopleById = useMemo(() => {
    const next = new Map<string, QMSPersonOption>();
    (personnelQuery.data ?? []).forEach((person) => next.set(person.id, person));
    return next;
  }, [personnelQuery.data]);

  const auditsQuery = useQuery({
    queryKey: ["qms-audits", "schedule-detail", amoCode],
    queryFn: () => qmsListAudits({ domain: "AMO", limit: 300 }, { silent: true }),
    staleTime: 60_000,
  });

  const dashboardQuery = useQuery({
    queryKey: ["qms-dashboard", "schedule-detail", amoCode],
    queryFn: () => qmsGetDashboard({ domain: "AMO" }),
    staleTime: 60_000,
  });

  const schedule = useMemo(
    () => (schedulesQuery.data ?? []).find((row) => row.id === scheduleId) ?? null,
    [scheduleId, schedulesQuery.data]
  );

  useEffect(() => {
    setParticipantForm(participantFormFromSchedule(schedule));
    setEditingParticipants(false);
    setParticipantMessage(null);
  }, [schedule?.id]);

  const participantUpdate = useMutation({
    mutationFn: async () => qmsUpdateAuditSchedule(scheduleId, {
      lead_auditor_user_id: participantForm.lead_auditor_user_id || null,
      observer_auditor_user_id: participantForm.observer_auditor_user_id || null,
      assistant_auditor_user_id: participantForm.assistant_auditor_user_id || null,
      auditee_user_id: schedule?.kind === "INTERNAL" ? participantForm.auditee_user_id || null : null,
      auditee: participantForm.auditee || null,
      auditee_email: participantForm.auditee_email || null,
    }),
    onSuccess: async () => {
      setParticipantMessage("Audit team and auditee details updated.");
      setEditingParticipants(false);
      await queryClient.invalidateQueries({ queryKey: ["qms-audit-schedules", amoCode] });
    },
    onError: (error: Error) => {
      setParticipantMessage(error.message || "Unable to update participants.");
    },
  });

  const scheduleAudits = useMemo(() => {
    const all = auditsQuery.data ?? [];
    if (!schedule) return [];
    const byTitle = all.filter((audit) => audit.title.trim().toLowerCase() === schedule.title.trim().toLowerCase());
    if (byTitle.length > 0) return byTitle;
    return all.filter((audit) => audit.kind === schedule.kind);
  }, [auditsQuery.data, schedule]);

  const carsQuery = useQuery({
    queryKey: ["qms-cars", "schedule-detail", amoCode],
    queryFn: async () => {
      if (scheduleAudits.length === 0) return [];
      const batches = await Promise.all(
        scheduleAudits.map((audit) => qmsListCars({ audit_id: audit.id, limit: 200 }, { silent: true }))
      );
      return batches.flat();
    },
    enabled: scheduleAudits.length > 0,
    staleTime: 60_000,
  });

  const findingsQueries = useQuery({
    queryKey: ["qms-findings", "schedule-detail", amoCode, scheduleId, scheduleAudits.map((item) => item.id).join(",")],
    queryFn: async () => {
      const auditIds = scheduleAudits.map((audit) => audit.id);
      const findings = await qmsListFindingsBulk({ domain: "AMO", audit_ids: auditIds, limit: 500 }, { silent: true });
      const findingsByAudit = new Map<string, QMSFindingOut[]>();
      findings.forEach((finding) => {
        const bucket = findingsByAudit.get(finding.audit_id) ?? [];
        bucket.push(finding);
        findingsByAudit.set(finding.audit_id, bucket);
      });
      return scheduleAudits.map((audit) => ({
        audit,
        findings: findingsByAudit.get(audit.id) ?? [],
      }));
    },
    enabled: scheduleAudits.length > 0,
    staleTime: 60_000,
  });

  const findingRows = useMemo<FindingRow[]>(() => {
    const carsByFinding = new Map<string, CAROut>();
    (carsQuery.data ?? []).forEach((car) => {
      if (car.finding_id && !carsByFinding.has(car.finding_id)) {
        carsByFinding.set(car.finding_id, car);
      }
    });

    return (findingsQueries.data ?? []).flatMap(({ audit, findings }) =>
      findings.map((finding) => ({
        finding,
        audit,
        linkedCar: carsByFinding.get(finding.id) ?? null,
      }))
    );
  }, [carsQuery.data, findingsQueries.data]);

  const filteredRows = useMemo(() => {
    const q = findingSearch.trim().toLowerCase();
    return findingRows
      .filter((row) => severityFilter === "ALL" || row.finding.level === severityFilter)
      .filter((row) => statusFilter === "ALL" || asStatus(row.finding) === statusFilter)
      .filter((row) => {
        if (!q) return true;
        return [row.finding.finding_ref, row.finding.requirement_ref, row.finding.description]
          .filter(Boolean)
          .join(" ")
          .toLowerCase()
          .includes(q);
      })
      .sort((a, b) => b.finding.created_at.localeCompare(a.finding.created_at));
  }, [findingRows, severityFilter, statusFilter, findingSearch]);

  const selectedRow = useMemo(
    () => findingRows.find((row) => row.finding.id === selectedFindingId) ?? null,
    [findingRows, selectedFindingId]
  );

  const [tick, setTick] = useState(Date.now());
  useEffect(() => { const id = window.setInterval(() => setTick(Date.now()), 60_000); return () => window.clearInterval(id); }, []);

  const upcomingAudit = useMemo(
    () => selectRelevantDueAudit(scheduleAudits, new Date(tick)) ?? scheduleAudits[0] ?? null,
    [scheduleAudits, tick],
  );

  const trendData = useMemo<TrendDatum[]>(() => {
    const grouped = new Map<string, number>();
    findingRows.forEach((row) => {
      const key = row.finding.created_at.slice(0, 7);
      grouped.set(key, (grouped.get(key) ?? 0) + 1);
    });
    if (grouped.size === 0) {
      return [];
    }
    return Array.from(grouped.entries())
      .sort(([a], [b]) => a.localeCompare(b))
      .slice(-6)
      .map(([label, value]) => ({ label: label.slice(5), value }));
  }, [findingRows]);

  const [clockMs, setClockMs] = useState(Date.now());
  useEffect(() => { const id = window.setInterval(() => setClockMs(Date.now()), 60_000); return () => window.clearInterval(id); }, []);
  const readiness = schedule ? computeReadiness(schedule, upcomingAudit) : null;
  const dueBanner = getDueMessage(new Date(clockMs), schedule?.next_due_date, upcomingAudit?.planned_start, upcomingAudit?.planned_end);
  const brand = getBrandContext();
  const dashboard = dashboardQuery.data;
  const risk = riskTone(dashboard?.findings_open_level_1 ?? 0, dashboard?.findings_open_level_2 ?? 0);

  const setFilter = (key: string, value: string) => {
    const next = new URLSearchParams(searchParams);
    if (!value || value === "ALL") next.delete(key);
    else next.set(key, value);
    setSearchParams(next);
  };

  const setTab = (tab: WorkspaceTab) => {
    const next = new URLSearchParams(searchParams);
    next.set("tab", tab);
    setSearchParams(next);
  };

  const openFinding = (findingId: string) => {
    const next = new URLSearchParams(searchParams);
    next.set("findingId", findingId);
    setSearchParams(next);
  };

  const closeFinding = () => {
    const next = new URLSearchParams(searchParams);
    next.delete("findingId");
    setSearchParams(next);
  };

  const clearFilters = () => {
    const next = new URLSearchParams(searchParams);
    next.delete("severity");
    next.delete("status");
    next.delete("q");
    setSearchParams(next);
  };

  const baseQmsPath = `/maintenance/${amoCode}/quality`;
  const goToRegister = () => navigate(`${baseQmsPath}/audits/register`);
  const goToEvidence = () => navigate(`${baseQmsPath}/evidence`);
  const personnelOptions = personnelQuery.data ?? [];
  const setParticipantField = (field: keyof ParticipantFormState, value: string) => setParticipantForm((prev) => ({ ...prev, [field]: value }));
  const cancelParticipantEdit = () => {
    setParticipantForm(participantFormFromSchedule(schedule));
    setEditingParticipants(false);
    setParticipantMessage(null);
  };
  const participantSelect = (field: keyof ParticipantFormState, label: string, value: string) => (
    <label className="qms-audit-detail__team-edit-field">
      <span>{label}</span>
      <select value={value} onChange={(event) => setParticipantField(field, event.target.value)}>
        <option value="">Unassigned</option>
        {personnelOptions.map((person) => <option key={person.id} value={person.id}>{person.full_name}{person.position_title ? ` · ${person.position_title}` : ""}</option>)}
      </select>
    </label>
  );

  if (!schedule && !schedulesQuery.isLoading) {
    return (
      <div className="qms-card">
        <h3>Schedule not found</h3>
        <p>The schedule is missing, inactive, or outside your AMO scope.</p>
        <button type="button" className="secondary-chip-btn" onClick={() => navigate(`/maintenance/${amoCode}/quality/audits/plan?view=list`)}>
          Back to list
        </button>
      </div>
    );
  }

  return (
    <div className="qms-audit-detail">
      {dueBanner ? (
        <section className="qms-card" style={{ marginBottom: 12 }}>
          <strong>{dueBanner.label}</strong>
          <div className="text-muted">
            Next due: {schedule?.next_due_date || "—"} · Upcoming notice: {upcomingAudit?.upcoming_notice_sent_at || "—"} · Day-of notice: {upcomingAudit?.day_of_notice_sent_at || "—"}
          </div>
        </section>
      ) : null}

      <section className="qms-card qms-audit-detail__hero">
        <div className="qms-audit-detail__breadcrumb">Audits &gt; {brand.name || amoCode} &gt; {schedule?.title || "Schedule"}</div>
        <div className="qms-audit-detail__hero-grid">
          <div>
            <h1 className="qms-audit-detail__title">Schedule Detail</h1>
            <h2 className="qms-audit-detail__audit-name">{schedule?.title || "Loading audit..."}</h2>
          </div>
          <div className="qms-audit-detail__hero-actions">
            <span className="qms-pill qms-pill--info">{upcomingAudit?.status || "PLANNED"}</span>
            <div
              className="qms-segmented"
              role="tablist"
              aria-label="Audit route tabs"
              style={{ "--segment-count": 3, "--segment-active-index": 0 } as React.CSSProperties}
            >
              <button type="button" className="is-active" onClick={() => navigate(`${baseQmsPath}/audits/plan?view=calendar`)}>Plan</button>
              <button type="button" onClick={goToRegister}>Register</button>
              <button type="button" onClick={goToEvidence}>Evidence</button>
            </div>
          </div>
        </div>

        <div className="qms-audit-detail__kpi-grid">
          <article className="qms-card qms-audit-detail__kpi-card">
            <h4>Preparation Status</h4>
            <div className="qms-audit-detail__prep-bar">
              <span style={{ width: `${readiness?.score ?? 0}%` }} />
            </div>
            <div className="qms-audit-detail__prep-meta">Steps Complete: {Math.round(((readiness?.score ?? 0) / 100) * 5)} of 5</div>
            <small>{readiness?.label ?? "Loading"}</small>
            <button type="button" className="btn qms-audit-detail__prep-cta">Start Preparation Steps</button>
          </article>

          <article className="qms-card qms-audit-detail__kpi-card qms-audit-detail__team-card">
            <div className="qms-audit-detail__team-head">
              <div>
                <h4>Audit team and auditee</h4>
                <small>{brand.name || amoCode} · {schedule?.frequency?.replaceAll("_", " ") || "No cadence"}</small>
              </div>
              {editingParticipants ? (
                <div className="qms-audit-detail__team-actions">
                  <button type="button" className="secondary-chip-btn" onClick={cancelParticipantEdit}><X size={13} /> Cancel</button>
                  <button type="button" className="btn btn--sm" onClick={() => participantUpdate.mutate()} disabled={participantUpdate.isPending}><Save size={13} /> Save</button>
                </div>
              ) : (
                <button type="button" className="secondary-chip-btn" onClick={() => setEditingParticipants(true)}><Pencil size={13} /> Edit team</button>
              )}
            </div>
            {participantMessage ? <p className="qms-audit-detail__team-message">{participantMessage}</p> : null}
            {editingParticipants ? (
              <div className="qms-audit-detail__team-editor">
                {participantSelect("lead_auditor_user_id", "Lead auditor", participantForm.lead_auditor_user_id)}
                {participantSelect("observer_auditor_user_id", "Observer auditor", participantForm.observer_auditor_user_id)}
                {participantSelect("assistant_auditor_user_id", "Assistant auditor", participantForm.assistant_auditor_user_id)}
                {schedule?.kind === "INTERNAL" ? participantSelect("auditee_user_id", "Internal auditee", participantForm.auditee_user_id) : null}
                <label className="qms-audit-detail__team-edit-field">
                  <span>Auditee label</span>
                  <input value={participantForm.auditee} onChange={(event) => setParticipantField("auditee", event.target.value)} placeholder="Department, contact name or external organisation" />
                </label>
                <label className="qms-audit-detail__team-edit-field">
                  <span>Auditee email</span>
                  <input type="email" value={participantForm.auditee_email} onChange={(event) => setParticipantField("auditee_email", event.target.value)} placeholder="name@example.com" />
                </label>
              </div>
            ) : (
              <div className="qms-audit-detail__team-list">
                <div><span>Lead auditor</span><strong>{personName(peopleById, schedule?.lead_auditor_user_id)}</strong></div>
                <div><span>Observer</span><strong>{personName(peopleById, schedule?.observer_auditor_user_id)}</strong></div>
                <div><span>Assistant</span><strong>{personName(peopleById, schedule?.assistant_auditor_user_id)}</strong></div>
                <div><span>Auditee</span><strong>{schedule?.kind === "INTERNAL" ? personName(peopleById, schedule?.auditee_user_id) : schedule?.auditee || "Unassigned"}</strong></div>
                <div><span>Auditee email</span><strong>{schedule?.auditee_email || "Not set"}</strong></div>
                <div><span>Risk summary</span><strong><span className={risk.className}>{risk.label}</span></strong></div>
              </div>
            )}
          </article>

          <TrendCard data={trendData} hasData={findingRows.length > 0} />
        </div>
      </section>

      <section className="qms-card">
        <div className="qms-audit-detail__workspace-tabs" role="tablist" aria-label="Audit detail workspace tabs">
          <button type="button" className={activeTab === "findings" ? "is-active" : ""} onClick={() => setTab("findings")}>Findings</button>
          <button type="button" className={activeTab === "checklists" ? "is-active" : ""} onClick={() => setTab("checklists")}>Checklists</button>
          <button type="button" className={activeTab === "documents" ? "is-active" : ""} onClick={() => setTab("documents")}>Document Library</button>
        </div>

        {activeTab === "findings" ? (
          <>
            <div className="qms-audit-detail__control-bar" style={{ marginTop: 12 }}>
              <label className="qms-audit-detail__search">
                <Search size={14} />
                <input
                  value={findingSearch}
                  onChange={(e) => setFilter("q", e.target.value)}
                  placeholder="Search findings, clause or description"
                />
              </label>
              <label className="qms-pill">Severity
                <select value={severityFilter} onChange={(e) => setFilter("severity", e.target.value)}>
                  <option value="ALL">All</option>
                  <option value="LEVEL_1">Level 1 · Critical</option>
                  <option value="LEVEL_2">Level 2 · Major</option>
                  <option value="LEVEL_3">Level 3 · Minor</option>
                  <option value="LEVEL_4">Observations</option>
                </select>
              </label>
              <label className="qms-pill">Status
                <select value={statusFilter} onChange={(e) => setFilter("status", e.target.value)}>
                  <option value="ALL">All</option>
                  <option value="Open">Open</option>
                  <option value="Closed">Closed</option>
                  <option value="Overdue">Overdue</option>
                </select>
              </label>
              <button type="button" className="secondary-chip-btn" onClick={clearFilters}>Clear filters</button>
            </div>
            <p className="qms-audit-detail__results-meta">{filteredRows.length} finding(s) shown</p>

            {findingsQueries.isLoading ? <div className="qms-skeleton-row"><div /><div /><div /><div /></div> : null}
            {findingsQueries.isError ? <p className="text-danger">Failed to load findings.</p> : null}
            {!findingsQueries.isLoading ? (
              <FindingsTable
                filteredRows={filteredRows}
                selectedFindingId={selectedFindingId}
                openFinding={openFinding}
                onAddFirstFinding={() => navigate(`${baseQmsPath}/audits/register?tab=findings`)}
              />
            ) : null}
          </>
        ) : activeTab === "checklists" ? (
          <div style={{ marginTop: 12 }}>
            <p><strong>{upcomingAudit?.checklist_file_ref ? "Checklist attached" : "No checklist attached yet"}</strong></p>
            {upcomingAudit ? <button type="button" className="secondary-chip-btn" onClick={() => navigate(`${baseQmsPath}/audits/${upcomingAudit.id}`)}>Open Run Hub</button> : null}
          </div>
        ) : (
          <div style={{ marginTop: 12 }}>
            <p>Review all reports/checklists and CAR attachments in the evidence library.</p>
            <button type="button" className="secondary-chip-btn" onClick={() => navigate(`${baseQmsPath}/evidence`)}>
              Open Document Library
            </button>
          </div>
        )}
      </section>

      <FindingDrawer
        isOpen={!!selectedFindingId}
        amoCode={amoCode}
        department={department}
        finding={selectedRow?.finding ?? null}
        linkedCar={selectedRow?.linkedCar ?? null}
        onClose={closeFinding}
      />
    </div>
  );
};

export default AuditDetailView;
