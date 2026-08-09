# DMS Frontend Refactor — Final As-Built Evidence

**Contract:** `docs/document-control/DMS_FRONTEND_OPERATING_MODEL_20260808.md`  
**PR:** #490  
**Branch:** `agent/dms-frontend-operating-model-refactor`  
**Evidence date:** 2026-08-09  

## 1. Final operating model

Document Control now presents seven permanent workspaces only:

1. Home
2. Library
3. Changes
4. Distribution
5. Compliance
6. Reports
7. Administration

Backend entities remain authoritative but are not permanent navigation peers.

### Canonical tenant route tree

```text
/maintenance/:amoCode/document-control
├── /                         Home / My Work
├── /library                  Controlled information Library
│   └── /:documentId          Unified Document Workspace
│       ├── ?tab=overview
│       ├── ?tab=content
│       ├── ?tab=changes
│       ├── ?tab=workflow
│       ├── ?tab=distribution
│       ├── ?tab=compliance
│       ├── ?tab=relationships
│       └── ?tab=history
├── /changes                  Change lifecycle portfolio
├── /distribution             Distribution and custody portfolio
├── /compliance               Document assurance / external data
├── /reports                  Controlled evidence registers
└── /administration           Governed DMS policy/configuration
```

The optimized controlled reader remains under the existing Publications route family:

`/maintenance/:amoCode/publications/:manualId/rev/:revId/read`

## 2. Compatibility convergence

Legacy list routes converge on canonical workspaces while specialist detail/mutation owners remain addressable.

| Legacy route | Canonical owner |
|---|---|
| `/drafts` | Changes · in review |
| `/change-proposals` | Changes · requests |
| `/authority` | Changes · authority |
| `/tr` | Changes · temporary revisions |
| `/reviews` | Compliance · reviews |
| `/external-sources` | Compliance · external technical data |
| `/integrations` | Compliance · relationships |
| `/registers` | Reports |
| `/settings` | Administration |
| `/archive` | Library / archival state |

Specialist routes for controlled-copy scans, retained records, hierarchy, authority/TR detail and distribution detail remain because they own proven mutation/evidence operations.

## 3. Component ownership

| Responsibility | Final owner |
|---|---|
| DMS shell / seven-workspace IA | `DocumentControlShell.tsx` |
| Home / My Work | `DocumentGovernanceDashboardPage.tsx` + `workspace_dashboard_router.py` |
| Default rich Library | `DocumentLibraryHubPage.tsx` + `workspace_library_router.py` |
| Library preset/rich discovery | `workspace_library_discovery_router.py` |
| Unified document workspace | `DocumentControlRecordPage.tsx` |
| Change lifecycle portfolio | `DocumentControlChangesPortfolioPage.tsx` + `workspace_portfolio_router.py` |
| Distribution portfolio | `DocumentControlDistributionPortfolioPage.tsx` + `workspace_distribution_portfolio_router.py` |
| Compliance portfolio | `DocumentControlCompliancePortfolioPage.tsx` + `workspace_compliance_portfolio_router.py` |
| External revision assessment | `ExternalRevisionAssessmentPanel.tsx` + `workspace_external_assessment_router.py` |
| Reports catalogue | `DocumentControlReportsPage.tsx` + `workspace_reports_register_router.py` |
| Administration policy | `DocumentControlAdministrationPage.tsx` + `workspace_administration_router.py` |
| Physical copy custody | `DocumentLibraryCopiesPage.tsx`, existing copy event router + `workspace_copy_incident_router.py` |
| Contextual Assisted Search | `DocumentationAssistantPanel.tsx` + `knowledge_assistant_router.py` |
| Revision Intelligence | `ManualDiffPage.tsx` |
| Reader | `ManualReaderPage -> PublicationsReaderPage -> PublicationPdfLayoutViewer` |

## 4. Home / My Work

Home is an operational command centre rather than a KPI-card dashboard.

It exposes:

- My Work;
- Exceptions;
- Due Soon;
- Recent Changes;
- Quick Actions.

The server aggregate only labels work as personal when it is attributable through direct ownership, review assignment, distribution-recipient assignment or confirmed/effective responsibility assignment. Manual rows are access-filtered before disclosure.

## 5. Library and controlled search

### Default Library fast path

The existing authoritative Library remains the default dense table. It provides:

- server-side pagination, filtering and sorting;
- debounced metadata search;
- stale-while-refresh behavior;
- hierarchy context;
- current revision / read target;
- external-source currency;
- controlled-copy availability;
- governed relationships and retained-record counts for controllers.

The browser never fetches the complete tenant population.

### Operational presets

The Library now implements the MD preset model:

- All Documents;
- My Documents;
- Favorites;
- Recently Opened;
- Recently Revised;
- Awaiting My Review;
- External Technical Data;
- Due for Review;
- Superseded;
- Archived.

These use a second bounded permission-filtered discovery endpoint rather than client filtering.

### Rich controlled discovery

The bounded discovery path can match:

