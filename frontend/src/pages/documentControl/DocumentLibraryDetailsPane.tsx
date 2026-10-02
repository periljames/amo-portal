import { useEffect, useMemo, useState } from "react";
import {
  Activity,
  BookOpen,
  FileClock,
  GitBranch,
  Send,
  ShieldCheck,
  X,
} from "lucide-react";

import {
  getDocumentControlDocument,
  type DocumentDetailResponse,
} from "../../services/documentControl";
import type { IntegratedLibraryItem, LibraryDiscoveryItem } from "../../services/documentLibrary";
import { DocumentControlError, DocumentControlLoading, DocumentControlStatus } from "./DocumentControlShell";

type SelectedLibraryItem =
  | { mode: "integrated"; item: IntegratedLibraryItem }
  | { mode: "discovery"; item: LibraryDiscoveryItem };

type DetailTab = "details" | "versions" | "relationships" | "distribution" | "read-status" | "compliance" | "activity";

type Props = {
  tenant: string;
  selected: SelectedLibraryItem;
  canControl: boolean;
  onClose: () => void;
  onRead: () => void;
  onOpenWorkspace?: () => void;
};

const TABS: Array<{ id: DetailTab; label: string; icon: typeof BookOpen }> = [
  { id: "details", label: "Details", icon: BookOpen },
  { id: "versions", label: "Versions", icon: FileClock },
  { id: "relationships", label: "Relationships", icon: GitBranch },
  { id: "distribution", label: "Distribution", icon: Send },
  { id: "read-status", label: "Read status", icon: BookOpen },
  { id: "compliance", label: "Compliance", icon: ShieldCheck },
  { id: "activity", label: "Activity", icon: Activity },
];

function formatDate(value?: string | null): string {
  if (!value) return "—";
  const parsed = new Date(value.length === 10 ? `${value}T00:00:00` : value);
  return Number.isNaN(parsed.getTime())
    ? value
    : parsed.toLocaleString([], value.length === 10
      ? { dateStyle: "medium" }
      : { dateStyle: "medium", timeStyle: "short" });
}

function revisionLabel(revision?: { issue_number?: string | null; revision_number?: string | null } | null): string {
  if (!revision) return "No revision";
  return `${revision.issue_number ? `Issue ${revision.issue_number} · ` : ""}Rev ${revision.revision_number || "—"}`;
}

function selectedFacts(selected: SelectedLibraryItem) {
  if (selected.mode === "integrated") {
    const item = selected.item;
    const revision = item.current_revision || item.latest_revision;
    return {
      id: item.id,
      code: item.code,
      title: item.title,
      type: item.library.node_type,
      hierarchy: item.library.structure_path || "—",
      owner: item.library.owner?.assignee?.name || item.profile.owner_department || item.owner_role || "Unassigned",
      department: item.library.responsible_department?.assignee?.name || item.profile.owner_department || "—",
      status: item.read_target.control_status || item.status,
      revision,
      reviewDue: item.profile.next_review_due,
      classification: String(item.profile.metadata?.classification || item.profile.document_class || "—"),
      tags: item.profile.tags || [],
      source: item.library.external?.provider || String(item.profile.metadata?.source_issuer || "Internal"),
      physical: item.library.physical,
    };
  }
  const item = selected.item;
  const revision = item.current_revision || item.latest_revision;
  return {
    id: item.id,
    code: item.code,
    title: item.title,
    type: item.node.type,
    hierarchy: item.node.path || "—",
    owner: item.owner.name || item.owner.department || "Unassigned",
    department: item.owner.department || "—",
    status: item.lifecycle_status,
    revision,
    reviewDue: item.next_review_due,
    classification: item.document_class,
    tags: [] as string[],
    source: revision?.source_filename ? "Controlled source" : "—",
    physical: null,
  };
}

