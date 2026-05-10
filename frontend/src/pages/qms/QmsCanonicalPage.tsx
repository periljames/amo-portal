// src/pages/qms/QmsCanonicalPage.tsx
import React, { useCallback, useEffect, useMemo, useRef, useState } from "react";
import { Link, NavLink, Navigate, useLocation, useNavigate, useParams, useSearchParams } from "react-router-dom";
import {
  Activity,
  AlertTriangle,
  Archive,
  ArrowRight,
  BarChart3,
  BookOpen,
  CalendarDays,
  CheckCircle2,
  ClipboardCheck,
  ClipboardList,
  FileSearch,
  FileText,
  Gauge,
  Inbox,
  Layers3,
  ListChecks,
  Plus,
  RefreshCw,
  Search,
  Settings,
  ShieldCheck,
  SlidersHorizontal,
  Users,
  Wrench,
} from "lucide-react";
import DepartmentLayout from "../../components/Layout/DepartmentLayout";
import PageHeader from "../../components/shared/PageHeader";
import SectionCard from "../../components/shared/SectionCard";
import InlineError from "../../components/shared/InlineError";
import Button from "../../components/UI/Button";
import { isPlatformSuperuser } from "../../app/routeGuards";
import { apiRequest, qmsPath } from "../../services/apiClient";
import { getQmsDashboard } from "../../services/qmsDashboard";
import type { QmsDashboardResponse } from "../../types/qms";
import "../../styles/qms-canonical.css";

type ModuleCategory = "command" | "assurance" | "control" | "archive";
type ModuleMode = "live" | "workflow" | "register" | "configuration";
type LoadState = "idle" | "loading" | "ready" | "error";
type QmsRow = Record<string, unknown>;

type QmsAction = {
  label: string;
  path: string;
  tone?: "default" | "attention" | "success" | "warning";
  description?: string;
};

type LifecycleStep = {
  label: string;
  path: string;
  description: string;
};

type ModuleMeta = {
  key: string;
  route: string;
  title: string;
  shortTitle: string;
  subtitle: string;
  category: ModuleCategory;
  mode: ModuleMode;
  icon: React.ComponentType<{ size?: number; className?: string }>;
  defaultView: string;
  sourceLabel: string;
  columns: string[];
  primary: QmsAction;
  actions: QmsAction[];
  taskHint: string;
  createEnabled?: boolean;
  lifecycle: LifecycleStep[];
  rowRoute?: (amoCode: string, row: QmsRow) => string | null;
};

type QmsModuleResponse = {
  module?: string;
  view?: string;
  table?: string;
  record_id?: string | null;
  tenant?: { amo_code?: string; amo_id?: string };
  items?: QmsRow[];
  columns?: string[];
  limit?: number;
  offset?: number;
  next_offset?: number | null;
  has_more?: boolean;
  table_missing?: boolean;
  warning?: string | null;
  trace_id?: string;
  elapsed_ms?: number;
  applied_filters?: Record<string, string>;
};

type CreateDraft = {
  title: string;
  status: string;
  due_date: string;
  owner_user_id: string;
  description: string;
};

const MODULE_GROUPS: Record<ModuleCategory, { title: string; subtitle: string }> = {
  command: { title: "Command", subtitle: "Daily queue, calendar, and live exposure." },
  assurance: { title: "Assurance", subtitle: "Audit, CAR, finding, risk, and change workflows." },
  control: { title: "Control", subtitle: "Documents, competence, suppliers, calibration, and external inputs." },
  archive: { title: "Reporting", subtitle: "Management review, reports, evidence, settings, and retention." },
};

function idFromRow(row: QmsRow): string | null {
  const value = row.id ?? row.uuid ?? row.record_id;
  return value == null ? null : String(value);
}

function detailRoute(route: string, amoCode: string, row: QmsRow): string | null {
  const id = idFromRow(row);
  return id ? `/maintenance/${amoCode}/qms/${route}/${id}/overview` : null;
}

