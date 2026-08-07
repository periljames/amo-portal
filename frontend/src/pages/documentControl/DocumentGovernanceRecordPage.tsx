import { useCallback, useEffect, useMemo, useState } from "react";
import {
  AlertTriangle,
  BookOpen,
  Check,
  ChevronRight,
  FileCheck2,
  FileSearch,
  FolderTree,
  History,
  Link2,
  Network,
  RefreshCw,
  ShieldCheck,
  UserRoundCog,
  X,
} from "lucide-react";
import { useNavigate } from "react-router-dom";

import {
  createResponsibility,
  decideDetectedReference,
  decideRelationship,
  decideResponsibility,
  getDocumentGovernance,
  reindexGovernedRevision,
  type DetectedReference,
  type GovernanceDetail,
  type GovernanceRelationship,
  type ResponsibilityAssignment,
} from "../../services/documentGovernance";
import DocumentControlShell, {
  DocumentControlEmpty,
  DocumentControlError,
  DocumentControlLoading,
  DocumentControlStatus,
} from "./DocumentControlShell";
import { useDocumentControlRoute } from "./documentControlRoute";
import "./documentGovernance.css";

const RESPONSIBILITIES = [
  ["BUSINESS_OWNER", "Business owner"],
  ["DOCUMENT_OWNER", "Document owner"],
  ["RESPONSIBLE_DEPARTMENT", "Responsible department"],
  ["RESPONSIBLE_ORG_UNIT", "Responsible section or organization unit"],
  ["ACCOUNTABLE_ROLE", "Accountable role"],
  ["DOCUMENT_CONTROLLER", "Document controller"],
  ["CUSTODIAN", "Custodian"],
  ["TECHNICAL_REVIEWER", "Technical reviewer"],
  ["QUALITY_REVIEWER", "Quality reviewer"],
  ["APPROVER", "Approver"],
  ["RETENTION_OWNER", "Retention owner"],
] as const;

const RELATIONSHIP_GROUPS: Array<[string, string[]]> = [
  ["Forms and templates", ["HAS_FORM", "HAS_TEMPLATE", "HAS_CHECKLIST", "FORM_FOR"]],
  ["Procedures and instructions", ["IMPLEMENTS", "SUPPORTS", "REFERENCES", "REQUIRES", "REQUIRED_BY"]],
  ["Records generated", ["GENERATES_RECORD", "EVIDENCE_FOR"]],
  ["Regulations", ["LINKED_REGULATION"]],
  ["Audit and corrective action", ["LINKED_AUDIT", "LINKED_FINDING", "LINKED_CAR"]],
  ["Training and change", ["TRAINING_REQUIRED_BY", "LINKED_CHANGE_PROPOSAL"]],
  ["Supersession", ["SUPERSEDES", "SUPERSEDED_BY", "AMENDS"]],
];

function label(value: string): string {
  return value.replaceAll("_", " ").toLowerCase().replace(/(^|\s)\S/g, (part) => part.toUpperCase());
}

function kind(status: string): "success" | "warning" | "danger" | "info" | "neutral" {
  const value = status.toUpperCase();
  if (["CONFIRMED", "COMPLETED", "PUBLISHED", "ACTIVE", "CURRENT"].includes(value)) return "success";
  if (["REJECTED", "FAILED", "CONFLICT", "BROKEN", "SUPERSEDED"].includes(value)) return "danger";
  if (["DETECTED", "UNRESOLVED", "MATCH_PROPOSED", "PENDING", "RUNNING", "AUTO_RESOLVED"].includes(value)) return "warning";
  return "neutral";
}

