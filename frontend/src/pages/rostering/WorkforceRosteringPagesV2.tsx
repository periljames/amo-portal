import "./components/roster-setup-refinement.css";

import { lazy, Suspense, type ReactNode } from "react";
import { CalendarDays, Download, Settings2, UsersRound } from "lucide-react";
import { Link, useLocation, useParams } from "react-router-dom";

import { RosterLoading, RosterShell } from "./components/RosterShell";

const LazyComplianceImpact = lazy(() => import("./components/ComplianceImpact")
  .then((module) => ({ default: module.ComplianceImpact })));
const LazyMyRosterWorkspace = lazy(() => import("./components/MyRosterWorkspace")
  .then((module) => ({ default: module.MyRosterWorkspace })));
const LazyRosterDashboard = lazy(() => import("./components/RosterDashboard")
  .then((module) => ({ default: module.RosterDashboard })));
const LazyRosterOperationsWorkspace = lazy(() => import("./components/RosterOperationsWorkspace")
  .then((module) => ({ default: module.RosterOperationsWorkspace })));
const LazyUnifiedRosterPlanner = lazy(() => import("./components/UnifiedRosterPlanner")
  .then((module) => ({ default: module.UnifiedRosterPlanner })));
const LazyRosteringSetupWorkspace = lazy(() => import("./components/RosteringSetupWorkspace")
  .then((module) => ({ default: module.RosteringSetupWorkspace })));
const LazyWorkforceHrWorkspace = lazy(() => import("./components/WorkforceHrWorkspace")
  .then((module) => ({ default: module.WorkforceHrWorkspace })));

function DeferredWorkspace({ label, children }: { label: string; children: ReactNode }) {
  return <Suspense fallback={<RosterLoading label={label} />}>{children}</Suspense>;
}

function useRosterRoot() {
  const { amoCode = "" } = useParams();
  return `/maintenance/${encodeURIComponent(amoCode)}/rostering`;
}

export function RosteringDashboardPage() {
  const root = useRosterRoot();
  return (
    <RosterShell
      eyebrow="Duty rostering · Operational control"
      title="Roster command centre"
      description="See what needs action, review approvals and move directly into planning, compliance or operations."
      actions={<Link className="wr-button wr-button--primary" to={`${root}/calendar`}><CalendarDays size={16} /> Open planner</Link>}
    >
      <DeferredWorkspace label="Opening roster command centre…"><LazyRosterDashboard /></DeferredWorkspace>
    </RosterShell>
  );
}

export function RosterCalendarPage() {
  const root = useRosterRoot();
  return (
    <RosterShell
      eyebrow="Planner workspace"
      title="Duty roster planner"
      description="Build controlled duty versions while seeing approved leave, training, unavailability and Quality commitments from their source records."
      actions={<Link className="wr-button wr-button--secondary" to={`${root}/settings?section=overview`}><Settings2 size={16} /> Setup</Link>}
    >
      <DeferredWorkspace label="Opening duty planner…"><LazyUnifiedRosterPlanner /></DeferredWorkspace>
    </RosterShell>
  );
}

export function ManpowerPlanningBoardPage() {
  return (
    <RosterShell
      eyebrow="Live operations"
      title="Capacity, coverage and reporting"
      description="Compare duty coverage with maintenance demand, then reconcile planned and actual time from the same operational workspace."
    >
      <DeferredWorkspace label="Opening operations workspace…"><LazyRosterOperationsWorkspace /></DeferredWorkspace>
    </RosterShell>
  );
}

export function MyRosterPage() {
  return (
    <RosterShell eyebrow="Employee self-service" title="My duty and time" description="Review published duty, acknowledge changes, request leave, capture attendance and inspect timesheet reconciliation.">
      <DeferredWorkspace label="Opening your duty workspace…"><LazyMyRosterWorkspace /></DeferredWorkspace>
    </RosterShell>
  );
}

export function TrainingImpactPage() {
  return (
    <RosterShell eyebrow="Compliance impact" title="Training, licence and authorisation coverage" description="See exactly which assignments are affected by expired training, licence validity, authorisation scope or certifying coverage.">
      <DeferredWorkspace label="Opening compliance coverage…"><LazyComplianceImpact /></DeferredWorkspace>
    </RosterShell>
  );
}

export function WorkforceHrPage() {
  return (
    <RosterShell
      eyebrow="Canonical Workforce ownership"
      title="Workforce and HR"
      description="Manage employment readiness, leave, attendance, timesheets, payroll controls and employee work-pattern assignments without duplicating records in Rostering."
      actions={<span className="wr-header-badge"><UsersRound size={15} /> HR · Workforce · Time</span>}
    >
      <DeferredWorkspace label="Opening Workforce and HR…"><LazyWorkforceHrWorkspace /></DeferredWorkspace>
    </RosterShell>
  );
}

export function RosterReportsPage() {
  return (
    <RosterShell
      eyebrow="Operational reporting"
      title="Roster and workforce operations"
      description="Reports now sit beside capacity and coverage so supervisors can move from a result directly to operational action."
      actions={<span className="wr-header-badge"><Download size={15} /> CSV · XLSX · PDF · ICS</span>}
    >
      <DeferredWorkspace label="Opening operations workspace…"><LazyRosterOperationsWorkspace /></DeferredWorkspace>
    </RosterShell>
  );
}

export function RosterSettingsPage() {
  const location = useLocation();
  const workforce = new URLSearchParams(location.search).get("section") === "workforce";
  if (workforce) return <WorkforceHrPage />;
  return (
    <RosterShell
      eyebrow="Guided setup"
      title="Roster setup"
      description="Check readiness, configure future periods and draft rotations, manage shifts and patterns, and review controlled policy."
    >
      <DeferredWorkspace label="Opening roster setup…"><LazyRosteringSetupWorkspace /></DeferredWorkspace>
    </RosterShell>
  );
}
