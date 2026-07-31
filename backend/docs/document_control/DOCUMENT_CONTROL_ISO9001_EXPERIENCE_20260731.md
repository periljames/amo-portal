# Document Control ISO 9001 Experience Review

Date: 2026-07-31  
Branch: `agent/document-control-iso9001-experience`

## 1. Standard baseline

The current published requirements baseline is **ISO 9001:2015**, together with **ISO 9001:2015/Amd 1:2024**. ISO states that the 2015 edition remains current and that Edition 6 is under publication for September 2026.

Official references:

- https://www.iso.org/standard/62085.html
- https://www.iso.org/standard/88431.html
- https://www.iso.org/standard/88464.html

This implementation therefore supports the current documented-information requirements while keeping the control model adaptable for the 2026 transition. The software must not be described as ISO certified. Certification and conformity depend on the organization's implemented processes, records, competence, internal audits, management review, corrective action, and independent assessment where certification is sought.

## 2. Reference-image findings

The supplied SharePoint references show a useful interaction model:

- a small number of primary tabs;
- a dense, full-width document register;
- grouping by document type;
- visible version, approval status, reviewer, approver, review date, department, and certification metadata;
- quick library views such as all documents and close to review;
- version history available from the selected document.

The references are effective as a familiar document-library pattern, but a shared library alone does not establish controlled change, release blocking, applicability, authority evidence, acknowledgement evidence, periodic review outcomes, external-data currency, copy custody, or cross-module traceability.

## 3. Experience changes

### Primary navigation

The previous sixteen equally weighted tabs are consolidated into five primary work areas:

1. **Overview** — control health and priority exceptions.
2. **Documents** — controlled library, structure, and generated records.
3. **Lifecycle** — change requests, revision workflow, authority submissions, and temporary revisions.
4. **Assurance** — distribution, acknowledgement, periodic review, controlled copies, and external technical data.
5. **Compliance** — QMS/module links, archive, registers, reports, and policy settings.

Each group exposes its routes in a hover and keyboard-focus menu. Existing canonical routes remain unchanged.

### Control Desk

The dashboard now prioritizes evidence gaps and deadlines instead of presenting every workspace as a large card. It shows:

- effective publications;
- active release workflows;
- controls due soon;
- overdue acknowledgements;
- documents missing control profiles;
- unassigned document owners;
- missing review dates;
- critical documents without acknowledgement control;
- documents without an effective issue;
- temporary revisions nearing expiry;
- external-source checks due;
- authority submissions pending.

### Controlled Library

The library now follows the useful parts of the reference design while retaining aviation governance:

- full-width, grouped metadata table;
- quick views for all documents, close to review, internal documents, external data, and records;
- document code, title, issue/revision, owner, review due date, governance state, and actions;
- direct opening of the permitted revision;
- separate access to the full control record;
- visible control gaps for missing or approaching review dates;
- preserved governed draft intake and approved-final-PDF intake.

## 4. ISO 9001 documented-information support map

The implementation supports the documented-information control intent through the following system controls.

| Control objective | Portal implementation | Evidence produced |
|---|---|---|
| Identify and describe documented information | Canonical document code, title, class, owner, language, issue, revision, effective date, source type, checksum, tags, and applicability | Master register and document control record |
| Review and approve before release | Controlled workflow with technical, Quality, accountable-manager, and authority gates where applicable | Workflow decisions, actor, timestamp, comments, evidence, and blockers |
| Ensure suitable format and media | Exact PDF/DOCX source retention, PDF-first approved intake, page/outline inspection, and source checksum | Original source, metadata, page structure, and SHA-256 evidence |
| Make current information available where needed | Role- and scope-aware current-issue reader with direct read target | Reader access, effective revision identity, and distribution records |
| Protect information from unauthorized use or loss of integrity | Tenant isolation, restricted profiles, role capabilities, immutable published revisions, checksums, and append-only actions | Access decisions, integrity data, and audit events |
| Control distribution, access, retrieval, and use | Recipient campaigns, access scope, acknowledgements, due dates, controlled-copy custody, and searchable library | Per-recipient status and custody history |
| Control changes and versions | Change requests, impact assessment, revision workflow, supersession, temporary revisions, and List of Effective Pages | Change history, revision history, LEP, and supersession evidence |
| Control retention and disposition | Archive register, retention settings, withdrawal, recall, return, destruction, and archive evidence | Archive and controlled-copy disposition records |
| Control externally originated documented information | OEM, authority, and supplier source register with currency checks and applicability | Source-check history, status, and due dates |
| Retain operational/QMS traceability | Canonical links to QMS, Training, Planning, Maintenance, Production, Fleet, Stores, Workforce, and Technical Records | Linked source records and publication blockers |

## 5. What this portal achieves beyond SharePoint-style storage

The competitive difference is not another file list. It is a governed aviation workflow around each document:

- publication can be blocked by unresolved QMS, training, authority, distribution, or operational dependencies;
- every document has a canonical identity and every revision has an immutable identity;
- current, draft, superseded, temporary, external, and controlled-copy states are handled differently;
- users receive the permitted current issue rather than browsing an uncontrolled folder;
- acknowledgment is retained per recipient instead of inferred from an email or shared link;
- authority submissions and responses remain linked to the exact revision;
- external technical data is monitored for currency and applicability;
- generated registers and audit evidence come from live transactional data;
- the documentation assistant searches the governed corpus without replacing the controlled workflow.

## 6. Acceptance criteria

- Only five primary navigation groups are visible to an authorized controller.
- Ordinary readers see only the Overview and Documents groups and cannot infer controller-only counts.
- Every existing Document Control route remains reachable.
- Hover and keyboard focus expose grouped routes without changing canonical URLs.
- The dashboard shows actionable exceptions before general totals.
- The library supports grouped rows, quick views, search, and full-width metadata.
- Dark and light themes preserve readable contrast.
- Mobile and tablet layouts remain usable without hiding required routes.
- Published revisions remain immutable and existing backend publication blockers remain enforced.
- The interface states that it supports ISO 9001 conformity and does not claim certification.

## 7. Validation required before merge

- clean PostgreSQL migration graph and upgrade;
- backend compilation and SQLAlchemy mapper configuration;
- Document Control backend tests;
- frontend TypeScript/Vite production build;
- integrated lint;
- authenticated browser acceptance for controller and reader roles;
- desktop hover-menu, keyboard-focus, tablet, and mobile navigation checks;
- light/dark visual review of dashboard and library;
- confirmation that every grouped menu route resolves to its existing page;
- confirmation that reader responses contain no tenant-wide controller metrics.
