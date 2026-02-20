import React from "react";
import { Link, useParams } from "react-router-dom";

const tiles = [
  ["Pending internal approvals", "/doc-control/drafts?status=Review"],
  ["Pending authority approval", "/doc-control/library?regulated=true&authority=Pending"],
  ["TRs in force", "/doc-control/tr?status=InForce"],
  ["TRs expiring in 30 days", "/doc-control/tr?expiring=30d"],
  ["Manuals due for review in 60 days", "/doc-control/reviews?due=60d"],
  ["Outstanding acknowledgements", "/doc-control/distribution?ack=pending"],
  ["Recently published revisions", "/doc-control/revisions/recent?window=30d"],
];

export const DocControlDashboardPage: React.FC = () => (
  <section className="page doc-control-page">
    <h1>Document Control</h1>
    <div style={{ display: "grid", gridTemplateColumns: "repeat(3,minmax(180px,1fr))", gap: 12 }}>
      {tiles.map(([label, href]) => (
        <Link key={label} to={href} className="card" style={{ padding: 12, border: "1px solid #ddd", borderRadius: 8 }}>
          {label}
        </Link>
      ))}
    </div>
  </section>
);

export const DocControlLibraryPage: React.FC = () => (
  <section className="page doc-control-page">
    <h1>Controlled Library</h1>
    <table><thead><tr><th>Doc ID</th><th>Title</th><th>Type</th><th>Issue</th><th>Revision</th><th>Effective date</th><th>Status</th><th>Regulated</th><th>Restricted</th><th>Owner department</th></tr></thead><tbody /></table>
  </section>
);

export const DocControlDocumentDetailPage: React.FC = () => {
  const { docId } = useParams();
  return <section className="page doc-control-page"><h1>Document {docId}</h1><p>Tabs: Overview, Revisions, LEP, TR, Distribution, Acks, Storage/Archive, Reviews, Audit Log.</p></section>;
};

export const DocControlDraftsPage: React.FC = () => <section className="page"><h1>Drafts</h1><button>Create Draft</button></section>;
export const DocControlDraftDetailPage: React.FC = () => { const { draftId } = useParams(); return <section className="page"><h1>Draft {draftId}</h1></section>; };
export const DocControlChangeProposalPage: React.FC = () => <section className="page"><h1>Change Proposals</h1></section>;
export const DocControlChangeProposalDetailPage: React.FC = () => { const { proposalId } = useParams(); return <section className="page"><h1>Change Proposal {proposalId}</h1></section>; };
export const DocControlRevisionsPage: React.FC = () => { const { docId } = useParams(); return <section className="page"><h1>Revision Packages for {docId}</h1></section>; };
export const DocControlLEPPage: React.FC = () => { const { docId } = useParams(); return <section className="page"><h1>LEP for {docId}</h1><button>Export PDF/Print</button></section>; };
export const DocControlTRPage: React.FC = () => <section className="page"><h1>Temporary Revisions</h1></section>;
export const DocControlTRDetailPage: React.FC = () => { const { trId } = useParams(); return <section className="page"><h1>Temporary Revision {trId}</h1></section>; };
export const DocControlDistributionPage: React.FC = () => <section className="page"><h1>Distribution</h1></section>;
export const DocControlDistributionDetailPage: React.FC = () => { const { eventId } = useParams(); return <section className="page"><h1>Distribution Event {eventId}</h1></section>; };
export const DocControlArchivePage: React.FC = () => <section className="page"><h1>Archive</h1></section>;
export const DocControlReviewsPage: React.FC = () => <section className="page"><h1>Reviews</h1></section>;
export const DocControlRegistersPage: React.FC = () => <section className="page"><h1>Registers</h1><button>Export PDF</button></section>;
export const DocControlSettingsPage: React.FC = () => <section className="page"><h1>Settings</h1></section>;