const QMS_MODULES: ModuleMeta[] = [
  {
    key: "cockpit",
    route: "",
    title: "QMS Command Centre",
    shortTitle: "Cockpit",
    subtitle: "One operational surface for open work, due items, audit status, CAR closure, reporting, and archive readiness.",
    category: "command",
    mode: "live",
    icon: Gauge,
    defaultView: "dashboard",
    sourceLabel: "Dashboard counters",
    columns: ["title", "status", "due_date", "updated_at"],
    primary: { label: "Command", path: "" },
    actions: [
      { label: "My work", path: "inbox/assigned-to-me" },
      { label: "Calendar", path: "calendar/list" },
      { label: "Overdue CARs", path: "cars/overdue", tone: "attention" },
      { label: "Reports", path: "reports/executive-dashboard" },
    ],
    taskHint: "Start here. It compresses the old Quality and QMS surfaces into one controlled operating cockpit.",
    lifecycle: [
      { label: "Open", path: "inbox/assigned-to-me", description: "Assigned work and unread decisions." },
      { label: "Plan", path: "audits/schedule", description: "Audit, review, and due date planning." },
      { label: "Execute", path: "audits/dashboard", description: "Fieldwork, evidence, and findings." },
      { label: "Correct", path: "cars/awaiting-auditee", description: "CAR response and implementation." },
      { label: "Verify", path: "cars/awaiting-quality-review", description: "Quality review and effectiveness checks." },
      { label: "Report", path: "reports/executive-dashboard", description: "Performance, trends, and readiness." },
      { label: "Archive", path: "evidence-vault/immutable-archive", description: "Evidence packs and retention." },
    ],
  },
  {
    key: "inbox",
    route: "inbox",
    title: "My QMS Work",
    shortTitle: "My work",
    subtitle: "Assigned notifications, approval decisions, overdue work, watched records, and completed items.",
    category: "command",
    mode: "live",
    icon: Inbox,
    defaultView: "assigned-to-me",
    sourceLabel: "Notification queue",
    columns: ["message", "severity", "created_at", "read_at"],
    primary: { label: "Assigned", path: "inbox/assigned-to-me" },
    actions: [
      { label: "Approvals", path: "inbox/approvals" },
      { label: "Overdue", path: "inbox/overdue", tone: "attention" },
      { label: "Watching", path: "inbox/watching" },
      { label: "Completed", path: "inbox/completed", tone: "success" },
    ],
    taskHint: "Use this as the shortest path to work that needs your action.",
    lifecycle: [
      { label: "Receive", path: "inbox/assigned-to-me", description: "New tasks and notices." },
      { label: "Decide", path: "inbox/approvals", description: "Approvals pending your action." },
      { label: "Escalate", path: "inbox/overdue", description: "Late work requiring intervention." },
      { label: "Monitor", path: "inbox/watching", description: "Watched records." },
      { label: "Done", path: "inbox/completed", description: "Closed work trail." },
    ],
  },
  {
    key: "calendar",
    route: "calendar",
    title: "QMS Calendar",
    shortTitle: "Calendar",
    subtitle: "Audit dates, CAR due dates, training expiries, review dates, and regulatory commitments in one QMS calendar.",
    category: "command",
    mode: "live",
    icon: CalendarDays,
    defaultView: "list",
    sourceLabel: "Calendar events",
    columns: ["date", "title", "event_type", "module", "entity_type"],
    primary: { label: "List", path: "calendar/list" },
    actions: [
      { label: "Audits", path: "calendar/audits" },
      { label: "CARs", path: "calendar/cars" },
      { label: "Training", path: "calendar/training" },
      { label: "Reviews", path: "calendar/management-review" },
    ],
    taskHint: "Use this to stop deadlines from living in separate pages.",
    lifecycle: [
      { label: "Schedule", path: "audits/schedule", description: "Audit programme and due dates." },
      { label: "Warn", path: "calendar/cars", description: "Corrective actions due soon." },
      { label: "Renew", path: "calendar/training", description: "Training and competence expiries." },
      { label: "Review", path: "management-review/meetings", description: "Management review cycle." },
    ],
  },
  {
    key: "audits",
    route: "audits",
    title: "Audits and Inspections",
    shortTitle: "Audits",
    subtitle: "Programme, schedule, checklists, fieldwork, reports, findings, CARs, follow-up, and archive.",
    category: "assurance",
    mode: "workflow",
    icon: ClipboardCheck,
    defaultView: "dashboard",
    sourceLabel: "Audit register",
    columns: ["audit_ref", "title", "kind", "status", "planned_start", "planned_end", "lead_auditor_user_id"],
    primary: { label: "Dashboard", path: "audits/dashboard" },
    actions: [
      { label: "Programme", path: "audits/program" },
      { label: "Schedule", path: "audits/schedule" },
      { label: "Checklists", path: "audits/checklists" },
      { label: "Reports", path: "audits/reports" },
      { label: "New", path: "audits/new", tone: "success" },
    ],
    taskHint: "Run the full audit lifecycle without jumping into a separate legacy quality area.",
    createEnabled: true,
    lifecycle: [
      { label: "Programme", path: "audits/program", description: "Annual and risk-based audit programme." },
      { label: "Schedule", path: "audits/schedule", description: "Audit dates, scope, and team." },
      { label: "Prepare", path: "audits/templates", description: "Templates, notices, and checklists." },
      { label: "Fieldwork", path: "audits/dashboard", description: "Execution, evidence, and observations." },
      { label: "Findings", path: "findings/register", description: "Classify and link findings." },
      { label: "Closeout", path: "cars/register", description: "CAR follow-up and closure." },
      { label: "Archive", path: "evidence-vault/audit-packages", description: "Audit pack and immutable record." },
    ],
    rowRoute: (amoCode, row) => detailRoute("audits", amoCode, row),
  },
  {
    key: "findings",
    route: "findings",
    title: "Findings Register",
    shortTitle: "Findings",
    subtitle: "Finding statements, objective evidence, severity, source, linked CARs, trends, and closeout context.",
    category: "assurance",
    mode: "register",
    icon: ClipboardList,
    defaultView: "register",
    sourceLabel: "Findings",
    columns: ["finding_ref", "title", "description", "severity", "status", "created_at", "closed_at"],
    primary: { label: "Register", path: "findings/register" },
    actions: [
      { label: "By process", path: "findings/by-process" },
      { label: "By severity", path: "findings/by-severity" },
      { label: "Trends", path: "findings/trends" },
      { label: "New", path: "findings/new", tone: "success" },
    ],
    taskHint: "Keep findings evidence-based and linked to the audit, process, risk, document, and corrective action.",
    createEnabled: true,
    lifecycle: [
      { label: "Capture", path: "findings/new", description: "Condition and objective evidence." },
      { label: "Classify", path: "findings/by-severity", description: "Severity and source." },
      { label: "Link", path: "findings/linked-cars", description: "CAR and process links." },
      { label: "Trend", path: "findings/trends", description: "Recurring issues." },
    ],
    rowRoute: (amoCode, row) => detailRoute("findings", amoCode, row),
  },
  {
    key: "cars",
    route: "cars",
    title: "CAR and CAPA",
    shortTitle: "CAR / CAPA",
    subtitle: "Corrective action requests, auditee responses, root cause, implementation evidence, review, effectiveness, and closure.",
    category: "assurance",
    mode: "workflow",
    icon: ListChecks,
    defaultView: "register",
    sourceLabel: "CAR register",
    columns: ["car_number", "title", "status", "due_date", "assigned_to_user_id", "updated_at"],
    primary: { label: "Register", path: "cars/register" },
    actions: [
      { label: "Overdue", path: "cars/overdue", tone: "attention" },
      { label: "Due soon", path: "cars/due-soon", tone: "warning" },
      { label: "Auditee", path: "cars/awaiting-auditee" },
      { label: "Quality review", path: "cars/awaiting-quality-review" },
      { label: "Closed", path: "cars/closed", tone: "success" },
    ],
    taskHint: "Move each CAR from issue to evidence-backed closure with clear owner, due date, and verification state.",
    createEnabled: true,
    lifecycle: [
      { label: "Issue", path: "cars/register", description: "CAR issued from finding or event." },
      { label: "Contain", path: "cars/awaiting-auditee", description: "Auditee response and containment." },
      { label: "Analyse", path: "cars/awaiting-auditee", description: "Root cause and action plan." },
      { label: "Implement", path: "cars/due-soon", description: "Evidence upload and tracking." },
      { label: "Verify", path: "cars/awaiting-quality-review", description: "Quality review and effectiveness." },
      { label: "Close", path: "cars/closed", description: "Closure record and archive." },
    ],
    rowRoute: (amoCode, row) => detailRoute("cars", amoCode, row),
  },
  {
    key: "risk",
    route: "risk",
    title: "Risk and Opportunities",
    shortTitle: "Risk",
    subtitle: "Risk register, opportunities, controls, treatment plans, linked audits, linked findings, and trends.",
    category: "assurance",
    mode: "register",
    icon: ShieldCheck,
    defaultView: "register",
    sourceLabel: "Risk register",
    columns: ["title", "status", "severity", "owner_user_id", "due_date", "updated_at"],
    primary: { label: "Register", path: "risk/register" },
    actions: [
      { label: "Matrix", path: "risk/risk-matrix" },
      { label: "Opportunities", path: "risk/opportunities" },
      { label: "Treatment", path: "risk/treatment-plans" },
      { label: "Trends", path: "risk/trends" },
    ],
    taskHint: "Tie risks and opportunities to process ownership, audits, findings, objectives, and review actions.",
    createEnabled: true,
    lifecycle: [
      { label: "Identify", path: "risk/register", description: "Risk or opportunity capture." },
      { label: "Assess", path: "risk/risk-matrix", description: "Likelihood and consequence." },
      { label: "Treat", path: "risk/treatment-plans", description: "Controls and actions." },
      { label: "Review", path: "management-review/actions", description: "Management review." },
    ],
    rowRoute: (amoCode, row) => detailRoute("risk", amoCode, row),
  },
  {
    key: "change-control",
    route: "change-control",
    title: "Change Control",
    shortTitle: "Change",
    subtitle: "Change requests, impact assessment, risk assessment, approvals, implementation, and post-change review.",
    category: "assurance",
    mode: "workflow",
    icon: SlidersHorizontal,
    defaultView: "register",
    sourceLabel: "Change register",
    columns: ["title", "status", "owner_user_id", "due_date", "updated_at"],
    primary: { label: "Register", path: "change-control/register" },
    actions: [
      { label: "Pending", path: "change-control/pending-approval", tone: "warning" },
      { label: "Implemented", path: "change-control/implemented", tone: "success" },
      { label: "Rejected", path: "change-control/rejected", tone: "attention" },
      { label: "New", path: "change-control/new", tone: "success" },
    ],
    taskHint: "Route change decisions through impact, risk, approval, implementation, and post-implementation checks.",
    createEnabled: true,
    lifecycle: [
      { label: "Request", path: "change-control/new", description: "Change proposal." },
      { label: "Assess", path: "change-control/register", description: "Impact and risk." },
      { label: "Approve", path: "change-control/pending-approval", description: "Approval queue." },
      { label: "Implement", path: "change-control/implemented", description: "Implementation evidence." },
      { label: "Review", path: "change-control/implemented", description: "Post-change review." },
    ],
    rowRoute: (amoCode, row) => detailRoute("change-control", amoCode, row),
  },
  {
    key: "system",
    route: "system",
    title: "System and Processes",
    shortTitle: "System",
    subtitle: "QMS scope, process map, owners, objectives, risks, opportunities, and process performance.",
    category: "control",
    mode: "configuration",
    icon: Layers3,
    defaultView: "processes",
    sourceLabel: "Process register",
    columns: ["title", "name", "status", "owner_user_id", "updated_at"],
    primary: { label: "Processes", path: "system/processes" },
    actions: [
      { label: "Scope", path: "system/qms-scope" },
      { label: "Objectives", path: "system/quality-objectives" },
      { label: "Risks", path: "system/risk-register" },
      { label: "Opportunities", path: "system/opportunities" },
    ],
    taskHint: "Maintain the process backbone that links documents, risks, audits, KPIs, and review outputs.",
    createEnabled: true,
    lifecycle: [
      { label: "Define", path: "system/qms-scope", description: "Scope and context." },
      { label: "Map", path: "system/processes", description: "Process ownership." },
      { label: "Control", path: "system/risk-register", description: "Risks and opportunities." },
      { label: "Measure", path: "system/quality-objectives", description: "Objectives and KPIs." },
    ],
    rowRoute: (amoCode, row) => detailRoute("system/processes", amoCode, row),
  },
  {
    key: "documents",
    route: "documents",
    title: "Controlled Documents",
    shortTitle: "Documents",
    subtitle: "Manuals, procedures, forms, approval letters, document changes, distribution, obsolete control, and archive trail.",
    category: "control",
    mode: "workflow",
    icon: FileText,
    defaultView: "library",
    sourceLabel: "Document library",
    columns: ["doc_code", "title", "name", "doc_type", "status", "effective_date", "updated_at"],
    primary: { label: "Library", path: "documents/library" },
    actions: [
      { label: "Change requests", path: "documents/change-requests" },
      { label: "Approvals", path: "documents/approvals" },
      { label: "Distribution", path: "documents/distribution" },
      { label: "Obsolete", path: "documents/obsolete", tone: "warning" },
    ],
    taskHint: "Keep controlled documents inside QMS instead of running a separate document-control navigation branch.",
    createEnabled: true,
    lifecycle: [
      { label: "Draft", path: "documents/library", description: "Create or revise document." },
      { label: "Review", path: "documents/change-requests", description: "Change request and impact." },
      { label: "Approve", path: "documents/approvals", description: "Approval evidence." },
      { label: "Distribute", path: "documents/distribution", description: "Controlled distribution." },
      { label: "Archive", path: "documents/obsolete", description: "Obsolete control." },
    ],
    rowRoute: (amoCode, row) => detailRoute("documents", amoCode, row),
  },
  {
    key: "training-competence",
    route: "training-competence",
    title: "Training and Competence",
    shortTitle: "Competence",
    subtitle: "Training records, personnel competence, courses, requirements, matrix, evaluations, expiries, and reports.",
    category: "control",
    mode: "live",
    icon: Users,
    defaultView: "dashboard",
    sourceLabel: "Training records",
    columns: ["user_id", "course_id", "status", "valid_until", "updated_at"],
    primary: { label: "Dashboard", path: "training-competence/dashboard" },
    actions: [
      { label: "People", path: "training-competence/people" },
      { label: "Courses", path: "training-competence/courses" },
      { label: "Matrix", path: "training-competence/matrix" },
      { label: "Overdue", path: "training-competence/overdue", tone: "attention" },
    ],
    taskHint: "Connect competence status to the same QMS calendar, audit evidence, and reporting surfaces.",
    lifecycle: [
      { label: "Assign", path: "training-competence/requirements", description: "Required training." },
      { label: "Complete", path: "training-competence/people", description: "Personnel history." },
      { label: "Monitor", path: "training-competence/matrix", description: "Competence matrix." },
      { label: "Renew", path: "training-competence/overdue", description: "Due and overdue records." },
      { label: "Report", path: "training-competence/reports", description: "Compliance reports." },
    ],
  },
  {
    key: "suppliers",
    route: "suppliers",
    title: "Suppliers",
    shortTitle: "Suppliers",
    subtitle: "Approved suppliers, approvals, scope, evaluations, supplier audits, findings, documents, and trends.",
    category: "control",
    mode: "register",
    icon: BookOpen,
    defaultView: "approved-list",
    sourceLabel: "Supplier register",
    columns: ["name", "status", "scope", "due_date", "updated_at"],
    primary: { label: "Approved list", path: "suppliers/approved-list" },
    actions: [
      { label: "Evaluations", path: "suppliers/evaluations" },
      { label: "Audits", path: "suppliers/supplier-audits" },
      { label: "Findings", path: "suppliers/supplier-findings" },
      { label: "Expired", path: "suppliers/expired-approvals", tone: "warning" },
    ],
    taskHint: "Manage supplier approval evidence and supplier findings in the same QMS closeout model.",
    lifecycle: [
      { label: "Approve", path: "suppliers/approved-list", description: "Supplier listing." },
      { label: "Evaluate", path: "suppliers/evaluations", description: "Performance review." },
      { label: "Audit", path: "suppliers/supplier-audits", description: "Supplier audit." },
      { label: "Close", path: "suppliers/supplier-findings", description: "Findings and actions." },
    ],
  },
  {
    key: "equipment-calibration",
    route: "equipment-calibration",
    title: "Equipment and Calibration",
    shortTitle: "Calibration",
    subtitle: "Equipment register, calibration history, certificates, out-of-tolerance events, due soon, overdue, and reports.",
    category: "control",
    mode: "register",
    icon: Wrench,
    defaultView: "register",
    sourceLabel: "Equipment register",
    columns: ["name", "title", "status", "due_date", "updated_at"],
    primary: { label: "Register", path: "equipment-calibration/register" },
    actions: [
      { label: "Due soon", path: "equipment-calibration/due-soon", tone: "warning" },
      { label: "Overdue", path: "equipment-calibration/overdue", tone: "attention" },
      { label: "Certificates", path: "equipment-calibration/certificates" },
      { label: "Reports", path: "equipment-calibration/reports" },
    ],
    taskHint: "Make calibration due dates visible in QMS instead of hidden in isolated equipment screens.",
    lifecycle: [
      { label: "Register", path: "equipment-calibration/register", description: "Controlled equipment." },
      { label: "Calibrate", path: "equipment-calibration/calibration-history", description: "Calibration records." },
      { label: "Certify", path: "equipment-calibration/certificates", description: "Certificates." },
      { label: "Escalate", path: "equipment-calibration/out-of-tolerance", description: "Out-of-tolerance events." },
    ],
  },
  {
    key: "external-interface",
    route: "external-interface",
    title: "External Interface",
    shortTitle: "External",
    subtitle: "Regulator findings, customer complaints, customer feedback, authority correspondence, responses, and commitments.",
    category: "control",
    mode: "workflow",
    icon: FileSearch,
    defaultView: "regulator-findings",
    sourceLabel: "External records",
    columns: ["title", "status", "source_type", "due_date", "updated_at"],
    primary: { label: "Regulator", path: "external-interface/regulator-findings" },
    actions: [
      { label: "Complaints", path: "external-interface/customer-complaints" },
      { label: "Feedback", path: "external-interface/customer-feedback" },
      { label: "Correspondence", path: "external-interface/authority-correspondence" },
      { label: "Commitments", path: "external-interface/commitments" },
    ],
    taskHint: "Capture external obligations and route them into QMS actions, evidence, and reporting.",
    lifecycle: [
      { label: "Receive", path: "external-interface/regulator-findings", description: "External input." },
      { label: "Assign", path: "external-interface/commitments", description: "Commitments and owner." },
      { label: "Respond", path: "external-interface/responses", description: "Response control." },
      { label: "Close", path: "cars/register", description: "Linked corrective action." },
    ],
  },
  {
    key: "management-review",
    route: "management-review",
    title: "Management Review",
    shortTitle: "Review",
    subtitle: "Review meetings, inputs, minutes, decisions, actions, attachments, approvals, and reports.",
    category: "archive",
    mode: "workflow",
    icon: Users,
    defaultView: "dashboard",
    sourceLabel: "Management review",
    columns: ["title", "status", "meeting_date", "due_date", "updated_at"],
    primary: { label: "Dashboard", path: "management-review/dashboard" },
    actions: [
      { label: "Meetings", path: "management-review/meetings" },
      { label: "Actions", path: "management-review/actions" },
      { label: "Open", path: "management-review/open-actions", tone: "warning" },
      { label: "Closed", path: "management-review/closed-actions", tone: "success" },
    ],
    taskHint: "Pull audit, CAR, risk, supplier, training, and document data into management decisions.",
    lifecycle: [
      { label: "Collect", path: "management-review/dashboard", description: "Inputs and KPIs." },
      { label: "Meet", path: "management-review/meetings", description: "Agenda and minutes." },
      { label: "Decide", path: "management-review/actions", description: "Decisions and actions." },
      { label: "Verify", path: "management-review/open-actions", description: "Open action closeout." },
    ],
  },
  {
    key: "reports",
    route: "reports",
    title: "Reports and Analytics",
    shortTitle: "Reports",
    subtitle: "QMS performance, audit performance, CAR performance, trends, readiness, exports, and custom reporting.",
    category: "archive",
    mode: "live",
    icon: BarChart3,
    defaultView: "executive-dashboard",
    sourceLabel: "Report outputs",
    columns: ["title", "name", "status", "created_at", "updated_at"],
    primary: { label: "Executive", path: "reports/executive-dashboard" },
    actions: [
      { label: "Audits", path: "reports/audit-performance" },
      { label: "CARs", path: "reports/car-performance" },
      { label: "Training", path: "reports/training-compliance" },
      { label: "Exports", path: "reports/exports" },
    ],
    taskHint: "Report from the unified QMS data model instead of separate Quality and QMS pages.",
    lifecycle: [
      { label: "Collect", path: "reports/executive-dashboard", description: "Live metrics." },
      { label: "Analyse", path: "reports/finding-trends", description: "Patterns and trends." },
      { label: "Export", path: "reports/exports", description: "Controlled outputs." },
      { label: "Archive", path: "evidence-vault/immutable-archive", description: "Evidence pack." },
    ],
  },
  {
    key: "evidence-vault",
    route: "evidence-vault",
    title: "Evidence Vault",
    shortTitle: "Evidence",
    subtitle: "Search, audit packages, CAR packages, document approval packages, regulator packages, archive, and retention.",
    category: "archive",
    mode: "register",
    icon: Archive,
    defaultView: "search",
    sourceLabel: "Evidence files",
    columns: ["title", "file_name", "source_type", "status", "created_at", "updated_at"],
    primary: { label: "Search", path: "evidence-vault/search" },
    actions: [
      { label: "Audit packs", path: "evidence-vault/audit-packages" },
      { label: "CAR packs", path: "evidence-vault/car-packages" },
      { label: "Regulator", path: "evidence-vault/regulator-packages" },
      { label: "Archive", path: "evidence-vault/immutable-archive" },
    ],
    taskHint: "Provide one archive for audit-proof evidence and retention management.",
    lifecycle: [
      { label: "Collect", path: "evidence-vault/search", description: "Evidence files." },
      { label: "Package", path: "evidence-vault/audit-packages", description: "Audit and CAR packs." },
      { label: "Lock", path: "evidence-vault/immutable-archive", description: "Immutable archive." },
      { label: "Retain", path: "evidence-vault/retention", description: "Retention rules." },
    ],
  },
  {
    key: "settings",
    route: "settings",
    title: "QMS Settings",
    shortTitle: "Settings",
    subtitle: "Numbering, workflow rules, approvals, roles, notifications, templates, classifications, retention, and integrations.",
    category: "archive",
    mode: "configuration",
    icon: Settings,
    defaultView: "general",
    sourceLabel: "Settings",
    columns: ["name", "title", "status", "updated_at"],
    primary: { label: "General", path: "settings/general" },
    actions: [
      { label: "Numbering", path: "settings/numbering" },
      { label: "Workflow", path: "settings/workflow-rules" },
      { label: "Approvals", path: "settings/approval-matrix" },
      { label: "Audit log", path: "settings/audit-log" },
    ],
    taskHint: "Configure the rules that drive QMS workflow, notifications, and record retention.",
    lifecycle: [
      { label: "Configure", path: "settings/general", description: "Base QMS settings." },
      { label: "Number", path: "settings/numbering", description: "Reference schemes." },
      { label: "Route", path: "settings/workflow-rules", description: "Workflow rules." },
      { label: "Retain", path: "settings/retention-rules", description: "Archive rules." },
    ],
  },
];

