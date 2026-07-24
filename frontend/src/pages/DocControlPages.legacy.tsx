import React, { useEffect, useMemo, useState } from "react";
import { Link, Navigate, useLocation, useNavigate, useParams } from "react-router-dom";
import PageHeader from "../components/shared/PageHeader";
import SectionCard from "../components/shared/SectionCard";
import DataTableShell from "../components/shared/DataTableShell";
import { getCachedUser, getContext, normalizeDepartmentCode } from "../services/auth";
import DepartmentLayout from "../components/Layout/DepartmentLayout";
import { decodeAmoCertFromUrl } from "../utils/amo";
import { getMasterList, listManuals, subscribeManualsUpdated, type ManualSummary } from "../services/manuals";

type DocRecord = {
  id: string;
  title: string;
  type: string;
  issue: string;
  revision: string;
  effectiveDate: string;
  owner: string;
  status: "In force" | "Review due" | "Superseded";
  regulated: boolean;
  restricted: boolean;
};


type ManualMasterRow = {
  manual_id?: string;
  code?: string;
  title?: string;
  manual_type?: string;
  issue_number?: string;
  rev_number?: string;
  effective_date?: string;
  owner_role?: string;
  status?: string;
  pending_ack_count?: number;
};
const seededControlledLibrary: DocRecord[] = [
  { id: "AMO-QM-001", title: "Quality Manual", type: "Manual", issue: "7", revision: "2", effectiveDate: "2026-01-11", owner: "Document Control", status: "In force", regulated: true, restricted: false },
  { id: "AMO-OP-005", title: "Maintenance Procedures", type: "Procedure", issue: "14", revision: "1", effectiveDate: "2025-12-02", owner: "Production", status: "In force", regulated: true, restricted: true },
  { id: "AMO-SAF-003", title: "Safety & HF Handbook", type: "Handbook", issue: "4", revision: "0", effectiveDate: "2025-10-20", owner: "Safety", status: "Review due", regulated: false, restricted: false },
  { id: "AMO-TRN-002", title: "Competence Matrix", type: "Register", issue: "5", revision: "4", effectiveDate: "2025-07-16", owner: "HR & Training", status: "Superseded", regulated: false, restricted: true },
];

const draftQueue = [
  { draftId: "DR-2201", title: "MOE section 1.7 amendment", originator: "Chief Inspector", step: "Internal technical review", due: "2026-03-12", priority: "High" },
  { draftId: "DR-2204", title: "Stores receiving checklist", originator: "Stores Lead", step: "QA validation", due: "2026-03-16", priority: "Medium" },
  { draftId: "DR-2206", title: "Engine run-up precautions", originator: "Safety Manager", step: "Accountable Manager approval", due: "2026-03-19", priority: "High" },
];

const distributionEvents = [
  { id: "DIST-321", doc: "AMO-QM-001 Rev 2", audience: "All certifying staff", releasedOn: "2026-02-20", ackRate: "81%", pending: 9 },
  { id: "DIST-322", doc: "AMO-OP-005 Rev 1", audience: "Production + Planning", releasedOn: "2026-02-23", ackRate: "62%", pending: 21 },
  { id: "DIST-323", doc: "AMO-SAF-003 Rev 0", audience: "All staff", releasedOn: "2026-02-27", ackRate: "34%", pending: 58 },
];

const temporaryRevisions = [
  { trId: "TR-104", ref: "AMO-QM-001", subject: "CAA finding closure wording", status: "In force", expiry: "2026-04-15" },
  { trId: "TR-108", ref: "AMO-OP-005", subject: "Torque tooling segregation", status: "Pending authority", expiry: "2026-03-20" },
  { trId: "TR-111", ref: "AMO-SAF-003", subject: "Ramp FOD escalation", status: "Draft", expiry: "2026-05-30" },
];

