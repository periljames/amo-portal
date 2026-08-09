# AMO Portal DMS Frontend Operating Model

**Status:** Controlled frontend architecture contract  
**Date:** 2026-08-08  
**Repository:** `periljames/amo-portal`  
**Baseline:** `main@aa7e754eeeac73ae4adbcb0c0f537a8c1adb89c8`  
**Scope:** Document Control / Publications frontend operating model

## 1. Purpose

This document is the implementation contract for refactoring AMO Portal Document Control into a daily-use aviation controlled-information workspace. It deliberately separates the human operating model from the existing backend domain topology.

The product lifecycle is:

**Find → Read → Understand → Change → Review → Approve → Publish → Distribute → Acknowledge → Monitor → Retain → Prove**

The refactor MUST simplify the frontend without weakening tenant isolation, immutable approved revisions, append-only evidence, source checksums, lifecycle controls, role separation, physical-copy custody, current/superseded distinction, access restrictions, generated retained records, source-module ownership, distribution evidence, review evidence or authority evidence.

## 2. Repository audit baseline

### 2.1 Current canonical frontend ownership

The repository currently has two overlapping route surfaces. `frontend/src/router.tsx` is the canonical route classifier for Document Control and Publications and delegates remaining portal routes to `PortalRouteSurface`. `frontend/src/portalRoutes.tsx` still carries compatibility Document Control and legacy Quality-reader routes.

Current Document Control page exports are assembled through `frontend/src/pages/DocControlPages.tsx`.

Primary current owners:

- DMS shell/navigation: `frontend/src/pages/documentControl/DocumentControlShell.tsx`
- DMS home/control desk: `DocumentGovernanceDashboardPage.tsx`
- Integrated library: `DocumentLibraryHubPage.tsx`
- Document record entry: `DocumentControlRecordEntryPage.tsx`
- Document record workspace internals: `DocumentControlRecordPage.tsx`, `DocumentGovernanceRecordPage.tsx`
- Lifecycle/register worklists: `DocumentControlWorklistPages.tsx`
- Physical controlled copies: `DocumentLibraryCopiesPage.tsx`
- Publications bridge: `frontend/src/pages/DocControlPublicationsBridge.tsx`
- Reader route owner: `frontend/src/pages/manuals/ManualReaderPage.tsx`
- Canonical publication reader experience: `frontend/src/pages/manuals/PublicationsReaderPage.tsx`
- PDF renderer/layout engine: `frontend/src/pages/manuals/PublicationPdfLayoutViewer.tsx`
- Reader governance: `PublicationGovernancePanel.tsx` plus `readerGovernance` service/API
- Documentation assistant: `DocumentationAssistantPanel.tsx`

The canonical PDF engine MUST be retained unless a measured benchmark proves replacement is necessary. The refactor targets shell ownership, hierarchy, action prioritization, reader chrome and workflow cohesion first.

### 2.2 Current Document Control route fragmentation

Current canonical routes include separate destinations for:

- root/control desk;
- library;
- structure;
- generated records;
- document detail;
- drafts/workflows;
- change proposals;
- revision/LEP views;
- authority submissions;
- temporary revisions;
- distribution;
- periodic reviews;
- controlled copies;
- external sources;
- integrations;
- archive;
- registers;
- settings.

Compatibility routing also exists under `/maintenance/:amoCode/:department/doc-control/*` and `/doc-control/*`. These compatibility routes MUST redirect into the canonical operating model rather than retain separate page ownership.

### 2.3 Current reader capability that must be preserved

`PublicationsReaderPage` already provides substantial engineering capability:

- cached bootstrap state and background refresh;
- persisted page, anchor and zoom position;
- PDF layout and accessible-text modes;
- lazy section-content loading;
- indexed in-publication search;
- native PDF outline support;
- controlled acknowledgement;
- download/print handling;
- reader annotations/governance;
- current page tracking;
- PDF navigation requests;
- reader themes and reading widths.