const MODULE_BY_ROUTE = Object.fromEntries(QMS_MODULES.filter((module) => module.route).map((module) => [module.route, module])) as Record<string, ModuleMeta>;
const MODULE_BY_KEY = Object.fromEntries(QMS_MODULES.map((module) => [module.key, module])) as Record<string, ModuleMeta>;
const CATEGORIES: ModuleCategory[] = ["command", "assurance", "control", "archive"];
const PAGE_SIZE_OPTIONS = [10, 15, 25, 50];

function routeToUrl(amoCode: string, route: string): string {
  return `/maintenance/${amoCode}/qms${route ? `/${route}` : ""}`;
}

function humanise(value: unknown): string {
  const raw = value == null ? "" : String(value);
  if (!raw) return "—";
  return raw.replaceAll("_", " ").replaceAll("-", " ").replace(/\b\w/g, (char) => char.toUpperCase());
}

function formatValue(value: unknown): string {
  if (value == null || value === "") return "—";
  if (typeof value === "boolean") return value ? "Yes" : "No";
  if (typeof value === "object") {
    const compact = JSON.stringify(value);
    return compact.length > 120 ? `${compact.slice(0, 117)}…` : compact;
  }
  const raw = String(value);
  if (/^\d{4}-\d{2}-\d{2}T/.test(raw)) {
    const date = new Date(raw);
    return Number.isNaN(date.getTime()) ? raw : date.toLocaleString();
  }
  return raw.length > 120 ? `${raw.slice(0, 117)}…` : raw;
}

