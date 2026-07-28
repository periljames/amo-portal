# Document Control Overhaul — Detailed Implementation Progress and Defect Review Record

**Repository:** `periljames/amo-portal`  
**Feature branch:** `agent/document-control-domain-overhaul`  
**Pull request:** `#358`  
**Base branch:** `main`  
**Initial implementation date:** 24 July 2026  
**Progress record updated:** 25 July 2026  
**Release state:** Draft; automated validation and live tenant acceptance must be complete before merge  

---

## 1. Why this document exists

This is the operational engineering record for the Document Control overhaul. It complements `DOCUMENT_CONTROL_DOMAIN_OVERHAUL_20260724.md`, which records the approved architecture and intended domain behavior.

This file records:

- what has actually been implemented;
- the canonical code and database paths;
- defects found during implementation;
- why each defect occurred;
- how it was corrected;
- automated checks that protect the correction;
- remaining risks and acceptance work;
- the exact review sequence to use before merge or later maintenance.

A reviewer should not need to infer intended behavior from screenshots, old seeded pages, or commit messages. Where implementation and original design differ, this record describes the implemented behavior and the reason.

---

## 2. Current completion summary

### 2.1 Implemented

- One canonical Document Control workspace.
- Publications treated as the Library/reader capability within Document Control.
- Direct opening of the permitted immutable revision.
- Direct controlled-reader access for published revisions.
- Direct uncontrolled-reader access for authorized controllers reviewing drafts.
- Role-separated reader and controller dashboards.
- Server-side removal of governance data from reader responses.
- Database-backed changes, workflow, authority, temporary revisions, distribution, acknowledgements, reviews, controlled copies, external-source tracking, applicability, integration links, and reports.
- Evidence-backed authority and waiver rules.
- Publication blockers for unresolved changes, unresolved module links, missing authority evidence, and incomplete distribution preparation.
- Live source-record validation for cross-module links.
- Full document audit timeline assembled from the entity IDs contained by the unified document record.
- Clean PostgreSQL migration path for the new domain tables.
- Compatibility handling for malformed historical Alembic branch bookkeeping.
- Reader-safe route precedence contracts.
- Focused backend, route, migration and frontend build workflow.
- Detailed architecture, implementation, validation, acceptance and rollback documentation.

### 2.2 Still required before merge

- Latest-head focused workflow must be green after the most recent integration and workflow hardening commits.
- Full release-candidate workflow must complete all backend, frontend, migration, lint and performance stages.
- Branch must be synchronized with the latest `main` without overwriting concurrent module work.
- Browser acceptance must be performed in a live tenant using representative searchable DOCX, searchable PDF and image-only PDF sources.
- Light and dark theme visual acceptance must be completed.
- Controller, approver, auditor and ordinary-reader permission matrices must be exercised with real accounts.
- End-to-end QMS and Training publication blocking must be demonstrated using real source records.
- Distribution issuance and recipient acknowledgement must be demonstrated with active and inactive tenant users.

The pull request remains draft until these items are complete.

---

## 3. Canonical architecture implemented

### 3.1 Source-of-truth identities

| Domain object | Canonical source | Identifier contract |
|---|---|---|
| Controlled document | `manuals` | `manuals.id` |
| Immutable revision | `manual_revisions` | `manual_revisions.id` |
| Rendered reader sections | `manual_sections` | Revision-scoped section ID |
| Search/accessibility blocks | `manual_blocks` | Revision-scoped block ID |
| Governance profile | `document_control_profiles` | Tenant + manual |
| Change request | `document_change_requests` | Immutable request ID |
| Revision workflow | `document_workflow_instances` | Revision-level workflow ID |
| Workflow decision | `document_workflow_decisions` | Append-only decision ID |
| Authority submission | `document_authority_submissions` | Submission ID |
| Temporary revision | `document_temporary_revisions` | TR ID |
| Distribution campaign | `document_distribution_campaigns` | Campaign ID |
| Distribution recipient | `document_distribution_campaign_recipients` | Recipient row ID |
| Periodic review | `document_review_plans` | Review ID |
| Controlled copy | `document_controlled_copies` | Copy custody ID |
| External source | `external_document_sources` | Source ID |
| External revision receipt | `external_revision_receipts` | Receipt ID |
| Applicability rule | `document_applicability_rules` | Rule ID |
| Cross-module link | `document_integration_links` | Integration link ID |
| Audit evidence | Existing `manual_audit_logs` | Append-only audit row ID |

