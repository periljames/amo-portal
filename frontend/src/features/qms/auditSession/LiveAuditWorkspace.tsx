import React, { useEffect, useMemo, useState } from "react";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import {
  AlertTriangle,
  ArrowLeft,
  ArrowRight,
  CheckCircle2,
  CircleSlash2,
  ClipboardCheck,
  Eye,
  FileWarning,
  MessageSquareText,
  ShieldAlert,
  Users,
  X,
} from "lucide-react";
import { Link } from "react-router-dom";

import { hasQmsRolePermission } from "../../../app/routeGuards";
import { ApiClientError } from "../../../services/apiClient";
import { isOfflineQueuedError } from "../../../services/offlineHttp";
import { listOfflineMutations } from "../../../services/offlinePersistence";
import { qmsListFindings, qmsResolveAudit } from "../../../services/qms";
import {
  createAtomicChecklistFinding,
  listChecklistExecutionGovernance,
  mutateChecklistFieldwork,
  type CanonicalChecklistResponse,
  type ChecklistExecutionGovernanceRow,
  type FieldworkFindingLevel,
  type FieldworkFindingSeverity,
} from "../../../services/qmsChecklistExecutionGovernance";
import { heartbeatAuditPresence, listAuditPresence } from "../../../services/qmsAuditPresence";
import { getAuditSession } from "../../../services/qmsAuditSession";
import LiveAuditEvidenceStrip from "./LiveAuditEvidenceStrip";
import { auditSessionPath } from "./auditSessionRoutes";
import "../../../styles/qms-live-audit-workspace.css";

const RESPONSE_OPTIONS: Array<{
  value: CanonicalChecklistResponse;
  label: string;
  icon: React.ComponentType<{ size?: number }>;
}> = [
  { value: "COMPLIANT", label: "Compliant", icon: CheckCircle2 },
  { value: "NONCOMPLIANT", label: "NCR", icon: FileWarning },
  { value: "OBSERVATION", label: "Observation", icon: MessageSquareText },
  { value: "NOT_APPLICABLE", label: "N/A", icon: CircleSlash2 },
  { value: "NOT_VERIFIED", label: "Not verified", icon: ShieldAlert },
];

type Props = { amoCode: string; auditKey: string };
type NonconformityLevel = "LEVEL_1" | "LEVEL_2" | "LEVEL_3";

type FindingDraft = {
  mode: "NONCOMPLIANT" | "OBSERVATION";
  item: ChecklistExecutionGovernanceRow;
  level: NonconformityLevel | "";
  statement: string;
  objectiveEvidence: string;
};

type FieldworkUpdateInput = {
  item: ChecklistExecutionGovernanceRow;
  response: CanonicalChecklistResponse;
  auditorNotes: string;
};

const NONCONFORMITY_LEVELS: Array<{ value: NonconformityLevel; label: string; severity: FieldworkFindingSeverity }> = [
  { value: "LEVEL_1", label: "Level 1 · Critical", severity: "CRITICAL" },
  { value: "LEVEL_2", label: "Level 2 · Major", severity: "MAJOR" },
  { value: "LEVEL_3", label: "Level 3 · Minor", severity: "MINOR" },
];

function findingClassification(draft: FindingDraft): { severity: FieldworkFindingSeverity; level: FieldworkFindingLevel } {
  if (draft.mode === "OBSERVATION") return { severity: "MINOR", level: "LEVEL_4" };
  const selected = NONCONFORMITY_LEVELS.find((candidate) => candidate.value === draft.level);
  if (!selected) throw new Error("Select the governed non-conformity classification before creating the finding.");
  return { severity: selected.severity, level: selected.value };
}