function visibleTabs(detail: DocumentDetailResponse | null, canControl: boolean): DetailTab[] {
  if (!detail) return ["details", "versions"];
  const tabs: DetailTab[] = ["details", "versions"];
  if (detail.integrations.length) tabs.push("relationships");
  if (detail.distribution_campaigns.length) {
    tabs.push("distribution");
    tabs.push("read-status");
  }
  if (canControl && (detail.external_sources.length || detail.applicability.length || detail.reviews.length)) tabs.push("compliance");
  if (canControl && detail.history.length) tabs.push("activity");
  return tabs;
}

export default function DocumentLibraryDetailsPane({
  tenant,
  selected,
  canControl,
  onClose,
  onRead,
  onOpenWorkspace,
}: Props) {
  const facts = useMemo(() => selectedFacts(selected), [selected]);
  const [detail, setDetail] = useState<DocumentDetailResponse | null>(null);
  const [activeTab, setActiveTab] = useState<DetailTab>("details");
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState("");

  useEffect(() => {
    let cancelled = false;
    setLoading(true);
    setError("");
    setActiveTab("details");
    void getDocumentControlDocument(tenant, facts.id)
      .then((response) => {
        if (!cancelled) setDetail(response);
      })
      .catch((caught) => {
        if (!cancelled) setError(caught instanceof Error ? caught.message : "Document details could not be loaded.");
      })
      .finally(() => {
        if (!cancelled) setLoading(false);
      });
    return () => { cancelled = true; };
  }, [facts.id, tenant]);

  const allowedTabs = visibleTabs(detail, canControl);
  useEffect(() => {
    if (!allowedTabs.includes(activeTab)) setActiveTab("details");
  }, [activeTab, allowedTabs]);

  const retry = () => {
    setLoading(true);
    setError("");
    void getDocumentControlDocument(tenant, facts.id)
      .then(setDetail)
      .catch((caught) => setError(caught instanceof Error ? caught.message : "Document details could not be loaded."))
      .finally(() => setLoading(false));
  };

  return <aside className="dlibrary-details" aria-label={`Document details for ${facts.code}`}>
    <header className="dlibrary-details__head">
      <div>
        <small>{facts.code}</small>
        <h2>{facts.title}</h2>
        <span>{facts.type.replaceAll("_", " ")} · {revisionLabel(facts.revision)}</span>
      </div>
      <button type="button" className="dlibrary-details__close" aria-label="Close document details" onClick={onClose}><X size={17} /></button>
    </header>

    <div className="dlibrary-details__actions">
      <button type="button" className="dc-button dc-button--primary" disabled={!facts.revision?.id} onClick={onRead}>Read</button>
      {canControl && onOpenWorkspace ? <button type="button" className="dc-button" onClick={onOpenWorkspace}>Open workspace</button> : null}
    </div>

    <nav className="dlibrary-details__tabs" aria-label="Document detail sections">
      {TABS.filter((tab) => allowedTabs.includes(tab.id)).map(({ id, label, icon: Icon }) =>
        <button type="button" key={id} className={activeTab === id ? "active" : ""} aria-current={activeTab === id ? "page" : undefined} onClick={() => setActiveTab(id)}>
          <Icon size={14} /><span>{label}</span>
        </button>)}
    </nav>

    <div className="dlibrary-details__body">
      {loading ? <DocumentControlLoading label="Loading document details…" /> : null}
      {error && !loading ? <DocumentControlError message={error} retry={retry} /> : null}

      {!loading && !error && activeTab === "details" ? <dl className="dlibrary-details__facts">
        <div><dt>Code</dt><dd>{facts.code}</dd></div>
        <div><dt>Type</dt><dd>{facts.type.replaceAll("_", " ")}</dd></div>
        <div><dt>Revision</dt><dd>{revisionLabel(facts.revision)}</dd></div>
        <div><dt>Status</dt><dd><DocumentControlStatus status={facts.status || "UNKNOWN"} /></dd></div>
        <div><dt>Effective</dt><dd>{formatDate(facts.revision?.effective_date)}</dd></div>
        <div><dt>Owner</dt><dd>{facts.owner}</dd></div>
        <div><dt>Responsible department</dt><dd>{facts.department}</dd></div>
        <div><dt>Review due</dt><dd>{formatDate(facts.reviewDue)}</dd></div>
        <div><dt>Classification</dt><dd>{facts.classification}</dd></div>
        <div><dt>Hierarchy</dt><dd>{facts.hierarchy}</dd></div>
        <div><dt>Source</dt><dd>{facts.source}</dd></div>
        <div><dt>Filename</dt><dd>{facts.revision?.source_filename || "—"}</dd></div>
        {facts.physical ? <div><dt>Physical availability</dt><dd>{facts.physical.on_shelf} on shelf · {facts.physical.checked_out} checked out</dd></div> : null}
        {facts.tags.length ? <div className="wide"><dt>Tags</dt><dd>{facts.tags.join(", ")}</dd></div> : null}
      </dl> : null}

      {!loading && !error && activeTab === "versions" ? <div className="dlibrary-details__timeline">
        {(detail?.revisions || []).map((revision) => <article key={revision.id}>
          <div><strong>{revisionLabel(revision)}</strong><span>{revision.status.replaceAll("_", " ")}</span></div>
          <small>{revision.source_filename || revision.source_type || "Controlled revision"}</small>
          <time>{formatDate(revision.effective_date || revision.created_at)}</time>
        </article>)}
        {!detail?.revisions.length ? <p>No visible revision history is available for your access level.</p> : null}
      </div> : null}

      {!loading && !error && activeTab === "relationships" ? <div className="dlibrary-details__list">
        {detail?.integrations.map((row) => <article key={row.id}>
          <strong>{row.relation_type.replaceAll("_", " ")}</strong>
          <span>{row.source_module.replaceAll("_", " ")} · {row.entity_type.replaceAll("_", " ")}</span>
          <small>{row.blocking ? "Blocking governed relationship" : "Governed relationship"}</small>
        </article>)}
      </div> : null}

      {!loading && !error && activeTab === "distribution" ? <div className="dlibrary-details__list">
        {detail?.distribution_campaigns.map((campaign) => <article key={campaign.id}>
          <strong>{campaign.title}</strong>
          <span>{campaign.status.replaceAll("_", " ")}</span>
          <small>{campaign.acknowledgement_required ? "Acknowledgement required" : "Information distribution"} · due {formatDate(campaign.due_at)}</small>
        </article>)}
      </div> : null}

      {!loading && !error && activeTab === "read-status" ? <div className="dlibrary-details__list">
        {detail?.distribution_campaigns.map((campaign) => <article key={campaign.id}>
          <strong>{campaign.title}</strong>
          <span>{Object.entries(campaign.recipients || {}).map(([state, count]) => `${state.replaceAll("_", " ")}: ${count}`).join(" · ") || "No recipient status summary"}</span>
          <small>{campaign.acknowledgement_required ? "Controlled read-and-understood tracking" : "Acknowledgement not required"}</small>
        </article>)}
      </div> : null}

      {!loading && !error && activeTab === "compliance" ? <>
        <div className="dlibrary-details__list">
          {detail?.external_sources.map((source) => <article key={source.id}>
            <strong>{source.authority || source.provider}</strong>
            <span>{source.status.replaceAll("_", " ")}</span>
            <small>Next currency check {formatDate(source.next_check_due_at)}</small>
          </article>)}
          {detail?.applicability.map((rule) => <article key={rule.id}>
            <strong>{rule.rule_type.replaceAll("_", " ")}</strong>
            <span>{rule.status.replaceAll("_", " ")}</span>
            <small>{rule.source}</small>
          </article>)}
          {detail?.reviews.map((review) => <article key={review.id}>
            <strong>Periodic review</strong>
            <span>{review.status.replaceAll("_", " ")}</span>
            <small>Due {formatDate(review.due_at)}</small>
          </article>)}
        </div>
      </> : null}

      {!loading && !error && activeTab === "activity" ? <div className="dlibrary-details__timeline">
        {detail?.history.map((row) => <article key={row.id}>
          <div><strong>{row.action.replaceAll("_", " ")}</strong><span>{row.entity_type.replaceAll("_", " ")}</span></div>
          <time>{formatDate(row.at)}</time>
        </article>)}
      </div> : null}
    </div>
  </aside>;
}