### 3.2 Why the existing Manuals schema remains authoritative

The reader, source storage, revision identity, publication status, bookmarks, extracted sections and controlled PDF behavior already existed in the Manuals domain. Creating another document table would have produced competing identities and broken existing deep links.

The overhaul therefore adds governance around the existing records. It does not duplicate source files or create a second publication identity.

### 3.3 Document classes

The governance profile distinguishes:

- `INTERNAL` — organization-authored manuals, procedures, policies, instructions, forms and checklists;
- `EXTERNAL` — OEM, authority, supplier and other externally issued technical data controlled for receipt, currency, applicability and access;
- `RECORD` — immutable approval, submission, acknowledgement, withdrawal and audit evidence.

---

## 4. Backend implementation map

### 4.1 Domain models

**File:** `backend/amodb/apps/doc_control/domain_models.py`

Implemented model groups:

- `DocumentControlProfile`
- `DocumentChangeRequest`
- `DocumentWorkflowInstance`
- `DocumentWorkflowDecision`
- `DocumentAuthoritySubmission`
- `DocumentTemporaryRevision`
- `DocumentDistributionCampaign`
- `DocumentDistributionRecipient`
- `DocumentReviewPlan`
- `DocumentControlledCopy`
- `DocumentControlledCopyEvent`
- `ExternalDocumentSource`
- `ExternalRevisionReceipt`
- `DocumentApplicabilityRule`
- `DocumentIntegrationLink`

All records are tenant-scoped and reference the canonical manual or revision where applicable.

### 4.2 Workspace API

**Primary files:**

- `backend/amodb/apps/doc_control/workspace_router.py`
- `backend/amodb/apps/doc_control/workspace_reports_router.py`
- `backend/amodb/apps/doc_control/workspace_schemas.py`
- `backend/amodb/apps/doc_control/workspace_service.py`

The original workspace router remains the broad compatibility implementation. Narrow first-registered routers now protect high-risk endpoint contracts without duplicating the full router:

- `workspace_dashboard_router.py` — reader-safe dashboard projection;
- `workspace_library_router.py` — access filtering before pagination and reader-safe library projection;
- `workspace_record_router.py` — reader-safe document detail and complete controller audit history;
- `workspace_workflow_router.py` — evidence-backed readiness and publication safeguards;
- `workspace_integration_router.py` — live tenant source-record verification and refresh;
- `workspace_access.py` — coarse fail-closed route boundary for controller worklists and reports.

**Composition file:** `backend/amodb/apps/doc_control/router.py`

The order of router registration is part of the security contract because Starlette resolves matching routes in declaration order. Tests assert that the safe override endpoints are first.

### 4.3 Reader versus controller response contract

Ordinary active users may:

- load the reader-safe dashboard;
- search the permitted Library;
- open the permitted published revision;
- open a document deep link and be redirected to the permitted revision;
- submit a reader-originated change request;
- acknowledge a distribution assigned to their own user account.

Ordinary users do not receive:

- draft revision metadata;
- workflow records;
- approval decisions;
- authority submissions;
- aggregate acknowledgement status;
- other recipients;
- controlled-copy custody;
- internal integration links;
- internal access-scope configuration;
- controller audit history;
- controller reports and operational worklists.

Controllers receive the complete unified record.

### 4.4 Controller and approver roles

The implementation uses roles present in the authoritative Accounts model:

- `SUPERUSER`
- `AMO_ADMIN`
- `QUALITY_MANAGER`
- `QUALITY_INSPECTOR`

`AUDITOR` is not treated as a mutation-capable Document Control role. A nonexistent `DOCUMENT_CONTROL_OFFICER` string is deliberately rejected. A dedicated officer role must be introduced through the shared RBAC/capability schema, seed data and migration before it is accepted by this domain.

Approval actions use the narrower approver check. Ordinary users and auditors cannot change readiness, publish, archive, issue controlled copies, alter authority state, or enumerate controller reports.

---

## 5. Frontend implementation map

