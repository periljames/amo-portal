# QMS Continuous Assurance Architecture

**Date:** 2026-08-04  
**Status:** Final integrated implementation on `agent/qms-accessibility-live-workflow`  
**Primary UI:** `/maintenance/{amoCode}/quality`

## 1. Product objective

The Quality module remains a complete aviation QMS, but the root experience is no longer a passive overview or a group of disconnected registers. It is a **continuous-assurance control centre** that connects regulated operational records without treating an aggregate score as proof of compliance.

The operating model is:

- obligations become durable, versioned controls;
- controls retain ownership, criticality, approval state, test method and cadence;
- evidence is selected from authoritative tenant records rather than entered as an unchecked identifier;
- source changes emit tenant-scoped assurance events and refresh linked evidence provenance;
- operating-effectiveness tests remain separate, attributable records;
- readiness is calculated from visible cross-module pressure;
- recommendations remain advisory until a named authorised person records a decision;
- audits, findings, CAR/CAPA, documents, training, suppliers, calibration, risks, changes, management review and external commitments remain the regulated sources of truth.

The architecture embeds assistance into normal work. It does not convert the portal into an unrestricted chat interface and does not permit AI or rule outputs to alter regulated records automatically.

## 2. Enterprise QMS baseline retained

The existing specialist workflows continue to provide the enterprise baseline:

| Domain | Authoritative operational surface |
|---|---|
| Personal work | Assigned work, due soon, overdue and approval queues |
| Audit management | Programme, planning, schedules, notices, scopes, checklists, fieldwork, findings, evidence, reporting and closeout |
| Corrective action | CAR register, containment, root cause, actions, Quality review, effectiveness and closure |
| Document control | Library, drafting, approvals, controlled distribution, revision, supersession and archive |
| Risk and opportunity | Registers, assessment, controls, treatments, actions and monitoring |
| Change control | Request, impact review, risk assessment, approval, implementation, verification and closure |
| Supplier quality | Supplier register, approvals, scopes, evaluations, audits, findings and performance monitoring |
| Equipment and calibration | Equipment register, calibration history, certificates, status changes and out-of-tolerance events |
| Training and competence | Personnel, courses, requirements, competence matrix, expiry, scheduling and certificates |
| Management review | Inputs, agenda, minutes, decisions, assigned actions, approvals and outputs |
| Evidence and reporting | Evidence vault, audit packs, archives, dashboards, exports and scheduled reports |
| External interfaces | Authority findings, correspondence, customer complaints, feedback and external commitments |

The continuous-assurance layer connects these domains. It does not duplicate or replace their records.

## 3. Direct frontend architecture

The QMS root is a direct route component:

```text
router.tsx
  -> QmsOverviewPage
      -> DepartmentLayout
          -> QualityExcellenceCockpit
```

`QmsOverviewPage` now owns the root route. The previous enhancement-host overlay has been removed. Therefore:

- the old dashboard is not rendered underneath the Control Centre;
- the old dashboard does not issue a hidden initial data request;
- the page retains the normal tenant department shell;
- shared text scaling, contextual QMS navigation, live refresh and checklist/audit integrity enhancements remain mounted through `QualityEnhancementsHost`;
- the Control Centre remains independently code-split at the QMS route boundary.

## 4. Quality Control Centre information architecture

### 4.1 Readiness

The Readiness view provides:

- transparent operational readiness and band;
- ten visible dimensions with weights;
- immediate action lane ranked by severity;
- 30-day workload forecast;
- cross-module health indicators;
- decision-ready management-review briefing;
- direct navigation to the authoritative workflow behind each signal;
- source warnings where a required table or supported field is unavailable.

The ten dimensions are:

1. audit programme;
2. CAPA discipline;
3. finding control;
4. document currency;
5. competence;
6. supplier and calibration assurance;
7. risk and change control;
8. continuous controls;
9. external commitments;
10. management-review action discipline.

The calculation is deterministic and labelled as an operational indicator, **not a regulatory compliance declaration**.

### 4.2 Versioned control library

`quality_assurance_controls` represents a continuing obligation rather than a one-time checklist item.

Each control stores:

- tenant and unique control code;
- version number;
- title and description;
- control objective;
- framework and clause reference;
- process area and owner;
- criticality;
- lifecycle state;
- approval state and approving user/time;
- test method and test frequency;
- expected evidence;
- last test and next test due date;
- creator and updater attribution.

Material changes to an approved control create a new version state and return it to draft approval status. Controls can be submitted, approved, rejected or retired without destroying their historical identity.

### 4.3 Operating-effectiveness testing

