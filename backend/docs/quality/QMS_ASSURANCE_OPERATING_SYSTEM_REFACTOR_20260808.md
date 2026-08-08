# QMS Assurance Operating System Refactor

**Date:** 2026-08-08  
**Status:** Active implementation — Phase A stabilized; Audit Programme + Audit Universe implemented and under exact-head validation  
**Pull request:** `#488` — **DRAFT**  
**Branch:** `agent/qms-assurance-operating-system-refactor`  
**Current base verified:** `main@aa7e754eeeac73ae4adbcb0c0f537a8c1adb89c8`

## 1. Permanent product model

The Quality module is an aviation **Assurance Operating System**. Its permanent top-level operating model is:

```text
CONTROL ROOM | PLANNER | MISSIONS | PEOPLE | ASSURANCE | INTELLIGENCE
```

This six-workspace model does **not** flatten specialist audit operations. Audits remain a deep operational domain inside Assurance with their own programme, planner, execution, findings, evidence, report, CAR, closeout and follow-up routes.

Quality exists to answer:

1. What requires action?
2. Why does it require action?
3. By when?
4. What approval, capability or control is exposed?
5. What authoritative evidence supports the conclusion?
6. What decision or assurance action is required next?
7. Did the corrective action actually work?

## 2. Source ownership

Quality must not copy authoritative operational master data simply because it needs to audit or assure it.

| Domain | Authoritative owner | Quality responsibility |
|---|---|---|
| Audits / findings / CAR / effectiveness | Quality | governed programme, execution, evidence, decisions and follow-up |
| Training / competence records | Training | reference evidence; Quality owns internal privilege decisions later |
| Workforce / roster / leave | Workforce / Rostering | reference availability and future coverage |
| Tooling / calibration | Tooling / Workshops | reference calibration state and exposure |
| Suppliers / procurement / receipts | Procurement / Stores | supplier assurance and surveillance decisions |
| Controlled manuals / procedures | DMS / Document Control | requirement and checklist references; no copied controlled text |
| Work orders / workpacks / defects | Maintenance | sampling, surveillance, findings and trend references |
| Fleet / aircraft records | Fleet / Technical Records | capability and aircraft surveillance references |
| Reliability | Reliability | source signals and exposure context |
| Safety occurrences | Safety / SMS | linked assurance context where legitimately available |
| Finance | Finance | no duplicated Quality records |

The new Audit Universe follows this rule by storing a typed source pointer rather than a copied supplier, department, station, aircraft or personnel master record.

## 3. Audit Operations target lifecycle

The governing lifecycle is:

```text
PROGRAMME
   ↓
PLAN
   ↓
SCHEDULE
   ↓
PREPARE
   ↓
NOTIFY
   ↓
EXECUTE
   ↓
FINDINGS
   ↓
REPORT
   ↓
CAR / FOLLOW-UP
   ↓
EFFECTIVENESS
   ↓
CLOSEOUT
   ↓
TREND
```

These are workflow states and gates, not cosmetic tabs. Existing specialist audit pages are retained while the lifecycle is progressively strengthened.

### Audit execution closure is not assurance closure

The architecture distinguishes:

```text
AUDIT EXECUTION CLOSED
```

from:

```text
ASSURANCE FOLLOW-UP COMPLETE
```

An issued report can close field execution while findings, CARs, effectiveness reviews or follow-up audits remain open.

## 4. Phase A stabilization — complete

Phase A was frozen and proven on exact head:

```text
5621c155b9398a8ebb0ac298d3efb67e3b723dd0
```

with base:

```text
main@aa7e754eeeac73ae4adbcb0c0f537a8c1adb89c8
```

### Repaired defects

- Mission browser fixtures now use the exact governed backend gate titles.
- Best-effort realtime presence/token bootstrap failures no longer masquerade as persistent failed user actions and block Quality navigation.
- Governed QMS dialogs restore focus to their opener; Planner keyboard quick-create returns focus to its canonical Quick Schedule control.
- Assurance workspace and specialist Audit Operations navigation are semantically distinct without removing audit workflow depth.

### Exact-head acceptance

Quality Module CI run `31269405823` passed on `5621c155...`, including:

- Quality frontend unit tests;
- CSS ownership checks;
- production build/typecheck;
- Control Room Playwright;
- Quality navigation/CAR Playwright;
- Mission Playwright;
- bounded-register Playwright;
- modern Planner Playwright;
- Planner lifecycle Playwright;
- Planner audit handoff Playwright;
- Quality frontend lint;
- backend Quality contracts;
- PostgreSQL Quality schema probe;
- continuous-assurance RLS probe;
- Mission migration/RLS probe.

Portal Error Feedback CI was also green on that stabilization head.

## 5. Existing audit systems retained

The repository already contains substantial functional audit capability. It is being extended, not replaced.

### Existing audit execution domain

`QMSAudit`, `QMSAuditFinding`, evidence, CAR and specialist audit routes remain the execution source of truth.

Existing execution features include:

- audit records and generated references;
- planned / actual execution dates;
- auditors and auditees;
- notice/reminder fields;
- checklist execution;
- findings;
- evidence;
- CAR lifecycle;
- report / closeout surfaces;
- the Audit War Room.

### Existing recurring schedule engine

The modern audit planner and `planner_schedule` domain already provide useful scheduling machinery including:

- tenant-owned schedules;
- recurrence source/occurrence relationships;
- timezone and location fields;
- responsible users and attendees;
- lifecycle/suspension state;
- controlled reschedule reasons;
- optimistic versioning;
- recurrence materialization;
- calendar/list/table projections;
- Planner → authoritative Audit Planner handoff.

This engine remains the schedule authority. The Audit Programme does not create a second scheduling system.

## 6. 2026-08-08 audit-domain gap map

The following findings are based on the implementation inspected on PR #488.

| Area | Existing state | Gap / action |
|---|---|---|
| Annual Audit Programme | old `Programme` surface was effectively a recurring schedule projection | **Slice 2 implemented governed versioned programme entity/API/UI** |
| Audit Universe | absent | **Slice 2 implemented typed authoritative-source catalogue** |
| Programme approval history | absent as a first-class immutable programme history | **Slice 2 implemented attributable programme events and revision supersession** |
| Programme amendments | schedule edits could mutate planning state | **Slice 2 creates a new DRAFT revision instead of editing approved programme history** |
| Risk-based planning | schedule has operational fields but no explainable surveillance priority model | pending deterministic signal/rule engine |
| Audit Planner | capable calendar/list/table and recurrence implementation exists | retain and expand; connect programme requirements and deterministic conflicts |
| Auditor availability | no complete Workforce/Rostering availability gate | pending Slice 4 |
| Auditor competence | no complete authoritative Training eligibility gate | pending Slice 4 |
| Auditor independence | not a complete deterministic assignment rule | pending Slice 4 |
| Notice lifecycle | notice/reminder fields exist | pending governed draft/review/generate/deliver/ack/revise workflow and configurable policy |
| Preparation workspace | execution pages exist | pending consolidated prior findings/CARs/DMS/source references/evidence requests |
| Checklist versioning | checklist capability exists | pending immutable template revision capture per audit |
| Audit lifecycle | legacy audit status remains too coarse for target lifecycle | pending progressive lifecycle strengthening without breaking existing records |
| Report governance | report workflow exists | pending revision/issued-history hardening |
| Closeout | closeout exists | pending explicit execution-close vs assurance-follow-up gates |
| Effectiveness | CAR workflow exists | pending expected outcome, measure, observation window, verification method and conclusion model |
| Recurrence | recurring schedule engine exists | retain; link recurrence requirements to programme rather than cloning completed history |
| Control Room audit signals | partial | pending due/overdue/conflicts/reports/CAR/effectiveness/deferral action queue |

## 7. Slice 2 — governed Audit Programme

Slice 2 introduces four Quality-owned relational tables.

### `quality_audit_programmes`

Fields include:

- `amo_id` — mandatory tenant owner;
- `programme_ref`;
- `programme_series`;
- `programme_year`;
- `revision_no`;
- `title`;
- `objectives`;
- `regulatory_basis`;
- `status`;
- `period_start` / `period_end`;
- `owner_user_id`;
- `supersedes_programme_id`;
- approval / activation / closure attribution and timestamps;
- created / updated attribution and timestamps.

Programme states:

```text
DRAFT
  ↓
UNDER_REVIEW
  ├──→ DRAFT
  └──→ APPROVED
          ↓
        ACTIVE
          ↓
        CLOSED
```

Approved or active revisions can also become `SUPERSEDED` through the controlled amendment path.

Terminal states:

```text
SUPERSEDED
CLOSED
```

### Amendment rule

Approved and active programme revisions are immutable through the programme edit API.

A controlled amendment creates:

```text
APPROVED/ACTIVE REVISION N
          |
          └── superseded by → DRAFT REVISION N+1
```

The previous approved revision is not marked `SUPERSEDED` until the replacement revision is itself approved. This preserves the currently approved programme while the amendment is being prepared/reviewed.

## 8. Slice 2 — Audit Universe

`quality_audit_universe_items` is the governed catalogue of auditable entities.

Supported entity classes currently include:

- department;
- facility;
- station;
- supplier;
- contractor;
- process;
- capability;
- approval rating;
- aircraft type;
- personnel group;
- other governed entity.

Each entry carries:

```text
source_owner_module
source_type
source_id
source_route
```

plus:

- risk classification;
- regulatory criticality;
- surveillance interval where applicable;
- mandatory-surveillance flag;
- active state;
- Quality notes.

The unique source identity is tenant-scoped:

```text
amo_id + source_owner_module + source_type + source_id
```

This prevents Quality from creating multiple copies of the same authoritative source record inside the Audit Universe.

## 9. Slice 2 — programme surveillance requirements

`quality_audit_programme_items` relates a programme revision to an Audit Universe item.

Supported audit types currently include:

- internal;
- departmental;
- technical;
- work-pack;
- supplier;
- contracted-function;
- facility;
- personnel;
- product;
- process;
- regulatory;
- special;
- reactive;
- follow-up.

Supported recurrence definitions currently include:

- one-time;
- monthly;
- quarterly;
- semi-annual;
- annual;
- custom interval;
- risk-triggered.

Requirement state:

```text
PLANNED | SCHEDULED | COMPLETED | DEFERRED | CANCELLED | FOLLOW_UP_REQUIRED
```

A deferral or cancellation requires an explicit reason through the programme API.

`prioritization_basis` is intentionally a structured evidence/rule container. It is **not** an opaque AI risk score. The deterministic risk/planning engine will populate explainable contributing factors in a later slice.

## 10. Slice 2 — immutable programme events

`quality_audit_programme_events` records human-attributed programme history.

Current event types include:

- created;
- updated;
- submitted for review;
- returned to draft;
- approved;
- activated;
- amendment created;
- superseded;
- closed;
- programme item added;
- programme item updated.

Each event carries:

- reason;
- before snapshot where relevant;
- after snapshot where relevant;
- actor;
- timestamp.

No programme-event update/delete API is exposed. Database-level append-only trigger hardening remains a later integrity improvement if required by the repository-wide event architecture.

## 11. Slice 2 API surface

Canonical APIs:

```text
GET    /api/maintenance/{amo_code}/quality/audit-programmes
POST   /api/maintenance/{amo_code}/quality/audit-programmes
GET    /api/maintenance/{amo_code}/quality/audit-programmes/{programme_id}
PATCH  /api/maintenance/{amo_code}/quality/audit-programmes/{programme_id}
POST   /api/maintenance/{amo_code}/quality/audit-programmes/{programme_id}/transitions
POST   /api/maintenance/{amo_code}/quality/audit-programmes/{programme_id}/amendments

GET    /api/maintenance/{amo_code}/quality/audit-programmes/universe/items
POST   /api/maintenance/{amo_code}/quality/audit-programmes/universe/items
PATCH  /api/maintenance/{amo_code}/quality/audit-programmes/universe/items/{item_id}

POST   /api/maintenance/{amo_code}/quality/audit-programmes/{programme_id}/items
PATCH  /api/maintenance/{amo_code}/quality/audit-programmes/{programme_id}/items/{item_id}
```

The legacy `/qms/` tenant alias is retained for compatibility.

Static Audit Programme routes are explicitly promoted ahead of the generic Quality catch-all so they cannot silently fall into the legacy register reader.

All list APIs are bounded.

## 12. Slice 2 frontend route ownership

