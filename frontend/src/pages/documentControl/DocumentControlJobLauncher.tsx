import { useState } from "react";
import {
  BookCopy,
  CalendarClock,
  ClipboardList,
  FileDiff,
  Landmark,
  Link2,
  ListChecks,
  Network,
  Send,
  ShieldCheck,
  X,
} from "lucide-react";
import { useNavigate } from "react-router-dom";

import {
  DOCUMENT_CONTROL_JOBS,
  documentJobSelectionPath,
  type DocumentControlJob,
  type DocumentControlJobId,
} from "./documentControlJobs";
import "./documentControlJobLauncher.css";

const ICONS: Record<DocumentControlJobId, typeof ClipboardList> = {
  "raise-change": ClipboardList,
  "start-workflow": ListChecks,
  "temporary-revision": FileDiff,
  "authority-submission": Landmark,
  distribute: Send,
  "controlled-copy": BookCopy,
  "schedule-review": CalendarClock,
  "external-source": ShieldCheck,
  applicability: Network,
  integration: Link2,
};

const GROUPS: Array<{ title: string; description: string; jobs: DocumentControlJobId[] }> = [
  {
    title: "Change & approval",
    description: "Create and advance controlled content through its governed lifecycle.",
    jobs: ["raise-change", "start-workflow", "temporary-revision", "authority-submission"],
  },
  {
    title: "Issue & custody",
    description: "Distribute effective information and control numbered physical copies.",
    jobs: ["distribute", "controlled-copy"],
  },
  {
    title: "Assurance & applicability",
    description: "Maintain review, external-source currentness and operational applicability.",
    jobs: ["schedule-review", "external-source", "applicability", "integration"],
  },
];

function JobButton({ job, basePath, close }: { job: DocumentControlJob; basePath: string; close: () => void }) {
  const navigate = useNavigate();
  const Icon = ICONS[job.id];
  return <button type="button" className="dc-job-launcher__job" onClick={() => { close(); navigate(documentJobSelectionPath(basePath, job.id)); }}>
    <Icon size={17} />
    <span><strong>{job.label}</strong><small>{job.description}</small></span>
  </button>;
}

export default function DocumentControlJobLauncher({ basePath }: { basePath: string }) {
  const [open, setOpen] = useState(false);

  return <>
    <button type="button" className="dc-button dc-button--primary" onClick={() => setOpen(true)} data-testid="document-control-start-work">
      <ClipboardList size={15} /> Start work
    </button>
    {open ? <div className="publications-upload-backdrop" role="presentation" onMouseDown={(event) => { if (event.target === event.currentTarget) setOpen(false); }}>
      <section className="publications-upload-dialog dc-job-launcher" role="dialog" aria-modal="true" aria-label="Start Document Control work">
        <header><div><h2>Start Document Control work</h2><p>Choose the job first. The DMS will then ask for the controlled document and open the correct governed form.</p></div><button type="button" onClick={() => setOpen(false)} aria-label="Close work launcher"><X size={18} /></button></header>
        <div className="dc-job-launcher__groups">
          {GROUPS.map((group) => <section key={group.title}><div><h3>{group.title}</h3><p>{group.description}</p></div><div className="dc-job-launcher__grid">{group.jobs.map((id) => <JobButton key={id} job={DOCUMENT_CONTROL_JOBS[id]} basePath={basePath} close={() => setOpen(false)} />)}</div></section>)}
        </div>
      </section>
    </div> : null}
  </>;
}
