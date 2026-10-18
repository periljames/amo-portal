export default function AuditStageLoading({ label }: { label: string }) {
  return <div className="audit-workflow-loading" role="status" aria-busy="true">
    <span className="sr-only">Loading {label}…</span>
    <div className="audit-workflow-loading__hero" aria-hidden><i /><i /></div>
    <div className="audit-workflow-loading__body" aria-hidden><i /><i /><i /></div>
  </div>;
}
