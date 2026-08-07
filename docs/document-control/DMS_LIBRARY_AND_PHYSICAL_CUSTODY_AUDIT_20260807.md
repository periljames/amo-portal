# DMS Library, Relationship, Physical-Custody and Private-Record Audit

Date: 2026-08-07

Repository: `periljames/amo-portal`

Branch: `agent/dms-reader-governance-completion`

## Purpose

This review treats Document Control as a company information library, not as a collection of workflow tables. It answers four operational questions:

1. Can an authorized employee find the company policy, manual, procedure, work instruction, form or external technical document they need without knowing which backend register owns it?
2. Can a controller trace why two documents are related and which operational QMS, training, workforce, maintenance, fleet, stores or technical-record record a controlled document governs or evidences?
3. Can a numbered physical controlled copy be traced from its home shelf to a custodian, due date, return, recall and disposition using a portal-generated QR label?
4. Can private personnel records and module-owned evidence use Document Control safely without turning the general company library into a privacy leak or a duplicate system of record?

## Findings before this pass

### Strong foundations already present

The repository already contained more of a DMS than the old tables implied:

- `Manual` is the stable controlled-document identity and `ManualRevision` is the immutable revision/source identity.
- `DocumentationNode` provides a real typed hierarchy with root, management-system, manual, policy, procedure, work-instruction, form, checklist, register, external-document and record-series nodes.
- `DocumentationReference` preserves detected exact source occurrences.
- `DocumentGovernedRelationship` provides reviewed semantic relationships such as `HAS_FORM`, `GENERATES_RECORD`, `IMPLEMENTS`, `REFERENCES`, `LINKED_REGULATION`, `LINKED_AUDIT`, `LINKED_CAR`, `LINKED_WORK_ORDER` and `LINKED_AIRCRAFT_OR_COMPONENT`.
- `DocumentIntegrationLink` verifies links to authoritative operational records in their owning modules rather than copying those records into Document Control.
- `DocumentationRecord` provides immutable generated outputs from controlled templates.
- `ExternalDocumentSource` and `ExternalRevisionReceipt` already represent OEM, authority and supplier source/currency/applicability evidence.
- `DocumentControlledCopy` and its event ledger already supplied the basis of physical copy identity and history.

### Main usability failures

The problem was fragmentation. The user had to understand the implementation model before finding information:

- the hierarchy lived under Structure;
- the register looked primarily like a lifecycle/controller table;
- physical copies were an assurance sub-table rather than a physical library;
- generated records were separate from the document that created them;
- external currency was not visible from the main shelf;
- document relationships and live module links existed but were not visible at a glance;
- ordinary users could read permitted documents but the company-policy/library entry point did not communicate the document categories clearly;
- returned physical copies did not behave naturally as reusable shelf inventory;
- QR-backed shelf circulation did not exist as a user workflow.

## Implemented company-library model

The canonical `/workspace/t/{tenant}/documents` response now drives a user-facing Company document library while retaining controller governance queues.

### Library categories

The primary shelf exposes:

- Policies;
- Manuals;
- Procedures;
- Work instructions;
- Forms;
- Checklists;
- Registers;
- External technical data.

The Full tree remains the authoritative hierarchical view and is one click from the library. The hierarchy is not duplicated into a second tree model.

### Search and bounded table

The company library searches document code/title/type, source filename and hierarchy node code/title. Results remain server bounded and access-filtered before disclosure. The table shows:

- controlled document identity and structure path;
- current issue/revision and readable target;
- named owner/responsible department when resolved;
- digital and physical availability;
- governed document relationships;
- verified module integration counts/modules;
- immutable generated-record counts;
- external source/currency status;
- direct Read and controller Manage actions.

### Governance queues preserved

Replacing the old governance list with the richer company library must not break controller remediation. The backend and frontend preserve URL-backed queue filters for:

- unresolved ownership;
- unresolved relationships/references;
- indexing status;
- orphaned structure;
- superseded referenced revisions;
- owner and department filters;
- stable sorting.

A visible `Governance queue` banner tells controllers when one of these constrained views is active.

## Document relationships and module boundaries

The DMS uses two different link types intentionally.

### Document-to-document meaning

`DocumentGovernedRelationship` answers questions such as:

- which form belongs to this procedure;
- which checklist implements this work instruction;
- which record does this form generate;
- which regulation or policy does this procedure implement;
- which controlled document supports another controlled document.

These links retain provenance, source location, reviewer state and immutable revision context.

### Document-to-operational-record meaning

`DocumentIntegrationLink` answers a different question: which live record in another module is connected to this document or revision?

The integration resolver verifies the source entity against the canonical tenant-owned table before accepting it. Supported owning-module families include QMS, Training, Workforce, Planning, Production, Maintenance, Fleet, Stores and Technical Records.

This is the correct boundary. Document Control should not copy a CAR, audit, employment contract data row, calibration record or work order into its own competing operational table merely to create a link.

