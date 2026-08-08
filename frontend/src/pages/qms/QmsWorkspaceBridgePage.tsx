import React from "react";
import {
  ArrowRight,
  BrainCircuit,
  ClipboardCheck,
  FileCheck2,
  FolderKanban,
  Gauge,
  GraduationCap,
  PackageCheck,
  Scale,
  ShieldCheck,
  SlidersHorizontal,
  UserRoundCheck,
  Wrench,
  type LucideIcon,
} from "lucide-react";
import { Link } from "react-router-dom";

import type { QmsWorkspaceId } from "./routes/qmsWorkspaceRegistry";
import "../../styles/qms-assurance-workspaces.css";

type WorkspaceId = Exclude<QmsWorkspaceId, "control-room" | "planner">;

type Lens = {
  title: string;
  description: string;
  path: string;
  icon: LucideIcon;
  eyebrow?: string;
};

type WorkspaceDefinition = {
  title: string;
  eyebrow: string;
  description: string;
  principle: string;
  lenses: Lens[];
  nextCapability: string;
};

function workspaceDefinition(amoCode: string, workspace: WorkspaceId): WorkspaceDefinition {
  const quality = `/maintenance/${encodeURIComponent(amoCode)}/quality`;
  const training = `/maintenance/${encodeURIComponent(amoCode)}/training/competence`;

  const definitions: Record<WorkspaceId, WorkspaceDefinition> = {
    missions: {
      title: "Missions",
      eyebrow: "Controlled change & capability projects",
      description: "Coordinate complex Quality-led work as governed projects instead of scattering the same change across forms, registers and email.",
      principle: "Existing Change Control remains the authoritative source until the Mission engine introduces typed gates, dependencies, evidence pointers and decision history.",
      nextCapability: "First mission template: aircraft / capability inclusion with facilities, tooling, technical data, people, training, procedures, manpower, safety assessment, Quality self-evaluation and authority gates.",
      lenses: [
        { title: "Controlled changes", description: "Review current change requests, approvals and implementation state without creating a second change register.", path: `${quality}/change-control/register`, icon: FolderKanban, eyebrow: "Current source" },
        { title: "Capability evidence", description: "Use the existing Quality evidence layer while mission-specific capability gates are introduced.", path: `${quality}/evidence-vault/search`, icon: PackageCheck },
        { title: "Controlled documents", description: "Open the governed document workflow for procedures, manuals and change-controlled instructions affected by a mission.", path: `/maintenance/${encodeURIComponent(amoCode)}/document-control`, icon: FileCheck2 },
        { title: "Competence dependencies", description: "Use Training & Competence as the authoritative source for qualification and course evidence.", path: `${training}/dashboard`, icon: GraduationCap },
      ],
    },
    people: {
      title: "People & Privileges",
      eyebrow: "Competence, authorization & future coverage",
      description: "Move Quality beyond course-expiry monitoring toward evidence-backed internal privileges and task eligibility.",
      principle: "Training owns courses and competence records. Quality owns the authorization decision, privilege scope, limitations and assurance of future qualified coverage.",
      nextCapability: "The People engine will answer whether a person can perform a task on a specific aircraft/component, at a location and time, under the AMO approval, while keeping hard eligibility gates separate from predictive exposure.",
      lenses: [
        { title: "Training & competence", description: "Open the authoritative personnel competence workspace rather than duplicating training records inside QMS.", path: `${training}/dashboard`, icon: GraduationCap, eyebrow: "Authoritative source" },
        { title: "My Quality work", description: "Review personnel-related approvals, verification tasks and decisions already assigned to you.", path: `${quality}/inbox/assigned-to-me`, icon: UserRoundCheck },
        { title: "Audit assurance", description: "Review personnel-qualification and authorization evidence through the governed audit workflow when surveillance is required.", path: `${quality}/audits/dashboard`, icon: ClipboardCheck },
        { title: "Evidence room", description: "Locate retained evidence packages and source records supporting competence or authorization decisions.", path: `${quality}/evidence-vault/search`, icon: PackageCheck },
      ],
    },
    assurance: {
      title: "Assurance",
      eyebrow: "Signals, cases, surveillance & effectiveness",
      description: "Use one assurance workspace to investigate operational signals and governed Quality cases instead of treating every source domain as a separate top-level module.",
      principle: "Audits, findings, CARs, suppliers, tooling and external commitments keep their authoritative workflows. Assurance is the decision layer that connects them.",
      nextCapability: "The Assurance Case engine will connect signals to evidence, investigations, causal analysis, corrective actions and effectiveness tests without auto-approving root causes or closures.",
      lenses: [
        { title: "Audits & surveillance", description: "Programme, plan, execute and close governed audits and targeted surveillance.", path: `${quality}/audits/dashboard`, icon: ClipboardCheck, eyebrow: "Specialist workflow" },
        { title: "Findings & corrective action", description: "Move from observed non-conformity through governed CAR/CAPA response, review and effectiveness.", path: `${quality}/cars/register`, icon: ShieldCheck },
        { title: "Supplier assurance", description: "Review supplier approval and Quality exposure while Procurement and Stores retain transactional ownership.", path: `${quality}/suppliers/approved-list`, icon: PackageCheck },
        { title: "Tooling exposure", description: "Review calibration exceptions and out-of-tolerance exposure without making Quality the tooling data owner.", path: `${quality}/equipment-calibration/overdue`, icon: Wrench },
        { title: "External assurance", description: "Regulator findings, commitments, customer feedback and authority correspondence.", path: `${quality}/external-interface/regulator-findings`, icon: Scale },
        { title: "Evidence room", description: "Search retained evidence and packages across governed Quality workflows.", path: `${quality}/evidence-vault/search`, icon: PackageCheck },
      ],
    },
    intelligence: {
      title: "Intelligence",
      eyebrow: "Performance, risk & approval readiness",
      description: "Turn Quality data into explainable trend, risk and decision intelligence rather than another collection of status registers.",
      principle: "Statistical methods and deterministic control logic come before AI. Every signal must retain lineage, as-of time and a route back to the source evidence.",
      nextCapability: "The Intelligence engine will add drift detection, exposure-normalised rates, recurrence clustering, risk-targeted surveillance, regulatory impact mapping and the AMO Approval Digital Twin.",
      lenses: [
        { title: "Performance", description: "Open the existing Quality reporting surface while the new intelligence models are introduced.", path: `${quality}/reports/executive-dashboard`, icon: Gauge, eyebrow: "Current source" },
        { title: "Risk intelligence", description: "Review risks, opportunities and treatments as inputs to assurance prioritisation.", path: `${quality}/risk/risk-matrix`, icon: BrainCircuit },
        { title: "Management review", description: "Review management actions and evidence that will feed generated management-review packs.", path: `${quality}/management-review/dashboard`, icon: ClipboardCheck },
        { title: "Quality system & controls", description: "Review current process/objective controls while the requirement-to-control graph is consolidated.", path: `${quality}/system/processes`, icon: SlidersHorizontal },
      ],
    },
  };

  return definitions[workspace];
}

