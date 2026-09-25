import React, { FormEvent, useCallback, useEffect, useMemo, useState } from "react";
import {
  AlertTriangle,
  BadgeCheck,
  CalendarClock,
  CheckCircle2,
  ClipboardCheck,
  Download,
  FilePlus2,
  History,
  RefreshCw,
  Search,
  Settings2,
  ShieldCheck,
  UserCheck,
  Users,
  XCircle,
} from "lucide-react";
import { useSearchParams } from "react-router-dom";

import { getCachedUser } from "../../services/auth";
import {
  addQmsAuthorizationEvidenceReference,
  createQmsAuthorizationCase,
  createQmsAuthorizationCasesBatch,
  createQmsAuthorizationReview,
  createQmsAuthorizationControlledExemption,
  createQmsCaseControlledExemption,
  createQmsPrivilegeRule,
  decideQmsAuthorizationCase,
  decideQmsAuthorizationLifecycle,
  downloadQmsAuthorizationEvidence,
  downloadQmsAuthorizationRecord,
  ensureQmsDefaultPrivilegeRules,
  getQmsAuthorizationCase,
  getQmsAuthorizationOverview,
  getQmsAuthorizationPerson,
  listQmsAuthorizationCases,
  listQmsAuthorizationPeople,
  listQmsAuthorizationReviews,
  listQmsAuthorizations,
  listQmsPrivilegeRules,
  prepareQmsAuthorizationCase,
  revokeQmsControlledExemption,
  submitQmsAuthorizationCase,
  updateQmsPrivilegeRule,
  uploadQmsAuthorizationCaseEvidence,
  type QmsAuthorization,
  type QmsAuthorizationCaseDetail,
  type QmsAuthorizationCaseSummary,
  type QmsAuthorizationOverview,
  type QmsAuthorizationPerson,
  type QmsAuthorizationPersonDetail,
  type QmsAuthorizationReview,
  type QmsPrivilegeRule,
} from "../../services/qmsPeople";
import { downloadBlob } from "../../services/typedApi";
import "../../styles/qms/people.css";

type Props = { amoCode: string };
type Tab = "overview" | "people" | "cases" | "reviews" | "administration";

const CASE_STATUSES = [
  "NOMINATED",
  "UNDER_REVIEW",
  "DEVELOPMENT",
  "AWAITING_EVIDENCE",
  "READY_FOR_DECISION",
  "RETURNED",
  "APPROVED",
  "REJECTED",
  "CANCELLED",
] as const;

function todayKey(): string {
  return new Date().toISOString().slice(0, 10);
}

function inOneYear(): string {
  const d = new Date();
  d.setFullYear(d.getFullYear() + 1);
  return d.toISOString().slice(0, 10);
}

function human(value?: string | null): string {
  if (!value) return "Not recorded";
  return value.replaceAll("_", " ").toLowerCase().replace(/\b\w/g, (char) => char.toUpperCase());
}

function shortDate(value?: string | null): string {
  if (!value) return "Not set";
  const date = new Date(value.length === 10 ? `${value}T00:00:00` : value);
  return Number.isNaN(date.getTime()) ? value : date.toLocaleDateString();
}

function errorText(error: unknown): string {
  return error instanceof Error ? error.message : "The operation could not be completed.";
}

function statusTone(status: string): string {
  const value = status.toUpperCase();
  if (["ACTIVE", "APPROVED", "READY_FOR_DECISION", "CURRENT", "CONTINUE"].includes(value)) return "good";
  if (["SUSPENDED", "RETURNED", "AWAITING_EVIDENCE", "DEVELOPMENT", "DUE", "REQUIRES_ACTION"].includes(value)) return "warn";
  if (["REVOKED", "REJECTED", "EXPIRED", "BLOCKED"].includes(value)) return "bad";
  return "neutral";
}

function Pill({ children, tone = "neutral" }: { children: React.ReactNode; tone?: string }) {
  return <span className={`qms-authz-pill qms-authz-pill--${tone}`}>{children}</span>;
}

function SectionTitle({ icon, title, subtitle }: { icon: React.ReactNode; title: string; subtitle?: string }) {
  return (
    <div className="qms-authz-section-title">
      <span>{icon}</span>
      <div>
        <h2>{title}</h2>
        {subtitle ? <p>{subtitle}</p> : null}
      </div>
    </div>
  );
}

