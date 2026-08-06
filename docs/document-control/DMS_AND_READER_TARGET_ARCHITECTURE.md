# Document Control and Universal Reader Target Architecture

## Architectural principles

1. `Manual.id` is the canonical controlled-document identity.
2. `ManualRevision.id` plus `source_sha256` is the immutable source identity.
3. Human-confirmed governance outranks inherited, migrated, imported or inferred data.
4. Detection creates reviewable suggestions, never approval.
5. The physical reader viewport is the only active-page authority.
6. Locations, annotations and evidence are format-neutral and checksum-bound.
7. Tenant and classification enforcement occurs server-side on every read and write.
8. Existing sound models are extended, not duplicated.

## Governed document domain

### Identity

Canonical identity remains in `manuals` and the compatibility control profile:

- tenant/manual ID;
- code and title;
- manual/document type;
- classification and lifecycle state;
- language and restricted/regulated flags;
- current published revision pointer.

### Immutable revision

`manual_revisions` remains authoritative for:

- issue/revision number;
- source filename/type/path/MIME;
- checksum and page count;
- effective/published/superseded state;
- immutable lock and authority reference.

Generated renderings, OCR text and indexes are derivatives. They never replace the original source.

### Responsibility assignment

`document_responsibility_assignments` stores one responsibility assignment per row:

- responsibility type;
- assignee type and one canonical target;
- effective period;
- primary/secondary/delegated state;
- source and confidence;
- confirmation state;
- creator/confirmer and timestamps;
- supersession link and provenance.

Precedence is deterministic:

1. confirmed manual;
2. confirmed imported/migrated;
3. confirmed inherited;
4. proposed manual/imported/migrated;
5. inferred proposal.

A lower-authority inference cannot replace an effective confirmed assignment.

### Controlled structure

`documentation_nodes` remains the hierarchy model. A node has stable identity, parent, ordered position, type, code, path, depth, status and provenance. Existing move validation prevents cycles and enforces tenant/type constraints. Ownership inheritance is resolved at read time and can be overridden by effective named assignments.

### Relationships

Two complementary models are retained:

- `DocumentationReference`: exact checksum-keyed extracted token occurrence with source page/section/block and candidate resolution.
- `DocumentGovernedRelationship`: normalized confirmed or proposed relationship to a document or external governed entity.

This separation preserves extraction evidence while allowing relationships to audits, findings, corrective actions, training, regulations, work orders and assets.

Relationship states:

`DETECTED → UNRESOLVED/MATCH_PROPOSED/CONFLICT → CONFIRMED or REJECTED → SUPERSEDED`

Every confirmed relation retains source, exact token/quote where available, location, confidence and reviewer evidence.

## Indexing and detection pipeline

1. Resolve tenant and immutable revision.
2. Compute source SHA-256 once when absent.
3. Select adapter from source format/MIME.
4. Reuse checksum plus adapter/index version cache when unchanged.
5. Extract structure, text aids and source metadata.
6. Detect codes, aliases, forms, records, regulations, responsibility clues and distribution/approval material.
7. Write exact `DocumentationReference` occurrences and responsibility/relationship proposals.
8. Match only against canonical tenant records.
9. Retain ambiguity and conflicts rather than choosing silently.
10. Expose job counts, error summary and unresolved queue.
11. Reindex only on explicit action, approval/upload hook or worker job.

OCR is an indexed aid and must be labelled as such. It is never authoritative text.

## Existing-document backfill

`DocumentGovernanceBackfillRun` and `DocumentGovernanceBackfillItem` provide:

- tenant-scoped idempotency;
- all/selected document scope;
- dry-run and execute modes;
- bounded batches;
- resumable pending/failed items;
- progress, attempts and retained failure evidence;
- checksum repair without source mutation;
- legacy ownership migration/proposals;
- one hierarchy reconciliation per execution run;
- index-job creation/reset keyed by checksum;
- reconciliation report.

CLI entry point:

```text
python -m amodb.jobs.document_governance_backfill --tenant <slug> --dry-run
python -m amodb.jobs.document_governance_backfill --tenant <slug> --execute
python -m amodb.jobs.document_governance_backfill --tenant <slug> --resume <run-id>
```

## Canonical location and annotation

`DocumentLocation` supports:

- PDF page and normalized rectangles;
- exact quote plus prefix/suffix context;
- semantic section/block and character range;
- spreadsheet sheet/cell range;
- slide/object identity;
- image region;
- adapter/version and source checksum.

`DocumentAnnotation` supports highlight, note, question, evidence, finding link and bookmark with controlled colours and visibility. An annotation cannot silently migrate to another checksum. A later migration service must produce a confidence-scored proposal requiring confirmation.

