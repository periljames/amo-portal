import React, { useEffect, useMemo, useState } from "react";
import { useQuery, useQueryClient } from "@tanstack/react-query";
import { useNavigate } from "react-router-dom";

import { hasQmsRolePermission } from "../../app/routeGuards";
import {
  downloadCarEvidencePack,
  qmsDeleteCarAttachment,
  qmsDownloadCarAttachmentBlob,
  qmsGetCarInvite,
  qmsListCarAttachments,
  qmsListCarResponses,
  qmsUploadCarAttachment,
  type CARAssignee,
  type CARAttachmentOut,
  type CARResponseOut,
} from "../../services/qms";
import {
  updateCarControlMilestone,
  updateCarDependency,
  type CarControlDependency,
  type CarControlLoop,
  type CarDependencyRisk,
  type CarDependencyStatus,
  type CarDependencyType,
} from "../../services/qmsCarControlLoop";
import { saveDownloadedFile } from "../../utils/downloads";

const DEPENDENCY_TYPES: CarDependencyType[] = ["INTERNAL", "EXTERNAL", "PROCUREMENT", "FACILITY", "RESOURCE", "SUPPLIER", "REGULATORY", "OTHER"];
const DEPENDENCY_RISKS: CarDependencyRisk[] = ["LOW", "MEDIUM", "HIGH", "CRITICAL"];
const DEPENDENCY_STATUSES: CarDependencyStatus[] = ["OPEN", "MITIGATING", "MITIGATED", "RESOLVED", "ACCEPTED_RISK", "CANCELLED"];
const COMPLETE_MILESTONE_STATUSES = new Set(["ACCEPTED", "COMPLETED", "WAIVED"]);

type DependencyDraft = {
  title: string;
  description: string;
  dependency_type: CarDependencyType;
  owner_user_id: string;
  milestone_id: string;
  due_date: string;
  risk_level: CarDependencyRisk;
  status: CarDependencyStatus;
  blocks_closure: boolean;
  mitigation_plan: string;
};

type Props = {
  amoCode: string;
  carId: string;
  control: CarControlLoop;
  assignees: CARAssignee[];
  canManage: boolean;
  onControlChange: (next: CarControlLoop) => void;
};

function humanize(value: string | null | undefined): string {
  if (!value) return "—";
  return value.replaceAll("_", " ").toLowerCase().replace(/\b\w/g, (character) => character.toUpperCase());
}

function formatDate(value: string | null | undefined): string {
  if (!value) return "—";
  const parsed = new Date(`${value.slice(0, 10)}T00:00:00Z`);
  return Number.isNaN(parsed.getTime())
    ? value
    : parsed.toLocaleDateString(undefined, { year: "numeric", month: "short", day: "2-digit" });
}

function formatDateTime(value: string | null | undefined): string {
  if (!value) return "—";
  const parsed = new Date(value);
  return Number.isNaN(parsed.getTime()) ? value : parsed.toLocaleString();
}

function formatBytes(value: number | null | undefined): string {
  if (!value || value <= 0) return "—";
  if (value < 1024) return `${value} B`;
  if (value < 1024 * 1024) return `${(value / 1024).toFixed(1)} KB`;
  return `${(value / (1024 * 1024)).toFixed(1)} MB`;
}

function assigneeName(assignees: CARAssignee[], userId: string | null | undefined): string {
  if (!userId) return "Unassigned";
  const match = assignees.find((item) => item.id === userId);
  return match?.full_name || match?.email || userId;
}

function escapeHtml(value: unknown): string {
  return String(value ?? "")
    .replaceAll("&", "&amp;")
    .replaceAll("<", "&lt;")
    .replaceAll(">", "&gt;")
    .replaceAll('"', "&quot;")
    .replaceAll("'", "&#039;");
}

function csvCell(value: unknown): string {
  const text = String(value ?? "").replaceAll('"', '""');
  return `"${text}"`;
}

function dependencyDraft(row: CarControlDependency): DependencyDraft {
  return {
    title: row.title,
    description: row.description || "",
    dependency_type: row.dependency_type,
    owner_user_id: row.owner_user_id || "",
    milestone_id: row.milestone_id || "",
    due_date: row.due_date || "",
    risk_level: row.risk_level,
    status: row.status,
    blocks_closure: row.blocks_closure,
    mitigation_plan: row.mitigation_plan || "",
  };
}