### 5.1 Canonical pages

**Directory:** `frontend/src/pages/documentControl/`

- `DocumentControlDashboardPage.tsx`
- `DocumentControlLibraryPage.tsx`
- `DocumentControlRecordEntryPage.tsx`
- `DocumentControlRecordPage.tsx`
- `DocumentControlRecordActions.tsx`
- `DocumentControlWorklistPages.tsx`
- `DocumentControlShell.tsx`
- `documentControlWorkspace.css`

### 5.2 Landing behavior

- Controller personas enter the Control Desk.
- Reader personas see a compact Library-focused dashboard.
- The dashboard no longer exposes controller workload metrics to readers.
- The Library row is the primary navigation surface.
- Published documents use `Read current issue`.
- Authorized controllers without a published issue use `Read uncontrolled draft`.
- A reader opening a document-record URL is redirected to the permitted immutable revision rather than shown empty governance tabs.

### 5.3 Controlled intake

The Library retains PDF/DOCX intake for authorized controllers.

The intake process:

1. inspects the source;
2. shows extracted metadata and outline information;
3. requires reviewed code, title, type, issue and revision metadata;
4. uploads through the existing Publications ingestion endpoint;
5. reasserts reviewed identity metadata after ingestion so a first PDF bookmark such as `CHAPTER 0: FRONT MATTER` cannot silently become the document title;
6. opens the newly created revision in the uncontrolled reader.

### 5.4 Reader routing

`DocumentControlRecordEntryPage.tsx` prevents ordinary readers from becoming lost on the control record:

- it loads the server-provided role capability;
- controllers proceed to the unified record;
- readers resolve the read target;
- readers are redirected to the immutable reader route;
- users without a readable revision return to the Library.

### 5.5 Navigation consolidation

`DepartmentLayout.tsx` relabels and consolidates the historical Publications/Manuals affordance into Document Control. Historical routes redirect into the canonical Library while immutable reader deep links remain supported.

---

## 6. Workflow and publication rules

### 6.1 Lifecycle

```text
DRAFT
  -> TECHNICAL_REVIEW
  -> TECHNICAL_APPROVED
  -> QUALITY_REVIEW
  -> QUALITY_APPROVED
  -> ACCOUNTABLE_MANAGER_APPROVAL
  -> AUTHORITY_SUBMITTED        [when required]
  -> AUTHORITY_APPROVED         [when required]
  -> SCHEDULED_FOR_EFFECTIVITY
  -> PUBLISHED
  -> ARCHIVED
```

`CORRECTIONS_REQUIRED` returns the revision to an editable draft and supports controlled resubmission.

### 6.2 Immutability

When a revision is published:

- its status becomes published;
- `immutable_locked` becomes true;
- publication time is set;
- any previously published revision is superseded;
- the document's `current_published_rev_id` changes atomically;
- an event is emitted;
- the source reader continues to reference the immutable revision ID.

### 6.3 Publication blockers

Publication is blocked when any of the following is true:

- an open or implementing change request remains unresolved;
- Training impact is required but not ready or evidenced as waived;
- QMS readiness is not ready, not required or evidenced as waived;
- distribution readiness has not been established by issuing a real campaign;
- authority approval is required but no approved authority submission exists;
- authority approval exists without retained evidence;
- the document profile requires acknowledgement but no issued campaign exists;
- an issued campaign has no active tenant recipients;
- a blocking cross-module link is unresolved;
- a linked source record cannot be reverified in its owning module;
- the scheduled effectivity time has not been reached.

### 6.4 Readiness is not a free-text override

The workflow transition API prevents manual `distribution = READY`. Distribution becomes ready only through the campaign issuance path.

Training and QMS readiness set to `READY` require a live, resolved integration link to the owning module.

A `WAIVED` readiness state requires:

- an approver;
- a recorded reason;
- supporting evidence.

---

## 7. Cross-module integration implementation

### 7.1 Supported modules

The integration schema supports:

- QMS
- Training
- Workforce
- Planning
- Production
- Maintenance
- Fleet
- Stores
- Technical Records

### 7.2 Live source verification

`workspace_integration_router.py` does not accept a client-provided status as authoritative.

For each link it:

1. resolves the entity type to an allowlisted table owned by the selected module;
2. verifies that the table exists in the loaded application metadata;
3. verifies an identity column;
4. verifies that the source table has an AMO or tenant boundary;
5. loads the source record;
6. rejects cross-tenant records;
7. reads the live source status where available;
8. stores the verified table, columns, status and verification time in link metadata;
9. provides a refresh endpoint;
10. refreshes linked status again during readiness and publication checks.

This avoids false links whose entity ID does not exist and avoids publication based on a stale client-supplied status.

### 7.3 Integration source allowlists

Each module has an allowlist of source-table prefixes. A Training link cannot point to `users`; a QMS link cannot point to an unrelated inventory table. An ambiguous or unknown entity type fails closed and returns the allowable module source tables.

### 7.4 Training and QMS

Training and QMS links have direct release significance:

- a Training-ready decision requires a live resolved Training record;
- a QMS-ready decision requires a live resolved QMS record;
- blocking status is refreshed again before publication;
- missing or cross-tenant source records block release.

---

## 8. Migration implementation and defects found

### 8.1 New migrations

- `document_control_20260724_domain_overhaul.py`
- `document_control_20260724_scope_fk_convergence.py`
- `document_control_20260724_distribution_integrity.py`

### 8.2 Historical graph defects exposed

The repository contained released Alembic branches with malformed or overlapping bookkeeping. Adding a new descendant exposed failures that were not caused by Document Control DDL itself.

Observed issues included:

- missing in-memory head markers during released merge traversal;
- redundant `phase2_14a_20260615` version rows;
- dependency heads being inserted alongside their descendants in the legacy probe;
- a Quality audit-scope table temporarily existing with a string key while another branch attempted to create a UUID foreign key.

### 8.3 Corrections

- `backend/sitecustomize.py` contains process-gated Alembic compatibility behavior.
- `backend/amodb/apps/doc_control/__init__.py` explicitly activates the hook for Alembic because console entry points did not consistently auto-discover repository-local `sitecustomize`.
- `backend/amodb/alembic/env.py` retains graph-verified compatibility handling.
- `quality_20260704_audit_scope_management.py` now creates an FK only when both sides are canonical UUIDs.
- `document_control_20260724_scope_fk_convergence.py` adds the canonical constraints after both Quality branches have converged.
- `postgres_migration_probe.py` now computes the real non-overlapping terminal version frontier rather than inserting every graph label into `alembic_version`.

The compatibility layer does not skip application DDL and does not blindly stamp target revisions.

### 8.4 Distribution integrity

`document_control_20260724_distribution_integrity.py` adds a partial unique index for campaign and recipient identity. A user cannot be added more than once to the same distribution campaign.

---

## 9. Defect register

