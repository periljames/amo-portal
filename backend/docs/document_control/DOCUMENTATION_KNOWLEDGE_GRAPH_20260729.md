# AMO Portal Documented-Information Knowledge Graph

**Status:** Implementation and controlled rollout specification  
**Date:** 2026-07-29  
**Scope:** Publications, Document Control, Quality, forms, checklists, registers, external technical information, and retained records

## 1. Purpose

The portal must manage documented information as a connected controlled system rather than as unrelated uploaded files. A user reading a manual must be able to select a reference such as `QAM 51`, resolve the effective permitted form, open it beside the source paragraph, download it, complete it when authorised, and submit the completed artifact into its governed record series without losing the source context.

The graph provides five connected capabilities:

1. a governed documented-information hierarchy;
2. exact, version-aware cross-references;
3. progressive reader presentation of linked resources;
4. executable controlled forms and checklists;
5. immutable retained records with review and retention controls.

The canonical `manuals`, `manual_revisions`, `manual_sections`, and `manual_blocks` records remain the source of truth for controlled content. The graph augments those records; it does not replace or duplicate their revision lifecycle.

## 2. Design principles

### 2.1 Approved content remains immutable

A hierarchy move, alias change, reference correction, or execution-profile change must not alter an approved file, revision checksum, signature, figure, annotation, or authority marking.

### 2.2 Hierarchy and content are separate concerns

`DocumentationNode` controls placement, type, aliases, order, and discovery. `Manual` and `ManualRevision` control document identity, content, approval, effectivity, and immutability. Moving a procedure in the tree therefore changes discovery metadata only.

### 2.3 References are occurrences, not strings

The system does not store only “QAM 51 links to form X.” It stores each occurrence with:

- source manual and revision;
- source section/block when available;
- exact PDF page;
- character offsets;
- normalized PDF page coordinates;
- source quote and surrounding context;
- source change hash;
- relationship type;
- target resolution policy;
- indexed target revision;
- confidence and verification evidence.

This supports precise navigation, change monitoring, and audit reconstruction.

### 2.4 Ambiguity fails visibly

A reference with zero or multiple possible targets is `UNRESOLVED` or `AMBIGUOUS`. It is not silently linked to the first approximate result. Document Control must resolve it or correct the source/register metadata.

### 2.5 Target revision is resolved at use time

A `CURRENT_EFFECTIVE` link resolves the target document's current immutable published revision when opened and when submitted. The indexed target revision remains retained as trace information. A `PINNED_REVISION` link continues to resolve only the specifically approved historical revision.

### 2.6 Execution produces a record, not a modified template

The controlled template remains unchanged. A completed PDF is stored as a new immutable `DocumentationRecord` tied to:

- the exact template manual and revision;
- the source reference occurrence;
- the source manual/revision/page context;
- the output record series;
- the submitter and submission time;
- the completed artifact checksum;
- retention and review status.

## 3. Governed hierarchy

### 3.1 Node types

| Node type | Purpose | May bind to a Manual | Executable |
|---|---|---:|---:|
| `ROOT` | Tenant documented-information root | No | No |
| `MANAGEMENT_SYSTEM` | QMS, SMS, operations, support, or other grouping | No | No |
| `MANUAL` | High-level controlled manual | Yes | No |
| `POLICY` | Controlled policy | Yes | No |
| `PROCEDURE` | Controlled process procedure | Yes | No |
| `WORK_INSTRUCTION` | Task-level instruction | Yes | No |
| `FORM` | Controlled information-capture template | Yes | Yes |
| `CHECKLIST` | Controlled verification/task checklist | Yes | Yes |
| `REGISTER` | Controlled structured register template | Yes | Yes |
| `EXTERNAL_DOCUMENT` | OEM, authority, standard, or external technical data | Yes | No |
| `RECORD_SERIES` | Retained output classification | No | Receives records |

### 3.2 Parent-child enforcement

The backend enforces allowed placements. Representative rules are:

- only `ROOT` may have no parent;
- a manual can contain policies, procedures, work instructions, forms, checklists, registers, and record series;
- a policy can contain procedures and lower-level implementation information;
- a procedure can contain work instructions, forms, checklists, registers, and record series;
- a work instruction can use forms, checklists, registers, and record series;
- a form/checklist/register can point to a record series but cannot contain another controlled procedure;
- a record series is terminal;
- a content node must bind to a canonical Manual record;
- a node cannot be moved under itself or any descendant;
- tenant boundaries are enforced on every parent, content, target, and record-series link.