- document code/title/type;
- revision / issue identifier;
- source filename;
- hierarchy code/title/path and controlled node metadata/aliases;
- owner name/email and owner department;
- indexed controlled section headings and block text.

### Contextual Assisted Search

The Documentation Assistant is not permanent DMS chrome. It is mounted only in controlled Library/document context and the controlled reader. Server-side retrieval access-filters manuals before searching and external AI use remains explicit, server-side and non-storing. Returned answers retain exact controlled-source citation/navigation context where available.

## 6. Unified Document Workspace

Controllers enter one document lifecycle workspace with exactly eight tabs:

**Overview · Content · Changes · Workflow · Distribution · Compliance · Relationships · History**

The workspace exposes:

- sticky controlled document identity;
- current/effective revision and lifecycle state;
- actual workflow stepper;
- first-class blockers;
- responsibility/governance access;
- change/TR/authority context;
- distribution and physical custody;
- compliance/external/applicability context;
- governed cross-module relationships;
- retained event history.

The primary “Raise change request” flow now selects a controlled document in Library and enters the existing authoritative Changes mutation form; it no longer loops between list routes.

## 7. Reader and Revision Intelligence

The post-#477 PDF engine was retained rather than replaced.

User-reachable reader modes:

- Standard;
- Immersive;
- Fullscreen;
- Review changes / Revision Intelligence.

Immersive/fullscreen hide duplicate portal/document chrome while retaining controlled warning, navigation, search, PDF controls and permitted print/download.

### Revision Intelligence

The review workspace exposes only evidence supported by retained source/index data:

- selected and baseline revision metadata;
- revision reason / lifecycle evidence where available;
- changed section/block counts;
- additions/deletions;
- changed pages where workflow evidence identifies them;
- Changed Content Only / All Indexed Content;
- Previous Change / Next Change navigation;
- side-by-side structured indexed comparison;
- direct open-selected-revision / changed-page actions.

When reliable automated comparison cannot be produced from retained source/index data, the UI states that limitation explicitly rather than manufacturing a diff. Aligned PDF overlay is therefore capability-dependent, not synthesized from unreliable geometry.

## 8. Changes lifecycle

Changes consolidates the frontend lifecycle over authoritative distinct backend entities.

Views:

- Requests;
- Draft;
- In Review;
- Awaiting Quality;
- Awaiting Management;
- Authority;
- Temporary Revisions;
- Ready for Release;
- Closed.

The portfolio is server-paginated and does not fetch whole workflow tables.

## 9. Distribution and physical controlled-copy custody

Distribution owns current campaigns, pending/overdue acknowledgements, recalls and physical custody.

The QR/scan custody console now exposes the complete MD physical-copy lifecycle supported by authoritative event records:

- register / label;
- check out with custody acknowledgement;
- check in / return;
- verify location;
- transfer to an active tenant custodian;
- location change;
- recall;
- damage incident with retained evidence;
- loss incident with retained evidence;
- withdrawal with reason/evidence;
- destruction with reason/evidence.

Damage/loss use the existing controlled-copy identity plus append-only event/audit evidence; no shadow custody record is introduced.

## 10. Compliance and External Technical Data

Compliance combines:

- periodic review;
- external-source currentness;
- governed relationships;
- applicability;
- superseded references.

### External revision assessment

The existing `ExternalRevisionReceipt` remains authoritative. The new assessment surface adds workflow over that retained receipt rather than copying it.

It shows:

- provider / authority / subscription context;
- last and next currency check;
- latest received revision;
- current source revision when one is confirmed;
- checksum/evidence context;
- confirmed affected internal documents;
- explicit `NEW REVISION REQUIRES ASSESSMENT` work state when the latest receipt is unverified/pending;
- applicability decision: APPLICABLE / PARTIAL / NOT APPLICABLE;
- assessor, timestamp and rationale evidence;
- append-only audit event `document.external_revision.assessed`.

## 11. Reports

Reports is no longer master-register-only. It exposes a bounded controlled evidence catalogue:

1. Master Documents
2. LEP
3. Revisions
4. Distribution
5. Acknowledgements
6. Controlled Copies
7. External Sources
8. Review Due
9. Temporary Revisions
10. Authority
11. Archive
12. Change History
13. Retention / Disposition

Common report capabilities include permission filtering, server pagination, search, status/date filtering where relevant, links back to evidence owners, safe current-page CSV export, and print/PDF output.

CSV values that could be interpreted as spreadsheet formulas are neutralized before quoting.

## 12. Administration

Administration is backend-authoritative and audited. Core defaults remain in `DocControlSettings`; extensible tenant DMS policy is stored in tenant `settings_json["document_control_admin"]`.

Governed administration includes:

- document classes;
- default retention and review interval;
- acknowledgement default;
- regulated-workflow default;
- technical/Quality/management review policy;
- authority routing policy;
- reusable retention classes;
- auto-index / source-checksum / retry policy;
- governed integration-module mappings;
- physical-copy due, custody acknowledgement, location verification and supersession-recall policy;
- specialist entry points for hierarchy/taxonomy, templates/forms, retained records, copy operations, relationship mappings and indexing exceptions.

