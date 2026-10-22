import InlineLoading from "../../components/shared/InlineLoading";
import { caseDate } from "../qualityAudits/carCaseModel";
import { personDisplay } from "../../utils/personDisplay";
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
} from "../../services/qmsCarControlEvidence";
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
import CarInviteGovernance from "../../components/QMS/carRca/CarInviteGovernance";
import { adoptCarEffectivenessProposal, getCarRcaInternal, listCarRcaParetoSnapshots } from "../../services/qmsCarRca";

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
  return value ? caseDate(value) : "Not set";
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
  return personDisplay(match?.full_name || match?.email);
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
  // Prevent spreadsheet formula execution from responder-entered CAR text.
  const raw = String(value ?? "");
  const safe = /^[\s\u0000-\u001f]*[=+@-]/.test(raw) ? "'" + raw : raw;
  return `"${safe.replaceAll('"', '""')}"`;
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
  const [effectivenessReviewer, setEffectivenessReviewer] = useState("");
  const [effectivenessReason, setEffectivenessReason] = useState("");
  const [effectivenessAdopting, setEffectivenessAdopting] = useState(false);
  const [effectivenessResult, setEffectivenessResult] = useState<{ case_ref: string; case_id: string } | null>(null);

  const responsesQuery = useQuery({
    queryKey: ["qms-car-control-responses", carId],
    queryFn: () => qmsListCarResponses(carId, false, amoCode),
    staleTime: 10_000,
  });
  const attachmentsQuery = useQuery({
    queryKey: ["qms-car-control-attachments", carId],
    queryFn: () => qmsListCarAttachments(carId),
    staleTime: 10_000,
  });
  const inviteQuery = useQuery({
    queryKey: ["qms-car-control-source", carId],
    queryFn: () => qmsGetCarInvite(carId, amoCode),
    staleTime: 30_000,
  });
  const rcaQuery = useQuery({
    queryKey: ["qms-car-control-rca", amoCode, carId],
    queryFn: () => getCarRcaInternal(amoCode, carId),
    staleTime: 10_000,
  });
  const paretoQuery = useQuery({
    queryKey: ["qms-car-control-pareto", amoCode, carId],
    queryFn: () => listCarRcaParetoSnapshots(amoCode, carId),
    staleTime: 10_000,
    enabled: canViewReports && hasQmsRolePermission("qms.reports.view"),
  });

  const proposal = rcaQuery.data?.submitted_snapshot?.investigation.effectiveness_proposal;
  const adoptEffectiveness = async () => {
    if (!effectivenessReviewer || effectivenessReason.trim().length < 8 || effectivenessAdopting) return;
    setEffectivenessAdopting(true);
    setLocalError(null);
    setEffectivenessResult(null);
    try {
      const next = await adoptCarEffectivenessProposal(amoCode, carId, effectivenessReviewer, effectivenessReason.trim());
      setEffectivenessResult({ case_id: next.case_id, case_ref: next.case_ref });
      setLocalMessage("Independent effectiveness verification plan established. Quality will review observations before closure.");
      void queryClient.invalidateQueries({ queryKey: ["qms-car-control", amoCode, carId] });
    } catch (error) {
      setLocalError(error instanceof Error ? error.message : "Could not establish the governed effectiveness plan.");
    } finally {
      setEffectivenessAdopting(false);
    }
  };

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
      ["Response", "Responder", personDisplay(latestResponse?.submitted_by_name || source?.submitted_by_name, "")],
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
      `type=${item.content_type || ""}; size=${item.size_bytes || ""}; uploaded=${item.uploaded_at}`,
    ]));
    control.events.forEach((item) => rows.push([
      "Timeline",
      item.event_type,
      `${item.created_at}; severity=${item.severity}; actor=${assigneeName(assignees, item.actor_user_id)}; ${item.reason}`,
    ]));
    control.closure_readiness.blockers.forEach((item) => rows.push(["Closure blocker", item.code, item.message]));
    const rca = rcaQuery.data;
    const documented = rca?.submitted_snapshot?.investigation || rca?.draft.investigation;
    if (rca) {
      rows.push(["Structured RCA", "Current revision", String(rca.revision)]);
      rows.push(["Structured RCA", "Submitted revision", rca.submitted_revision == null ? "Not submitted" : String(rca.submitted_revision)]);
      rows.push(["Structured RCA", "Consolidated proposed root cause", documented?.conclusion || "Not recorded"]);
      rows.push(["Structured RCA", "Conclusion evidence", (documented?.conclusion_evidence_references || []).join("; ")]);
      documented?.investigations.forEach(method => method.nodes.forEach(node =>
        rows.push(["Investigation " + method.method, node.category + " · " + node.entry_type,
          node.statement + "; parent=" + (node.parent_id || "") + "; evidence=" + node.evidence_references.join("; ")])));
      rca.actions.forEach(action => rows.push(["Action " + action.action_number, action.kind + " · " + action.state,
        action.description + "; owner=" + (action.external_owner_name || action.owner_user_id || "") +
        "; due=" + (action.target_date || "") + "; evidence=" + action.evidence_references.join("; ") +
        "; Quality review=" + (action.quality_review_note || "")]));
      rca.history.forEach(event => rows.push(["RCA revision " + event.revision, event.event_type,
        event.created_at + "; actor=" + (event.actor_ref || "unattributed") + "; reason=" + event.reason]));
    }
    (paretoQuery.data || []).forEach(snapshot => {
      rows.push(["QMS Pareto", "Source cohort", snapshot.population]);
      rows.push(["QMS Pareto", "Snapshot", snapshot.id + " generated " + snapshot.created_at]);
      rows.push(["QMS Pareto", "Period", snapshot.filters.start + " to " + snapshot.filters.end]);
      rows.push(["QMS Pareto", "Population", String(snapshot.sample_size)]);
      snapshot.categories.forEach(item => rows.push(["QMS Pareto category", item.category,
        "count=" + item.count + "; share=" + item.share_percent + "%; cumulative=" + item.cumulative_percent + "%"]));
      snapshot.source_references.forEach(source => rows.push(["QMS source finding", source.reference || source.id,
        "audit=" + (source.audit_reference || "") + "; requirement=" + (source.requirement || "")]));
    });
    return ["Section,Field,Value", ...rows.map((row) => row.map(csvCell).join(","))].join("\n");
  };

  const exportCsv = () => {
    if (rcaQuery.isError || rcaQuery.isPending ||
        (paretoQuery.isEnabled !== false && (paretoQuery.isError || paretoQuery.isPending))) {
      setLocalError("Controlled RCA/Pareto data could not be loaded. Retry before exporting a complete package.");
      return;
    }
    saveDownloadedFile(new Blob([buildCsv()], { type: "text/csv;charset=utf-8" }), `${control.car.car_number}-controlled-package.csv`);
  };

  const printPackage = () => {
    if (rcaQuery.isError || rcaQuery.isPending ||
        (paretoQuery.isEnabled !== false && (paretoQuery.isError || paretoQuery.isPending))) {
      setLocalError("Controlled RCA/Pareto data could not be loaded. Retry before printing a complete package.");
      return;
    }
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
    const evidenceRows = attachments.map((item) => `<tr><td>${escapeHtml(item.filename)}</td><td>${escapeHtml(item.content_type || "")}</td><td>${escapeHtml(formatBytes(item.size_bytes))}</td><td>${escapeHtml(formatDateTime(item.uploaded_at))}</td></tr>`).join("");
    const eventRows = control.events.map((item) => `<tr><td>${escapeHtml(formatDateTime(item.created_at))}</td><td>${escapeHtml(humanize(item.event_type))}</td><td>${escapeHtml(item.severity)}</td><td>${escapeHtml(item.reason)}</td><td>${escapeHtml(assigneeName(assignees, item.actor_user_id))}</td></tr>`).join("");
    const blockerItems = control.closure_readiness.blockers.map((item) => `<li><strong>${escapeHtml(item.code)}</strong> — ${escapeHtml(item.message)}</li>`).join("");
    const rcaRecord = rcaQuery.data;
    const qmsParetoRows = (paretoQuery.data || []).flatMap(snapshot => snapshot.categories.map(row =>
      `<tr><td>${escapeHtml(snapshot.created_at)}</td><td>${escapeHtml(snapshot.filters.group_by)}</td><td>${escapeHtml(row.category)}</td><td>${row.count}</td><td>${row.share_percent.toFixed(2)}%</td><td>${row.cumulative_percent.toFixed(2)}%</td></tr>`
    )).join("");
    const documented = rcaRecord?.submitted_snapshot?.investigation || rcaRecord?.draft.investigation;
    const methodRows = documented?.investigations.flatMap(method => method.nodes.map(node =>
      `<tr><td>${escapeHtml(method.method.replaceAll("_", " "))}</td><td>${escapeHtml(node.category)}</td><td>${escapeHtml(node.statement)}</td><td>${escapeHtml(node.entry_type)}</td><td>${escapeHtml(node.parent_id || "")}</td><td>${escapeHtml(node.evidence_references.join("; "))}</td></tr>`
    )).join("") || "";
    const actionRows = (rcaRecord?.actions || []).map(action =>
      `<tr><td>${escapeHtml(action.action_number)}</td><td>${escapeHtml(action.kind)}</td><td>${escapeHtml(action.description)}</td><td>${escapeHtml(action.external_owner_name || action.owner_user_id || "")}</td><td>${escapeHtml(action.target_date || "")}</td><td>${escapeHtml(action.state)}</td><td>${escapeHtml(action.evidence_references.join("; "))}</td><td>${escapeHtml(action.quality_review_note || "")}</td></tr>`
    ).join("");
    const rcaHistoryRows = (rcaRecord?.history || []).map(row =>
      `<tr><td>${escapeHtml(formatDateTime(row.created_at))}</td><td>${escapeHtml(row.revision)}</td><td>${escapeHtml(row.event_type)}</td><td>${escapeHtml(row.actor_kind)}</td><td>${escapeHtml(row.actor_ref || "")}</td><td>${escapeHtml(row.reason)}</td></tr>`
    ).join("");
    const fishbone = documented?.investigations.find(method => method.method === "ISHIKAWA");
    const branches = [...new Set((fishbone?.nodes || []).map(node => node.category))].slice(0, 8);
    const fishboneSvg = branches.length ? `<svg viewBox="0 0 800 330" style="width:100%;border:1px solid #aaa;max-height:330px" role="img" aria-label="Recorded Fishbone diagram">
      <path d="M70 165 L620 165 M620 128 L790 128 L790 200 L620 200 Z" fill="none" stroke="black" stroke-width="2"/>
      <text x="705" y="160" font-size="12" text-anchor="middle">${escapeHtml((documented?.problem_statement || "").slice(0, 23))}</text>
      ${branches.map((branch, index) => {
        const x = 150 + Math.floor(index / 2) * 120;
        const y = index % 2 === 0 ? 30 : 305;
        const node = (fishbone?.nodes || []).find(cause => cause.category === branch);
        return `<g><line x1="${x}" y1="165" x2="${x-60}" y2="${y}" stroke="black"/><text x="${x-57}" y="${y}" font-size="11">${escapeHtml(branch.slice(0, 17))}</text><text x="${x-57}" y="${y + (index % 2 ? -17 : 17)}" font-size="9">${escapeHtml((node?.statement || "").slice(0, 22))}</text></g>`;
      }).join("")}</svg>` : "";
    const paretoMethod = documented?.investigations.find(method => method.method === "PARETO");
    const paretoSource = paretoMethod?.context?.frequencies;
    const paretoCounts = Array.isArray(paretoSource) ? paretoSource.filter((row): row is { category: string; count: number; source_ref: string } =>
      Boolean(row) && typeof row === "object" && typeof row.category === "string" && typeof row.count === "number" && typeof row.source_ref === "string"
    ).sort((left, right) => right.count - left.count) : [];
    const paretoTotal = paretoCounts.reduce((sum, row) => sum + row.count, 0);
    let cumulative = 0;
    const paretoRows = paretoCounts.map(row => {
      cumulative += row.count;
      return `<tr><td>${escapeHtml(row.category)}</td><td>${row.count}</td><td>${paretoTotal ? (100 * cumulative / paretoTotal).toFixed(1) : "0.0"}%</td><td>${escapeHtml(row.source_ref)}</td></tr>`;
    }).join("");
    const html = `<!doctype html><html><head><meta charset="utf-8"><title>${escapeHtml(control.car.car_number)} CAR Package</title><style>
      @page{size:A4;margin:14mm} body{font:12px Arial,sans-serif;color:#111;line-height:1.35} h1{font-size:20px;margin:0 0 4px} h2{font-size:14px;border-bottom:1px solid #222;padding-bottom:4px;margin-top:20px} h3{font-size:12px;margin:12px 0 4px}.meta{display:grid;grid-template-columns:repeat(4,1fr);gap:8px;border:1px solid #bbb;padding:8px}.meta div{min-width:0}.label{font-size:10px;color:#555;text-transform:uppercase}.value{font-weight:700}.box{border:1px solid #bbb;padding:8px;white-space:pre-wrap} table{width:100%;border-collapse:collapse;font-size:10px} th,td{border:1px solid #aaa;padding:5px;vertical-align:top;text-align:left} th{background:#eee}.mono{font-family:monospace;word-break:break-all}.footer{margin-top:24px;border-top:1px solid #777;padding-top:8px;font-size:9px;color:#555}.no-print{margin-bottom:10px}@media print{.no-print{display:none}}
    </style></head><body><button class="no-print" onclick="window.print()">Print / Save PDF</button>
      <h1>${escapeHtml(control.car.car_number)} · Corrective Action Request Package</h1><div>Generated ${escapeHtml(new Date().toLocaleString())}</div>
      <div class="meta"><div><div class="label">Audit</div><div class="value">${escapeHtml(source?.audit_ref || "—")}</div></div><div><div class="label">Finding</div><div class="value">${escapeHtml(source?.finding_ref || control.car.finding_id || "—")}</div></div><div><div class="label">Status</div><div class="value">${escapeHtml(humanize(control.car.status))}</div></div><div><div class="label">Priority</div><div class="value">${escapeHtml(humanize(control.car.priority))}</div></div><div><div class="label">Accountable owner</div><div class="value">${escapeHtml(assigneeName(assignees, control.profile?.accountable_owner_user_id))}</div></div><div><div class="label">Original due</div><div class="value">${escapeHtml(formatDate(control.profile?.original_due_date || control.car.due_date))}</div></div><div><div class="label">Current due</div><div class="value">${escapeHtml(formatDate(control.profile?.current_due_date || control.car.target_closure_date || control.car.due_date))}</div></div><div><div class="label">Health</div><div class="value">${escapeHtml(humanize(control.health.state))} · ${control.health.risk_score}/100</div></div></div>
      <h2>Finding / requirement context</h2><h3>Finding</h3><div class="box">${escapeHtml(source?.finding_description || control.car.summary)}</div><h3>Next required action</h3><div class="box">${escapeHtml(control.health.next_action)}</div>
      <h2>Auditee / responsible-manager response</h2><div class="meta"><div><div class="label">Responder</div><div class="value">${escapeHtml(personDisplay(response?.submitted_by_name, "—"))}</div></div><div><div class="label">Submitted</div><div class="value">${escapeHtml(formatDateTime(response?.submitted_at))}</div></div><div><div class="label">RCA review</div><div class="value">${escapeHtml(humanize(source?.root_cause_status))}</div></div><div><div class="label">CAP review</div><div class="value">${escapeHtml(humanize(source?.capa_status))}</div></div></div><h3>Immediate / containment action</h3><div class="box">${escapeHtml(response?.containment_action || "Not recorded")}</div><h3>Root cause analysis</h3><div class="box">${escapeHtml(response?.root_cause || "Not recorded")}</div><h3>Corrective action</h3><div class="box">${escapeHtml(response?.corrective_action || "Not recorded")}</div><h3>Preventive / long-term systemic action</h3><div class="box">${escapeHtml(response?.preventive_action || "Not recorded")}</div><h3>Quality review comments</h3><div class="box">RCA: ${escapeHtml(source?.root_cause_review_note || "—")}\nCAP: ${escapeHtml(source?.capa_review_note || "—")}</div>
      <h2>Structured RCA evidence and diagram</h2>
      <div class="box">RCA revision: ${escapeHtml(rcaRecord?.revision ?? "Legacy only")}; Submitted revision: ${escapeHtml(rcaRecord?.submitted_revision || "Not submitted")}</div>
      <h3>Proposed systemic root cause</h3><div class="box">${escapeHtml(documented?.conclusion || "No structured RCA recorded.")}</div>
      <h3>Supporting evidence references</h3><div class="box">${escapeHtml((documented?.conclusion_evidence_references || []).join("; "))}</div>
      ${fishboneSvg}
      <table><thead><tr><th>Method</th><th>Branch</th><th>Recorded finding / Why</th><th>Evidence class</th><th>Parent cause ID</th><th>References</th></tr></thead><tbody>${methodRows || '<tr><td colspan="6">No causal nodes recorded.</td></tr>'}</tbody></table>
      <h3>Pareto analysis — respondent-reported source counts, Quality confirmation pending</h3>
      <div class="box">Population: ${escapeHtml(paretoMethod?.context?.population || "Not specified")}; Period: ${escapeHtml(paretoMethod?.context?.period_from || "not set")} — ${escapeHtml(paretoMethod?.context?.period_to || "not set")}; Sample total: ${paretoTotal}</div>
      <table><thead><tr><th>Category</th><th>Count</th><th>Cumulative %</th><th>Provenance</th></tr></thead><tbody>${paretoRows || '<tr><td colspan="4">No Pareto data recorded.</td></tr>'}</tbody></table>
      <h3>Controlled QMS source-backed Pareto snapshots</h3>
      <p>These are full-cohort aggregate frequencies from documented Quality audit findings, not proof of individual root causation.</p>
      <table><thead><tr><th>Saved at</th><th>Grouping</th><th>Category</th><th>Count</th><th>Frequency</th><th>Cumulative</th></tr></thead><tbody>${qmsParetoRows || '<tr><td colspan="6">No saved QMS-source Pareto snapshots.</td></tr>'}</tbody></table>
      <h2>Individually controlled corrective actions</h2><table><thead><tr><th>No.</th><th>Kind</th><th>Action</th><th>Owner</th><th>Due</th><th>State</th><th>Implementation evidence</th><th>Quality decision</th></tr></thead><tbody>${actionRows || '<tr><td colspan="8">No individually governed actions.</td></tr>'}</tbody></table>
      <h3>RCA revision history</h3><table><thead><tr><th>Time</th><th>Revision</th><th>Event</th><th>Actor kind</th><th>Attribution</th><th>Reason</th></tr></thead><tbody>${rcaHistoryRows || '<tr><td colspan="6">No structured RCA revisions.</td></tr>'}</tbody></table>
      <h2>Governed lifecycle milestones</h2><table><thead><tr><th>Stage</th><th>Status</th><th>Owner</th><th>Original due</th><th>Current due</th><th>Evidence ref</th><th>Control note</th></tr></thead><tbody>${milestoneRows || '<tr><td colspan="7">No milestones recorded.</td></tr>'}</tbody></table>
      <h2>Dependencies and blockers</h2><table><thead><tr><th>Dependency</th><th>Type</th><th>Risk</th><th>Owner</th><th>Due</th><th>Blocks closure</th><th>Status</th><th>Description</th><th>Mitigation</th></tr></thead><tbody>${dependencyRows || '<tr><td colspan="9">No dependencies recorded.</td></tr>'}</tbody></table>
      <h2>Deadline / extension history</h2><table><thead><tr><th>Previous</th><th>Requested</th><th>Reason</th><th>Impact</th><th>Status</th><th>Decision</th></tr></thead><tbody>${extensionRows || '<tr><td colspan="6">No staged deadline changes recorded.</td></tr>'}</tbody></table>
      <h2>Objective evidence index</h2><table><thead><tr><th>File</th><th>Type</th><th>Size</th><th>Uploaded</th></tr></thead><tbody>${evidenceRows || '<tr><td colspan="4">No attachment evidence recorded.</td></tr>'}</tbody></table>
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
        {responsesQuery.isLoading || inviteQuery.isLoading ? <p className="muted"><InlineLoading label={"Loading response history…"}/></p> : null}
        {latestResponse || inviteQuery.data ? (
          <div className="stack">
            <div className="stats-grid"><div><span className="muted">Responder</span><strong>{personDisplay(latestResponse?.submitted_by_name || inviteQuery.data?.submitted_by_name, "—")}</strong></div><div><span className="muted">Submitted</span><strong>{formatDateTime(latestResponse?.submitted_at || inviteQuery.data?.submitted_at)}</strong></div><div><span className="muted">RCA review</span><strong>{humanize(inviteQuery.data?.root_cause_status)}</strong></div><div><span className="muted">CAP review</span><strong>{humanize(inviteQuery.data?.capa_status)}</strong></div></div>
            <div><strong>Immediate / containment action</strong><p>{latestResponse?.containment_action || inviteQuery.data?.containment_action || "Not submitted."}</p></div>
            <div><strong>Root cause analysis</strong><p>{latestResponse?.root_cause || inviteQuery.data?.root_cause || "Not submitted."}</p></div>
            <div><strong>Corrective action</strong><p>{latestResponse?.corrective_action || inviteQuery.data?.corrective_action || "Not submitted."}</p></div>
            <div><strong>Preventive / long-term systemic action</strong><p>{latestResponse?.preventive_action || inviteQuery.data?.preventive_action || "Not submitted."}</p></div>
            {(inviteQuery.data?.root_cause_review_note || inviteQuery.data?.capa_review_note) ? <div className="alert"><strong>Quality review comments</strong><div>RCA: {inviteQuery.data?.root_cause_review_note || "—"}</div><div>CAP: {inviteQuery.data?.capa_review_note || "—"}</div></div> : null}
          </div>
        ) : <p className="muted">No auditee/responsible-manager response has been submitted.</p>}
      </section>

      {proposal && <section className="card" aria-labelledby="car-effectiveness-proposal-heading">
        <div className="card__header">
          <div><h2 id="car-effectiveness-proposal-heading">Proposed independent effectiveness verification</h2>
            <p>The auditee's suggested measure is not an approved verification plan. Quality must nominate the reviewer and adopt the plan independently.</p></div>
        </div>
        <dl className="case-key-values">
          <div><dt>Expected outcome</dt><dd>{proposal.expected_result || "Not provided"}</dd></div>
          <div><dt>Measurable criterion</dt><dd>{proposal.measurable_success_criterion || "Not provided"}</dd></div>
          <div><dt>Verification method</dt><dd>{proposal.verification_method || "Not provided"}</dd></div>
          <div><dt>Observation period</dt><dd>{proposal.observation_period || "Not provided"}</dd></div>
          <div><dt>Proposed review date</dt><dd>{proposal.proposed_review_date || "Not provided"}</dd></div>
        </dl>
        {proposal.supporting_records?.length ? <ul>{proposal.supporting_records.map((source, index) => <li key={index}>{source}</li>)}</ul> : null}
        {canManage && !effectivenessResult && <div className="form-grid">
          <label>Independent effectiveness reviewer
            <select className="input" value={effectivenessReviewer} onChange={e => setEffectivenessReviewer(e.target.value)}
              disabled={effectivenessAdopting}>
              <option value="">Select an authorized reviewer</option>
              {assignees.filter(user => user.id !== control.car.assigned_to_user_id).map(user =>
                <option key={user.id} value={user.id}>{personDisplay(user.full_name || user.email)}</option>)}
            </select>
          </label>
          <label>Quality adoption and independence rationale
            <textarea className="input" rows={2} value={effectivenessReason} maxLength={4000}
              onChange={e => setEffectivenessReason(e.target.value)} disabled={effectivenessAdopting}/>
          </label>
          <button className="btn btn--primary" type="button" disabled={effectivenessAdopting || !effectivenessReviewer || effectivenessReason.trim().length < 8}
            onClick={() => void adoptEffectiveness()}>
            {effectivenessAdopting ? "Establishing plan…" : "Adopt governed effectiveness plan"}
          </button>
        </div>}
        {effectivenessResult && <p role="status">Assurance Case {effectivenessResult.case_ref} created.
          <button className="btn" type="button" onClick={() => navigate(`/maintenance/${encodeURIComponent(amoCode)}/quality?workspace=assurance`)}>
            Open Assurance Cases</button></p>}
      </section>}
      <CarInviteGovernance amoCode={amoCode} carId={carId} canManage={canManage}
        onChanged={() => { void queryClient.invalidateQueries({ queryKey: ["qms-car-control-source", carId] }); }} />
      <section className="card" aria-labelledby="car-evidence-heading">
        <div className="card__header"><div><h2 id="car-evidence-heading">Objective evidence</h2><p>Upload, index, link and retrieve the evidence used to accept implementation and closure.</p></div><span className="badge badge--neutral">{attachments.length} file{attachments.length === 1 ? "" : "s"}</span></div>
        {canManage ? <div className="form-grid"><label>Link new evidence to milestone<select className="input" value={evidenceMilestoneId} onChange={(event) => setEvidenceMilestoneId(event.target.value)}><option value="">CAR-wide evidence</option>{control.milestones.map((item) => <option key={item.id} value={item.id}>{item.phase_order}. {item.title}</option>)}</select></label><label>Upload evidence files<input className="input" type="file" multiple disabled={uploadBusy} onChange={(event) => { void handleUpload(event.target.files); event.currentTarget.value = ""; }} /></label><div className="muted">Use the underlying evidence record for documents, photos, spreadsheets, certificates, work orders and other accepted proof. Filename, size and upload time remain visible below.</div></div> : null}
        <div className="table-wrap"><table className="table"><thead><tr><th>Evidence</th><th>Type</th><th>Size</th><th>Uploaded</th><th>Actions</th></tr></thead><tbody>{attachmentsQuery.isLoading ? <tr><td colSpan={5}>Loading evidence…</td></tr> : attachments.length ? attachments.map((item) => <tr key={item.id}><td><strong>{item.filename}</strong>{item.description ? <div className="muted">{item.description}</div> : null}</td><td>{item.content_type || "—"}</td><td>{formatBytes(item.size_bytes)}</td><td>{formatDateTime(item.uploaded_at)}</td><td><div className="toolbar"><button className="btn btn--small" type="button" disabled={actionBusy !== null} onClick={() => void handleDownload(item)}>Download</button>{canManage ? <button className="btn btn--small" type="button" disabled={actionBusy !== null} onClick={() => void handleDelete(item)}>Remove</button> : null}</div></td></tr>) : <tr><td colSpan={5} className="muted">No objective evidence files are currently linked to this CAR.</td></tr>}</tbody></table></div>
      </section>

      <section className="card" aria-labelledby="dependency-detail-heading">
        <div className="card__header"><div><h2 id="dependency-detail-heading">Dependency detail editor</h2><p>Dependencies are active controls: ownership, required date, risk, mitigation and closure impact remain editable until resolved.</p></div></div>
        {control.dependencies.length ? control.dependencies.map((row) => {
          const draft = dependencyDrafts[row.id] || dependencyDraft(row);
          return <div key={row.id} className="card" style={{ marginBottom: 12 }}><div className="form-grid"><label>Dependency title<input className="input" disabled={!canManage} value={draft.title} onChange={(event) => setDraft(row.id, { title: event.target.value })} /></label><label>Description<textarea className="input" disabled={!canManage} rows={3} value={draft.description} onChange={(event) => setDraft(row.id, { description: event.target.value })} /></label><label>Type<select className="input" disabled={!canManage} value={draft.dependency_type} onChange={(event) => setDraft(row.id, { dependency_type: event.target.value as CarDependencyType })}>{DEPENDENCY_TYPES.map((item) => <option key={item} value={item}>{humanize(item)}</option>)}</select></label><label>Risk<select className="input" disabled={!canManage} value={draft.risk_level} onChange={(event) => setDraft(row.id, { risk_level: event.target.value as CarDependencyRisk })}>{DEPENDENCY_RISKS.map((item) => <option key={item} value={item}>{humanize(item)}</option>)}</select></label><label>Owner<select className="input" disabled={!canManage} value={draft.owner_user_id} onChange={(event) => setDraft(row.id, { owner_user_id: event.target.value })}><option value="">Unassigned</option>{assignees.map((person) => <option key={person.id} value={person.id}>{personDisplay(person.full_name || person.email)}</option>)}</select></label><label>Linked milestone<select className="input" disabled={!canManage} value={draft.milestone_id} onChange={(event) => setDraft(row.id, { milestone_id: event.target.value })}><option value="">CAR-wide</option>{control.milestones.map((item) => <option key={item.id} value={item.id}>{item.phase_order}. {item.title}</option>)}</select></label><label>Required by<input className="input" disabled={!canManage} type="date" value={draft.due_date} onChange={(event) => setDraft(row.id, { due_date: event.target.value })} /></label><label>Status<select className="input" disabled={!canManage} value={draft.status} onChange={(event) => setDraft(row.id, { status: event.target.value as CarDependencyStatus })}>{DEPENDENCY_STATUSES.map((item) => <option key={item} value={item}>{humanize(item)}</option>)}</select></label><label>Mitigation / recovery plan<textarea className="input" disabled={!canManage} rows={3} value={draft.mitigation_plan} onChange={(event) => setDraft(row.id, { mitigation_plan: event.target.value })} /></label><label className="checkbox-row"><input disabled={!canManage} type="checkbox" checked={draft.blocks_closure} onChange={(event) => setDraft(row.id, { blocks_closure: event.target.checked })} /> Blocks CAR closure</label>{canManage ? <div><button className="btn btn--primary" type="button" disabled={draft.title.trim().length < 3 || actionBusy !== null} onClick={() => void handleDependencySave(row.id)}>{actionBusy === `dependency-save-${row.id}` ? "Saving…" : "Save dependency"}</button></div> : null}</div></div>;
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