const changeProposals = [
  { id: "CP-774", source: "Audit finding CAR-19", impactedDoc: "AMO-QM-001", owner: "Quality Manager", status: "In review" },
  { id: "CP-775", source: "Authority recommendation", impactedDoc: "AMO-OP-005", owner: "Head of Production", status: "Awaiting AM sign-off" },
  { id: "CP-779", source: "Safety report SAF-288", impactedDoc: "AMO-SAF-003", owner: "Safety Manager", status: "Draft" },
];

function useDocControlContext() {
  const { amoCode, department, docId, draftId, proposalId, trId, eventId } = useParams();
  const location = useLocation();
  const isStandaloneNamespace = location.pathname.startsWith(`/maintenance/${amoCode}/document-control`);
  const activeDepartment = department || (isStandaloneNamespace ? "document-control" : "quality");
  const basePath = !amoCode
    ? "/doc-control"
    : activeDepartment === "document-control"
      ? `/maintenance/${amoCode}/document-control`
      : `/maintenance/${amoCode}/${activeDepartment}/doc-control`;
  return { amoCode, department: activeDepartment, basePath, docId, draftId, proposalId, trId, eventId };
}

function DocControlShell({ title, subtitle, children }: { title: string; subtitle: string; children: React.ReactNode }) {
  const navigate = useNavigate();
  const context = getContext();
  const { amoCode, basePath, department } = useDocControlContext();
  const resolvedAmoCode = amoCode || context.amoCode || "system";
  const amoDisplay = decodeAmoCertFromUrl(resolvedAmoCode);
  const navItems = [
    ["Overview", basePath],
    ["Controlled library", `${basePath}/library`],
    ["Drafting & approval", `${basePath}/drafts`],
    ["Change proposals", `${basePath}/change-proposals`],
    ["Temporary revisions", `${basePath}/tr`],
    ["Distribution & ACK", `${basePath}/distribution`],
    ["Archive / obsolete", `${basePath}/archive`],
    ["Review planner", `${basePath}/reviews`],
    ["Registers", `${basePath}/registers`],
    ["Settings", `${basePath}/settings`],
  ] as const;

  return (
    <DepartmentLayout amoCode={resolvedAmoCode} activeDepartment={department}>
      <div className="qms-shell">
        <PageHeader
          title={title}
          subtitle={subtitle}
          breadcrumbs={[
            {
              label: `Document Control · ${amoDisplay}`,
              to: basePath,
            },
            { label: title },
          ]}
          actions={
            <div className="qms-header__actions">
              <button className="btn btn-primary">Create controlled document</button>
              <button
                type="button"
                className="secondary-chip-btn"
                onClick={() => navigate(department === "document-control" ? `/maintenance/${resolvedAmoCode}/document-control` : `/maintenance/${resolvedAmoCode}/${department}`)}
              >
                Back to department dashboard
              </button>
            </div>
          }
        />

        <div className="qms-content">
          <SectionCard title="Document control workbench" subtitle="Separated from Quality & Compliance but fully integrated for traceability.">
            <div style={{ display: "grid", gridTemplateColumns: "repeat(auto-fit,minmax(220px,1fr))", gap: 12 }}>
              {navItems.map(([label, to]) => (
                <Link key={label} to={to} className="card" style={{ padding: 12, border: "1px solid var(--border-subtle)", borderRadius: 10 }}>
                  <strong>{label}</strong>
                </Link>
              ))}
            </div>
          </SectionCard>

          {children}
        </div>
      </div>
    </DepartmentLayout>
  );
}