The refactor MUST preserve these capabilities while making the document the dominant surface.

### 2.4 Backend source-of-truth boundary

The existing Document Control backend is authoritative and is NOT replaced by this frontend project. `backend/amodb/apps/doc_control/router.py` composes legacy compatibility plus hardened governance, reader-governance, knowledge, library, workflow, authority, copy, distribution, external-source, review, integration, reporting and temporary-revision routers under `/doc-control`.

Frontend work MUST consume these authoritative routes and add backend endpoints only where a bounded operational aggregate is genuinely missing. It MUST NOT create DMS shadow copies of QMS, Training, Workforce, Planning, Production, Fleet, Stores, Procurement, Technical Records or Reliability records.

## 3. Target information architecture

Permanent primary navigation is reduced to seven workspaces:

1. **Home** — personal/role work, exceptions, due soon, recent controlled changes, quick actions.
2. **Library** — controlled-information discovery and document workspaces.
3. **Changes** — change requests, revision packages, temporary revisions and authority stages as one lifecycle.
4. **Distribution** — digital distribution, acknowledgements, recalls and physical controlled-copy custody.
5. **Compliance** — periodic review, external technical-data currency, relationships, applicability and assurance context.
6. **Reports** — controlled registers and exportable evidence views.
7. **Administration** — low-frequency taxonomy, workflow policy, retention, indexing and configuration.

The frontend MUST NOT expose backend entity topology as permanent navigation.

## 4. Target route tree

The canonical tenant route root remains:

`/maintenance/:amoCode/document-control`

Target route tree:

```text
/maintenance/:amoCode/document-control
├── /                         Home / My Work
├── /library                  Library
│   ├── /:documentId          Unified Document Workspace
│   │   ├── ?tab=overview
│   │   ├── ?tab=content
│   │   ├── ?tab=changes
│   │   ├── ?tab=workflow
│   │   ├── ?tab=distribution
│   │   ├── ?tab=compliance
│   │   ├── ?tab=relationships
│   │   └── ?tab=history
│   └── saved/filter state encoded in query parameters
├── /changes                  Changes portfolio
│   └── /:changeId            Change/revision lifecycle workspace
├── /distribution             Distribution control
│   ├── /:distributionId      Distribution detail
│   └── /copies/:copyId       Controlled-copy custody detail
├── /compliance               Document assurance workspace
│   ├── ?view=reviews
│   ├── ?view=external
│   └── ?view=relationships
├── /reports                  Registers and reports
└── /administration           DMS configuration
```

Publication reading remains separately optimized under the existing Publications route family so reader chrome can be reduced independently of controller workspaces:

`/maintenance/:amoCode/publications/:documentId/rev/:revisionId/read`

Reader state that is meaningful across refresh/back-forward SHOULD be URL-addressable, including page, search term/result and review/comparison mode where practical.

## 5. Compatibility and redirect contract

Existing identifiers MUST be preserved. Old deep links remain accepted and redirect to the replacement view.

Planned mappings:

| Existing route | Replacement |
|---|---|
| `/document-control/drafts` | `/document-control/changes?view=in-review` or state-derived portfolio view |
| `/document-control/drafts/:draftId` | `/document-control/changes/:changeId` using authoritative workflow identity |
| `/document-control/change-proposals` | `/document-control/changes?view=requests` |
| `/document-control/change-proposals/:proposalId` | `/document-control/changes/:changeId` or document Changes tab when appropriate |
| `/document-control/revisions/:docId` | `/document-control/library/:docId?tab=changes` |
| `/document-control/lep/:docId` | `/document-control/library/:docId?tab=changes&view=lep` |
| `/document-control/authority` | `/document-control/changes?view=authority` |
| `/document-control/tr` | `/document-control/changes?view=temporary-revisions` |
| `/document-control/tr/:trId` | `/document-control/changes/:changeId` or resolved TR workspace |
| `/document-control/reviews` | `/document-control/compliance?view=reviews` |
| `/document-control/external-sources` | `/document-control/compliance?view=external` |
| `/document-control/integrations` | `/document-control/compliance?view=relationships` |
| `/document-control/controlled-copies` | `/document-control/distribution?view=physical-copies` |
| `/document-control/archive` | `/document-control/library?view=archived` |
| `/document-control/registers` | `/document-control/reports` |
| `/document-control/settings` | `/document-control/administration` |
| `/document-control/structure` | Library hierarchy/filter mode, not a permanent top-level destination |
| `/document-control/records` | Library/report filtered retained-record view, subject to controller permission |