| ID | Defect | Impact | Correction | Regression protection |
|---|---|---|---|---|
| DC-001 | Published-only dashboard target made drafts unreadable to controllers | Controllers were forced through record pages and could not inspect intake directly | Library resolves published target or latest uncontrolled revision by role | Library build and role tests |
| DC-002 | Publications and Document Control were separate navigation concepts | Users became lost between reading and governance | One Document Control workspace; Publications becomes Library | Route and navigation composition |
| DC-003 | Legacy pages displayed hardcoded operational records | Tenant UI falsely implied workflows existed | Canonical routes no longer export legacy seeded pages | CI source scan |
| DC-004 | PDF outline chapter could become document title | Manual displayed as `CHAPTER 0: FRONT MATTER` | Reviewed intake metadata is reasserted after upload | Intake implementation review |
| DC-005 | Library paginated before access/class filtering | Short pages, false totals and skipped permitted documents | Filter visible candidates before pagination | First-route contract and focused CI |
| DC-006 | Reader Library payload exposed draft/workflow aggregate information | Ordinary users could infer governance activity | Server-side reader projection | Access tests and route precedence |
| DC-007 | Reader record response contained controller arrays | Direct API access could expose workflow and audit detail | Server-side record projection; reader redirects to revision | Route contract and access tests |
| DC-008 | Controller worklist GET routes relied on frontend hiding | Ordinary users could enumerate governance records through API | Global fail-closed workspace route dependency | `test_normal_user_cannot_enumerate_controller_worklists` |
| DC-009 | Nonexistent `DOCUMENT_CONTROL_OFFICER` role was accepted as a string | Unprovisioned role could be treated as authoritative | Use only shared AccountRole values | Role invariant test |
| DC-010 | `AUDITOR` inherited mutation-capable controller access | Auditor could create or transition governance work | Auditor removed from control roles | Role invariant test |
| DC-011 | Workflow readiness fields could be marked ready manually | Publication could bypass owning modules | Distribution readiness system-managed; Training/QMS require live link | Release-guard tests |
| DC-012 | Open change requests were not included in release blockers | Revision could publish with known unresolved changes | Pre-publication change count blocker | Workflow guard implementation |
| DC-013 | Authority approval did not require retained evidence at release | Unsubstantiated approval could permit publication | Approved submission plus evidence required | Publication blocker logic |
| DC-014 | Integration link accepted arbitrary entity/status | Fake or stale records could clear blockers | Live table, ID, tenant and status verification | Integration allowlist tests |
| DC-015 | Audit history filtered only manual/revision entity IDs | Workflow, TR, distribution and copy actions were absent | Build timeline from all entity IDs in unified record | Record projection implementation |
| DC-016 | Duplicate campaign recipients could be created | Acknowledgement totals and reminders could be duplicated | Database partial unique index | Clean migration gate |
| DC-017 | Released Quality branch created FK before key types converged | Clean PostgreSQL migration failed | Guarded FK plus convergence migration | Clean PostgreSQL upgrade |
| DC-018 | Legacy migration probe inserted dependency heads with descendants | Probe produced an impossible overlapping current state | Terminal non-overlapping version frontier | Release-candidate legacy probe |
| DC-019 | Record entry shell omitted required subtitle | TypeScript build failed | Complete shell props | Publications Reader CI/build |

New defects found during review must be added to this table with a test or explicit acceptance step.

---

## 10. Automated validation

### 10.1 Dedicated workflow

**File:** `.github/workflows/document-control-domain-ci.yml`

The workflow performs:

- backend dependency installation;
- current-main migration baseline capture;
- Alembic graph inspection;
- clean PostgreSQL upgrade;
- backend compilation;
- SQLAlchemy mapper configuration;
- critical workspace route verification;
- reader-safe route precedence verification;
- Document Control invariant tests;
- frontend dependency installation;
- full TypeScript and Vite production build;
- source scan proving canonical routes do not re-export seeded legacy worklists;
- diagnostic artifact upload.

### 10.2 Domain tests

**Directory:** `backend/amodb/apps/doc_control/tests/`

Coverage includes:

- role and approver boundaries;
- public reader versus controller route boundaries;
- reader-safe override route ordering;
- invalid workflow transitions;
- authority path enforcement;
- published revision locking;
- correction reopening;
- distribution readiness system ownership;
- Training-ready live-link requirement;
- evidence-backed waiver requirement;
- integration source-table allowlists.

### 10.3 Existing suite compatibility

The full release-candidate workflow must still run:

- Quality contracts and regressions;
- SaaS control-plane contracts and regressions;
- account regressions;
- Workforce regressions;
- Rostering migration and behavior regressions;
- realtime and messaging regressions;
- worker smoke tests;
- production frontend build;
- bundle budgets;
- Quality/platform frontend tests;
- Rostering/offline tests;
- lint;
- constrained-network performance measurement.

A focused green workflow is not sufficient for merge if the release-candidate workflow is red.

---

## 11. Browser acceptance procedure

Use a tenant with realistic roles and active users.

### 11.1 Source documents

Upload:

1. one searchable DOCX with headings, tables and figures;
2. one searchable PDF with bookmarks, signatures, tables and figures;
3. one image-only PDF.

### 11.2 Personas

Test as:

- ordinary technician;
- view-only user;
- auditor;
- Quality Inspector acting as Document Controller;
- Quality Manager/approver;
- AMO administrator;
- inactive user;
- system account where applicable.

### 11.3 Mandatory checks

