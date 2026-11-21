import "./work-lifecycle.css";
const phases = ["Preparation", "Dispatched", "Accepted", "In progress", "Completed", "Release submitted", "Closed"];
const phaseIndex: Record<string, number> = {
  DRAFT: 0, TECHNICAL_SCOPE_REVIEW: 0, QUALIFICATION_AGREEMENT_CHECK: 0, AWAITING_AUTHORIZATION: 0, AUTHORIZED: 0, DISPATCHED: 1, PROVIDER_ACCEPTED: 2, IN_PROGRESS: 3,
  WORK_COMPLETED: 4, RELEASE_SUBMITTED: 5, RETURNED: 5, INSPECTION: 5, TECHNICALLY_ACCEPTED: 5, CLOSED: 6,
};
export default function WorkLifecycle({ status }: { status: string }) {
  const current = phaseIndex[status];
  return <div className="work-lifecycle" aria-label="Contracted work progress">
    <p><strong>Work progress</strong><span>{status.replaceAll("_", " ").toLowerCase()}</span></p>
    {current !== undefined ? <ol>{phases.map((phase, index) => <li key={phase}
      data-progress={index < current ? "complete" : index === current ? "current" : "upcoming"}
      aria-current={index === current ? "step" : undefined}>
      <span aria-hidden="true">{index + 1}</span>{phase}
    </li>)}</ol> : <p className="work-lifecycle-note">Review the current work status and authorized actions before continuing.</p>}
  </div>;
}
