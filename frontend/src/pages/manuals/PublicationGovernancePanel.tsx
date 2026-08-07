import { useCallback, useEffect, useMemo, useState } from "react";
import {
  Archive,
  BookmarkPlus,
  Check,
  ClipboardCheck,
  Download,
  FileDiff,
  FileKey2,
  Highlighter,
  Link2,
  MessageSquareText,
  RefreshCw,
  ShieldCheck,
  X,
  XCircle,
} from "lucide-react";

import "./publicationReaderGovernanceWorkspace.css";

import {
  compareReaderRevisions,
  createEvidenceSnapshot,
  createReaderAnnotation,
  decideAnnotationMigration,
  getEvidenceSnapshot,
  getReaderEvidence,
  getReaderManifest,
  listAnnotationMigrations,
  listEvidenceSnapshots,
  listReaderAnnotations,
  prepareAnnotationMigrations,
  updateReaderAnnotation,
  type AnnotationMigration,
  type ReaderAnnotation,
  type ReaderComparison,
  type ReaderEvidence,
  type ReaderManifest,
} from "../../services/readerGovernance";

type Tab = "annotations" | "evidence" | "compare";

type SelectedLocation = {
  section_id?: string;
  page_number?: number;
  exact_quote?: string;
  normalized_rects?: Array<{ x: number; y: number; width: number; height: number }>;
};

function formatDate(value?: string | null): string {
  if (!value) return "—";
  const parsed = new Date(value);
  return Number.isNaN(parsed.getTime()) ? value : parsed.toLocaleString();
}

function counter(value?: Record<string, number> | null): string {
  if (!value || !Object.keys(value).length) return "None";
  return Object.entries(value).map(([key, count]) => `${key.replaceAll("_", " ")}: ${count}`).join(" · ");
}

function selectedSemanticLocation(): SelectedLocation {
  const selection = window.getSelection();
  const text = selection?.toString().trim() || "";
  if (!selection?.rangeCount || !text) return {};
  const range = selection.getRangeAt(0);
  const element = (range.commonAncestorContainer.nodeType === Node.ELEMENT_NODE
    ? range.commonAncestorContainer
    : range.commonAncestorContainer.parentElement) as Element | null;
  const section = element?.closest<HTMLElement>(".publication-html-section[data-section-id]");
  if (!section) return {};
  return { section_id: section.dataset.sectionId, exact_quote: text.slice(0, 4000) };
}

function selectedPdfLocation(): SelectedLocation {
  const selection = window.getSelection();
  const text = selection?.toString().trim() || "";
  if (!selection?.rangeCount || !text) return {};
  const range = selection.getRangeAt(0);
  const element = (range.commonAncestorContainer.nodeType === Node.ELEMENT_NODE
    ? range.commonAncestorContainer
    : range.commonAncestorContainer.parentElement) as Element | null;
  const page = element?.closest<HTMLElement>(".pdfv3-page[data-page-number]");
  const surface = page?.querySelector<HTMLElement>(".pdfv3-page-surface");
  const pageNumber = Number(page?.dataset.pageNumber || 0);
  if (!page || !surface || !Number.isInteger(pageNumber) || pageNumber < 1) return {};
  const bounds = surface.getBoundingClientRect();
  if (bounds.width <= 0 || bounds.height <= 0) return {};
  const normalized_rects: NonNullable<SelectedLocation["normalized_rects"]> = [];
  for (const rect of range.getClientRects()) {
    const left = Math.max(bounds.left, rect.left);
    const top = Math.max(bounds.top, rect.top);
    const right = Math.min(bounds.right, rect.right);
    const bottom = Math.min(bounds.bottom, rect.bottom);
    if (right <= left || bottom <= top) continue;
    normalized_rects.push({
      x: Math.max(0, Math.min(1, (left - bounds.left) / bounds.width)),
      y: Math.max(0, Math.min(1, (top - bounds.top) / bounds.height)),
      width: Math.max(0, Math.min(1, (right - left) / bounds.width)),
      height: Math.max(0, Math.min(1, (bottom - top) / bounds.height)),
    });
  }
  if (!normalized_rects.length) return {};
  return { page_number: pageNumber, exact_quote: text.slice(0, 4000), normalized_rects };
}