const QmsCarControlOperations: React.FC<Props> = ({ amoCode, carId, control, assignees, canManage, onControlChange }) => {
  const navigate = useNavigate();
  const queryClient = useQueryClient();
  const canViewReports = hasQmsRolePermission("qms.reports.view") || canManage;
  const [evidenceMilestoneId, setEvidenceMilestoneId] = useState("");
  const [uploadBusy, setUploadBusy] = useState(false);
  const [actionBusy, setActionBusy] = useState<string | null>(null);
  const [localMessage, setLocalMessage] = useState<string | null>(null);
  const [localError, setLocalError] = useState<string | null>(null);
  const [dependencyDrafts, setDependencyDrafts] = useState<Record<string, DependencyDraft>>({});

  const responsesQuery = useQuery({
    queryKey: ["qms-car-control-responses", carId],
    queryFn: () => qmsListCarResponses(carId, false),
    staleTime: 10_000,
  });
  const attachmentsQuery = useQuery({
    queryKey: ["qms-car-control-attachments", carId],
    queryFn: () => qmsListCarAttachments(carId),
    staleTime: 10_000,
  });
  const inviteQuery = useQuery({
    queryKey: ["qms-car-control-source", carId],
    queryFn: () => qmsGetCarInvite(carId),
    staleTime: 30_000,
  });

  useEffect(() => {
    const next: Record<string, DependencyDraft> = {};
    control.dependencies.forEach((row) => {
      next[row.id] = dependencyDraft(row);
    });
    setDependencyDrafts(next);
  }, [control.dependencies]);

  const responses = useMemo(() => responsesQuery.data ?? [], [responsesQuery.data]);
  const attachments = attachmentsQuery.data ?? [];
  const latestResponse = useMemo<CARResponseOut | null>(() => {
    const explicitlyLatest = responses.find((item) => item.is_latest);
    if (explicitlyLatest) return explicitlyLatest;
    return [...responses].sort((left, right) => right.submitted_at.localeCompare(left.submitted_at))[0] ?? null;
  }, [responses]);
  const nextMilestone = useMemo(
    () => [...control.milestones]
      .sort((left, right) => left.phase_order - right.phase_order)
      .find((item) => !COMPLETE_MILESTONE_STATUSES.has(item.status)) ?? null,
    [control.milestones],
  );
  const nextOwner = assigneeName(assignees, nextMilestone?.owner_user_id || control.profile?.accountable_owner_user_id);
  const nextDue = nextMilestone?.current_due_date || control.profile?.current_due_date || control.car.target_closure_date || control.car.due_date;

  const setDraft = (dependencyId: string, patch: Partial<DependencyDraft>) => {
    setDependencyDrafts((current) => ({
      ...current,
      [dependencyId]: { ...(current[dependencyId] || dependencyDraft(control.dependencies.find((row) => row.id === dependencyId)!)), ...patch },
    }));
  };

  const refreshAttachments = async () => {
    await queryClient.invalidateQueries({ queryKey: ["qms-car-control-attachments", carId] });
  };

  const handleUpload = async (files: FileList | null) => {
    if (!files?.length) return;
    setUploadBusy(true);
    setLocalError(null);
    setLocalMessage(null);
    try {
      const uploaded: CARAttachmentOut[] = [];
      for (const file of Array.from(files)) {
        uploaded.push(await qmsUploadCarAttachment(carId, file));
      }
      if (evidenceMilestoneId && uploaded.length) {
        const milestone = control.milestones.find((item) => item.id === evidenceMilestoneId);
        if (milestone) {
          const newRefs = uploaded.map((item) => `car-attachment:${item.id}:${item.filename}`);
          const combined = [milestone.evidence_ref, ...newRefs].filter(Boolean).join("; ").slice(0, 1024);
          const next = await updateCarControlMilestone(amoCode, carId, milestone.id, { evidence_ref: combined });
          onControlChange(next);
        }
      }
      await refreshAttachments();
      setLocalMessage(`${uploaded.length} evidence file${uploaded.length === 1 ? "" : "s"} uploaded${evidenceMilestoneId ? " and linked to the selected milestone" : ""}.`);
    } catch (error) {
      setLocalError(error instanceof Error ? error.message : "Evidence upload failed.");
    } finally {
      setUploadBusy(false);
    }
  };

  const handleDownload = async (attachment: CARAttachmentOut) => {
    setActionBusy(`download-${attachment.id}`);
    setLocalError(null);
    try {
      const blob = await qmsDownloadCarAttachmentBlob(carId, attachment.id);
      saveDownloadedFile(blob, attachment.filename);
    } catch (error) {
      setLocalError(error instanceof Error ? error.message : "Evidence download failed.");
    } finally {
      setActionBusy(null);
    }
  };

  const handleDelete = async (attachment: CARAttachmentOut) => {
    if (!window.confirm(`Remove evidence file ${attachment.filename} from the current CAR evidence set?`)) return;
    setActionBusy(`delete-${attachment.id}`);
    setLocalError(null);
    try {
      await qmsDeleteCarAttachment(carId, attachment.id);
      await refreshAttachments();
      setLocalMessage("Evidence file removed from the current CAR attachment set.");
    } catch (error) {
      setLocalError(error instanceof Error ? error.message : "Evidence removal failed.");
    } finally {
      setActionBusy(null);
    }
  };

  const handleDependencySave = async (dependencyId: string) => {
    const draft = dependencyDrafts[dependencyId];
    if (!draft) return;
    setActionBusy(`dependency-save-${dependencyId}`);
    setLocalError(null);
    setLocalMessage(null);
    try {
      const next = await updateCarDependency(amoCode, carId, dependencyId, {
        title: draft.title.trim(),
        description: draft.description.trim() || null,
        dependency_type: draft.dependency_type,
        owner_user_id: draft.owner_user_id || null,
        milestone_id: draft.milestone_id || null,
        due_date: draft.due_date || null,
        risk_level: draft.risk_level,
        status: draft.status,
        blocks_closure: draft.blocks_closure,
        mitigation_plan: draft.mitigation_plan.trim() || null,
      });
      onControlChange(next);
      setLocalMessage("Dependency controls updated.");
    } catch (error) {
      setLocalError(error instanceof Error ? error.message : "Dependency update failed.");
    } finally {
      setActionBusy(null);
    }
  };

  const buildCsv = (): string => {
    const source = inviteQuery.data;
    const generated = new Date().toISOString();
    const rows: Array<[string, string, string]> = [
      ["Package", "Generated at", generated],
      ["CAR", "Reference", control.car.car_number],
      ["CAR", "Title", control.car.title],
      ["CAR", "Status", control.car.status],
      ["CAR", "Priority", control.car.priority],
      ["CAR", "Finding reference", source?.finding_ref || control.car.finding_id || ""],
      ["CAR", "Finding", source?.finding_description || ""],
      ["CAR", "Audit reference", source?.audit_ref || ""],
      ["CAR", "Audit title", source?.audit_title || ""],
      ["CAR", "Accountable owner", assigneeName(assignees, control.profile?.accountable_owner_user_id)],
      ["CAR", "Original due", control.profile?.original_due_date || control.car.due_date || ""],
      ["CAR", "Current due", control.profile?.current_due_date || control.car.target_closure_date || control.car.due_date || ""],
      ["CAR", "Health", `${control.health.state} ${control.health.risk_score}/100`],
      ["CAR", "Next required action", control.health.next_action],
      ["Response", "Responder", latestResponse?.submitted_by_name || source?.submitted_by_name || ""],
      ["Response", "Submitted", latestResponse?.submitted_at || source?.submitted_at || ""],
      ["Response", "Immediate / containment action", latestResponse?.containment_action || source?.containment_action || ""],
      ["Response", "Root cause", latestResponse?.root_cause || source?.root_cause || ""],
      ["Response", "Corrective action", latestResponse?.corrective_action || source?.corrective_action || ""],
      ["Response", "Preventive / systemic action", latestResponse?.preventive_action || source?.preventive_action || ""],
      ["Review", "RCA status", source?.root_cause_status || ""],
      ["Review", "RCA review note", source?.root_cause_review_note || ""],
      ["Review", "CAP status", source?.capa_status || ""],
      ["Review", "CAP review note", source?.capa_review_note || ""],
    ];
    control.milestones.forEach((item) => rows.push([
      `Milestone ${item.phase_order}`,
      item.title,
      `${item.status}; owner=${assigneeName(assignees, item.owner_user_id)}; original_due=${item.original_due_date}; current_due=${item.current_due_date}; evidence=${item.evidence_ref || ""}; notes=${item.notes || ""}`,
    ]));
    control.dependencies.forEach((item) => rows.push([
      "Dependency",
      item.title,
      `${item.status}; type=${item.dependency_type}; risk=${item.risk_level}; owner=${assigneeName(assignees, item.owner_user_id)}; due=${item.due_date || ""}; blocks_closure=${item.blocks_closure}; description=${item.description || ""}; mitigation=${item.mitigation_plan || ""}`,
    ]));
    control.deadline_changes.forEach((item) => rows.push([
      "Deadline change",
      item.status,
      `previous=${item.previous_due_date}; requested=${item.requested_due_date}; reason=${item.reason}; impact=${item.impact_statement || ""}; decision=${item.review_note || ""}`,
    ]));
    attachments.forEach((item) => rows.push([
      "Evidence",
      item.filename,
      `type=${item.content_type || ""}; size=${item.size_bytes || ""}; sha256=${item.sha256 || ""}; uploaded=${item.uploaded_at}`,
    ]));
    control.events.forEach((item) => rows.push([
      "Timeline",
      item.event_type,
      `${item.created_at}; severity=${item.severity}; actor=${assigneeName(assignees, item.actor_user_id)}; ${item.reason}`,
    ]));
    control.closure_readiness.blockers.forEach((item) => rows.push(["Closure blocker", item.code, item.message]));
    return ["Section,Field,Value", ...rows.map((row) => row.map(csvCell).join(","))].join("\n");
  };

  const exportCsv = () => {
    saveDownloadedFile(new Blob([buildCsv()], { type: "text/csv;charset=utf-8" }), `${control.car.car_number}-controlled-package.csv`);
  };

  const printPackage = () => {
    const source = inviteQuery.data;
    const popup = window.open("", "_blank", "width=1100,height=850");
    if (!popup) {
      setLocalError("The browser blocked the printable CAR package window. Allow pop-ups for this portal and try again.");
      return;
    }
    popup.opener = null;
    const response = latestResponse || source;
    const milestoneRows = control.milestones.map((item) => `<tr><td>${item.phase_order}. ${escapeHtml(item.title)}</td><td>${escapeHtml(humanize(item.status))}</td><td>${escapeHtml(assigneeName(assignees, item.owner_user_id))}</td><td>${escapeHtml(formatDate(item.original_due_date))}</td><td>${escapeHtml(formatDate(item.current_due_date))}</td><td>${escapeHtml(item.evidence_ref || "")}</td><td>${escapeHtml(item.notes || "")}</td></tr>`).join("");
    const dependencyRows = control.dependencies.map((item) => `<tr><td>${escapeHtml(item.title)}</td><td>${escapeHtml(humanize(item.dependency_type))}</td><td>${escapeHtml(humanize(item.risk_level))}</td><td>${escapeHtml(assigneeName(assignees, item.owner_user_id))}</td><td>${escapeHtml(formatDate(item.due_date))}</td><td>${item.blocks_closure ? "Yes" : "No"}</td><td>${escapeHtml(humanize(item.status))}</td><td>${escapeHtml(item.description || "")}</td><td>${escapeHtml(item.mitigation_plan || "")}</td></tr>`).join("");
    const extensionRows = control.deadline_changes.map((item) => `<tr><td>${escapeHtml(formatDate(item.previous_due_date))}</td><td>${escapeHtml(formatDate(item.requested_due_date))}</td><td>${escapeHtml(item.reason)}</td><td>${escapeHtml(item.impact_statement || "")}</td><td>${escapeHtml(humanize(item.status))}</td><td>${escapeHtml(item.review_note || "")}</td></tr>`).join("");
    const evidenceRows = attachments.map((item) => `<tr><td>${escapeHtml(item.filename)}</td><td>${escapeHtml(item.content_type || "")}</td><td>${escapeHtml(formatBytes(item.size_bytes))}</td><td>${escapeHtml(formatDateTime(item.uploaded_at))}</td><td class="mono">${escapeHtml(item.sha256 || "")}</td></tr>`).join("");
    const eventRows = control.events.map((item) => `<tr><td>${escapeHtml(formatDateTime(item.created_at))}</td><td>${escapeHtml(humanize(item.event_type))}</td><td>${escapeHtml(item.severity)}</td><td>${escapeHtml(item.reason)}</td><td>${escapeHtml(assigneeName(assignees, item.actor_user_id))}</td></tr>`).join("");
    const blockerItems = control.closure_readiness.blockers.map((item) => `<li><strong>${escapeHtml(item.code)}</strong> — ${escapeHtml(item.message)}</li>`).join("");
    const html = `<!doctype html><html><head><meta charset="utf-8"><title>${escapeHtml(control.car.car_number)} CAR Package</title><style>
      @page{size:A4;margin:14mm} body{font:12px Arial,sans-serif;color:#111;line-height:1.35} h1{font-size:20px;margin:0 0 4px} h2{font-size:14px;border-bottom:1px solid #222;padding-bottom:4px;margin-top:20px} h3{font-size:12px;margin:12px 0 4px}.meta{display:grid;grid-template-columns:repeat(4,1fr);gap:8px;border:1px solid #bbb;padding:8px}.meta div{min-width:0}.label{font-size:10px;color:#555;text-transform:uppercase}.value{font-weight:700}.box{border:1px solid #bbb;padding:8px;white-space:pre-wrap} table{width:100%;border-collapse:collapse;font-size:10px} th,td{border:1px solid #aaa;padding:5px;vertical-align:top;text-align:left} th{background:#eee}.mono{font-family:monospace;word-break:break-all}.footer{margin-top:24px;border-top:1px solid #777;padding-top:8px;font-size:9px;color:#555}.no-print{margin-bottom:10px}@media print{.no-print{display:none}}
    </style></head><body><button class="no-print" onclick="window.print()">Print / Save PDF</button>
      <h1>${escapeHtml(control.car.car_number)} · Corrective Action Request Package</h1><div>Generated ${escapeHtml(new Date().toLocaleString())}</div>
      <div class="meta"><div><div class="label">Audit</div><div class="value">${escapeHtml(source?.audit_ref || "—")}</div></div><div><div class="label">Finding</div><div class="value">${escapeHtml(source?.finding_ref || control.car.finding_id || "—")}</div></div><div><div class="label">Status</div><div class="value">${escapeHtml(humanize(control.car.status))}</div></div><div><div class="label">Priority</div><div class="value">${escapeHtml(humanize(control.car.priority))}</div></div><div><div class="label">Accountable owner</div><div class="value">${escapeHtml(assigneeName(assignees, control.profile?.accountable_owner_user_id))}</div></div><div><div class="label">Original due</div><div class="value">${escapeHtml(formatDate(control.profile?.original_due_date || control.car.due_date))}</div></div><div><div class="label">Current due</div><div class="value">${escapeHtml(formatDate(control.profile?.current_due_date || control.car.target_closure_date || control.car.due_date))}</div></div><div><div class="label">Health</div><div class="value">${escapeHtml(humanize(control.health.state))} · ${control.health.risk_score}/100</div></div></div>
      <h2>Finding / requirement context</h2><h3>Finding</h3><div class="box">${escapeHtml(source?.finding_description || control.car.summary)}</div><h3>Next required action</h3><div class="box">${escapeHtml(control.health.next_action)}</div>
      <h2>Auditee / responsible-manager response</h2><div class="meta"><div><div class="label">Responder</div><div class="value">${escapeHtml(response?.submitted_by_name || "—")}</div></div><div><div class="label">Submitted</div><div class="value">${escapeHtml(formatDateTime(response?.submitted_at))}</div></div><div><div class="label">RCA review</div><div class="value">${escapeHtml(humanize(source?.root_cause_status))}</div></div><div><div class="label">CAP review</div><div class="value">${escapeHtml(humanize(source?.capa_status))}</div></div></div><h3>Immediate / containment action</h3><div class="box">${escapeHtml(response?.containment_action || "Not recorded")}</div><h3>Root cause analysis</h3><div class="box">${escapeHtml(response?.root_cause || "Not recorded")}</div><h3>Corrective action</h3><div class="box">${escapeHtml(response?.corrective_action || "Not recorded")}</div><h3>Preventive / long-term systemic action</h3><div class="box">${escapeHtml(response?.preventive_action || "Not recorded")}</div><h3>Quality review comments</h3><div class="box">RCA: ${escapeHtml(source?.root_cause_review_note || "—")}\nCAP: ${escapeHtml(source?.capa_review_note || "—")}</div>
      <h2>Governed lifecycle milestones</h2><table><thead><tr><th>Stage</th><th>Status</th><th>Owner</th><th>Original due</th><th>Current due</th><th>Evidence ref</th><th>Control note</th></tr></thead><tbody>${milestoneRows || '<tr><td colspan="7">No milestones recorded.</td></tr>'}</tbody></table>
      <h2>Dependencies and blockers</h2><table><thead><tr><th>Dependency</th><th>Type</th><th>Risk</th><th>Owner</th><th>Due</th><th>Blocks closure</th><th>Status</th><th>Description</th><th>Mitigation</th></tr></thead><tbody>${dependencyRows || '<tr><td colspan="9">No dependencies recorded.</td></tr>'}</tbody></table>
      <h2>Deadline / extension history</h2><table><thead><tr><th>Previous</th><th>Requested</th><th>Reason</th><th>Impact</th><th>Status</th><th>Decision</th></tr></thead><tbody>${extensionRows || '<tr><td colspan="6">No staged deadline changes recorded.</td></tr>'}</tbody></table>
      <h2>Objective evidence index</h2><table><thead><tr><th>File</th><th>Type</th><th>Size</th><th>Uploaded</th><th>SHA-256</th></tr></thead><tbody>${evidenceRows || '<tr><td colspan="5">No attachment evidence recorded.</td></tr>'}</tbody></table>
      <h2>Effectiveness and closure readiness</h2><div class="box">Effectiveness verification: ${control.profile?.effectiveness_required ? "Required" : "Not required"}\nClosure ready: ${control.closure_readiness.ready ? "Yes" : "No"}</div>${blockerItems ? `<ul>${blockerItems}</ul>` : ""}
      <h2>Complete control timeline</h2><table><thead><tr><th>Time</th><th>Event</th><th>Severity</th><th>Reason</th><th>Actor</th></tr></thead><tbody>${eventRows || '<tr><td colspan="5">No control events recorded.</td></tr>'}</tbody></table>
      <div class="footer">Controlled output generated from the live AMO Portal QMS CAR record. Verify signatures/authorizations and the current controlled evidence set before regulatory submission.</div></body></html>`;
    popup.document.open();
    popup.document.write(html);
    popup.document.close();
  };

  const downloadEvidencePack = async () => {
    setActionBusy("evidence-pack");
    setLocalError(null);
    try {
      const blob = await downloadCarEvidencePack(carId);
      saveDownloadedFile(blob, `${control.car.car_number}-evidence-pack.zip`);
    } catch (error) {
      setLocalError(error instanceof Error ? error.message : "Evidence pack export failed.");
    } finally {
      setActionBusy(null);
    }
  };

  const openOriginalCarPdf = () => {
    const url = inviteQuery.data?.car_form_download_url;
    if (!url) {
      setLocalError("The canonical CAR PDF is not available for this record yet.");
      return;
    }
    window.open(url, "_blank", "noopener,noreferrer");
  };

  return (
    <>
      {localError ? <div className="alert alert--danger" role="alert">{localError}</div> : null}
      {localMessage ? <div className="alert alert--success" role="status">{localMessage}</div> : null}

      <section className="card" aria-labelledby="car-next-action-heading">
        <div className="card__header">
          <div><h2 id="car-next-action-heading">Next required action</h2><p>One operational instruction, with the accountable person and controlling date visible.</p></div>
          <span className={`badge ${control.health.state === "HEALTHY" || control.health.state === "CLOSED" ? "badge--success" : control.health.state === "CRITICAL" || control.health.state === "OVERDUE" ? "badge--danger" : "badge--warning"}`}>{humanize(control.health.state)} · {control.health.risk_score}/100</span>
        </div>
        <div className="stats-grid">
          <div><span className="muted">Action</span><strong>{control.health.next_action}</strong></div>
          <div><span className="muted">Owner</span><strong>{nextOwner}</strong></div>
          <div><span className="muted">Due</span><strong>{formatDate(nextDue)}</strong></div>
          <div><span className="muted">Stage</span><strong>{nextMilestone?.title || "Final closure"}</strong></div>
        </div>
      </section>

      <section className="card" aria-labelledby="car-response-heading">
        <div className="card__header"><div><h2 id="car-response-heading">Corrective action response</h2><p>Auditee/responsible-manager submission retained separately from Quality review and staged governance.</p></div><button className="btn btn--small" type="button" onClick={() => navigate(`/maintenance/${amoCode}/quality/cars/${carId}`)}>Open CAR review</button></div>
        {responsesQuery.isLoading || inviteQuery.isLoading ? <p className="muted">Loading response history…</p> : null}
        {latestResponse || inviteQuery.data ? (
          <div className="stack">
            <div className="stats-grid"><div><span className="muted">Responder</span><strong>{latestResponse?.submitted_by_name || inviteQuery.data?.submitted_by_name || "—"}</strong></div><div><span className="muted">Submitted</span><strong>{formatDateTime(latestResponse?.submitted_at || inviteQuery.data?.submitted_at)}</strong></div><div><span className="muted">RCA review</span><strong>{humanize(inviteQuery.data?.root_cause_status)}</strong></div><div><span className="muted">CAP review</span><strong>{humanize(inviteQuery.data?.capa_status)}</strong></div></div>
            <div><strong>Immediate / containment action</strong><p>{latestResponse?.containment_action || inviteQuery.data?.containment_action || "Not submitted."}</p></div>
            <div><strong>Root cause analysis</strong><p>{latestResponse?.root_cause || inviteQuery.data?.root_cause || "Not submitted."}</p></div>
            <div><strong>Corrective action</strong><p>{latestResponse?.corrective_action || inviteQuery.data?.corrective_action || "Not submitted."}</p></div>
            <div><strong>Preventive / long-term systemic action</strong><p>{latestResponse?.preventive_action || inviteQuery.data?.preventive_action || "Not submitted."}</p></div>
            {(inviteQuery.data?.root_cause_review_note || inviteQuery.data?.capa_review_note) ? <div className="alert"><strong>Quality review comments</strong><div>RCA: {inviteQuery.data?.root_cause_review_note || "—"}</div><div>CAP: {inviteQuery.data?.capa_review_note || "—"}</div></div> : null}
          </div>
        ) : <p className="muted">No auditee/responsible-manager response has been submitted.</p>}
      </section>

      <section className="card" aria-labelledby="car-evidence-heading">
        <div className="card__header"><div><h2 id="car-evidence-heading">Objective evidence</h2><p>Upload, index, link and retrieve the evidence used to accept implementation and closure.</p></div><span className="badge badge--neutral">{attachments.length} file{attachments.length === 1 ? "" : "s"}</span></div>
        {canManage ? <div className="form-grid"><label>Link new evidence to milestone<select className="input" value={evidenceMilestoneId} onChange={(event) => setEvidenceMilestoneId(event.target.value)}><option value="">CAR-wide evidence</option>{control.milestones.map((item) => <option key={item.id} value={item.id}>{item.phase_order}. {item.title}</option>)}</select></label><label>Upload evidence files<input className="input" type="file" multiple disabled={uploadBusy} onChange={(event) => { void handleUpload(event.target.files); event.currentTarget.value = ""; }} /></label><div className="muted">Use the underlying evidence record for documents, photos, spreadsheets, certificates, work orders and other accepted proof. File hash and upload time remain visible below.</div></div> : null}
        <div className="table-wrap"><table className="table"><thead><tr><th>Evidence</th><th>Type</th><th>Size</th><th>Uploaded</th><th>SHA-256</th><th>Actions</th></tr></thead><tbody>{attachmentsQuery.isLoading ? <tr><td colSpan={6}>Loading evidence…</td></tr> : attachments.length ? attachments.map((item) => <tr key={item.id}><td><strong>{item.filename}</strong>{item.description ? <div className="muted">{item.description}</div> : null}</td><td>{item.content_type || "—"}</td><td>{formatBytes(item.size_bytes)}</td><td>{formatDateTime(item.uploaded_at)}</td><td><code>{item.sha256 ? `${item.sha256.slice(0, 12)}…` : "—"}</code></td><td><div className="toolbar"><button className="btn btn--small" type="button" disabled={actionBusy !== null} onClick={() => void handleDownload(item)}>Download</button>{canManage ? <button className="btn btn--small" type="button" disabled={actionBusy !== null} onClick={() => void handleDelete(item)}>Remove</button> : null}</div></td></tr>) : <tr><td colSpan={6} className="muted">No objective evidence files are currently linked to this CAR.</td></tr>}</tbody></table></div>
      </section>

      <section className="card" aria-labelledby="dependency-detail-heading">
        <div className="card__header"><div><h2 id="dependency-detail-heading">Dependency detail editor</h2><p>Dependencies are active controls: ownership, required date, risk, mitigation and closure impact remain editable until resolved.</p></div></div>
        {control.dependencies.length ? control.dependencies.map((row) => {
          const draft = dependencyDrafts[row.id] || dependencyDraft(row);
          return <div key={row.id} className="card" style={{ marginBottom: 12 }}><div className="form-grid"><label>Dependency title<input className="input" disabled={!canManage} value={draft.title} onChange={(event) => setDraft(row.id, { title: event.target.value })} /></label><label>Description<textarea className="input" disabled={!canManage} rows={3} value={draft.description} onChange={(event) => setDraft(row.id, { description: event.target.value })} /></label><label>Type<select className="input" disabled={!canManage} value={draft.dependency_type} onChange={(event) => setDraft(row.id, { dependency_type: event.target.value as CarDependencyType })}>{DEPENDENCY_TYPES.map((item) => <option key={item} value={item}>{humanize(item)}</option>)}</select></label><label>Risk<select className="input" disabled={!canManage} value={draft.risk_level} onChange={(event) => setDraft(row.id, { risk_level: event.target.value as CarDependencyRisk })}>{DEPENDENCY_RISKS.map((item) => <option key={item} value={item}>{humanize(item)}</option>)}</select></label><label>Owner<select className="input" disabled={!canManage} value={draft.owner_user_id} onChange={(event) => setDraft(row.id, { owner_user_id: event.target.value })}><option value="">Unassigned</option>{assignees.map((person) => <option key={person.id} value={person.id}>{person.full_name || person.email}</option>)}</select></label><label>Linked milestone<select className="input" disabled={!canManage} value={draft.milestone_id} onChange={(event) => setDraft(row.id, { milestone_id: event.target.value })}><option value="">CAR-wide</option>{control.milestones.map((item) => <option key={item.id} value={item.id}>{item.phase_order}. {item.title}</option>)}</select></label><label>Required by<input className="input" disabled={!canManage} type="date" value={draft.due_date} onChange={(event) => setDraft(row.id, { due_date: event.target.value })} /></label><label>Status<select className="input" disabled={!canManage} value={draft.status} onChange={(event) => setDraft(row.id, { status: event.target.value as CarDependencyStatus })}>{DEPENDENCY_STATUSES.map((item) => <option key={item} value={item}>{humanize(item)}</option>)}</select></label><label>Mitigation / recovery plan<textarea className="input" disabled={!canManage} rows={3} value={draft.mitigation_plan} onChange={(event) => setDraft(row.id, { mitigation_plan: event.target.value })} /></label><label className="checkbox-row"><input disabled={!canManage} type="checkbox" checked={draft.blocks_closure} onChange={(event) => setDraft(row.id, { blocks_closure: event.target.checked })} /> Blocks CAR closure</label>{canManage ? <div><button className="btn btn--primary" type="button" disabled={draft.title.trim().length < 3 || actionBusy !== null} onClick={() => void handleDependencySave(row.id)}>{actionBusy === `dependency-save-${row.id}` ? "Saving…" : "Save dependency"}</button></div> : null}</div></div>;
        }) : <p className="muted">No dependencies are currently recorded. Use the dependency capture section below when implementation relies on another person, department, resource or external party.</p>}
      </section>

      <section className="card" aria-labelledby="car-package-heading">
        <div className="card__header"><div><h2 id="car-package-heading">Evidence & report package</h2><p>Regulator/auditor-ready outputs and direct access to CAR performance reporting.</p></div></div>
        <div className="toolbar">
          <button className="btn btn--primary" type="button" onClick={printPackage}>Print CAR package</button>
          <button className="btn" type="button" onClick={exportCsv}>Export CAR CSV</button>
          <button className="btn" type="button" disabled={actionBusy !== null} onClick={() => void downloadEvidencePack()}>{actionBusy === "evidence-pack" ? "Exporting…" : "Evidence pack"}</button>
          <button className="btn" type="button" disabled={!inviteQuery.data?.car_form_download_url} onClick={openOriginalCarPdf}>Original CAR PDF</button>
          {canViewReports ? <button className="btn" type="button" onClick={() => navigate(`/maintenance/${amoCode}/quality/reports/car-performance`)}>CAR performance</button> : null}
          {canViewReports ? <button className="btn" type="button" onClick={() => navigate(`/maintenance/${amoCode}/quality/reports/exports`)}>Report exports</button> : null}
        </div>
        <p className="muted">The printable package includes the finding context, latest response, Quality review state, lifecycle milestones, dependencies, extension history, evidence index, effectiveness/closure position and complete control timeline. The generated timestamp is included in both printable and CSV outputs.</p>
      </section>
    </>
  );
};

export default QmsCarControlOperations;
