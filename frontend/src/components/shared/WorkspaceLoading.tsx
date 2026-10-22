import "./workspaceLoading.css";

type Props = { label?: string; compact?: boolean };
/** A themed content placeholder, usable inside the existing page shell. */
export default function WorkspaceLoading({ label = "Opening workspace", compact = false }: Props) {
  return <section className={`workspace-loading${compact ? " workspace-loading--compact" : ""}`} role="status" aria-label={label} aria-busy="true">
    <span className="sr-only">{label}</span>
    <div className="workspace-loading__title" aria-hidden="true" />
    <div className="workspace-loading__toolbar" aria-hidden="true"><i/><i/><i/></div>
    <div className="workspace-loading__body" aria-hidden="true">
      {Array.from({ length: compact ? 3 : 6 }, (_, index) => <div key={index}><i/><i/><i/></div>)}
    </div>
  </section>;
}