function counterValue(dashboard: QmsDashboardResponse | null, key: string): number {
  return dashboard?.counters?.[key] ?? 0;
}

function currentQmsParts(pathname: string): string[] {
  const parts = pathname.split("/").filter(Boolean);
  const qmsIndex = parts.indexOf("qms");
  return qmsIndex >= 0 ? parts.slice(qmsIndex + 1) : [];
}

function moduleFromPath(pathname: string): ModuleMeta {
  const first = currentQmsParts(pathname)[0];
  return first && MODULE_BY_ROUTE[first] ? MODULE_BY_ROUTE[first] : MODULE_BY_KEY.cockpit;
}

function viewFromPath(pathname: string, module: ModuleMeta): string {
  if (!module.route) return module.defaultView;
  const parts = currentQmsParts(pathname);
  const afterModule = parts.slice(1);
  const knownViews = new Set([module.defaultView, module.primary.path.split("/").slice(-1)[0], ...module.actions.map((action) => action.path.split("/").slice(-1)[0])].filter(Boolean));
  const view = afterModule.find((part) => knownViews.has(part));
  return view || module.defaultView;
}

function fetchSuffix(module: ModuleMeta, view: string): string {
  if (!module.route) return "dashboard";
  if (view === "default" || !view) return module.route;
  return `${module.route}/${view}`;
}