The redirect layer MUST retain query/hash state where meaningful and MUST be deterministic on refresh.

## 6. Role-aware visibility

Backend authorization remains authoritative. Frontend visibility is an affordance only.

- **Ordinary employee / reader:** Home if useful, Library, reader, permitted acknowledgement actions and permitted relationships. No controller administration.
- **Document Controller:** all daily operational workspaces, lifecycle controls, distribution, compliance, reports and controller configuration permitted by backend capability.
- **Technical reviewer:** assigned work, relevant document workspace, comparison/review controls and technical decision actions only.
- **Quality role:** assigned quality review, compliance context, authority evidence and controlled decisions permitted by backend capability.
- **Management approver:** assigned approval decisions and required evidence without controller-only setup surfaces.
- **Tenant administrator:** DMS administration only where backend permission permits; administration does not imply authority to perform controlled Quality/technical decisions.

No frontend route, hidden button or client-side role cache may substitute for backend permission enforcement.

## 7. Desktop, tablet and mobile layout

### 7.1 Desktop 1440–1920

Desktop is the primary operating environment.

- persistent compact DMS command bar and seven-workspace navigation;
- full-width dense data tables;
- split panes where task context benefits from simultaneous visibility;
- sticky document identity/action headers;
- contextual right drawer instead of repeated modal navigation;
- no narrow centered marketing column;
- page titles are compact and operational.

### 7.2 1280 / smaller laptop

- retain table density;
- collapse optional context rail first;
- allow horizontally scroll-safe bounded tables;
- keep primary action and document identity visible.

### 7.3 Tablet

- compact workspace switcher;
- context drawers become overlays;
- tables may progressively hide lower-priority columns but retain semantics and row actions.

### 7.4 Mobile

Mobile is primarily read/access oriented. The reader, search, acknowledgement and permitted quick actions remain usable. Controller-heavy configuration and wide comparison flows may provide a constrained mobile presentation rather than fake desktop parity.

## 8. Home / My Work model

Home answers one question: **what needs attention now?**

Priority order:

1. My Work — assigned actionable decisions/tasks.
2. Exceptions — only real exceptions; zero-exception categories are not noisy cards.
3. Due Soon — date-bound obligations.
4. Recent Changes — meaningful controlled publication/review events.
5. Quick Actions — permission-aware common starts.

Every queue item must deep-link to the exact resolution context. Home must not become an analytics-card dashboard.

If current backend endpoints do not expose a bounded aggregate for Home, add one server-side aggregate endpoint rather than loading many complete registers into the browser.

## 9. Library model

The existing server-side integrated library is retained as the foundation.

Required frontend behavior:

- debounced metadata search;
- server-side filtering/sorting/pagination;
- saved/preset views such as All, My Documents, Recently Opened, Favorites, Recently Revised, Awaiting My Review, External Technical Data, Due for Review, Superseded and Archived;
- dense table as the primary presentation;
- query-string route state;
- stale-while-revalidate list behavior so filter/search changes do not blank the whole workspace;
- one primary row action plus compact secondary menu;
- direct Document Workspace open rather than raw governance forms.

The browser MUST NOT fetch the entire document population.

## 10. Unified Document Workspace

`/library/:documentId` becomes the single operational context for one controlled document.

### 10.1 Sticky identity header

Show code, title, type, current issue/revision, effective date, controlled status, internal/external source, owner and active workflow status without repeating page headings.

### 10.2 Action model