export const LegacyDocControlRedirectPage: React.FC = () => {
  const { amoCode, department } = useDocControlContext();
  const location = useLocation();
  const context = getContext();
  const suffix = location.pathname.replace(/^\/doc-control/, "") || "";
  const targetAmo = amoCode || context.amoCode || "system";
  const normalizedContextDepartment = normalizeDepartmentCode(context.department || "") || undefined;
  const user = getCachedUser() as (Record<string, unknown> & { department_code?: string; department?: { code?: string } }) | null;
  const normalizedUserDepartment = normalizeDepartmentCode(
    (user?.department?.code as string | undefined) || user?.department_code || "",
  ) || undefined;
  const authorizedDepartment = normalizedContextDepartment || normalizedUserDepartment || "quality";
  const targetPath = !amoCode
    ? authorizedDepartment === "document-control"
      ? `/maintenance/${targetAmo}/document-control${suffix}`
      : `/maintenance/${targetAmo}/${authorizedDepartment}/doc-control${suffix}`
    : department === "document-control"
      ? `/maintenance/${targetAmo}/document-control${suffix}`
      : `/maintenance/${targetAmo}/${department || authorizedDepartment}/doc-control${suffix}`;
  return <Navigate to={`${targetPath}${location.search}`} replace />;
};

export const DocControlDashboardPage: React.FC = () => {
  const { basePath } = useDocControlContext();
  const workflowTiles = [
    ["Manual issue and revision packaging", `${basePath}/revisions/AMO-QM-001`],
    ["Approval routing queue", `${basePath}/drafts`],
    ["Distribution matrix and read-and-understand", `${basePath}/distribution`],
    ["Remove obsolete copies", `${basePath}/archive`],
    ["Master register and LEP", `${basePath}/registers`],
    ["Periodic review planner", `${basePath}/reviews`],
  ] as const;

  return (
    <DocControlShell
      title="AMO Document Control Hub"
      subtitle="Purpose-built module for manual lifecycle control, approvals, controlled distribution, acknowledgement tracking, and obsolete withdrawal."
    >
      <SectionCard title="Role-focused journeys" subtitle="Everything needed for document controller, approver, and department focal points.">
        <div style={{ display: "grid", gridTemplateColumns: "repeat(auto-fit,minmax(260px,1fr))", gap: 12 }}>
          {workflowTiles.map(([label, to]) => (
            <Link key={label} to={to} className="card" style={{ padding: 16, borderRadius: 10 }}>
              {label}
            </Link>
          ))}
        </div>
      </SectionCard>
    </DocControlShell>
  );
};

export const DocControlLibraryPage: React.FC = () => {
  const { amoCode, basePath } = useDocControlContext();
  const tenantSlug = (amoCode || getContext().amoCode || "").toLowerCase();
  const [manuals, setManuals] = useState<ManualSummary[]>([]);
  const [masterRows, setMasterRows] = useState<ManualMasterRow[]>([]);

  useEffect(() => {
    if (!tenantSlug) {
      setManuals([]);
      setMasterRows([]);
      return;
    }
    const load = () => {
      listManuals(tenantSlug).then(setManuals).catch(() => setManuals([]));
      getMasterList(tenantSlug).then((rows) => setMasterRows(rows as ManualMasterRow[])).catch(() => setMasterRows([]));
    };
    load();
    const unsubscribe = subscribeManualsUpdated((detail) => {
      if (detail.tenantSlug === tenantSlug) load();
    });
    return unsubscribe;
  }, [tenantSlug]);

  const libraryRows = useMemo(() => {
    if (!manuals.length) return [] as DocRecord[];
    return manuals.map((manual) => {
      const matched = masterRows.find((row) => row.manual_id === manual.id || row.code === manual.code);
      return {
        id: manual.code,
        title: manual.title,
        type: manual.manual_type || matched?.manual_type || "Manual",
        issue: matched?.issue_number || "-",
        revision: matched?.rev_number || "-",
        effectiveDate: matched?.effective_date || "-",
        owner: matched?.owner_role || "Document Control",
        status: manual.status === "OBSOLETE" ? "Superseded" : manual.status === "ACTIVE" ? "In force" : "Review due",
        regulated: true,
        restricted: false,
      } as DocRecord;
    });
  }, [manuals, masterRows]);

  const hasRealData = manuals.length > 0 || masterRows.length > 0;
  const rows = hasRealData ? libraryRows : (import.meta.env.PROD ? [] : seededControlledLibrary);

  return (
    <DocControlShell title="Controlled Library Catalogue" subtitle="Master inventory of manuals and documented information currently under control.">
      <DataTableShell title="Document inventory register" actions={<button className="btn btn-secondary">Export XLSX</button>}>
        <div className="table-wrapper">
          <table className="table table-row--compact">
            <thead>
              <tr>
                <th>Document ID</th><th>Title</th><th>Type</th><th>Issue</th><th>Revision</th><th>Effective date</th><th>Status</th><th>Regulated</th><th>Restricted</th><th>Owner</th>
              </tr>
            </thead>
            <tbody>
              {rows.map((item) => (
                <tr key={item.id}>
                  <td><Link to={`${basePath}/library/${item.id}`}>{item.id}</Link></td>
                  <td>{item.title}</td>
                  <td>{item.type}</td>
                  <td>{item.issue}</td>
                  <td>{item.revision}</td>
                  <td>{item.effectiveDate}</td>
                  <td>{item.status}</td>
                  <td>{item.regulated ? "Yes" : "No"}</td>
                  <td>{item.restricted ? "Yes" : "No"}</td>
                  <td>{item.owner}</td>
                </tr>
              ))}
              {rows.length === 0 ? (
                <tr>
                  <td colSpan={10}>No controlled documents have been uploaded yet.</td>
                </tr>
              ) : null}
            </tbody>
          </table>
        </div>
      </DataTableShell>
    </DocControlShell>
  );
};