```text
/maintenance/:amoCode/quality/audits/program
```

now owns the governed Audit Programme and Audit Universe workspace.

The existing authoritative schedule/planner remains:

```text
/maintenance/:amoCode/quality/audits/plan
/maintenance/:amoCode/quality/audits/schedule
```

The existing execution domain remains:

```text
/maintenance/:amoCode/quality/audits/register
/maintenance/:amoCode/quality/audits/:auditId/*
```

This separation is deliberate:

```text
PROGRAMME REQUIREMENT
        |
        v
AUDIT PLANNER / SCHEDULE
        |
        v
LIVE AUDIT RECORD / WAR ROOM
```

The programme does not directly manufacture a parallel live audit record.

## 13. Tenant isolation and data integrity

Migration:

```text
quality_260808_audit_programme
```

descends from:

```text
quality_260808_missions
```

All four Slice 2 tables:

- require non-null `amo_id`;
- use real tenant FKs;
- have tenant-oriented indexes;
- enable PostgreSQL RLS;
- force PostgreSQL RLS;
- use a tenant-isolation policy based on `app.tenant_id`.

The PostgreSQL Audit Programme probe verifies:

1. RLS enabled and forced;
2. tenant policy exists on every new table;
3. tenant A can create programme/universe/item/event records;
4. tenant B sees zero tenant-A rows;
5. tenant B cannot update or delete tenant-A programme data.

## 14. Slice 2 testing / CI contract

Dedicated tests added:

```text
backend/amodb/apps/quality/tests/test_audit_programme_contract.py
backend/amodb/apps/quality/tests/postgres_audit_programme_probe.py
frontend/tests/e2e/qms-audit-programme.spec.ts
```

Quality CI now has named checks for:

- Audit Programme backend contract;
- Audit Programme PostgreSQL migration/RLS;
- Audit Programme Playwright.

The browser contract verifies:

- governed programme route loads;
- programme reference/history is visible;
- Audit Universe source lineage remains visible;
- a programme can be created in DRAFT;
- review transition remains disabled until a reason is entered;
- reasoned transition history is visible after the state change.

At the time of this documentation update, Slice 2 is running through exact-head GitHub Actions and must not be called accepted until those jobs complete on the same branch head.

## 15. Audit Planner — next vertical slice

The next implementation slice extends the existing planner; it does not replace it.

Required additions:

### Programme handoff

A programme requirement must be able to create a scheduling **intent** in the authoritative Audit Planner while retaining:

- programme ID;
- programme-item ID;
- Audit Universe item;
- audit type;
- title;
- scope;
- criteria;
- mandatory-surveillance requirement;
- target window;
- explainable prioritization basis.

The Planner remains responsible for creating the actual scheduled/live audit record.

### Deterministic conflict engine

Conflicts will be classified as:

```text
BLOCKING
WARNING
```

Planned deterministic rules include:

- missing lead auditor;
- missing auditee where required;
- missing scope;
- missing criteria;
- lead auditor double-booked;
- audit-team member double-booked;
- Workforce/Rostering unavailability where authoritative data exists;
- auditor competence ineligibility where authoritative Training data exists;
- independence conflict;
- schedule outside programme period;
- mandatory surveillance past due;
- configured notice period insufficient;
- unrealistic overlapping surveillance of the same entity;
- location/facility constraints where authoritative data exists.

Mandatory regulatory surveillance is a hard constraint and will not be averaged away by a numerical risk score.

## 16. Planned remaining vertical slices

### Slice 3 — Audit Planner + conflict engine

- programme-to-planner handoff;
- deterministic conflict classes;
- controlled date/auditor changes;
- richer Year / Quarter / Month / Week / Agenda perspectives using bounded requests.

### Slice 4 — auditor availability / competence / independence

- Workforce/Rostering source references;
- Training/Competence source references;
- explicit independence declarations/rules;
- workload/capacity projection;
- no copied training or roster records.

### Slice 5 — notices + controlled rescheduling / deferral

- configurable tenant notice policy;
- draft/review/approval/generation/delivery/acknowledgement/revision;
- explicit exception path for emergency/unannounced audits;
- immutable before/after schedule history.

### Slice 6 — preparation + checklist versioning