Render one state/role-derived primary action. Secondary actions live in a compact menu. The frontend must use backend-authoritative state and permissions.

### 10.3 Lifecycle stepper

Represent the actual revision lifecycle using authoritative workflow data. A generic example is:

`Draft → Technical Review → Quality Review → Accountable Manager → Authority → Release → Distribution`

Stages are shown only when applicable. Completion, current stage, actor, evidence and blockers are explicit.

### 10.4 Blockers

Blockers are first-class. Each blocker links to its resolution control. Do not bury missing assignments, authority evidence, linked-document problems, training impact or distribution prerequisites in long metadata forms.

### 10.5 Tabs

The canonical tab set is:

- Overview
- Content
- Changes
- Workflow
- Distribution
- Compliance
- Relationships
- History

Additional tabs require a documented reason.

Responsibility assignments are presented as a compact table, with unresolved assignments promoted above the fold.

## 11. Reader operating model

### 11.1 Canonical implementation

`ManualReaderPage → PublicationsReaderPage → PublicationPdfLayoutViewer` remains the canonical reader chain during the refactor. Post-#477 stability work is retained.

### 11.2 Modes

- Standard Reading
- Immersive
- Fullscreen
- Review / Compare
- Form mode only for actually editable controlled forms

### 11.3 Layout

Desktop reader:

```text
compact identity/action strip
┌──────────────┬──────────────────────────────────────────────┬──────────────┐
│ Contents /   │                                              │ Context      │
│ Pages /      │               DOCUMENT                       │ optional     │
│ Search       │                                              │ drawer       │
└──────────────┴──────────────────────────────────────────────┴──────────────┘
compact page / zoom / fit / fullscreen controls
```

The document canvas owns the majority of the viewport. Portal and DMS navigation must collapse in immersive/fullscreen modes.

Navigator requirements: Contents, thumbnails, search results, collapse, keyboard navigation, active-section tracking, scroll preservation and virtualization for very large manuals.

Toolbar requirements: navigation, page/current count, previous/next, zoom, fit page/width, search, print/download when permitted, fullscreen and overflow menu. Duplicated controls are removed.

### 11.4 Controlled state

Use compact explicit statuses: `CURRENT`, `UNCONTROLLED`, `DRAFT`, `SUPERSEDED`, `WITHDRAWN`.

Opening a superseded revision must show the current revision and a direct `Open current revision` action.

## 12. Revision intelligence

Comparison is an evidence feature, not decoration.

The UI supports, only where source data is reliable:

- revision reason and metadata;
- changed pages/sections;
- previous/next change navigation;
- changed-pages-only mode;
- side-by-side comparison;
- aligned visual overlay for compatible PDFs;
- indexed/structured text diff.

When reliable automated comparison is unavailable, display exactly that limitation rather than manufacturing a diff.

## 13. Changes lifecycle

The frontend consolidates Change Requests, Revision Workflows, Temporary Revisions and Authority Submissions into one Changes portfolio. Backend entities remain distinct.

Portfolio views include My Changes, Draft, In Review, Awaiting Quality, Awaiting Management, Authority Pending, Temporary Revisions, Ready for Release and Closed.

A change workspace shows document identity, reason, originating request, source/current/proposed revision, affected content, impact assessment, regulatory links, training/operational impact, review comments, stage, authority status and distribution consequence.

Authority submission and temporary-revision details remain part of the parent lifecycle rather than unrelated registers.

## 14. Distribution and physical custody

Distribution owns:

- digital issue populations;
- acknowledgement requirements/deadlines;
- acknowledged/overdue/failed delivery;
- recalls and supersession evidence;
- physical controlled copies;
- checkout, custody acknowledgement, return, transfer, location verification, recall, damage/loss, withdrawal/destruction evidence.

Current physical-copy state must be directly visible (`ON SHELF`, `CHECKED OUT`, `OVERDUE`, `RECALLED`, `WITHDRAWN`) without reconstructing an event log.

## 15. Compliance and external technical data