function statusClass(value: unknown): string {
  const normalized = String(value || "").toUpperCase();
  if (["CLOSED", "COMPLETE", "COMPLETED", "ACTIVE", "APPROVED", "IMPLEMENTED"].includes(normalized)) return "qms-ops-pill qms-ops-pill--success";
  if (["OVERDUE", "REJECTED", "CANCELLED", "FAILED"].includes(normalized)) return "qms-ops-pill qms-ops-pill--danger";
  if (["DRAFT", "PENDING", "PENDING_APPROVAL", "OPEN", "IN_PROGRESS", "AWAITING_AUDITEE", "AWAITING_QUALITY_REVIEW"].includes(normalized)) return "qms-ops-pill qms-ops-pill--warning";
  return "qms-ops-pill";
}

function friendlyError(error: unknown, fallback = "Unable to load this QMS view."): string {
  if (error instanceof Error && error.message) {
    if (/timed out/i.test(error.message)) return `${error.message}. The request was logged in the browser console with the QMS module and endpoint.`;
    if (/failed to fetch|networkerror/i.test(error.message)) return "The QMS API is not reachable. Confirm the backend is running, then retry.";
    return error.message;
  }
  return fallback;
}

function ModuleBadge({ mode }: { mode: ModuleMode }): React.ReactElement {
  return <span className={`qms-ops-mode qms-ops-mode--${mode}`}>{humanise(mode)}</span>;
}

function SignalCards({ amoCode, dashboard }: { amoCode: string; dashboard: QmsDashboardResponse | null }): React.ReactElement {
  const signals = [
    { label: "Open audits", value: counterValue(dashboard, "open_audits"), icon: ClipboardCheck, to: "audits/dashboard" },
    { label: "Overdue CARs", value: counterValue(dashboard, "overdue_cars"), icon: AlertTriangle, to: "cars/overdue", tone: "danger" },
    { label: "CARs due soon", value: counterValue(dashboard, "cars_due_soon"), icon: CalendarDays, to: "cars/due-soon", tone: "warning" },
    { label: "Open findings", value: counterValue(dashboard, "open_findings"), icon: ClipboardList, to: "findings/register" },
    { label: "Draft documents", value: counterValue(dashboard, "draft_documents"), icon: FileText, to: "documents/library" },
    { label: "Expired training", value: counterValue(dashboard, "training_expired_records"), icon: Users, to: "training-competence/overdue", tone: "warning" },
  ];
  return (
    <div className="qms-ops-signal-rail" aria-label="QMS signals">
      {signals.map((item) => {
        const Icon = item.icon;
        return (
          <Link key={item.label} to={routeToUrl(amoCode, item.to)} className={`qms-ops-signal qms-ops-signal--${item.tone || "default"}`}>
            <span className="qms-ops-signal__icon"><Icon size={18} /></span>
            <span className="qms-ops-signal__copy"><strong>{Intl.NumberFormat().format(item.value)}</strong><small>{item.label}</small></span>
          </Link>
        );
      })}
    </div>
  );
}

function ModuleNavigation({ amoCode, activeKey }: { amoCode: string; activeKey: string }): React.ReactElement {
  return (
    <section className="qms-ops-module-strip" aria-label="QMS modules">
      {CATEGORIES.map((category) => {
        const modules = QMS_MODULES.filter((module) => module.category === category);
        const group = MODULE_GROUPS[category];
        return (
          <div key={category} className="qms-ops-module-strip__group">
            <div className="qms-ops-module-strip__group-head">
              <strong>{group.title}</strong>
              <span>{group.subtitle}</span>
            </div>
            <div className="qms-ops-module-strip__rail">
              {modules.map((module) => {
                const Icon = module.icon;
                return (
                  <NavLink key={module.key} to={routeToUrl(amoCode, module.route ? `${module.route}/${module.defaultView}` : "")} end={module.key === "cockpit"} className={`qms-ops-module-card${activeKey === module.key ? " is-active" : ""}`}>
                    <span className="qms-ops-module-card__icon"><Icon size={18} /></span>
                    <span className="qms-ops-module-card__text"><strong>{module.shortTitle}</strong><small>{module.mode}</small></span>
                  </NavLink>
                );
              })}
            </div>
          </div>
        );
      })}
    </section>
  );
}