const QmsWorkspaceBridgePage: React.FC<{ amoCode: string; workspace: WorkspaceId }> = ({ amoCode, workspace }) => {
  const definition = workspaceDefinition(amoCode, workspace);

  return (
    <main className="qms-workspace-bridge" aria-label={definition.title}>
      <header className="qms-workspace-bridge__header">
        <div>
          <span>{definition.eyebrow}</span>
          <h1>{definition.title}</h1>
          <p>{definition.description}</p>
        </div>
        <aside>
          <strong>Source-of-truth rule</strong>
          <p>{definition.principle}</p>
        </aside>
      </header>

      <section className="qms-workspace-bridge__lenses" aria-label={`${definition.title} working lenses`}>
        {definition.lenses.map((lens) => {
          const Icon = lens.icon;
          return (
            <Link key={lens.title} to={lens.path}>
              <span className="qms-workspace-bridge__icon"><Icon size={18} aria-hidden="true" /></span>
              <span>
                {lens.eyebrow ? <small>{lens.eyebrow}</small> : null}
                <strong>{lens.title}</strong>
                <p>{lens.description}</p>
              </span>
              <ArrowRight size={16} aria-hidden="true" />
            </Link>
          );
        })}
      </section>

      <section className="qms-workspace-bridge__next">
        <ShieldCheck size={18} aria-hidden="true" />
        <div>
          <span>Refactor contract</span>
          <strong>No duplicate register is being introduced on this surface.</strong>
          <p>{definition.nextCapability}</p>
        </div>
      </section>
    </main>
  );
};

export default QmsWorkspaceBridgePage;