Compliance combines periodic review, external-source currentness, regulatory/document relationships, superseded references, unresolved applicability and cross-module impact.

Compliance context also appears inside the Document Workspace and reader where permitted.

External-source management displays provider, publication ID, current/received revision, last check, next review, currency, applicability, affected internal documents and assessment status. A newer source produces an explicit `NEW REVISION REQUIRES ASSESSMENT` work item.

## 16. Relationship model

DMS stores governed links, not copied operational records.

Relationship displays identify the owning source module and preserve permission checks. Examples include regulation → manual section → work instruction → form → generated record and audit finding → CAR → revised procedure.

Restricted source records are never exposed through relationship summaries to users who cannot access the source module record.

## 17. Reports and Administration

Reports consolidate master document register, LEP, revision, distribution, acknowledgement, controlled-copy, external-source, review-due, temporary-revision, authority-submission, archive, change-history and retention/disposition registers. Large exports are server bounded.

Administration contains low-frequency taxonomy, document classes, workflow policy, review intervals, acknowledgement defaults, retention classes, indexing, integration mappings, templates and physical-copy policy.

## 18. Search model

Four search concepts remain distinct:

1. Library metadata search.
2. In-document search.
3. Permission-filtered controlled-content search across the tenant.
4. Assisted search returning evidence-backed answers with exact current source, revision and section/page where available.

The Documentation Assistant is contextual and secondary. It must not be permanently mounted as a chat-first replacement for the DMS workspace.

## 19. State ownership

- URL/router state: workspace, document, tab, filters, page, comparison context and durable reader state where sensible.
- query/cache layer: server state, stale-while-revalidate data and prefetch.
- local component state: transient drawers, menus and unsaved UI affordances.
- backend: all business workflow truth, decisions, lifecycle, permissions and evidence.

No controlled business state is authoritative only in React state or localStorage.

## 20. Loading and error model

Avoid page blanking after initial route hydration.

- initial route may use contained skeleton/status UI;
- list refetch keeps last-known permitted rows visible;
- panel actions load locally;
- reader preserves canvas/page geometry during navigation/rendering;
- destination pages render before unrelated offscreen PDF work;
- stale rendering/search work is cancelable where the engine supports it.

User-facing errors are operational and retryable. Technical detail may be disclosed behind a secondary control. Controlled-record mutation failures must never be silently swallowed.

## 21. Accessibility contract

Every migrated surface must support keyboard navigation, visible focus, semantic tables, screen-reader labels, accessible menus, Escape-close for temporary overlays, appropriate focus restoration, reduced motion, sufficient contrast and at least 200% browser/text zoom without loss of core workflow.

Reader and dense-table accessibility must be tested, not assumed from component-library defaults.

## 22. Performance contract

### Library

- server-side pagination/filtering is mandatory;
- search is debounced;
- lists are bounded;
- large recipient/event/history sets are paginated or virtualized;
- query caches preserve prior usable state during refresh.

### Reader

Do not render every PDF page at once. Preserve virtualization, prioritize destination/adjacent pages, cache rendered pages only within a measured memory budget, cancel stale work and preserve approximate page geometry while high-resolution rendering catches up.

Acceptance datasets include 100, 500, 1,000 and 2,000+ page manuals where practical, and 1,000/10,000-document library fixtures where practical.

Measurements must include first usable page, toolbar ready, TOC jump, arbitrary page jump, zoom, fit width/page, first search result, search navigation, return-to-rendered-page latency, memory and browser stability.

## 23. Runtime issue investigation contract

### Vite HMR WebSocket

Production deployment must serve the built frontend and must not rely on development HMR. Development proxy/HMR configuration is investigated separately from DMS product behavior.

### Portal preferences 401

Investigate authentication hydration, credentials/cookies/token state, API wrapper behavior and route mounting. A successfully authenticated portal should not generate routine preference-sync 401s.

### PDF worker warnings

Do not suppress warnings blindly. Browser tests must prove render, text extraction, search, selection and rapid navigation on affected files.

