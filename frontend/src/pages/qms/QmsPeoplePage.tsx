import React, { FormEvent, useCallback, useEffect, useMemo, useRef, useState } from "react";
import { AlertTriangle, BookOpen, CheckCircle2, Plus, RefreshCw, Search, ShieldCheck, UserRoundCheck, X } from "lucide-react";
import { useSearchParams } from "react-router-dom";

import { hasQmsRolePermission } from "../../app/routeGuards";
import { clearQmsApiResponseCache } from "../../services/apiClient";
import { qmsListAuditPersonnelOptions, type QMSPersonOption } from "../../services/qmsCore";
import {
  createQmsPrivilege,
  createQmsPrivilegeRule,
  decideQmsPrivilege,
  declareQmsIndependence,
  getQmsEligibility,
  getQmsPeopleSummary,
  listQmsIndependenceDeclarations,
  listQmsPrivilegeRules,
  listQmsPrivileges,
  preflightQmsAuditorAssignment,
  updateQmsPrivilegeRule,
  type QmsAuditorAssignmentAssessment,
  type QmsAuditorAssignmentRole,
  type QmsAuditorEligibilityPreflight,
  type QmsEligibility,
  type QmsIndependenceDeclaration,
  type QmsPeopleSummary,
  type QmsPrivilege,
  type QmsPrivilegeDecision,
  type QmsPrivilegeRule,
} from "../../services/qmsPeople";
import { allowedPrivilegeDecisions, defaultPrivilegeDecision, privilegeDecisionLabel } from "./qmsPeopleDecisions";
import { catalogEntryForType, humanisePrivilegeType, QMS_PRIVILEGE_ROLE_CATALOG } from "./qmsPrivilegeRoleCatalog";
import "../../styles/qms-people.css";

type Props = { amoCode: string };
type PageTab = "privileges" | "rules" | "reference";
type ActionMode = "NONE" | "CREATE" | "DECISION" | "AUDIT_ASSIGNMENT" | "INDEPENDENCE" | "CREATE_RULE" | "EDIT_RULE";
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

const EMPTY_SUMMARY: QmsPeopleSummary = { active_privileges: 0, expiring_within_60_days: 0, suspended_privileges: 0, independence_exceptions: 0 };
const PRIVILEGE_TYPES: QmsPrivilegeRule["privilege_type"][] = ["LEAD_AUDITOR", "AUDITOR", "QUALITY_INSPECTOR", "AUTHORIZATION_REVIEWER", "CUSTOM"];
const ACTION_MODES = new Set<ActionMode>(["CREATE", "DECISION", "AUDIT_ASSIGNMENT", "INDEPENDENCE", "CREATE_RULE", "EDIT_RULE"]);
const PAGE_TABS = new Set<PageTab>(["privileges", "rules", "reference"]);
const DEFAULT_BATCH_RATIONALE = "Batch grant for governed audit assignment eligibility.";
const QUICK_RATIONALE = {
  SUSPEND: "Suspended via People authorization board quick action.",
  REVOKE: "Revoked via People authorization board quick action.",
  REINSTATE: "Reinstated via People authorization board quick action.",
  PROMOTE_GRANT: "Promoted from Observer/Trainee to Auditor under competence lifecycle.",
  PROMOTE_SUSPEND: "Suspended Observer/Trainee after promotion to Auditor.",
  DEMOTE_GRANT: "Demoted from Auditor to Observer/Trainee under competence lifecycle.",
  DEMOTE_SUSPEND: "Suspended Auditor after demotion to Observer/Trainee.",
} as const;

