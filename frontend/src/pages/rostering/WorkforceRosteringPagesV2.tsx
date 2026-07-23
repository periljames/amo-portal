import { CalendarDays, Download, RefreshCw, Settings2 } from "lucide-react";
import { Link, useParams } from "react-router-dom";

import { CapacityBoard } from "./components/CapacityBoard";
import { ComplianceImpact } from "./components/ComplianceImpact";
import { MyRosterWorkspace } from "./components/MyRosterWorkspace";
import { RosterDashboard } from "./components/RosterDashboard";
import { RosterReports } from "./components/RosterReports";
import { RosterShell } from "./components/RosterShell";
import { UnifiedRosterPlanner } from "./components/UnifiedRosterPlanner";
import { UnifiedRosterSettings } from "./components/UnifiedRosterSettings";

function useRosterRoot() {
  const { amoCode = "" } = useParams();
  return `/maintenance/${encodeURIComponent(amoCode)}/rostering`;
}

export function RosteringDashboardPage() {
  const root = useRosterRoot();
  return <RosterShell eyebrow="Duty rostering · Workforce control" title="Roster command centre" description="Control periods, approvals, compliance, capacity, leave and published-duty acknowledgements from one operational view." actions={<Link className="wr-button wr-button--primary" to={`${root}/calendar`}><CalendarDays size={16} /> Open planner</Link>}><RosterDashboard /></RosterShell>;
}

export function RosterCalendarPage() {
  const root = useRosterRoot();
  return <RosterShell eyebrow="Planner workspace" title="Duty roster planner" description="Build controlled duty versions while automatically seeing training, approved leave, unavailability and assigned Quality work from the same tenant personnel record." actions={<Link className="wr-button wr-button--secondary" to={`${root}/settings`}><Settings2 size={16} /> Setup</Link>}><UnifiedRosterPlanner /></RosterShell>;
}

export function ManpowerPlanningBoardPage() {
  return <RosterShell eyebrow="Maintenance demand" title="Manpower capacity board" description="Compare published duty hours, certifying coverage and task demand by base before maintenance work is committed."><CapacityBoard /></RosterShell>;
}

export function MyRosterPage() {
  return <RosterShell eyebrow="Employee self-service" title="My duty and time" description="Review published duty, acknowledge changes, request leave, capture attendance and inspect timesheet reconciliation."><MyRosterWorkspace /></RosterShell>;
}

export function TrainingImpactPage() {
  return <RosterShell eyebrow="Compliance impact" title="Training, licence and authorisation coverage" description="See exactly which published assignments are affected by expired training, licence validity, authorisation scope or certifying coverage."><ComplianceImpact /></RosterShell>;
}

export function RosterReportsPage() {
  return <RosterShell eyebrow="Operational reporting" title="Roster and workforce reports" description="Reconcile planned duty, attendance, productive hours, overtime, leave and acknowledgements with export-ready evidence." actions={<span className="wr-header-badge"><Download size={15} /> CSV · XLSX · PDF · ICS</span>}><RosterReports /></RosterShell>;
}

export function RosterSettingsPage() {
  return <RosterShell eyebrow="Module configuration" title="Roster and workforce setup" description="Manage periods, shift templates, work patterns, employment contracts, leave policy, rules, approvals and planner preferences without duplicating tenant personnel data." actions={<span className="wr-header-badge"><RefreshCw size={15} /> Source-aware</span>}><UnifiedRosterSettings /></RosterShell>;
}
