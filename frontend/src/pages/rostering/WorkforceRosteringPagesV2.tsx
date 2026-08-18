import "./components/roster-setup-refinement.css";

import { lazy, Suspense, type ReactNode } from "react";
import { CalendarDays, Download, UsersRound } from "lucide-react";
import { Link, useLocation, useParams } from "react-router-dom";

import { errorMessage } from "./rosterUi";
import { RosterError, RosterLoading, RosterShell } from "./components/RosterShell";
import { useWorkforcePermissions } from "./hooks/useWorkforcePermissions";

const LazyCalendarSubscriptionSecurityPanel = lazy(() => import("./components/CalendarSubscriptionSecurityPanel")
  .then((module) => ({ default: module.CalendarSubscriptionSecurityPanel })));
const LazyComplianceImpact = lazy(() => import("./components/ComplianceImpact")
  .then((module) => ({ default: module.ComplianceImpact })));
const LazyDutyLocationAssistant = lazy(() => import("./components/DutyLocationAssistant")
  .then((module) => ({ default: module.DutyLocationAssistant })));
const LazyMyRosterConsentPanel = lazy(() => import("./components/RosterConsentWorkflows")
  .then((module) => ({ default: module.MyRosterConsentPanel })));
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
const LazyWorkforceHrWorkspace = lazy(() => import("./components/WorkforceHrWorkspaceV2")
  .then((module) => ({ default: module.WorkforceHrWorkspaceV2 })));

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
  return (
    <RosterShell
      eyebrow="Planner workspace"
      title="Duty roster planner"
      description="Build controlled duty versions while seeing approved leave, training, unavailability and Quality commitments from their source records."
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
    <RosterShell eyebrow="Employee self-service" title="My duty and time" description="Review published duty, acknowledge exact proposed changes, request leave, capture attendance and inspect timesheet reconciliation.">
      <DeferredWorkspace label="Checking private duty-location guidance…"><LazyDutyLocationAssistant /></DeferredWorkspace>
      <DeferredWorkspace label="Checking calendar subscription security…"><LazyCalendarSubscriptionSecurityPanel /></DeferredWorkspace>
      <DeferredWorkspace label="Opening controlled duty acknowledgements…"><LazyMyRosterConsentPanel /></DeferredWorkspace>
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
  const permissionsQuery = useWorkforcePermissions();
  const canView = (permissionsQuery.data?.permissions || []).includes("workforce.view_sensitive");
  const waitingForServer = permissionsQuery.isPending || permissionsQuery.fetchStatus === "paused";

  return (
    <RosterShell
      eyebrow="Canonical Workforce ownership"
      title="Workforce and HR"
      description="Manage employment readiness, leave, attendance, timesheets, payroll controls and employee work-pattern assignments without duplicating records in Rostering."
      actions={<span className="wr-header-badge"><UsersRound size={15} /> HR · Workforce · Time</span>}
    >
      {waitingForServer ? <RosterLoading label="Waiting for the server to verify Workforce access…" /> : null}
      {!waitingForServer && permissionsQuery.isError ? (
        <RosterError
          title="Could not verify Workforce access"
          message={errorMessage(permissionsQuery.error)}
          onRetry={() => void permissionsQuery.refetch()}
        />
      ) : null}
      {!waitingForServer && permissionsQuery.isSuccess && !canView ? (
        <RosterError
          title="Workforce access restricted"
          message="Your live account permissions do not include Workforce sensitive-data access. Ask an AMO administrator to grant the appropriate Workforce scope."
        />
      ) : null}
      {!waitingForServer && permissionsQuery.isSuccess && canView ? (
        <DeferredWorkspace label="Opening Workforce and HR…"><LazyWorkforceHrWorkspace /></DeferredWorkspace>
      ) : null}
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
      description="Follow one clear path: define reusable rotations, create the month, then review and publish. Advanced controls stay collapsed until needed."
    >
      <DeferredWorkspace label="Opening roster setup…"><LazyRosteringSetupWorkspace /></DeferredWorkspace>
    </RosterShell>
  );
}