export const DocControlDocumentDetailPage: React.FC = () => {
  const { docId, basePath } = useDocControlContext();
  return (
    <DocControlShell title={`Document ${docId || "-"}`} subtitle="Complete control pack: issue history, LEP, TR impacts, acknowledgements, and archive traceability.">
      <SectionCard title="Document actions">
        <div style={{ display: "flex", gap: 8, flexWrap: "wrap" }}>
          <Link to={`${basePath}/revisions/${docId}`} className="btn btn-secondary">Create revision package</Link>
          <Link to={`${basePath}/lep/${docId}`} className="btn btn-secondary">Generate LEP</Link>
          <Link to={`${basePath}/distribution`} className="btn btn-secondary">Issue controlled distribution</Link>
        </div>
      </SectionCard>
      <SectionCard title="Control checklist" subtitle="Read-and-understand, superseded retrieval, and audit evidences are mandatory.">
        <ul>
          <li>Latest approved revision is in force and visible to permitted users.</li>
          <li>Superseded hard copies withdrawn and destruction/return recorded.</li>
          <li>Acknowledgement completion above target before effectiveness gate closes.</li>
          <li>Change-origin trace linked to CAR, audit, or safety source.</li>
        </ul>
      </SectionCard>
    </DocControlShell>
  );
};

export const DocControlDraftsPage: React.FC = () => {
  const { basePath } = useDocControlContext();
  return (
  <DocControlShell title="Drafting and Approval Queue" subtitle="From draft initiation through technical review, AM approval, and authority acceptance.">
    <DataTableShell title="Open draft packages" actions={<button className="btn btn-primary">Create draft</button>}>
      <div className="table-wrapper"><table className="table table-row--compact"><thead><tr><th>Draft ID</th><th>Title</th><th>Originator</th><th>Current approval step</th><th>Due</th><th>Priority</th></tr></thead><tbody>{draftQueue.map((row) => <tr key={row.draftId}><td><Link to={`${basePath}/drafts/${row.draftId}`}>{row.draftId}</Link></td><td>{row.title}</td><td>{row.originator}</td><td>{row.step}</td><td>{row.due}</td><td>{row.priority}</td></tr>)}</tbody></table></div>
    </DataTableShell>
  </DocControlShell>
  );
};

export const DocControlDraftDetailPage: React.FC = () => {
  const { draftId } = useDocControlContext();
  return <DocControlShell title={`Draft ${draftId || "-"}`} subtitle="Approval packet, impact assessment, and sign-off trail for this draft."><SectionCard title="Approval trail"><p>Reviewer signoffs, comments, and release gates appear here.</p></SectionCard></DocControlShell>;
};