### Reader zoom/theme

The zoom menu and all reader controls must be tested in light, dark and system modes and at standard browser zoom. Theme variables must keep menus readable.

## 24. Component ownership target

Shared DMS ownership should converge on components equivalent to:

- `DmsShell`
- `DmsPrimaryNavigation`
- `DmsCommandBar`
- `DmsStatusBadge`
- `DmsWorkQueue`
- `DocumentIdentityHeader`
- `DocumentLifecycleStepper`
- `DocumentActionMenu`
- `DocumentWorkspaceTabs`
- `DocumentResponsibilityTable`
- `DocumentRelationshipPanel`
- `DocumentHistoryTimeline`
- `RevisionComparisonWorkspace`
- `DistributionStatusPanel`
- `AuthorityStatusPanel`
- `ComplianceContextPanel`
- `DocumentSearch`
- `ReaderShell`
- `ReaderNavigator`
- `ReaderToolbar`
- `ReaderContextDrawer`

Names may vary, but parallel page-specific implementations of the same behavior are not acceptable.

## 25. Migration strategy

Implementation proceeds in buildable slices:

1. architecture contract, route registry/consolidation foundation and new shell;
2. Home / My Work;
3. Library;
4. Unified Document Workspace;
5. Reader immersive shell/stability;
6. revision comparison;
7. Changes lifecycle;
8. Distribution / controlled copies;
9. Compliance / external sources;
10. Reports / Administration and legacy removal.

Old frontend owners are removed only after their replacement routes and browser contracts are green. Compatibility redirects survive until references/bookmarks are verified.

The old AeroDoc frontend PR is not adopted as a second DMS architecture. Reusable concepts must be reconciled into the canonical Document Control backend and this operating model before inclusion.

## 26. Test and release contract

### Library

Load, search debounce, pagination, filters, role restrictions, document open, current/superseded behavior, empty states and failures.

### Document Workspace

Identity/current revision, workflow stage, blockers, assignments, revision history, role-derived primary action, permission denial, deep link and refresh.

### Reader

Real PDF files; outline, thumbnails, search, page/internal-link jump, zoom, fit modes, fullscreen, themes, form mode, print/download permissions, rapid navigation, virtualization, no snap-back and active-page correctness.

### Revision lifecycle

Current-vs-previous comparison, changed-page navigation, unavailable-comparison truthfulness, draft/current distinction, technical review, Quality review, management approval, authority submission/response, release, distribution and temporary revision.

### Distribution

Issue, acknowledgement, overdue, recall, controlled-copy checkout/return/overdue and QR resolution.

### Roles

At minimum Document Controller, Quality role, technical reviewer, ordinary reader and admin.

### Release gate

The PR remains draft until exact-head production build, backend compatibility, Document Control tests, Publications reader tests, authenticated browser acceptance, role isolation, large-library/large-PDF evidence and material console-error review are green.

## 27. CI baseline observation

At this baseline, the Document Control frontend build/contracts and separate Publications Reader/Post-477 consolidation workflows have recent successful evidence. A Document Control Governance CI run is blocked by a brittle migration assertion that expects the historical head `docgov_rel_20260807_merge` exactly. Repository migration evolution can legitimately place the Document Control ancestry under a newer single head. The governance workflow must therefore verify **one current Alembic head plus required Document Control ancestry**, not hard-code Document Control as the permanent repository head.

This CI correction is test-infrastructure hardening; it does not change DMS domain behavior.

## 28. Completion evidence required

Before this refactor is represented as complete, the exact final head must provide:

- final route tree and compatibility redirects;
- component ownership map;
- retained/replaced/removed screens;
- backend APIs reused and any bounded additions;
- performance measurements;
- accessibility evidence;
- browser and role acceptance results;
- large-PDF and large-library results;
- screenshots/browser artifacts for critical workflows;
- current known limitations;
- exact CI run identifiers.

Until those gates are met, the branch/PR stays draft.