function ResponsibilityRow({
  type,
  title,
  assignments,
  canControl,
  reviewing,
  onDecision,
}: {
  type: string;
  title: string;
  assignments: ResponsibilityAssignment[];
  canControl: boolean;
  reviewing: string;
  onDecision: (row: ResponsibilityAssignment, decision: "CONFIRMED" | "REJECTED") => void;
}) {
  const current = assignments[0];
  return (
    <div className="dgov-responsibility" data-responsibility={type}>
      <div><strong>{title}</strong><small>{current ? `${current.assignment_source} · ${current.confidence_percent}% confidence` : "No effective assignment"}</small></div>
      <div className="dgov-responsibility__value">
        {current ? <><span>{current.assignee.name}</span><DocumentControlStatus status={current.confirmation_status} kind={kind(current.confirmation_status)} /></> : <span className="dgov-warning"><AlertTriangle size={14} /> Resolve required</span>}
      </div>
      <div><small>{current ? `${current.effective_from} → ${current.effective_to || "open-ended"}` : "Assign an accountable person, role, department or unit."}</small></div>
      {canControl && current && ["DETECTED", "UNRESOLVED", "MATCH_PROPOSED", "CONFLICT"].includes(current.confirmation_status) ? (
        <div className="dgov-row-actions">
          <button type="button" disabled={reviewing === current.id} onClick={() => onDecision(current, "CONFIRMED")}><Check size={14} /> Confirm</button>
          <button type="button" disabled={reviewing === current.id} onClick={() => onDecision(current, "REJECTED")}><X size={14} /> Reject</button>
        </div>
      ) : null}
    </div>
  );
}

function RelationshipCard({
  row,
  canControl,
  reviewing,
  onDecision,
  openSource,
  openTarget,
}: {
  row: GovernanceRelationship;
  canControl: boolean;
  reviewing: string;
  onDecision: (row: GovernanceRelationship, decision: "CONFIRMED" | "REJECTED") => void;
  openSource: (row: GovernanceRelationship) => void;
  openTarget: (row: GovernanceRelationship) => void;
}) {
  return (
    <article className="dgov-relationship">
      <div className="dgov-relationship__head"><strong>{label(row.relationship_type)}</strong><DocumentControlStatus status={row.resolution_status} kind={kind(row.resolution_status)} /></div>
      <h4>{row.target_manual ? `${row.target_manual.code} · ${row.target_manual.title}` : `${label(row.target_entity_type)} · ${row.target_entity_id || "Unresolved target"}`}</h4>
      <p>{row.exact_quote || row.exact_token || "Manually governed relationship; no extracted quote is stored."}</p>
      <div className="dgov-meta"><span>{row.relationship_source}</span><span>{row.confidence_percent}% confidence</span>{row.page_number ? <span>Page {row.page_number}</span> : null}</div>
      <div className="dgov-row-actions">
        {row.source_revision_id && row.page_number ? <button type="button" onClick={() => openSource(row)}>Open source</button> : null}
        {row.target_manual ? <button type="button" onClick={() => openTarget(row)}>Open target</button> : null}
        {canControl && ["DETECTED", "UNRESOLVED", "MATCH_PROPOSED", "CONFLICT"].includes(row.resolution_status) ? <>
          <button type="button" disabled={reviewing === row.id} onClick={() => onDecision(row, "CONFIRMED")}><Check size={14} /> Confirm</button>
          <button type="button" disabled={reviewing === row.id} onClick={() => onDecision(row, "REJECTED")}><X size={14} /> Reject</button>
        </> : null}
      </div>
    </article>
  );
}

