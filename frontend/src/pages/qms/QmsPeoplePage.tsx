import React, { FormEvent, useCallback, useEffect, useMemo, useRef, useState } from "react";
import {
  AlertTriangle,
  BadgeCheck,
  Ban,
  CalendarClock,
  CheckCircle2,
  ClipboardCheck,
  Crown,
  Download,
  ExternalLink,
  Eye,
  FileBadge,
  FileText,
  HelpCircle,
  PauseCircle,
  Pencil,
  Plus,
  RefreshCw,
  RotateCcw,
  Search,
  Shield,
  ShieldCheck,
  Trash2,
  Upload,
  UserCheck,
  UserRoundCheck,
  Users,
  X,
} from "lucide-react";
import { Link, useSearchParams } from "react-router-dom";

import { hasQmsRolePermission, isPlatformSuperuser } from "../../app/routeGuards";
import { ApiClientError, clearQmsApiResponseCache } from "../../services/apiClient";
import { qmsListAuditPersonnelOptions, type QMSPersonOption } from "../../services/qmsCore";
import {
  assessQmsIndependence,
  createQmsPrivilege,
  changeQmsAuditorRank,
  purgeQmsPrivilege,
  downloadQmsAuthorization,
  createQmsPrivilegeRule,
  createQmsQmTrainingBypass,
  decideQmsPrivilege,
  declareQmsIndependence,
  deleteQmsPrivilegeRule,
  downloadQmsPersonAuditIssuedReport,
  getQmsEligibility,
  getQmsIndependencePolicy,
  getQmsPeopleSummary,
  getQmsPersonAuditParticipation,
  invalidateQmsEligibilityMemory,
  listQmsAuthorizationCandidates,
  listQmsIndependenceDeclarations,
  listQmsPrivilegeRules,
  listQmsPrivileges,
  peekQmsEligibility,
  preflightQmsAuditorAssignment,
  updateQmsIndependencePolicy,
  updateQmsPrivilegeRule,
  uploadQmsAuthorizationEvidence,
  type QmsAuthorizationCandidate,
  type QmsAuditorAssignmentAssessment,
  type QmsAuditorAssignmentRole,
  type QmsAuditorEligibilityPreflight,
  type QmsEligibility,
  type QmsIndependenceAssessment,
  type QmsIndependenceConflict,
  type QmsIndependenceDeclaration,
  type QmsIndependencePolicy,
  type QmsIndependenceRemediation,
  type QmsPeopleSummary,
  type QmsPersonAuditParticipationItem,
  type QmsPrivilege,
  type QmsPrivilegeDecision,
  type QmsPrivilegeRule,
  type QmsQmTrainingBypass,
} from "../../services/qmsPeople";
import { listTrainingCourses } from "../../services/training";
import type { TrainingCourseRead } from "../../types/training";
import { auditSessionPath } from "../../features/qms/auditSession/auditSessionRoutes";
import { allowedPrivilegeDecisions, bindEligibilityToPrivilege, defaultPrivilegeDecision, privilegeDecisionLabel, privilegeDisplayGates, privilegeDraftReason, privilegeReadinessLabel, privilegeStatusAfterDecision } from "./qmsPeopleDecisions";
import { capPrivilegeExpiresOn, competenceChipStatus, earliestCompetenceValidUntil } from "./qmsPeopleCompetence";
import {
  authorizeValidityLabel,
  buildPrivilegeRuleScopeSchema,
  courseCodeSelected,
  defaultCompetenceScopeForPrivilegeType,
  defaultTrainingCodesForPrivilegeType,
  defaultTrainingExpression,
  formatTrainingRuleSummary,
  normalizeCourseCode,
  parseTrainingExpression,
  ruleConfiguredTrainingCodes,
  ruleRequiredTrainingPayload,
  ruleTrainingExpressionFromRule,
  ruleUsesCompetencePackage,
  toggleTrainingSelectionWithPairs,
  uniqueCourseCodes,
  type TrainingRuleJoin,
} from "./qmsPeopleRuleTraining";
import { catalogEntryForType, humanisePrivilegeType } from "./qmsPrivilegeRoleCatalog";
import "../../styles/qms/people.css";
import { downloadBlob } from "../../services/typedApi";
import { useActionFlash } from "../../hooks/useActionFlash";
import { queueOptimisticAction } from "../../utils/optimisticAction";
import { personDisplay } from "../../utils/personDisplay";

type Props = { amoCode: string };
type PageTab = "privileges" | "rules";
type ActionMode = "NONE" | "CREATE" | "DECISION" | "AUDIT_ASSIGNMENT" | "IMPARTIALITY_FORM" | "CREATE_RULE" | "EDIT_RULE" | "INDEPENDENCE_POLICY";
type ConfirmDialog =
  | { kind: "purge"; privilegeId: string; personName: string }
  | { kind: "delete-rule"; ruleId: string; ruleTitle: string };
type RankFilter = "ALL" | "LEAD" | "AUDITOR" | "OBSERVER" | "INSPECTOR" | "SUSPENDED" | "EXPIRING";
type AssignmentContextType = "AUDIT" | "AUDIT_SCHEDULE" | "PROGRAMME_ITEM" | "ASSURANCE_CASE" | "MISSION" | "OTHER" | "";
type AssignmentSubmission = {
  selected_privilege_id: string;
  selected_privilege_code: string;
  selected_scope_key: string;
  user_id: string;
  assignment_role: QmsAuditorAssignmentRole;
  assignment_date: string;
  assignment_scope_key: string;
  context_type: AssignmentContextType;
  context_id: string;
};

const EMPTY_SUMMARY: QmsPeopleSummary = {
  active_privileges: 0,
  expiring_within_60_days: 0,
  suspended_privileges: 0,
  independence_exceptions: 0,
  lead_auditors: 0,
  auditors: 0,
  observers: 0,
  inspectors: 0,
};
const PRIVILEGE_TYPES: QmsPrivilegeRule["privilege_type"][] = ["LEAD_AUDITOR", "AUDITOR", "QUALITY_INSPECTOR", "AUTHORIZATION_REVIEWER", "CUSTOM"];
const ACTION_MODES = new Set<ActionMode>(["CREATE", "DECISION", "AUDIT_ASSIGNMENT", "IMPARTIALITY_FORM", "CREATE_RULE", "EDIT_RULE", "INDEPENDENCE_POLICY"]);
const HARD_INDEPENDENCE_CODES = new Set(["OWN_WORK", "OWN_DEPARTMENT"]);
const PAGE_TABS = new Set<PageTab>(["privileges", "rules"]);
const DEFAULT_BATCH_RATIONALE = "Batch grant for governed audit assignment eligibility.";
const QUICK_RATIONALE = {
  SUSPEND: "Suspended via People authorization board quick action.",
  REVOKE: "Revoked via People authorization board quick action.",
  REINSTATE: "Reinstated via People authorization board quick action.",
} as const;
const PURGEABLE_STATUSES: QmsPrivilege["status"][] = ["REVOKED", "EXPIRED", "DRAFT"];
const MAX_CONCURRENT_OPTIONS = ["", "1", "2", "3", "5", "10"] as const;

type EligibilityErrorDetail = {
  message?: unknown;
  eligibility?: { hard_gates?: Record<string, boolean>; training?: { missing?: string[] } };
  current_status?: unknown;
  decision_type?: unknown;
};

function formatEligibilityDetail(detail: EligibilityErrorDetail): string | null {
  if (!detail || typeof detail !== "object") return null;
  const message = typeof detail.message === "string" ? detail.message.trim() : "";
  const gates = detail.eligibility?.hard_gates || {};
  const failed = Object.entries(gates)
    .filter(([key, passed]) => !passed && key !== "active_privilege" && key !== "independence" && key !== "selected_privilege_active")
    .map(([key]) => humanise(key));
  const missing = detail.eligibility?.training?.missing || [];
  if (!message && !failed.length && !missing.length) return null;
  const parts = [message || "Privilege decision was blocked."];
  if (failed.length) parts.push(`Failed gates: ${failed.join(", ")}.`);
  if (missing.length) parts.push(`Missing training: ${missing.join(", ")}.`);
  if (typeof detail.current_status === "string" && typeof detail.decision_type === "string") {
    parts.push(`Current status ${humanise(detail.current_status)} cannot accept ${humanise(detail.decision_type)}.`);
  }
  return parts.join(" ");
}

function messageFromError(error: unknown): string {
  if (error instanceof ApiClientError) {
    const body = error.body;
    if (body && typeof body === "object") {
      const detail = (body as { detail?: unknown }).detail;
      if (typeof detail === "string" && detail.trim()) return detail.trim();
      if (detail && typeof detail === "object") {
        const formatted = formatEligibilityDetail(detail as EligibilityErrorDetail);
        if (formatted) return formatted;
      }
    }
  }
  if (!(error instanceof Error)) return "The People & Privileges operation could not be completed.";
  const raw = error.message.trim();
  if (!raw) return "The People & Privileges operation could not be completed.";
  try {
    const parsed = JSON.parse(raw) as EligibilityErrorDetail;
    const formatted = formatEligibilityDetail(parsed);
    if (formatted) return formatted;
  } catch {
    /* plain string error */
  }
  return raw;
}

function adjustPrivilegeSummary(
  summary: QmsPeopleSummary,
  from: QmsPrivilege["status"] | null,
  to: QmsPrivilege["status"] | null,
): QmsPeopleSummary {
  let active = summary.active_privileges;
  let suspended = summary.suspended_privileges;
  if (from === "ACTIVE") active = Math.max(0, active - 1);
  if (from === "SUSPENDED") suspended = Math.max(0, suspended - 1);
  if (to === "ACTIVE") active += 1;
  if (to === "SUSPENDED") suspended += 1;
  return { ...summary, active_privileges: active, suspended_privileges: suspended };
}

function ruleIsSupervisedDevelopment(rule: QmsPrivilegeRule): boolean {
  return Boolean((rule.scope_schema as { supervised_development?: boolean } | undefined)?.supervised_development);
}

function isObserverTraineeRule(rule: QmsPrivilegeRule): boolean {
  return rule.privilege_type === "AUDITOR" && ruleIsSupervisedDevelopment(rule);
}

function isFullAuditorRule(rule: QmsPrivilegeRule): boolean {
  return rule.privilege_type === "AUDITOR" && !ruleIsSupervisedDevelopment(rule);
}

function isAuditorRankRule(rule: QmsPrivilegeRule): boolean {
  return rule.privilege_type === "AUDITOR" || rule.privilege_type === "LEAD_AUDITOR";
}

function findActiveAuditorPrivilege(
  items: QmsPrivilege[],
  rules: QmsPrivilegeRule[],
  userId: string,
): QmsPrivilege | null {
  return (
    items.find((item) => {
      if (item.user_id !== userId || item.status !== "ACTIVE") return false;
      const rule = rules.find((entry) => entry.id === item.rule_id);
      return Boolean(rule && isAuditorRankRule(rule));
    }) || null
  );
}

function privilegeRankLabel(privilege: QmsPrivilege, rules: QmsPrivilegeRule[]): string {
  const rule = rules.find((entry) => entry.id === privilege.rule_id);
  if (rule) return rule.title;
  return humanise(privilege.privilege_code);
}

function humanise(value: string): string {
  return value.replaceAll("_", " ").toLowerCase().replace(/\b\w/g, (letter) => letter.toUpperCase());
}

function dateLabel(value?: string | null): string {
  if (!value) return "Not set";
  const parsed = new Date(`${value}T00:00:00`);
  if (Number.isNaN(parsed.getTime())) return value;
  return parsed.toLocaleDateString(undefined, { day: "numeric", month: "short", year: "numeric" });
}

function localDateKey(date = new Date()): string {
  const month = String(date.getMonth() + 1).padStart(2, "0");
  const day = String(date.getDate()).padStart(2, "0");
  return `${date.getFullYear()}-${month}-${day}`;
}

function isExpiringSoon(item: QmsPrivilege): boolean {
  if (!item.expires_on || item.status !== "ACTIVE") return false;
  return new Date(`${item.expires_on}T23:59:59`).getTime() <= Date.now() + 60 * 86400000;
}

function selectedAssignmentAssessment(
  result: QmsAuditorEligibilityPreflight | null,
  rule: QmsPrivilegeRule | null,
): QmsAuditorAssignmentAssessment | null {
  if (!result || !rule) return null;
  if (result.assessment?.rule_id === rule.id) return result.assessment;
  return result.assessments.find((assessment) => assessment.rule_id === rule.id) || null;
}

function trainingCodesLabel(codes: string[]): string {
  return codes.length ? codes.join(", ") : "None";
}

function privilegeMatchesRankFilter(
  item: QmsPrivilege,
  rules: QmsPrivilegeRule[],
  rankFilter: RankFilter,
): boolean {
  if (rankFilter === "ALL") return true;
  if (rankFilter === "SUSPENDED") return item.status === "SUSPENDED";
  if (rankFilter === "EXPIRING") return isExpiringSoon(item);
  const rule = rules.find((entry) => entry.id === item.rule_id);
  if (!rule) return false;
  if (rankFilter === "LEAD") return rule.privilege_type === "LEAD_AUDITOR";
  if (rankFilter === "AUDITOR") return isFullAuditorRule(rule);
  if (rankFilter === "OBSERVER") return isObserverTraineeRule(rule);
  if (rankFilter === "INSPECTOR") return rule.privilege_type === "QUALITY_INSPECTOR";
  return true;
}

function actionTitle(mode: ActionMode): string {
  if (mode === "CREATE") return "Authorize people";
  if (mode === "DECISION") return "Record decision";
  if (mode === "AUDIT_ASSIGNMENT") return "Assignment check";
  if (mode === "CREATE_RULE") return "Create privilege rule";
  if (mode === "EDIT_RULE") return "Edit privilege rule";
  if (mode === "INDEPENDENCE_POLICY") return "Independence rules";
  return "Record impartiality form";
}

function hasHardIndependenceConflict(conflicts: QmsIndependenceConflict[] | undefined | null): boolean {
  return Boolean(conflicts?.some((item) => HARD_INDEPENDENCE_CODES.has(String(item.code || "").toUpperCase())));
}

function IndependenceFeedback({
  conflicts,
  remediations,
  message,
  notes,
}: {
  conflicts?: QmsIndependenceConflict[] | null;
  remediations?: QmsIndependenceRemediation[] | null;
  message?: string | null;
  notes?: string[] | null;
}) {
  const conflictRows = conflicts || [];
  const remediationRows = remediations || [];
  const noteRows = notes || [];
  if (!conflictRows.length && !remediationRows.length && !message && !noteRows.length) return null;
  return (
    <div className="qms-people__independence-feedback">
      {message ? <p className="qms-people__independence-message">{message}</p> : null}
      {conflictRows.length ? (
        <ul className="qms-people__independence-conflicts">
          {conflictRows.map((item) => (
            <li key={`${item.code}-${item.title}`} className={item.severity === "hard" ? "is-hard" : "is-warning"}>
              <strong>{item.title || humanise(item.code)}</strong>
              <span>{item.message}</span>
            </li>
          ))}
        </ul>
      ) : null}
      {remediationRows.length ? (
        <ul className="qms-people__independence-remediations">
          {remediationRows.map((item) => (
            <li key={item.code}>
              <strong>{item.label}</strong>
              <span>{item.detail}</span>
            </li>
          ))}
        </ul>
      ) : null}
      {noteRows.length ? (
        <ul className="qms-people__independence-notes">
          {noteRows.map((note) => (
            <li key={note}>{note}</li>
          ))}
        </ul>
      ) : null}
    </div>
  );
}

type RuleIconTone = "lead" | "auditor" | "observer" | "inspector" | "reviewer" | "custom";

function ruleIconTone(rule: QmsPrivilegeRule | null | undefined): RuleIconTone {
  if (!rule) return "custom";
  if (rule.privilege_type === "LEAD_AUDITOR") return "lead";
  if (rule.privilege_type === "QUALITY_INSPECTOR") return "inspector";
  if (rule.privilege_type === "AUTHORIZATION_REVIEWER") return "reviewer";
  if (rule.privilege_type === "CUSTOM") return "custom";
  if (isObserverTraineeRule(rule)) return "observer";
  if (rule.privilege_type === "AUDITOR") return "auditor";
  return "custom";
}

function RuleTypeIcon({ tone, size = 14 }: { tone: RuleIconTone; size?: number }) {
  const Icon =
    tone === "lead" ? Crown
      : tone === "auditor" ? BadgeCheck
        : tone === "observer" ? Eye
          : tone === "inspector" ? ClipboardCheck
            : tone === "reviewer" ? FileBadge
              : Shield;
  return (
    <span className={`qms-people__row-icon qms-people__row-icon--${tone}`} aria-hidden="true">
      <Icon size={size} strokeWidth={2.1} />
    </span>
  );
}

