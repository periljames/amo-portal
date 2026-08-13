export type DocumentControlJobId =
  | "raise-change"
  | "start-workflow"
  | "temporary-revision"
  | "authority-submission"
  | "distribute"
  | "controlled-copy"
  | "schedule-review"
  | "external-source"
  | "applicability"
  | "integration";

export type DocumentControlJob = {
  id: DocumentControlJobId;
  label: string;
  shortLabel: string;
  description: string;
  selectionPrompt: string;
  selectLabel: string;
  tab: "changes" | "workflow" | "distribution" | "compliance" | "relationships";
  domain: "CHANGE" | "DISTRIBUTION" | "ASSURANCE" | "RELATIONSHIP";
  requiresPublished?: boolean;
  externalOnly?: boolean;
};

export const DOCUMENT_CONTROL_JOBS: Record<DocumentControlJobId, DocumentControlJob> = {
  "raise-change": {
    id: "raise-change",
    label: "Raise change request",
    shortLabel: "Raise change",
    description: "Record a governed reason, source, impact, priority and due date for a document change.",
    selectionPrompt: "Select the controlled document that needs to change.",
    selectLabel: "Select for change",
    tab: "changes",
    domain: "CHANGE",
  },
  "start-workflow": {
    id: "start-workflow",
    label: "Start revision workflow",
    shortLabel: "Start workflow",
    description: "Take an existing draft revision into technical, Quality, management and release control.",
    selectionPrompt: "Select the document whose latest draft must enter controlled review.",
    selectLabel: "Select for workflow",
    tab: "workflow",
    domain: "CHANGE",
  },
  "temporary-revision": {
    id: "temporary-revision",
    label: "Create temporary revision",
    shortLabel: "Create TR",
    description: "Create a time-bounded temporary revision with effectivity and incorporation/expiry control.",
    selectionPrompt: "Select the published document that requires a temporary revision.",
    selectLabel: "Select for TR",
    tab: "changes",
    domain: "CHANGE",
    requiresPublished: true,
  },
  "authority-submission": {
    id: "authority-submission",
    label: "Record authority submission",
    shortLabel: "Authority submission",
    description: "Create or continue the authority submission record attached to a governed revision workflow.",
    selectionPrompt: "Select the document whose revision requires authority action.",
    selectLabel: "Select for authority",
    tab: "workflow",
    domain: "CHANGE",
  },
  distribute: {
    id: "distribute",
    label: "Create distribution",
    shortLabel: "New distribution",
    description: "Select the effective revision, recipients and acknowledgement requirements for controlled issue.",
    selectionPrompt: "Select the published document to distribute.",
    selectLabel: "Select to distribute",
    tab: "distribution",
    domain: "DISTRIBUTION",
    requiresPublished: true,
  },
  "controlled-copy": {
    id: "controlled-copy",
    label: "Issue controlled copy",
    shortLabel: "Issue copy",
    description: "Register numbered physical custody against an effective controlled revision.",
    selectionPrompt: "Select the published document for the numbered controlled copy.",
    selectLabel: "Select for copy",
    tab: "distribution",
    domain: "DISTRIBUTION",
    requiresPublished: true,
  },
  "schedule-review": {
    id: "schedule-review",
    label: "Schedule periodic review",
    shortLabel: "Schedule review",
    description: "Assign a continued-applicability review owner and due date.",
    selectionPrompt: "Select the document that requires a periodic review plan.",
    selectLabel: "Select for review",
    tab: "compliance",
    domain: "ASSURANCE",
  },
  "external-source": {
    id: "external-source",
    label: "Register external source",
    shortLabel: "External source",
    description: "Record provider, authority, access method and currency-check controls for external technical data.",
    selectionPrompt: "Select the external controlled document whose source must be registered or maintained.",
    selectLabel: "Select external source",
    tab: "compliance",
    domain: "ASSURANCE",
    externalOnly: true,
  },
  applicability: {
    id: "applicability",
    label: "Define applicability",
    shortLabel: "Applicability",
    description: "Define governed aircraft, component, base, role or work-scope applicability.",
    selectionPrompt: "Select the document whose applicability must be defined.",
    selectLabel: "Select for applicability",
    tab: "compliance",
    domain: "ASSURANCE",
  },
  integration: {
    id: "integration",
    label: "Link module record",
    shortLabel: "Link record",
    description: "Create a governed relationship to QMS, Training, Workforce, Planning or another portal record.",
    selectionPrompt: "Select the document to connect to another governed portal record.",
    selectLabel: "Select to link",
    tab: "relationships",
    domain: "RELATIONSHIP",
  },
};

export function documentControlJob(value?: string | null): DocumentControlJob | null {
  if (!value || !(value in DOCUMENT_CONTROL_JOBS)) return null;
  return DOCUMENT_CONTROL_JOBS[value as DocumentControlJobId];
}

export function documentJobTarget(basePath: string, manualId: string, job: DocumentControlJob): string {
  return `${basePath}/library/${encodeURIComponent(manualId)}?tab=${job.tab}#document-control-record-actions`;
}

export function documentJobSelectionPath(basePath: string, jobId: DocumentControlJobId): string {
  return `${basePath}/library?action=${encodeURIComponent(jobId)}`;
}