### 3.3 System groups

Initial reconciliation creates deterministic tenant groups:

- Management systems;
- Operations and maintenance;
- Support processes;
- Forms, checklists and registers;
- External controlled information;
- Records and retained evidence.

These groups provide a usable first view while allowing controlled reclassification beneath the same root.

### 3.4 Classification and aliases

The reconciliation process uses document class, manual type, code, title, and owner department to propose a node type and system group. Document Control can verify or change the classification.

Every content node retains aliases. Examples for one controlled form may include:

- `QAM 51`;
- `QAM-051`;
- `QAM/51`;
- `Quality Form 51`.

Aliases are normalized for matching while the exact source text remains retained for display and audit.

## 4. Reference graph

### 4.1 Relationship types

| Relationship | Meaning |
|---|---|
| `REFERENCES` | General controlled citation |
| `IMPLEMENTS` | Lower-level content implements higher-level requirements |
| `USES_FORM` | Procedure/manual instructs use of a form |
| `USES_CHECKLIST` | Procedure/manual instructs use of a checklist |
| `UPDATES_REGISTER` | Action updates a controlled register |
| `CREATES_RECORD` | Action explicitly creates retained evidence |

### 4.2 Resolution policies

#### `CURRENT_EFFECTIVE`

Use for ordinary operational references. The reader and submission endpoint resolve the target's current immutable published revision every time. This prevents a revised form from leaving manuals linked to a superseded template.

#### `PINNED_REVISION`

Use where the source intentionally requires a fixed historical revision, contractual baseline, authority submission package, investigation evidence pack, or frozen certification basis.

### 4.3 Reference states

| State | Meaning | User behaviour |
|---|---|---|
| `AUTO_RESOLVED` | One registered target and effective revision found | Open normally |
| `VERIFIED` | Controller explicitly confirmed target | Open normally; retain verifier evidence |
| `AMBIGUOUS` | Multiple registered candidates | No operational link; controller resolution required |
| `UNRESOLVED` | Token detected but no target identified | No operational link; register/source correction required |
| `BROKEN` | Target exists but no permitted effective immutable revision | No operational link; publication or target repair required |
| `OUTDATED` | Previously verified occurrence changed/disappeared | Controller re-verification required |
| `RESTRICTED` | Target exists but user cannot read it | Hide target details and deny open |

### 4.4 PDF indexing

PDF sources are indexed page by page using the exact approved source:

1. extract searchable text from each page;
2. match registered aliases from longest to shortest;
3. run a conservative code-candidate detector for unknown references;
4. exclude self-references where the only candidate is the source manual;
5. store page-relative normalized bounding coordinates;
6. store page text offsets and surrounding context;
7. resolve candidate targets and current published revision;
8. retain unresolved/ambiguous/broken occurrences;
9. expose a warning when the source is image-only and controlled OCR indexing is required.

The indexer never rasterizes, edits, signs, flattens, or rewrites the approved PDF.

### 4.5 DOCX and structured-content indexing

DOCX/structured revisions are indexed from canonical ManualBlock content. Each occurrence retains section, block, character offsets, source hash, and context. Accessible-text rendering can then wrap the exact reference text with a controlled link.

### 4.6 Reindex triggers

Indexing is idempotent per tenant/revision/checksum/index version and is triggered by:

- controlled PDF upload;
- controlled DOCX upload;
- first reader open when no current index exists;
- explicit controller reindex;
- future publication/change events;
- future scheduled integrity sweeps.

Each job records detected, resolved, unresolved, and broken counts plus timestamps and warning/error detail.

## 5. Reader experience

### 5.1 Approved-layout view

For PDF sources, linked occurrences are displayed as precise non-destructive hotspots over the approved page. Selecting a hotspot opens the controlled target in a portrait side pane while preserving the source page and reading position.

Every page also exposes a linked-items list. This provides access when:

- a reliable bounding box is unavailable;
- several occurrences share nearby geometry;
- the source uses scanned or irregular typography;
- the user uses keyboard navigation;
- a reference is unresolved and must be visibly reported to controllers.

### 5.2 Accessible-text view