export const DocControlChangeProposalPage: React.FC = () => {
  const { basePath } = useDocControlContext();
  return (
  <DocControlShell title="Change Proposal Register" subtitle="Capture triggers from findings, regulations, operational events, and continuous improvement.">
    <DataTableShell title="Active proposals">
      <div className="table-wrapper"><table className="table table-row--compact"><thead><tr><th>ID</th><th>Source</th><th>Impacted document</th><th>Owner</th><th>Status</th></tr></thead><tbody>{changeProposals.map((row) => <tr key={row.id}><td><Link to={`${basePath}/change-proposals/${row.id}`}>{row.id}</Link></td><td>{row.source}</td><td>{row.impactedDoc}</td><td>{row.owner}</td><td>{row.status}</td></tr>)}</tbody></table></div>
    </DataTableShell>
  </DocControlShell>
  );
};

export const DocControlChangeProposalDetailPage: React.FC = () => {
  const { proposalId } = useDocControlContext();
  return <DocControlShell title={`Change Proposal ${proposalId || "-"}`} subtitle="Impact, required approvals, and implementation checklist."><SectionCard title="Implementation plan"><p>Track linked drafts, training needs, and effective-date readiness checks.</p></SectionCard></DocControlShell>;
};

export const DocControlRevisionsPage: React.FC = () => {
  const { docId } = useDocControlContext();
  return <DocControlShell title={`Revision Packages • ${docId || "-"}`} subtitle="Build issue/revision package with authority references and transmittal notes."><SectionCard title="Package controls"><p>Attach revised pages, list of effective pages, transmittal matrix, and rollback plan.</p></SectionCard></DocControlShell>;
};

export const DocControlLEPPage: React.FC = () => {
  const { docId } = useDocControlContext();
  return <DocControlShell title={`LEP • ${docId || "-"}`} subtitle="List of effective pages generated from approved revision set."><SectionCard title="LEP actions" actions={<button className="btn btn-secondary">Export PDF</button>}><p>Validate page integrity before release and archive a signed LEP snapshot.</p></SectionCard></DocControlShell>;
};

export const DocControlTRPage: React.FC = () => {
  const { basePath } = useDocControlContext();
  return (
  <DocControlShell title="Temporary Revision Register" subtitle="Control temporary revisions until incorporation into next full issue.">
    <DataTableShell title="TR status board">
      <div className="table-wrapper"><table className="table table-row--compact"><thead><tr><th>TR ID</th><th>Reference document</th><th>Subject</th><th>Status</th><th>Expiry / incorporation due</th></tr></thead><tbody>{temporaryRevisions.map((row) => <tr key={row.trId}><td><Link to={`${basePath}/tr/${row.trId}`}>{row.trId}</Link></td><td>{row.ref}</td><td>{row.subject}</td><td>{row.status}</td><td>{row.expiry}</td></tr>)}</tbody></table></div>
    </DataTableShell>
  </DocControlShell>
  );
};

export const DocControlTRDetailPage: React.FC = () => {
  const { trId } = useDocControlContext();
  return <DocControlShell title={`Temporary Revision ${trId || "-"}`} subtitle="Track in-force controls, expiry, and incorporation workflow."><SectionCard title="Compliance controls"><p>Ensure applicable TR has been distributed and acknowledged before effectivity.</p></SectionCard></DocControlShell>;
};

