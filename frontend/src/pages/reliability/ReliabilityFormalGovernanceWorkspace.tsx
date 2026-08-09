import React, { useEffect, useMemo, useState } from "react";

import { listFormalProfiles, listFormalReports, type FormalPeriodType, type FormalProfile, type FormalReport } from "./reliabilityFormalReportingApi";
import {
  createAmpRecommendation,
  createReportingSchedule,
  createSupersedingRevision,
  distributeReport,
  listAmpRecommendations,
  listDistribution,
  listReportingSchedule,
  transitionAmpRecommendation,
  updateReportingSchedule,
  type AmpRecommendation,
  type AmpRecommendationStatus,
  type FormalDistribution,
  type ReportingSchedule,
  type ReportingScheduleStatus,
} from "./reliabilityFormalGovernanceApi";
import "./ReliabilityFormalGovernanceWorkspace.css";

const PERIODS: FormalPeriodType[] = ["MONTHLY", "QUARTERLY", "HALF_YEAR", "ANNUAL", "YEAR_TO_DATE", "ROLLING_3_MONTH", "ROLLING_6_MONTH", "ROLLING_12_MONTH", "CUSTOM"];
const SCHEDULE_STATES: ReportingScheduleStatus[] = ["PLANNED", "DUE", "IN_PREPARATION", "IN_REVIEW", "COMPLETE", "CANCELLED"];
const AMP_FLOW: AmpRecommendationStatus[] = [
  "IDENTIFIED", "ANALYSIS", "RECOMMENDED", "TECHNICAL_REVIEW", "QUALITY_REVIEW",
  "AUTHORITY_APPROVAL_REQUIRED", "APPROVED", "IMPLEMENTED", "EFFECTIVENESS_MONITORING", "CLOSED",
];
const AMP_CHANGE_TYPES = [
  "TASK_ESCALATION", "TASK_DE_ESCALATION", "INTERVAL_CHANGE", "INSPECTION_CHANGE", "ADDITIONAL_TASK",
  "REMOVE_INEFFECTIVE_TASK", "ENHANCED_INSPECTION", "REPETITIVE_MONITORING", "COMPONENT_PROGRAMME_CHANGE", "ENGINEERING_INVESTIGATION",
];

function nowYear(): number {
  return new Date().getFullYear();
}

function initialPeriod() {
  const year = nowYear();
  return { start: `${year}-01-01`, end: `${year}-06-30`, due: `${year}-07-31` };
}

function safeJson(value: string, label: string): Record<string, unknown> {
  const trimmed = value.trim();
  if (!trimmed) return {};
  const parsed = JSON.parse(trimmed) as unknown;
  if (!parsed || Array.isArray(parsed) || typeof parsed !== "object") throw new Error(`${label} must be a JSON object.`);
  return parsed as Record<string, unknown>;
}

function tone(status: string): string {
  if (["COMPLETE", "CLOSED", "APPROVED", "PUBLISHED"].includes(status)) return "good";
  if (["OVERDUE", "CANCELLED", "WITHDRAWN"].includes(status)) return "bad";
  if (["SUPERSEDED"].includes(status)) return "muted";
  return "active";
}