export default function DocumentGovernanceRecordPage() {
  const navigate = useNavigate();
  const { tenant, docId, basePath, readerBasePath } = useDocumentControlRoute();
  const [data, setData] = useState<GovernanceDetail | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState("");
  const [reviewing, setReviewing] = useState("");
  const [reindexing, setReindexing] = useState(false);
  const [showAssignment, setShowAssignment] = useState(false);
  const [assignment, setAssignment] = useState({ responsibility_type: "DOCUMENT_OWNER", assignee_type: "USER", assignee_id: "", role: "", effective_from: new Date().toISOString().slice(0, 10) });

  const load = useCallback(async () => {
    if (!tenant || !docId) return;
    setLoading(true);
    setError("");
    try {
      setData(await getDocumentGovernance(tenant, docId));
    } catch (caught) {
      setError(caught instanceof Error ? caught.message : "The governed document record could not be loaded.");
    } finally {
      setLoading(false);
    }
  }, [tenant, docId]);

  useEffect(() => { void load(); }, [load]);

  const groupedRelationships = useMemo(() => {
    const result = new Map<string, GovernanceRelationship[]>();
    if (!data) return result;
    RELATIONSHIP_GROUPS.forEach(([group, types]) => result.set(group, data.relationships.filter((row) => types.includes(row.relationship_type))));
    const known = new Set(RELATIONSHIP_GROUPS.flatMap(([, types]) => types));
    result.set("Other governed links", data.relationships.filter((row) => !known.has(row.relationship_type)));
    return result;
  }, [data]);

  const reviewResponsibility = async (row: ResponsibilityAssignment, decision: "CONFIRMED" | "REJECTED") => {
    setReviewing(row.id);
    setError("");
    try {
      await decideResponsibility(tenant, row.id, decision, `${decision === "CONFIRMED" ? "Confirmed" : "Rejected"} in the governed document workspace.`);
      await load();
    } catch (caught) {
      setError(caught instanceof Error ? caught.message : "The responsibility decision failed.");
    } finally {
      setReviewing("");
    }
  };

  const reviewRelationship = async (row: GovernanceRelationship, decision: "CONFIRMED" | "REJECTED") => {
    setReviewing(row.id);
    setError("");
    try {
      await decideRelationship(tenant, row.id, decision, `${decision === "CONFIRMED" ? "Confirmed" : "Rejected"} in the governed document workspace.`);
      await load();
    } catch (caught) {
      setError(caught instanceof Error ? caught.message : "The relationship decision failed.");
    } finally {
      setReviewing("");
    }
  };

  const reviewDetectedReference = async (row: DetectedReference, decision: "CONFIRMED" | "REJECTED") => {
    setReviewing(row.id);
    setError("");
    try {
      await decideDetectedReference(tenant, row.id, decision, `${decision === "CONFIRMED" ? "Confirmed" : "Rejected"} from the exact detected occurrence.`);
      await load();
    } catch (caught) {
      setError(caught instanceof Error ? caught.message : "The detected reference decision failed.");
    } finally {
      setReviewing("");
    }
  };

  const submitAssignment = async () => {
    if (!docId || (!assignment.assignee_id && assignment.assignee_type !== "ROLE") || (assignment.assignee_type === "ROLE" && !assignment.role.trim())) return;
    setReviewing("new-assignment");
    setError("");
    try {
      await createResponsibility(tenant, docId, {
        responsibility_type: assignment.responsibility_type,
        assignee_type: assignment.assignee_type,
        assignee_user_id: assignment.assignee_type === "USER" ? assignment.assignee_id : null,
        assignee_department_id: assignment.assignee_type === "DEPARTMENT" ? assignment.assignee_id : null,
        assignee_org_unit_id: assignment.assignee_type === "ORG_UNIT" ? assignment.assignee_id : null,
        assignee_role: assignment.assignee_type === "ROLE" ? assignment.role : null,
        is_primary: true,
        effective_from: assignment.effective_from,
        assignment_source: "MANUAL",
        confidence_percent: 100,
        confirmation_status: "CONFIRMED",
        provenance: { interface: "document_governance_workspace" },
      });
      setShowAssignment(false);
      await load();
    } catch (caught) {
      setError(caught instanceof Error ? caught.message : "The responsibility could not be assigned.");
    } finally {
      setReviewing("");
    }
  };

  const reindex = async () => {
    const revisionId = data?.document.read_target.revision_id || data?.document.latest_revision?.id;
    if (!revisionId) return;
    setReindexing(true);
    setError("");
    try {
      await reindexGovernedRevision(tenant, revisionId);
      await load();
    } catch (caught) {
      setError(caught instanceof Error ? caught.message : "Reindexing could not be scheduled.");
    } finally {
      setReindexing(false);
    }
  };

  const openReader = (revisionId?: string | null, page?: number | null) => {
    if (!docId || !revisionId) return;
    const search = page ? `?page=${page}` : "";
    navigate(`${readerBasePath}/${docId}/rev/${revisionId}/read${search}`);
  };

  const document = data?.document;
  const canControl = Boolean(data?.capabilities.control);

  return (
    <DocumentControlShell
      title={document?.title || "Governed document"}
      eyebrow={document?.code || "DOCUMENT CONTROL"}
      subtitle={document ? `${document.manual_type} · ${document.profile.document_class} · ${data?.completeness.indexing_status.replaceAll("_", " ")}` : "Ownership, structure, relationships and immutable revision evidence"}
      canControl={canControl}
      actions={document ? <>
        <button type="button" className="dc-button" onClick={() => navigate(`${basePath}/library`)}>Back to library</button>
        <button type="button" className="dc-button dc-button--primary" disabled={!document.read_target.revision_id} onClick={() => openReader(document.read_target.revision_id)}><BookOpen size={15} /> {document.read_target.label}</button>
      </> : undefined}
    >
      {loading ? <DocumentControlLoading label="Loading governed document identity and relationships…" /> : null}
      {error ? <DocumentControlError message={error} retry={() => void load()} /> : null}
      {!loading && data && document ? (
        <div className="dgov-record" data-testid="document-governance-record">
          {data.issues.length ? <section className="dgov-alerts">{data.issues.map((issue) => <div key={issue.code}><AlertTriangle size={17} /><span><strong>{label(issue.code)}</strong> · {issue.count} item{issue.count === 1 ? "" : "s"} require controlled action.</span></div>)}</section> : <section className="dgov-clear"><ShieldCheck size={18} /> No unresolved high-level governance condition is currently reported.</section>}

          <section className="dgov-identity">
            <div><strong>{document.code}</strong><span>{document.title}</span><small>{document.manual_type}</small></div>
            <div><strong>{document.latest_revision?.issue_number ? `Issue ${document.latest_revision.issue_number}` : "Issue —"}</strong><span>Revision {document.latest_revision?.revision_number || "—"}</span><small>{document.latest_revision?.effective_date || "Not effective"}</small></div>
            <div><DocumentControlStatus status={document.status} kind={kind(document.status)} /><span>{document.profile.document_class}</span><small>{document.profile.restricted_flag ? "Restricted access" : "Standard controlled access"}</small></div>
            <div><strong>{document.latest_revision?.source_sha256 ? `${document.latest_revision.source_sha256.slice(0, 16)}…` : "Checksum missing"}</strong><span>Immutable source checksum</span><small>{document.latest_revision?.source_type || "Unknown source format"}</small></div>
          </section>

          <section className="dgov-panel">
            <header><div><UserRoundCog size={18} /><span><strong>Ownership and responsibility</strong><small>Separate accountable assignments with effective dates, provenance and review state.</small></span></div>{canControl ? <button type="button" className="dc-button" onClick={() => setShowAssignment((value) => !value)}>{showAssignment ? "Close assignment" : "Assign responsibility"}</button> : null}</header>
            {showAssignment && canControl ? <div className="dgov-assignment-form">
              <label>Responsibility<select value={assignment.responsibility_type} onChange={(event) => setAssignment({ ...assignment, responsibility_type: event.target.value })}>{RESPONSIBILITIES.map(([value, title]) => <option key={value} value={value}>{title}</option>)}</select></label>
              <label>Assignee type<select value={assignment.assignee_type} onChange={(event) => setAssignment({ ...assignment, assignee_type: event.target.value, assignee_id: "", role: "" })}><option value="USER">Named person</option><option value="DEPARTMENT">Department</option><option value="ORG_UNIT">Organization unit</option><option value="ROLE">Role</option></select></label>
              {assignment.assignee_type === "USER" ? <label>Person<select value={assignment.assignee_id} onChange={(event) => setAssignment({ ...assignment, assignee_id: event.target.value })}><option value="">Select person</option>{data.assignment_options.users.map((user) => <option key={user.id} value={user.id}>{user.name} · {user.email}</option>)}</select></label> : null}
              {assignment.assignee_type === "DEPARTMENT" ? <label>Department<select value={assignment.assignee_id} onChange={(event) => setAssignment({ ...assignment, assignee_id: event.target.value })}><option value="">Select department</option>{data.assignment_options.departments.map((department) => <option key={department.id} value={department.id}>{department.code} · {department.name}</option>)}</select></label> : null}
              {assignment.assignee_type === "ORG_UNIT" ? <label>Organization unit<select value={assignment.assignee_id} onChange={(event) => setAssignment({ ...assignment, assignee_id: event.target.value })}><option value="">Select organization unit</option>{data.assignment_options.org_units.map((unit) => <option key={unit.id} value={unit.id}>{unit.code} · {unit.name} ({unit.unit_type})</option>)}</select></label> : null}
              {assignment.assignee_type === "ROLE" ? <label>Role<input value={assignment.role} onChange={(event) => setAssignment({ ...assignment, role: event.target.value })} placeholder="e.g. HEAD_OF_QUALITY" /></label> : null}
              <label>Effective from<input type="date" value={assignment.effective_from} onChange={(event) => setAssignment({ ...assignment, effective_from: event.target.value })} /></label>
              <button type="button" className="dc-button dc-button--primary" disabled={reviewing === "new-assignment"} onClick={() => void submitAssignment()}>Save governed assignment</button>
            </div> : null}
            <div className="dgov-responsibility-list">{RESPONSIBILITIES.map(([type, title]) => <ResponsibilityRow key={type} type={type} title={title} assignments={data.effective_responsibilities[type] || []} canControl={canControl} reviewing={reviewing} onDecision={(row, decision) => void reviewResponsibility(row, decision)} />)}</div>
          </section>

          <section className="dgov-panel">
            <header><div><FolderTree size={18} /><span><strong>Controlled structure</strong><small>Stable hierarchy identity remains separate from immutable publication revisions.</small></span></div><button type="button" className="dc-button" onClick={() => navigate(`${basePath}/structure`)}>Open full structure</button></header>
            {data.structure ? <div className="dgov-structure"><div className="dgov-breadcrumb">{data.structure.parent ? <><span>{data.structure.parent.code}</span><ChevronRight size={14} /></> : null}<strong>{data.structure.code}</strong></div><h3>{data.structure.title}</h3><p>{data.structure.path}</p><div className="dgov-child-grid">{data.structure.children.map((child) => <article key={child.id}><small>{label(child.node_type)}</small><strong>{child.code}</strong><span>{child.title}</span></article>)}</div>{!data.structure.children.length ? <DocumentControlEmpty title="No child nodes" message="This node has no governed child procedure, form, annex, template or record series." /> : null}</div> : <DocumentControlEmpty title="Structure unresolved" message="Run reconciliation or assign this document to a governed hierarchy node. No implicit folder is treated as authoritative." />}
          </section>

          <section className="dgov-panel">
            <header><div><Network size={18} /><span><strong>Related controlled items</strong><small>Confirmed and detected relationships are separated by provenance and resolution state.</small></span></div></header>
            {[...groupedRelationships.entries()].map(([group, rows]) => rows.length ? <div className="dgov-relationship-group" key={group}><h3>{group} <span>{rows.length}</span></h3><div className="dgov-relationship-grid">{rows.map((row) => <RelationshipCard key={row.id} row={row} canControl={canControl} reviewing={reviewing} onDecision={(item, decision) => void reviewRelationship(item, decision)} openSource={(item) => openReader(item.source_revision_id, item.page_number)} openTarget={(item) => navigate(`${basePath}/library/${item.target_manual?.id}`)} />)}</div></div> : null)}
            {!data.relationships.length ? <DocumentControlEmpty title="No governed relationships" message="No manual relationship has been confirmed and no normalized proposal is available. Reindex the current source or add a controlled link." /> : null}
          </section>

          <section className="dgov-panel">
            <header><div><FileSearch size={18} /><span><strong>Detection review</strong><small>Exact source occurrences remain suggestions until Document Control resolves them.</small></span></div><button type="button" className="dc-button" disabled={reindexing || !document.read_target.revision_id} onClick={() => void reindex()}><RefreshCw size={14} /> {reindexing ? "Scheduling…" : "Reindex current revision"}</button></header>
            <div className="dgov-index-state"><DocumentControlStatus status={data.completeness.indexing_status} kind={kind(data.completeness.indexing_status)} />{data.index_jobs[0] ? <span>{data.index_jobs[0].detected_count} detected · {data.index_jobs[0].resolved_count} resolved · {data.index_jobs[0].unresolved_count} unresolved · {data.index_jobs[0].broken_count} broken</span> : <span>No checksum-keyed indexing job exists.</span>}</div>
            {data.detected_references.length ? <div className="dgov-detections">{data.detected_references.map((reference) => <article key={reference.id}><div><Link2 size={15} /><strong>{reference.raw_token}</strong><DocumentControlStatus status={reference.status} kind={kind(reference.status)} /></div><p>{reference.source_quote}</p>{reference.target_manual ? <p><strong>Proposed target:</strong> {reference.target_manual.code} · {reference.target_manual.title}</p> : null}<small>{reference.detection_method} · {reference.confidence_percent}% confidence{reference.source_page_number ? ` · page ${reference.source_page_number}` : ""}</small><div className="dgov-row-actions">{reference.source_revision_id ? <button type="button" onClick={() => openReader(reference.source_revision_id, reference.source_page_number)}>Open exact source</button> : null}{canControl && !["VERIFIED", "REJECTED"].includes(reference.status) ? <><button type="button" disabled={reviewing === reference.id || !reference.target_manual || !reference.target_revision_id} title={!reference.target_revision_id ? "Resolve an immutable target revision first" : undefined} onClick={() => void reviewDetectedReference(reference, "CONFIRMED")}><Check size={14} /> Confirm match</button><button type="button" disabled={reviewing === reference.id} onClick={() => void reviewDetectedReference(reference, "REJECTED")}><X size={14} /> Reject</button></> : null}</div></article>)}</div> : <DocumentControlEmpty title="No detected references" message={data.completeness.indexing_status === "FAILED" ? "Indexing failed. Review the retained error and retry after correcting the source or adapter." : "No unresolved reference occurrence is stored for the current source."} />}
          </section>

          <section className="dgov-panel">
            <header><div><History size={18} /><span><strong>Revision and lifecycle evidence</strong><small>Every reader link is pinned to an immutable revision identity.</small></span></div></header>
            <div className="dgov-revisions">{data.revisions.map((row) => {
              const revision = row as { id: string; issue_number?: string | null; revision_number?: string; status?: string; effective_date?: string | null; source_sha256?: string | null };
              return <article key={revision.id}><FileCheck2 size={17} /><div><strong>{revision.issue_number ? `Issue ${revision.issue_number} · ` : ""}Revision {revision.revision_number || "—"}</strong><span>{revision.status || "UNKNOWN"} · {revision.effective_date || "Not effective"}</span><small>{revision.source_sha256 ? `${revision.source_sha256.slice(0, 20)}…` : "Checksum unavailable"}</small></div><button type="button" className="dc-button" onClick={() => openReader(revision.id)}>Read</button></article>;
            })}</div>
          </section>
        </div>
      ) : null}
    </DocumentControlShell>
  );
}