function messageFromError(error: unknown): string {
  return error instanceof Error ? error.message : "The People & Privileges operation could not be completed.";
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

function findDefaultAuditorRule(rules: QmsPrivilegeRule[]): QmsPrivilegeRule | null {
  return (
    rules.find((rule) => rule.is_active && rule.privilege_code === "AUDITOR_GLOBAL")
    || rules.find((rule) => rule.is_active && isFullAuditorRule(rule))
    || null
  );
}

function findDefaultObserverTraineeRule(rules: QmsPrivilegeRule[]): QmsPrivilegeRule | null {
  return (
    rules.find((rule) => rule.is_active && rule.privilege_code === "OBSERVER_TRAINEE_GLOBAL")
    || rules.find((rule) => rule.is_active && isObserverTraineeRule(rule))
    || null
  );
}

function matchingPrivilegeRecord(
  items: QmsPrivilege[],
  input: { userId: string; privilegeCode: string; scopeKey: string },
): QmsPrivilege | null {
  const scope = input.scopeKey.trim().toUpperCase() || "GLOBAL";
  return (
    items.find(
      (item) =>
        item.user_id === input.userId
        && item.privilege_code === input.privilegeCode
        && item.scope_key.trim().toUpperCase() === scope,
    ) || null
  );
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

function shortIdentifier(value: string): string {
  if (value.length <= 24) return value;
  return `${value.slice(0, 10)}…${value.slice(-6)}`;
}

function bindEligibilityToPrivilege(snapshot: QmsEligibility, privilege: QmsPrivilege): QmsEligibility {
  const selectedPrivilegeMatches = privilege.status === "ACTIVE" && snapshot.active_privilege?.id === privilege.id;
  return {
    ...snapshot,
    eligible: snapshot.eligible && selectedPrivilegeMatches,
    hard_gates: { ...snapshot.hard_gates, selected_privilege_active: selectedPrivilegeMatches },
  };
}

function selectedAssignmentAssessment(
  result: QmsAuditorEligibilityPreflight | null,
  rule: QmsPrivilegeRule | null,
): QmsAuditorAssignmentAssessment | null {
  if (!result || !rule) return null;
  if (result.assessment?.rule_id === rule.id) return result.assessment;
  return result.assessments.find((assessment) => assessment.rule_id === rule.id) || null;
}

function parseTrainingCodes(value: string): string[] {
  return value.split(/[,\n]/).map((item) => item.trim().toUpperCase()).filter(Boolean);
}

function trainingCodesLabel(codes: string[]): string {
  return codes.length ? codes.join(", ") : "None";
}

const QmsPeoplePage: React.FC<Props> = ({ amoCode }) => {
  const [searchParams, setSearchParams] = useSearchParams();
  const deepLinkConsumed = useRef(false);
  const [pageTab, setPageTab] = useState<PageTab>("privileges");
  const [summary, setSummary] = useState<QmsPeopleSummary>(EMPTY_SUMMARY);
  const [rules, setRules] = useState<QmsPrivilegeRule[]>([]);
  const [privileges, setPrivileges] = useState<QmsPrivilege[]>([]);
  const [personnel, setPersonnel] = useState<QMSPersonOption[]>([]);
  const [independenceRows, setIndependenceRows] = useState<QmsIndependenceDeclaration[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState("");
  const [notice, setNotice] = useState("");
  const [statusFilter, setStatusFilter] = useState<QmsPrivilege["status"] | "ALL">("ALL");
  const [search, setSearch] = useState("");
  const [showInactiveRules, setShowInactiveRules] = useState(true);
  const [actionMode, setActionMode] = useState<ActionMode>("NONE");

  const [ruleId, setRuleId] = useState("");
  const [userIds, setUserIds] = useState<string[]>([]);
  const [personQuery, setPersonQuery] = useState("");
  const [scopeKey, setScopeKey] = useState("GLOBAL");
  const [grantOnCreate, setGrantOnCreate] = useState(true);
  const [batchRationale, setBatchRationale] = useState(DEFAULT_BATCH_RATIONALE);
  const [creating, setCreating] = useState(false);

  const [selectedId, setSelectedId] = useState("");
  const [selectedRuleId, setSelectedRuleId] = useState("");
  const [decisionType, setDecisionType] = useState<QmsPrivilegeDecision["decision_type"]>("GRANT");
  const [decisionReason, setDecisionReason] = useState("");
  const [effectiveFrom, setEffectiveFrom] = useState("");
  const [expiresOn, setExpiresOn] = useState("");
  const [deciding, setDeciding] = useState(false);
  const [lifecycleBusy, setLifecycleBusy] = useState(false);
  const [personnelLoading, setPersonnelLoading] = useState(false);

  const [ruleCode, setRuleCode] = useState("");
  const [ruleTitle, setRuleTitle] = useState("");
  const [ruleType, setRuleType] = useState<QmsPrivilegeRule["privilege_type"]>("LEAD_AUDITOR");
  const [ruleDescription, setRuleDescription] = useState("");
  const [ruleTraining, setRuleTraining] = useState("");
  const [ruleIndependenceRequired, setRuleIndependenceRequired] = useState(true);
  const [ruleMaxConcurrent, setRuleMaxConcurrent] = useState("");
  const [ruleSupervisedDevelopment, setRuleSupervisedDevelopment] = useState(false);
  const [ruleActive, setRuleActive] = useState(true);
  const [savingRule, setSavingRule] = useState(false);

  const [selectedSnapshot, setSelectedSnapshot] = useState<QmsEligibility | null>(null);
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
  const [indDeclaration, setIndDeclaration] = useState<"INDEPENDENT" | "CONFLICT" | "REQUIRES_REVIEW">("INDEPENDENT");
  const [indRelationship, setIndRelationship] = useState("");
  const [indRationale, setIndRationale] = useState("");
  const [declaring, setDeclaring] = useState(false);

  const personLabelById = useMemo(() => {
    const map = new Map<string, string>();
    for (const person of personnel) {
      map.set(person.id, person.full_name || person.id);
    }
    return map;
  }, [personnel]);

  const loadPersonnel = useCallback(async (signal?: AbortSignal, options: { bypassCache?: boolean } = {}) => {
    setPersonnelLoading(true);
    try {
      const personnelResponse = await qmsListAuditPersonnelOptions(
        amoCode,
        { limit: 100, bypassCache: options.bypassCache },
        signal,
      );
      if (signal?.aborted) return;
      setPersonnel(personnelResponse);
    } catch (nextError) {
      if (!(nextError instanceof DOMException && nextError.name === "AbortError") && !signal?.aborted) {
        // Soft-fail so privilege board still loads; authorize drawer surfaces empty + retry.
        setError((current) => current || `Personnel directory unavailable: ${messageFromError(nextError)}`);
      }
    } finally {
      setPersonnelLoading(false);
    }
  }, [amoCode]);

  const loadGenerationRef = useRef(0);

  const load = useCallback(async (signal?: AbortSignal) => {
    const generation = ++loadGenerationRef.current;
    // Always bypass GET cache: an empty/stale rules payload (e.g. prior RLS miss)
    // otherwise leaves the board looking like the tenant has no privilege rules.
    clearQmsApiResponseCache();
    setLoading(true);
    setError("");
    try {
      // Settle independently so a slow/failing summary cannot blank rules/privileges.
      const [summaryResult, rulesResult, privilegesResult] = await Promise.allSettled([
        getQmsPeopleSummary(amoCode, signal),
        listQmsPrivilegeRules(amoCode, { includeInactive: true }, signal),
        listQmsPrivileges(amoCode, {}, signal),
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
      if (failures.length) setError(failures.join(" · "));
      setSnapshotRevision((value) => value + 1);
      void loadPersonnel(signal, { bypassCache: true });
    } catch (nextError) {
      if (!(nextError instanceof DOMException && nextError.name === "AbortError") && generation === loadGenerationRef.current) {
        setError(messageFromError(nextError));
      }
    } finally {
      if (generation === loadGenerationRef.current) setLoading(false);
    }
  }, [amoCode, loadPersonnel]);

  useEffect(() => {
    const controller = new AbortController();
    void load(controller.signal);
    return () => controller.abort();
  }, [load]);

  const selected = privileges.find((item) => item.id === selectedId) || null;
  const selectedRule = selected ? rules.find((rule) => rule.id === selected.rule_id) || null : null;
  const catalogRule = selectedRule || rules.find((rule) => rule.id === selectedRuleId) || null;
  const selectedIsAuditorPrivilege = selectedRule?.privilege_type === "AUDITOR" || selectedRule?.privilege_type === "LEAD_AUDITOR";
  const selectedIsObserverTrainee = Boolean(selectedRule && isObserverTraineeRule(selectedRule));
  const selectedIsFullAuditor = Boolean(selectedRule && isFullAuditorRule(selectedRule));
  const canManagePrivileges = hasQmsRolePermission("qms.training.manage");
  const canManageAuditGovernance = hasQmsRolePermission("qms.audit.manage");
  const canRunAuditPreflight = selectedIsAuditorPrivilege && canManageAuditGovernance;
  const assignmentContextRequired = Boolean(selectedRule?.independence_required);
  const assignmentInputComplete = Boolean(
    selected
    && selectedRule
    && assignmentDate
    && assignmentScopeKey.trim()
    && (!assignmentContextRequired || (assignmentContextType && assignmentContextId.trim())),
  );
  const allowedDecisions = selected ? allowedPrivilegeDecisions(selected.status) : [];
  const defaultAuditorRule = useMemo(() => findDefaultAuditorRule(rules), [rules]);
  const defaultObserverTraineeRule = useMemo(() => findDefaultObserverTraineeRule(rules), [rules]);

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
    if (!selected) {
      setSelectedSnapshot(null);
      setIndependenceRows([]);
      return;
    }
    const controller = new AbortController();
    setSnapshotLoading(true);
    setSelectedSnapshot(null);
    void Promise.all([
      getQmsEligibility(amoCode, { userId: selected.user_id, privilegeCode: selected.privilege_code }, controller.signal),
      listQmsIndependenceDeclarations(amoCode, { userId: selected.user_id }, controller.signal),
    ])
      .then(([snapshot, independence]) => {
        if (!controller.signal.aborted) {
          setSelectedSnapshot(bindEligibilityToPrivilege(snapshot, selected));
          setIndependenceRows(independence.items);
        }
      })
      .catch((nextError) => {
        if (!(nextError instanceof DOMException && nextError.name === "AbortError")) {
          setSelectedSnapshot(null);
          setIndependenceRows([]);
        }
      })
      .finally(() => {
        if (!controller.signal.aborted) setSnapshotLoading(false);
      });
    return () => controller.abort();
  }, [amoCode, selected, snapshotRevision]);

  const visiblePrivileges = useMemo(() => {
    const needle = search.trim().toLowerCase();
    return privileges.filter((item) => {
      if (statusFilter !== "ALL" && item.status !== statusFilter) return false;
      if (!needle) return true;
      const personLabel = personLabelById.get(item.user_id) || "";
      return [item.user_id, personLabel, item.privilege_code, item.scope_key].some((value) => value.toLowerCase().includes(needle));
    });
  }, [privileges, search, statusFilter, personLabelById]);

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

  function personLabel(userIdValue: string): string {
    return personLabelById.get(userIdValue) || shortIdentifier(userIdValue);
  }

  function resetRuleForm(rule?: QmsPrivilegeRule | null) {
    const supervised = Boolean((rule?.scope_schema as { supervised_development?: boolean } | undefined)?.supervised_development);
    setRuleCode(rule?.privilege_code || "");
    setRuleTitle(rule?.title || "");
    setRuleType(rule?.privilege_type || "LEAD_AUDITOR");
    setRuleDescription(rule?.description || "");
    setRuleTraining(trainingCodesLabel(rule?.required_training_course_codes || []));
    setRuleIndependenceRequired(rule?.independence_required ?? true);
    setRuleMaxConcurrent(rule?.max_concurrent_assignments ? String(rule.max_concurrent_assignments) : "");
    setRuleSupervisedDevelopment(supervised);
    setRuleActive(rule?.is_active ?? true);
  }

  function seedRuleForm(type: QmsPrivilegeRule["privilege_type"]) {
    resetRuleForm(null);
    setRuleType(type);
    if (type === "LEAD_AUDITOR") {
      setRuleCode("LEAD_AUDITOR_GLOBAL");
      setRuleTitle("Lead auditor");
      setRuleTraining("");
      setRuleIndependenceRequired(true);
      setRuleSupervisedDevelopment(false);
    } else if (type === "AUDITOR") {
      setRuleCode("AUDITOR_GLOBAL");
      setRuleTitle("Auditor");
      setRuleTraining("");
      setRuleIndependenceRequired(true);
      setRuleSupervisedDevelopment(false);
    }
  }

  function openAction(mode: ActionMode, options: { ruleType?: QmsPrivilegeRule["privilege_type"]; ruleId?: string } = {}) {
    if ((mode === "CREATE" || mode === "DECISION" || mode === "CREATE_RULE" || mode === "EDIT_RULE") && !canManagePrivileges) return;
    if ((mode === "AUDIT_ASSIGNMENT" || mode === "INDEPENDENCE") && !canManageAuditGovernance) return;
    setError("");
    setNotice("");
    if (mode === "AUDIT_ASSIGNMENT") invalidateAssignmentResult();
    if (selected && mode === "INDEPENDENCE") setIndUserId(selected.user_id);
    if (mode === "DECISION" && selected) setDecisionType(defaultPrivilegeDecision(selected.status));
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
      if (!personnel.length) void loadPersonnel(undefined, { bypassCache: true });
    }
    if (mode === "CREATE_RULE") {
      if (options.ruleType) seedRuleForm(options.ruleType);
      else resetRuleForm(null);
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
    setNotice("");
    const failures: string[] = [];
    let lastCreatedId = "";
    let createdCount = 0;
    let grantedCount = 0;
    for (const personId of userIds) {
      try {
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
    await load();
    if (lastCreatedId) setSelectedId(lastCreatedId);
    setPageTab("privileges");
    setUserIds([]);
    setScopeKey("GLOBAL");
    if (failures.length && !createdCount) {
      setError(failures.join(" · "));
    } else {
      setActionMode("NONE");
      const summaryParts = [
        createdCount ? `${createdCount} draft${createdCount === 1 ? "" : "s"} created` : null,
        grantOnCreate ? `${grantedCount} granted` : null,
      ].filter(Boolean);
      setNotice(summaryParts.join(" · ") || "Batch privilege update complete.");
      if (failures.length) setError(`Some people failed: ${failures.join(" · ")}`);
    }
    setCreating(false);
  }

  async function submitRule(event: FormEvent) {
    event.preventDefault();
    if (!canManagePrivileges) return;
    setSavingRule(true);
    setError("");
    const scopeSchema = ruleType === "AUDITOR" && ruleSupervisedDevelopment
      ? { supervised_development: true, allowed_assignment_roles: ["OBSERVER_AUDITOR", "ASSISTANT_AUDITOR"] }
      : {};
    const payload = {
      title: ruleTitle.trim(),
      description: ruleDescription.trim() || null,
      required_training_course_codes: parseTrainingCodes(ruleTraining),
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
          required_training_course_codes: parseTrainingCodes(ruleTraining),
          independence_required: ruleIndependenceRequired,
          max_concurrent_assignments: ruleMaxConcurrent.trim() ? Number(ruleMaxConcurrent) : null,
          scope_schema: scopeSchema,
        });
      } else if (actionMode === "EDIT_RULE" && selectedRuleId) {
        await updateQmsPrivilegeRule(amoCode, selectedRuleId, payload);
      }
      await load();
      setPageTab("rules");
      setActionMode("NONE");
    } catch (nextError) {
      setError(messageFromError(nextError));
    } finally {
      setSavingRule(false);
    }
  }

  async function submitDecision(event: FormEvent) {
    event.preventDefault();
    if (!canManagePrivileges || !selected || decisionReason.trim().length < 8) return;
    setDeciding(true);
    setError("");
    try {
      await decideQmsPrivilege(amoCode, selected.id, { decision_type: decisionType, rationale: decisionReason.trim(), effective_from: effectiveFrom || undefined, expires_on: expiresOn || undefined });
      setDecisionReason("");
      setEffectiveFrom("");
      setExpiresOn("");
      await load();
      setActionMode("NONE");
      setNotice(`${privilegeDecisionLabel(decisionType)} recorded.`);
    } catch (nextError) {
      setError(messageFromError(nextError));
    } finally {
      setDeciding(false);
    }
  }

  async function ensureTargetPrivilegeActive(
    targetRule: QmsPrivilegeRule,
    userId: string,
    grantRationale: string,
  ): Promise<string> {
    const existing = matchingPrivilegeRecord(privileges, {
      userId,
      privilegeCode: targetRule.privilege_code,
      scopeKey: "GLOBAL",
    });
    if (!existing) {
      const created = await createQmsPrivilege(amoCode, {
        rule_id: targetRule.id,
        user_id: userId,
        scope_key: "GLOBAL",
      });
      await decideQmsPrivilege(amoCode, created.id, {
        decision_type: "GRANT",
        rationale: grantRationale,
      });
      return created.id;
    }
    if (existing.status === "ACTIVE") return existing.id;
    if (existing.status === "DRAFT") {
      await decideQmsPrivilege(amoCode, existing.id, {
        decision_type: "GRANT",
        rationale: grantRationale,
      });
      return existing.id;
    }
    if (existing.status === "SUSPENDED") {
      await decideQmsPrivilege(amoCode, existing.id, {
        decision_type: "REINSTATE",
        rationale: grantRationale,
      });
      return existing.id;
    }
    if (existing.status === "EXPIRED") {
      await decideQmsPrivilege(amoCode, existing.id, {
        decision_type: "RENEW",
        rationale: grantRationale,
      });
      return existing.id;
    }
    throw new Error(
      `Cannot activate ${targetRule.privilege_code} for this person: an existing GLOBAL privilege is revoked and records are append-only.`,
    );
  }

  async function runQuickDecision(
    decision: Extract<QmsPrivilegeDecision["decision_type"], "SUSPEND" | "REVOKE" | "REINSTATE">,
    rationale: string,
    successNotice: string,
  ) {
    if (!canManagePrivileges || !selected || lifecycleBusy) return;
    setLifecycleBusy(true);
    setError("");
    setNotice("");
    try {
      await decideQmsPrivilege(amoCode, selected.id, {
        decision_type: decision,
        rationale,
      });
      await load();
      setNotice(successNotice);
    } catch (nextError) {
      setError(messageFromError(nextError));
    } finally {
      setLifecycleBusy(false);
    }
  }

  async function promoteToAuditor() {
    if (!canManagePrivileges || !selected || !selectedIsObserverTrainee || selected.status !== "ACTIVE" || lifecycleBusy) return;
    if (!defaultAuditorRule) {
      setError("Auditor rule (AUDITOR_GLOBAL) is not active. Refresh defaults or create the auditor rule first.");
      return;
    }
    setLifecycleBusy(true);
    setError("");
    setNotice("");
    try {
      const targetId = await ensureTargetPrivilegeActive(
        defaultAuditorRule,
        selected.user_id,
        QUICK_RATIONALE.PROMOTE_GRANT,
      );
      await decideQmsPrivilege(amoCode, selected.id, {
        decision_type: "SUSPEND",
        rationale: QUICK_RATIONALE.PROMOTE_SUSPEND,
      });
      await load();
      setSelectedId(targetId);
      setNotice("Promoted to Auditor: AUDITOR_GLOBAL granted and Observer/Trainee suspended.");
    } catch (nextError) {
      setError(messageFromError(nextError));
      await load();
    } finally {
      setLifecycleBusy(false);
    }
  }

  async function demoteToObserverTrainee() {
    if (!canManagePrivileges || !selected || !selectedIsFullAuditor || selected.status !== "ACTIVE" || lifecycleBusy) return;
    if (!defaultObserverTraineeRule) {
      setError("Observer/Trainee rule (OBSERVER_TRAINEE_GLOBAL) is not active. Refresh defaults or create the supervised auditor rule first.");
      return;
    }
    setLifecycleBusy(true);
    setError("");
    setNotice("");
    try {
      const targetId = await ensureTargetPrivilegeActive(
        defaultObserverTraineeRule,
        selected.user_id,
        QUICK_RATIONALE.DEMOTE_GRANT,
      );
      await decideQmsPrivilege(amoCode, selected.id, {
        decision_type: "SUSPEND",
        rationale: QUICK_RATIONALE.DEMOTE_SUSPEND,
      });
      await load();
      setSelectedId(targetId);
      setNotice("Demoted to Observer/Trainee: OBSERVER_TRAINEE_GLOBAL granted and Auditor suspended.");
    } catch (nextError) {
      setError(messageFromError(nextError));
      await load();
    } finally {
      setLifecycleBusy(false);
    }
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

  async function submitIndependence(event: FormEvent) {
    event.preventDefault();
    if (!canManageAuditGovernance || !indUserId.trim() || !indContextId.trim() || indRationale.trim().length < 8) return;
    setDeclaring(true);
    setError("");
    try {
      await declareQmsIndependence(amoCode, {
        user_id: indUserId.trim(), context_type: indContextType, context_id: indContextId.trim(), declaration: indDeclaration,
        relationship_to_subject: indRelationship.trim() || undefined, rationale: indRationale.trim(),
      });
      setIndRationale("");
      setIndRelationship("");
      await load();
      setActionMode("NONE");
    } catch (nextError) {
      setError(messageFromError(nextError));
    } finally {
      setDeclaring(false);
    }
  }

  const selectedName = selectedSnapshot?.person.full_name || personLabel(selected?.user_id || "") || "No person selected";
  const readinessLabel = snapshotLoading ? "Checking authoritative gates…" : !selectedSnapshot ? "Readiness unavailable" : selectedSnapshot.eligible ? "Ready" : "Blocked";
  const activeRules = rules.filter((rule) => rule.is_active);
  const hasLeadRule = activeRules.some((rule) => rule.privilege_type === "LEAD_AUDITOR");
  const hasObserverTraineeRule = activeRules.some((rule) => isObserverTraineeRule(rule));
  const hasAuditorRule = activeRules.some((rule) => isFullAuditorRule(rule));
  const missingLeadRule = !hasLeadRule;
  const missingObserverTraineeRule = !hasObserverTraineeRule;
  const missingAuditorRule = !hasAuditorRule;
  const batchPersonnel = useMemo(() => {
    const needle = personQuery.trim().toLowerCase();
    if (!needle) return personnel;
    return personnel.filter((person) =>
      [person.full_name, person.role, person.id].some((value) => (value || "").toLowerCase().includes(needle)),
    );
  }, [personnel, personQuery]);

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

  return (
    <main className="qms-people" aria-label="People and Privileges">
      <header className="qms-people__hero">
        <div>
          <span>People & Privileges</span>
          <h1>Quality authorization board</h1>
          <p>Configure privilege rules, grant or suspend authorizations, and verify audit assignment eligibility. Privileges are append-only records — revoke or suspend instead of deleting. AMO admins with training governance permission control rules and decisions.</p>
        </div>
        <div className="qms-people__hero-actions">
          <button type="button" onClick={() => void load()} disabled={loading}><RefreshCw size={16} aria-hidden="true" /> Refresh</button>
          {canManagePrivileges ? <button type="button" onClick={() => { setPageTab("rules"); openAction("CREATE_RULE"); }}><Plus size={16} aria-hidden="true" /> New rule</button> : null}
          {canManagePrivileges ? (
            <button type="button" className="is-primary" onClick={() => { setPageTab("privileges"); openAction("CREATE"); }}>
              <Plus size={16} aria-hidden="true" /> Authorize people
            </button>
          ) : null}
        </div>
      </header>

      <nav className="qms-people__tabs" aria-label="People workspace views">
        <button type="button" className={pageTab === "privileges" ? "is-active" : ""} onClick={() => setPageTab("privileges")}>Authorizations</button>
        <button type="button" className={pageTab === "rules" ? "is-active" : ""} onClick={() => setPageTab("rules")}>Privilege rules</button>
        <button type="button" className={pageTab === "reference" ? "is-active" : ""} onClick={() => setPageTab("reference")}><BookOpen size={15} aria-hidden="true" /> Role reference</button>
      </nav>

      {error ? <div className="qms-people__error" role="alert"><AlertTriangle size={18} aria-hidden="true" /> {error}</div> : null}
      {notice ? <div className="qms-people__notice" role="status"><CheckCircle2 size={18} aria-hidden="true" /> {notice}</div> : null}

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
                Authorize people
              </button>
            ) : null}
          </div>
        </section>
      ) : null}

      <section className="qms-people__metrics" aria-label="Privilege exposure summary">
        <article><strong>{summary.active_privileges}</strong><span>Active privileges</span><small>Current internal Quality authorizations</small></article>
        <article><strong>{summary.expiring_within_60_days}</strong><span>Expiring within 60 days</span><small>Review before authorization lapses</small></article>
        <article><strong>{summary.suspended_privileges}</strong><span>Suspended</span><small>Blocked for governed assignments</small></article>
        <article className={summary.independence_exceptions ? "is-attention" : ""}><strong>{summary.independence_exceptions}</strong><span>Independence exceptions</span><small>Conflict or review states requiring attention</small></article>
      </section>

      {pageTab === "reference" ? (
        <section className="qms-people__panel qms-people__reference">
          <div className="qms-people__panel-head"><div><span>Role contract</span><h2>Privilege types and audit assignment scope</h2></div></div>
          <div className="qms-people__reference-grid">
            {QMS_PRIVILEGE_ROLE_CATALOG.map((entry) => (
              <article key={entry.type}>
                <header><strong>{entry.label}</strong><span>{entry.type}</span></header>
                <p>{entry.summary}</p>
                <dl>
                  <div><dt>Audit assignment</dt><dd>{entry.auditAssignmentRoles.join(" · ")}</dd></div>
                  <div><dt>Typical scope</dt><dd>{entry.typicalScope}</dd></div>
                </dl>
              </article>
            ))}
          </div>
        </section>
      ) : null}

      {pageTab === "rules" ? (
        <section className="qms-people__workspace qms-people__workspace--rules">
          <section className="qms-people__panel qms-people__register">
            <div className="qms-people__panel-head">
              <div><span>Rule catalog</span><h2>Configured privilege rules</h2></div>
              <div className="qms-people__filters">
                <label className="qms-people__search"><Search size={15} aria-hidden="true" /><input value={search} onChange={(event) => setSearch(event.target.value)} placeholder="Search rule title or code" /></label>
                <label className="qms-people__checkbox"><input type="checkbox" checked={showInactiveRules} onChange={(event) => setShowInactiveRules(event.target.checked)} /> Show inactive</label>
              </div>
            </div>
            <div className="qms-people__table-wrap">
              <table>
                <thead><tr><th>Rule</th><th>Type</th><th>Training</th><th>Capacity</th><th>Status</th></tr></thead>
                <tbody>
                  {visibleRules.length ? visibleRules.map((rule) => (
                    <tr key={rule.id} className={rule.id === selectedRuleId ? "is-selected" : ""} onClick={() => setSelectedRuleId(rule.id)}>
                      <td><strong>{rule.title}</strong><small>{rule.privilege_code}</small></td>
                      <td>{humanisePrivilegeType(rule.privilege_type)}</td>
                      <td>{rule.required_training_course_codes.length ? rule.required_training_course_codes.join(", ") : "None"}</td>
                      <td>{rule.max_concurrent_assignments ?? "Unlimited"}</td>
                      <td><span className={`qms-people__status ${rule.is_active ? "qms-people__status--active" : "qms-people__status--suspended"}`}>{rule.is_active ? "Active" : "Inactive"}</span></td>
                    </tr>
                  )) : <tr><td colSpan={5}>{loading ? "Loading privilege rules…" : "No privilege rules configured yet."}</td></tr>}
                </tbody>
              </table>
            </div>
          </section>

          <aside className="qms-people__detail" aria-label="Selected privilege rule">
            {catalogRule ? (
              <>
                <div className="qms-people__detail-head">
                  <span>Selected rule</span>
                  <h2>{catalogRule.title}</h2>
                  <p>{catalogRule.privilege_code} · {humanisePrivilegeType(catalogRule.privilege_type)}</p>
                  <div className="qms-people__detail-badges">
                    <span className={`qms-people__status ${catalogRule.is_active ? "qms-people__status--active" : "qms-people__status--suspended"}`}>{catalogRule.is_active ? "Active" : "Inactive"}</span>
                  </div>
                </div>
                <dl className="qms-people__facts">
                  <div><dt>Description</dt><dd>{catalogRule.description || "No description recorded."}</dd></div>
                  <div><dt>Required training</dt><dd>{trainingCodesLabel(catalogRule.required_training_course_codes)}</dd></div>
                  <div><dt>Independence required</dt><dd>{catalogRule.independence_required ? "Yes — audit-specific declaration needed" : "No — assignment context optional"}</dd></div>
                  <div><dt>Max concurrent assignments</dt><dd>{catalogRule.max_concurrent_assignments ?? "Unlimited"}</dd></div>
                  <div><dt>Supervised development</dt><dd>{(catalogRule.scope_schema as { supervised_development?: boolean })?.supervised_development ? "Enabled for observer/assistant roles" : "Not enabled"}</dd></div>
                </dl>
                {catalogEntryForType(catalogRule.privilege_type) ? (
                  <section className="qms-people__rule-contract">
                    <header><span>Assignment contract</span><h3>{catalogEntryForType(catalogRule.privilege_type)?.label}</h3></header>
                    <p>{catalogEntryForType(catalogRule.privilege_type)?.summary}</p>
                    <p><strong>Audit roles:</strong> {catalogEntryForType(catalogRule.privilege_type)?.auditAssignmentRoles.join(" · ")}</p>
                  </section>
                ) : null}
                {canManagePrivileges ? (
                  <div className="qms-people__detail-actions">
                    <button type="button" className="is-primary" onClick={() => openAction("EDIT_RULE")}>Edit rule</button>
                    {catalogRule.is_active ? <button type="button" onClick={() => void updateQmsPrivilegeRule(amoCode, catalogRule.id, { is_active: false }).then(() => load()).catch((nextError) => setError(messageFromError(nextError)))}>Deactivate rule</button> : <button type="button" onClick={() => void updateQmsPrivilegeRule(amoCode, catalogRule.id, { is_active: true }).then(() => load()).catch((nextError) => setError(messageFromError(nextError)))}>Reactivate rule</button>}
                  </div>
                ) : null}
              </>
            ) : (
              <div className="qms-people__placeholder"><ShieldCheck size={30} /><strong>Select a privilege rule</strong><p>Create or select a rule before granting privileges to personnel.</p></div>
            )}
          </aside>
        </section>
      ) : null}

      {pageTab === "privileges" ? (
        <section className="qms-people__workspace">
          <section className="qms-people__panel qms-people__register">
            <div className="qms-people__panel-head">
              <div><span>Authorization register</span><h2>People and current privileges</h2></div>
              <div className="qms-people__filters">
                <label className="qms-people__search"><Search size={15} aria-hidden="true" /><input value={search} onChange={(event) => setSearch(event.target.value)} placeholder="Search person, privilege or scope" /></label>
                <label>Status<select value={statusFilter} onChange={(event) => setStatusFilter(event.target.value as typeof statusFilter)}><option value="ALL">All</option><option value="DRAFT">Draft</option><option value="ACTIVE">Active</option><option value="SUSPENDED">Suspended</option><option value="REVOKED">Revoked</option><option value="EXPIRED">Expired</option></select></label>
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
                <thead><tr><th>Person</th><th>Privilege</th><th>Scope</th><th>Status</th><th>Expiry</th></tr></thead>
                <tbody>
                  {visiblePrivileges.length ? visiblePrivileges.map((item) => (
                    <tr key={item.id} className={item.id === selectedId ? "is-selected" : ""} onClick={() => setSelectedId(item.id)}>
                      <td><button type="button" className="qms-people__row-button" onClick={() => setSelectedId(item.id)}><strong>{personLabel(item.user_id)}</strong><small>{shortIdentifier(item.user_id)}</small></button></td>
                      <td><strong>{humanise(item.privilege_code)}</strong><small>{item.decisions?.length || 0} recorded decision(s)</small></td>
                      <td>{humanise(item.scope_key)}</td>
                      <td><span className={`qms-people__status qms-people__status--${item.status.toLowerCase()}`}>{humanise(item.status)}</span></td>
                      <td>{dateLabel(item.expires_on)}</td>
                    </tr>
                  )) : <tr><td colSpan={5}>{loading ? "Loading governed privileges…" : "No privileges match this view."}</td></tr>}
                </tbody>
              </table>
            </div>
          </section>

          <aside className="qms-people__detail" aria-label="Selected person and privilege">
            {selected ? (
              <>
                <div className="qms-people__detail-head">
                  <span>Selected authorization</span>
                  <h2>{selectedName}</h2>
                  <p>{selectedSnapshot?.person.email || selected.user_id}</p>
                  <div className="qms-people__detail-badges">
                    <span className={`qms-people__status qms-people__status--${selected.status.toLowerCase()}`}>{humanise(selected.status)}</span>
                    <span>{humanise(selected.privilege_code)}</span>
                    {selectedRule ? <span>{humanisePrivilegeType(selectedRule.privilege_type)}</span> : null}
                  </div>
                </div>
                <dl className="qms-people__facts">
                  <div><dt>Scope</dt><dd>{humanise(selected.scope_key)}</dd></div>
                  <div><dt>Effective</dt><dd>{dateLabel(selected.effective_from)}</dd></div>
                  <div><dt>Expiry</dt><dd>{dateLabel(selected.expires_on)}</dd></div>
                  <div><dt>Decision history</dt><dd>{selected.decisions?.length || 0} event(s)</dd></div>
                  {selectedRule ? <div><dt>Rule contract</dt><dd>{selectedRule.title} · independence {selectedRule.independence_required ? "required" : "optional"}</dd></div> : null}
                </dl>
                <section className="qms-people__eligibility-summary">
                  <header><div><span>Current authorization readiness</span><h3>{readinessLabel}</h3></div>{selectedSnapshot?.eligible ? <CheckCircle2 size={20} /> : <ShieldCheck size={20} />}</header>
                  {selectedSnapshot ? (
                    <>
                      <div className="qms-people__gate-grid">{Object.entries(selectedSnapshot.hard_gates).map(([gate, passed]) => <span key={gate} className={passed ? "is-pass" : "is-block"}><strong>{passed ? "Pass" : "Block"}</strong>{humanise(gate)}</span>)}</div>
                      {selectedSnapshot.training.missing.length ? <p>Missing verified/current training: {selectedSnapshot.training.missing.join(", ")}</p> : <p>Required training evidence is satisfied for this selected authorization.</p>}
                      {selectedIsAuditorPrivilege ? <p>Audit assignment scope, role, date, capacity and independence are verified separately by the governed Planner assignment preflight.</p> : null}
                    </>
                  ) : <p>Authoritative readiness evidence is unavailable for this selected authorization.</p>}
                </section>
                {canManagePrivileges && (selected.status === "ACTIVE" || selected.status === "SUSPENDED") ? (
                  <div className="qms-people__lifecycle-actions" aria-label="Privilege lifecycle actions">
                    {selected.status === "ACTIVE" ? (
                      <>
                        <button
                          type="button"
                          disabled={lifecycleBusy}
                          onClick={() => void runQuickDecision("SUSPEND", QUICK_RATIONALE.SUSPEND, "Privilege suspended.")}
                        >
                          Suspend
                        </button>
                        <button
                          type="button"
                          className="is-danger"
                          disabled={lifecycleBusy}
                          onClick={() => void runQuickDecision("REVOKE", QUICK_RATIONALE.REVOKE, "Privilege revoked.")}
                        >
                          Revoke
                        </button>
                        {selectedIsObserverTrainee ? (
                          <button
                            type="button"
                            className="is-primary"
                            disabled={lifecycleBusy || !defaultAuditorRule}
                            title={!defaultAuditorRule ? "Active AUDITOR_GLOBAL rule required" : "Grant Auditor and suspend this Observer/Trainee privilege"}
                            onClick={() => void promoteToAuditor()}
                          >
                            Promote to Auditor
                          </button>
                        ) : null}
                        {selectedIsFullAuditor ? (
                          <button
                            type="button"
                            disabled={lifecycleBusy || !defaultObserverTraineeRule}
                            title={!defaultObserverTraineeRule ? "Active OBSERVER_TRAINEE_GLOBAL rule required" : "Grant Observer/Trainee and suspend this Auditor privilege"}
                            onClick={() => void demoteToObserverTrainee()}
                          >
                            Demote to Observer/Trainee
                          </button>
                        ) : null}
                      </>
                    ) : null}
                    {selected.status === "SUSPENDED" ? (
                      <>
                        <button
                          type="button"
                          className="is-primary"
                          disabled={lifecycleBusy}
                          onClick={() => void runQuickDecision("REINSTATE", QUICK_RATIONALE.REINSTATE, "Privilege reinstated.")}
                        >
                          Reinstate
                        </button>
                        <button
                          type="button"
                          className="is-danger"
                          disabled={lifecycleBusy}
                          onClick={() => void runQuickDecision("REVOKE", QUICK_RATIONALE.REVOKE, "Privilege revoked.")}
                        >
                          Revoke
                        </button>
                      </>
                    ) : null}
                  </div>
                ) : null}
                <div className="qms-people__detail-actions">
                  {canRunAuditPreflight ? <button type="button" className="is-primary" onClick={() => openAction("AUDIT_ASSIGNMENT")}><CheckCircle2 size={16} /> Check audit assignment</button> : null}
                  {canManagePrivileges && allowedDecisions.length ? <button type="button" onClick={() => openAction("DECISION")}><ShieldCheck size={16} /> Change privilege</button> : null}
                  {canManageAuditGovernance ? <button type="button" onClick={() => openAction("INDEPENDENCE")}><UserRoundCheck size={16} /> Independence</button> : null}
                </div>
                <section className="qms-people__history">
                  <header><span>Decision history</span><h3>Immutable authorization record</h3></header>
                  {selected.decisions?.length ? selected.decisions.slice().reverse().map((decision) => (
                    <article key={decision.id}><div><strong>{humanise(decision.decision_type)}</strong><span>{humanise(decision.resulting_status)}</span></div><p>{decision.rationale}</p><small>{new Date(decision.decided_at).toLocaleString()}</small></article>
                  )) : <p className="qms-people__empty">No authorization decision has been recorded yet.</p>}
                </section>
                <section className="qms-people__history">
                  <header><span>Independence declarations</span><h3>Recorded for this person</h3></header>
                  {independenceRows.length ? independenceRows.map((row) => (
                    <article key={row.id}><div><strong>{humanise(row.declaration)}</strong><span>{humanise(row.context_type)}</span></div><p>{row.rationale}</p><small>{row.context_id} · {new Date(row.declared_at).toLocaleString()}</small></article>
                  )) : <p className="qms-people__empty">No independence declarations recorded for this person.</p>}
                </section>
              </>
            ) : (
              <div className="qms-people__placeholder"><UserRoundCheck size={30} /><strong>Select a person or privilege</strong><p>The selected authorization, readiness posture and governed actions will appear here.</p></div>
            )}
          </aside>
        </section>
      ) : null}

      {actionMode !== "NONE" ? (
        <div className="qms-people__drawer-layer" role="dialog" aria-modal="true" aria-label="People and privileges governed action">
          <section className="qms-people__drawer">
            <header>
              <div>
                <span>Governed action</span>
                <h2>
                  {actionMode === "CREATE" ? "Authorize people"
                    : actionMode === "DECISION" ? "Record privilege decision"
                    : actionMode === "AUDIT_ASSIGNMENT" ? "Check governed audit assignment"
                    : actionMode === "CREATE_RULE" ? "Create privilege rule"
                    : actionMode === "EDIT_RULE" ? "Edit privilege rule"
                    : "Declare independence state"}
                </h2>
              </div>
              <button type="button" className="qms-people__icon-button" onClick={closeAction} aria-label="Close action"><X size={18} /></button>
            </header>

            {actionMode === "CREATE" && canManagePrivileges ? (
              <form onSubmit={submitDraft} className="qms-people__form">
                <section className="qms-people__form-section" aria-labelledby="people-authorize-rule">
                  <header>
                    <h3 id="people-authorize-rule">Rule</h3>
                  </header>
                  <div className="qms-people__form-row">
                    <label>
                      Privilege rule
                      <select value={ruleId} onChange={(event) => setRuleId(event.target.value)} required>
                        <option value="">Select rule</option>
                        {activeRules.map((rule) => (
                          <option key={rule.id} value={rule.id}>
                            {rule.title} · {humanisePrivilegeType(rule.privilege_type)}
                          </option>
                        ))}
                      </select>
                    </label>
                    <label>
                      Scope
                      <input value={scopeKey} onChange={(event) => setScopeKey(event.target.value)} placeholder="GLOBAL" />
                    </label>
                  </div>
                </section>

                <section className="qms-people__form-section" aria-labelledby="people-authorize-people">
                  <header>
                    <h3 id="people-authorize-people">People</h3>
                    <span>{userIds.length} selected</span>
                  </header>
                  <div className="qms-people__batch-people">
                    <div className="qms-people__batch-people-toolbar">
                      <label className="qms-people__search">
                        <Search size={15} aria-hidden="true" />
                        <input value={personQuery} onChange={(event) => setPersonQuery(event.target.value)} placeholder="Filter people" />
                      </label>
                      <button
                        type="button"
                        onClick={() => setUserIds(batchPersonnel.map((person) => person.id))}
                        disabled={!batchPersonnel.length}
                      >
                        Select visible
                      </button>
                      <button type="button" onClick={() => setUserIds([])} disabled={!userIds.length}>
                        Clear
                      </button>
                    </div>
                    <div className="qms-people__person-checklist" role="group" aria-label="People to authorize">
                      {batchPersonnel.length ? (
                        batchPersonnel.map((person) => {
                          const checked = userIds.includes(person.id);
                          return (
                            <label key={person.id} className={`qms-people__person-option${checked ? " is-selected" : ""}`}>
                              <input type="checkbox" checked={checked} onChange={() => toggleBatchPerson(person.id)} />
                              <span className="qms-people__person-name">{person.full_name}</span>
                              <span className="qms-people__person-role">{person.role || ""}</span>
                            </label>
                          );
                        })
                      ) : (
                        <div className="qms-people__empty-inline-block">
                          <p className="qms-people__empty-inline">
                            {personnelLoading
                              ? "Loading personnel options…"
                              : personnel.length
                                ? "No people match this filter."
                                : "No personnel options loaded."}
                          </p>
                          {!personnel.length && !personnelLoading ? (
                            <button
                              type="button"
                              className="qms-people__text-button"
                              onClick={() => void loadPersonnel(undefined, { bypassCache: true })}
                            >
                              Retry personnel load
                            </button>
                          ) : null}
                        </div>
                      )}
                    </div>
                  </div>
                </section>

                <section className="qms-people__form-section is-secondary" aria-labelledby="people-authorize-grant">
                  <header>
                    <h3 id="people-authorize-grant">Grant</h3>
                  </header>
                  <label className="qms-people__checkbox">
                    <input type="checkbox" checked={grantOnCreate} onChange={(event) => setGrantOnCreate(event.target.checked)} />
                    Grant immediately
                  </label>
                  {grantOnCreate ? (
                    <label>
                      Rationale
                      <textarea
                        value={batchRationale}
                        onChange={(event) => setBatchRationale(event.target.value)}
                        minLength={8}
                        rows={2}
                        required
                      />
                    </label>
                  ) : null}
                </section>

                <footer>
                  <button type="button" onClick={closeAction}>Cancel</button>
                  <button
                    type="submit"
                    className="is-primary"
                    disabled={creating || !ruleId || !userIds.length || (grantOnCreate && batchRationale.trim().length < 8)}
                  >
                    {creating
                      ? "Working…"
                      : grantOnCreate
                        ? `Authorize ${userIds.length || ""} people`
                        : `Create ${userIds.length || ""} draft${userIds.length === 1 ? "" : "s"}`}
                  </button>
                </footer>
              </form>
            ) : null}

            {(actionMode === "CREATE_RULE" || actionMode === "EDIT_RULE") && canManagePrivileges ? (
              <form onSubmit={submitRule} className="qms-people__form">
                {actionMode === "CREATE_RULE" ? (
                  <>
                    <label>Privilege code<span>Uppercase code used in eligibility and assignment checks.</span><input value={ruleCode} onChange={(event) => setRuleCode(event.target.value.toUpperCase())} required pattern="[A-Z0-9_\-]+" placeholder="LEAD_AUDITOR_GLOBAL" /></label>
                    <label>Privilege type<select value={ruleType} onChange={(event) => setRuleType(event.target.value as QmsPrivilegeRule["privilege_type"])}>{PRIVILEGE_TYPES.map((type) => <option key={type} value={type}>{humanisePrivilegeType(type)}</option>)}</select></label>
                  </>
                ) : null}
                <label>Title<input value={ruleTitle} onChange={(event) => setRuleTitle(event.target.value)} required minLength={3} /></label>
                <label>Description<textarea value={ruleDescription} onChange={(event) => setRuleDescription(event.target.value)} rows={3} /></label>
                <label>Required training course codes<span>Comma-separated course codes verified in Training before grant.</span><input value={ruleTraining} onChange={(event) => setRuleTraining(event.target.value)} placeholder="AUDITOR, LEAD_AUDITOR" /></label>
                <label className="qms-people__checkbox"><input type="checkbox" checked={ruleIndependenceRequired} onChange={(event) => setRuleIndependenceRequired(event.target.checked)} /> Independence declaration required before audit assignment</label>
                {ruleType === "AUDITOR" ? <label className="qms-people__checkbox"><input type="checkbox" checked={ruleSupervisedDevelopment} onChange={(event) => setRuleSupervisedDevelopment(event.target.checked)} /> Supervised development rule (observer/assistant only)</label> : null}
                <label>Max concurrent assignments<input type="number" min={1} max={100} value={ruleMaxConcurrent} onChange={(event) => setRuleMaxConcurrent(event.target.value)} placeholder="Unlimited" /></label>
                {actionMode === "EDIT_RULE" ? <label className="qms-people__checkbox"><input type="checkbox" checked={ruleActive} onChange={(event) => setRuleActive(event.target.checked)} /> Rule active (uncheck to deactivate and block new grants)</label> : null}
                <footer><button type="button" onClick={closeAction}>Cancel</button><button type="submit" className="is-primary" disabled={savingRule || !ruleTitle.trim() || (actionMode === "CREATE_RULE" && !ruleCode.trim())}>{savingRule ? "Saving…" : actionMode === "CREATE_RULE" ? "Create rule" : "Save rule changes"}</button></footer>
              </form>
            ) : null}

            {actionMode === "DECISION" && selected && canManagePrivileges ? (
              <form onSubmit={submitDecision} className="qms-people__form">
                <div className="qms-people__context-card"><strong>{selectedName}</strong><span>{humanise(selected.privilege_code)} · {humanise(selected.scope_key)}</span></div>
                <label>Decision<select value={decisionType} onChange={(event) => setDecisionType(event.target.value as QmsPrivilegeDecision["decision_type"])}>{allowedDecisions.map((decision) => <option key={decision} value={decision}>{privilegeDecisionLabel(decision)}</option>)}</select></label>
                <div className="qms-people__dates"><label>Effective<input type="date" value={effectiveFrom} onChange={(event) => setEffectiveFrom(event.target.value)} /></label><label>Expiry<input type="date" value={expiresOn} onChange={(event) => setExpiresOn(event.target.value)} /></label></div>
                <label>Decision rationale<textarea value={decisionReason} onChange={(event) => setDecisionReason(event.target.value)} minLength={8} rows={5} required placeholder="Record the evidence-backed reason for this decision." /></label>
                <footer><button type="button" onClick={closeAction}>Cancel</button><button type="submit" className="is-primary" disabled={deciding || decisionReason.trim().length < 8}>{deciding ? "Recording…" : "Record immutable decision"}</button></footer>
              </form>
            ) : null}

            {actionMode === "AUDIT_ASSIGNMENT" && selected && selectedRule && canRunAuditPreflight ? (
              <form onSubmit={submitAuditAssignment} className="qms-people__form">
                <div className="qms-people__context-card"><strong>{selectedName}</strong><span>{humanise(selected.privilege_code)} · selected authorization {humanise(selected.scope_key)}</span></div>
                <label>Assignment role<select value={assignmentRole} disabled={checkingAssignment} onChange={(event) => { invalidateAssignmentResult(); setAssignmentRole(event.target.value as QmsAuditorAssignmentRole); }}>{selectedRule.privilege_type === "LEAD_AUDITOR" ? <option value="LEAD_AUDITOR">Lead auditor</option> : <><option value="OBSERVER_AUDITOR">Observer auditor</option><option value="ASSISTANT_AUDITOR">Assistant auditor</option></>}</select></label>
                <label>Assignment date<input type="date" value={assignmentDate} disabled={checkingAssignment} onChange={(event) => { invalidateAssignmentResult(); setAssignmentDate(event.target.value); }} required /></label>
                <label>Assignment scope code<span>Enter the actual audit/programme scope being assigned; this is checked against the selected privilege scope.</span><input value={assignmentScopeKey} disabled={checkingAssignment} onChange={(event) => { invalidateAssignmentResult(); setAssignmentScopeKey(event.target.value); }} required placeholder="e.g. LINE_MAINTENANCE" /></label>
                <label>Assignment context<select value={assignmentContextType} disabled={checkingAssignment} onChange={(event) => { invalidateAssignmentResult(); setAssignmentContextType(event.target.value as AssignmentContextType); }} required={assignmentContextRequired}><option value="">{assignmentContextRequired ? "Select governed context" : "No context required"}</option><option value="AUDIT">Audit</option><option value="AUDIT_SCHEDULE">Audit schedule</option><option value="PROGRAMME_ITEM">Programme item</option><option value="MISSION">Mission</option><option value="ASSURANCE_CASE">Assurance case</option><option value="OTHER">Other</option></select></label>
                <label>Context ID<span>{assignmentContextRequired ? "Required so independence is verified against this assignment." : "Optional governed assignment record."}</span><input value={assignmentContextId} disabled={checkingAssignment} onChange={(event) => { invalidateAssignmentResult(); setAssignmentContextId(event.target.value); }} required={assignmentContextRequired} placeholder={assignmentContextRequired ? "Required governed record ID" : "Optional governed record ID"} /></label>
                {assignmentResultAppliesToSelection && assignmentResult && assignmentResultInput ? (
                  <div className={`qms-people__eligibility ${assignmentEligible ? "is-eligible" : "is-blocked"}`}>
                    <strong>{assignmentEligible ? "Eligible for this assignment" : "Blocked for this assignment"}</strong>
                    <span>{humanise(assignmentResultInput.assignment_role)} · {assignmentResultInput.assignment_date} · {humanise(assignmentResultInput.assignment_scope_key)}</span>
                    {assignmentResultInput.context_type ? <p>Checked context: {humanise(assignmentResultInput.context_type)} · {assignmentResultInput.context_id || "No context identifier"}</p> : null}
                    {assignmentAssessment ? <div className="qms-people__gate-grid">{Object.entries(assignmentAssessment.hard_gates).map(([gate, passed]) => <span key={gate} className={passed ? "is-pass" : "is-block"}><strong>{passed ? "Pass" : "Block"}</strong>{humanise(gate)}</span>)}</div> : null}
                    {!assignmentUsesSelectedPrivilege ? <p>The governed assignment guard did not use this selected authorization. Choose the authorization whose scope is actually being relied on.</p> : null}
                    {assignmentResult.reason ? <p>{assignmentResult.reason}</p> : null}
                    {assignmentAssessment?.independence.message ? <p>{assignmentAssessment.independence.message}</p> : null}
                  </div>
                ) : null}
                <footer><button type="button" onClick={closeAction}>Close</button><button type="submit" className="is-primary" disabled={checkingAssignment || !assignmentInputComplete}>{checkingAssignment ? "Checking…" : "Run governed assignment preflight"}</button></footer>
              </form>
            ) : null}

            {actionMode === "INDEPENDENCE" && canManageAuditGovernance ? (
              <form onSubmit={submitIndependence} className="qms-people__form">
                <label>Person<select value={indUserId} onChange={(event) => setIndUserId(event.target.value)} required><option value="">Select person</option>{personnel.map((person) => <option key={person.id} value={person.id}>{person.full_name}{person.role ? ` · ${person.role}` : ""}</option>)}</select></label>
                <label>Context<select value={indContextType} onChange={(event) => setIndContextType(event.target.value as typeof indContextType)}><option value="AUDIT_SCHEDULE">Audit schedule</option><option value="AUDIT">Audit</option><option value="PROGRAMME_ITEM">Programme item</option><option value="MISSION">Mission</option><option value="ASSURANCE_CASE">Assurance case</option><option value="OTHER">Other</option></select></label>
                <label>Context ID<input value={indContextId} onChange={(event) => setIndContextId(event.target.value)} required /></label>
                <label>Declaration<select value={indDeclaration} onChange={(event) => setIndDeclaration(event.target.value as typeof indDeclaration)}><option value="INDEPENDENT">Independent</option><option value="REQUIRES_REVIEW">Requires review</option><option value="CONFLICT">Conflict</option></select></label>
                <label>Relationship to subject<input value={indRelationship} onChange={(event) => setIndRelationship(event.target.value)} /></label>
                <label>Rationale<textarea value={indRationale} onChange={(event) => setIndRationale(event.target.value)} minLength={8} rows={5} required /></label>
                <footer><button type="button" onClick={closeAction}>Cancel</button><button type="submit" className="is-primary" disabled={declaring || !indUserId.trim() || !indContextId.trim() || indRationale.trim().length < 8}>{declaring ? "Recording…" : "Record immutable declaration"}</button></footer>
              </form>
            ) : null}
          </section>
        </div>
      ) : null}
    </main>
  );
};

export default QmsPeoplePage;