function fieldworkConflictMessage(error: unknown): string | null {
  if (!(error instanceof ApiClientError) || error.status !== 409) return null;
  const body = error.body as { detail?: unknown } | null;
  const detail = body?.detail && typeof body.detail === "object" ? body.detail as Record<string, unknown> : null;
  if (!detail) return error.message;
  const code = String(detail.code || "");
  if (code === "FIELDWORK_VERSION_CONFLICT") {
    const serverVersion = detail.server_version;
    return `Conflict detected: another auditor or device changed this checklist item${typeof serverVersion === "number" ? ` to version ${serverVersion}` : ""}. Refresh and review the server record before retrying; the portal will not silently overwrite it.`;
  }
  if (code === "FIELDWORK_IDEMPOTENCY_CONFLICT") return "The same offline mutation identifier was received with different content. The portal rejected it to prevent duplicate or ambiguous fieldwork.";
  if (code === "FIELDWORK_FINDING_ALREADY_LINKED") return "This checklist item already has a governed finding. Review the existing finding instead of creating a duplicate.";
  return typeof detail.message === "string" ? detail.message : error.message;
}

const LiveAuditWorkspace: React.FC<Props> = ({ amoCode, auditKey }) => {
  const queryClient = useQueryClient();
  const canManage = hasQmsRolePermission("qms.audit.manage");
  const [selectedId, setSelectedId] = useState<string | null>(null);
  const [noteDrafts, setNoteDrafts] = useState<Record<string, string>>({});
  const [findingDraft, setFindingDraft] = useState<FindingDraft | null>(null);
  const [localError, setLocalError] = useState<string | null>(null);
  const [syncNotice, setSyncNotice] = useState<string | null>(null);

  const auditQuery = useQuery({
    queryKey: ["qms", "live-audit-resolve", auditKey],
    queryFn: () => qmsResolveAudit(auditKey),
    staleTime: 5_000,
  });
  const auditId = auditQuery.data?.id || "";
  const checklistQuery = useQuery({
    queryKey: ["qms", "live-audit-checklist", amoCode, auditId],
    queryFn: ({ signal }) => listChecklistExecutionGovernance(amoCode, auditId, signal),
    enabled: Boolean(auditId),
    staleTime: 1_500,
  });
  const findingsQuery = useQuery({
    queryKey: ["qms", "live-audit-findings", auditId],
    queryFn: () => qmsListFindings(auditId),
    enabled: Boolean(auditId),
    staleTime: 2_000,
  });
  const sessionQuery = useQuery({
    queryKey: ["qms", "audit-session", amoCode, auditId],
    queryFn: ({ signal }) => getAuditSession(amoCode, auditId, signal),
    enabled: Boolean(auditId),
    staleTime: 2_000,
  });
  const presenceQuery = useQuery({
    queryKey: ["qms", "audit-presence", amoCode, auditId],
    queryFn: ({ signal }) => listAuditPresence(amoCode, auditId, signal),
    enabled: Boolean(auditId),
    staleTime: 3_000,
    refetchInterval: 15_000,
  });
  const outboxQuery = useQuery({
    queryKey: ["qms", "live-audit-outbox", auditId],
    queryFn: async () => {
      const auditMarker = `/audits/${encodeURIComponent(auditId)}/`;
      const entries = await listOfflineMutations();
      return entries.filter((entry) => entry.entityType === "qms-audit-checklist-item" && entry.path.includes(auditMarker));
    },
    enabled: Boolean(auditId),
    staleTime: 500,
    refetchInterval: 2_000,
  });

  useEffect(() => {
    if (!auditId) return undefined;
    let cancelled = false;
    const beat = async () => {
      try {
        await heartbeatAuditPresence(amoCode, auditId, "live");
        if (!cancelled) void presenceQuery.refetch();
      } catch {
        // Presence is a collaboration projection and must never block fieldwork.
      }
    };
    void beat();
    const timer = window.setInterval(() => void beat(), 20_000);
    return () => { cancelled = true; window.clearInterval(timer); };
  }, [amoCode, auditId]); // eslint-disable-line react-hooks/exhaustive-deps

  const items = useMemo(() => checklistQuery.data?.items ?? [], [checklistQuery.data?.items]);
  const effectiveSelectedId = useMemo(() => {
    if (!items.length) return null;
    if (selectedId && items.some((item) => item.checklist_item_id === selectedId)) return selectedId;
    return (items.find((item) => item.canonical_response_status === "NOT_VERIFIED") || items[0]).checklist_item_id;
  }, [items, selectedId]);
  const selectedIndex = effectiveSelectedId ? items.findIndex((item) => item.checklist_item_id === effectiveSelectedId) : -1;
  const selected = selectedIndex >= 0 ? items[selectedIndex] : null;
  const notes = selected ? noteDrafts[selected.checklist_item_id] ?? selected.auditor_notes ?? "" : "";
  const outboxEntries = outboxQuery.data ?? [];
  const outbox = useMemo(() => ({
    queued: outboxEntries.filter((entry) => entry.status === "queued" || entry.status === "syncing").length,
    conflicts: outboxEntries.filter((entry) => entry.status === "conflict").length,
    failed: outboxEntries.filter((entry) => entry.status === "failed").length,
  }), [outboxEntries]);
  const presence = presenceQuery.data?.items || [];
  const auditeePresence = presence.filter((entry) => entry.actor_type === "AUDITEE_GUEST");
  const auditTeamPresence = presence.filter((entry) => entry.actor_type !== "AUDITEE_GUEST");

  const refreshFieldwork = async () => {
    await queryClient.invalidateQueries({ queryKey: ["qms"] });
  };

  const updateMutation = useMutation({
    mutationFn: ({ item, response, auditorNotes }: FieldworkUpdateInput) => mutateChecklistFieldwork(amoCode, auditId, item, {
      canonical_response_status: response,
      auditor_notes: auditorNotes.trim() || null,
      evidence_references: item.evidence_references || [],
      reason: "Live audit fieldwork checklist update.",
    }),
    onSuccess: async (_result, variables) => {
      setLocalError(null);
      setSyncNotice("Saved to the authoritative audit record.");
      setNoteDrafts((current) => { const next = { ...current }; delete next[variables.item.checklist_item_id]; return next; });
      await refreshFieldwork();
      void outboxQuery.refetch();
    },
    onError: (error) => {
      if (isOfflineQueuedError(error)) {
        setLocalError(null);
        setSyncNotice("Saved securely on this device · pending ordered sync. The authoritative audit state will not change until the server accepts the mutation.");
        void outboxQuery.refetch();
        return;
      }
      setSyncNotice(null);
      setLocalError(fieldworkConflictMessage(error) || (error instanceof Error ? error.message : "Checklist update failed."));
      void outboxQuery.refetch();
    },
  });

  const findingMutation = useMutation({
    mutationFn: async (draft: FindingDraft) => {
      const classification = findingClassification(draft);
      const auditorNotes = noteDrafts[draft.item.checklist_item_id] ?? draft.item.auditor_notes ?? "";
      return createAtomicChecklistFinding(amoCode, auditId, draft.item, {
        canonical_response_status: draft.mode,
        severity: classification.severity,
        level: classification.level,
        requirement_ref: draft.item.requirement_ref || draft.item.checklist_ref || null,
        description: draft.statement.trim(),
        objective_evidence: draft.objectiveEvidence.trim() || draft.item.objective_evidence || null,
        safety_sensitive: false,
        auditor_notes: auditorNotes.trim() || null,
        evidence_references: draft.item.evidence_references || [],
        reason: `Live audit fieldwork ${draft.mode === "NONCOMPLIANT" ? "non-conformity" : "observation"} recorded atomically with the governed checklist response.`,
      });
    },
    onSuccess: async (_result, draft) => {
      setFindingDraft(null);
      setLocalError(null);
      setSyncNotice("Finding, checklist response and governed CAR/task consequences committed as one authoritative transaction.");
      setNoteDrafts((current) => { const next = { ...current }; delete next[draft.item.checklist_item_id]; return next; });
      await refreshFieldwork();
      void outboxQuery.refetch();
    },
    onError: (error) => {
      if (isOfflineQueuedError(error)) {
        setFindingDraft(null);
        setLocalError(null);
        setSyncNotice("Finding captured securely on this device as one atomic intent · pending ordered sync. No server finding, CAR or checklist response exists until the complete transaction is accepted.");
        void outboxQuery.refetch();
        return;
      }
      setSyncNotice(null);
      setLocalError(fieldworkConflictMessage(error) || (error instanceof Error ? error.message : "Finding creation failed."));
      void outboxQuery.refetch();
    },
  });

  const counts = useMemo(() => {
    const base: Record<CanonicalChecklistResponse, number> = { COMPLIANT: 0, NONCOMPLIANT: 0, OBSERVATION: 0, NOT_APPLICABLE: 0, NOT_VERIFIED: 0 };
    items.forEach((item) => { base[item.canonical_response_status] += 1; });
    return base;
  }, [items]);
  const completed = items.length - counts.NOT_VERIFIED;
  const percent = items.length ? Math.round((completed / items.length) * 100) : 0;
  const findings = findingsQuery.data || [];

  const move = (offset: number) => {
    if (!items.length || selectedIndex < 0) return;
    const nextIndex = Math.min(items.length - 1, Math.max(0, selectedIndex + offset));
    setSelectedId(items[nextIndex].checklist_item_id);
  };

  const selectResponse = (item: ChecklistExecutionGovernanceRow, response: CanonicalChecklistResponse) => {
    if (!canManage) return;
    setSyncNotice(null);
    if (response === "NONCOMPLIANT" || response === "OBSERVATION") {
      setFindingDraft({ mode: response, item, level: "", statement: "", objectiveEvidence: item.objective_evidence || "" });
      return;
    }
    updateMutation.mutate({ item, response, auditorNotes: notes });
  };

  if (auditQuery.isLoading || checklistQuery.isLoading) return <div className="qms-live-audit-focus qms-live-audit-focus--loading">Preparing live audit workspace…</div>;
  if (auditQuery.isError || checklistQuery.isError || !auditQuery.data) {
    const error = auditQuery.error || checklistQuery.error;
    return <div className="qms-live-audit-focus qms-live-audit-focus--loading" role="alert"><AlertTriangle size={20} /> {error instanceof Error ? error.message : "Live audit workspace could not be loaded."}</div>;
  }

  return (
    <div className="qms-live-audit-focus" role="region" aria-label="Live audit fieldwork workspace">
      <header className="qms-live-audit-focus__header">
        <div><span>LIVE AUDIT · governed fieldwork</span><h1>{auditQuery.data.audit_ref} · {auditQuery.data.title}</h1></div>
        <div className="qms-live-audit-focus__header-meta">
          <span>{canManage ? "AUDITOR MODE" : "READ-ONLY MODE"}</span>
          <span>{sessionQuery.data ? `Authoritative stage: ${sessionQuery.data.current_stage_label}` : "Verifying lifecycle…"}</span>
          <span>{completed}/{items.length} complete · {percent}%</span>
          <span><Users size={13} /> {presence.length} active</span>
          {outbox.queued || outbox.conflicts || outbox.failed ? <span>DEVICE SYNC · {outbox.queued} pending · {outbox.conflicts} conflict · {outbox.failed} failed</span> : <span>DEVICE SYNC · clear</span>}
          <Link to={auditSessionPath(amoCode, auditKey, "prepare")}><X size={16} /> Exit field mode</Link>
        </div>
      </header>

      {localError ? <div className="qms-live-audit-focus__error" role="alert"><AlertTriangle size={16} /> {localError}</div> : null}
      {syncNotice ? <div className="qms-live-audit-focus__sync-notice" role="status">{syncNotice}</div> : null}

      <div className="qms-live-audit-focus__body">
        <aside className="qms-live-audit-focus__sections" aria-label="Checklist questions">
          <div className="qms-live-audit-focus__progress"><span style={{ width: `${percent}%` }} /></div>
          <strong>Checklist</strong>
          <div className="qms-live-audit-focus__question-list">
            {items.map((item, index) => (
              <button type="button" key={item.checklist_item_id} className={item.checklist_item_id === selected?.checklist_item_id ? "is-selected" : ""} onClick={() => setSelectedId(item.checklist_item_id)}>
                <span>{index + 1}</span>
                <div><strong>{item.checklist_ref || item.requirement_ref || `Question ${index + 1}`}</strong><small>{item.section || "General"}</small></div>
                <em data-status={item.canonical_response_status}>{item.canonical_response_status.replaceAll("_", " ")}</em>
              </button>
            ))}
          </div>
        </aside>

        <main className="qms-live-audit-focus__question">
          {selected ? (
            <>
              <div className="qms-live-audit-focus__question-head"><div><span>{selected.section || "Checklist"}</span><h2>{selected.prompt}</h2></div><span>{selectedIndex + 1} / {items.length}</span></div>
              <dl className="qms-live-audit-focus__references"><div><dt>Checklist ref</dt><dd>{selected.checklist_ref || "—"}</dd></div><div><dt>Requirement</dt><dd>{selected.requirement_ref || "—"}</dd></div><div><dt>Current</dt><dd>{selected.canonical_response_status.replaceAll("_", " ")} · v{selected.entity_version}</dd></div></dl>

              <div className="qms-live-audit-focus__responses" aria-label="Checklist response">
                {RESPONSE_OPTIONS.map((option) => {
                  const Icon = option.icon;
                  return <button type="button" key={option.value} className={selected.canonical_response_status === option.value ? "is-active" : ""} disabled={!canManage || updateMutation.isPending || findingMutation.isPending} onClick={() => selectResponse(selected, option.value)}><Icon size={17} /> {option.label}</button>;
                })}
              </div>

              <label className="qms-live-audit-focus__notes"><span>Auditor note</span><textarea readOnly={!canManage} value={notes} onChange={(event) => setNoteDrafts((current) => ({ ...current, [selected.checklist_item_id]: event.target.value }))} rows={5} placeholder="Record objective, attributable fieldwork notes." /></label>
              <div className="qms-live-audit-focus__note-actions"><button type="button" disabled={!canManage || updateMutation.isPending} onClick={() => { setSyncNotice(null); updateMutation.mutate({ item: selected, response: selected.canonical_response_status, auditorNotes: notes }); }}>Save note</button></div>

              <LiveAuditEvidenceStrip amoCode={amoCode} auditId={auditId} item={selected} canManage={canManage} onChanged={refreshFieldwork} onError={setLocalError} onNotice={setSyncNotice} />

              <footer className="qms-live-audit-focus__nav"><button type="button" onClick={() => move(-1)} disabled={selectedIndex <= 0}><ArrowLeft size={16} /> Previous</button><button type="button" onClick={() => move(1)} disabled={selectedIndex < 0 || selectedIndex >= items.length - 1}>Next <ArrowRight size={16} /></button></footer>
            </>
          ) : <div className="qms-live-audit-focus__empty">No governed checklist items are bound to this audit.</div>}
        </main>

        <aside className="qms-live-audit-focus__summary">
          <section><span>Progress</span><strong>{percent}%</strong><small>{completed} of {items.length} questions resolved</small></section>
          <section className="qms-live-audit-focus__stats"><div><strong>{counts.COMPLIANT}</strong><span>Compliant</span></div><div><strong>{counts.NONCOMPLIANT}</strong><span>NCR</span></div><div><strong>{counts.OBSERVATION}</strong><span>Observations</span></div><div><strong>{counts.NOT_VERIFIED}</strong><span>Pending</span></div></section>
          <section><span>Device sync</span><strong>{outbox.queued + outbox.conflicts + outbox.failed}</strong><small>{outbox.queued} pending · {outbox.conflicts} conflict · {outbox.failed} failed. Conflicts require review; they are never silently overwritten.</small></section>
          <section className="qms-live-audit-focus__presence">
            <span><Users size={14} /> Audit team live</span>
            <strong>{auditTeamPresence.length}</strong>
            <ul>{auditTeamPresence.slice(0, 8).map((entry) => <li key={entry.id}><b>{entry.display_name}</b><small>{entry.role || entry.actor_type.replaceAll("_", " ")}{entry.route ? ` · ${entry.route}` : ""}</small></li>)}</ul>
          </section>
          <section className="qms-live-audit-focus__presence">
            <span><Eye size={14} /> Auditee viewing</span>
            <strong>{auditeePresence.length}</strong>
            <small>{auditeePresence.length ? auditeePresence.map((entry) => entry.display_name).join(", ") : "No auditee guest with progress/presence scope is currently active."}</small>
          </section>
          <section><span>Findings</span><strong>{findings.length}</strong><ul>{findings.slice(0, 6).map((finding) => <li key={finding.id}><b>{finding.finding_ref || finding.level}</b><small>{finding.description}</small></li>)}</ul></section>
          <section className="qms-live-audit-focus__sharing"><span>Auditee live view</span><strong>Released-data boundary active</strong><small>Auditees receive only server-released findings and permitted progress/evidence projections; private checklist notes remain internal.</small></section>
          <Link className="qms-live-audit-focus__closing-link" to={auditSessionPath(amoCode, auditKey, "closing")}><ClipboardCheck size={16} /> Go to Closing</Link>
        </aside>
      </div>

      {findingDraft ? (
        <div className="qms-live-audit-finding-backdrop" role="presentation">
          <section className="qms-live-audit-finding" role="dialog" aria-modal="true" aria-label="Raise finding">
            <header><div><span>{findingDraft.mode === "NONCOMPLIANT" ? "NON-CONFORMITY" : "OBSERVATION"}</span><h2>Raise finding from checklist</h2></div><button type="button" onClick={() => setFindingDraft(null)} aria-label="Close finding composer"><X size={18} /></button></header>
            <dl><div><dt>Requirement</dt><dd>{findingDraft.item.requirement_ref || findingDraft.item.checklist_ref || "—"}</dd></div></dl>
            {findingDraft.mode === "NONCOMPLIANT" ? <label><span>Classification</span><select value={findingDraft.level} onChange={(event) => setFindingDraft((current) => current ? { ...current, level: event.target.value as NonconformityLevel } : current)}><option value="">Select governed level</option>{NONCONFORMITY_LEVELS.map((level) => <option key={level.value} value={level.value}>{level.label}</option>)}</select></label> : null}
            <label><span>Finding statement</span><textarea rows={5} value={findingDraft.statement} onChange={(event) => setFindingDraft((current) => current ? { ...current, statement: event.target.value } : current)} /></label>
            <label><span>Objective evidence</span><textarea rows={4} value={findingDraft.objectiveEvidence} onChange={(event) => setFindingDraft((current) => current ? { ...current, objectiveEvidence: event.target.value } : current)} /></label>
            <p>{findingDraft.mode === "NONCOMPLIANT" ? "Select the applicable governed finding level. The workspace does not infer severity from the checklist response." : "This creates a governed observation linked to the exact checklist item."}</p>
            <footer><button type="button" onClick={() => setFindingDraft(null)}>Cancel</button><button type="button" className="is-primary" disabled={findingDraft.statement.trim().length < 8 || (findingDraft.mode === "NONCOMPLIANT" && !findingDraft.level) || findingMutation.isPending} onClick={() => findingMutation.mutate(findingDraft)}>{findingMutation.isPending ? "Creating…" : "Create finding"}</button></footer>
          </section>
        </div>
      ) : null}
    </div>
  );
};

export default LiveAuditWorkspace;