- Only one Document Control navigation entry is visible.
- Ordinary user lands in the Library experience.
- Controller lands on the Control Desk.
- Clicking a published Library row opens the reader immediately.
- Clicking a draft Library row as controller opens an uncontrolled reader immediately.
- Ordinary user cannot discover or open the draft.
- Document-record deep link redirects an ordinary user to the permitted revision.
- Controller document record shows all governance areas.
- Search, TOC and page navigation work on the original PDF.
- Original tables, figures, signatures and stamps remain intact.
- Dark theme controls are readable and the document page remains white.
- Intake title remains the reviewed title rather than the first chapter bookmark.
- Change request appears in the document record.
- Invalid workflow action is rejected.
- QMS blocker prevents publication until a real QMS source record resolves.
- Training blocker prevents publication until a real Training source record resolves.
- Authority-controlled revision cannot publish without evidence.
- Acknowledgement-required revision cannot publish without a real issued campaign and recipients.
- Inactive/system/cross-tenant users cannot become recipients.
- Recipient acknowledgement updates only that recipient.
- Temporary revision expiry appears as overdue.
- Controlled-copy issue, transfer, recall, return and destruction evidence persist.
- External-source currency and receipt evidence persist.
- Master register, LEP, archive and overdue reports match database records.
- Back-to-top and chat controls do not overlap.
- Tablet and mobile widths retain all primary actions.

### 11.4 Evidence to retain

- screenshots in light and dark themes;
- browser console log;
- failing network requests, if any;
- API request/response for each lifecycle transition;
- source document and rendered-reader comparison;
- user IDs and roles used;
- document ID and immutable revision ID;
- timestamps and audit rows;
- report exports.

---

## 12. Known review risks

1. A dedicated Document Control Officer account role is not yet part of the shared AccountRole enum. Quality Inspector is currently the narrow controller role.
2. The legacy Manuals audit table remains the append-only audit source. It is now assembled across the unified record's domain entity IDs, but a future audit-ledger consolidation must preserve historical rows.
3. Integration source-table verification depends on source models being registered in application metadata. The full mapper/route gate protects this in the deployed application.
4. The generic integration allowlist intentionally fails closed. New source entity types may require an explicit allowlist expansion.
5. Large document libraries currently perform access filtering in application memory before pagination to keep results correct. Production-scale optimization should move access scope into queryable relational fields or indexed predicates without changing result semantics.
6. Live browser acceptance cannot be claimed from repository-only validation.
7. Historical Alembic compatibility code is intentionally narrow. Do not broaden it into a general exception suppressor.
8. Old legacy routes remain for compatibility. Removal requires usage telemetry and a separate migration plan.

---

## 13. Review sequence before marking PR ready

1. Confirm branch is current with `main`.
2. Confirm PR is mergeable with no conflicts.
3. Confirm Document Control Domain CI is green on the final head.
4. Confirm Publications Reader CI is green on the final head.
5. Confirm full release-candidate workflow is green on the final head.
6. Review all inline PR findings and resolve each thread.
7. Execute the browser acceptance matrix.
8. Attach acceptance evidence or reference its controlled location.
9. Update this file with final run IDs, commit SHA and acceptance result.
10. Update the PR body with truthful final validation status.
11. Mark the PR ready for review.
12. Merge only after explicit approval.

---

## 14. Defect investigation procedure after deployment

For every defect:

1. capture tenant slug and AMO ID;
2. capture authenticated user ID and role;
3. capture route and query string;
4. capture document ID and revision ID;
5. capture workflow, campaign, TR, copy or integration ID where relevant;
6. capture timestamp and request correlation ID;
7. inspect the reader/API response before changing data;
8. inspect `manual_audit_logs` for every entity ID in the unified record;
9. verify source-module record and tenant boundary;
10. reproduce on a clean PostgreSQL database and an upgraded legacy database;
11. add a regression test;
12. correct the defect without weakening publication or tenant controls;
13. update the defect register in this document;
14. rerun focused and full release gates.

---

## 15. Final completion condition

The overhaul is complete only when:

- all automated workflows are green on the final synchronized head;
- no unresolved PR review thread remains;
- the browser acceptance matrix passes;
- representative document fidelity is accepted;
- reader/controller/approver permissions are accepted;
- QMS and Training integrations are demonstrated end to end;
- authority and distribution blockers are demonstrated end to end;
- no hardcoded operational rows appear on canonical routes;
- documentation reflects the final implementation and evidence;
- the PR is approved and merged through the repository's normal process.