function statusToneClass(status: string, active?: boolean): string {
  if (typeof active === "boolean") return active ? "qms-people__status--active" : "qms-people__status--suspended";
  const key = status.toLowerCase();
  if (key === "active") return "qms-people__status--active";
  if (key === "draft") return "qms-people__status--draft";
  if (key === "suspended" || key === "inactive") return "qms-people__status--suspended";
  if (key === "revoked" || key === "expired") return `qms-people__status--${key}`;
  return "qms-people__status--draft";
}

function StatusPill({
  label,
  status,
  active,
  title,
  onActivate,
}: {
  label: string;
  status?: string;
  active?: boolean;
  title?: string;
  onActivate?: () => void;
}) {
  const tone = typeof active === "boolean" ? (active ? "active" : "inactive") : (status || "").toLowerCase();
  const Icon =
    tone === "active" ? CheckCircle2
      : tone === "draft" ? HelpCircle
      : tone === "suspended" || tone === "inactive" ? PauseCircle
        : tone === "revoked" || tone === "expired" ? Ban
          : FileText;
  const className = `qms-people__status ${statusToneClass(status || "", active)}${onActivate ? " is-actionable" : ""}`;
  if (onActivate) {
    return (
      <button
        type="button"
        className={className}
        title={title || label}
        onClick={(event) => {
          event.stopPropagation();
          onActivate();
        }}
      >
        <Icon size={12} aria-hidden="true" strokeWidth={2.2} />
        {label}
      </button>
    );
  }
  return (
    <span className={className} title={title}>
      <Icon size={12} aria-hidden="true" strokeWidth={2.2} />
      {label}
    </span>
  );
}

function personInitials(name: string): string {
  const parts = name.trim().split(/\s+/).filter(Boolean);
  if (!parts.length) return "?";
  if (parts.length === 1) return parts[0].slice(0, 2).toUpperCase();
  return `${parts[0][0] || ""}${parts[parts.length - 1][0] || ""}`.toUpperCase();
}

function PersonCell({ name }: { name: string }) {
  return (
    <div className="qms-people__person-cell">
      <span className="qms-people__avatar" aria-hidden="true">{personInitials(name)}</span>
      <div className="qms-people__cell-stack">
        <span className="qms-people__cell-main">{name}</span>
      </div>
    </div>
  );
}

function PeopleCountCell({ active, total }: { active: number; total: number }) {
  return (
    <div className="qms-people__people-cell">
      <Users size={14} className="qms-people__inline-icon" aria-hidden="true" />
      <div className="qms-people__cell-stack">
        <span className="qms-people__cell-main">{active} active</span>
        <span className="qms-people__cell-sub">{total} total</span>
      </div>
    </div>
  );
}

function ExpiryCell({ expiresOn }: { expiresOn?: string | null }) {
  if (!expiresOn) {
    return <span className="qms-people__cell-sub">No expiry</span>;
  }
  return (
    <span className="qms-people__expiry-cell">
      <CalendarClock size={14} className="qms-people__inline-icon" aria-hidden="true" />
      <span className="qms-people__cell-main">{dateLabel(expiresOn)}</span>
    </span>
  );
}

const METRIC_CHIP_ICONS: Record<Exclude<RankFilter, "ALL">, typeof Crown> = {
  LEAD: Crown,
  AUDITOR: UserCheck,
  OBSERVER: Eye,
  INSPECTOR: ClipboardCheck,
  SUSPENDED: PauseCircle,
  EXPIRING: CalendarClock,
};