`quality_control_tests` is an immutable test history for controls.

A test records:

- control and tenant;
- result (`PASS`, `FAIL`, `PARTIAL`, `NOT_TESTED`);
- tester and test time;
- method and notes;
- evidence summary;
- next test due date.

A failed or partial test produces an advisory intelligence item. It does not auto-create, close or modify a CAR. Quality personnel must follow the governed corrective-action workflow.

### 4.4 Validated evidence graph

`quality_assurance_evidence_links` creates typed relationships between controls and authoritative portal records.

A user does not enter an unchecked source identifier. The evidence workflow:

1. selects a supported source category;
2. searches the authoritative tenant table;
3. selects a resolved record;
4. validates tenant ownership and record availability;
5. captures a label, route, snapshot and source table;
6. records relationship semantics and verification state;
7. stores validity, verification and synchronization information.

Supported source categories include:

- audits and audit schedules;
- findings;
- CAR/CAPA;
- controlled documents;
- training and competence;
- suppliers and supplier approvals;
- equipment, calibration records and certificates;
- risks;
- change controls;
- management-review actions;
- regulator findings;
- external commitments;
- governed reports.

Relationships include `EVIDENCES`, `TESTS`, `IMPLEMENTS`, `REMEDIATES` and `QUALIFIES`.

A deleted, soft-deleted, cancelled, rejected, obsolete, void or superseded source invalidates its evidence relationship. Restored evidence returns to a linked state and requires a new human verification rather than silently regaining verified status.

### 4.5 Assurance event outbox

`quality_assurance_events` receives database-level lifecycle events from authoritative QMS tables.

PostgreSQL triggers capture:

- insert, update and delete event type;
- source table, type and identifier;
- previous and current snapshots;
- changed fields;
- valid actor when one can be resolved;
- correlation identifier when supplied;
- processing state and time.

The trigger derives tenant context from the authoritative row before writing to forced-RLS assurance tables. This allows normal API requests, trusted imports and scheduled jobs to emit events safely. Free-form import principals are not inserted into the user foreign key.

The trigger immediately refreshes matching evidence snapshots and invalidation state. The reconciliation endpoint additionally:

- resolves each relationship against the current authoritative source;
- recalculates validity and source route;
- marks unavailable sources rejected;
- returns restored sources to linked status pending verification;
- marks processed outbox events complete.

Date ageing is also evaluated in readiness queries, so expired evidence does not continue to contribute verified-control credit while awaiting a manual reconciliation run.

### 4.6 Human-governed Quality Intelligence

`quality_intelligence_reviews` stores explainable recommendations with:

- insight type;
- rationale;
- recommendation;
- risk level;
- source fingerprint;
- supporting payload;
- origin (`RULE_ENGINE`, `HUMAN`, or a future governed AI service);
- human decision, decision maker, note and timestamp.

The current engine is deterministic. It detects defined operational conditions such as overdue CARs, programme drift, expired competence, missing control coverage, due control tests and failed operating-effectiveness tests.

No intelligence item can directly modify an audit, finding, CAR, controlled document, training record or control. A named authorised user must accept, dismiss or implement it through normal governed workflows.

## 5. Schema-aware cross-module aggregation

Canonical QMS tables share a base contract that includes `amo_id`, `status`, `due_date`, `payload`, attribution and soft deletion. Some specialist migrations add richer fields such as `next_due_date`, `valid_until`, `closed_at` or direct risk columns.

The metric layer inspects the live PostgreSQL schema and chooses the strongest available supported field. Examples:

- audit due: `next_due_date`, otherwise `due_date`;
- supplier approval: specific validity field, otherwise canonical `due_date`;
- calibration: `next_due_date`, `due_date` or `valid_until`;
- risk level: direct severity field, otherwise governed values inside `payload`;
- finding state: `closed_at`, otherwise canonical `status`.

A missing table or unsupported shape produces an explicit source warning. It is not silently interpreted as zero exposure.

## 6. Authorisation model

### Read access

- `qms.dashboard.view`: readiness, controls and intelligence queue;
- `qms.evidence.view`: evidence catalogue, source search, graph and event stream;
- `qms.management_review.view`: management-review briefing.

Quality Inspectors and Auditors receive read access to supplier, equipment, risk, change, competence and management-review assurance inputs. They do not receive control management, evidence verification, recommendation decision or settings permissions.

### Management access

`qms.settings.manage` is required to:

- create or update controls;
- submit or decide control approval;
- link or decide evidence;
- record control tests;
- reconcile evidence and events;
- rebuild or decide intelligence recommendations.