const QmsPeoplePage: React.FC<Props> = ({ amoCode }) => {
  const [searchParams, setSearchParams] = useSearchParams();
  const requestedTab = searchParams.get("tab") as Tab | null;
  const [tab, setTab] = useState<Tab>(
    requestedTab && ["overview", "people", "cases", "reviews", "administration"].includes(requestedTab)
      ? requestedTab
      : "overview",
  );
  const [revision, setRevision] = useState(0);
  const [overview, setOverview] = useState<QmsAuthorizationOverview | null>(null);
  const [people, setPeople] = useState<QmsAuthorizationPerson[]>([]);
  const [cases, setCases] = useState<QmsAuthorizationCaseSummary[]>([]);
  const [reviews, setReviews] = useState<QmsAuthorizationReview[]>([]);
  const [authorizations, setAuthorizations] = useState<QmsAuthorization[]>([]);
  const [rules, setRules] = useState<QmsPrivilegeRule[]>([]);
  const [selectedPersonKey, setSelectedPersonKey] = useState("");
  const [personDetail, setPersonDetail] = useState<QmsAuthorizationPersonDetail | null>(null);
  const [selectedCaseId, setSelectedCaseId] = useState("");
  const [caseDetail, setCaseDetail] = useState<QmsAuthorizationCaseDetail | null>(null);
  const [search, setSearch] = useState("");
  const [caseStatus, setCaseStatus] = useState("");
  const [busy, setBusy] = useState(false);
  const [pageLoading, setPageLoading] = useState(true);
  const [notice, setNotice] = useState<string | null>(null);
  const [error, setError] = useState<string | null>(null);

  const [nominateOpen, setNominateOpen] = useState(false);
  const [nominatePerson, setNominatePerson] = useState("");
  const [nominateRule, setNominateRule] = useState("");
  const [nominateReason, setNominateReason] = useState("Nominate for governed Quality authorization review.");

  const [batchOpen, setBatchOpen] = useState(false);
  const [batchPeople, setBatchPeople] = useState<string[]>([]);
  const [batchRule, setBatchRule] = useState("");
  const [batchReason, setBatchReason] = useState("Nominate selected personnel for governed Quality authorization review.");

  const [preparationStatus, setPreparationStatus] = useState<"UNDER_REVIEW" | "DEVELOPMENT" | "AWAITING_EVIDENCE" | "RETURNED">("UNDER_REVIEW");
  const [recommendation, setRecommendation] = useState("");
  const [preparationReason, setPreparationReason] = useState("Authorization case preparation updated.");
  const [decision, setDecision] = useState<"APPROVE" | "REJECT" | "RETURN">("APPROVE");
  const [decisionReason, setDecisionReason] = useState("");
  const [decisionEffective, setDecisionEffective] = useState(todayKey());
  const [decisionExpiry, setDecisionExpiry] = useState("");
  const [decisionReviewDue, setDecisionReviewDue] = useState("");
  const [developmentBasis, setDevelopmentBasis] = useState("");
  const [decisionEvidenceIds, setDecisionEvidenceIds] = useState<string[]>([]);

  const [evidenceLabel, setEvidenceLabel] = useState("");
  const [evidenceType, setEvidenceType] = useState("OTHER");
  const [evidenceSource, setEvidenceSource] = useState("");

  const [exemptionOpen, setExemptionOpen] = useState(false);
  const [exemptionAuthorization, setExemptionAuthorization] = useState<QmsAuthorization | null>(null);
  const [exemptionCriterion, setExemptionCriterion] = useState("training_current_verified");
  const [exemptionReason, setExemptionReason] = useState("");
  const [exemptionEquivalentEvidence, setExemptionEquivalentEvidence] = useState("");
  const [exemptionConditions, setExemptionConditions] = useState("");
  const [exemptionLimitations, setExemptionLimitations] = useState("");
  const [exemptionSupervisionRequired, setExemptionSupervisionRequired] = useState(false);
  const [exemptionSupervisor, setExemptionSupervisor] = useState("");
  const [exemptionEffective, setExemptionEffective] = useState(todayKey());
  const [exemptionExpiry, setExemptionExpiry] = useState(inOneYear());

  const [reviewOpen, setReviewOpen] = useState(false);
  const [reviewAuthorization, setReviewAuthorization] = useState("");
  const [reviewOutcome, setReviewOutcome] = useState<"CONTINUE" | "CONTINUE_WITH_CONDITIONS" | "SUSPEND" | "REVOKE" | "REQUIRES_ACTION">("CONTINUE");
  const [reviewReason, setReviewReason] = useState("");
  const [reviewNextDue, setReviewNextDue] = useState("");
  const [reviewEvidenceReferences, setReviewEvidenceReferences] = useState("");
  const [reviewNotes, setReviewNotes] = useState("");

  const [lifecycleOpen, setLifecycleOpen] = useState(false);
  const [lifecycleAuthorization, setLifecycleAuthorization] = useState<QmsAuthorization | null>(null);
  const [lifecycleDecision, setLifecycleDecision] = useState<"SUSPEND" | "REVOKE" | "REINSTATE" | "RENEW">("SUSPEND");
  const [lifecycleReason, setLifecycleReason] = useState("");
  const [lifecycleDate, setLifecycleDate] = useState(todayKey());
  const [lifecycleExpiry, setLifecycleExpiry] = useState("");
  const [lifecycleReviewDue, setLifecycleReviewDue] = useState("");
  const [lifecycleEvidenceReferences, setLifecycleEvidenceReferences] = useState("");

  const [ruleOpen, setRuleOpen] = useState(false);
  const [editingRule, setEditingRule] = useState<QmsPrivilegeRule | null>(null);
  const [ruleTitle, setRuleTitle] = useState("");
  const [ruleCode, setRuleCode] = useState("");
  const [ruleType, setRuleType] = useState<QmsPrivilegeRule["privilege_type"]>("AUDITOR");
  const [ruleDescription, setRuleDescription] = useState("");
  const [ruleTraining, setRuleTraining] = useState("");
  const [ruleIndependence, setRuleIndependence] = useState(true);
  const [ruleDevelopmental, setRuleDevelopmental] = useState(false);

  const permissions = overview?.permissions;
  const actorName = getCachedUser()?.full_name || "Current authorized user";
  const canPrepare = permissions?.can_prepare === true;
  const canApprove = permissions?.can_approve === true;
  const canReview = permissions?.can_review === true;
  const canExempt = permissions?.can_approve_exemption === true;
  const canManagePolicy = permissions?.can_manage_policy === true;
  const selfServiceOnly = permissions?.self_service_only === true;
  const currentUserId = getCachedUser()?.id || "";
  const activePersonKey = selfServiceOnly ? currentUserId : selectedPersonKey;
  const effectiveTab: Tab = selfServiceOnly ? "people" : tab;
  const visibleTabs: Array<[Tab, string]> = selfServiceOnly
    ? [["people", "My Authorization"]]
    : [
        ["overview", "Overview"],
        ["people", "People"],
        ["cases", "Authorization Cases"],
        ["reviews", "Reviews"],
        ...(canManagePolicy ? [["administration", "Administration"] as [Tab, string]] : []),
      ];

  const refresh = useCallback(() => setRevision((value) => value + 1), []);

  useEffect(() => {
    const controller = new AbortController();
    setPageLoading(true);
    setError(null);
    void getQmsAuthorizationOverview(amoCode, controller.signal)
      .then(async (overviewData) => {
        if (controller.signal.aborted) return;
        setOverview(overviewData);
        const canReadPolicy = overviewData.permissions.can_prepare || overviewData.permissions.can_manage_policy;
        const [peopleData, caseData, reviewData, authorizationData, ruleData] = await Promise.all([
          listQmsAuthorizationPeople(amoCode, { limit: 500 }, controller.signal),
          listQmsAuthorizationCases(amoCode, { limit: 500 }, controller.signal),
          listQmsAuthorizationReviews(amoCode, {}, controller.signal),
          listQmsAuthorizations(amoCode, {}, controller.signal),
          canReadPolicy
            ? listQmsPrivilegeRules(amoCode, { includeInactive: true }, controller.signal)
            : Promise.resolve({ items: [] as QmsPrivilegeRule[] }),
        ]);
        if (controller.signal.aborted) return;
        setPeople(peopleData.items);
        setCases(caseData.items);
        setReviews(reviewData.items);
        setAuthorizations(authorizationData.items);
        setRules(ruleData.items);
      })
      .catch((cause) => {
        if (!controller.signal.aborted) setError(errorText(cause));
      })
      .finally(() => {
        if (!controller.signal.aborted) setPageLoading(false);
      });
    return () => controller.abort();
  }, [amoCode, revision]);

  useEffect(() => {
    if (!activePersonKey) {
      setPersonDetail(null);
      return;
    }
    const controller = new AbortController();
    void getQmsAuthorizationPerson(amoCode, activePersonKey, controller.signal)
      .then(setPersonDetail)
      .catch((cause) => {
        if (!controller.signal.aborted) setError(errorText(cause));
      });
    return () => controller.abort();
  }, [activePersonKey, amoCode, revision]);

  useEffect(() => {
    if (!selectedCaseId) {
      setCaseDetail(null);
      return;
    }
    const controller = new AbortController();
    void getQmsAuthorizationCase(amoCode, selectedCaseId, controller.signal)
      .then((detail) => {
        setCaseDetail(detail);
        setRecommendation(detail.case.recommendation || "");
        setDecisionEvidenceIds([]);
      })
      .catch((cause) => {
        if (!controller.signal.aborted) setError(errorText(cause));
      });
    return () => controller.abort();
  }, [amoCode, selectedCaseId, revision]);

  useEffect(() => {
    const action = searchParams.get("action");
    if (action === "CREATE" && canPrepare) {
      setTab("people");
      setNominateOpen(true);
    }
    if (action === "CREATE_RULE" && canManagePolicy) {
      setTab("administration");
      setRuleOpen(true);
      const requestedType = searchParams.get("ruleType");
      if (requestedType === "LEAD_AUDITOR" || requestedType === "AUDITOR") setRuleType(requestedType);
    }
  }, [canManagePolicy, canPrepare, searchParams]);

  const filteredPeople = useMemo(() => {
    const term = search.trim().toLowerCase();
    if (!term) return people;
    return people.filter((person) =>
      [person.name, person.staff_code, person.home_role, person.department]
        .some((value) => String(value || "").toLowerCase().includes(term)),
    );
  }, [people, search]);

  const filteredCases = useMemo(() => cases.filter((item) => !caseStatus || item.status === caseStatus), [cases, caseStatus]);

  const reviewQueues = useMemo(() => {
    const today = new Date(todayKey() + "T00:00:00");
    const daysUntil = (value?: string | null) => {
      if (!value) return null;
      const parsed = new Date(value.slice(0, 10) + "T00:00:00");
      if (Number.isNaN(parsed.getTime())) return null;
      return Math.floor((parsed.getTime() - today.getTime()) / 86_400_000);
    };
    const overdue = authorizations.filter((item) => {
      const days = daysUntil(item.next_review_due);
      return days != null && days < 0 && item.status !== "REVOKED";
    });
    const dueSoon = authorizations.filter((item) => {
      const days = daysUntil(item.next_review_due);
      return days != null && days >= 0 && days <= 60 && item.status !== "REVOKED";
    });
    const conditionalExpiring = authorizations.filter((item) => {
      const exemption = item.readiness?.controlled_exemption;
      const days = daysUntil(exemption?.expires_on);
      return Boolean(exemption && days != null && days >= 0 && days <= 60);
    });
    const suspended = authorizations.filter((item) => item.status === "SUSPENDED");
    const competenceLapses = authorizations.filter((item) =>
      item.readiness?.hard_blockers.some((blocker) => blocker.code === "training_current_verified"),
    );
    return { overdue, dueSoon, conditionalExpiring, suspended, competenceLapses };
  }, [authorizations]);

  function chooseTab(next: Tab) {
    setTab(next);
    const params = new URLSearchParams(searchParams);
    params.set("workspace", "people");
    params.set("tab", next);
    params.delete("action");
    params.delete("ruleType");
    params.delete("ruleId");
    setSearchParams(params, { replace: true });
  }

  async function run(label: string, action: () => Promise<unknown>): Promise<boolean> {
    setBusy(true);
    setError(null);
    setNotice(null);
    try {
      await action();
      setNotice(label);
      refresh();
      return true;
    } catch (cause) {
      setError(errorText(cause));
      return false;
    } finally {
      setBusy(false);
    }
  }

  async function submitNomination(event: FormEvent) {
    event.preventDefault();
    if (!nominatePerson || !nominateRule) return;
    const ok = await run("Authorization case created.", () => createQmsAuthorizationCase(amoCode, {
      user_id: nominatePerson,
      requested_rule_id: nominateRule,
      nomination_reason: nominateReason,
    }));
    if (ok) {
      setNominateOpen(false);
      chooseTab("cases");
    }
  }

  async function submitBatch(event: FormEvent) {
    event.preventDefault();
    if (!batchPeople.length || !batchRule) return;
    const ok = await run("Batch nomination completed.", () => createQmsAuthorizationCasesBatch(amoCode, {
      user_ids: batchPeople,
      requested_rule_id: batchRule,
      nomination_reason: batchReason,
    }));
    if (ok) {
      setBatchOpen(false);
      setBatchPeople([]);
      chooseTab("cases");
    }
  }

  async function savePreparation() {
    if (!selectedCaseId) return;
    await run("Case preparation saved.", () => prepareQmsAuthorizationCase(amoCode, selectedCaseId, {
      status: preparationStatus,
      recommendation,
      reason: preparationReason,
    }));
  }

  async function submitForDecision() {
    if (!selectedCaseId || !recommendation.trim()) {
      setError("Enter the Quality Officer recommendation before submitting the case.");
      return;
    }
    await run("Case submitted for final decision.", () => submitQmsAuthorizationCase(amoCode, selectedCaseId, {
      recommendation,
      reason: "Prepared evidence reviewed and case submitted for final Quality decision.",
    }));
  }

  async function makeDecision() {
    if (!selectedCaseId || !caseDetail || !decisionReason.trim()) {
      setError("A decision reason is required.");
      return;
    }
    if (
      decision === "APPROVE"
      && caseDetail.case.case_type === "CHANGE_AUTHORIZATION"
      && caseDetail.readiness.development.observed_audits < caseDetail.readiness.development.target
      && !developmentBasis.trim()
    ) {
      setError("Record the approval basis when the three-observer-audit development target is incomplete.");
      return;
    }
    if (decision === "APPROVE" && caseDetail.evidence.length > 0 && decisionEvidenceIds.length === 0) {
      setError("Select the case evidence considered for this authorization decision.");
      return;
    }
    if (!window.confirm("Confirm final decision: " + human(decision) + "?")) return;
    const sourceReferences = caseDetail.evidence
      .filter((item) => decisionEvidenceIds.includes(item.id))
      .map((item) => ({
        type: "AUTHORIZATION_EVIDENCE",
        evidence_id: item.id,
        evidence_type: item.type,
        label: item.label,
      }));
    await run("Authorization decision recorded.", () => decideQmsAuthorizationCase(amoCode, selectedCaseId, {
      decision,
      reason: decisionReason,
      effective_from: decision === "APPROVE" ? decisionEffective : undefined,
      expires_on: decision === "APPROVE" && decisionExpiry ? decisionExpiry : undefined,
      next_review_due: decision === "APPROVE" && decisionReviewDue ? decisionReviewDue : undefined,
      incomplete_development_basis: developmentBasis || undefined,
      source_references: sourceReferences,
      confirmed: true,
    }));
  }

  async function addEvidenceReference() {
    if (!selectedCaseId || !evidenceLabel.trim()) return;
    let sourceReference: Record<string, unknown> = {};
    if (evidenceSource.trim()) {
      sourceReference = { reference: evidenceSource.trim() };
    }
    await run("Evidence reference linked.", () => addQmsAuthorizationEvidenceReference(amoCode, selectedCaseId, {
      evidence_type: evidenceType,
      label: evidenceLabel,
      source_module: evidenceSource ? "EXTERNAL" : undefined,
      source_reference: sourceReference,
    }));
    setEvidenceLabel("");
    setEvidenceSource("");
  }

  async function uploadEvidence(file: File | null) {
    if (!file || !selectedCaseId) return;
    await run("Evidence file uploaded.", () => uploadQmsAuthorizationCaseEvidence(amoCode, selectedCaseId, {
      file,
      label: evidenceLabel.trim() || file.name,
      evidence_type: evidenceType,
    }));
    setEvidenceLabel("");
  }

  async function downloadEvidence(evidenceId: string, fallbackName: string) {
    try {
      setBusy(true);
      const { blob, filename } = await downloadQmsAuthorizationEvidence(amoCode, evidenceId);
      downloadBlob(blob, filename || fallbackName);
    } catch (cause) {
      setError(errorText(cause));
    } finally {
      setBusy(false);
    }
  }

  function resetExemptionForm() {
    setExemptionCriterion("training_current_verified");
    setExemptionReason("");
    setExemptionEquivalentEvidence("");
    setExemptionConditions("");
    setExemptionLimitations("");
    setExemptionSupervisionRequired(false);
    setExemptionSupervisor("");
    setExemptionEffective(todayKey());
    setExemptionExpiry(inOneYear());
  }

  function openCaseExemption() {
    setExemptionAuthorization(null);
    resetExemptionForm();
    setExemptionOpen(true);
  }

  function openAuthorizationExemption(item: QmsAuthorization) {
    setExemptionAuthorization(item);
    resetExemptionForm();
    setExemptionOpen(true);
  }

  async function approveExemption() {
    if ((!selectedCaseId && !exemptionAuthorization) || !exemptionReason.trim() || !exemptionEquivalentEvidence.trim() || !exemptionConditions.trim()) {
      setError("Criterion, reason, equivalent evidence and at least one operating condition are required.");
      return;
    }
    if (exemptionSupervisionRequired && !exemptionSupervisor) {
      setError("Select a supervisor when supervision is required.");
      return;
    }
    if (!window.confirm("Approve this time-bounded Controlled Exemption / Conditional Authorization?")) return;
    const payload = {
      criterion: exemptionCriterion,
      reason_normal_compliance_impossible: exemptionReason,
      equivalent_evidence: exemptionEquivalentEvidence.split("\n").map((value) => value.trim()).filter(Boolean).map((reference) => ({ reference })),
      limitations: exemptionLimitations.split("\n").map((value) => value.trim()).filter(Boolean),
      supervision_required: exemptionSupervisionRequired,
      supervisor_user_id: exemptionSupervisionRequired ? exemptionSupervisor : undefined,
      conditions: exemptionConditions.split("\n").map((value) => value.trim()).filter(Boolean),
      effective_from: exemptionEffective,
      expires_on: exemptionExpiry,
      confirmed: true,
    };
    const action = exemptionAuthorization
      ? () => createQmsAuthorizationControlledExemption(amoCode, exemptionAuthorization.key, payload)
      : () => createQmsCaseControlledExemption(amoCode, selectedCaseId, payload);
    const ok = await run("Controlled exemption approved.", action);
    if (ok) {
      setExemptionOpen(false);
      setExemptionAuthorization(null);
    }
  }

  async function revokeExemption(exemptionId: string) {
    const reason = window.prompt("Reason for revoking this Controlled Exemption / Conditional Authorization:");
    if (!reason?.trim()) return;
    if (!window.confirm("Confirm revocation of this controlled exemption?")) return;
    await run("Controlled exemption revoked.", () => revokeQmsControlledExemption(amoCode, exemptionId, {
      reason: reason.trim(),
      confirmed: true,
    }));
  }

  function openLifecycle(item: QmsAuthorization, action: "SUSPEND" | "REVOKE" | "REINSTATE" | "RENEW") {
    setLifecycleAuthorization(item);
    setLifecycleDecision(action);
    setLifecycleReason("");
    setLifecycleDate(todayKey());
    setLifecycleExpiry(item.expires_on || "");
    setLifecycleReviewDue(item.next_review_due || "");
    setLifecycleEvidenceReferences("");
    setLifecycleOpen(true);
  }

  async function submitLifecycle(event: FormEvent) {
    event.preventDefault();
    if (!lifecycleAuthorization || !lifecycleReason.trim()) return;
    if (!window.confirm(`Confirm ${human(lifecycleDecision)} for ${lifecycleAuthorization.person || "this person"}?`)) return;
    const ok = await run(`${human(lifecycleDecision)} decision recorded.`, () => decideQmsAuthorizationLifecycle(
      amoCode,
      lifecycleAuthorization.key,
      {
        decision: lifecycleDecision,
        reason: lifecycleReason,
        effective_date: lifecycleDate,
        expires_on: ["RENEW", "REINSTATE"].includes(lifecycleDecision) && lifecycleExpiry ? lifecycleExpiry : undefined,
        next_review_due: lifecycleReviewDue || undefined,
        source_references: lifecycleEvidenceReferences
          .split("\n")
          .map((value) => value.trim())
          .filter(Boolean)
          .map((reference) => ({ reference })),
        confirmed: true,
      },
    ));
    if (ok) setLifecycleOpen(false);
  }

  async function submitReview(event: FormEvent) {
    event.preventDefault();
    if (!reviewAuthorization || !reviewReason.trim()) return;
    if (!window.confirm("Confirm this governed periodic authorization review?")) return;
    const ok = await run("Periodic authorization review recorded.", () => createQmsAuthorizationReview(amoCode, reviewAuthorization, {
      review_outcome: reviewOutcome,
      review_reason: reviewReason,
      next_review_due: reviewNextDue || undefined,
      review_evidence: reviewEvidenceReferences
        .split("\n")
        .map((value) => value.trim())
        .filter(Boolean)
        .map((reference) => ({ reference })),
      review_notes: reviewNotes || undefined,
      confirmed: true,
    }));
    if (ok) setReviewOpen(false);
  }

  async function downloadAuthorization(item: QmsAuthorization) {
    try {
      setBusy(true);
      const { blob, filename } = await downloadQmsAuthorizationRecord(amoCode, item.key);
      downloadBlob(blob, filename || "quality-authorization-record.pdf");
    } catch (cause) {
      setError(errorText(cause));
    } finally {
      setBusy(false);
    }
  }

  function openCreateRule() {
    setEditingRule(null);
    setRuleTitle("");
    setRuleCode("");
    setRuleType("AUDITOR");
    setRuleDescription("");
    setRuleTraining("");
    setRuleIndependence(true);
    setRuleDevelopmental(false);
    setRuleOpen(true);
  }

  function openEditRule(rule: QmsPrivilegeRule) {
    setEditingRule(rule);
    setRuleTitle(rule.title);
    setRuleCode(rule.privilege_code);
    setRuleType(rule.privilege_type);
    setRuleDescription(rule.description || "");
    const competence = rule.scope_schema?.qms_competence;
    const competenceCodes = competence && typeof competence === "object" && Array.isArray((competence as { codes?: unknown[] }).codes)
      ? (competence as { codes: unknown[] }).codes.map((value) => String(value))
      : [];
    setRuleTraining((rule.required_training_course_codes.length ? rule.required_training_course_codes : competenceCodes).join(", "));
    setRuleIndependence(rule.independence_required);
    setRuleDevelopmental(Boolean((rule.scope_schema || {}).supervised_development));
    setRuleOpen(true);
  }

  async function saveRule(event: FormEvent) {
    event.preventDefault();
    const training = ruleTraining.split(",").map((value) => value.trim().toUpperCase()).filter(Boolean);
    const scope_schema: Record<string, unknown> = editingRule ? { ...(editingRule.scope_schema || {}) } : {};
    if (ruleDevelopmental) {
      scope_schema.supervised_development = true;
      scope_schema.allowed_assignment_roles = ["OBSERVER_AUDITOR", "ASSISTANT_AUDITOR"];
    } else {
      delete scope_schema.supervised_development;
      delete scope_schema.allowed_assignment_roles;
    }
    if (editingRule) {
      const ok = await run("Authorization policy updated.", () => updateQmsPrivilegeRule(amoCode, editingRule.id, {
        title: ruleTitle,
        description: ruleDescription,
        required_training_course_codes: training,
        independence_required: ruleIndependence,
        scope_schema,
      }));
      if (!ok) return;
    } else {
      const ok = await run("Authorization policy created.", () => createQmsPrivilegeRule(amoCode, {
        privilege_code: ruleCode.trim().toUpperCase().replace(/[^A-Z0-9_-]+/g, "_"),
        title: ruleTitle,
        privilege_type: ruleType,
        description: ruleDescription,
        required_training_course_codes: training,
        independence_required: ruleIndependence,
        scope_schema,
      }));
      if (!ok) return;
    }
    setRuleOpen(false);
  }

  async function toggleRule(rule: QmsPrivilegeRule) {
    if (rule.is_active && !window.confirm(`Deactivate ${rule.title}? Live authorizations must already be resolved.`)) return;
    await run("Authorization policy status updated.", () => updateQmsPrivilegeRule(amoCode, rule.id, { is_active: !rule.is_active }));
  }

  async function createDefaultPolicies() {
    await run("Default Quality authorization policies are ready.", () => ensureQmsDefaultPrivilegeRules(amoCode));
  }

  if (pageLoading && !overview) {
    return <section className="qms-authz qms-people qms-surface-root"><div className="qms-authz-loading">Loading Quality authorization control…</div></section>;
  }

  return (
    <section className="qms-authz qms-people qms-surface-root" aria-label="QMS People and authorization control">
      <header className="qms-authz-header">
        <div>
          <p className="qms-authz-eyebrow">Quality Management System</p>
          <h2 className="qms-authz-page-heading">Authorization governance</h2>
          <p>
            Govern Quality appointments, authorization cases, competence evidence, periodic reviews and authorization decisions.
            Audit assignment remains in the audit workflow.
          </p>
        </div>
        <button type="button" className="qms-authz-button qms-authz-button--ghost" onClick={refresh} disabled={pageLoading || busy}>
          <RefreshCw size={16} /> Refresh
        </button>
      </header>

      {error ? <div className="qms-authz-alert qms-authz-alert--error" role="alert"><AlertTriangle size={17} /> {error}</div> : null}
      {notice ? <div className="qms-authz-alert qms-authz-alert--success" role="status"><CheckCircle2 size={17} /> {notice}</div> : null}

      <nav className="qms-authz-tabs" aria-label="Authorization control views">
        {visibleTabs.map(([value, label]) => (
          <button key={value} type="button" className={effectiveTab === value ? "is-active" : ""} onClick={() => chooseTab(value)}>
            {label}
          </button>
        ))}
      </nav>

      {effectiveTab === "overview" && overview && !selfServiceOnly ? (
        <div className="qms-authz-stack">
          <div className="qms-authz-metrics">
            {[
              ["Active authorizations", overview.metrics.active_authorizations],
              ["Open cases", overview.metrics.open_authorization_cases],
              ["Expiring ≤60 days", overview.metrics.expiring_within_60_days],
              ["Suspended", overview.metrics.suspended_authorizations],
              ["Reviews due", overview.metrics.reviews_due],
              ["Controlled exemptions", overview.metrics.active_controlled_exemptions],
            ].map(([label, value]) => (
              <article className="qms-authz-metric" key={String(label)}>
                <span>{label}</span>
                <strong>{value}</strong>
              </article>
            ))}
          </div>
          <article className="qms-authz-card">
            <SectionTitle icon={<CalendarClock size={19} />} title="Attention required" subtitle="Items needing preparation, decision or review." />
            {overview.attention.length ? (
              <div className="qms-authz-list">
                {overview.attention.map((item, index) => (
                  <div className="qms-authz-row" key={`${item.type}-${item.person}-${index}`}>
                    <div>
                      <strong>{item.person}</strong>
                      <span>{item.authorization || item.type}</span>
                    </div>
                    <div>
                      <Pill tone={statusTone(item.status)}>{human(item.status)}</Pill>
                      <small>{item.reason}</small>
                    </div>
                  </div>
                ))}
              </div>
            ) : <div className="qms-authz-empty">No current authorization-control items require attention.</div>}
          </article>
        </div>
      ) : null}

      {effectiveTab === "people" ? (
        <div className={selfServiceOnly ? "qms-authz-stack" : "qms-authz-grid qms-authz-grid--split"}>
          {!selfServiceOnly ? <article className="qms-authz-card">
            <div className="qms-authz-toolbar">
              <SectionTitle icon={<Users size={19} />} title="People" subtitle="Workforce identity and current Quality authorization status." />
              {canPrepare ? (
                <div className="qms-authz-toolbar__actions">
                  <button type="button" className="qms-authz-button" onClick={() => setNominateOpen(true)}><UserCheck size={16} /> Nominate</button>
                  <button type="button" className="qms-authz-button qms-authz-button--secondary" onClick={() => setBatchOpen(true)}>Batch nominate</button>
                </div>
              ) : null}
            </div>
            <label className="qms-authz-search"><Search size={16} /><input value={search} onChange={(event) => setSearch(event.target.value)} placeholder="Search name, staff code, role or department" /></label>
            <div className="qms-authz-list">
              {filteredPeople.map((person) => (
                <button type="button" className={`qms-authz-row qms-authz-row--button ${selectedPersonKey === person.key ? "is-selected" : ""}`} key={person.key} onClick={() => setSelectedPersonKey(person.key)}>
                  <div>
                    <strong>{person.name}</strong>
                    <span>{[person.home_role ? human(person.home_role) : null, person.department].filter(Boolean).join(" · ") || "Role not recorded"}</span>
                  </div>
                  <div>
                    <Pill tone={person.workforce_status === "Active" ? "good" : "bad"}>{person.workforce_status}</Pill>
                    <small>{person.authorizations.length ? person.authorizations.map((item) => `${item.authorization} — ${human(item.status)}`).join(" · ") : "No Quality authorization"}</small>
                  </div>
                </button>
              ))}
            </div>
          </article> : null}

          <article className="qms-authz-card qms-authz-detail">
            {personDetail ? (
              <>
                <SectionTitle icon={<ShieldCheck size={19} />} title={personDetail.person.name} subtitle={[personDetail.person.home_role ? human(personDetail.person.home_role) : null, personDetail.person.department].filter(Boolean).join(" · ")} />
                <div className="qms-authz-facts">
                  <div><span>Workforce</span><strong>{personDetail.person.active ? "Active" : "Inactive"}</strong></div>
                  <div><span>Staff code</span><strong>{personDetail.person.staff_code || "Not recorded"}</strong></div>
                  <div><span>Observer development</span><strong>{personDetail.audit_participation.observed_completed} / {personDetail.audit_participation.observed_target}</strong></div>
                </div>
                <h3>Quality appointments</h3>
                {personDetail.appointments.length ? personDetail.appointments.map((item, index) => (
                  <div className="qms-authz-subrow" key={`${item.function}-${index}`}>
                    <div><strong>{item.function}</strong><span>{shortDate(item.effective_from)} – {shortDate(item.effective_until)}</span></div>
                    <Pill tone={statusTone(item.status)}>{human(item.status)}</Pill>
                  </div>
                )) : <p className="qms-authz-muted">No governed Quality appointment recorded.</p>}

                <h3>Quality authorizations</h3>
                {personDetail.authorizations.length ? personDetail.authorizations.map((item) => (
                  <div className="qms-authz-authorization" key={item.key}>
                    <div className="qms-authz-authorization__heading">
                      <div><strong>{item.authorization}</strong><span>{item.scope}</span></div>
                      <Pill tone={statusTone(item.status)}>{human(item.status)}</Pill>
                    </div>
                    <div className="qms-authz-facts qms-authz-facts--compact">
                      <div><span>Effective</span><strong>{shortDate(item.effective_from)}</strong></div>
                      <div><span>Expires</span><strong>{shortDate(item.expires_on)}</strong></div>
                      <div><span>Next review</span><strong>{shortDate(item.next_review_due)}</strong></div>
                      {item.readiness ? <div><span>Training</span><strong>{item.readiness.training.status}</strong></div> : null}
                    </div>
                    {item.readiness?.development.supervision_required ? (
                      <div className="qms-authz-alert qms-authz-alert--info">
                        <BadgeCheck size={16} />
                        Development authorization · Training: {item.readiness.training.status} · Supervision required · Observed audits {item.readiness.development.progress_label}
                      </div>
                    ) : null}
                    {item.readiness?.controlled_exemption ? (
                      <div className="qms-authz-exemption">
                        <Pill tone="warn">Conditional</Pill>
                        <strong>Controlled Exemption Active until {shortDate(item.readiness.controlled_exemption.expires_on)}</strong>
                        {item.readiness.controlled_exemption.limitations.length ? (
                          <p><strong>Limitations:</strong> {item.readiness.controlled_exemption.limitations.map(String).join("; ")}</p>
                        ) : null}
                        {item.readiness.controlled_exemption.conditions.length ? (
                          <p><strong>Conditions:</strong> {item.readiness.controlled_exemption.conditions.map(String).join("; ")}</p>
                        ) : null}
                      </div>
                    ) : null}
                    <div className="qms-authz-actions">
                      <button type="button" className="qms-authz-link" onClick={() => void downloadAuthorization(item)}><Download size={15} /> Authorization record</button>
                      {canApprove && item.status === "ACTIVE" ? <>
                        <button type="button" className="qms-authz-link" onClick={() => openLifecycle(item, "SUSPEND")}>Suspend</button>
                        <button type="button" className="qms-authz-link qms-authz-link--danger" onClick={() => openLifecycle(item, "REVOKE")}>Revoke</button>
                        <button type="button" className="qms-authz-link" onClick={() => openLifecycle(item, "RENEW")}>Renew</button>
                        {canExempt && item.readiness?.controlled_exemption ? (
                          <button type="button" className="qms-authz-link qms-authz-link--danger" onClick={() => void revokeExemption(item.readiness!.controlled_exemption!.id)}>Revoke exemption</button>
                        ) : canExempt ? (
                          <button type="button" className="qms-authz-link" onClick={() => openAuthorizationExemption(item)}>Controlled exemption</button>
                        ) : null}
                      </> : null}
                      {canApprove && item.status === "SUSPENDED" ? <>
                        <button type="button" className="qms-authz-link" onClick={() => openLifecycle(item, "REINSTATE")}>Reinstate</button>
                        <button type="button" className="qms-authz-link qms-authz-link--danger" onClick={() => openLifecycle(item, "REVOKE")}>Revoke</button>
                      </> : null}
                    </div>
                  </div>
                )) : <p className="qms-authz-muted">No Quality authorizations recorded.</p>}

                <h3>Audit participation</h3>
                {personDetail.audit_participation.items.length ? personDetail.audit_participation.items.map((audit, index) => (
                  <div className="qms-authz-subrow" key={`${audit.reference || audit.title}-${index}`}>
                    <div><strong>{audit.reference || "Audit"} · {audit.title}</strong><span>{audit.roles.join(", ")}</span></div>
                    <Pill tone={statusTone(audit.status || "")}>{human(audit.status)}</Pill>
                  </div>
                )) : <p className="qms-authz-muted">No recorded audit participation.</p>}
              </>
            ) : <div className="qms-authz-empty">Select a person to view appointments, authorizations, development history and audit participation.</div>}
          </article>
        </div>
      ) : null}

      {effectiveTab === "cases" ? (
        <div className="qms-authz-grid qms-authz-grid--split">
          <article className="qms-authz-card">
            <div className="qms-authz-toolbar">
              <SectionTitle icon={<ClipboardCheck size={19} />} title="Authorization Cases" subtitle="Pre-decision nomination, evidence, recommendation and approval." />
              {canPrepare ? <button type="button" className="qms-authz-button" onClick={() => setNominateOpen(true)}><FilePlus2 size={16} /> New case</button> : null}
            </div>
            <select className="qms-authz-select" value={caseStatus} onChange={(event) => setCaseStatus(event.target.value)}>
              <option value="">All case statuses</option>
              {CASE_STATUSES.map((value) => <option value={value} key={value}>{human(value)}</option>)}
            </select>
            <div className="qms-authz-list">
              {filteredCases.map((item) => (
                <button type="button" className={`qms-authz-row qms-authz-row--button ${selectedCaseId === item.id ? "is-selected" : ""}`} key={item.id} onClick={() => setSelectedCaseId(item.id)}>
                  <div><strong>{item.person}</strong><span>{item.authorization} · {human(item.case_type)}</span></div>
                  <div><Pill tone={statusTone(item.status)}>{human(item.status)}</Pill><small>{item.next_action}</small></div>
                </button>
              ))}
            </div>
          </article>

          <article className="qms-authz-card qms-authz-detail">
            {caseDetail ? (
              <>
                <SectionTitle icon={<History size={19} />} title={caseDetail.case.person.name || "Person unavailable"} subtitle={caseDetail.case.authorization} />
                <div className="qms-authz-case-banner">
                  <Pill tone={statusTone(caseDetail.case.status)}>{human(caseDetail.case.status)}</Pill>
                  <span>{human(caseDetail.case.case_type)} · Nominated {shortDate(caseDetail.case.nomination_date)} by {caseDetail.case.nominator}</span>
                </div>

                <div className="qms-authz-decision-context">
                  <span><strong>Current authorization:</strong> {String(caseDetail.case.current_authorization.authorization || "None")} {caseDetail.case.current_authorization.status ? ` · ${human(String(caseDetail.case.current_authorization.status))}` : ""}</span>
                  <span><strong>Requested authorization:</strong> {String(caseDetail.case.requested_authorization.authorization || caseDetail.case.authorization)} · {String(caseDetail.case.requested_authorization.scope || "Global")}</span>
                </div>

                <div className="qms-authz-facts">
                  <div><span>Readiness</span><strong>{caseDetail.readiness.status}</strong></div>
                  <div><span>Training</span><strong>{caseDetail.readiness.training.status}</strong></div>
                  <div><span>Observer development</span><strong>{caseDetail.readiness.development.progress_label}</strong></div>
                </div>
                {caseDetail.readiness.hard_blockers.length ? (
                  <div className="qms-authz-alert qms-authz-alert--error">
                    <AlertTriangle size={16} />
                    <div>{caseDetail.readiness.hard_blockers.map((item) => <div key={item.code}>{item.message}</div>)}</div>
                  </div>
                ) : null}
                {caseDetail.readiness.development.observed_audits < caseDetail.readiness.development.target ? (
                  <div className="qms-authz-alert qms-authz-alert--info">
                    <BadgeCheck size={16} />
                    The three-observer-audit target is development evidence, not an automatic promotion gate. An approving manager must record the basis if approving before the target is complete.
                  </div>
                ) : null}

                <h3>Training evidence</h3>
                <div className="qms-authz-course-grid">
                  {caseDetail.readiness.training.courses.length ? caseDetail.readiness.training.courses.map((course) => (
                    <div key={course.course}>
                      <strong>{course.course}</strong>
                      <Pill tone={statusTone(course.status)}>{course.status}</Pill>
                      <small>{course.valid_until ? `Valid to ${shortDate(course.valid_until)}` : "No validity date"}</small>
                    </div>
                  )) : <p className="qms-authz-muted">No hard Training requirement is configured for this authorization.</p>}
                </div>

                <h3>Case evidence</h3>
                {caseDetail.evidence.length ? caseDetail.evidence.map((item) => (
                  <div className="qms-authz-subrow" key={item.id}>
                    <div><strong>{item.label}</strong><span>{human(item.type)}{item.source_module ? ` · ${item.source_module}` : ""}</span></div>
                    <div>
                      <Pill>{item.has_file ? "File" : "Reference"}</Pill>
                      {item.has_file ? <button type="button" className="qms-authz-link" onClick={() => void downloadEvidence(item.id, item.filename || "authorization-evidence")}>Download</button> : null}
                    </div>
                  </div>
                )) : <p className="qms-authz-muted">No case evidence linked yet.</p>}

                {caseDetail.controlled_exemption ? (
                  <>
                    <h3>Controlled Exemption / Conditional Authorization</h3>
                    <div className="qms-authz-exemption">
                      <strong>{caseDetail.controlled_exemption.criterion}</strong>
                      <p>{caseDetail.controlled_exemption.reason}</p>
                      <span>{shortDate(caseDetail.controlled_exemption.effective_from)} – {shortDate(caseDetail.controlled_exemption.expires_on)}</span>
                      {caseDetail.controlled_exemption.supervision_required ? <p><strong>Supervisor:</strong> {caseDetail.controlled_exemption.supervisor || "Recorded supervisor"}</p> : null}
                      <p><strong>Equivalent evidence</strong></p>
                      <ul>{caseDetail.controlled_exemption.equivalent_evidence.map((item, index) => <li key={index}>{String(item.reference || JSON.stringify(item))}</li>)}</ul>
                      <p><strong>Conditions</strong></p>
                      <ul>{caseDetail.controlled_exemption.conditions.map((item, index) => <li key={index}>{String(item)}</li>)}</ul>
                      {caseDetail.controlled_exemption.limitations.length ? <>
                        <p><strong>Limitations</strong></p>
                        <ul>{caseDetail.controlled_exemption.limitations.map((item, index) => <li key={index}>{String(item)}</li>)}</ul>
                      </> : null}
                      {canExempt && caseDetail.controlled_exemption.status === "ACTIVE" ? (
                        <button type="button" className="qms-authz-link qms-authz-link--danger" onClick={() => void revokeExemption(caseDetail.controlled_exemption!.id)}>Revoke controlled exemption</button>
                      ) : null}
                    </div>
                  </>
                ) : null}

                {canPrepare && !["APPROVED", "REJECTED", "CANCELLED"].includes(caseDetail.case.status) ? (
                  <details className="qms-authz-workflow" open={caseDetail.case.status !== "READY_FOR_DECISION"}>
                    <summary>Quality Officer preparation</summary>
                    <div className="qms-authz-form-grid">
                      <label>Status<select value={preparationStatus} onChange={(event) => setPreparationStatus(event.target.value as typeof preparationStatus)}>
                        <option value="UNDER_REVIEW">Under review</option>
                        <option value="DEVELOPMENT">Development</option>
                        <option value="AWAITING_EVIDENCE">Awaiting evidence</option>
                        <option value="RETURNED">Returned</option>
                      </select></label>
                      <label className="span-2">Recommendation<textarea value={recommendation} onChange={(event) => setRecommendation(event.target.value)} rows={4} /></label>
                      <label className="span-2">Preparation reason<textarea value={preparationReason} onChange={(event) => setPreparationReason(event.target.value)} rows={3} /></label>
                    </div>
                    <div className="qms-authz-actions">
                      <button type="button" className="qms-authz-button qms-authz-button--secondary" onClick={() => void savePreparation()} disabled={busy}>Save preparation</button>
                      <button type="button" className="qms-authz-button" onClick={() => void submitForDecision()} disabled={busy || Boolean(caseDetail.readiness.hard_blockers.length)}>Submit for decision</button>
                    </div>
                  </details>
                ) : null}

                {canPrepare && !["APPROVED", "REJECTED", "CANCELLED"].includes(caseDetail.case.status) ? (
                  <details className="qms-authz-workflow">
                    <summary>Evidence</summary>
                    <div className="qms-authz-form-grid">
                      <label>Type<select value={evidenceType} onChange={(event) => setEvidenceType(event.target.value)}>
                        {["COMPETENCE_ASSESSMENT", "PRIOR_AUTHORIZATION", "AUDIT_EXPERIENCE", "COMPETENCE_PACKAGE", "APPOINTMENT_LETTER", "OTHER"].map((value) => <option key={value} value={value}>{human(value)}</option>)}
                      </select></label>
                      <label>Label<input value={evidenceLabel} onChange={(event) => setEvidenceLabel(event.target.value)} /></label>
                      <label className="span-2">External reference<input value={evidenceSource} onChange={(event) => setEvidenceSource(event.target.value)} placeholder="Optional controlled source reference" /></label>
                      <div className="qms-authz-actions span-2">
                        <button type="button" className="qms-authz-button qms-authz-button--secondary" onClick={() => void addEvidenceReference()} disabled={!evidenceLabel.trim() || busy}>Link reference</button>
                        <label className="qms-authz-file-button">Upload evidence<input type="file" onChange={(event) => void uploadEvidence(event.target.files?.[0] || null)} /></label>
                      </div>
                    </div>
                  </details>
                ) : null}

                {canExempt && !["APPROVED", "REJECTED", "CANCELLED"].includes(caseDetail.case.status) ? (
                  <div className="qms-authz-actions">
                    <button type="button" className="qms-authz-button qms-authz-button--secondary" onClick={openCaseExemption}>
                      Controlled Exemption / Conditional Authorization
                    </button>
                  </div>
                ) : null}

                {exemptionOpen && canExempt && !exemptionAuthorization ? (
                  <div className="qms-authz-workflow">
                    <div className="qms-authz-decision-context"><span><strong>Approving authority:</strong> {actorName}</span></div>
                    <div className="qms-authz-form-grid">
                      <label>Missing criterion<input value={exemptionCriterion} onChange={(event) => setExemptionCriterion(event.target.value)} /></label>
                      <label>Effective<input type="date" value={exemptionEffective} onChange={(event) => setExemptionEffective(event.target.value)} /></label>
                      <label>Expires<input type="date" value={exemptionExpiry} onChange={(event) => setExemptionExpiry(event.target.value)} /></label>
                      <label className="span-2">Why normal compliance is not currently possible<textarea value={exemptionReason} onChange={(event) => setExemptionReason(event.target.value)} rows={3} /></label>
                      <label className="span-2">Equivalent evidence, one controlled reference per line<textarea value={exemptionEquivalentEvidence} onChange={(event) => setExemptionEquivalentEvidence(event.target.value)} rows={3} /></label>
                      <label className="qms-authz-checkbox span-2"><input type="checkbox" checked={exemptionSupervisionRequired} onChange={(event) => setExemptionSupervisionRequired(event.target.checked)} /> Supervision required</label>
                      {exemptionSupervisionRequired ? <label className="span-2">Supervisor<select value={exemptionSupervisor} onChange={(event) => setExemptionSupervisor(event.target.value)}><option value="">Select supervisor</option>{people.filter((item) => item.workforce_status === "Active").map((item) => <option value={item.key} key={item.key}>{item.name}</option>)}</select></label> : null}
                      <label className="span-2">Operating conditions, one per line<textarea value={exemptionConditions} onChange={(event) => setExemptionConditions(event.target.value)} rows={3} /></label>
                      <label className="span-2">Limitations, one per line<textarea value={exemptionLimitations} onChange={(event) => setExemptionLimitations(event.target.value)} rows={3} /></label>
                    </div>
                    <button type="button" className="qms-authz-button" onClick={() => void approveExemption()} disabled={busy}>Approve controlled exemption</button>
                  </div>
                ) : null}

                {canApprove && caseDetail.case.status === "READY_FOR_DECISION" ? (
                  <div className="qms-authz-workflow qms-authz-workflow--decision">
                    <h3>Final authorization decision</h3>
                    <div className="qms-authz-decision-context">
                      <span><strong>Decision authority:</strong> {actorName}</span>
                      <span><strong>Affected future assignments:</strong> {caseDetail.readiness.affected_assignments.length}</span>
                    </div>
                    {caseDetail.readiness.affected_assignments.length ? (
                      <ul className="qms-authz-assignment-impact">
                        {caseDetail.readiness.affected_assignments.map((item, index) => (
                          <li key={`${item.reference || item.title}-${index}`}>
                            {item.reference || "Audit"} · {item.title || "Scheduled audit"} · {item.role || "Assigned role"}
                          </li>
                        ))}
                      </ul>
                    ) : null}
                    <div className="qms-authz-form-grid">
                      <label>Decision<select value={decision} onChange={(event) => setDecision(event.target.value as typeof decision)}>
                        <option value="APPROVE">Approve</option>
                        <option value="RETURN">Return for more evidence</option>
                        <option value="REJECT">Reject case</option>
                      </select></label>
                      {decision === "APPROVE" ? <>
                        <label>Effective<input type="date" value={decisionEffective} onChange={(event) => setDecisionEffective(event.target.value)} /></label>
                        <label>Expires<input type="date" value={decisionExpiry} onChange={(event) => setDecisionExpiry(event.target.value)} /></label>
                        <label>Next review due<input type="date" value={decisionReviewDue} onChange={(event) => setDecisionReviewDue(event.target.value)} /></label>
                      </> : null}
                      <label className="span-2">Decision reason<textarea value={decisionReason} onChange={(event) => setDecisionReason(event.target.value)} rows={4} /></label>
                      {decision === "APPROVE" && caseDetail.readiness.development.observed_audits < caseDetail.readiness.development.target && caseDetail.case.case_type === "CHANGE_AUTHORIZATION" ? (
                        <label className="span-2">Basis for approval before development target is complete<textarea value={developmentBasis} onChange={(event) => setDevelopmentBasis(event.target.value)} rows={3} /></label>
                      ) : null}
                      {caseDetail.evidence.length ? (
                        <fieldset className="qms-authz-checklist span-2">
                          <legend>Evidence considered for this decision</legend>
                          {caseDetail.evidence.map((item) => (
                            <label key={item.id}>
                              <input
                                type="checkbox"
                                checked={decisionEvidenceIds.includes(item.id)}
                                onChange={(event) => setDecisionEvidenceIds((current) =>
                                  event.target.checked
                                    ? [...current, item.id]
                                    : current.filter((value) => value !== item.id),
                                )}
                              />
                              <span>{item.label} · {human(item.type)}</span>
                            </label>
                          ))}
                        </fieldset>
                      ) : <p className="qms-authz-muted span-2">No separately linked case evidence is available; source-backed readiness remains captured in the decision snapshot.</p>}
                    </div>
                    <button type="button" className="qms-authz-button" onClick={() => void makeDecision()} disabled={busy}>Record final decision</button>
                  </div>
                ) : null}

                <h3>Prior authorization review history</h3>
                {caseDetail.authorization_reviews.length ? (
                  <div className="qms-authz-list">
                    {caseDetail.authorization_reviews.map((item) => (
                      <div className="qms-authz-subrow" key={item.id}>
                        <div>
                          <strong>{human(item.outcome)}</strong>
                          <span>{shortDate(item.last_reviewed)} · Reviewed by {item.reviewed_by}</span>
                        </div>
                        <small>Next review: {shortDate(item.next_review_due)}</small>
                      </div>
                    ))}
                  </div>
                ) : <p className="qms-authz-muted">No prior governed authorization reviews are recorded for the current authorization.</p>}

                <h3>Case history</h3>
                <div className="qms-authz-timeline">
                  {caseDetail.history.map((item, index) => (
                    <div key={`${item.action}-${item.occurred_at}-${index}`}>
                      <strong>{human(item.action)}</strong>
                      <span>{item.actor} · {shortDate(item.occurred_at)}</span>
                      <p>{item.reason}</p>
                    </div>
                  ))}
                </div>
              </>
            ) : <div className="qms-authz-empty">Select an authorization case to review evidence, readiness and decision history.</div>}
          </article>
        </div>
      ) : null}

      {effectiveTab === "reviews" ? (
        <div className="qms-authz-stack">
          <article className="qms-authz-card">
            <div className="qms-authz-toolbar">
              <SectionTitle icon={<CalendarClock size={19} />} title="Review Control" subtitle="Due, overdue, conditional, suspended and competence-driven reassessment queues." />
              {canReview ? <button type="button" className="qms-authz-button" onClick={() => setReviewOpen(true)}>Record review</button> : null}
            </div>
            <div className="qms-authz-metrics">
              {[
                ["Due soon", reviewQueues.dueSoon.length],
                ["Overdue", reviewQueues.overdue.length],
                ["Conditions expiring", reviewQueues.conditionalExpiring.length],
                ["Suspended", reviewQueues.suspended.length],
                ["Competence lapses", reviewQueues.competenceLapses.length],
                ["Completed reviews", reviews.length],
              ].map(([label, value]) => (
                <article className="qms-authz-metric" key={String(label)}>
                  <span>{label}</span>
                  <strong>{value}</strong>
                </article>
              ))}
            </div>
          </article>

          {([
            ["Overdue", reviewQueues.overdue, "Next review date has passed."],
            ["Due soon", reviewQueues.dueSoon, "Next governed review is due within 60 days."],
            ["Conditional authorizations expiring", reviewQueues.conditionalExpiring, "Controlled exemption expires within 60 days."],
            ["Suspensions requiring reassessment", reviewQueues.suspended, "Authorization remains suspended until a governed decision changes it."],
            ["Competence lapses", reviewQueues.competenceLapses, "Mandatory current competence is not verified."],
          ] as Array<[string, QmsAuthorization[], string]>).map(([title, items, helper]) => (
            <article className="qms-authz-card" key={title}>
              <SectionTitle icon={<AlertTriangle size={18} />} title={title} subtitle={helper} />
              <div className="qms-authz-list">
                {items.length ? items.map((item) => (
                  <div className="qms-authz-row" key={item.key}>
                    <div>
                      <strong>{item.person || "Person unavailable"}</strong>
                      <span>{item.authorization} · {human(item.status)}</span>
                    </div>
                    <div>
                      {item.readiness?.controlled_exemption ? <Pill tone="warn">Conditional</Pill> : <Pill tone={statusTone(item.status)}>{human(item.status)}</Pill>}
                      <small>
                        {item.readiness?.controlled_exemption
                          ? "Condition expires " + shortDate(item.readiness.controlled_exemption.expires_on)
                          : "Next review " + shortDate(item.next_review_due)}
                      </small>
                    </div>
                  </div>
                )) : <div className="qms-authz-empty">No items in this queue.</div>}
              </div>
            </article>
          ))}

          <article className="qms-authz-card">
            <SectionTitle icon={<History size={19} />} title="Completed Reviews" subtitle="Immutable governed review history." />
            <div className="qms-authz-list">
              {reviews.length ? reviews.map((item) => (
                <div className="qms-authz-row" key={item.id}>
                  <div><strong>{item.person || "Person unavailable"}</strong><span>{item.authorization || "Quality authorization"} · Reviewed by {item.reviewed_by}</span></div>
                  <div><Pill tone={statusTone(item.outcome)}>{human(item.outcome)}</Pill><small>Next: {shortDate(item.next_review_due)}</small></div>
                </div>
              )) : <div className="qms-authz-empty">No periodic reviews have been recorded.</div>}
            </div>
          </article>
        </div>
      ) : null}

      {effectiveTab === "administration" && canManagePolicy ? (
        <article className="qms-authz-card">
          <div className="qms-authz-toolbar">
            <SectionTitle icon={<Settings2 size={19} />} title="Authorization Policy Administration" subtitle="Restricted configuration. Training course recurrence remains owned by Training." />
            <div className="qms-authz-toolbar__actions">
              {!rules.some((rule) => rule.is_active) ? <button type="button" className="qms-authz-button qms-authz-button--secondary" onClick={() => void createDefaultPolicies()} disabled={busy}>Create default policies</button> : null}
              <button type="button" className="qms-authz-button" onClick={openCreateRule}>New authorization type</button>
            </div>
          </div>
          <div className="qms-authz-list">
            {rules.map((rule) => (
              <div className="qms-authz-row" key={rule.id}>
                <div>
                  <strong>{rule.title}</strong>
                  <span>{human(rule.privilege_type)} · {rule.required_training_course_codes.length ? rule.required_training_course_codes.join(", ") : "No hard course list on policy"}</span>
                </div>
                <div>
                  <Pill tone={rule.is_active ? "good" : "neutral"}>{rule.is_active ? "Active" : "Inactive"}</Pill>
                  <div className="qms-authz-inline-actions">
                    <button type="button" className="qms-authz-link" onClick={() => openEditRule(rule)}>Edit</button>
                    <button type="button" className="qms-authz-link" onClick={() => void toggleRule(rule)}>{rule.is_active ? "Deactivate" : "Activate"}</button>
                  </div>
                </div>
              </div>
            ))}
          </div>
        </article>
      ) : null}

      {nominateOpen ? (
        <div className="qms-authz-modal" role="dialog" aria-modal="true" aria-label="Nominate person for Quality authorization">
          <form className="qms-authz-modal__panel" onSubmit={(event) => void submitNomination(event)}>
            <div className="qms-authz-modal__header"><h2>Nominate for Quality authorization</h2><button type="button" onClick={() => setNominateOpen(false)}><XCircle size={20} /></button></div>
            <label>Person<select required value={nominatePerson} onChange={(event) => setNominatePerson(event.target.value)}><option value="">Select person</option>{people.filter((item) => item.workforce_status === "Active").map((item) => <option value={item.key} key={item.key}>{item.name}{item.home_role ? ` — ${human(item.home_role)}` : ""}</option>)}</select></label>
            <label>Authorization type<select required value={nominateRule} onChange={(event) => setNominateRule(event.target.value)}><option value="">Select authorization</option>{rules.filter((item) => item.is_active).map((item) => <option key={item.id} value={item.id}>{item.title}</option>)}</select></label>
            <label>Nomination reason<textarea required rows={4} value={nominateReason} onChange={(event) => setNominateReason(event.target.value)} /></label>
            <div className="qms-authz-actions"><button type="button" className="qms-authz-button qms-authz-button--ghost" onClick={() => setNominateOpen(false)}>Cancel</button><button className="qms-authz-button" disabled={busy}>Create case</button></div>
          </form>
        </div>
      ) : null}

      {batchOpen ? (
        <div className="qms-authz-modal" role="dialog" aria-modal="true" aria-label="Batch nominate personnel">
          <form className="qms-authz-modal__panel" onSubmit={(event) => void submitBatch(event)}>
            <div className="qms-authz-modal__header"><h2>Batch nominate</h2><button type="button" onClick={() => setBatchOpen(false)}><XCircle size={20} /></button></div>
            <label>Authorization type<select required value={batchRule} onChange={(event) => setBatchRule(event.target.value)}><option value="">Select authorization</option>{rules.filter((item) => item.is_active).map((item) => <option key={item.id} value={item.id}>{item.title}</option>)}</select></label>
            <fieldset className="qms-authz-checklist"><legend>People</legend>{people.filter((item) => item.workforce_status === "Active").map((item) => <label key={item.key}><input type="checkbox" checked={batchPeople.includes(item.key)} onChange={(event) => setBatchPeople((current) => event.target.checked ? [...current, item.key] : current.filter((value) => value !== item.key))} /> <span>{item.name}</span></label>)}</fieldset>
            <label>Nomination reason<textarea required rows={4} value={batchReason} onChange={(event) => setBatchReason(event.target.value)} /></label>
            <div className="qms-authz-actions"><button type="button" className="qms-authz-button qms-authz-button--ghost" onClick={() => setBatchOpen(false)}>Cancel</button><button className="qms-authz-button" disabled={busy || !batchPeople.length}>Create {batchPeople.length || ""} case{batchPeople.length === 1 ? "" : "s"}</button></div>
          </form>
        </div>
      ) : null}

      {reviewOpen ? (
        <div className="qms-authz-modal" role="dialog" aria-modal="true" aria-label="Record periodic authorization review">
          <form className="qms-authz-modal__panel" onSubmit={(event) => void submitReview(event)}>
            <div className="qms-authz-modal__header"><h2>Record periodic review</h2><button type="button" onClick={() => setReviewOpen(false)}><XCircle size={20} /></button></div>
            <p><strong>Reviewer:</strong> {actorName}</p>
            <label>Authorization<select required value={reviewAuthorization} onChange={(event) => setReviewAuthorization(event.target.value)}><option value="">Select active authorization</option>{authorizations.filter((item) => ["ACTIVE", "SUSPENDED"].includes(item.status)).map((item) => <option key={item.key} value={item.key}>{item.person} — {item.authorization}</option>)}</select></label>
            <label>Outcome<select value={reviewOutcome} onChange={(event) => setReviewOutcome(event.target.value as typeof reviewOutcome)}><option value="CONTINUE">Continue</option><option value="CONTINUE_WITH_CONDITIONS">Continue with conditions</option><option value="REQUIRES_ACTION">Requires action</option><option value="SUSPEND">Suspend</option><option value="REVOKE">Revoke</option></select></label>
            <label>Next review due<input type="date" value={reviewNextDue} onChange={(event) => setReviewNextDue(event.target.value)} /></label>
            <label>Review reason<textarea required rows={4} value={reviewReason} onChange={(event) => setReviewReason(event.target.value)} /></label>
            <label>Evidence / controlled references<textarea rows={3} value={reviewEvidenceReferences} onChange={(event) => setReviewEvidenceReferences(event.target.value)} placeholder="One business reference per line" /></label>
            <label>Review notes<textarea rows={3} value={reviewNotes} onChange={(event) => setReviewNotes(event.target.value)} /></label>
            <div className="qms-authz-actions"><button type="button" className="qms-authz-button qms-authz-button--ghost" onClick={() => setReviewOpen(false)}>Cancel</button><button className="qms-authz-button" disabled={busy}>Record review</button></div>
          </form>
        </div>
      ) : null}

      {exemptionOpen && canExempt && exemptionAuthorization ? (
        <div className="qms-authz-modal" role="dialog" aria-modal="true" aria-label="Controlled exemption for active authorization">
          <div className="qms-authz-modal__panel">
            <div className="qms-authz-modal__header"><h2>Controlled Exemption / Conditional Authorization</h2><button type="button" onClick={() => { setExemptionOpen(false); setExemptionAuthorization(null); }}><XCircle size={20} /></button></div>
            <p><strong>{exemptionAuthorization.person || personDetail?.person.name}</strong> · {exemptionAuthorization.authorization}</p>
            <div className="qms-authz-decision-context"><span><strong>Approving authority:</strong> {actorName}</span></div>
            <div className="qms-authz-form-grid">
              <label>Missing criterion<input value={exemptionCriterion} onChange={(event) => setExemptionCriterion(event.target.value)} /></label>
              <label>Effective<input type="date" value={exemptionEffective} onChange={(event) => setExemptionEffective(event.target.value)} /></label>
              <label>Expires<input type="date" value={exemptionExpiry} onChange={(event) => setExemptionExpiry(event.target.value)} /></label>
              <label className="span-2">Why normal compliance is not currently possible<textarea value={exemptionReason} onChange={(event) => setExemptionReason(event.target.value)} rows={3} /></label>
              <label className="span-2">Equivalent evidence, one controlled reference per line<textarea value={exemptionEquivalentEvidence} onChange={(event) => setExemptionEquivalentEvidence(event.target.value)} rows={3} /></label>
              <label className="qms-authz-checkbox span-2"><input type="checkbox" checked={exemptionSupervisionRequired} onChange={(event) => setExemptionSupervisionRequired(event.target.checked)} /> Supervision required</label>
              {exemptionSupervisionRequired ? <label className="span-2">Supervisor<select value={exemptionSupervisor} onChange={(event) => setExemptionSupervisor(event.target.value)}><option value="">Select supervisor</option>{people.filter((item) => item.workforce_status === "Active").map((item) => <option value={item.key} key={item.key}>{item.name}</option>)}</select></label> : null}
              <label className="span-2">Operating conditions, one per line<textarea value={exemptionConditions} onChange={(event) => setExemptionConditions(event.target.value)} rows={3} /></label>
              <label className="span-2">Limitations, one per line<textarea value={exemptionLimitations} onChange={(event) => setExemptionLimitations(event.target.value)} rows={3} /></label>
            </div>
            <div className="qms-authz-actions">
              <button type="button" className="qms-authz-button qms-authz-button--ghost" onClick={() => { setExemptionOpen(false); setExemptionAuthorization(null); }}>Cancel</button>
              <button type="button" className="qms-authz-button" onClick={() => void approveExemption()} disabled={busy}>Approve controlled exemption</button>
            </div>
          </div>
        </div>
      ) : null}

      {lifecycleOpen && lifecycleAuthorization ? (
        <div className="qms-authz-modal" role="dialog" aria-modal="true" aria-label="Authorization lifecycle decision">
          <form className="qms-authz-modal__panel" onSubmit={(event) => void submitLifecycle(event)}>
            <div className="qms-authz-modal__header"><h2>{human(lifecycleDecision)} authorization</h2><button type="button" onClick={() => setLifecycleOpen(false)}><XCircle size={20} /></button></div>
            <p><strong>{lifecycleAuthorization.person}</strong> · {lifecycleAuthorization.authorization}</p>
            <div className="qms-authz-decision-context">
              <span><strong>Decision authority:</strong> {actorName}</span>
              <span><strong>Current status:</strong> {human(lifecycleAuthorization.status)}</span>
            </div>
            {lifecycleAuthorization.readiness?.affected_assignments?.length ? (
              <ul className="qms-authz-assignment-impact">
                {lifecycleAuthorization.readiness.affected_assignments.map((item, index) => (
                  <li key={`${item.reference || item.title}-${index}`}>
                    {item.reference || "Audit"} · {item.title || "Scheduled audit"} · {item.role || "Assigned role"}
                  </li>
                ))}
              </ul>
            ) : null}
            <label>Effective date<input required type="date" value={lifecycleDate} onChange={(event) => setLifecycleDate(event.target.value)} /></label>
            {["RENEW", "REINSTATE"].includes(lifecycleDecision) ? <label>Expires<input type="date" value={lifecycleExpiry} onChange={(event) => setLifecycleExpiry(event.target.value)} /></label> : null}
            <label>Next review due<input type="date" value={lifecycleReviewDue} onChange={(event) => setLifecycleReviewDue(event.target.value)} /></label>
            <label>Decision reason<textarea required rows={4} value={lifecycleReason} onChange={(event) => setLifecycleReason(event.target.value)} /></label>
            <label>Evidence / controlled references<textarea rows={3} value={lifecycleEvidenceReferences} onChange={(event) => setLifecycleEvidenceReferences(event.target.value)} placeholder="One business reference per line" /></label>
            <div className="qms-authz-actions"><button type="button" className="qms-authz-button qms-authz-button--ghost" onClick={() => setLifecycleOpen(false)}>Cancel</button><button className={`qms-authz-button ${lifecycleDecision === "REVOKE" ? "qms-authz-button--danger" : ""}`} disabled={busy}>{human(lifecycleDecision)}</button></div>
          </form>
        </div>
      ) : null}

      {ruleOpen && canManagePolicy ? (
        <div className="qms-authz-modal" role="dialog" aria-modal="true" aria-label="Authorization policy">
          <form className="qms-authz-modal__panel" onSubmit={(event) => void saveRule(event)}>
            <div className="qms-authz-modal__header"><h2>{editingRule ? "Edit authorization policy" : "New authorization policy"}</h2><button type="button" onClick={() => setRuleOpen(false)}><XCircle size={20} /></button></div>
            <label>Title<input required value={ruleTitle} onChange={(event) => setRuleTitle(event.target.value)} /></label>
            {!editingRule ? <label>Code<input required value={ruleCode} onChange={(event) => setRuleCode(event.target.value)} placeholder="AUDITOR_SPECIALIST" /></label> : null}
            {!editingRule ? <label>Type<select value={ruleType} onChange={(event) => setRuleType(event.target.value as typeof ruleType)}><option value="AUDITOR">Auditor</option><option value="LEAD_AUDITOR">Lead Auditor</option><option value="QUALITY_INSPECTOR">Quality Assurance Inspector</option><option value="AUTHORIZATION_REVIEWER">Authorization Reviewer</option><option value="CUSTOM">Custom</option></select></label> : null}
            <label>Description<textarea rows={3} value={ruleDescription} onChange={(event) => setRuleDescription(event.target.value)} /></label>
            <label>Required Training course codes<input value={ruleTraining} onChange={(event) => setRuleTraining(event.target.value)} placeholder="QMS-INIT, QMS-REF, QMS-ADMIN" /><small>Course recurrence and validity are controlled in Training, not here.</small></label>
            <label className="qms-authz-checkbox"><input type="checkbox" checked={ruleIndependence} onChange={(event) => setRuleIndependence(event.target.checked)} /> Independence required at audit assignment</label>
            {ruleType === "AUDITOR" ? <label className="qms-authz-checkbox"><input type="checkbox" checked={ruleDevelopmental} onChange={(event) => setRuleDevelopmental(event.target.checked)} /> Supervised Observer / Trainee authorization</label> : null}
            <div className="qms-authz-actions"><button type="button" className="qms-authz-button qms-authz-button--ghost" onClick={() => setRuleOpen(false)}>Cancel</button><button className="qms-authz-button" disabled={busy}>Save policy</button></div>
          </form>
        </div>
      ) : null}
    </section>
  );
};

export default QmsPeoplePage;