const ReliabilityFormalGovernanceWorkspace: React.FC = () => {
  const defaults = useMemo(initialPeriod, []);
  const [profiles, setProfiles] = useState<FormalProfile[]>([]);
  const [reports, setReports] = useState<FormalReport[]>([]);
  const [schedule, setSchedule] = useState<ReportingSchedule[]>([]);
  const [amp, setAmp] = useState<AmpRecommendation[]>([]);
  const [distribution, setDistribution] = useState<FormalDistribution[]>([]);
  const [selectedReportId, setSelectedReportId] = useState("");
  const [busy, setBusy] = useState(false);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState("");
  const [message, setMessage] = useState("");

  const [scheduleProfile, setScheduleProfile] = useState("");
  const [scheduleCode, setScheduleCode] = useState("REL-HALF-YEAR");
  const [scheduleName, setScheduleName] = useState("Half-year Reliability Programme review");
  const [schedulePeriodType, setSchedulePeriodType] = useState<FormalPeriodType>("HALF_YEAR");
  const [scheduleStart, setScheduleStart] = useState(defaults.start);
  const [scheduleEnd, setScheduleEnd] = useState(defaults.end);
  const [scheduleDue, setScheduleDue] = useState(defaults.due);

  const [ampTitle, setAmpTitle] = useState("");
  const [ampSummary, setAmpSummary] = useState("");
  const [ampType, setAmpType] = useState("ENGINEERING_INVESTIGATION");
  const [ampEvidence, setAmpEvidence] = useState("FORMAL_REPORT");
  const [ampProposal, setAmpProposal] = useState("{}");
  const [ampBasis, setAmpBasis] = useState("{}");
  const [ampAuthority, setAmpAuthority] = useState(false);

  const [recipientRole, setRecipientRole] = useState("QUALITY_MANAGER");
  const [externalRecipient, setExternalRecipient] = useState("");

  const selectedReport = reports.find((item) => item.id === selectedReportId) || null;
  const distributableReports = reports.filter((item) => item.status === "PUBLISHED");

  async function loadAll(preferredReport?: string) {
    const [profileRows, reportPayload, scheduleRows, ampRows] = await Promise.all([
      listFormalProfiles(),
      listFormalReports(250),
      listReportingSchedule(),
      listAmpRecommendations(),
    ]);
    setProfiles(profileRows);
    setReports(reportPayload.reports);
    setSchedule(scheduleRows);
    setAmp(ampRows);
    setScheduleProfile((current) => current || profileRows[0]?.id || "");
    const nextReport = preferredReport || selectedReportId || distributableReports[0]?.id || reportPayload.reports.find((item) => item.status === "PUBLISHED")?.id || reportPayload.reports[0]?.id || "";
    setSelectedReportId(nextReport);
    if (nextReport) {
      try {
        setDistribution(await listDistribution(nextReport));
      } catch {
        setDistribution([]);
      }
    } else {
      setDistribution([]);
    }
  }

  useEffect(() => {
    let active = true;
    void (async () => {
      try {
        setLoading(true);
        await loadAll();
      } catch (cause) {
        if (active) setError(cause instanceof Error ? cause.message : "Unable to load Reliability governance.");
      } finally {
        if (active) setLoading(false);
      }
    })();
    return () => { active = false; };
    // Initial controlled load only; subsequent refreshes are explicit.
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  useEffect(() => {
    if (!selectedReportId) {
      setDistribution([]);
      return;
    }
    let active = true;
    void listDistribution(selectedReportId)
      .then((rows) => { if (active) setDistribution(rows); })
      .catch(() => { if (active) setDistribution([]); });
    return () => { active = false; };
  }, [selectedReportId]);

  async function perform(label: string, action: () => Promise<void>) {
    setBusy(true);
    setError("");
    setMessage("");
    try {
      await action();
      setMessage(label);
    } catch (cause) {
      setError(cause instanceof Error ? cause.message : "Controlled governance action failed.");
    } finally {
      setBusy(false);
    }
  }

  async function onCreateSchedule(event: React.FormEvent) {
    event.preventDefault();
    await perform("Reporting obligation created.", async () => {
      await createReportingSchedule({
        profile_id: scheduleProfile || null,
        obligation_code: scheduleCode.trim(),
        name: scheduleName.trim(),
        period_type: schedulePeriodType,
        period_start: scheduleStart,
        period_end: scheduleEnd,
        due_date: scheduleDue,
      });
      setSchedule(await listReportingSchedule());
    });
  }

  async function onScheduleStatus(row: ReportingSchedule, status: ReportingScheduleStatus) {
    await perform(`Reporting obligation moved to ${status}.`, async () => {
      await updateReportingSchedule(row.id, status, row.report_id);
      setSchedule(await listReportingSchedule());
    });
  }

  async function onCreateAmp(event: React.FormEvent) {
    event.preventDefault();
    await perform("AMP recommendation entered into governed change control.", async () => {
      const proposedChange = safeJson(ampProposal, "Proposed change");
      if (Object.keys(proposedChange).length === 0) throw new Error("Proposed change cannot be empty.");
      await createAmpRecommendation({
        report_id: selectedReportId || null,
        title: ampTitle.trim(),
        summary: ampSummary.trim(),
        change_type: ampType,
        source_evidence: [{ kind: ampEvidence.trim() || "FORMAL_REPORT", report_id: selectedReportId || null }],
        proposed_change: proposedChange,
        technical_basis: safeJson(ampBasis, "Technical basis"),
        authority_approval_required: ampAuthority,
      });
      setAmp(await listAmpRecommendations());
      setAmpTitle("");
      setAmpSummary("");
      setAmpProposal("{}");
      setAmpBasis("{}");
    });
  }

  async function advanceAmp(row: AmpRecommendation) {
    const index = AMP_FLOW.indexOf(row.status);
    const next = AMP_FLOW[index + 1];
    if (!next) return;
    await perform(`AMP recommendation advanced to ${next}.`, async () => {
      await transitionAmpRecommendation(row.id, next, `Advanced through Reliability Programme governance to ${next}.`);
      setAmp(await listAmpRecommendations());
    });
  }

  async function onSupersedingRevision(row: FormalReport) {
    await perform("Superseding draft revision created and linked to the published evidence chain.", async () => {
      const created = await createSupersedingRevision(row.id);
      await loadAll(created.id);
    });
  }

  async function onDistribute(event: React.FormEvent) {
    event.preventDefault();
    if (!selectedReport || selectedReport.status !== "PUBLISHED") {
      setError("Select the current PUBLISHED revision before distribution.");
      return;
    }
    await perform("Controlled portal distribution recorded.", async () => {
      await distributeReport(selectedReport.id, {
        recipient_role: recipientRole.trim() || null,
        external_recipient_ref: externalRecipient.trim() || null,
      });
      setDistribution(await listDistribution(selectedReport.id));
      setExternalRecipient("");
    });
  }

  if (loading) return <div className="rfg-loading" role="status">Loading Reliability Programme governance…</div>;

  return (
    <main className="rfg-shell" data-testid="reliability-formal-governance">
      <header className="rfg-header">
        <div>
          <p className="rfg-eyebrow">Reliability Programme</p>
          <h1>Governance & publication control</h1>
          <p>Plan reporting obligations, control AMP recommendations, create superseding revisions and retain distribution evidence.</p>
        </div>
        <button type="button" onClick={() => void perform("Governance registers refreshed.", () => loadAll())} disabled={busy}>Refresh registers</button>
      </header>

      {(error || message) && <div className={`rfg-banner ${error ? "error" : "success"}`} role={error ? "alert" : "status"}>{error || message}</div>}

      <section className="rfg-panel" aria-labelledby="rfg-schedule-title">
        <div className="rfg-panel-head"><div><p className="rfg-eyebrow">Calendar</p><h2 id="rfg-schedule-title">Reporting obligations</h2></div><span>{schedule.length}</span></div>
        <form className="rfg-form rfg-form--schedule" onSubmit={onCreateSchedule}>
          <label>Profile<select value={scheduleProfile} onChange={(event) => setScheduleProfile(event.target.value)} disabled={busy}>{profiles.map((profile) => <option key={profile.id} value={profile.id}>{profile.code} · {profile.version}</option>)}</select></label>
          <label>Obligation code<input value={scheduleCode} onChange={(event) => setScheduleCode(event.target.value)} required disabled={busy} /></label>
          <label>Name<input value={scheduleName} onChange={(event) => setScheduleName(event.target.value)} required disabled={busy} /></label>
          <label>Period type<select value={schedulePeriodType} onChange={(event) => setSchedulePeriodType(event.target.value as FormalPeriodType)}>{PERIODS.map((item) => <option key={item}>{item}</option>)}</select></label>
          <label>Start<input type="date" value={scheduleStart} onChange={(event) => setScheduleStart(event.target.value)} required /></label>
          <label>End<input type="date" value={scheduleEnd} onChange={(event) => setScheduleEnd(event.target.value)} required /></label>
          <label>Due<input type="date" value={scheduleDue} onChange={(event) => setScheduleDue(event.target.value)} required /></label>
          <button type="submit" className="rfg-primary" disabled={busy}>Add obligation</button>
        </form>
        <div className="rfg-table-wrap"><table><thead><tr><th>Obligation</th><th>Period</th><th>Due</th><th>State</th><th>Linked report</th><th>Control</th></tr></thead><tbody>
          {schedule.map((row) => <tr key={row.id}><td><strong>{row.obligation_code}</strong><small>{row.name}</small></td><td>{row.period_start}<br />{row.period_end}</td><td>{row.due_date}</td><td><span className={`rfg-chip ${tone(row.effective_status)}`}>{row.effective_status}</span></td><td>{row.report_id || "—"}</td><td><select aria-label={`Status for ${row.obligation_code}`} value={row.status} onChange={(event) => void onScheduleStatus(row, event.target.value as ReportingScheduleStatus)} disabled={busy}>{SCHEDULE_STATES.map((state) => <option key={state}>{state}</option>)}</select></td></tr>)}
          {schedule.length === 0 && <tr><td colSpan={6}>No reporting obligations configured.</td></tr>}
        </tbody></table></div>
      </section>

      <section className="rfg-panel" aria-labelledby="rfg-amp-title">
        <div className="rfg-panel-head"><div><p className="rfg-eyebrow">Maintenance programme</p><h2 id="rfg-amp-title">AMP recommendations</h2></div><span>{amp.length}</span></div>
        <form className="rfg-form" onSubmit={onCreateAmp}>
          <label>Source report<select value={selectedReportId} onChange={(event) => setSelectedReportId(event.target.value)}><option value="">Unlinked recommendation</option>{reports.map((item) => <option key={item.id} value={item.id}>{item.report_number} · Rev {item.revision} · {item.status}</option>)}</select></label>
          <label>Change type<select value={ampType} onChange={(event) => setAmpType(event.target.value)}>{AMP_CHANGE_TYPES.map((item) => <option key={item}>{item}</option>)}</select></label>
          <label>Title<input value={ampTitle} onChange={(event) => setAmpTitle(event.target.value)} required minLength={3} /></label>
          <label className="rfg-span-2">Engineering summary<textarea value={ampSummary} onChange={(event) => setAmpSummary(event.target.value)} required minLength={10} rows={3} /></label>
          <label>Evidence kind<input value={ampEvidence} onChange={(event) => setAmpEvidence(event.target.value)} /></label>
          <label>Proposed change JSON<textarea value={ampProposal} onChange={(event) => setAmpProposal(event.target.value)} rows={3} /></label>
          <label>Technical basis JSON<textarea value={ampBasis} onChange={(event) => setAmpBasis(event.target.value)} rows={3} /></label>
          <label className="rfg-check"><input type="checkbox" checked={ampAuthority} onChange={(event) => setAmpAuthority(event.target.checked)} /> Authority approval required</label>
          <button type="submit" className="rfg-primary" disabled={busy}>Create governed recommendation</button>
        </form>
        <div className="rfg-cards">{amp.map((row) => {
          const index = AMP_FLOW.indexOf(row.status); const next = AMP_FLOW[index + 1];
          return <article key={row.id} className="rfg-card"><div><strong>{row.title}</strong><span className={`rfg-chip ${tone(row.status)}`}>{row.status}</span></div><p>{row.summary}</p><small>{row.change_type}{row.authority_approval_required ? " · authority approval flagged" : ""}</small>{next && <button type="button" onClick={() => void advanceAmp(row)} disabled={busy}>Advance to {next.replaceAll("_", " ")}</button>}</article>;
        })}{amp.length === 0 && <p>No AMP recommendations recorded.</p>}</div>
      </section>

      <section className="rfg-panel" aria-labelledby="rfg-publication-title">
        <div className="rfg-panel-head"><div><p className="rfg-eyebrow">Controlled copies</p><h2 id="rfg-publication-title">Publication chain & distribution</h2></div></div>
        <div className="rfg-publication-grid">
          <div>
            <h3>Published revisions</h3>
            <div className="rfg-cards">{distributableReports.map((row) => <article key={row.id} className="rfg-card"><div><strong>{row.report_number} · Rev {row.revision}</strong><span className="rfg-chip good">PUBLISHED</span></div><p>{row.period_start} — {row.period_end}</p><small>PDF {row.pdf_sha256 ? `${row.pdf_sha256.slice(0, 12)}…` : "hash unavailable"}</small><div className="rfg-actions"><button type="button" onClick={() => setSelectedReportId(row.id)}>Select distribution</button><button type="button" onClick={() => void onSupersedingRevision(row)} disabled={busy}>Create superseding revision</button></div></article>)}{distributableReports.length === 0 && <p>No current published revision is available.</p>}</div>
          </div>
          <div>
            <h3>Distribution register</h3>
            <form className="rfg-form rfg-form--distribution" onSubmit={onDistribute}>
              <label>Current report<select value={selectedReportId} onChange={(event) => setSelectedReportId(event.target.value)}><option value="">Select published revision</option>{distributableReports.map((row) => <option key={row.id} value={row.id}>{row.report_number} · Rev {row.revision}</option>)}</select></label>
              <label>Recipient role<input value={recipientRole} onChange={(event) => setRecipientRole(event.target.value)} /></label>
              <label>External recipient/reference<input value={externalRecipient} onChange={(event) => setExternalRecipient(event.target.value)} placeholder="Optional authority / controlled recipient reference" /></label>
              <button type="submit" className="rfg-primary" disabled={busy || !selectedReportId}>Record distribution</button>
            </form>
            <div className="rfg-distribution">{distribution.map((row) => <div key={row.id}><strong>{row.recipient_role || row.external_recipient_ref || row.recipient_user_id || "Controlled recipient"}</strong><span>Rev {row.revision} · {new Date(row.distributed_at).toLocaleString()}</span><small>{row.report_hash.slice(0, 16)}…</small></div>)}{selectedReportId && distribution.length === 0 && <p>No distribution records for this revision.</p>}</div>
          </div>
        </div>
      </section>
    </main>
  );
};

export default ReliabilityFormalGovernanceWorkspace;