Saving policy writes audit event `document.administration.updated`; it does not rewrite existing approved evidence.

## 13. Role and authority boundaries

Backend authorization remains authoritative.

- Readers receive permitted Home/Library/reader/acknowledgement surfaces only.
- Document Controllers receive the seven operational workspaces subject to backend capability.
- Technical, Quality and management decision authority remains enforced by backend workflow policy rather than frontend visibility.
- Tenant administration does not imply technical/Quality approval authority.
- Restricted source records are not exposed through Library/relationship/assistant summaries without source-module permission.

Role-matrix contracts remain part of the Document Control governance suite.

## 14. Performance and scale evidence

### Large Library

The release benchmark seeds 10,000 additional controlled documents on top of the deterministic governance fixture and enforces a **5 second maximum** for each measured query.

It measures:

- first 100-row default Library page;
- exact default Library search;
- exact rich discovery/index path search;
- returned rows remain bounded to requested page size.

Previous pre-expansion evidence on this PR demonstrated 10,003 visible documents with default first-page/exact-search response times in the tens of milliseconds. The final exact-head run is authoritative for merge readiness.

### Large PDF

The Governance release gate replaces the disposable browser fixture with a real 2,000-page PDF and preserves the hard bounds:

- first usable page <= 20 seconds;
- deep jumps to pages 100, 500, 1,000 and 1,999 <= 15 seconds each;
- <= 30 mounted PDF page nodes during deep navigation;
- no reader error state;
- production runtime must remain free of material page errors, server 500s, phantom HMR/WebSocket failures and anonymous preference 401s.

Post-#477 separately exercises authenticated real-PDF source, scrolling, zoom, navigator and responsive behavior.

## 15. Accessibility / responsive acceptance

Release acceptance covers:

- keyboard-focus visibility on primary Home action;
- 200% visual zoom without losing core Home work surfaces;
- light/dark desktop and 390px mobile tenant-shell geometry;
- navigation drawer final position inside viewport;
- mobile profile/appearance controls inside viewport;
- minimum contrast assertions in the shared tenant-shell test;
- responsive reader and controlled document surfaces.

Controller-heavy configuration remains progressively constrained on small screens rather than pretending to provide desktop-table parity.

## 16. Deterministic MD browser acceptance

`frontend/tests/e2e/document-control-md-completion.spec.ts` locks the expanded MD surfaces:

- all Library presets and contextual controlled-information search;
- all Reports evidence-register destinations;
- governed Administration policy sections;
- Review Changes -> Revision Intelligence and evidence-safe comparison controls;
- external technical-data assessment context;
- physical custody verification, incident evidence and withdrawal state.

The existing production acceptance additionally covers Home -> Library, category/external-source evidence, hard browser navigation, all controller workspaces, legacy route convergence, regulatory links, the eight-tab document workspace, real 2,000-page reader navigation and physical register -> QR -> checkout -> return.

## 17. Backend regression contracts added for MD completion

`test_document_control_md_completion_contract.py` locks:

- permission-filtered, <=100-row Library discovery;
- bounded/controller-only report registers;
- backend-authoritative/audited Administration;
- external assessment against existing revision receipts and governed relationships;
- damage/loss against existing controlled-copy/event identities;
- route precedence before the compatibility workspace router.

The Domain workflow now always uploads its JUnit XML, so future backend failures retain exact diagnostic evidence.

## 18. Data-integrity invariants preserved

This frontend refactor does **not** weaken:

- tenant isolation;
- immutable approved revisions;
- source checksums;
- current/superseded distinction;
- workflow/decision authority;
- QMS/training impact ownership;
- distribution and acknowledgement evidence;
- physical copy event evidence;
- external source receipt identity;
- generated retained records;
- source-module ownership of operational records.

No controlled business truth was moved into React state/localStorage as an authority.

## 19. Known capability-dependent limitations

- PDF visual overlay comparison is shown only when source geometry/data can support a reliable alignment. The product does not fabricate overlays.
- Automatic changed-page evidence is shown only where retained workflow/index evidence identifies changed pages; otherwise structured diff and explicit limitation text are used.
- Mobile remains primarily a read/search/acknowledgement surface; dense controller configuration uses progressive constraints rather than fake desktop parity.

These are evidence-safety constraints, not missing backend state.

## 20. Merge gate

PR #490 must remain draft until the **exact final head** proves all triggered DMS/shared workflows green after this evidence package and the expanded MD acceptance changes. Before ready-for-review:

1. verify current `main` and PR mergeability;
2. require one Alembic head on the synthetic PR merge ref;
3. require Document Control Domain CI green;
4. require Document Control Governance CI green, including clean PostgreSQL, 10k default + discovery benchmark and production 2,000-page acceptance;
5. require Publications Reader and post-#477 reader consolidation green;
6. require Portal Error Feedback, Quality and any triggered shared-module suites green;
7. resolve all actionable PR review threads;
8. update the PR body to the exact final SHA/run IDs and current-main base;
9. mark ready for review only after the above.

The PR must not be merged by the implementation agent unless explicitly instructed.