Frontend visibility mirrors these permissions, while backend checks remain authoritative.

## 7. Tenant isolation and integrity

All assurance tables contain mandatory `amo_id` foreign keys.

PostgreSQL additionally enforces:

- row-level security;
- forced row-level security;
- tenant-scoped read and write policies using `app.tenant_id`;
- tenant predicates in every API query;
- source resolution against the same tenant;
- cross-tenant write rejection.

Integrity rules include:

- control codes unique per tenant;
- evidence edges unique by control, source type, source ID and relationship;
- intelligence fingerprints unique per tenant;
- constrained lifecycle, evidence, test, insight and risk values;
- immutable control-test history;
- attributed control approval and intelligence decisions;
- verifier and time retained for verified evidence;
- no readiness, event or intelligence operation writes to a regulated source record.

## 8. API surface

Canonical prefix:

```text
/api/maintenance/{amo_code}/quality/excellence
```

Primary endpoints:

```text
GET    /overview/full
GET    /source-catalog
GET    /source-search
GET    /controls
POST   /controls
PATCH  /controls/{control_id}
POST   /controls/{control_id}/approval
GET    /controls/{control_id}/tests
POST   /controls/{control_id}/tests
POST   /controls/{control_id}/evidence
PATCH  /evidence/{evidence_id}
GET    /evidence-graph
POST   /reconcile
GET    /events
GET    /management-review-pack
GET    /insights
POST   /insights
POST   /insights/rebuild
PATCH  /insights/{insight_id}
```

Static assurance routes are de-duplicated by path and method, with the latest stricter handler promoted ahead of the generic canonical QMS catch-all.

## 9. Frontend UX contract

The direct Control Centre provides:

- full-width, responsive desktop, large-display, tablet and mobile layouts;
- fluid typography and user-controlled text scaling;
- minimum operational target sizes and visible keyboard focus;
- four stable views rather than nested card dashboards;
- compact action lanes with direct source navigation;
- searchable, filterable control register;
- focused side drawers for control, evidence and test workflows;
- authoritative source search rather than free-form evidence IDs;
- visible approval, evidence, due and test states;
- event provenance and source synchronization time;
- read-only presentation for auditors and inspectors;
- source warnings without presenting incomplete inputs as a clean result;
- responsive tables that collapse into readable record blocks on smaller screens.

The existing PDF checklist editor remains lazy-loaded only when the checklist route is active.

## 10. Migrations

Apply all repository heads:

```bash
alembic -c backend/amodb/alembic.ini upgrade heads
```

Revision chain:

```text
accounts_20260803_auth_session
  -> accounts_260804_portal_prefs
  -> quality_260804_assurance_hub
  -> quality_260804_assurance_rls
  -> quality_260804_assurance_wiring
  -> quality_260804_trigger_fix
```

## 11. Validation contract

Quality CI validates:

### Backend

- migration chain and revision-length limits;
- Python compilation;
- SQLAlchemy mapper registration;
- canonical and compatibility route mounts;
- exact route override and catch-all precedence;
- enterprise source registry coverage;
- schema-aware metric route precedence;
- bounded and pressure-sensitive readiness;
- inspector/auditor read-only permission alignment;
- PostgreSQL migration execution;
- forced RLS and tenant policies;
- non-superuser same-tenant writes;
- cross-tenant read and write rejection;
- trigger installation;
- actor validation;
- event emission without pre-set request context;
- linked-evidence snapshot propagation.

### Frontend

- focused unit regressions;
- TypeScript production build;
- focused Quality linting;
- Chromium installation and production preview;
- direct QMS root rendering;
- absence of the overlay activation state;
- cross-module readiness indicators;
- authoritative evidence source selection and linking;
- control approval and operating-effectiveness testing;
- auditor read-only intelligence;
- user text-scale persistence;
- contextual QMS navigation;
- explicit refresh-driven data revalidation.

## 12. Non-negotiable governance rules

1. Operational readiness is never presented as proof of compliance.
2. Recommendations never mutate regulated records directly.
3. Audit dates are not silently moved to hide programme drift.
4. Verified evidence identifies its source, verifier and verification time.
5. Evidence must resolve to an authoritative record in the same tenant.
6. Tenant isolation is enforced by both application predicates and PostgreSQL RLS.
7. Human approvals and decisions remain attributable.
8. Existing specialist registers remain the source of truth.
9. Missing sources are disclosed and never treated as proof of no exposure.
10. A restored source does not silently regain verified evidence status.
11. Failed control tests require governed human follow-up.
12. Future AI services must write only advisory intelligence records unless a separate approved workflow explicitly authorises another action.
