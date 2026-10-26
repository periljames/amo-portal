import "./workspaceLoading.css";
/** Compact data placeholder; status remains available to assistive technology. */
export default function InlineLoading({ label = "Loading records" }: { label?: string }) {
  return <span className="inline-loading" role="status" aria-label={label} aria-busy="true"><span aria-hidden="true"/><span aria-hidden="true"/><span aria-hidden="true"/></span>;
}