export const DocControlDistributionPage: React.FC = () => {
  const { basePath } = useDocControlContext();
  return (
  <DocControlShell title="Controlled Distribution and Acknowledgements" subtitle="Issue revisions to targeted recipients and monitor read-and-understand completion.">
    <DataTableShell title="Distribution events" actions={<button className="btn btn-primary">Create distribution event</button>}>
      <div className="table-wrapper"><table className="table table-row--compact"><thead><tr><th>Event</th><th>Document</th><th>Audience</th><th>Released</th><th>Ack completion</th><th>Pending</th></tr></thead><tbody>{distributionEvents.map((row) => <tr key={row.id}><td><Link to={`${basePath}/distribution/${row.id}`}>{row.id}</Link></td><td>{row.doc}</td><td>{row.audience}</td><td>{row.releasedOn}</td><td>{row.ackRate}</td><td>{row.pending}</td></tr>)}</tbody></table></div>
    </DataTableShell>
  </DocControlShell>
  );
};

export const DocControlDistributionDetailPage: React.FC = () => {
  const { eventId } = useDocControlContext();
  return <DocControlShell title={`Distribution Event ${eventId || "-"}`} subtitle="Recipient list, escalation logs, and acknowledgement evidence."><SectionCard title="Escalation actions"><p>Reminder cadence: day 3, day 7, and department manager escalation after day 10.</p></SectionCard></DocControlShell>;
};

export const DocControlArchivePage: React.FC = () => (
  <DocControlShell title="Archive and Obsolete Copy Withdrawal" subtitle="Prove obsolete copies were removed from circulation and archived with full traceability.">
    <DataTableShell title="Obsolete withdrawal log">
      <div className="table-wrapper"><table className="table table-row--compact"><thead><tr><th>Document</th><th>Superseded by</th><th>Locations retrieved</th><th>Digital access revoked</th><th>Disposal method</th><th>Evidence ref</th></tr></thead><tbody><tr><td>AMO-QM-001 Rev 1</td><td>Rev 2</td><td>9/9</td><td>Yes</td><td>Shred + return stamp</td><td>OBS-2231</td></tr><tr><td>AMO-OP-005 Rev 0</td><td>Rev 1</td><td>14/14</td><td>Yes</td><td>Controlled bin destruction</td><td>OBS-2240</td></tr></tbody></table></div>
    </DataTableShell>
  </DocControlShell>
);

export const DocControlReviewsPage: React.FC = () => (
  <DocControlShell title="Periodic Review Planner" subtitle="Prevent stale manuals by planning review cycles with accountable owners.">
    <DataTableShell title="Review horizon (next 90 days)">
      <div className="table-wrapper"><table className="table table-row--compact"><thead><tr><th>Document</th><th>Current revision</th><th>Owner</th><th>Next review due</th><th>Status</th></tr></thead><tbody><tr><td>AMO-QM-001</td><td>Rev 2</td><td>Quality Manager</td><td>2026-04-01</td><td>On track</td></tr><tr><td>AMO-SAF-003</td><td>Rev 0</td><td>Safety Manager</td><td>2026-03-18</td><td>At risk</td></tr><tr><td>AMO-OP-005</td><td>Rev 1</td><td>Head of Production</td><td>2026-03-22</td><td>In progress</td></tr></tbody></table></div>
    </DataTableShell>
  </DocControlShell>
);

export const DocControlRegistersPage: React.FC = () => (
  <DocControlShell title="Registers and Master Lists" subtitle="Single source of truth for document inventory, distribution matrices, LEP snapshots, and authority submissions.">
    <SectionCard title="Registers in scope">
      <ul>
        <li>Master document register (all controlled documented information).</li>
        <li>Distribution matrix by role, station, and contractor profile.</li>
        <li>Acknowledgement register for read-and-understand evidence.</li>
        <li>Obsolete withdrawal and archive register.</li>
        <li>Authority submission and approval tracker.</li>
      </ul>
    </SectionCard>
  </DocControlShell>
);

export const DocControlSettingsPage: React.FC = () => (
  <DocControlShell title="Document Control Settings" subtitle="Configure numbering schema, approval routing, mandatory acknowledgement rules, and retention controls.">
    <SectionCard title="Module controls">
      <p>Define tenant-specific defaults for issue/revision formats, authority workflow requirements, and distribution reminder policy.</p>
    </SectionCard>
  </DocControlShell>
);