## Reader command state machine

All TOC, search, internal-link, page-entry and deep-link requests use one command lifecycle:

1. create command with unique ID and destination;
2. request virtualizer scroll once;
3. observe physical viewport intersection;
4. publish active page from viewport only;
5. consume command;
6. permanently release command;
7. manual scroll becomes authoritative.

Reflow operations preserve a physical anchor and never replay consumed commands. The current merged reader already follows this direction and remains the only reader engine.

## Reader modes

- **Standard:** identity, control state, navigation and document.
- **Reader:** portal chrome collapsed; toolbar, watermark and control state retained; `Esc` restores layout and physical position.
- **Audit target:** reader plus evidence tray using canonical annotations and links to audit/checklist/finding/CAR records.
- **Compare target:** two immutable checksums with synchronized navigation and explicit annotation migration proposals.

Audit and compare are target states and are not represented as complete by this branch.

## Cross-format adapter contract

Each adapter must expose:

```text
inspect(source) -> capabilities + metadata
extract_structure(source) -> normalized nodes
render_window(source, location, bounds) -> bounded view
search(source, query) -> canonical locations
resolve_link(source, link) -> canonical or external target
locate_selection(selection) -> DocumentLocation
create_derivative(source, policy) -> immutable derivative metadata
compare(left, right) -> supported diff stream
```

Planned adapters: PDF, DOCX, ODT, XLSX, ODS, PPTX, ODP, HTML, Markdown, text, TIFF, PNG, JPEG and scanned-document OCR aid.

## Frontend composition

### Dashboard

Only actionable, reconciliable queues are promoted:

- ownership awaiting confirmation;
- relationships awaiting review;
- failed indexing;
- orphaned hierarchy nodes;
- superseded revisions still referenced.

Every queue opens a URL-backed library filter.

### Library

- server-bounded result set;
- stable sort and page sizes 25/50/100/250;
- URL-backed filters;
- sticky header and bounded viewport;
- ownership, structure, relationship and indexing completeness;
- ordinary readers remain access-filtered before pagination/count disclosure.

### Document detail

One aggregate supplies:

- identity/current revision/checksum;
- separate responsibility rows and history;
- controlled structure context;
- grouped governed relationships;
- exact detected references and job state;
- revision history and reader entry points;
- confirmation/rejection controls for authorized controllers;
- assignment controls using active tenant users/departments/roles.

Empty states explain what is missing and provide the corrective action.

## Security and sharing

- Tenant comes from authenticated server context and route resolution, never from trusted client data alone.
- Assignee user/department/org-unit IDs are revalidated against the active tenant.
- Target documents/revisions are tenant validated.
- Restricted profile rules are applied before document detail or library disclosure.
- Private annotations are visible only to their creator; audit/controlled-record visibility requires control authority.
- Shared links contain immutable revision and location but grant no access by possession.
- External social sharing remains disabled for controlled/internal/restricted documents.

## Observability catalogue

Record privacy-safe metrics for:

- document open/source resolution latency;
- checksum cache hit/miss;
- indexing duration and counts;
- unresolved/conflict totals;
- reader page render latency and error category;
- stale-navigation prevention events;
- fit/zoom/reader-mode failures;
- annotation save failure;
- backfill throughput/failure/retry.

Never log full document text, selected private text, form values, restricted content or credentials.

## Delivery phases and current branch boundary

### Phase 1 — governance normalization and demonstrable workspace

Implemented in this branch:

- normalized responsibility, relationship, location, annotation and backfill models;
- migration and indexes;
- aggregate/read/write routes;
- bounded governance library and actionable dashboard;
- controller detail with ownership, hierarchy, relationships, detections and revisions;
- dry-run/resumable backfill command;
- unit/API-client/live-browser contracts.

### Phase 2 — reader-native annotation and audit evidence tray

Required before claiming complete audit mode:

- text/region selection bridge from reader to `DocumentLocation`;
- annotation toolbar/list/filter/jump;
- audit/checklist/finding/CAR entity validators;
- evidence index export and custody tests.

### Phase 3 — universal adapters and compare

Required before claiming universal-reader completion:

- adapter registry and capability negotiation;
- bounded viewers for every listed format;
- OCR labelling and cache rules;
- revision compare contract and synchronized viewer;
- malformed/unsupported source UX and test corpus.

### Phase 4 — exact-head production evidence

Merge is blocked until migration, backend, frontend build/lint/unit, authenticated reader, DMS browser, cross-tenant, form custody and manual multi-format review gates pass on the same head SHA.
