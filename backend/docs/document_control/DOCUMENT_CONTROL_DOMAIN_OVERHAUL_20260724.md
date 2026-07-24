# AMO Portal Document Control Domain Overhaul

**Document status:** Active implementation record  
**Date opened:** 24 July 2026  
**Branch:** `agent/document-control-domain-overhaul`  
**Target:** `main`  
**Scope owner:** Document Control / Publications domain  
**Primary acceptance source:** Safarilink Maintenance Training Manual, Issue 3, Revision 0, dated 24 December 2025

---

## 1. Purpose

This file is the permanent engineering, verification, and defect-triage record for the AMO Portal Document Control overhaul. It must be updated whenever the data model, workflow, API contract, route surface, integration behavior, or acceptance status changes.

The overhaul replaces the split and misleading arrangement in which:

- `Publications` acted as a reader and upload register;
- `Document Control` acted as a second module with partly static workflow pages;
- draft revisions were not directly readable from the library;
- the same document was represented by unrelated `manuals` and `doc_control_documents` records;
- dashboard metrics were approximated from title counts instead of operational database state;
- several tenant pages displayed hardcoded draft, distribution, temporary-revision, archive, and review examples;
- users had to navigate between two sidebar modules to read and control one manual.

The target is one coherent aviation document-control domain with one canonical document identity, one canonical revision identity, a faithful reader, database-backed governance, controlled distribution, traceable integrations, and honest status reporting.

---

## 2. Non-negotiable domain decisions

1. **Document Control is the only top-level module.**
2. **Publications is the Library workspace inside Document Control.**
3. **`manuals.id` is the canonical document identifier.**
4. **`manual_revisions.id` is the canonical revision identifier.**
5. **Published revisions are immutable.**
6. **Authorized controllers and reviewers may read drafts.** Draft access never implies operational approval.
7. **Every non-published PDF view, download, or print is visibly uncontrolled.**
8. **The original approved PDF is the authoritative visual artifact.** Extracted text is an accessibility/search representation, not a replacement master.
9. **Every workflow page must use tenant-scoped database records.** No seeded tenant data, fixed arrays, fabricated percentages, or placeholder operational metrics are permitted.
10. **External technical data is controlled differently from internally authored manuals.**
11. **Cross-module records remain owned by their source modules.** Document Control links to QMS, Training, Planning, Maintenance, Production, Stores, Fleet, and Workforce records without copying their state.
12. **All state transitions are server-authoritative and audit logged.**
13. **Historical `/manuals` and `/publications` links remain compatible through redirects or canonical reader routes.**
14. **Ordinary staff receive a reading-first experience. Controllers receive a control-desk experience.**

---

## 3. Canonical architecture

### 3.1 Content and revision authority

The existing `manuals` domain remains the authority for:

- tenant publication identity;
- publication code and title;
- publication category/type;
- immutable revision identity;
- issue and revision labels;
- source file metadata and checksum;
- extracted sections and blocks;
- reader progress and bookmarks;
- publication acknowledgements;
- regulatory requirement links;
- PDF output and print records;
- publication audit events.

The Document Control domain must not create another editable copy of the publication body or revision label.

### 3.2 Governance authority

The `doc_control` domain owns:

- control profiles attached to canonical manuals;
- change requests and impact assessments;
- revision workflow instances and decisions;
- authority submissions and responses;
- temporary revisions;
- controlled distribution campaigns and recipients;
- periodic review plans and review evidence;
- numbered controlled copies and custody events;
- external-source currency records;
- applicability rules;
- cross-module integration links;
- operational dashboard projections.

### 3.3 Compatibility

Legacy `doc_control_documents`, drafts, proposals, revision packages, TRs, distributions, reviews, and archives remain readable during migration. New workflows must attach to `manual_id` and `revision_id`. Legacy rows without canonical links must not appear as current tenant truth unless successfully reconciled.

---

## 4. Document classes

### 4.1 Organization-controlled documents

Examples:

- Maintenance Procedures Manual;
- Quality Manual;
- Maintenance Training Manual;
- Safety Management Manual;
- procedures;
- work instructions;
- forms and checklists;
- policies.

These use the complete internal review, approval, authority, effectivity, distribution, and supersession lifecycle.