## Calibration certificate example

The QMS assurance source registry already recognizes authoritative `CALIBRATION`, `CALIBRATION_CERTIFICATE` and `EQUIPMENT` records and routes them back to the Quality equipment/calibration workspace.

Therefore a controlled work instruction, maintenance procedure or calibration policy can have a verified DMS integration link to the canonical QMS calibration certificate/equipment record without duplicating it.

A remaining distinction is important: the current physical-copy table is revision-centric (`manual_id` + `revision_id`). It can track a hard copy of a governed DMS document, but it does not yet make an arbitrary QMS calibration certificate record into a physical library asset unless that certificate is also registered as a governed DMS document/revision. A later generic retained-record physical-asset target should solve this without weakening the existing controlled-copy foreign keys.

## Physical controlled library implemented

### Shelf identity

Document Control can register a published immutable revision as a numbered hard copy or offline-media copy with a home shelf/location. A shelf copy is available (`RETURNED` with no holder) rather than artificially issued to Document Control.

### Circulation

The scan workflow supports:

- check out;
- explicit custody acknowledgement/sign-off;
- future return due time;
- current custodian;
- check in/return;
- current physical-location verification;
- recall;
- controlled transfer/location change;
- withdrawal/destruction with existing disposition controls;
- immutable event history plus the ordinary Document Control audit ledger.

A returned copy is reusable shelf inventory. Return clears custodian and due date and restores the home/declared shelf location.

### QR labels

Document Control can generate an A6 PDF stick-on label containing:

- document code/title;
- controlled issue and revision;
- copy number and format;
- home shelf/location;
- physical-copy identifier;
- QR code into the authenticated scan workflow.

The QR is deliberately not a bearer credential. The label states that it is an identifier, and every scan still resolves tenant access and the user's permission to read the underlying document.

### Privacy on scan

Possession of a QR label must not reveal another employee's identity. The scan endpoint therefore applies three levels:

- Document Control sees the full custody record needed to administer the library;
- the current custodian sees their own custody status and a sanitized history without other staff IDs/evidence payloads;
- another authorized document reader can resolve the controlled document but does not receive the other custodian's identity or custody event history.

## Personnel contracts and private employee records

### What exists

Workforce already owns canonical employment-contract data through `EmploymentContract`. Document Control's integration resolver accepts Workforce/`employment_` entities, so a governed policy, procedure or controlled template can be verified against the canonical contract record without duplicating Workforce data.

### What does not yet exist

The repository review did not find a dedicated signed employment-contract/personnel-document file vault with employee/HR-specific file authorization and retention semantics.

Putting signed contracts, identity documents, disciplinary files, medical/private HR evidence or other personnel files in the general Company document library would be an architectural and privacy error.

### Required secure boundary

Private personnel files should be a separate restricted Records vault that reuses DMS custody primitives but is not discoverable through the public company-library facets or counts. The target must require:

- immutable file checksum/version identity;
- tenant and employee subject identity;
- authoritative Workforce entity link;
- explicit HR/authorized-role and employee-self authorization rules;
- no general Document Control reader disclosure by default;
- privacy-safe search/counts;
- access/download audit trail;
- retention class, retention due date and legal hold;
- supersession/replacement without overwriting prior evidence;
- protected storage URI rather than public file paths;
- malware/type/size validation at intake;
- optional employee acknowledgement/signature evidence where the owning workflow requires it.

This vault is intentionally not claimed complete in the current physical-library slice.

## Security boundaries retained

- Tenant is resolved server-side from authenticated context.
- Document access is evaluated before library pagination/count disclosure.
- QR possession does not grant read or custody access.
- Controller-only relationship/integration counts are not exposed to ordinary readers when they could leak restricted entities.
- Module-owned records remain authoritative in their source modules.
- Original controlled source files and immutable revisions are not rewritten by library/circulation functions.

## Remaining merge blockers / future slices

The following should remain explicit rather than being hidden behind a broad `Library` label:

1. Generic physical-asset custody for an arbitrary retained record such as a standalone QMS calibration certificate that is not itself a governed `ManualRevision`.
2. Secure personnel/signed-contract file vault and HR/employee access policy.
3. End-user access-filtered relationship browsing from the general library/reader without leaking restricted target counts.
4. Production-like browser proof of full-tree navigation, policy discovery, external-data currency, physical QR check-out/check-in, overdue return and label printing.
5. Production-scale query plans for the integrated company-library aggregates.

## Conclusion

The DMS should present three coherent experiences, not one giant table:

1. **Company library** — permitted controlled information that employees can find and read.
2. **Control workspace** — lifecycle, governance, relationships, distribution, external currency, generated records and module integrations for Document Control.
3. **Physical/private records custody** — numbered shelf copies and, in a separate restricted slice, personnel or other sensitive retained records.

This separation keeps the interface library-like while preserving aviation traceability, employee privacy and authoritative module ownership.
