import "./workspaceLoading.css";

/** Stable page geometry while a never-visited route chunk is fetched. */
export default function WorkspaceLoading() {
  return <section className="workspace-loading" role="status" aria-label="Opening workspace" aria-busy="true">
    <span className="sr-only">Opening workspace</span>
    <div className="workspace-loading__title" aria-hidden="true" />
    <div className="workspace-loading__toolbar" aria-hidden="true" />
    <div className="workspace-loading__body" aria-hidden="true">
      {Array.from({ length: 5 }, (_, index) => <div key={index} />)}
    </div>
  </section>;
}