### 4.2 External controlled technical data

Examples:

- AMM, IPC, CMM, SRM and WDM publications;
- service bulletins;
- airworthiness directives;
- KCAA, EASA and FAA instruments;
- OEM planning data;
- vendor instructions.

The AMO controls receipt, revision currency, applicability, access, distribution, and proof of the revision used. The AMO does not rewrite the external source as an internally approved manual.

### 4.3 Records and evidence

Examples:

- approval signatures;
- authority correspondence;
- distribution evidence;
- acknowledgement evidence;
- controlled-copy custody records;
- withdrawal and destruction evidence;
- audit evidence;
- submission receipts.

These are immutable records linked to the relevant document, revision, workflow, or campaign.

---

## 5. Controlled revision lifecycle

The target lifecycle is:

```text
DRAFT
  -> TECHNICAL_REVIEW
  -> CORRECTIONS_REQUIRED
  -> TECHNICAL_APPROVED
  -> QUALITY_REVIEW
  -> QUALITY_APPROVED
  -> ACCOUNTABLE_MANAGER_APPROVAL
  -> AUTHORITY_SUBMITTED          [conditional]
  -> AUTHORITY_APPROVED           [conditional]
  -> SCHEDULED_FOR_EFFECTIVITY
  -> PUBLISHED
  -> SUPERSEDED
  -> ARCHIVED
```

### 5.1 Transition invariants

- A published revision cannot return to an editable state.
- A rejected review returns the workflow to `CORRECTIONS_REQUIRED`, not silently to a clean draft.
- A workflow requiring authority approval cannot reach publication without an approved authority submission and evidence reference.
- A revision with identified training impact cannot reach publication until the training readiness gate is satisfied or a documented authorized waiver is recorded.
- A revision with unresolved QMS blockers cannot reach publication.
- A revision cannot become effective before its required distribution campaign is issued.
- A revision requiring acknowledgement cannot close distribution until overdue recipients are resolved or formally exempted.
- Publishing a new revision supersedes the previous published revision atomically.
- Every transition records actor, role/capability, timestamp, reason, comments, previous state, next state, source IP/device, and relevant evidence identifiers.

---

## 6. User experience contract

### 6.1 Sidebar

Only one top-level item is presented: **Document Control**.

The historical Publications button is removed from normal navigation. Existing publication reader URLs remain valid.

### 6.2 Default landing behavior

- Ordinary users land in **Library**.
- Users with document-control capabilities land in **Control Desk**.
- The page remembers the last valid workspace without overriding permission changes.

### 6.3 Library row behavior

Each document row has one truthful primary action:

- `Continue reading` when saved progress exists;
- `Read current issue` when a published revision exists;
- `Read draft` when the user is authorized and only a draft/review revision exists;
- `View record` only when no readable revision exists;
- `Resolve access` when the document exists but policy prevents access.

The entire row is keyboard and pointer accessible. Record governance actions remain secondary.

### 6.4 Unified document record

A document record provides these views without leaving the domain:

- Read;
- Overview;
- Revisions;
- Changes;
- Workflow;
- Authority;
- Temporary revisions;
- Distribution;
- Acknowledgements;
- Compliance links;
- Applicability;
- Controlled copies;
- Reviews;
- History;
- Evidence.

---

## 7. Cross-module integration contract

### 7.1 Quality / QMS

Document Control may link to:

- audit findings;
- CARs and corrective actions;
- audit reports;
- change drivers;
- compliance requirements.

QMS remains authoritative for finding and CAR state. A linked blocking item is projected into the document workflow. Closing a QMS record must update workflow readiness through an event or live read, not copied text.

### 7.2 Training and competence

A change request and revision workflow record:

- whether training impact exists;
- affected roles, departments, bases, and authorization groups;
- required course, briefing, or read-and-understand action;
- training readiness status;
- linked training event/course identifiers.

Training remains authoritative for attendance and competence completion.

### 7.3 Planning, Production, Maintenance, and Work Orders

Document revisions may link to:

- work packages;
- work orders;
- task cards;
- defects and non-routines;
- maintenance programme tasks;
- engineering orders;
- aircraft allocations.

The link proves which source revision governed the work. Operational records must store immutable revision IDs, not mutable publication labels.

