import { useEffect, useMemo, useState } from "react";
import { BookOpen, GitCompareArrows, Send, Workflow } from "lucide-react";
import { Link } from "react-router-dom";

import { getManual, listRevisions, type ManualRevision, type ManualSummary } from "../../services/manuals";
import { useManualRouteContext } from "./context";
import ManualsPageLayout from "./ManualsPageLayout";
import "./manualReader.css";
import "./publicationsDashboard.css";

export default function PublicationOverviewPage() {
  const { tenant, manualId, basePath } = useManualRouteContext();
  const [publication, setPublication] = useState<ManualSummary | null>(null);
  const [revisions, setRevisions] = useState<ManualRevision[]>([]);
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    if (!tenant || !manualId) return;
    let active = true;
    setLoading(true);
    Promise.all([getManual(tenant, manualId), listRevisions(tenant, manualId)])
      .then(([record, revisionRows]) => {
        if (!active) return;
        setPublication(record);
        setRevisions(revisionRows);
      })
      .catch(() => {
        if (!active) return;
        setPublication(null);
        setRevisions([]);
      })
      .finally(() => {
        if (active) setLoading(false);
      });
    return () => { active = false; };
  }, [tenant, manualId]);

  const currentPublished = useMemo(
    () => revisions.find((revision) => revision.id === publication?.current_published_rev_id) || revisions.find((revision) => revision.status_enum === "PUBLISHED") || null,
    [publication?.current_published_rev_id, revisions],
  );

  return (
    <ManualsPageLayout
      title={publication?.title || "Publication record"}
      subtitle={publication ? `${publication.code} · ${publication.manual_type}` : "Controlled publication and revision history"}
      actions={currentPublished ? <Link className="manuals-primary-btn" to={`${basePath}/${manualId}/rev/${currentPublished.id}/read`}><BookOpen size={16} /> Read current issue</Link> : undefined}
    >
      {loading ? <div className="publication-record-empty">Loading publication record…</div> : null}
      {!loading && !publication ? <div className="publication-record-empty">Publication record not found.</div> : null}
      {publication ? (
        <>
          <section className="publications-overview-strip" aria-label="Publication record summary">
            <div><strong>{publication.code}</strong><span>Publication code</span></div>
            <div><strong>{revisions.length}</strong><span>Revision records</span></div>
            <div><strong>{currentPublished?.rev_number || "—"}</strong><span>Current published revision</span></div>
            <div><strong>{publication.status || "—"}</strong><span>Publication status</span></div>
          </section>
          <section className="publication-record-panel" style={{ maxWidth: "none", minHeight: 0, padding: 0 }}>
            <h2>Revision history</h2>
            <p>Use the immutable revision ID behind each action. Revision labels are shown only for people.</p>
            <div className="publication-history-list">
              {revisions.map((revision) => (
                <article key={revision.id} style={{ gridTemplateColumns: "minmax(12rem, 1fr) minmax(10rem, auto) minmax(18rem, auto)" }}>
                  <div><strong>Issue {revision.issue_number || "—"} · Rev {revision.rev_number}</strong><small style={{ display: "block" }}>{revision.status_enum.replaceAll("_", " ")}</small></div>
                  <span>{revision.effective_date || "No effective date"}</span>
                  <div style={{ display: "flex", gap: "0.55rem", flexWrap: "wrap" }}>
                    <Link to={`${basePath}/${manualId}/rev/${revision.id}/read`}><BookOpen size={14} /> Reader</Link>
                    <Link to={`${basePath}/${manualId}/rev/${revision.id}/diff`}><GitCompareArrows size={14} /> Compare</Link>
                    <Link to={`${basePath}/${manualId}/rev/${revision.id}/workflow`}><Workflow size={14} /> Workflow</Link>
                    <Link to={`${basePath}/${manualId}/rev/${revision.id}/exports`}><Send size={14} /> PDF exports</Link>
                  </div>
                </article>
              ))}
              {!revisions.length ? <div className="publication-record-empty">No revisions have been uploaded.</div> : null}
            </div>
          </section>
        </>
      ) : null}
    </ManualsPageLayout>
  );
}