Canonical HTML/text blocks are decorated with inline reference controls using the retained token and source context. The same linked-resource endpoint and access policy are used as the PDF view.

### 5.3 Split layout

Desktop layout uses:

- source navigation/tree pane;
- source reading pane;
- linked controlled resource pane.

Where width is constrained, the navigation collapses first. On tablet the linked pane becomes an overlay drawer. On mobile it becomes a full-screen controlled-resource view with a clear return action.

### 5.4 Target metadata

The linked pane displays:

- controlled code and title;
- issue/revision/effective date;
- relationship type;
- hierarchy type/path;
- source occurrence context;
- execution mode;
- read-only/editable safety state;
- download, full-reader, and submit actions where authorised.

## 6. Executable forms and checklists

### 6.1 Execution profile

Each executable template has a controlled execution profile containing:

- execution type;
- submission mode;
- output record series;
- retention period;
- naming pattern;
- download permission;
- working-draft permission;
- signature requirement;
- post-submission review requirement;
- optional portal schema;
- access scope and metadata;
- optimistic version.

### 6.2 Execution types

- `PDF_ACROFORM`: native PDF form fields rendered by PDF.js;
- `CHECKLIST`: portal checklist execution;
- `PORTAL_FORM`: schema-driven portal form;
- `DOWNLOADABLE_TEMPLATE`: controlled download and completed-copy upload;
- `HYBRID`: PDF/portal combined execution;
- `NONE`: reference-only content.

The current implementation supports native PDF AcroForm fill-and-submit and controlled downloadable templates. Checklist/portal-schema execution uses the same profile and record contract for subsequent module integration.

### 6.3 PDF safety

- source is served by authenticated range-enabled endpoints;
- JavaScript evaluation is disabled;
- PDFs containing scripted actions remain read-only;
- XFA and field appearances may render where supported;
- fields become editable only when the execution profile explicitly permits it;
- user entries remain browser-local until download or submission;
- submission saves a new PDF artifact and never updates the source revision.

### 6.4 Submission requirements

A record can only be created when:

- the target revision is published and immutable;
- the source reference resolves to the template;
- the current user may read/execute the target;
- the execution profile permits submission;
- a PDF artifact is provided;
- the artifact satisfies size and signature rules configured for the template;
- the output record series belongs to the same tenant.

## 7. Generated records

### 7.1 Record identity

Each generated record receives a tenant-unique number. The initial default is:

`{NORMALIZED_TEMPLATE_CODE}-{YYYYMMDD}-{SEQUENCE}`

Profiles retain a naming-pattern field for later tenant-specific numbering engines.

### 7.2 Record metadata

The generated record retains:

- record number;
- exact template manual/revision;
- originating reference occurrence;
- originating manual/revision/page/quote;
- output record series;
- submitted metadata/payload;
- artifact path, filename, MIME type, and SHA-256;
- status and review history;
- retention years and disposition;
- submitter/reviewer/timestamps.

### 7.3 Record review

Where review is required, an accountable document decision role may:

- accept the record;
- return it for correction;
- retain comments and evidence references;
- only decide after checksum integrity is verified.

Acceptance is terminal for that artifact. A correction creates a new submitted artifact rather than overwriting the returned record.

### 7.4 Artifact integrity

Record detail recomputes SHA-256 and reports:

- `VERIFIED`;
- `MISSING`;
- `MISMATCH`.

A missing or mismatched artifact cannot be accepted. Operational downloads remain private/no-store.

## 8. Access control

### 8.1 Reader users

Active tenant users may:

- read the permitted hierarchy;
- open permitted effective references;
- download where the execution profile permits;
- complete and submit permitted executable templates;
- open their own retained artifact.

Restricted target details are not exposed when the user lacks access.

### 8.2 Document Control / Quality controllers

Controllers may:

- reconcile/classify the hierarchy;
- maintain aliases and placement;
- configure execution profiles;
- schedule reindexing;
- resolve ambiguous or broken references;
- view the generated-record register and integrity status.

### 8.3 Accountable decision roles

Only the server-defined decision-approver policy may accept or return a generated record. Controller capability alone does not grant this approval decision.

### 8.4 Tenant isolation

Every hierarchy, reference, execution, record, target, and review query is scoped to the resolved active AMO. Cross-tenant identifiers are rejected rather than ignored.