### 7.4 Fleet and technical records

Applicability rules may target:

- aircraft type/model;
- registration;
- serial number range;
- engine or component type;
- station/base;
- department;
- role or authorization group.

Fleet remains authoritative for aircraft and component identity.

### 7.5 Stores and procurement

External technical data and supplier instructions may link to:

- supplier records;
- purchase orders;
- receiving inspections;
- parts and tool records.

### 7.6 Workforce and accounts

Recipient, reviewer, approver, custodian, and owner identities always reference canonical active tenant users. Inactive, suspended, system, or cross-tenant users cannot receive new controlled responsibilities.

### 7.7 Notifications and events

The domain emits events for:

- change request created/assigned/decided;
- workflow state changed;
- approval requested/decided;
- authority submission sent/responded;
- revision scheduled/published/superseded;
- distribution issued;
- acknowledgement due/overdue/completed;
- TR approaching expiry/expired/incorporated;
- periodic review due/completed;
- controlled copy issued/transferred/recalled/withdrawn;
- external source revision received/verified/overdue.

---

## 8. API contract principles

- Tenant is resolved from the authenticated user and validated against the route workspace.
- Raw storage paths never leave the backend.
- All list endpoints support pagination, filtering, stable ordering, and truthful empty states.
- Mutations use capability checks and optimistic concurrency where concurrent edits are possible.
- Database writes and audit events commit atomically.
- Reader targets return immutable `manual_id` and `revision_id` values.
- Dashboard metrics are calculated from persisted state only.
- The API distinguishes `document_count`, `draft_revision_count`, `published_revision_count`, and `effective_publication_count`.
- No API calls a draft a controlled issue in force.

---

## 9. Implementation phases and progress

### Phase 0 - Restore direct usability

- [ ] Collapse the sidebar to one Document Control entry.
- [ ] Redirect Publications root and record routes into the Document Control library/record surface.
- [ ] Preserve canonical reader routes.
- [ ] Add a server-authoritative read-target endpoint.
- [ ] Permit authorized draft reading with uncontrolled markings.
- [ ] Correct PDF title extraction so an outline chapter cannot silently become the document title.
- [ ] Replace contradictory dashboard labels.
- [ ] Repair floating support control accessibility and collision behavior where owned by this module.

### Phase 1 - Remove false tenant workflows

- [ ] Remove all hardcoded draft rows.
- [ ] Remove all hardcoded change proposals.
- [ ] Remove all hardcoded TR rows.
- [ ] Remove all hardcoded distribution rows.
- [ ] Remove all hardcoded archive rows.
- [ ] Remove all hardcoded review rows.
- [ ] Replace placeholder actions with real endpoints or an explicit not-configured state.
- [ ] Add canonical control profiles linked to manuals.
- [ ] Reconcile legacy rows to canonical manual/revision IDs where safe.

### Phase 2 - Operational document control

- [ ] Change requests and impact assessment.
- [ ] Revision workflow and approval decisions.
- [ ] Authority submission and response tracking.
- [ ] Temporary revision lifecycle.
- [ ] Distribution campaigns and acknowledgement escalation.
- [ ] Periodic review programme.
- [ ] Controlled hard-copy custody and withdrawal.
- [ ] Archive and retention evidence.
- [ ] Master register, LEP, overdue and status reports.

### Phase 3 - Integrated intelligence

- [ ] QMS finding/CAR integration.
- [ ] Training impact and readiness integration.
- [ ] Work order/task/work-package revision evidence.
- [ ] Fleet and component applicability.
- [ ] External technical-data currency monitoring.
- [ ] Regulatory requirement and section mapping.
- [ ] Event-driven notifications.
- [ ] Offline-safe reading contract.
- [ ] Search and AI hooks constrained to authorized source content.

---

## 10. Verification matrix

### 10.1 Backend

- Alembic graph has no unintended new head collision.
- Clean PostgreSQL upgrade reaches all heads.
- Legacy multi-head compatibility probe remains successful.
- SQLAlchemy mapper configuration succeeds.
- Tenant isolation is tested for every new list and mutation route.
- Capabilities are tested for reader, controller, reviewer, approver, and administrator personas.
- Published immutability is tested.
- Draft reader target behavior is tested.
- Workflow transitions and blockers are tested.
- Authority-required and authority-not-required paths are tested.
- Training and QMS blockers are tested.
- Distribution and acknowledgement due-state calculations are tested.
- TR expiry and incorporation are tested.
- Controlled-copy custody transitions are tested.
- External-source currentness is tested.