function ActionTabs({ amoCode, module, currentPath }: { amoCode: string; module: ModuleMeta; currentPath: string }): React.ReactElement {
  const actions = [module.primary, ...module.actions];
  return (
    <div className="qms-ops-action-tabs" role="tablist" aria-label={`${module.shortTitle} views`}>
      {actions.map((action) => {
        const url = routeToUrl(amoCode, action.path);
        const active = currentPath === url || currentPath.startsWith(`${url}/`);
        return (
          <NavLink key={`${action.label}-${action.path}`} to={url} className={`qms-ops-action-tab qms-ops-action-tab--${action.tone || "default"}${active ? " is-active" : ""}`}>
            <span>{action.label}</span>
            <ArrowRight size={14} />
          </NavLink>
        );
      })}
    </div>
  );
}

function LifecycleRunway({ amoCode, steps }: { amoCode: string; steps: LifecycleStep[] }): React.ReactElement {
  return (
    <div className="qms-ops-runway" aria-label="Workflow runway">
      {steps.map((step, index) => (
        <Link key={`${step.label}-${step.path}`} to={routeToUrl(amoCode, step.path)} className="qms-ops-runway__step">
          <span className="qms-ops-runway__index">{index + 1}</span>
          <span className="qms-ops-runway__copy"><strong>{step.label}</strong><small>{step.description}</small></span>
        </Link>
      ))}
    </div>
  );
}

function EmptyRows({ module }: { module: ModuleMeta }): React.ReactElement {
  return (
    <div className="qms-ops-empty-state">
      <CheckCircle2 size={18} />
      <div>
        <strong>No rows in this view</strong>
        <p>{module.taskHint}</p>
      </div>
    </div>
  );
}

function RecordTable({ amoCode, module, rows, response }: { amoCode: string; module: ModuleMeta; rows: QmsRow[]; response: QmsModuleResponse | null }): React.ReactElement {
  const responseColumns = response?.columns || [];
  const columns = useMemo(() => {
    const seen = new Set<string>();
    const list = [...module.columns, ...responseColumns].filter((column) => {
      if (seen.has(column)) return false;
      seen.add(column);
      return rows.some((row) => row[column] != null && row[column] !== "");
    });
    return (list.length ? list : module.columns).slice(0, 7);
  }, [module.columns, responseColumns, rows]);

  if (!rows.length) return <EmptyRows module={module} />;

  return (
    <div className="qms-ops-table-wrap">
      <table className="qms-ops-table">
        <thead>
          <tr>
            {columns.map((column) => <th key={column}>{humanise(column)}</th>)}
            <th>Action</th>
          </tr>
        </thead>
        <tbody>
          {rows.map((row, index) => {
            const rowId = idFromRow(row) || `${index}`;
            const openTo = module.rowRoute?.(amoCode, row) || null;
            return (
              <tr key={rowId}>
                {columns.map((column, colIndex) => {
                  const value = row[column];
                  if (column === "status" || column === "severity") {
                    return <td key={column}><span className={statusClass(value)}>{humanise(value)}</span></td>;
                  }
                  if (colIndex === 0) {
                    return (
                      <td key={column}>
                        <div className="qms-ops-record-title">
                          <strong>{formatValue(value)}</strong>
                          <small>{rowId}</small>
                        </div>
                      </td>
                    );
                  }
                  return <td key={column}>{formatValue(value)}</td>;
                })}
                <td className="qms-ops-table__actions">
                  {openTo ? <Link className="qms-ops-open-link" to={openTo}>Open</Link> : <span className="qms-ops-muted">Inline</span>}
                </td>
              </tr>
            );
          })}
        </tbody>
      </table>
    </div>
  );
}

function CreateRecordPanel({ amoCode, module, view, onCreated }: { amoCode: string; module: ModuleMeta; view: string; onCreated: () => void }): React.ReactElement {
  const [open, setOpen] = useState(false);
  const [saving, setSaving] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [draft, setDraft] = useState<CreateDraft>({ title: "", status: "OPEN", due_date: "", owner_user_id: "", description: "" });

  const submit = async () => {
    if (!draft.title.trim() && !draft.description.trim()) {
      setError("Add at least a title or description before creating a row.");
      return;
    }
    setSaving(true);
    setError(null);
    try {
      await apiRequest(qmsPath(amoCode, fetchSuffix(module, view)), {
        method: "POST",
        body: JSON.stringify({ ...draft, payload: { capture_source: "qms_command_centre", view } }),
        timeoutMs: 12000,
      });
      setDraft({ title: "", status: "OPEN", due_date: "", owner_user_id: "", description: "" });
      setOpen(false);
      onCreated();
    } catch (err) {
      console.error("[QMS] quick capture failed", { module: module.key, view, error: err });
      setError(friendlyError(err, "Quick capture failed."));
    } finally {
      setSaving(false);
    }
  };

  return (
    <SectionCard title="Quick capture" subtitle="Use for simple register rows. Controlled workflows still use the runway." variant="subtle">
      <div className="qms-ops-create-head">
        <span className={module.createEnabled ? "qms-ops-pill qms-ops-pill--success" : "qms-ops-pill"}>{module.createEnabled ? "Enabled" : "Read only"}</span>
        {module.createEnabled ? <Button size="sm" variant="secondary" onClick={() => setOpen((value) => !value)}><Plus size={14} /> {open ? "Close" : "Capture"}</Button> : null}
      </div>
      {open && module.createEnabled ? (
        <div className="qms-ops-create-grid">
          <label><span>Title</span><input value={draft.title} onChange={(event) => setDraft((prev) => ({ ...prev, title: event.target.value }))} /></label>
          <label><span>Status</span><select value={draft.status} onChange={(event) => setDraft((prev) => ({ ...prev, status: event.target.value }))}><option>OPEN</option><option>DRAFT</option><option>PENDING_REVIEW</option><option>CLOSED</option></select></label>
          <label><span>Due date</span><input type="date" value={draft.due_date} onChange={(event) => setDraft((prev) => ({ ...prev, due_date: event.target.value }))} /></label>
          <label><span>Owner user id</span><input value={draft.owner_user_id} onChange={(event) => setDraft((prev) => ({ ...prev, owner_user_id: event.target.value }))} placeholder="Optional" /></label>
          <label className="qms-ops-create-grid__wide"><span>Description</span><textarea rows={3} value={draft.description} onChange={(event) => setDraft((prev) => ({ ...prev, description: event.target.value }))} /></label>
          {error ? <div className="qms-ops-create-grid__wide"><InlineError message={error} /></div> : null}
          <div className="qms-ops-create-grid__wide qms-ops-create-actions">
            <Button variant="secondary" onClick={() => setOpen(false)}>Cancel</Button>
            <Button loading={saving} onClick={submit}>Create row</Button>
          </div>
        </div>
      ) : (
        <p className="qms-ops-muted">Use the workflow runway where a record needs notices, approvals, auditee responses, evidence, or archive packaging.</p>
      )}
    </SectionCard>
  );
}

function LoadingPanel({ label }: { label: string }): React.ReactElement {
  return (
    <div className="qms-ops-loading-card">
      <RefreshCw size={18} />
      <span>{label}</span>
    </div>
  );
}