## 9. Storage and indexing operations

### 9.1 Controlled source storage

Approved document sources continue to use the canonical ManualRevision storage path and checksum. The graph stores no duplicate source bytes.

### 9.2 Generated record storage

Generated artifacts are stored beneath the configured `DOCUMENT_RECORD_DIR`, partitioned by tenant, normalized template code, and date. Production deployment should place this root on managed object or durable file storage with:

- server-side encryption;
- versioning/WORM policy where required;
- malware scanning before availability;
- backup and restore testing;
- lifecycle/retention controls;
- tenant-aware object keys;
- checksum verification;
- access logs.

### 9.3 Database indexes

The migration adds indexes for:

- tenant/parent/order hierarchy traversal;
- tenant/type and materialized path;
- source revision/page and section/block occurrences;
- target/status and normalized token resolution;
- index job tenant/status and revision/checksum;
- template revision/submission time;
- record series/status;
- tenant/submitter.

### 9.4 Scale expectations

The graph is revision-scoped and page/block-indexed. Reader calls can filter references by page or section. The PDF viewer remains virtualized and renders only nearby pages. Hierarchy payloads can later move to paginated/expanded-node retrieval if a tenant reaches a size where one tree payload is no longer appropriate.

## 10. Monitoring and failure handling

Document Control monitors:

- pending/running/failed index jobs;
- searchable-text warnings;
- unresolved references;
- ambiguous candidates;
- broken effective targets;
- outdated verified occurrences;
- generated-record integrity failures;
- pending record reviews;
- returned records;
- retention and disposition due dates.

A failed background index preserves a failed job state and error summary after transaction rollback so operators can diagnose it.

## 11. Migration and rollout

1. Apply Alembic revision `document_control_20260729_knowledge_graph`.
2. Reconcile each tenant hierarchy.
3. Verify classifications and aliases for forms/checklists/registers.
4. Configure execution profiles and output record series.
5. Index all current published revisions, then controlled drafts as required.
6. Resolve ambiguous/broken high-risk operational references.
7. Pilot native AcroForm submission with selected forms.
8. Verify generated-record numbering, custody, review, and retention.
9. Enable organisation-wide reader hotspots.
10. Schedule periodic integrity sweeps and retention jobs.

## 12. Acceptance criteria

### Hierarchy

- all registered controlled documents appear once in the tree;
- a content document cannot exist as an unbound content node;
- invalid parent-child moves fail server-side;
- hierarchy changes do not alter revision checksum/content;
- tree and register views display the same canonical identities.

### References

- `QAM 51` resolves despite configured punctuation/spacing aliases;
- a PDF occurrence opens from its actual page and coordinates;
- accessible text opens from the matching paragraph/block;
- ambiguous targets never become operational links automatically;
- current-effective links advance when the target publication changes;
- pinned links remain fixed;
- restricted targets do not leak metadata;
- broken/outdated references remain visible in the monitor.

### Forms and records

- read-only resources cannot be modified or submitted;
- scripted PDFs remain non-executable;
- editable AcroForm fields retain entered values in the saved artifact;
- the controlled template checksum never changes;
- submission creates a separate record tied to exact template revision and source reference;
- record detail verifies checksum;
- integrity failure blocks approval;
- non-approvers cannot decide record review;
- accepted artifacts are not overwritten.

### Performance and usability

- opening a source reference does not reload the source manual;
- linked resource uses progressive/range PDF loading;
- desktop source and target fit without horizontal page loss at supported widths;
- keyboard users can open page-level and inline references;
- mobile linked resource has a full-screen controlled flow;
- 1,000+ page manuals remain virtualized;
- hierarchy and reference-monitor queries use indexed tenant-scoped filters.

## 13. Future extensions on the same contract

- controlled OCR pipeline for image-only publications;
- semantic reference suggestions as candidates only, never automatic approvals;
- schema-driven portal forms and offline checklist execution;
- electronic signature policy and identity verification;
- record disposition workflows and legal holds;
- graph impact analysis before publication;
- bulk reference verification work queues;
- document-package and authority-submission graph views;
- OEM/regulatory requirement nodes connected to implementing paragraphs;
- API/webhook integrations for engineering, training, audits, work orders, and reliability records;
- graph search: “show every procedure using QAM 51” or “show records created from Rev 4.”