const QmsPeoplePage: React.FC<Props> = ({ amoCode }) => {
  const [searchParams, setSearchParams] = useSearchParams();
  const deepLinkConsumed = useRef(false);
  const [pageTab, setPageTab] = useState<PageTab>("privileges");
  const [summary, setSummary] = useState<QmsPeopleSummary>(EMPTY_SUMMARY);
  const [rules, setRules] = useState<QmsPrivilegeRule[]>([]);
  const [privileges, setPrivileges] = useState<QmsPrivilege[]>([]);
  const [personnel, setPersonnel] = useState<QMSPersonOption[]>([]);
  const [independenceRows, setIndependenceRows] = useState<QmsIndependenceDeclaration[]>([]);
  const [independencePolicy, setIndependencePolicy] = useState<QmsIndependencePolicy | null>(null);
  const [independenceAssessment, setIndependenceAssessment] = useState<QmsIndependenceAssessment | null>(null);
  const [independenceLoading, setIndependenceLoading] = useState(false);
  const [policyBusy, setPolicyBusy] = useState(false);
  const [trainingCourses, setTrainingCourses] = useState<TrainingCourseRead[]>([]);
  const [auditParticipation, setAuditParticipation] = useState<QmsPersonAuditParticipationItem[]>([]);
  const [auditParticipationLoading, setAuditParticipationLoading] = useState(false);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState("");
  const { actionFlash, flashAction, clearActionFlash } = useActionFlash(2200);
  const [purgeFarewell, setPurgeFarewell] = useState<QmsPrivilege | null>(null);
  const [statusFilter, setStatusFilter] = useState<QmsPrivilege["status"] | "ALL">("ALL");
  const [rankFilter, setRankFilter] = useState<RankFilter>("ALL");
  const [search, setSearch] = useState("");
  const [showInactiveRules, setShowInactiveRules] = useState(true);
  const [actionMode, setActionMode] = useState<ActionMode>("NONE");
  const [confirmDialog, setConfirmDialog] = useState<ConfirmDialog | null>(null);

  const [ruleId, setRuleId] = useState("");
  const [userIds, setUserIds] = useState<string[]>([]);
  const [personQuery, setPersonQuery] = useState("");
  const [scopeKey, setScopeKey] = useState("GLOBAL");
  const [grantOnCreate, setGrantOnCreate] = useState(true);
  const [batchRationale, setBatchRationale] = useState(DEFAULT_BATCH_RATIONALE);
  const [creating, setCreating] = useState(false);
  const [authorizeCandidates, setAuthorizeCandidates] = useState<QmsAuthorizationCandidate[]>([]);
  const [authorizeMatchMode, setAuthorizeMatchMode] = useState<string>("none");
  const [authorizeTrainingCodes, setAuthorizeTrainingCodes] = useState<string[]>([]);
  const [authorizeCandidatesLoading, setAuthorizeCandidatesLoading] = useState(false);

  const [selectedId, setSelectedId] = useState("");
  const [selectedRuleId, setSelectedRuleId] = useState("");
  const [decisionType, setDecisionType] = useState<QmsPrivilegeDecision["decision_type"]>("GRANT");
  const [decisionReason, setDecisionReason] = useState("");
  const [effectiveFrom, setEffectiveFrom] = useState("");
  const [expiresOn, setExpiresOn] = useState("");
  const [deciding, setDeciding] = useState(false);
  const [lifecycleBusy, setLifecycleBusy] = useState(false);
  const [evidenceBusy, setEvidenceBusy] = useState(false);
  const evidenceInputRef = useRef<HTMLInputElement | null>(null);
  const [bypassRationale, setBypassRationale] = useState("");
  const [bypassUntil, setBypassUntil] = useState("");
  const [bypassBusy, setBypassBusy] = useState(false);
  const [showBypassForm, setShowBypassForm] = useState(false);
  const [deletingRule, setDeletingRule] = useState(false);
  const [personnelLoading, setPersonnelLoading] = useState(false);

  const [ruleCode, setRuleCode] = useState("");
  const [ruleTitle, setRuleTitle] = useState("");
  const [ruleType, setRuleType] = useState<QmsPrivilegeRule["privilege_type"]>("LEAD_AUDITOR");
  const [ruleDescription, setRuleDescription] = useState("");
  const [ruleTrainingCodes, setRuleTrainingCodes] = useState<string[]>([]);
  const [ruleTrainingJoin, setRuleTrainingJoin] = useState<TrainingRuleJoin>("AND");
  const [ruleTrainingExpression, setRuleTrainingExpression] = useState("");
  const [ruleTrainingAdvanced, setRuleTrainingAdvanced] = useState(false);
  const [ruleTrainingNotice, setRuleTrainingNotice] = useState<string | null>(null);
  const [ruleTrainingExpressionError, setRuleTrainingExpressionError] = useState<string | null>(null);
  const [ruleFormBaselineScope, setRuleFormBaselineScope] = useState<Record<string, unknown>>({});
  const [ruleIndependenceRequired, setRuleIndependenceRequired] = useState(true);
  const [ruleMaxConcurrent, setRuleMaxConcurrent] = useState("");
  const [ruleSupervisedDevelopment, setRuleSupervisedDevelopment] = useState(false);
  const [ruleActive, setRuleActive] = useState(true);
  const [savingRule, setSavingRule] = useState(false);

  const [selectedSnapshot, setSelectedSnapshot] = useState<QmsEligibility | null>(null);
  const selectedSnapshotRef = useRef<QmsEligibility | null>(null);
  selectedSnapshotRef.current = selectedSnapshot;
  const [snapshotLoading, setSnapshotLoading] = useState(false);
  const [snapshotRevision, setSnapshotRevision] = useState(0);

  const [assignmentResult, setAssignmentResult] = useState<QmsAuditorEligibilityPreflight | null>(null);
  const [assignmentResultInput, setAssignmentResultInput] = useState<AssignmentSubmission | null>(null);
  const [assignmentRole, setAssignmentRole] = useState<QmsAuditorAssignmentRole>("OBSERVER_AUDITOR");
  const [assignmentDate, setAssignmentDate] = useState(localDateKey());
  const [assignmentScopeKey, setAssignmentScopeKey] = useState("");
  const [assignmentContextType, setAssignmentContextType] = useState<AssignmentContextType>("");
  const [assignmentContextId, setAssignmentContextId] = useState("");
  const [checkingAssignment, setCheckingAssignment] = useState(false);
  const assignmentRequestRevision = useRef(0);

  const [indUserId, setIndUserId] = useState("");
  const [indContextType, setIndContextType] = useState<"AUDIT" | "AUDIT_SCHEDULE" | "PROGRAMME_ITEM" | "ASSURANCE_CASE" | "MISSION" | "OTHER">("AUDIT_SCHEDULE");
  const [indContextId, setIndContextId] = useState("");
  const [indDeclaration, setIndDeclaration] = useState<"INDEPENDENT" | "CONFLICT" | "REQUIRES_REVIEW">("REQUIRES_REVIEW");
  const [indRelationship, setIndRelationship] = useState("");
  const [indRationale, setIndRationale] = useState("");
  const [declaring, setDeclaring] = useState(false);
  const platformSuperuser = isPlatformSuperuser();

  const personLabelById = useMemo(() => {
    const map = new Map<string, string>();
    for (const person of personnel) {
      map.set(person.id, personDisplay(person.full_name));
    }
    for (const privilege of privileges) {
      if (!map.has(privilege.user_id) && privilege.person_name) map.set(privilege.user_id, personDisplay(privilege.person_name));
    }
    return map;
  }, [personnel, privileges]);

  const loadPersonnel = useCallback(async (signal?: AbortSignal, options: { bypassCache?: boolean; search?: string } = {}) => {
    setPersonnelLoading(true);
    try {
      const personnelResponse = await qmsListAuditPersonnelOptions(
        amoCode,
        { limit: 200, search: options.search, auditorsOnly: false, bypassCache: options.bypassCache },
        signal,
      );
      if (signal?.aborted) return;
      setPersonnel(personnelResponse);
    } catch (nextError) {
      if (!(nextError instanceof DOMException && nextError.name === "AbortError") && !signal?.aborted) {
        setError((current) => current || `Personnel directory unavailable: ${messageFromError(nextError)}`);
      }
    } finally {
      setPersonnelLoading(false);
    }
  }, [amoCode]);

  const loadTrainingCourses = useCallback(async (signal?: AbortSignal) => {
    try {
      const courses = await listTrainingCourses({ include_inactive: false, limit: 300 });
      if (signal?.aborted) return;
      setTrainingCourses(courses);
    } catch (nextError) {
      if (signal?.aborted || (nextError instanceof DOMException && nextError.name === "AbortError")) return;
      setTrainingCourses([]);
      setError((current) => current || `Training catalogue unavailable: ${messageFromError(nextError)}`);
    }
  }, []);

  useEffect(() => {
    if (actionMode !== "CREATE" || !ruleId) {
      setAuthorizeCandidates([]);
      setAuthorizeMatchMode("none");
      setAuthorizeTrainingCodes([]);
      setAuthorizeCandidatesLoading(false);
      return;
    }
    const controller = new AbortController();
    setAuthorizeCandidatesLoading(true);
    const searchNeedle = personQuery.trim();
    const delayMs = searchNeedle ? 120 : 0;
    const timer = window.setTimeout(() => {
      void listQmsAuthorizationCandidates(
        amoCode,
        { ruleId, search: searchNeedle || undefined, limit: 200 },
        controller.signal,
      )
        .then((response) => {
          if (controller.signal.aborted) return;
          setAuthorizeCandidates(response.items);
          setAuthorizeMatchMode(response.match_mode || "none");
          setAuthorizeTrainingCodes(response.training_codes || []);
          setUserIds((current) => current.filter((id) => response.items.some((person) => person.id === id)));
        })
        .catch((nextError) => {
          if (controller.signal.aborted || (nextError instanceof DOMException && nextError.name === "AbortError")) return;
          setAuthorizeCandidates([]);
          setError(`Authorization candidates: ${messageFromError(nextError)}`);
        })
        .finally(() => {
          if (!controller.signal.aborted) setAuthorizeCandidatesLoading(false);
        });
    }, delayMs);
    return () => {
      window.clearTimeout(timer);
      controller.abort();
    };
  }, [actionMode, amoCode, ruleId, personQuery]);

  useEffect(() => {
    const controller = new AbortController();
    void loadTrainingCourses(controller.signal);
    return () => controller.abort();
  }, [loadTrainingCourses]);

  const loadGenerationRef = useRef(0);

  const load = useCallback(async (signal?: AbortSignal, options?: { soft?: boolean; refresh?: boolean }) => {
    const generation = ++loadGenerationRef.current;
    const soft = options?.soft === true;
    const shouldRefresh = options?.refresh !== false;
    // Soft reloads still need a fresh list — otherwise create/grant leaves the register stale
    // until the user hits Refresh (GET cache TTL is several seconds).
    if (shouldRefresh) {
      clearQmsApiResponseCache();
      if (!soft) invalidateQmsEligibilityMemory(amoCode);
    }
    if (!soft) setLoading(true);
    setError("");
    if (!soft) void loadPersonnel(signal, { bypassCache: shouldRefresh });
    try {
      const [summaryResult, rulesResult, privilegesResult, policyResult] = await Promise.allSettled([
        getQmsPeopleSummary(amoCode, signal),
        listQmsPrivilegeRules(amoCode, { includeInactive: true }, signal),
        listQmsPrivileges(amoCode, {}, signal).then((response) => {
          if (!signal?.aborted && generation === loadGenerationRef.current) {
            setPrivileges(response.items);
            setSelectedId((value) => response.items.some((item) => item.id === value) ? value : response.items[0]?.id || "");
            setLoading(false);
          }
          return response;
        }),
        getQmsIndependencePolicy(amoCode, signal),
      ]);
      if (signal?.aborted || generation !== loadGenerationRef.current) return;
      const failures: string[] = [];
      if (summaryResult.status === "fulfilled") {
        setSummary(summaryResult.value);
      } else if (!(summaryResult.reason instanceof DOMException && summaryResult.reason.name === "AbortError")) {
        failures.push(`Summary: ${messageFromError(summaryResult.reason)}`);
      }
      if (rulesResult.status === "fulfilled") {
        const ruleResponse = rulesResult.value;
        setRules(ruleResponse.items);
        setRuleId((value) => value || ruleResponse.items.find((item) => item.is_active)?.id || ruleResponse.items[0]?.id || "");
        setSelectedRuleId((value) => value && ruleResponse.items.some((item) => item.id === value) ? value : ruleResponse.items.find((item) => item.is_active)?.id || ruleResponse.items[0]?.id || "");
      } else if (!(rulesResult.reason instanceof DOMException && rulesResult.reason.name === "AbortError")) {
        failures.push(`Rules: ${messageFromError(rulesResult.reason)}`);
      }
      if (privilegesResult.status === "fulfilled") {
        const privilegeResponse = privilegesResult.value;
        setPrivileges(privilegeResponse.items);
        setSelectedId((value) => value && privilegeResponse.items.some((item) => item.id === value) ? value : privilegeResponse.items[0]?.id || "");
      } else if (!(privilegesResult.reason instanceof DOMException && privilegesResult.reason.name === "AbortError")) {
        failures.push(`Privileges: ${messageFromError(privilegesResult.reason)}`);
      }
      if (policyResult.status === "fulfilled") {
        setIndependencePolicy(policyResult.value);
      } else if (!(policyResult.reason instanceof DOMException && policyResult.reason.name === "AbortError")) {
        failures.push(`Independence policy: ${messageFromError(policyResult.reason)}`);
      }
      if (failures.length && !soft) setError(failures.join(" · "));
      // Soft reloads must not force eligibility re-fetch (that made every CTA feel like 5–10s).
      if (!soft) {
        setSnapshotRevision((value) => value + 1);
      }
    } catch (nextError) {
      if (!(nextError instanceof DOMException && nextError.name === "AbortError") && generation === loadGenerationRef.current && !soft) {
        setError(messageFromError(nextError));
      }
    } finally {
      if (!soft && generation === loadGenerationRef.current) setLoading(false);
    }
  }, [amoCode, loadPersonnel]);

  useEffect(() => {
    const controller = new AbortController();
    void load(controller.signal, { refresh: false });
    return () => controller.abort();
  }, [load]);

  const selected = privileges.find((item) => item.id === selectedId) || (actionFlash === "PURGE" ? purgeFarewell : null);
  const selectedRule = selected ? rules.find((rule) => rule.id === selected.rule_id) || null : null;
  const catalogRule = selectedRule || rules.find((rule) => rule.id === selectedRuleId) || null;
  const selectedIsAuditorPrivilege = selectedRule?.privilege_type === "AUDITOR" || selectedRule?.privilege_type === "LEAD_AUDITOR";
  const canManagePrivileges = hasQmsRolePermission("qms.training.manage");
  const canManageAuditGovernance = hasQmsRolePermission("qms.audit.manage");
  const canRunAuditPreflight = selectedIsAuditorPrivilege && canManageAuditGovernance && selected?.status === "ACTIVE";
  const assignmentContextRequired = Boolean(selectedRule?.independence_required);
  const assignmentInputComplete = Boolean(
    selected
    && selectedRule
    && assignmentDate
    && assignmentScopeKey.trim()
    && (!assignmentContextRequired || (assignmentContextType && assignmentContextId.trim())),
  );
  const allowedDecisions = selected ? allowedPrivilegeDecisions(selected.status) : [];

  const invalidateAssignmentResult = useCallback(() => {
    assignmentRequestRevision.current += 1;
    setAssignmentResult(null);
    setAssignmentResultInput(null);
  }, []);

  useEffect(() => {
    invalidateAssignmentResult();
    setCheckingAssignment(false);
    setAssignmentRole(selectedRule?.privilege_type === "LEAD_AUDITOR" ? "LEAD_AUDITOR" : "OBSERVER_AUDITOR");
    setAssignmentDate(localDateKey());
    setAssignmentScopeKey(selected?.scope_key && !["GLOBAL", "*"].includes(selected.scope_key.toUpperCase()) ? selected.scope_key : "");
    setAssignmentContextType("");
    setAssignmentContextId("");
  }, [invalidateAssignmentResult, selected?.id, selected?.scope_key, selectedRule?.privilege_type]);

  useEffect(() => {
    if (!selected?.id || !selected.user_id || !selected.privilege_code) {
      setSelectedSnapshot(null);
      setIndependenceRows([]);
      setIndependenceAssessment(null);
      setSnapshotLoading(false);
      setIndependenceLoading(false);
      return;
    }
    const controller = new AbortController();
    const privilegeId = selected.id;
    const userId = selected.user_id;
    const privilegeCode = (selectedRule?.privilege_code || selected.privilege_code).trim().toUpperCase();
    const privilegeSnapshot = selected;

    // Instant paint from memory when available; otherwise keep prior same-person chips.
    const cached = peekQmsEligibility(amoCode, userId, privilegeCode);
    const samePerson = selectedSnapshotRef.current?.person.user_id === userId;
    if (cached) {
      setSelectedSnapshot(bindEligibilityToPrivilege(cached, privilegeSnapshot));
      setSnapshotLoading(false);
    } else if (!samePerson) {
      setSelectedSnapshot(null);
      setSnapshotLoading(true);
    } else {
      setSnapshotLoading(true);
    }
    setIndependenceLoading(true);

    const contextApplies =
      assignmentResultInput !== null
      && assignmentResultInput.selected_privilege_id === privilegeId
      && Boolean(assignmentResultInput.context_type)
      && Boolean(assignmentResultInput.context_id);
    const assignmentContext = contextApplies
      ? {
          contextType: assignmentResultInput.context_type,
          contextId: assignmentResultInput.context_id,
          assignmentScopeKey: assignmentResultInput.assignment_scope_key || undefined,
        }
      : {};

    // Eligibility first — pills must not wait on independence endpoints.
    void getQmsEligibility(
      amoCode,
      { userId, privilegeCode },
      controller.signal,
    )
      .then((snapshot) => {
        if (controller.signal.aborted) return;
        setSelectedSnapshot(bindEligibilityToPrivilege(snapshot, privilegeSnapshot));
      })
      .catch((nextError) => {
        if (controller.signal.aborted || (nextError instanceof DOMException && nextError.name === "AbortError")) return;
        if (!cached) setSelectedSnapshot(null);
        setError((current) => current || `Eligibility: ${messageFromError(nextError)}`);
      })
      .finally(() => {
        if (!controller.signal.aborted) setSnapshotLoading(false);
      });

    // Defer secondary panels one frame so the first paint can commit pills.
    const deferId = window.setTimeout(() => {
      if (controller.signal.aborted) return;
      void listQmsIndependenceDeclarations(amoCode, { userId }, controller.signal)
        .then((independence) => {
          if (!controller.signal.aborted) setIndependenceRows(independence.items);
        })
        .catch(() => {
          if (!controller.signal.aborted) setIndependenceRows([]);
        });

      void assessQmsIndependence(amoCode, { userId, ...assignmentContext }, controller.signal)
        .then((assessment) => {
          if (!controller.signal.aborted) setIndependenceAssessment(assessment);
        })
        .catch(() => {
          if (!controller.signal.aborted) setIndependenceAssessment(null);
        })
        .finally(() => {
          if (!controller.signal.aborted) setIndependenceLoading(false);
        });
    }, 0);

    return () => {
      controller.abort();
      window.clearTimeout(deferId);
    };
  }, [
    amoCode,
    selected?.id,
    selected?.user_id,
    selected?.privilege_code,
    selected?.rule_id,
    selected?.status,
    selectedRule?.privilege_code,
    snapshotRevision,
    assignmentResultInput,
  ]);

  useEffect(() => {
    if (actionMode !== "DECISION") return;
    if (decisionType !== "GRANT" && decisionType !== "RENEW" && decisionType !== "REINSTATE") return;
    if (!selectedSnapshot) return;
    const courseCap = earliestCompetenceValidUntil(selectedSnapshot.training);
    if (!courseCap) return;
    setExpiresOn((current) => {
      if (!current) return courseCap;
      return current <= courseCap ? current : courseCap;
    });
  }, [actionMode, decisionType, selectedSnapshot]);

  useEffect(() => {
    if (!selected?.user_id) {
      setAuditParticipation([]);
      setAuditParticipationLoading(false);
      return;
    }
    const controller = new AbortController();
    setAuditParticipationLoading(true);
    setAuditParticipation([]);
    void getQmsPersonAuditParticipation(amoCode, selected.user_id, controller.signal)
      .then((response) => {
        if (!controller.signal.aborted) setAuditParticipation(response.items || []);
      })
      .catch((nextError) => {
        if (!(nextError instanceof DOMException && nextError.name === "AbortError") && !controller.signal.aborted) {
          setAuditParticipation([]);
        }
      })
      .finally(() => {
        if (!controller.signal.aborted) setAuditParticipationLoading(false);
      });
    return () => controller.abort();
  }, [amoCode, selected?.user_id]);

  const [expiringOnly, setExpiringOnly] = useState(false);
  const visiblePrivileges = useMemo(() => {
    const needle = search.trim().toLowerCase();
    return privileges.filter((item) => {
      if (!privilegeMatchesRankFilter(item, rules, rankFilter)) return false;
      if (rankFilter === "ALL" && statusFilter !== "ALL" && item.status !== statusFilter) return false;
      if (rankFilter === "ALL" && expiringOnly && !isExpiringSoon(item)) return false;
      if (!needle) return true;
      const personLabel = personLabelById.get(item.user_id) || "";
      const rankLabel = privilegeRankLabel(item, rules);
      return [personLabel, rankLabel, item.privilege_code, item.scope_key].some((value) => value.toLowerCase().includes(needle));
    });
  }, [privileges, search, statusFilter, personLabelById, expiringOnly, rules, rankFilter]);

  // Eligibility can perform server-side currency/independence checks. Load only
  // the selected person; speculative scans of twelve people competed with navigation.

  const visibleRules = useMemo(() => {
    const needle = search.trim().toLowerCase();
    return rules.filter((rule) => {
      if (!showInactiveRules && !rule.is_active) return false;
      if (!needle) return true;
      return [rule.title, rule.privilege_code, rule.privilege_type].some((value) => value.toLowerCase().includes(needle));
    });
  }, [rules, search, showInactiveRules]);

  const assignmentResultAppliesToSelection = Boolean(
    assignmentResult
    && assignmentResultInput
    && selected
    && assignmentResultInput.selected_privilege_id === selected.id,
  );
  const assignmentAssessment = assignmentResultAppliesToSelection ? selectedAssignmentAssessment(assignmentResult, selectedRule) : null;
  const assignmentUsesSelectedPrivilege = Boolean(selected && assignmentAssessment?.active_privilege?.id === selected.id);
  const assignmentEligible = Boolean(assignmentResultAppliesToSelection && assignmentResult?.eligible && assignmentAssessment?.eligible && assignmentUsesSelectedPrivilege);
  const independenceConflicts = independenceAssessment?.conflicts || [];
  const independenceHardBlocked = hasHardIndependenceConflict(independenceConflicts);
  const impartialityRemediationOffered = Boolean(
    independenceAssessment?.remediations?.some((item) => String(item.code || "").toUpperCase() === "IMPARTIALITY_FORM"),
  );
  const allowImpartialityForm = Boolean(
    (independenceAssessment?.policy?.allow_impartiality_form ?? independencePolicy?.allow_impartiality_form ?? true)
    && !independenceHardBlocked
    && impartialityRemediationOffered
    && (independenceAssessment?.passed === false || independenceConflicts.length > 0),
  );
  const canRecordImpartialityForm = Boolean(canManageAuditGovernance && allowImpartialityForm && selected);

  function personLabel(userIdValue: string): string {
    return personLabelById.get(userIdValue) || "Person unavailable";
  }

  function toggleRankFilter(next: RankFilter) {
    setPageTab("privileges");
    setRankFilter((current) => (current === next ? "ALL" : next));
  }

  function applyPrivilegeTypePreset(type: QmsPrivilegeRule["privilege_type"]) {
    setRuleType(type);
    setRuleTrainingNotice(null);
    setRuleTrainingExpressionError(null);
    setRuleTrainingAdvanced(false);
    setRuleTrainingJoin("AND");
    if (type === "LEAD_AUDITOR") {
      setRuleCode("LEAD_AUDITOR_GLOBAL");
      setRuleTitle("Lead auditor");
      setRuleIndependenceRequired(true);
      setRuleSupervisedDevelopment(false);
      const codes = defaultTrainingCodesForPrivilegeType("LEAD_AUDITOR");
      setRuleTrainingCodes(codes);
      setRuleTrainingExpression(defaultTrainingExpression(codes, "AND"));
      setRuleFormBaselineScope(defaultCompetenceScopeForPrivilegeType("LEAD_AUDITOR"));
    } else if (type === "AUDITOR") {
      setRuleCode("AUDITOR_GLOBAL");
      setRuleTitle("Auditor");
      setRuleIndependenceRequired(true);
      setRuleSupervisedDevelopment(false);
      const codes = defaultTrainingCodesForPrivilegeType("AUDITOR");
      setRuleTrainingCodes(codes);
      setRuleTrainingExpression(defaultTrainingExpression(codes, "AND"));
      setRuleFormBaselineScope(defaultCompetenceScopeForPrivilegeType("AUDITOR"));
    } else if (type === "QUALITY_INSPECTOR") {
      setRuleCode("QUALITY_INSPECTOR_GLOBAL");
      setRuleTitle("Quality inspector");
      setRuleIndependenceRequired(false);
      setRuleSupervisedDevelopment(false);
      setRuleTrainingCodes([]);
      setRuleTrainingExpression("");
      setRuleFormBaselineScope({});
    } else if (type === "AUTHORIZATION_REVIEWER") {
      setRuleCode("AUTHORIZATION_REVIEWER_GLOBAL");
      setRuleTitle("Authorization reviewer");
      setRuleIndependenceRequired(false);
      setRuleSupervisedDevelopment(false);
      setRuleTrainingCodes([]);
      setRuleTrainingExpression("");
      setRuleFormBaselineScope({});
    } else {
      setRuleCode("");
      setRuleTitle("");
      setRuleIndependenceRequired(true);
      setRuleSupervisedDevelopment(false);
      setRuleTrainingCodes([]);
      setRuleTrainingExpression("");
      setRuleFormBaselineScope({});
    }
  }

  function resetRuleForm(rule?: QmsPrivilegeRule | null) {
    const supervised = Boolean((rule?.scope_schema as { supervised_development?: boolean } | undefined)?.supervised_development);
    const codes = ruleConfiguredTrainingCodes(rule);
    const expression = ruleTrainingExpressionFromRule(rule);
    const parsed = expression ? parseTrainingExpression(expression) : null;
    setRuleCode(rule?.privilege_code || "");
    setRuleTitle(rule?.title || "");
    setRuleType(rule?.privilege_type || "LEAD_AUDITOR");
    setRuleDescription(rule?.description || "");
    setRuleTrainingCodes(codes);
    setRuleTrainingJoin(parsed?.ok ? parsed.join : "AND");
    setRuleTrainingExpression(expression);
    setRuleTrainingAdvanced(Boolean(expression && parsed?.ok && parsed.join === "OR"));
    setRuleTrainingNotice(null);
    setRuleTrainingExpressionError(null);
    setRuleFormBaselineScope({ ...((rule?.scope_schema as Record<string, unknown> | undefined) || {}) });
    setRuleIndependenceRequired(rule?.independence_required ?? true);
    setRuleMaxConcurrent(rule?.max_concurrent_assignments ? String(rule.max_concurrent_assignments) : "");
    setRuleSupervisedDevelopment(supervised);
    setRuleActive(rule?.is_active ?? true);
  }

  function seedRuleForm(type: QmsPrivilegeRule["privilege_type"]) {
    resetRuleForm(null);
    applyPrivilegeTypePreset(type);
    setRuleDescription("");
    setRuleMaxConcurrent("");
    setRuleActive(true);
  }

  function syncTrainingExpressionFromCodes(codes: string[], join: TrainingRuleJoin = ruleTrainingJoin) {
    setRuleTrainingExpression(defaultTrainingExpression(codes, join));
    setRuleTrainingExpressionError(null);
  }

  function toggleTrainingCode(courseId: string) {
    const catalogue = trainingCourses.map((course) => normalizeCourseCode(course.course_id));
    const result = toggleTrainingSelectionWithPairs(ruleTrainingCodes, courseId, catalogue);
    setRuleTrainingCodes(result.codes);
    setRuleTrainingNotice(result.notice);
    if (!ruleTrainingAdvanced) {
      syncTrainingExpressionFromCodes(result.codes, ruleTrainingJoin);
      return;
    }
    const parsed = parseTrainingExpression(ruleTrainingExpression);
    if (!parsed.ok || parsed.join === ruleTrainingJoin) {
      syncTrainingExpressionFromCodes(result.codes, ruleTrainingJoin);
    }
  }

  function applyTrainingExpression(nextExpression: string) {
    const parsed = parseTrainingExpression(nextExpression);
    setRuleTrainingExpression(nextExpression);
    if (!parsed.ok) {
      setRuleTrainingExpressionError(parsed.error);
      return;
    }
    setRuleTrainingExpressionError(null);
    setRuleTrainingJoin(parsed.join);
    if (parsed.codes.length) setRuleTrainingCodes(parsed.codes);
  }

  function openAction(
    mode: ActionMode,
    options: { ruleType?: QmsPrivilegeRule["privilege_type"]; ruleId?: string; privilege?: QmsPrivilege } = {},
  ) {
    if ((mode === "CREATE" || mode === "DECISION" || mode === "CREATE_RULE" || mode === "EDIT_RULE") && !canManagePrivileges) return;
    if (mode === "AUDIT_ASSIGNMENT" && !canManageAuditGovernance) return;
    if (mode === "IMPARTIALITY_FORM" && !canManageAuditGovernance) return;
    setError("");
    clearActionFlash();
    if (mode === "AUDIT_ASSIGNMENT") invalidateAssignmentResult();
    if (selected && mode === "IMPARTIALITY_FORM") {
      setIndUserId(selected.user_id);
      setIndDeclaration("REQUIRES_REVIEW");
      if (
        assignmentResultInput?.context_type
        && assignmentResultInput.context_id
        && assignmentResultInput.selected_privilege_id === selected.id
      ) {
        setIndContextType(assignmentResultInput.context_type);
        setIndContextId(assignmentResultInput.context_id);
      }
    }
    const decisionTarget = options.privilege || selected;
    if (mode === "DECISION" && decisionTarget) {
      if (options.privilege) setSelectedId(options.privilege.id);
      setDecisionType(defaultPrivilegeDecision(decisionTarget.status));
      setDecisionReason("");
      setEffectiveFrom("");
      const courseCap = snapshotMatchesSelection && selectedSnapshot
        ? earliestCompetenceValidUntil(selectedSnapshot.training)
        : null;
      setExpiresOn(courseCap || "");
    }
    if (mode === "CREATE") {
      setUserIds([]);
      setPersonQuery("");
      setScopeKey("GLOBAL");
      setGrantOnCreate(true);
      setBatchRationale(DEFAULT_BATCH_RATIONALE);
      const preferredType = options.ruleType;
      const preferredRule =
        (options.ruleId && rules.find((rule) => rule.id === options.ruleId && rule.is_active)) ||
        (preferredType
          ? rules.find((rule) => rule.is_active && rule.privilege_type === preferredType)
          : null) ||
        rules.find((rule) => rule.is_active) ||
        null;
      if (preferredRule) setRuleId(preferredRule.id);
      setAuthorizeCandidates([]);
      setUserIds([]);
    }
    if (mode === "CREATE_RULE") {
      if (options.ruleType) seedRuleForm(options.ruleType);
      else seedRuleForm("LEAD_AUDITOR");
    }
    if (mode === "EDIT_RULE") resetRuleForm(rules.find((rule) => rule.id === selectedRuleId) || catalogRule || null);
    setActionMode(mode);
  }

  function closeAction() {
    if (actionMode === "AUDIT_ASSIGNMENT") {
      invalidateAssignmentResult();
      setCheckingAssignment(false);
    }
    setActionMode("NONE");
  }

  function toggleBatchPerson(personId: string) {
    setUserIds((current) => (current.includes(personId) ? current.filter((id) => id !== personId) : [...current, personId]));
  }

  async function submitDraft(event: FormEvent) {
    event.preventDefault();
    if (!canManagePrivileges || !ruleId || !userIds.length) return;
    if (grantOnCreate && batchRationale.trim().length < 8) {
      setError("Grant rationale must be at least 8 characters.");
      return;
    }
    setCreating(true);
    setError("");
    clearActionFlash();
    const targetRule = rules.find((rule) => rule.id === ruleId) || null;
    const grantingAuditorRank = Boolean(targetRule && isAuditorRankRule(targetRule));
    const failures: string[] = [];
    let lastCreatedId = "";
    let createdCount = 0;
    let grantedCount = 0;
    let rankedCount = 0;
    for (const personId of userIds) {
      try {
        if (grantingAuditorRank) {
          const activeAuditor = findActiveAuditorPrivilege(privileges, rules, personId);
          if (activeAuditor) {
            if (activeAuditor.rule_id === ruleId) {
              failures.push(`${personLabel(personId)}: already holds this active auditor rank — open it to manage lifecycle`);
              continue;
            }
            const updated = await changeQmsAuditorRank(
              amoCode,
              activeAuditor.id,
              ruleId,
              (grantOnCreate ? batchRationale.trim() : "") || `Rank changed to ${targetRule?.title || "auditor"} during authorization.`,
            );
            rankedCount += 1;
            lastCreatedId = updated.id;
            continue;
          }
        }
        const created = await createQmsPrivilege(amoCode, {
          rule_id: ruleId,
          user_id: personId,
          scope_key: scopeKey.trim() || "GLOBAL",
        });
        createdCount += 1;
        lastCreatedId = created.id;
        if (grantOnCreate) {
          await decideQmsPrivilege(amoCode, created.id, {
            decision_type: "GRANT",
            rationale: batchRationale.trim(),
          });
          grantedCount += 1;
        }
      } catch (nextError) {
        failures.push(`${personLabel(personId)}: ${messageFromError(nextError)}`);
      }
    }
    setCreating(false);
    if (failures.length && !createdCount && !rankedCount) {
      setError(failures.join(" · "));
      return;
    }
    if (lastCreatedId) setSelectedId(lastCreatedId);
    setPageTab("privileges");
    setUserIds([]);
    setScopeKey("GLOBAL");
    setActionMode("NONE");
    flashAction("CREATE");
    if (failures.length) setError(`Some people failed: ${failures.join(" · ")}`);
    invalidateQmsEligibilityMemory(amoCode);
    setSnapshotRevision((value) => value + 1);
    void load(undefined, { soft: true });
  }

  async function submitRule(event: FormEvent) {
    event.preventDefault();
    if (!canManagePrivileges) return;
    const trainingCodes = uniqueCourseCodes(ruleTrainingCodes);
    const expression = ruleTrainingAdvanced
      ? ruleTrainingExpression.trim()
      : defaultTrainingExpression(trainingCodes, ruleTrainingJoin);
    if (expression) {
      const parsed = parseTrainingExpression(expression);
      if (!parsed.ok) {
        setRuleTrainingExpressionError(parsed.error);
        setError(parsed.error);
        return;
      }
    }
    setSavingRule(true);
    setError("");
    const scopeSchema = buildPrivilegeRuleScopeSchema({
      privilegeType: ruleType,
      supervisedDevelopment: ruleType === "AUDITOR" && ruleSupervisedDevelopment,
      selectedTrainingCodes: trainingCodes,
      join: ruleTrainingJoin,
      expression: expression || null,
      previousScope: ruleFormBaselineScope,
    });
    const usesPackage = ruleUsesCompetencePackage(
      { privilege_type: ruleType, scope_schema: scopeSchema },
      ruleType === "AUDITOR" && ruleSupervisedDevelopment,
    );
    const requiredCodes = ruleRequiredTrainingPayload({
      usesCompetencePackage: usesPackage,
      selectedTrainingCodes: trainingCodes,
    });
    const payload = {
      title: ruleTitle.trim(),
      description: ruleDescription.trim() || null,
      required_training_course_codes: requiredCodes,
      independence_required: ruleIndependenceRequired,
      max_concurrent_assignments: ruleMaxConcurrent.trim() ? Number(ruleMaxConcurrent) : null,
      scope_schema: scopeSchema,
      is_active: ruleActive,
    };
    try {
      if (actionMode === "CREATE_RULE") {
        await createQmsPrivilegeRule(amoCode, {
          privilege_code: ruleCode.trim().toUpperCase(),
          title: ruleTitle.trim(),
          privilege_type: ruleType,
          description: ruleDescription.trim() || undefined,
          required_training_course_codes: requiredCodes,
          independence_required: ruleIndependenceRequired,
          max_concurrent_assignments: ruleMaxConcurrent.trim() ? Number(ruleMaxConcurrent) : null,
          scope_schema: scopeSchema,
        });
      } else if (actionMode === "EDIT_RULE" && selectedRuleId) {
        await updateQmsPrivilegeRule(amoCode, selectedRuleId, payload);
      }
      setPageTab("rules");
      setActionMode("NONE");
      flashAction(actionMode === "CREATE_RULE" ? "CREATE_RULE" : "EDIT_RULE");
      void load(undefined, { soft: true });
    } catch (nextError) {
      setError(messageFromError(nextError));
    } finally {
      setSavingRule(false);
    }
  }

  async function submitDecision(event: FormEvent) {
    event.preventDefault();
    if (!canManagePrivileges || !selected || decisionReason.trim().length < 8) return;
    const previous = selected;
    const previousSummary = summary;
    const nextStatus = privilegeStatusAfterDecision(decisionType);
    const rationale = decisionReason.trim();
    const effective = effectiveFrom || undefined;
    const isActivation = decisionType === "GRANT" || decisionType === "RENEW" || decisionType === "REINSTATE";
    const cappedExpires = isActivation
      ? (capPrivilegeExpiresOn(expiresOn || null, selectedSnapshot?.training) || undefined)
      : undefined;
    const optimistic: QmsPrivilege = {
      ...previous,
      status: nextStatus,
      ...(isActivation && cappedExpires ? { expires_on: cappedExpires } : {}),
      updated_at: new Date().toISOString(),
    };
    setDeciding(true);
    setError("");
    queueOptimisticAction({
      apply: () => {
        setPrivileges((current) => current.map((item) => (item.id === previous.id ? optimistic : item)));
        setSummary((current) => adjustPrivilegeSummary(current, previous.status, nextStatus));
        setDecisionReason("");
        setEffectiveFrom("");
        setExpiresOn("");
        setActionMode("NONE");
        flashAction("DECISION");
        setDeciding(false);
      },
      revert: () => {
        setPrivileges((current) => current.map((item) => (item.id === previous.id ? previous : item)));
        setSummary(previousSummary);
        setDecisionReason(rationale);
        setEffectiveFrom(effective || "");
        setExpiresOn(cappedExpires || "");
        setActionMode("DECISION");
        clearActionFlash();
        setDeciding(false);
      },
      commit: () => decideQmsPrivilege(amoCode, previous.id, {
        decision_type: decisionType,
        rationale,
        ...(isActivation ? { effective_from: effective, expires_on: cappedExpires } : {}),
      }),
      onSuccess: (result) => {
        clearQmsApiResponseCache();
        invalidateQmsEligibilityMemory(amoCode, previous.user_id);
        setPrivileges((current) => current.map((item) => (item.id === result.privilege.id ? result.privilege : item)));
        setSnapshotRevision((value) => value + 1);
        void load(undefined, { soft: true });
      },
      onError: (nextError) => {
        setError(messageFromError(nextError));
        setDeciding(false);
      },
    });
  }

  function runQuickDecision(
    decision: Extract<QmsPrivilegeDecision["decision_type"], "SUSPEND" | "REVOKE" | "REINSTATE">,
    rationale: string,
  ) {
    if (!canManagePrivileges || !selected || lifecycleBusy) return;
    const previous = selected;
    const previousSummary = summary;
    const nextStatus = privilegeStatusAfterDecision(decision);
    const optimistic: QmsPrivilege = {
      ...previous,
      status: nextStatus,
      updated_at: new Date().toISOString(),
    };
    setError("");
    setLifecycleBusy(true);
    queueOptimisticAction({
      apply: () => {
        setPrivileges((current) => current.map((item) => (item.id === previous.id ? optimistic : item)));
        setSummary((current) => adjustPrivilegeSummary(current, previous.status, nextStatus));
        flashAction(decision);
        setLifecycleBusy(false);
      },
      revert: () => {
        setPrivileges((current) => current.map((item) => (item.id === previous.id ? previous : item)));
        setSummary(previousSummary);
        clearActionFlash();
        setLifecycleBusy(false);
      },
      commit: () => decideQmsPrivilege(amoCode, previous.id, {
        decision_type: decision,
        rationale,
      }),
      onSuccess: (result) => {
        clearQmsApiResponseCache();
        invalidateQmsEligibilityMemory(amoCode, previous.user_id);
        setPrivileges((current) => current.map((item) => (item.id === result.privilege.id ? result.privilege : item)));
        setSnapshotRevision((value) => value + 1);
        void load(undefined, { soft: true });
      },
      onError: (nextError) => {
        setError(messageFromError(nextError));
        setLifecycleBusy(false);
      },
    });
  }

  async function changeRankTo(target: QmsPrivilegeRule | null) {
    if (!canManagePrivileges || !selected || !target || selected.status !== "ACTIVE" || lifecycleBusy) return;
    const previousId = selected.id;
    const previousUserId = selected.user_id;
    setLifecycleBusy(true);
    setError("");
    flashAction("RANK");
    try {
      const updated = await changeQmsAuditorRank(amoCode, selected.id, target.id, `Rank changed to ${target.title} by Quality.`);
      clearQmsApiResponseCache();
      invalidateQmsEligibilityMemory(amoCode, previousUserId);
      setPrivileges((current) => {
        const withoutPrevious = current.filter((item) => item.id !== previousId);
        return [updated, ...withoutPrevious.filter((item) => item.id !== updated.id)];
      });
      setSelectedId(updated.id);
      setSnapshotRevision((value) => value + 1);
      void load(undefined, { soft: true });
    } catch (cause) {
      clearActionFlash();
      setError(messageFromError(cause));
    } finally {
      setLifecycleBusy(false);
    }
  }

  function requestPurgeSelected() {
    if (!selected || !canManagePrivileges || lifecycleBusy) return;
    setConfirmDialog({
      kind: "purge",
      privilegeId: selected.id,
      personName: personLabel(selected.user_id),
    });
  }

  function purgeSelected() {
    if (!selected || !canManagePrivileges || lifecycleBusy) return;
    if (confirmDialog?.kind === "purge" && confirmDialog.privilegeId !== selected.id) return;
    setConfirmDialog(null);
    const previous = selected;
    const previousSummary = summary;
    const previousPrivileges = privileges;
    const previousSelectedId = selectedId;
    const previousSnapshot = selectedSnapshot;
    setError("");
    setLifecycleBusy(true);
    queueOptimisticAction({
      apply: () => {
        setPurgeFarewell(previous);
        setPrivileges((current) => current.filter((item) => item.id !== previous.id));
        setSummary((current) => adjustPrivilegeSummary(current, previous.status, null));
        flashAction("PURGE");
        setLifecycleBusy(false);
        window.setTimeout(() => {
          setSelectedId("");
          setSelectedSnapshot(null);
          setPurgeFarewell(null);
        }, 2200);
      },
      revert: () => {
        setPrivileges(previousPrivileges);
        setSummary(previousSummary);
        setSelectedId(previousSelectedId);
        setSelectedSnapshot(previousSnapshot);
        setPurgeFarewell(null);
        clearActionFlash();
        setLifecycleBusy(false);
      },
      commit: () => purgeQmsPrivilege(amoCode, previous.id),
      onSuccess: () => {},
      onError: (cause) => {
        setError(messageFromError(cause));
        setLifecycleBusy(false);
      },
    });
  }

  function requestDeleteSelectedRule() {
    if (!catalogRule || !canManagePrivileges || deletingRule) return;
    const liveHolders = catalogRule.live_holders ?? 0;
    if (liveHolders > 0 && !catalogRule.can_delete) {
      setError(`Cannot delete “${catalogRule.title}”: ${liveHolders} live holder${liveHolders === 1 ? "" : "s"} remain.`);
      return;
    }
    if (!(catalogRule.can_delete || liveHolders === 0)) {
      setError(`Cannot delete “${catalogRule.title}”: holders are still assigned.`);
      return;
    }
    setConfirmDialog({
      kind: "delete-rule",
      ruleId: catalogRule.id,
      ruleTitle: catalogRule.title,
    });
  }

  function deleteSelectedRule() {
    if (!catalogRule || !canManagePrivileges || deletingRule) return;
    if (confirmDialog?.kind === "delete-rule" && confirmDialog.ruleId !== catalogRule.id) return;
    setConfirmDialog(null);
    const previous = catalogRule;
    const previousRules = rules;
    const previousSelectedRuleId = selectedRuleId;
    setError("");
    setDeletingRule(true);
    queueOptimisticAction({
      apply: () => {
        flashAction("DELETE_RULE");
        setDeletingRule(false);
        window.setTimeout(() => {
          setRules((current) => current.filter((item) => item.id !== previous.id));
          setSelectedRuleId("");
        }, 2200);
      },
      revert: () => {
        setRules(previousRules);
        setSelectedRuleId(previousSelectedRuleId);
        clearActionFlash();
        setDeletingRule(false);
      },
      commit: async () => {
        await deleteQmsPrivilegeRule(amoCode, previous.id);
      },
      onSuccess: () => {
        void load(undefined, { soft: true });
      },
      onError: (cause) => {
        setError(messageFromError(cause));
        setDeletingRule(false);
      },
    });
  }

  async function submitAuditAssignment(event: FormEvent) {
    event.preventDefault();
    if (!selected || !selectedRule || !canRunAuditPreflight || !assignmentInputComplete || checkingAssignment) return;

    const submitted: AssignmentSubmission = {
      selected_privilege_id: selected.id,
      selected_privilege_code: selected.privilege_code,
      selected_scope_key: selected.scope_key,
      user_id: selected.user_id,
      assignment_role: assignmentRole,
      assignment_date: assignmentDate,
      assignment_scope_key: assignmentScopeKey.trim(),
      context_type: assignmentContextType,
      context_id: assignmentContextId.trim(),
    };
    const requestRevision = assignmentRequestRevision.current + 1;
    assignmentRequestRevision.current = requestRevision;
    setAssignmentResult(null);
    setAssignmentResultInput(null);
    setCheckingAssignment(true);
    setError("");

    try {
      const result = await preflightQmsAuditorAssignment(amoCode, {
        user_id: submitted.user_id,
        assignment_role: submitted.assignment_role,
        assignment_date: submitted.assignment_date,
        assignment_scope_key: submitted.assignment_scope_key,
        context_type: submitted.context_type || undefined,
        context_id: submitted.context_id || undefined,
        enforce_independence: true,
      });
      if (assignmentRequestRevision.current !== requestRevision) return;
      setAssignmentResultInput(submitted);
      setAssignmentResult(result);
    } catch (nextError) {
      if (assignmentRequestRevision.current !== requestRevision) return;
      setAssignmentResult(null);
      setAssignmentResultInput(null);
      setError(messageFromError(nextError));
    } finally {
      if (assignmentRequestRevision.current === requestRevision) setCheckingAssignment(false);
    }
  }

  async function submitImpartialityForm(event: FormEvent) {
    event.preventDefault();
    if (!canManageAuditGovernance || !indUserId.trim() || !indContextId.trim() || indRationale.trim().length < 8) return;
    setDeclaring(true);
    setError("");
    try {
      await declareQmsIndependence(amoCode, {
        user_id: indUserId.trim(),
        context_type: indContextType,
        context_id: indContextId.trim(),
        declaration: indDeclaration,
        relationship_to_subject: indRelationship.trim() || undefined,
        rationale: indRationale.trim(),
        source_references: [{ type: "AUDITOR_IMPARTIALITY_FORM" }],
      });
      setIndRationale("");
      setIndRelationship("");
      setIndDeclaration("REQUIRES_REVIEW");
      setActionMode("NONE");
      flashAction("IMPARTIALITY");
      void load(undefined, { soft: true });
    } catch (nextError) {
      setError(messageFromError(nextError));
    } finally {
      setDeclaring(false);
    }
  }

  async function toggleIndependenceEnforcement(nextEnforced: boolean) {
    if (!platformSuperuser || policyBusy) return;
    setPolicyBusy(true);
    setError("");
    try {
      const policy = await updateQmsIndependencePolicy(amoCode, { enforced: nextEnforced });
      setIndependencePolicy(policy);
      setSnapshotRevision((value) => value + 1);
      flashAction(nextEnforced ? "INDEPENDENCE_ON" : "INDEPENDENCE_OFF");
    } catch (nextError) {
      setError(messageFromError(nextError));
    } finally {
      setPolicyBusy(false);
    }
  }

  const snapshotMatchesSelection = Boolean(
    selected
    && selectedSnapshot
    && selectedSnapshot.person.user_id === selected.user_id,
  );
  const selectedName = personDisplay(
    snapshotMatchesSelection ? selectedSnapshot?.person.full_name : null,
    personLabel(selected?.user_id || ""),
  );
  const readinessLabel = selected
    ? privilegeReadinessLabel(selected, {
        loading: snapshotLoading,
        snapshot: selectedSnapshot,
        matchesSelection: snapshotMatchesSelection,
      })
    : "Checking authoritative gates…";
  const draftReason = selected ? privilegeDraftReason(selected) : "";
  const openDraftDecision = canManagePrivileges && selected?.status === "DRAFT" && allowedPrivilegeDecisions("DRAFT").length
    ? () => openAction("DECISION")
    : undefined;
  const selectedRankLabel = selected ? privilegeRankLabel(selected, rules) : "";
  const selectedTypeLabel = selectedRule ? humanisePrivilegeType(selectedRule.privilege_type) : "";
  const showSelectedTypeBadge = Boolean(
    selectedTypeLabel
    && selectedTypeLabel.trim().toLowerCase() !== selectedRankLabel.trim().toLowerCase(),
  );
  const grantBlocked = Boolean(
    selected
    && (decisionType === "GRANT" || decisionType === "RENEW" || decisionType === "REINSTATE")
    && snapshotMatchesSelection
    && !snapshotLoading
    && selectedSnapshot
    && !selectedSnapshot.eligible,
  );
  const displayGates = selected && snapshotMatchesSelection && selectedSnapshot
    ? privilegeDisplayGates(selected, selectedSnapshot.hard_gates)
    : [];
  const courseExpiryCap = snapshotMatchesSelection
    ? earliestCompetenceValidUntil(selectedSnapshot?.training)
    : null;
  const readinessTone = snapshotLoading || !snapshotMatchesSelection
    ? "muted"
    : selectedSnapshot?.eligible
      ? "ready"
      : "blocked";
  const expiryCaption = !selected
    ? ""
    : selected.expires_on
      ? `Expires ${dateLabel(selected.expires_on)}`
      : selected.status === "DRAFT"
        ? "No expiry until granted"
        : "No expiry";
  const trainingMissing = Boolean(
    snapshotMatchesSelection
    && selectedSnapshot
    && (
      (selectedSnapshot.training.missing || []).length > 0
      || (selectedSnapshot.training.expired || []).length > 0
      || selectedSnapshot.hard_gates.training_current_verified === false
    ),
  );
  const activeBypass: QmsQmTrainingBypass | null = snapshotMatchesSelection
    ? (selectedSnapshot?.qm_bypass || selectedSnapshot?.training.qm_bypass || null)
    : null;
  const competenceChips = (["QMS-INIT", "QMS-REF", "QMS-ADMIN"] as const).map((code) => {
    if (!snapshotMatchesSelection || (snapshotLoading && !selectedSnapshot)) {
      return { label: code, tone: "muted" as const, detail: "checking…" };
    }
    return competenceChipStatus(code, selectedSnapshot?.training);
  });
  const activeRules = rules.filter((rule) => rule.is_active);
  const hasLeadRule = activeRules.some((rule) => rule.privilege_type === "LEAD_AUDITOR");
  const hasObserverTraineeRule = activeRules.some((rule) => isObserverTraineeRule(rule));
  const hasAuditorRule = activeRules.some((rule) => isFullAuditorRule(rule));
  const missingLeadRule = !hasLeadRule;
  const missingObserverTraineeRule = !hasObserverTraineeRule;
  const missingAuditorRule = !hasAuditorRule;
  const batchPersonnel = useMemo(() => authorizeCandidates, [authorizeCandidates]);
  const authorizeFilterActive = Boolean(ruleId && authorizeMatchMode !== "none");
  const authorizeFilterHint = !ruleId
    ? "Select a rule to list people who meet its training requirements."
    : authorizeMatchMode === "none"
      ? "This rule has no training courses configured — showing the active workforce."
      : authorizeMatchMode === "all_of"
        ? `Showing people with a Training record or scheduled enrollment for every required course (${authorizeTrainingCodes.join(", ") || "configured codes"}).`
        : `Showing people with a Training record or scheduled enrollment for any of: ${authorizeTrainingCodes.join(", ") || "configured codes"}.`;

  const auditorRankRules = activeRules.filter((rule) => isAuditorRankRule(rule));
  const catalogLiveHolders = catalogRule?.live_holders ?? 0;
  const canDeleteCatalogRule = Boolean(catalogRule && (catalogRule.can_delete || catalogLiveHolders === 0));

  async function downloadSelectedCertificate() {
    if (!selected) return;
    try {
      const { blob, filename } = await downloadQmsAuthorization(amoCode, selected.id);
      downloadBlob(blob, filename || "quality-authorization.pdf");
    } catch (cause) {
      setError(messageFromError(cause));
    }
  }

  async function uploadEvidence(file: File) {
    if (!selected || !canManagePrivileges) return;
    setEvidenceBusy(true);
    setError("");
    try {
      const preferredCode = (selectedSnapshot?.training.missing || []).includes("QMS-REF")
        ? "QMS-REF"
        : (selectedSnapshot?.training.missing || []).includes("QMS-ADMIN")
          ? "QMS-ADMIN"
          : "QMS-INIT";
      await uploadQmsAuthorizationEvidence(amoCode, selected.id, { file, course_code: preferredCode });
      clearQmsApiResponseCache();
      invalidateQmsEligibilityMemory(amoCode, selected.user_id);
      const snap = await getQmsEligibility(amoCode, { userId: selected.user_id, privilegeCode: selected.privilege_code });
      setSelectedSnapshot(bindEligibilityToPrivilege(snap, selected));
      setSnapshotRevision((value) => value + 1);
    } catch (cause) {
      setError(messageFromError(cause));
    } finally {
      setEvidenceBusy(false);
    }
  }

  async function submitQmBypass() {
    if (!selected || !canManagePrivileges) return;
    if (bypassRationale.trim().length < 8 || !bypassUntil) {
      setError("QM bypass needs a rationale (8+ characters) and a valid-until date.");
      return;
    }
    setBypassBusy(true);
    setError("");
    try {
      const result = await createQmsQmTrainingBypass(amoCode, selected.id, {
        rationale: bypassRationale.trim(),
        valid_until: bypassUntil,
      });
      setPrivileges((rows) => rows.map((row) => (row.id === result.privilege.id ? { ...row, ...result.privilege } : row)));
      clearQmsApiResponseCache();
      invalidateQmsEligibilityMemory(amoCode, selected.user_id);
      const snap = await getQmsEligibility(amoCode, { userId: selected.user_id, privilegeCode: selected.privilege_code });
      setSelectedSnapshot(bindEligibilityToPrivilege(snap, result.privilege));
      setShowBypassForm(false);
      setBypassRationale("");
      setBypassUntil("");
      setSnapshotRevision((value) => value + 1);
    } catch (cause) {
      setError(messageFromError(cause));
    } finally {
      setBypassBusy(false);
    }
  }

  async function downloadAuditIssuedReport(item: QmsPersonAuditParticipationItem) {
    if (!selected) return;
    try {
      const { blob, filename } = await downloadQmsPersonAuditIssuedReport(amoCode, selected.user_id, item.audit_id);
      downloadBlob(blob, filename || item.issued_filename || "issued-audit-report.pdf");
    } catch (cause) {
      setError(messageFromError(cause));
    }
  }

  function auditOpenHref(item: QmsPersonAuditParticipationItem): string | null {
    try {
      return auditSessionPath(amoCode, item.audit_ref || item.audit_id, item.has_issued_report ? "closing" : "setup");
    } catch {
      return null;
    }
  }

  useEffect(() => {
    if (deepLinkConsumed.current || loading) return;
    const tab = searchParams.get("tab");
    const action = searchParams.get("action");
    const ruleTypeParam = searchParams.get("ruleType");
    const ruleIdParam = searchParams.get("ruleId");
    if (!tab && !action && !ruleTypeParam && !ruleIdParam) {
      deepLinkConsumed.current = true;
      return;
    }
    deepLinkConsumed.current = true;
    if (tab && PAGE_TABS.has(tab as PageTab)) setPageTab(tab as PageTab);
    const typedRuleType = PRIVILEGE_TYPES.includes(ruleTypeParam as QmsPrivilegeRule["privilege_type"])
      ? (ruleTypeParam as QmsPrivilegeRule["privilege_type"])
      : undefined;
    if (action && ACTION_MODES.has(action as ActionMode)) {
      openAction(action as ActionMode, { ruleType: typedRuleType, ruleId: ruleIdParam || undefined });
    }
    const next = new URLSearchParams(searchParams);
    next.delete("tab");
    next.delete("action");
    next.delete("ruleType");
    next.delete("ruleId");
    next.set("workspace", "people");
    setSearchParams(next, { replace: true });
    // One-shot deep-link consume after first successful load.
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [loading]);

  const metricChips: Array<{ key: Exclude<RankFilter, "ALL">; label: string; value: number }> = [
    { key: "LEAD", label: "Lead", value: summary.lead_auditors ?? 0 },
    { key: "AUDITOR", label: "Auditors", value: summary.auditors ?? 0 },
    { key: "OBSERVER", label: "Observers", value: summary.observers ?? 0 },
    { key: "INSPECTOR", label: "Inspectors", value: summary.inspectors ?? 0 },
    { key: "SUSPENDED", label: "Suspended", value: summary.suspended_privileges },
    { key: "EXPIRING", label: "Expiring", value: summary.expiring_within_60_days },
  ];

  return (
    <main className="qms-people" aria-label="People and Privileges">
      <header className="qms-people__hero">
        <div>
          <span>People & Privileges</span>
          <h1>Authorizations</h1>
          <p>Authorize people, change auditor rank, and manage lifecycle from one board.</p>
        </div>
        <div className="qms-people__hero-actions">
          <button type="button" onClick={() => void load()} disabled={loading}><RefreshCw size={16} aria-hidden="true" /> Refresh</button>
          {canManagePrivileges ? <button type="button" className={actionFlash === "CREATE_RULE" ? "is-action-done" : ""} onClick={() => { setPageTab("rules"); openAction("CREATE_RULE"); }}>{actionFlash === "CREATE_RULE" ? <><CheckCircle2 size={16} className="qms-people__action-tick" aria-hidden="true" /> Done</> : <><Plus size={16} aria-hidden="true" /> New rule</>}</button> : null}
          {canManagePrivileges ? (
            <button type="button" className={actionFlash === "CREATE" ? "is-primary is-action-done" : "is-primary"} onClick={() => { setPageTab("privileges"); openAction("CREATE"); }}>
              {actionFlash === "CREATE" ? <><CheckCircle2 size={16} className="qms-people__action-tick" aria-hidden="true" /> Done</> : <><Plus size={16} aria-hidden="true" /> Authorize</>}
            </button>
          ) : null}
        </div>
      </header>

      <nav className="qms-people__tabs" aria-label="People workspace views">
        <button type="button" className={pageTab === "privileges" ? "is-active" : ""} onClick={() => setPageTab("privileges")}>Authorizations</button>
        <button type="button" className={pageTab === "rules" ? "is-active" : ""} onClick={() => setPageTab("rules")}>Privilege rules</button>
      </nav>

      {error && actionMode === "NONE" && !confirmDialog ? <div className="qms-people__error" role="alert"><AlertTriangle size={18} aria-hidden="true" /> {error}</div> : null}

      {canManagePrivileges && (missingLeadRule || missingObserverTraineeRule || missingAuditorRule) ? (
        <section className="qms-people__setup-strip" aria-label="Auditor competence setup">
          <div>
            <strong>Default competence rules incomplete</strong>
            <p>
              {missingLeadRule ? "Lead auditor missing. " : ""}
              {missingObserverTraineeRule ? "Observer / Trainee missing. " : ""}
              {missingAuditorRule ? "Auditor missing. " : ""}
              Refresh to provision tenant defaults, or create the missing rule.
            </p>
          </div>
          <div className="qms-people__setup-strip-actions">
            <button type="button" onClick={() => void load()}>Refresh defaults</button>
            {missingLeadRule ? (
              <button type="button" onClick={() => { setPageTab("rules"); openAction("CREATE_RULE", { ruleType: "LEAD_AUDITOR" }); }}>
                Add lead rule
              </button>
            ) : null}
            {missingObserverTraineeRule || missingAuditorRule ? (
              <button type="button" onClick={() => { setPageTab("rules"); openAction("CREATE_RULE", { ruleType: "AUDITOR" }); }}>
                Add auditor rule
              </button>
            ) : null}
            {hasLeadRule || hasObserverTraineeRule || hasAuditorRule ? (
              <button
                type="button"
                className="is-primary"
                onClick={() => {
                  setPageTab("privileges");
                  openAction("CREATE", {
                    ruleType: hasAuditorRule || hasObserverTraineeRule ? "AUDITOR" : "LEAD_AUDITOR",
                  });
                }}
              >
                Authorize
              </button>
            ) : null}
          </div>
        </section>
      ) : null}

      <section className="qms-people__metrics" aria-label="Privilege exposure summary">
        {metricChips.map((chip) => {
          const ChipIcon = METRIC_CHIP_ICONS[chip.key];
          return (
            <button
              key={chip.key}
              type="button"
              className={`qms-people__metric-chip${rankFilter === chip.key ? " is-active" : ""}`}
              aria-pressed={rankFilter === chip.key}
              onClick={() => toggleRankFilter(chip.key)}
            >
              <ChipIcon size={14} aria-hidden="true" />
              <strong>{chip.value}</strong>
              <span>{chip.label}</span>
            </button>
          );
        })}
      </section>

      {pageTab === "rules" ? (
        <section className="qms-people__workspace qms-people__workspace--rules">
          <section className="qms-people__panel qms-people__register">
            <div className="qms-people__panel-head">
              <div><span>Rule catalog</span><h2>Privilege rules</h2></div>
              <div className="qms-people__filters">
                <label className="qms-people__search"><Search size={15} aria-hidden="true" /><input value={search} onChange={(event) => setSearch(event.target.value)} placeholder="Search rules" /></label>
                <label className="qms-people__checkbox"><input type="checkbox" checked={showInactiveRules} onChange={(event) => setShowInactiveRules(event.target.checked)} /> Show inactive</label>
              </div>
            </div>
            <div className="qms-people__table-wrap">
              <table>
                <thead><tr><th>Rule</th><th>Type</th><th>People</th><th>Training</th><th>Capacity</th><th>Status</th></tr></thead>
                <tbody>
                  {visibleRules.length ? visibleRules.map((rule) => (
                    <tr key={rule.id} className={rule.id === selectedRuleId ? "is-selected" : ""} onClick={() => setSelectedRuleId(rule.id)}>
                      <td>
                        <div className="qms-people__rule-cell">
                          <RuleTypeIcon tone={ruleIconTone(rule)} />
                          <div className="qms-people__cell-stack">
                            <span className="qms-people__cell-main">{rule.title}</span>
                            <span className="qms-people__cell-sub">{rule.privilege_code}</span>
                          </div>
                        </div>
                      </td>
                      <td>{humanisePrivilegeType(rule.privilege_type)}</td>
                      <td><PeopleCountCell active={rule.active_holders ?? 0} total={rule.total_holders ?? 0} /></td>
                      <td>{(() => {
                        const codes = ruleConfiguredTrainingCodes(rule);
                        return codes.length ? codes.join(", ") : "None";
                      })()}</td>
                      <td>{rule.max_concurrent_assignments ?? "Unlimited"}</td>
                      <td>
                        <StatusPill label={rule.is_active ? "Active" : "Inactive"} active={rule.is_active} />
                      </td>
                    </tr>
                  )) : <tr><td colSpan={6}>{loading ? "Loading privilege rules…" : "No privilege rules configured yet."}</td></tr>}
                </tbody>
              </table>
            </div>
          </section>

          <aside className="qms-people__detail" aria-label="Selected privilege rule">
            {catalogRule ? (
              <>
                <div className="qms-people__detail-head">
                  <span>Selected rule</span>
                  <div className="qms-people__detail-title">
                    <RuleTypeIcon tone={ruleIconTone(catalogRule)} size={16} />
                    <h2>{catalogRule.title}</h2>
                  </div>
                  <p>{catalogRule.privilege_code} · {humanisePrivilegeType(catalogRule.privilege_type)}</p>
                  <div className="qms-people__detail-badges">
                    <StatusPill label={catalogRule.is_active ? "Active" : "Inactive"} active={catalogRule.is_active} />
                    <span>{`${catalogRule.active_holders ?? 0} active · ${catalogRule.total_holders ?? 0} total`}</span>
                  </div>
                </div>
                {canManagePrivileges ? (
                  <div className="qms-people__detail-actions qms-people__detail-actions--sticky">
                    <button type="button" className={actionFlash === "EDIT_RULE" ? "is-primary is-action-done" : "is-primary"} onClick={() => openAction("EDIT_RULE")}>
                      {actionFlash === "EDIT_RULE" ? <><CheckCircle2 size={15} className="qms-people__action-tick" aria-hidden="true" /> Done</> : <><Pencil size={15} aria-hidden="true" /> Edit rule</>}
                    </button>
                    {catalogRule.is_active ? (
                      <button type="button" onClick={() => void updateQmsPrivilegeRule(amoCode, catalogRule.id, { is_active: false }).then(() => load()).catch((nextError) => setError(messageFromError(nextError)))}>
                        <Ban size={15} aria-hidden="true" /> Deactivate
                      </button>
                    ) : (
                      <button type="button" onClick={() => void updateQmsPrivilegeRule(amoCode, catalogRule.id, { is_active: true }).then(() => load()).catch((nextError) => setError(messageFromError(nextError)))}>
                        <RotateCcw size={15} aria-hidden="true" /> Reactivate
                      </button>
                    )}
                    {canDeleteCatalogRule ? (
                      <button
                        type="button"
                        className={actionFlash === "DELETE_RULE" ? "is-danger is-action-done" : "is-danger"}
                        disabled={deletingRule || actionFlash === "DELETE_RULE"}
                        onClick={() => requestDeleteSelectedRule()}
                      >
                        {actionFlash === "DELETE_RULE" ? (
                          <><CheckCircle2 size={15} className="qms-people__action-tick" aria-hidden="true" /> Done</>
                        ) : (
                          <><Trash2 size={15} aria-hidden="true" /> {deletingRule ? "Deleting…" : "Delete rule"}</>
                        )}
                      </button>
                    ) : catalogLiveHolders > 0 ? (
                      <p className="qms-people__lifecycle-hint">Cannot delete while {catalogLiveHolders} live holder{catalogLiveHolders === 1 ? "" : "s"} remain.</p>
                    ) : null}
                  </div>
                ) : null}
                <dl className="qms-people__facts">
                  <div><dt>Description</dt><dd>{catalogRule.description || "No description recorded."}</dd></div>
                  <div><dt>Required training</dt><dd>{trainingCodesLabel(ruleConfiguredTrainingCodes(catalogRule))}</dd></div>
                  <div><dt>Independence</dt><dd>{catalogRule.independence_required ? "Required" : "Optional"}</dd></div>
                  <div><dt>Max concurrent</dt><dd>{catalogRule.max_concurrent_assignments ?? "Unlimited"}</dd></div>
                  <div><dt>Supervised development</dt><dd>{(catalogRule.scope_schema as { supervised_development?: boolean })?.supervised_development ? "Yes (observer/trainee)" : "No"}</dd></div>
                  <div><dt>Live holders</dt><dd>{catalogLiveHolders}</dd></div>
                </dl>
                {catalogEntryForType(catalogRule.privilege_type) ? (
                  <details className="qms-people__history">
                    <summary>Assignment contract</summary>
                    <article>
                      <p>{catalogEntryForType(catalogRule.privilege_type)?.summary}</p>
                      <p><strong>Audit roles:</strong> {catalogEntryForType(catalogRule.privilege_type)?.auditAssignmentRoles.join(" · ")}</p>
                    </article>
                  </details>
                ) : null}
              </>
            ) : (
              <div className="qms-people__placeholder"><ShieldCheck size={30} /><strong>Select a privilege rule</strong><p>Create or select a rule before granting privileges.</p></div>
            )}
          </aside>
        </section>
      ) : null}

      {pageTab === "privileges" ? (
        <section className="qms-people__workspace">
          <section className="qms-people__panel qms-people__register">
            <div className="qms-people__panel-head">
              <div><span>Register</span><h2>People authorizations</h2></div>
              <div className="qms-people__filters">
                <label className="qms-people__search">
                  <Search size={15} aria-hidden="true" />
                  <input value={search} onChange={(event) => setSearch(event.target.value)} placeholder="Search name, rank or scope" />
                </label>
                <label>
                  Status
                  <select value={statusFilter} onChange={(event) => setStatusFilter(event.target.value as typeof statusFilter)} disabled={rankFilter !== "ALL"}>
                    <option value="ALL">All</option>
                    <option value="DRAFT">Draft</option>
                    <option value="ACTIVE">Active</option>
                    <option value="SUSPENDED">Suspended</option>
                    <option value="REVOKED">Revoked</option>
                    <option value="EXPIRED">Expired</option>
                  </select>
                </label>
                <label className="qms-people__checkbox">
                  <input type="checkbox" checked={expiringOnly || rankFilter === "EXPIRING"} disabled={rankFilter !== "ALL"} onChange={(event) => setExpiringOnly(event.target.checked)} />
                  Expiring ≤60d
                </label>
              </div>
            </div>
            {!activeRules.length && canManagePrivileges ? (
              <p className="qms-people__banner">
                No active privilege rules exist for this tenant.{" "}
                <button type="button" className="qms-people__text-button" onClick={() => { setPageTab("rules"); openAction("CREATE_RULE", { ruleType: "AUDITOR" }); }}>
                  Create auditor rule
                </button>
              </p>
            ) : null}
            <div className="qms-people__table-wrap">
              <table>
                <thead>
                  <tr>
                    <th>Person</th>
                    <th>Rank / Privilege</th>
                    <th>Status</th>
                    <th>Expiry</th>
                  </tr>
                </thead>
                <tbody>
                  {visiblePrivileges.length ? visiblePrivileges.map((item) => {
                    const itemRule = rules.find((rule) => rule.id === item.rule_id) || null;
                    return (
                      <tr
                        key={item.id}
                        className={item.id === selectedId ? "is-selected" : ""}
                        onClick={() => setSelectedId(item.id)}
                      >
                        <td><PersonCell name={personLabel(item.user_id)} /></td>
                        <td>
                          <div className="qms-people__rule-cell">
                            <RuleTypeIcon tone={ruleIconTone(itemRule)} />
                            <span className="qms-people__cell-main">{privilegeRankLabel(item, rules)}</span>
                          </div>
                        </td>
                        <td>
                          <StatusPill
                            label={humanise(item.status)}
                            status={item.status}
                            title={item.status === "DRAFT" ? privilegeDraftReason(item) || "Draft — awaiting Grant" : undefined}
                            onActivate={
                              canManagePrivileges && item.status === "DRAFT"
                                ? () => openAction("DECISION", { privilege: item })
                                : undefined
                            }
                          />
                        </td>
                        <td><ExpiryCell expiresOn={item.expires_on} /></td>
                      </tr>
                    );
                  }) : (
                    <tr>
                      <td colSpan={4}>{loading ? "Loading authorizations…" : "No authorizations match these filters."}</td>
                    </tr>
                  )}
                </tbody>
              </table>
            </div>
          </section>

          <aside className="qms-people__detail" aria-label="Selected authorization">
            {selected ? (
              <>
                <div className="qms-people__detail-head">
                  <span>Selected person</span>
                  <div className="qms-people__detail-title">
                    <RuleTypeIcon tone={ruleIconTone(selectedRule)} size={16} />
                    <h2>{selectedName}</h2>
                  </div>
                  <p>{expiryCaption}</p>
                  <div className="qms-people__detail-badges">
                    <StatusPill
                      label={humanise(selected.status)}
                      status={selected.status}
                      title={draftReason || undefined}
                      onActivate={openDraftDecision}
                    />
                    <span>{selectedRankLabel}</span>
                    {showSelectedTypeBadge ? <span>{selectedTypeLabel}</span> : null}
                  </div>
                  <p className={`qms-people__readiness-line is-${readinessTone}`}>
                    {readinessLabel}
                    {draftReason ? ` · ${draftReason}` : null}
                  </p>
                </div>

                <div className="qms-people__detail-actions qms-people__detail-actions--sticky">
                  {canManagePrivileges && allowedDecisions.length ? (
                    <button
                      type="button"
                      className={actionFlash === "DECISION" ? "is-primary is-action-done" : "is-primary"}
                      onClick={() => openAction("DECISION")}
                    >
                      {actionFlash === "DECISION"
                        ? <><CheckCircle2 size={15} className="qms-people__action-tick" aria-hidden="true" /> Done</>
                        : <><ShieldCheck size={15} aria-hidden="true" /> {selected.status === "DRAFT" ? "Grant / Decision" : "Decision"}</>}
                    </button>
                  ) : null}
                  {canManagePrivileges && trainingMissing ? (
                    <>
                      <input
                        ref={evidenceInputRef}
                        type="file"
                        accept=".pdf,.png,.jpg,.jpeg,.webp"
                        hidden
                        onChange={(event) => {
                          const file = event.target.files?.[0];
                          event.target.value = "";
                          if (file) void uploadEvidence(file);
                        }}
                      />
                      <button type="button" disabled={evidenceBusy || lifecycleBusy} onClick={() => evidenceInputRef.current?.click()}>
                        <Upload size={15} aria-hidden="true" /> {evidenceBusy ? "Uploading…" : "Upload evidence"}
                      </button>
                    </>
                  ) : null}
                  {canManagePrivileges && selected.status === "ACTIVE" ? (
                    <button type="button" disabled={bypassBusy || lifecycleBusy} onClick={() => setShowBypassForm((value) => !value)}>
                      <Shield size={15} aria-hidden="true" /> QM bypass
                    </button>
                  ) : null}
                  {canRunAuditPreflight ? (
                    <button type="button" onClick={() => openAction("AUDIT_ASSIGNMENT")}><ClipboardCheck size={15} aria-hidden="true" /> Assignment check</button>
                  ) : null}
                  <button type="button" disabled={lifecycleBusy} onClick={() => void downloadSelectedCertificate()}>
                    <Download size={15} aria-hidden="true" /> Download {selected.status === "ACTIVE" ? "certificate" : "record"}
                  </button>
                  {canManagePrivileges && PURGEABLE_STATUSES.includes(selected.status) ? (
                    <button
                      type="button"
                      className={actionFlash === "PURGE" ? "is-danger is-action-done" : "is-danger"}
                      disabled={lifecycleBusy || actionFlash === "PURGE"}
                      onClick={() => requestPurgeSelected()}
                    >
                      {actionFlash === "PURGE" ? (
                        <><CheckCircle2 size={15} className="qms-people__action-tick" aria-hidden="true" /> Done</>
                      ) : (
                        <><Trash2 size={15} aria-hidden="true" /> Delete</>
                      )}
                    </button>
                  ) : null}
                </div>

                <section className="qms-people__competence-strip" aria-label="QMS competence">
                  <header>
                    <strong>QMS competence</strong>
                    {activeBypass ? (
                      <span className="qms-people__competence-bypass">Bypass until {activeBypass.valid_until}</span>
                    ) : null}
                  </header>
                  <div className="qms-people__competence-chips">
                    {competenceChips.map((chip) => (
                      <span key={chip.label} className={`qms-people__competence-chip is-${chip.tone}`} title="Competence status from Training records">
                        <strong>{chip.label}</strong>
                        <small>{chip.detail}</small>
                      </span>
                    ))}
                  </div>
                </section>

                {showBypassForm && canManagePrivileges && selected.status === "ACTIVE" ? (
                  <div className="qms-people__bypass-form" aria-label="QM training bypass">
                    <label>
                      Bypass rationale
                      <textarea
                        value={bypassRationale}
                        onChange={(event) => setBypassRationale(event.target.value)}
                        rows={3}
                        placeholder="Why is a time-bounded training gate bypass justified?"
                      />
                    </label>
                    <label>
                      Valid until
                      <input type="date" value={bypassUntil} onChange={(event) => setBypassUntil(event.target.value)} />
                    </label>
                    <div className="qms-people__bypass-actions">
                      <button type="button" className="is-primary" disabled={bypassBusy} onClick={() => void submitQmBypass()}>
                        {bypassBusy ? "Saving…" : "Approve bypass"}
                      </button>
                      <button type="button" disabled={bypassBusy} onClick={() => setShowBypassForm(false)}>Cancel</button>
                    </div>
                  </div>
                ) : null}

                {canManagePrivileges && selectedIsAuditorPrivilege && selected.status === "ACTIVE" && auditorRankRules.length ? (
                  <div className="qms-people__rank-action">
                    <label>
                      Auditor rank
                      <select
                        value={selected.rule_id}
                        disabled={lifecycleBusy}
                        onChange={(event) => {
                          const next = rules.find((rule) => rule.id === event.target.value) || null;
                          if (next && next.id !== selected.rule_id) void changeRankTo(next);
                        }}
                      >
                        {auditorRankRules.map((rule) => (
                          <option key={rule.id} value={rule.id}>{rule.title}</option>
                        ))}
                      </select>
                    </label>
                    <p className="qms-people__lifecycle-hint">
                      {actionFlash === "RANK" ? (
                        <span className="qms-people__action-tick" style={{ display: "inline-flex", alignItems: "center", gap: 6, color: "var(--qms-people-positive)" }}>
                          <CheckCircle2 size={14} aria-hidden="true" /> Rank updated
                        </span>
                      ) : (
                        "Changing rank updates this authorization in place."
                      )}
                    </p>
                  </div>
                ) : null}

                {actionFlash === "SUSPEND" || actionFlash === "REVOKE" || actionFlash === "REINSTATE" ? (
                  <div className="qms-people__lifecycle-actions" aria-live="polite">
                    <button type="button" className="is-action-done" disabled>
                      <CheckCircle2 size={15} className="qms-people__action-tick" aria-hidden="true" /> Done
                    </button>
                  </div>
                ) : canManagePrivileges && (selected.status === "ACTIVE" || selected.status === "SUSPENDED") ? (
                  <div className="qms-people__lifecycle-actions" aria-label="Privilege lifecycle actions">
                    {selected.status === "ACTIVE" ? (
                      <>
                        <button type="button" className="is-warning" disabled={lifecycleBusy} onClick={() => runQuickDecision("SUSPEND", QUICK_RATIONALE.SUSPEND)}>
                          <PauseCircle size={15} aria-hidden="true" /> Suspend
                        </button>
                        <button type="button" className="is-danger" disabled={lifecycleBusy} onClick={() => runQuickDecision("REVOKE", QUICK_RATIONALE.REVOKE)}>
                          <Ban size={15} aria-hidden="true" /> Revoke
                        </button>
                      </>
                    ) : null}
                    {selected.status === "SUSPENDED" ? (
                      <>
                        <button type="button" className="is-primary" disabled={lifecycleBusy} onClick={() => runQuickDecision("REINSTATE", QUICK_RATIONALE.REINSTATE)}>
                          <RotateCcw size={15} aria-hidden="true" /> Reinstate
                        </button>
                        <button type="button" className="is-danger" disabled={lifecycleBusy} onClick={() => runQuickDecision("REVOKE", QUICK_RATIONALE.REVOKE)}>
                          <Ban size={15} aria-hidden="true" /> Revoke
                        </button>
                      </>
                    ) : null}
                  </div>
                ) : null}

                <details className="qms-people__eligibility-summary" open={selected.status === "DRAFT"}>
                  <summary>Grant readiness · {readinessLabel}</summary>
                  {snapshotMatchesSelection && selectedSnapshot ? (
                    <>
                      <div className="qms-people__gate-grid">
                        {displayGates.map(([gate, passed]) => (
                          <span key={gate} className={passed ? "is-pass" : "is-block"}>
                            <strong>{passed ? "Pass" : "Block"}</strong>{humanise(gate)}
                          </span>
                        ))}
                      </div>
                      {selectedSnapshot.training.missing.length ? (
                        <p>Missing training: {selectedSnapshot.training.missing.join(", ")}</p>
                      ) : (
                        <p>Required training evidence is satisfied.</p>
                      )}
                      {selected.status === "DRAFT" ? (
                        <p className="qms-people__form-hint">Independence is checked at assignment time, not for granting this draft.</p>
                      ) : null}
                    </>
                  ) : (
                    <p>{snapshotLoading || !snapshotMatchesSelection ? "Checking gates…" : "Eligibility unavailable for this authorization."}</p>
                  )}
                </details>

                <details className="qms-people__history">
                  <summary>Audit participation ({auditParticipationLoading ? "…" : auditParticipation.length})</summary>
                  {auditParticipationLoading ? (
                    <p className="qms-people__empty">Loading audit participation…</p>
                  ) : auditParticipation.length ? (
                    auditParticipation.map((item) => {
                      const href = auditOpenHref(item);
                      return (
                        <article key={`${item.audit_id}-${item.audit_ref}`} className="qms-people__participation-row">
                          <div>
                            <strong className="qms-people__participation-title">
                              <FileText size={14} aria-hidden="true" />
                              {item.audit_ref || item.title}
                            </strong>
                            <span>{humanise(item.status)}</span>
                          </div>
                          <p>{item.title}</p>
                          <small>{(item.roles || []).map((role) => humanise(role)).join(" · ") || "No roles"}</small>
                          <div className="qms-people__participation-actions">
                            {href ? (
                              <Link to={href}><ExternalLink size={13} aria-hidden="true" /> Open</Link>
                            ) : (
                              <span>Open unavailable</span>
                            )}
                            {item.has_issued_report ? (
                              <button type="button" onClick={() => void downloadAuditIssuedReport(item)}>
                                <Download size={13} aria-hidden="true" /> Download
                              </button>
                            ) : null}
                          </div>
                        </article>
                      );
                    })
                  ) : (
                    <p className="qms-people__empty">No audit participation recorded for this person.</p>
                  )}
                </details>

                <details className="qms-people__history">
                  <summary>Authorization history ({selected.decisions?.length || 0})</summary>
                  {selected.decisions?.length ? selected.decisions.slice().reverse().map((decision) => (
                    <article key={decision.id}>
                      <div><strong>{humanise(decision.decision_type)}</strong><span>{humanise(decision.resulting_status)}</span></div>
                      <p>{decision.rationale}</p>
                      <small>{new Date(decision.decided_at).toLocaleString()}</small>
                    </article>
                  )) : <p className="qms-people__empty">No decisions recorded yet.</p>}
                </details>

                <section className="qms-people__independence-panel" aria-label="Independence">
                  <header className="qms-people__independence-head">
                    <div>
                      <h3>Independence policy</h3>
                      <span className={`qms-people__independence-status ${independencePolicy?.enforced === false ? "is-deactivated" : "is-enforced"}`}>
                        {independencePolicy?.enforced === false ? "Tenant policy off" : "Tenant policy on"}
                      </span>
                    </div>
                    <div className="qms-people__independence-head-actions">
                      <button
                        type="button"
                        className="qms-people__icon-button"
                        aria-label="Independence rules"
                        title="Independence rules"
                        onClick={() => openAction("INDEPENDENCE_POLICY")}
                      >
                        <HelpCircle size={15} aria-hidden="true" />
                      </button>
                      {platformSuperuser ? (
                        actionFlash === "INDEPENDENCE_ON" || actionFlash === "INDEPENDENCE_OFF" ? (
                          <span className="qms-people__enforcement-toggle is-action-done" role="status">
                            <CheckCircle2 size={15} className="qms-people__action-tick" aria-hidden="true" /> Done
                          </span>
                        ) : (
                          <label className="qms-people__enforcement-toggle">
                            <input
                              type="checkbox"
                              checked={independencePolicy?.enforced !== false}
                              disabled={policyBusy || !independencePolicy}
                              onChange={(event) => void toggleIndependenceEnforcement(event.target.checked)}
                            />
                            Enforce
                          </label>
                        )
                      ) : null}
                    </div>
                  </header>

                  {independenceLoading ? (
                    <p className="qms-people__empty">Assessing independence…</p>
                  ) : (
                    <>
                      {independenceAssessment?.passed === false || independenceConflicts.length ? (
                        <div className="qms-people__independence-alert" role="status">
                          <AlertTriangle size={15} aria-hidden="true" />
                          <div>
                            <strong>{independenceHardBlocked ? "Independence conflict" : "Independence warning"}</strong>
                            <IndependenceFeedback
                              conflicts={independenceConflicts}
                              remediations={independenceAssessment?.remediations}
                              message={independenceAssessment?.message}
                              notes={independenceAssessment?.notes}
                            />
                          </div>
                        </div>
                      ) : (
                        <p className="qms-people__independence-ok">
                          {selected.status === "DRAFT"
                            ? "Grant does not require an independence check. Run Assignment check after this authorization is Active and tied to an audit."
                            : independenceAssessment?.pending
                              ? "No assignment context yet — run Assignment check with an audit or schedule to evaluate conflicts."
                              : "No independence conflicts detected for the current context."}
                        </p>
                      )}

                      {canRecordImpartialityForm ? (
                        <button
                          type="button"
                          className="qms-people__text-button"
                          onClick={() => openAction("IMPARTIALITY_FORM")}
                        >
                          Record impartiality form
                        </button>
                      ) : null}
                    </>
                  )}

                  <details className="qms-people__history qms-people__independence-history">
                    <summary>Impartiality forms ({independenceRows.length})</summary>
                    {independenceRows.length ? independenceRows.map((row) => (
                      <article key={row.id}>
                        <div><strong>{humanise(row.declaration)}</strong><span>{humanise(row.context_type)}</span></div>
                        <p>{row.rationale}</p>
                        <small>{new Date(row.declared_at).toLocaleString()}</small>
                      </article>
                    )) : <p className="qms-people__empty">No impartiality forms recorded for this person.</p>}
                  </details>
                </section>
              </>
            ) : (
              <div className="qms-people__placeholder">
                <UserRoundCheck size={30} />
                <strong>Select a row</strong>
                <p>Lifecycle, certificate download, and rank changes appear here.</p>
              </div>
            )}
          </aside>
        </section>
      ) : null}

      {confirmDialog ? (
        <div
          className="upsell-modal__backdrop qms-people__modal-layer"
          role="presentation"
          onClick={(event) => { if (event.target === event.currentTarget) setConfirmDialog(null); }}
        >
          <section
            className="upsell-modal qms-people__modal"
            role="alertdialog"
            aria-modal="true"
            aria-labelledby="qms-people-confirm-title"
            onClick={(event) => event.stopPropagation()}
          >
            <header className="upsell-modal__header">
              <div>
                <p className="upsell-modal__eyebrow">Confirm</p>
                <h3 className="upsell-modal__title" id="qms-people-confirm-title">
                  {confirmDialog.kind === "purge" ? "Delete authorization permanently?" : "Delete privilege rule?"}
                </h3>
              </div>
              <button
                type="button"
                className="upsell-modal__close"
                onClick={() => setConfirmDialog(null)}
                aria-label="Close confirmation"
                disabled={lifecycleBusy || deletingRule}
              >
                <X size={18} />
              </button>
            </header>
            <div className="qms-people__modal-form">
              <div className="qms-people__modal-scroll">
                {confirmDialog.kind === "purge" ? (
                  <p>
                    Permanently delete this authorization and its history for <strong>{confirmDialog.personName}</strong>?
                    This cannot be undone.
                  </p>
                ) : (
                  <p>
                    Delete privilege rule <strong>“{confirmDialog.ruleTitle}”</strong>? This cannot be undone.
                  </p>
                )}
              </div>
              <footer className="qms-people__modal-footer">
                <button type="button" disabled={lifecycleBusy || deletingRule} onClick={() => setConfirmDialog(null)}>
                  Cancel
                </button>
                <button
                  type="button"
                  className="is-danger"
                  disabled={lifecycleBusy || deletingRule}
                  onClick={() => {
                    if (confirmDialog.kind === "purge") purgeSelected();
                    else deleteSelectedRule();
                  }}
                >
                  <Trash2 size={15} aria-hidden="true" />
                  {confirmDialog.kind === "purge" ? "Delete permanently" : "Delete rule"}
                </button>
              </footer>
            </div>
          </section>
        </div>
      ) : null}

      {actionMode !== "NONE" ? (
        <div
          className="upsell-modal__backdrop qms-people__modal-layer"
          role="dialog"
          aria-modal="true"
          aria-label="People and privileges governed action"
          onClick={(event) => { if (event.target === event.currentTarget) closeAction(); }}
        >
          <section className="upsell-modal qms-people__modal" onClick={(event) => event.stopPropagation()}>
            <header className="upsell-modal__header">
              <div>
                <p className="upsell-modal__eyebrow">Governed action</p>
                <h3 className="upsell-modal__title">{actionTitle(actionMode)}</h3>
              </div>
              <button type="button" className="upsell-modal__close" onClick={closeAction} aria-label="Close action"><X size={18} /></button>
            </header>
            {error ? (
              <div className="qms-people__error qms-people__error--modal" role="alert">
                <AlertTriangle size={16} aria-hidden="true" />
                <span>{error}</span>
              </div>
            ) : null}

            {actionMode === "CREATE" && canManagePrivileges ? (
              <form onSubmit={submitDraft} className="qms-people__modal-form">
                <div className="qms-people__modal-scroll">
                  <div className="qms-people__form-row">
                    <label>
                      Rule
                      <select
                        value={ruleId}
                        onChange={(event) => {
                          setRuleId(event.target.value);
                          setUserIds([]);
                          setPersonQuery("");
                        }}
                        required
                      >
                        <option value="">Select rule</option>
                        {activeRules.map((rule) => (
                          <option key={rule.id} value={rule.id}>
                            {rule.title}
                          </option>
                        ))}
                      </select>
                    </label>
                    <label>
                      Scope
                      <select value={scopeKey} onChange={(event) => setScopeKey(event.target.value)}>
                        <option value="GLOBAL">GLOBAL</option>
                      </select>
                    </label>
                  </div>

                  <section className="qms-people__form-section" aria-labelledby="people-authorize-people">
                    <header>
                      <h3 id="people-authorize-people">People</h3>
                      <span>{userIds.length} selected</span>
                    </header>
                    <p className="qms-people__form-hint">{authorizeFilterHint}</p>
                    <div className="qms-people__batch-people">
                      <div className="qms-people__batch-people-toolbar">
                        <label className="qms-people__search">
                          <Search size={15} aria-hidden="true" />
                          <input value={personQuery} onChange={(event) => setPersonQuery(event.target.value)} placeholder="Filter people" disabled={!ruleId} />
                        </label>
                        <button type="button" onClick={() => setUserIds(batchPersonnel.map((person) => person.id))} disabled={!batchPersonnel.length}>All</button>
                        <button type="button" onClick={() => setUserIds([])} disabled={!userIds.length}>Clear</button>
                      </div>
                      <div className="qms-people__person-checklist" role="group" aria-label="People to authorize">
                        {!ruleId ? (
                          <div className="qms-people__empty-inline-block">
                            <p className="qms-people__empty-inline">Choose a rule first.</p>
                          </div>
                        ) : batchPersonnel.length ? (
                          batchPersonnel.map((person) => {
                            const checked = userIds.includes(person.id);
                            const validity = authorizeValidityLabel({
                              validUntil: person.valid_until,
                              matchReasons: person.match_reasons,
                            });
                            return (
                              <label key={person.id} className={`qms-people__person-option${checked ? " is-selected" : ""}${validity.dueSoon ? " is-due-soon" : ""}`}>
                                <input type="checkbox" checked={checked} onChange={() => toggleBatchPerson(person.id)} />
                                <span className="qms-people__person-name">
                                  {personDisplay(person.full_name)}
                                  {validity.text && authorizeFilterActive ? (
                                    <span className={`qms-people__person-meta${validity.dueSoon ? " is-due-soon" : ""}`}>
                                      {validity.text}
                                    </span>
                                  ) : null}
                                </span>
                                {validity.dueSoon ? (
                                  <span className="qms-people__person-due-warn" title="Expires within 60 days">
                                    <AlertTriangle size={14} aria-hidden="true" />
                                  </span>
                                ) : (
                                  <span className="qms-people__person-role" aria-hidden="true" />
                                )}
                              </label>
                            );
                          })
                        ) : (
                          <div className="qms-people__empty-inline-block">
                            <p className="qms-people__empty-inline">
                              {authorizeCandidatesLoading
                                ? "Loading people who meet this rule…"
                                : personQuery.trim()
                                  ? "No matches in the rule-filtered list."
                                  : authorizeFilterActive
                                    ? "No one has a Training record or scheduled enrollment for this rule’s courses yet."
                                    : "No personnel loaded."}
                            </p>
                          </div>
                        )}
                      </div>
                    </div>
                  </section>

                  <label className="qms-people__checkbox">
                    <input type="checkbox" checked={grantOnCreate} onChange={(event) => setGrantOnCreate(event.target.checked)} />
                    Grant now
                  </label>
                  {grantOnCreate ? (
                    <label>
                      Rationale
                      <textarea value={batchRationale} onChange={(event) => setBatchRationale(event.target.value)} minLength={8} rows={2} required />
                    </label>
                  ) : null}
                </div>
                <footer className="qms-people__modal-footer">
                  <button type="button" onClick={closeAction}>Cancel</button>
                  <button
                    type="submit"
                    className="is-primary"
                    disabled={creating || !ruleId || !userIds.length || (grantOnCreate && batchRationale.trim().length < 8)}
                  >
                    {creating
                      ? "Working…"
                      : grantOnCreate
                        ? `Authorize ${userIds.length || ""}`
                        : `Create ${userIds.length || ""} draft${userIds.length === 1 ? "" : "s"}`}
                  </button>
                </footer>
              </form>
            ) : null}

            {(actionMode === "CREATE_RULE" || actionMode === "EDIT_RULE") && canManagePrivileges ? (
              <form onSubmit={submitRule} className="qms-people__modal-form">
                <div className="qms-people__modal-scroll">
                  <label>
                    Privilege type
                    <select
                      value={ruleType}
                      disabled={actionMode === "EDIT_RULE"}
                      onChange={(event) => {
                        const next = event.target.value as QmsPrivilegeRule["privilege_type"];
                        if (actionMode === "CREATE_RULE") applyPrivilegeTypePreset(next);
                        else setRuleType(next);
                      }}
                    >
                      {PRIVILEGE_TYPES.map((type) => <option key={type} value={type}>{humanisePrivilegeType(type)}</option>)}
                    </select>
                  </label>
                  {actionMode === "CREATE_RULE" ? (
                    <label>
                      Code
                      <input value={ruleCode} onChange={(event) => setRuleCode(event.target.value.toUpperCase())} required pattern="[A-Z0-9_\-]+" />
                    </label>
                  ) : null}
                  <label>
                    Title
                    <input value={ruleTitle} onChange={(event) => setRuleTitle(event.target.value)} required minLength={3} />
                  </label>
                  <label>
                    Description
                    <textarea value={ruleDescription} onChange={(event) => setRuleDescription(event.target.value)} rows={2} />
                  </label>
                  <fieldset className="qms-people__form-section">
                    <header>
                      <h3>Required training</h3>
                      <span>{ruleTrainingCodes.length} selected</span>
                    </header>
                    <p className="qms-people__form-hint">
                      Selected courses are required with <strong>AND</strong> by default. Initial (INIT) and refresher (REF) courses are kept as a pair.
                    </p>
                    <div className="qms-people__person-checklist" role="group" aria-label="Required training courses">
                      {trainingCourses.length ? trainingCourses.map((course) => {
                        const code = normalizeCourseCode(course.course_id);
                        const checked = courseCodeSelected(code, ruleTrainingCodes);
                        return (
                          <label key={course.id || code} className={`qms-people__person-option${checked ? " is-selected" : ""}`}>
                            <input type="checkbox" checked={checked} onChange={() => toggleTrainingCode(code)} />
                            <span className="qms-people__person-name">{course.course_name}</span>
                            <span className="qms-people__person-role">{code}</span>
                          </label>
                        );
                      }) : ruleTrainingCodes.length ? (
                        ruleTrainingCodes.map((code) => (
                          <label key={code} className="qms-people__person-option is-selected">
                            <input type="checkbox" checked onChange={() => toggleTrainingCode(code)} />
                            <span className="qms-people__person-name">{code}</span>
                            <span className="qms-people__person-role">configured</span>
                          </label>
                        ))
                      ) : (
                        <p className="qms-people__empty-inline">No training courses available.</p>
                      )}
                    </div>
                    {ruleTrainingNotice ? (
                      <p className="qms-people__training-notice" role="status">{ruleTrainingNotice}</p>
                    ) : null}
                    <div className="qms-people__rule-summary" aria-live="polite">
                      <span className="qms-people__rule-summary-label">Rule summary</span>
                      <code className="qms-people__rule-summary-value">
                        {ruleTrainingAdvanced && ruleTrainingExpression.trim()
                          ? ruleTrainingExpression.trim()
                          : formatTrainingRuleSummary(ruleTrainingCodes, ruleTrainingJoin)}
                      </code>
                    </div>
                    <div className="qms-people__rule-advanced">
                      <button
                        type="button"
                        className="qms-people__linkish"
                        onClick={() => {
                          const next = !ruleTrainingAdvanced;
                          setRuleTrainingAdvanced(next);
                          if (next) {
                            setRuleTrainingExpression(defaultTrainingExpression(ruleTrainingCodes, ruleTrainingJoin));
                            setRuleTrainingExpressionError(null);
                          } else {
                            setRuleTrainingJoin("AND");
                            syncTrainingExpressionFromCodes(ruleTrainingCodes, "AND");
                          }
                        }}
                      >
                        {ruleTrainingAdvanced ? "Hide advanced rule" : "Advanced rule"}
                      </button>
                      {ruleTrainingAdvanced ? (
                        <label className="qms-people__rule-expression">
                          Custom rule (use AND / OR)
                          <textarea
                            value={ruleTrainingExpression}
                            rows={2}
                            spellCheck={false}
                            placeholder="QMS-INIT AND QMS-REF AND QMS-ADMIN"
                            onChange={(event) => applyTrainingExpression(event.target.value)}
                          />
                          <span>
                            Example: QMS-INIT AND QMS-REF AND QMS-ADMIN · or (QMS-INIT OR QMS-REF) AND QMS-ADMIN
                          </span>
                        </label>
                      ) : null}
                      {ruleTrainingExpressionError ? (
                        <p className="qms-people__training-notice is-error" role="alert">{ruleTrainingExpressionError}</p>
                      ) : null}
                    </div>
                    {!trainingCourses.length && ruleTrainingCodes.length ? (
                      <p className="qms-people__form-hint">Training catalogue unavailable — showing this rule’s persisted course codes. Refresh when Training is online to pick from the full list.</p>
                    ) : null}
                  </fieldset>
                  <label>
                    Max concurrent
                    <select value={ruleMaxConcurrent} onChange={(event) => setRuleMaxConcurrent(event.target.value)}>
                      {MAX_CONCURRENT_OPTIONS.map((option) => (
                        <option key={option || "unlimited"} value={option}>{option ? option : "Unlimited"}</option>
                      ))}
                    </select>
                  </label>
                  <label className="qms-people__checkbox">
                    <input type="checkbox" checked={ruleIndependenceRequired} onChange={(event) => setRuleIndependenceRequired(event.target.checked)} />
                    Independence required
                  </label>
                  {ruleType === "AUDITOR" ? (
                    <label className="qms-people__checkbox">
                      <input
                        type="checkbox"
                        checked={ruleSupervisedDevelopment}
                        onChange={(event) => {
                          const next = event.target.checked;
                          setRuleSupervisedDevelopment(next);
                          setRuleTrainingNotice(null);
                          setRuleTrainingExpressionError(null);
                          setRuleTrainingAdvanced(false);
                          setRuleTrainingJoin("AND");
                          if (next) {
                            setRuleTrainingCodes([]);
                            setRuleTrainingExpression("");
                            setRuleIndependenceRequired(false);
                            setRuleFormBaselineScope((current) => {
                              const nextScope = { ...current };
                              delete nextScope.qms_competence;
                              return {
                                ...nextScope,
                                supervised_development: true,
                                allowed_assignment_roles: ["OBSERVER_AUDITOR", "ASSISTANT_AUDITOR"],
                              };
                            });
                          } else {
                            setRuleIndependenceRequired(true);
                            const codes = defaultTrainingCodesForPrivilegeType("AUDITOR");
                            setRuleTrainingCodes(codes);
                            setRuleTrainingExpression(defaultTrainingExpression(codes, "AND"));
                            setRuleFormBaselineScope(defaultCompetenceScopeForPrivilegeType("AUDITOR"));
                          }
                        }}
                      />
                      Supervised (observer/trainee)
                    </label>
                  ) : null}
                  {actionMode === "EDIT_RULE" ? (
                    <label className="qms-people__checkbox">
                      <input type="checkbox" checked={ruleActive} onChange={(event) => setRuleActive(event.target.checked)} />
                      Rule active
                    </label>
                  ) : null}
                </div>
                <footer className="qms-people__modal-footer">
                  <button type="button" onClick={closeAction}>Cancel</button>
                  <button type="submit" className="is-primary" disabled={savingRule || !ruleTitle.trim() || (actionMode === "CREATE_RULE" && !ruleCode.trim())}>
                    {savingRule ? "Saving…" : actionMode === "CREATE_RULE" ? "Create rule" : "Save rule"}
                  </button>
                </footer>
              </form>
            ) : null}

            {actionMode === "DECISION" && selected && canManagePrivileges ? (
              <form onSubmit={submitDecision} className="qms-people__modal-form">
                <div className="qms-people__modal-scroll">
                  <div className="qms-people__context-card"><strong>{selectedName}</strong><span>{selectedRankLabel || humanise(selected.privilege_code)}</span></div>
                  {selected.status === "DRAFT" ? (
                    <div className={`qms-people__decision-readiness ${grantBlocked ? "is-blocked" : "is-ready"}`}>
                      <strong>{readinessLabel}</strong>
                      <p>{draftReason || "Choose Grant to activate, or Reject to discard."}</p>
                      {displayGates.length ? (
                        <div className="qms-people__gate-grid">
                          {displayGates.map(([gate, passed]) => (
                            <span key={gate} className={passed ? "is-pass" : "is-block"}>
                              <strong>{passed ? "Pass" : "Block"}</strong>{humanise(gate)}
                            </span>
                          ))}
                        </div>
                      ) : null}
                    </div>
                  ) : null}
                  <label>
                    Decision
                    <select value={decisionType} onChange={(event) => setDecisionType(event.target.value as QmsPrivilegeDecision["decision_type"])}>
                      {allowedDecisions.map((decision) => <option key={decision} value={decision}>{privilegeDecisionLabel(decision)}</option>)}
                    </select>
                  </label>
                  {decisionType === "GRANT" || decisionType === "RENEW" || decisionType === "REINSTATE" ? (
                    <div className="qms-people__dates">
                      <label>Effective <small>(optional — defaults to today)</small><input type="date" value={effectiveFrom} onChange={(event) => setEffectiveFrom(event.target.value)} /></label>
                      <label>
                        Expiry
                        <small>
                          {courseExpiryCap
                            ? `capped to course · ${courseExpiryCap}`
                            : "optional — set from course currency when available"}
                        </small>
                        <input
                          type="date"
                          value={expiresOn}
                          max={courseExpiryCap || undefined}
                          onChange={(event) => {
                            const next = event.target.value;
                            setExpiresOn(capPrivilegeExpiresOn(next, selectedSnapshot?.training) || next);
                          }}
                        />
                      </label>
                    </div>
                  ) : null}
                  <label>
                    Rationale
                    <textarea value={decisionReason} onChange={(event) => setDecisionReason(event.target.value)} minLength={8} rows={3} required />
                  </label>
                  {grantBlocked ? (
                    <p className="qms-people__form-hint" role="status">Grant is blocked until failed gates above are cleared (or Reject the draft).</p>
                  ) : null}
                </div>
                <footer className="qms-people__modal-footer">
                  <button type="button" onClick={closeAction}>Cancel</button>
                  <button
                    type="submit"
                    className="is-primary"
                    disabled={deciding || decisionReason.trim().length < 8 || (grantBlocked && decisionType !== "REJECT")}
                  >
                    {deciding ? "Recording…" : decisionType === "GRANT" ? "Grant authorization" : "Record decision"}
                  </button>
                </footer>
              </form>
            ) : null}

            {actionMode === "AUDIT_ASSIGNMENT" && selected && selectedRule && canRunAuditPreflight ? (
              <form onSubmit={submitAuditAssignment} className="qms-people__modal-form">
                <div className="qms-people__modal-scroll">
                  <div className="qms-people__context-card"><strong>{selectedName}</strong><span>{humanise(selected.privilege_code)}</span></div>
                  <label>
                    Role
                    <select value={assignmentRole} disabled={checkingAssignment} onChange={(event) => { invalidateAssignmentResult(); setAssignmentRole(event.target.value as QmsAuditorAssignmentRole); }}>
                      {selectedRule.privilege_type === "LEAD_AUDITOR"
                        ? <option value="LEAD_AUDITOR">Lead auditor</option>
                        : <><option value="OBSERVER_AUDITOR">Observer</option><option value="ASSISTANT_AUDITOR">Assistant</option></>}
                    </select>
                  </label>
                  <label>
                    Date
                    <input type="date" value={assignmentDate} disabled={checkingAssignment} onChange={(event) => { invalidateAssignmentResult(); setAssignmentDate(event.target.value); }} required />
                  </label>
                  <label>
                    Scope
                    <input value={assignmentScopeKey} disabled={checkingAssignment} onChange={(event) => { invalidateAssignmentResult(); setAssignmentScopeKey(event.target.value); }} required placeholder="LINE_MAINTENANCE" />
                  </label>
                  <label>
                    Context
                    <select value={assignmentContextType} disabled={checkingAssignment} onChange={(event) => { invalidateAssignmentResult(); setAssignmentContextType(event.target.value as AssignmentContextType); }} required={assignmentContextRequired}>
                      <option value="">{assignmentContextRequired ? "Select context" : "Optional"}</option>
                      <option value="AUDIT">Audit</option>
                      <option value="AUDIT_SCHEDULE">Audit schedule</option>
                      <option value="PROGRAMME_ITEM">Programme item</option>
                      <option value="MISSION">Mission</option>
                      <option value="ASSURANCE_CASE">Assurance case</option>
                      <option value="OTHER">Other</option>
                    </select>
                  </label>
                  <label>
                    Context ID
                    <input value={assignmentContextId} disabled={checkingAssignment} onChange={(event) => { invalidateAssignmentResult(); setAssignmentContextId(event.target.value); }} required={assignmentContextRequired} />
                  </label>
                  {assignmentResultAppliesToSelection && assignmentResult && assignmentResultInput ? (
                    <div className={`qms-people__eligibility ${assignmentEligible ? "is-eligible" : "is-blocked"}`}>
                      <strong>{assignmentEligible ? "Eligible" : "Blocked"}</strong>
                      <span>{humanise(assignmentResultInput.assignment_role)} · {assignmentResultInput.assignment_date}</span>
                      {assignmentAssessment ? (
                        <div className="qms-people__gate-grid">
                          {Object.entries(assignmentAssessment.hard_gates).map(([gate, passed]) => (
                            <span key={gate} className={passed ? "is-pass" : "is-block"}><strong>{passed ? "Pass" : "Block"}</strong>{humanise(gate)}</span>
                          ))}
                        </div>
                      ) : null}
                      {!assignmentUsesSelectedPrivilege ? <p>Preflight did not use this selected authorization.</p> : null}
                      {assignmentResult.reason ? <p>{assignmentResult.reason}</p> : null}
                      {assignmentAssessment?.independence && (
                        assignmentAssessment.independence.passed === false
                        || (assignmentAssessment.independence.conflicts?.length ?? 0) > 0
                        || assignmentAssessment.independence.message
                      ) ? (
                        <div className="qms-people__independence-alert is-inline" role="status">
                          <AlertTriangle size={15} aria-hidden="true" />
                          <div>
                            <strong>Independence gate</strong>
                            <IndependenceFeedback
                              conflicts={assignmentAssessment.independence.conflicts}
                              remediations={assignmentAssessment.independence.remediations}
                              message={assignmentAssessment.independence.message}
                              notes={assignmentAssessment.independence.notes}
                            />
                          </div>
                        </div>
                      ) : assignmentAssessment?.independence.message ? (
                        <p>{assignmentAssessment.independence.message}</p>
                      ) : null}
                    </div>
                  ) : null}
                </div>
                <footer className="qms-people__modal-footer">
                  <button type="button" onClick={closeAction}>Cancel</button>
                  <button type="submit" className="is-primary" disabled={checkingAssignment || !assignmentInputComplete}>
                    {checkingAssignment ? "Checking…" : "Run preflight"}
                  </button>
                </footer>
              </form>
            ) : null}

            {actionMode === "INDEPENDENCE_POLICY" ? (
              <div className="qms-people__modal-form">
                <div className="qms-people__modal-scroll">
                  <p className="qms-people__independence-policy-intro">
                    Independence is enforced by the portal from ISO 19011 / ISO 9001 rules. Operators cannot freely declare independence.
                  </p>
                  <ul className="qms-people__independence-rules">
                    {(independencePolicy?.rules || []).map((rule) => (
                      <li key={rule.code}>
                        <strong>{rule.title}</strong>
                        <small>{rule.standard}</small>
                        <span>{rule.summary}</span>
                      </li>
                    ))}
                  </ul>
                  {(independencePolicy?.remediations || []).length ? (
                    <>
                      <h4 className="qms-people__independence-subtitle">Remediation options</h4>
                      <ul className="qms-people__independence-remediations">
                        {independencePolicy?.remediations.map((item) => (
                          <li key={item.code}>
                            <strong>{item.label}</strong>
                            <span>{item.detail}</span>
                          </li>
                        ))}
                      </ul>
                    </>
                  ) : null}
                </div>
                <footer className="qms-people__modal-footer">
                  <button type="button" className="is-primary" onClick={closeAction}>Close</button>
                </footer>
              </div>
            ) : null}

            {actionMode === "IMPARTIALITY_FORM" && canManageAuditGovernance && canRecordImpartialityForm ? (
              <form onSubmit={submitImpartialityForm} className="qms-people__modal-form">
                <div className="qms-people__modal-scroll">
                  <p className="qms-people__independence-policy-intro">
                    Record an Auditor Impartiality Form for residual small-organisation cases. This does not clear hard conflicts such as auditing your own work or department.
                  </p>
                  <label>
                    Person
                    <select value={indUserId} onChange={(event) => setIndUserId(event.target.value)} required>
                      <option value="">Select person</option>
                      {personnel.map((person) => (
                        <option key={person.id} value={person.id}>{personDisplay(person.full_name)}</option>
                      ))}
                    </select>
                  </label>
                  <label>
                    Context
                    <select value={indContextType} onChange={(event) => setIndContextType(event.target.value as typeof indContextType)}>
                      <option value="AUDIT_SCHEDULE">Audit schedule</option>
                      <option value="AUDIT">Audit</option>
                      <option value="PROGRAMME_ITEM">Programme item</option>
                      <option value="MISSION">Mission</option>
                      <option value="ASSURANCE_CASE">Assurance case</option>
                      <option value="OTHER">Other</option>
                    </select>
                  </label>
                  <label>
                    Context ID
                    <input value={indContextId} onChange={(event) => setIndContextId(event.target.value)} required />
                  </label>
                  <label>
                    Form outcome
                    <select value={indDeclaration} onChange={(event) => setIndDeclaration(event.target.value as typeof indDeclaration)}>
                      <option value="REQUIRES_REVIEW">Requires review</option>
                      <option value="CONFLICT">Conflict disclosed</option>
                    </select>
                  </label>
                  <label>
                    Relationship
                    <input value={indRelationship} onChange={(event) => setIndRelationship(event.target.value)} />
                  </label>
                  <label>
                    Rationale
                    <textarea value={indRationale} onChange={(event) => setIndRationale(event.target.value)} minLength={8} rows={3} required />
                  </label>
                </div>
                <footer className="qms-people__modal-footer">
                  <button type="button" onClick={closeAction}>Cancel</button>
                  <button type="submit" className="is-primary" disabled={declaring || !indUserId.trim() || !indContextId.trim() || indRationale.trim().length < 8}>
                    {declaring ? "Recording…" : "Record impartiality form"}
                  </button>
                </footer>
              </form>
            ) : null}
          </section>
        </div>
      ) : null}
    </main>
  );
};

export default QmsPeoplePage;