function WorkspacePanel({
  amoCode,
  module,
  view,
  state,
  data,
  error,
  query,
  statusFilter,
  pageSize,
  onQueryChange,
  onStatusChange,
  onPageSizeChange,
  onRetry,
  onPage,
}: {
  amoCode: string;
  module: ModuleMeta;
  view: string;
  state: LoadState;
  data: QmsModuleResponse | null;
  error: string | null;
  query: string;
  statusFilter: string;
  pageSize: number;
  onQueryChange: (value: string) => void;
  onStatusChange: (value: string) => void;
  onPageSizeChange: (value: number) => void;
  onRetry: () => void;
  onPage: (direction: "next" | "prev") => void;
}): React.ReactElement {
  const rows = data?.items || [];
  const source = data?.table || module.sourceLabel;
  const offset = data?.offset || 0;
  const limit = data?.limit || pageSize;
  const currentPage = Math.floor(offset / limit) + 1;
  return (
    <div className="qms-ops-workspace-grid">
      <SectionCard className="qms-ops-span-2" title={module.title} subtitle={module.subtitle} variant="subtle" actions={<Button variant="secondary" size="sm" onClick={onRetry} loading={state === "loading"}><RefreshCw size={14} /> Refresh</Button>}>
        <div className="qms-ops-workspace-head">
          <div><span>View</span><strong>{humanise(data?.view || view)}</strong></div>
          <div><span>Source</span><strong>{humanise(source)}</strong></div>
          <div><span>Page rows</span><strong>{Intl.NumberFormat().format(rows.length)}</strong></div>
          <div><span>Trace</span><strong>{data?.trace_id || "—"}</strong></div>
          <ModuleBadge mode={module.mode} />
        </div>
        <ActionTabs amoCode={amoCode} module={module} currentPath={window.location.pathname} />
        <div className="qms-ops-filter-bar">
          <label className="qms-ops-search"><Search size={16} /><input value={query} onChange={(event) => onQueryChange(event.target.value)} placeholder="Search this QMS view" /></label>
          <label><span>Status</span><select value={statusFilter} onChange={(event) => onStatusChange(event.target.value)}><option value="">All</option><option value="OPEN">Open</option><option value="IN_PROGRESS">In progress</option><option value="PENDING_REVIEW">Pending review</option><option value="CLOSED">Closed</option><option value="REJECTED">Rejected</option></select></label>
          <label><span>Rows</span><select value={pageSize} onChange={(event) => onPageSizeChange(Number(event.target.value))}>{PAGE_SIZE_OPTIONS.map((value) => <option key={value} value={value}>{value}</option>)}</select></label>
          <span className="qms-ops-pill">Page {currentPage}</span>
        </div>
        {data?.warning ? <div className="qms-ops-warning"><AlertTriangle size={16} /> {data.warning}</div> : null}
        {data?.table_missing ? <div className="qms-ops-warning"><AlertTriangle size={16} /> The configured QMS table is missing. Run the canonical QMS migration for this environment.</div> : null}
        {error ? <InlineError message={error} onAction={onRetry} /> : null}
        {state === "loading" ? <LoadingPanel label={`Loading ${module.sourceLabel.toLowerCase()}...`} /> : null}
        {state !== "loading" && !error ? <RecordTable amoCode={amoCode} module={module} rows={rows} response={data} /> : null}
        <div className="qms-ops-pagination">
          <Button variant="secondary" size="sm" disabled={offset <= 0 || state === "loading"} onClick={() => onPage("prev")}>Previous</Button>
          <span>{data?.elapsed_ms != null ? `${data.elapsed_ms} ms backend` : "Backend timing pending"}</span>
          <Button variant="secondary" size="sm" disabled={!data?.has_more || state === "loading"} onClick={() => onPage("next")}>Next</Button>
        </div>
      </SectionCard>

      <SectionCard title="Workflow runway" subtitle="Stepwise work pans horizontally. Pick the next task without scrolling through dead content." variant="subtle">
        <LifecycleRunway amoCode={amoCode} steps={module.lifecycle} />
      </SectionCard>

      <SectionCard title="Operational purpose" subtitle="Why this item exists in the unified QMS." variant="subtle">
        <div className="qms-ops-purpose-list">
          <span><CheckCircle2 size={16} /> {module.taskHint}</span>
          <span><Activity size={16} /> Uses paginated tenant-scoped backend reads.</span>
          <span><ShieldCheck size={16} /> Browser console receives QMS endpoint, module, view, and error details when a request fails.</span>
        </div>
      </SectionCard>

      <CreateRecordPanel amoCode={amoCode} module={module} view={view} onCreated={onRetry} />
    </div>
  );
}

function CockpitWorkspace({ amoCode, dashboard, loading }: { amoCode: string; dashboard: QmsDashboardResponse | null; loading: boolean }): React.ReactElement {
  return (
    <div className="qms-ops-workspace-grid">
      <SectionCard className="qms-ops-span-2" title="Daily operating sequence" subtitle="One horizontal runway from opening work to reporting and archive." variant="subtle">
        {loading ? <LoadingPanel label="Loading command centre..." /> : null}
        <LifecycleRunway amoCode={amoCode} steps={MODULE_BY_KEY.cockpit.lifecycle} />
      </SectionCard>
      <SectionCard title="Priority queue" subtitle="Backend counters loaded from the tenant QMS dashboard." variant="subtle">
        <div className="qms-ops-priority-list">
          <Link to={routeToUrl(amoCode, "cars/overdue")}><AlertTriangle size={16} /> Overdue CARs <strong>{counterValue(dashboard, "overdue_cars")}</strong></Link>
          <Link to={routeToUrl(amoCode, "audits/schedule")}><CalendarDays size={16} /> Audits due soon <strong>{counterValue(dashboard, "audits_due_soon")}</strong></Link>
          <Link to={routeToUrl(amoCode, "documents/library")}><FileText size={16} /> Draft documents <strong>{counterValue(dashboard, "draft_documents")}</strong></Link>
          <Link to={routeToUrl(amoCode, "training-competence/overdue")}><Users size={16} /> Expired training <strong>{counterValue(dashboard, "training_expired_records")}</strong></Link>
        </div>
      </SectionCard>
      <SectionCard title="Direct actions" subtitle="No separate Quality and QMS surfaces." variant="subtle">
        <ActionTabs amoCode={amoCode} module={MODULE_BY_KEY.cockpit} currentPath={window.location.pathname} />
      </SectionCard>
    </div>
  );
}