### 10.2 Frontend

- Document Control is the only sidebar entry for this domain.
- Library rows open the correct reader target with one action.
- Draft and published badges are unambiguous.
- Controller and ordinary-user landing behavior differs correctly.
- Every workspace has loading, empty, error, and populated states.
- No page imports or renders seeded operational arrays.
- All forms validate required fields and preserve server errors.
- Tables remain usable at 1366x768, tablet, mobile, and ultrawide sizes.
- Light and dark themes remain readable.
- Keyboard navigation and focus states are present.
- Reader routes continue to render the original PDF layout.

### 10.3 Integration

- QMS-linked blockers reflect current QMS state.
- Training readiness reflects source training records.
- Work-order evidence stores immutable revision IDs.
- Fleet applicability uses canonical aircraft/component IDs.
- Recipient selection excludes inactive and cross-tenant users.
- Domain events are emitted once per committed transition.

### 10.4 Performance

- Library initial load is paginated and does not fetch complete revision bodies.
- Control Desk uses one summary endpoint instead of request fan-out.
- Reader remains lazy and virtualized.
- Search requests are debounced and cancellable.
- No large source file is embedded in JSON.

---

## 11. Defect-triage procedure

For every future defect, record:

1. observed behavior;
2. expected domain invariant;
3. tenant/user role;
4. route and immutable IDs;
5. request/response or event evidence;
6. relevant database rows;
7. root cause;
8. repair commit;
9. regression test added;
10. deployment or migration action;
11. verification result.

Do not close a defect based only on successful compilation. Reproduce the user workflow and verify the persisted state transition.

---

## 12. Progress log

### 24 July 2026 - Architecture baseline

- Confirmed the split Publications/Document Control experience is rejected.
- Confirmed `manuals` and `manual_revisions` will remain canonical document and revision identities.
- Confirmed all phases are in scope.
- Created the isolated implementation branch.
- Created this review and defect-triage record.
- Began repository audit of manuals, Document Control, routing, reader, navigation, and cross-module extension points.

---

## 13. Known pre-implementation defects

| ID | Severity | Defect | Confirmed cause | Target phase |
|---|---|---|---|---|
| DC-001 | P1 | Draft manual cannot be opened directly from the library | UI uses only `current_published_rev_id` as the row reader target | Phase 0 |
| DC-002 | P1 | Publications and Document Control form a navigation loop | Separate top-level modules and bridge buttons | Phase 0 |
| DC-003 | P1 | Production tenant pages contain hardcoded operational records | Legacy frontend arrays remain routed for drafts, proposals, TRs, distribution, archive, and reviews | Phase 1 |
| DC-004 | P1 | Dashboard metrics misrepresent document state | Counts are inferred from manual totals rather than workflow records | Phase 1 |
| DC-005 | P2 | PDF title may become the first outline chapter | Fallback title selection uses `outline[0]` | Phase 0 |
| DC-006 | P1 | Canonical manuals and legacy controlled documents are not reliably linked | Parallel domain identities use code strings instead of canonical IDs | Phase 1 |
| DC-007 | P1 | Approval, authority, distribution, review, and archive screens are incomplete | Placeholder UI and partial legacy endpoints | Phase 2 |
| DC-008 | P1 | QMS, Training, Work, Fleet, and Stores links are not governed by one integration contract | No canonical document integration-link model | Phase 3 |

---

## 14. Completion definition

The overhaul is complete only when:

- users can reliably find and read the correct permitted revision;
- controllers can progress a real document through all applicable governance stages;
- no tenant operational page uses hardcoded records;
- every published document is traceable to approvals, authority evidence where required, distribution, acknowledgements, applicability, and source checksum;
- every superseded or withdrawn copy has traceable disposition;
- linked modules resolve the same immutable document and revision identities;
- automated tests and browser acceptance cover the complete workflow;
- this document accurately records final implementation and residual limitations.