- prior audit/findings/CAR context;
- DMS/regulatory links;
- evidence requests;
- opening-meeting preparation;
- immutable checklist template revision captured by audit.

### Slice 7 — Audit War Room enhancement

- execution progress;
- evidence requests;
- source-record viewer/deep links;
- quick structured finding creation;
- controlled autosave without auto-finalization.

### Slice 8 — reporting + execution closeout

- governed report revision lifecycle;
- execution-close gates;
- issued report immutability;
- CAR/follow-up obligations remain independently open.

### Slice 9 — follow-up + effectiveness engineering

- expected outcome;
- effectiveness measure;
- verification method;
- responsible reviewer;
- observation period;
- planned review date;
- source indicators;
- conclusion: EFFECTIVE / PARTIALLY_EFFECTIVE / INEFFECTIVE / INCONCLUSIVE;
- reopen/escalate/follow-up actions when ineffective.

### Slice 10 — People & Privileges

Training remains authoritative for training records. Quality will own internal privileges such as auditor, lead auditor, supplier auditor, technical auditor, CAR reviewer and effectiveness reviewer.

### Slice 11 — Assurance Cases + Investigation Studio

- evidence/decision-centred cases;
- 5 Whys;
- Ishikawa;
- causal factor analysis;
- barrier analysis;
- change analysis;
- human/organizational factors;
- explicit fact vs hypothesis vs causal conclusion.

### Slice 12 — Quality Intelligence

- audit completion vs programme;
- deferral rate;
- finding recurrence;
- CAR ageing/closure cycle;
- ineffective-action rate;
- supplier/department surveillance;
- auditor capacity;
- explainable derived indicators.

### Slice 13 — Regulatory Impact Graph + Approval Digital Twin

- requirement → approval/manual/procedure/form/training/role/checklist/evidence/mission/finding/action graph;
- supported / unsupported / stale / unresolved / blocked capability state;
- no unsupported binary compliance declaration.

### Slice 14 — controlled removal of obsolete surfaces

Only remove generic/legacy QMS surfaces once replacement behaviour is proven and deep links remain compatible.

## 17. UX rules

Audit planning and execution must behave like an operational planning application, not a register wrapped in cards.

Prefer:

- bounded dense tables;
- split panes;
- compact drawers;
- keyboard operation;
- stable URLs and deep links;
- saved filters/views;
- visible source lineage;
- clear blocking vs warning state;
- mobile/tablet layouts that preserve essential actions.

Avoid:

- KPI walls;
- fake percentages;
- giant empty hero sections;
- repeated headers;
- duplicate top-level navigation;
- uncontrolled modal stacks;
- browser-side loading of the entire Quality history for filtering.

## 18. Security and API rules

All new Quality APIs must:

- resolve tenant from the authenticated route context;
- set PostgreSQL tenant context;
- enforce server-side Quality permissions;
- return deterministic validation/conflict errors;
- use bounded pagination;
- avoid N+1 fan-out;
- keep date/calendar reads bounded;
- preserve actor attribution;
- use timezone-aware timestamps for events;
- never rely on frontend permission checks for security.

## 19. AI boundary

AI may:

- explain source evidence;
- help draft reports/findings/actions;
- surface trends;
- recommend what to inspect;
- suggest investigation methods;
- help navigate the portal.

AI may not independently:

- fabricate objective evidence;
- approve a programme;
- accept a root cause;
- grant a privilege;
- close a finding/CAR/audit;
- declare a capability compliant;
- override a mandatory surveillance requirement.

Named authorized humans remain accountable for controlled decisions.

## 20. Definition of done

PR #488 remains **DRAFT** until the complete required Quality scope is implemented and proven.

The six workspace routes rendering is not completion.

Audit Operations is complete only when programme, universe, risk planning, scheduling, eligibility, notices, preparation, versioned checklists, execution, findings, reporting, CAR handoff, follow-up, effectiveness, governed closeout, recurrence and programme-performance visibility are operational.

The overall Assurance Operating System is complete only when People/Privileges, Assurance Cases, Investigation Studio, Intelligence, Regulatory Impact and Approval Digital Twin are also operational and all impacted exact-head CI is green.

Until then:

```text
KEEP PR #488 DRAFT.
```