export default function QmsCanonicalPage(): React.ReactElement {
  const { amoCode = "UNKNOWN" } = useParams<{ amoCode: string }>();
  const location = useLocation();
  const navigate = useNavigate();
  const [searchParams, setSearchParams] = useSearchParams();
  const cacheRef = useRef<Map<string, QmsModuleResponse>>(new Map());
  const abortRef = useRef<AbortController | null>(null);

  const module = moduleFromPath(location.pathname);
  const view = viewFromPath(location.pathname, module);
  const [dashboard, setDashboard] = useState<QmsDashboardResponse | null>(null);
  const [dashboardState, setDashboardState] = useState<LoadState>("idle");
  const [dashboardError, setDashboardError] = useState<string | null>(null);
  const [moduleData, setModuleData] = useState<QmsModuleResponse | null>(null);
  const [moduleState, setModuleState] = useState<LoadState>("idle");
  const [moduleError, setModuleError] = useState<string | null>(null);

  const query = searchParams.get("q") || "";
  const statusFilter = searchParams.get("status") || "";
  const pageSize = Number(searchParams.get("limit") || 15);
  const offset = Number(searchParams.get("offset") || 0);

  const breadcrumbs = useMemo(() => [
    { label: "Quality", to: `/maintenance/${amoCode}/qms` },
    { label: module.shortTitle },
  ], [amoCode, module.shortTitle]);

  const loadDashboard = useCallback(async () => {
    setDashboardState("loading");
    setDashboardError(null);
    const started = performance.now();
    try {
      const result = await getQmsDashboard(amoCode);
      setDashboard(result);
      setDashboardState("ready");
      console.info("[QMS] dashboard loaded", { amoCode, elapsedMs: Math.round(performance.now() - started) });
    } catch (err) {
      console.error("[QMS] dashboard failed", { amoCode, error: err });
      setDashboard(null);
      setDashboardError(friendlyError(err, "Unable to load QMS dashboard."));
      setDashboardState("error");
    }
  }, [amoCode]);

  const buildModulePath = useCallback((nextOffset = offset) => {
    const params = new URLSearchParams();
    params.set("limit", String(pageSize));
    params.set("offset", String(Math.max(0, nextOffset)));
    if (query.trim()) params.set("q", query.trim());
    if (statusFilter) params.set("status", statusFilter);
    return `${qmsPath(amoCode, fetchSuffix(module, view))}?${params.toString()}`;
  }, [amoCode, module, offset, pageSize, query, statusFilter, view]);

  const loadModule = useCallback(async ({ force = false, nextOffset = offset }: { force?: boolean; nextOffset?: number } = {}) => {
    if (!module.route) {
      setModuleData(null);
      setModuleState("ready");
      setModuleError(null);
      return;
    }
    const path = buildModulePath(nextOffset);
    const cacheKey = path;
    const cached = cacheRef.current.get(cacheKey);
    if (cached && !force) {
      setModuleData(cached);
      setModuleError(null);
      setModuleState("ready");
      return;
    }
    abortRef.current?.abort(new DOMException("Superseded by a newer QMS request", "AbortError"));
    const controller = new AbortController();
    abortRef.current = controller;
    setModuleState("loading");
    setModuleError(null);
    const started = performance.now();
    console.info("[QMS] module request started", { amoCode, module: module.key, view, path, offset: nextOffset, pageSize, query, statusFilter });
    try {
      const result = await apiRequest<QmsModuleResponse>(path, { timeoutMs: 15000, signal: controller.signal });
      cacheRef.current.set(cacheKey, result);
      setModuleData(result);
      setModuleState("ready");
      console.info("[QMS] module request finished", { amoCode, module: module.key, view, path, rows: result.items?.length || 0, traceId: result.trace_id, backendMs: result.elapsed_ms, elapsedMs: Math.round(performance.now() - started) });
    } catch (err) {
      if (err instanceof DOMException && err.name === "AbortError") return;
      console.error("[QMS] module request failed", { amoCode, module: module.key, view, path, error: err });
      setModuleError(friendlyError(err));
      setModuleState("error");
    }
  }, [amoCode, buildModulePath, module, offset, pageSize, query, statusFilter, view]);

  useEffect(() => {
    void loadDashboard();
  }, [loadDashboard]);

  useEffect(() => {
    void loadModule();
    return () => abortRef.current?.abort(new DOMException("QMS view changed", "AbortError"));
  }, [loadModule]);

  useEffect(() => {
    if (!module.route || moduleState !== "ready") return;
    const nextAction = module.actions[0];
    if (!nextAction) return;
    const timer = window.setTimeout(() => {
      const params = new URLSearchParams({ limit: "10", offset: "0" });
      const prefetchPath = `${qmsPath(amoCode, nextAction.path)}?${params.toString()}`;
      if (cacheRef.current.has(prefetchPath)) return;
      void apiRequest<QmsModuleResponse>(prefetchPath, { timeoutMs: 8000 })
        .then((result) => cacheRef.current.set(prefetchPath, result))
        .catch((err) => console.info("[QMS] background prefetch skipped", { path: prefetchPath, error: err }));
    }, 650);
    return () => window.clearTimeout(timer);
  }, [amoCode, module, moduleState]);

  const setParam = (key: string, value: string) => {
    const next = new URLSearchParams(searchParams);
    if (value) next.set(key, value);
    else next.delete(key);
    if (key !== "offset") next.set("offset", "0");
    setSearchParams(next, { replace: true });
  };

  const refreshAll = () => {
    cacheRef.current.clear();
    void loadDashboard();
    void loadModule({ force: true });
  };

  const page = (direction: "next" | "prev") => {
    const nextOffset = direction === "next" ? (moduleData?.next_offset ?? offset + pageSize) : Math.max(0, offset - pageSize);
    setParam("offset", String(nextOffset));
  };

  if (isPlatformSuperuser()) {
    return <Navigate to="/platform/control" replace />;
  }

  return (
    <DepartmentLayout amoCode={amoCode} activeDepartment="quality">
      <div className="qms-ops-page">
        <PageHeader
          eyebrow="Unified Quality Management System"
          title={module.title}
          subtitle={module.subtitle}
          breadcrumbs={breadcrumbs}
          meta={<ModuleBadge mode={module.mode} />}
          actions={
            <div className="qms-ops-header-actions">
              <Button variant="secondary" onClick={() => navigate(routeToUrl(amoCode, "inbox/assigned-to-me"))}>My work</Button>
              <Button onClick={refreshAll} loading={dashboardState === "loading" || moduleState === "loading"}><RefreshCw size={16} /> Refresh</Button>
            </div>
          }
        />

        {dashboardError ? <InlineError message={dashboardError} onAction={loadDashboard} /> : null}

        <section className="qms-ops-hero">
          <div className="qms-ops-hero__copy">
            <span>Tenant workspace</span>
            <strong>{dashboard?.tenant?.amo_code || amoCode}</strong>
            <p>Quality, QMS, document control, calendar, reporting, feedback, and archive actions now resolve into one canonical operational path.</p>
          </div>
          <SignalCards amoCode={amoCode} dashboard={dashboard} />
        </section>

        <ModuleNavigation amoCode={amoCode} activeKey={module.key} />

        {module.key === "cockpit" ? (
          <CockpitWorkspace amoCode={amoCode} dashboard={dashboard} loading={dashboardState === "loading"} />
        ) : (
          <WorkspacePanel
            amoCode={amoCode}
            module={module}
            view={view}
            state={moduleState}
            data={moduleData}
            error={moduleError}
            query={query}
            statusFilter={statusFilter}
            pageSize={pageSize}
            onQueryChange={(value) => setParam("q", value)}
            onStatusChange={(value) => setParam("status", value)}
            onPageSizeChange={(value) => setParam("limit", String(value))}
            onRetry={() => void loadModule({ force: true })}
            onPage={page}
          />
        )}
      </div>
    </DepartmentLayout>
  );
}