export default function PublicationGovernancePanel({
  open,
  onClose,
  tenant,
  manualId,
  revisionId,
  currentPage,
  activeSectionId,
  viewMode,
  onAnnotationsChanged,
}: {
  open: boolean;
  onClose: () => void;
  tenant: string;
  manualId: string;
  revisionId: string;
  currentPage: number;
  activeSectionId?: string;
  viewMode: "layout" | "text";
  onAnnotationsChanged?: (items: ReaderAnnotation[]) => void;
}) {
  const [tab, setTab] = useState<Tab>("annotations");
  const [manifest, setManifest] = useState<ReaderManifest | null>(null);
  const [annotations, setAnnotations] = useState<ReaderAnnotation[]>([]);
  const [evidence, setEvidence] = useState<ReaderEvidence | null>(null);
  const [snapshots, setSnapshots] = useState<Array<Record<string, unknown>>>([]);
  const [comparison, setComparison] = useState<ReaderComparison | null>(null);
  const [migrations, setMigrations] = useState<AnnotationMigration[]>([]);
  const [sourceRevisionId, setSourceRevisionId] = useState("");
  const [note, setNote] = useState("");
  const [tags, setTags] = useState("");
  const [linkedType, setLinkedType] = useState("");
  const [linkedId, setLinkedId] = useState("");
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState("");

  const otherRevisions = useMemo(
    () => (manifest?.revision_options || []).filter((revision) => revision.id !== revisionId),
    [manifest, revisionId],
  );
  const currentAnnotations = useMemo(
    () => annotations.filter((item) => !item.location?.page_number || item.location.page_number === currentPage),
    [annotations, currentPage],
  );

  const loadManifest = useCallback(async () => {
    const value = await getReaderManifest(tenant, manualId, revisionId);
    setManifest(value);
    setSourceRevisionId((current) => current || value.revision_options.find((item) => item.id !== revisionId)?.id || "");
  }, [manualId, revisionId, tenant]);

  const loadAnnotations = useCallback(async () => {
    const value = await listReaderAnnotations(tenant, manualId, revisionId);
    setAnnotations(value.items);
    onAnnotationsChanged?.(value.items);
  }, [manualId, onAnnotationsChanged, revisionId, tenant]);

  const loadEvidence = useCallback(async () => {
    const [value, stored] = await Promise.all([
      getReaderEvidence(tenant, manualId, revisionId),
      listEvidenceSnapshots(tenant, manualId, revisionId),
    ]);
    setEvidence(value);
    setSnapshots(stored);
  }, [manualId, revisionId, tenant]);

  const loadCompare = useCallback(async () => {
    if (!sourceRevisionId || sourceRevisionId === revisionId) {
      setComparison(null);
      return;
    }
    const value = await compareReaderRevisions(tenant, manualId, sourceRevisionId, revisionId);
    setComparison(value);
    if (value.capabilities.control) {
      setMigrations(await listAnnotationMigrations(tenant, manualId, revisionId));
    }
  }, [manualId, revisionId, sourceRevisionId, tenant]);

  useEffect(() => {
    if (!open) return;
    setError("");
    void loadManifest().catch((caught) => setError(caught instanceof Error ? caught.message : "Reader governance is unavailable."));
  }, [loadManifest, open]);

  useEffect(() => {
    if (!open) return;
    const loader = tab === "annotations" ? loadAnnotations : tab === "evidence" ? loadEvidence : loadCompare;
    void loader().catch((caught) => setError(caught instanceof Error ? caught.message : "Reader governance could not be loaded."));
  }, [loadAnnotations, loadCompare, loadEvidence, open, tab]);

  const createAnnotation = async (annotationType: "NOTE" | "BOOKMARK" | "HIGHLIGHT" | "EVIDENCE") => {
    if (!manifest?.source_sha256) {
      setError("This revision has no immutable source checksum, so governed annotations are disabled.");
      return;
    }
    setBusy(true);
    setError("");
    try {
      const selected = viewMode === "text" ? selectedSemanticLocation() : selectedPdfLocation();
      if (annotationType === "HIGHLIGHT" && !selected.exact_quote) {
        setError("Select text in the document before creating a highlight.");
        return;
      }
      const semanticSection = selected.section_id || (viewMode === "text" ? activeSectionId : undefined);
      const pageNumber = selected.page_number || (viewMode === "layout" ? currentPage : undefined);
      const effectiveType = annotationType;
      await createReaderAnnotation(tenant, manualId, revisionId, {
        expected_source_sha256: manifest.source_sha256,
        annotation_type: effectiveType,
        color: effectiveType === "HIGHLIGHT" ? "YELLOW" : effectiveType === "BOOKMARK" ? "BLUE" : "AMBER",
        visibility: "PRIVATE",
        note_text: note.trim() || (effectiveType === "BOOKMARK" ? `Bookmark page ${currentPage}` : null),
        tags: tags.split(",").map((tag) => tag.trim()).filter(Boolean),
        linked_entity_type: annotationType === "EVIDENCE" ? linkedType : undefined,
        linked_entity_id: annotationType === "EVIDENCE" ? linkedId.trim() : undefined,
        location: {
          location_type: selected.exact_quote ? "TEXT_SELECTION" : semanticSection ? "SECTION" : "PAGE",
          page_number: pageNumber,
          section_id: semanticSection,
          exact_quote: selected.exact_quote,
          normalized_rects: selected.normalized_rects || [],
          adapter_name: pageNumber ? "PDF_CANONICAL_PAGE" : "SEMANTIC_SECTION_BLOCK",
          adapter_version: "1",
        },
      });
      setNote("");
      setTags("");
      if (annotationType === "EVIDENCE") { setLinkedType(""); setLinkedId(""); }
      await loadAnnotations();
    } catch (caught) {
      setError(caught instanceof Error ? caught.message : "Annotation could not be created.");
    } finally {
      setBusy(false);
    }
  };

  const archiveAnnotation = async (annotation: ReaderAnnotation) => {
    setBusy(true);
    try {
      await updateReaderAnnotation(tenant, manualId, revisionId, annotation.id, { status: "ARCHIVED" });
      await loadAnnotations();
    } catch (caught) {
      setError(caught instanceof Error ? caught.message : "Annotation could not be archived.");
    } finally {
      setBusy(false);
    }
  };

  const downloadSnapshot = async (snapshotId: string) => {
    setBusy(true);
    setError("");
    try {
      const value = await getEvidenceSnapshot(tenant, manualId, revisionId, snapshotId);
      const blob = new Blob([JSON.stringify(value, null, 2)], { type: "application/json" });
      const url = URL.createObjectURL(blob);
      const link = document.createElement("a");
      link.href = url;
      link.download = `document-evidence-${manualId}-${revisionId}-${snapshotId}.json`;
      document.body.appendChild(link);
      link.click();
      link.remove();
      URL.revokeObjectURL(url);
    } catch (caught) {
      setError(caught instanceof Error ? caught.message : "Evidence snapshot could not be exported.");
    } finally {
      setBusy(false);
    }
  };

  const createSnapshot = async () => {
    setBusy(true);
    setError("");
    try {
      await createEvidenceSnapshot(tenant, manualId, revisionId);
      await loadEvidence();
    } catch (caught) {
      setError(caught instanceof Error ? caught.message : "Evidence snapshot could not be created.");
    } finally {
      setBusy(false);
    }
  };

  const prepareMigrations = async () => {
    if (!sourceRevisionId) return;
    setBusy(true);
    setError("");
    try {
      await prepareAnnotationMigrations(tenant, manualId, sourceRevisionId, revisionId);
      setMigrations(await listAnnotationMigrations(tenant, manualId, revisionId));
      await loadCompare();
    } catch (caught) {
      setError(caught instanceof Error ? caught.message : "Migration review could not be prepared.");
    } finally {
      setBusy(false);
    }
  };

  const decideMigration = async (migration: AnnotationMigration, decision: "ACCEPT" | "REJECT") => {
    const comments = window.prompt(`${decision === "ACCEPT" ? "Accept" : "Reject"} migration review comments`, decision === "ACCEPT" ? "Reviewed against the target revision." : "Target location is not equivalent.");
    if (!comments?.trim()) return;
    setBusy(true);
    try {
      await decideAnnotationMigration(tenant, manualId, migration.id, decision, comments.trim());
      setMigrations(await listAnnotationMigrations(tenant, manualId, revisionId));
      await loadAnnotations();
    } catch (caught) {
      setError(caught instanceof Error ? caught.message : "Migration decision could not be saved.");
    } finally {
      setBusy(false);
    }
  };

  if (!open) return null;

  return (
    <aside className="publication-governance-panel" aria-label="Document governance workspace">
      <header className="publication-governance-panel__head">
        <div><span>CONTROLLED CONTEXT</span><strong>Reader governance</strong><small>Revision-bound notes, evidence and change review.</small></div>
        <button type="button" onClick={onClose} aria-label="Close reader governance"><X size={18} /></button>
      </header>

      <nav className="publication-governance-tabs" aria-label="Reader governance tabs">
        <button type="button" className={tab === "annotations" ? "active" : ""} onClick={() => setTab("annotations")}><MessageSquareText size={15} /> Annotations</button>
        <button type="button" className={tab === "evidence" ? "active" : ""} onClick={() => setTab("evidence")}><ShieldCheck size={15} /> Evidence</button>
        <button type="button" className={tab === "compare" ? "active" : ""} onClick={() => setTab("compare")}><FileDiff size={15} /> Compare</button>
      </nav>

      {error ? <div className="publication-governance-error" role="alert">{error}</div> : null}

      <div className="publication-governance-panel__body">
        {tab === "annotations" ? (
          <>
            <section className="publication-governance-context">
              <span>Current context</span><strong>{viewMode === "layout" ? `Physical page ${currentPage}` : "Accessible text"}</strong>
              <small>{manifest?.source_sha256 ? `Source ${manifest.source_sha256.slice(0, 12)}…` : "Checksum unavailable"}</small>
            </section>
            <section className="publication-governance-compose">
              <textarea value={note} onChange={(event) => setNote(event.target.value)} placeholder="Add a revision-bound note or select text in accessible-text mode before highlighting…" rows={3} />
              <input value={tags} onChange={(event) => setTags(event.target.value)} placeholder="Tags, comma separated" />
              {manifest?.capabilities.control ? <div className="publication-governance-linked-evidence">
                <select value={linkedType} onChange={(event) => setLinkedType(event.target.value)} aria-label="Linked QMS record type">
                  <option value="">No QMS link</option>
                  <option value="QMS_AUDIT">QMS audit</option>
                  <option value="QMS_FINDING">Audit finding</option>
                  <option value="QMS_CORRECTIVE_ACTION">Corrective action</option>
                </select>
                <input value={linkedId} onChange={(event) => setLinkedId(event.target.value)} placeholder="QMS record UUID" disabled={!linkedType} />
              </div> : null}
              <div>
                <button type="button" disabled={busy || !manifest?.capabilities.annotations} onClick={() => void createAnnotation("NOTE")}><MessageSquareText size={14} /> Note</button>
                <button type="button" disabled={busy || !manifest?.capabilities.annotations} onClick={() => void createAnnotation("BOOKMARK")}><BookmarkPlus size={14} /> Bookmark</button>
                <button type="button" disabled={busy || !manifest?.capabilities.annotations} onClick={() => void createAnnotation("HIGHLIGHT")}><Highlighter size={14} /> Highlight selection</button>
                {manifest?.capabilities.control ? <button type="button" disabled={busy || !manifest?.capabilities.annotations || !linkedType || !linkedId.trim()} onClick={() => void createAnnotation("EVIDENCE")}><ClipboardCheck size={14} /> Link QMS evidence</button> : null}
              </div>
            </section>
            <section className="publication-governance-list">
              <header><strong>Active annotations</strong><button type="button" onClick={() => void loadAnnotations()} aria-label="Refresh annotations"><RefreshCw size={14} /></button></header>
              {currentAnnotations.length ? currentAnnotations.map((annotation) => (
                <article key={annotation.id}>
                  <div className="publication-governance-list__meta"><span>{annotation.annotation_type}</span><small>{annotation.visibility} · {annotation.location?.page_number ? `p. ${annotation.location.page_number}` : annotation.location?.location_type}</small></div>
                  {annotation.location?.exact_quote ? <blockquote>{annotation.location.exact_quote}</blockquote> : null}
                  {annotation.note_text ? <p>{annotation.note_text}</p> : null}
                  {annotation.tags.length ? <small>{annotation.tags.join(" · ")}</small> : null}
                  <div className="publication-governance-list__actions"><a href={annotation.reader_url}><Link2 size={13} /> Deep link</a><button type="button" disabled={busy} onClick={() => void archiveAnnotation(annotation)}><Archive size={13} /> Archive</button></div>
                </article>
              )) : <p className="publication-governance-empty">No active annotations in the current reader context.</p>}
            </section>
          </>
        ) : null}

        {tab === "evidence" ? (
          <>
            <section className="publication-governance-evidence-card">
              <span>Revision identity</span><strong>{evidence?.document.code} · Rev {evidence?.revision.revision_number || "—"}</strong>
              <dl>
                <div><dt>Checksum</dt><dd>{evidence?.revision.source_sha256 || "Not recorded"}</dd></div>
                <div><dt>Immutable</dt><dd>{evidence?.revision.immutable_locked ? "Yes" : "No"}</dd></div>
                <div><dt>Effective</dt><dd>{evidence?.revision.effective_date || "Not recorded"}</dd></div>
                <div><dt>Workflow</dt><dd>{evidence?.workflow?.state?.replaceAll("_", " ") || "No workflow"}</dd></div>
                <div><dt>Reference health</dt><dd>{counter(evidence?.reference_health)}</dd></div>
                <div><dt>Relationships</dt><dd>{counter(evidence?.relationship_summary)}</dd></div>
                <div><dt>Annotations</dt><dd>{evidence?.annotations.count ?? 0}</dd></div>
                <div><dt>Audit events</dt><dd>{evidence?.audit_history.length ?? 0}</dd></div>
                <div><dt>Reader adapter</dt><dd>{manifest?.renderer || "—"} · {manifest?.location_adapter || "—"}</dd></div>
              </dl>
              {evidence?.capabilities.snapshot ? <button type="button" disabled={busy} onClick={() => void createSnapshot()}><FileKey2 size={14} /> Create immutable evidence snapshot</button> : null}
            </section>
            <section className="publication-governance-list">
              <header><strong>Stored snapshots</strong><span>{snapshots.length}</span></header>
              {snapshots.length ? snapshots.map((snapshot, index) => <article key={String(snapshot.id || index)}><strong>{String(snapshot.snapshot_sha256 || "")}</strong><small>{formatDate(String(snapshot.created_at || ""))} · source {String(snapshot.source_sha256 || "not recorded")}</small><div className="publication-governance-list__actions"><button type="button" disabled={busy || !snapshot.id} onClick={() => void downloadSnapshot(String(snapshot.id))}><Download size={13} /> Download verified JSON</button></div></article>) : <p className="publication-governance-empty">No immutable evidence snapshot has been created for this revision.</p>}
            </section>
          </>
        ) : null}

        {tab === "compare" ? (
          <>
            <section className="publication-governance-compare-controls">
              <label><span>Compare prior/source revision</span><select value={sourceRevisionId} onChange={(event) => setSourceRevisionId(event.target.value)}><option value="">Select revision</option>{otherRevisions.map((revision) => <option key={revision.id} value={revision.id}>Issue {revision.issue_number || "—"} · Rev {revision.revision_number} · {revision.status}</option>)}</select></label>
              <button type="button" disabled={!sourceRevisionId || busy} onClick={() => void loadCompare()}><FileDiff size={14} /> Compare with current</button>
              {comparison?.capabilities.prepare_migrations ? <button type="button" disabled={busy} onClick={() => void prepareMigrations()}><ClipboardCheck size={14} /> Prepare annotation migration review</button> : null}
            </section>
            {comparison ? <section className="publication-governance-diff-summary"><strong>Revision change summary</strong><div>{Object.entries(comparison.summary).map(([status, count]) => <span key={status}>{status.replaceAll("_", " ")} <b>{count}</b></span>)}</div></section> : null}
            {comparison ? <section className="publication-governance-diff-list">{comparison.sections.slice(0, 250).map((section, index) => <article key={`${section.source_section_id || "new"}:${section.target_section_id || index}`} className={`is-${section.status.toLowerCase()}`}><span>{section.status}</span><div><strong>{section.source_heading || "New section"}</strong>{section.target_heading && section.target_heading !== section.source_heading ? <small>→ {section.target_heading}</small> : null}<small>{section.strategy.replaceAll("_", " ")} · {section.source_block_count} → {section.target_block_count} blocks</small></div></article>)}</section> : null}
            {migrations.length ? <section className="publication-governance-list"><header><strong>Annotation migration review</strong><span>{migrations.filter((item) => item.status === "PENDING").length} pending</span></header>{migrations.map((migration) => <article key={migration.id}><div className="publication-governance-list__meta"><span>{migration.strategy.replaceAll("_", " ")}</span><small>{migration.confidence_percent}% confidence · {migration.status}</small></div><p>{migration.reason || "No proposal reason recorded."}</p>{migration.status === "PENDING" ? <div className="publication-governance-list__actions"><button type="button" disabled={busy || migration.strategy === "UNRESOLVED"} onClick={() => void decideMigration(migration, "ACCEPT")}><Check size={13} /> Accept</button><button type="button" disabled={busy} onClick={() => void decideMigration(migration, "REJECT")}><XCircle size={13} /> Reject</button></div> : null}</article>)}</section> : null}
          </>
        ) : null}
      </div>
    </aside>
  );
}
