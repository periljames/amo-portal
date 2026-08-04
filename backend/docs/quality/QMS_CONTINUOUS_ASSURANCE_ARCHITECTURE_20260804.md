# QMS Continuous Assurance Architecture

**Date:** 2026-08-04  
**Status:** Implemented foundation on `agent/qms-accessibility-live-workflow`  
**Primary UI:** `/maintenance/{amoCode}/quality`

## 1. Product objective

The Quality module must remain a complete aviation QMS while becoming materially more useful than a collection of registers. The operating model is **continuous assurance**:

- obligations are represented as durable controls;
- controls retain ownership, criticality, test cadence and expected proof;
- evidence is linked to controls across module boundaries;
- readiness is calculated from visible operational pressure, not declared as compliance;
- recommendations remain advisory until a named person decides them;
- audits, findings, CAR/CAPA, documents, competence and supplier records remain the authoritative regulated records.

The architecture deliberately avoids converting the portal into an unrestricted chat interface. Assistance is embedded in the workflow and is subject to human approval.

## 2. Enterprise baseline retained

The canonical QMS route registry and existing specialist pages continue to provide the expected enterprise feature set:

| Domain | Existing operational surface |
|---|---|
| Personal work | Assigned work, due soon, overdue and approvals inboxes |
| Audit management | Programme, planner, schedules, checklists, execution workspace, findings, evidence, reports and closeout |
| Corrective action | CAR register, containment, root cause, actions, response, Quality review, effectiveness and closure |
| Document control | Library, drafting, approvals, controlled distribution, revisions, superseded records and archive |
| Risk and opportunity | Registers, assessment, treatment, monitoring and heat-map views |
| Change control | Requests, assessment, implementation, verification and closure |
| Supplier quality | Supplier register, approvals, evaluations, audits and monitoring |
| Equipment and calibration | Equipment register, due/overdue calibration, certificates and serviceability |
| Training and competence | People, courses, requirements, matrix, expiry, scheduling, certificates and reports |
| Management review | Agenda, inputs, actions, minutes and outputs |
| Evidence and reporting | Evidence vault, audit packs, immutable archive, dashboards, trends, exports and scheduled reports |
| External interfaces | Authority, customer, occurrence and feedback records |

The continuous-assurance layer does not replace these modules. It connects them.

## 3. New differentiating capabilities

### 3.1 Control Twin

`quality_assurance_controls` represents a continuing obligation rather than a one-time checklist question.

Each control contains:

- tenant and control code;
- title and operating description;
- framework and clause reference;
- process area;
- accountable owner;
- criticality;
- active/draft/retired state;
- test frequency;
- evidence expectation;
- previous test and next test due date.

A control can be assessed in many audits without losing its identity between audit events.

### 3.2 Evidence Graph

`quality_assurance_evidence_links` creates typed, tenant-scoped relationships between a control and authoritative portal records.

Supported source categories are intentionally extensible and include:

- controlled documents;
- audits and checklists;
- findings;
- CAR/CAPA records;
- training and competence records;
- supplier records;
- equipment and calibration records;
- reports and other governed evidence.

Relationships may describe evidence, implementation, testing, remediation or qualification. Evidence also records verification state and validity date. This enables ageing evidence and unsupported controls to be found without waiting for the next audit.

### 3.3 Transparent readiness model

The Control Centre calculates operational readiness from six visible dimensions:

1. audit programme adherence;
2. CAPA discipline;
3. finding control;
4. document currency;
5. competence evidence;
6. continuous-control verification.

The model is deterministic and exposes its dimensions and weighting. It is explicitly labelled as an operational indicator, **not a regulatory compliance declaration**.

The score must never be used to auto-close, auto-approve or auto-certify a regulated record.

### 3.4 Assurance workload forecast

The 30-day forecast combines:

- audit schedule commitments;
- CAR due dates;
- control test dates.

This gives the Quality Manager an early workload signal before overdue conditions occur.

### 3.5 Human-governed Quality Intelligence

`quality_intelligence_reviews` stores explainable recommendations with:

- insight type;
- rationale;
- recommendation;
- risk level;
- source fingerprint;
- supporting payload;
- origin (`RULE_ENGINE`, `HUMAN`, or a future governed AI service);
- human decision, decision maker, note and timestamp.

An intelligence item cannot directly modify an audit, finding, CAR, controlled document, training record or control. A named authorised user must accept, dismiss or implement it through the normal governed workflow.

### 3.6 Embedded accessibility and live operations

The shared portal layer now includes:

- account-backed Standard, Large and Extra Large text settings;
- larger operational labels and targets;
- persistent QMS context navigation;
- automatic active-query revalidation after navigation, reconnection, focus and mutation-style actions;
- direct audit scheduling entry;
- reduced duplicate headers.

## 4. Information architecture

The QMS root is presented as a **Quality Control Centre** with four focused views:

### Readiness

- readiness score and six dimensions;
- immediate action lane;
- 30-day workload forecast;
- evidence-based management-review briefing;
- links to the Control Twin, Evidence Graph and Intelligence Review.

### Control library

- durable control register;
- framework/clause and process ownership;
- criticality and due state;
- evidence verification count;
- governed control creation;
- evidence-linking workflow.

### Evidence graph

- control-to-evidence relationships;
- evidence state and validity;
- unsupported-control count;
- cross-module traceability.

### Intelligence review

- visible guardrails;
- explainable recommendation queue;
- source fingerprint and origin;
- Quality-management decision controls;
- read-only access for inspectors/auditors.

The existing top context bar remains the primary cross-module navigation for My Work, Calendar, Audits, Findings, CAR/CAPA and Reports.

## 5. Authorisation model

### View access

Users with `qms.dashboard.view` can view readiness, controls and recommendations. Evidence graph access also requires `qms.evidence.view`.

### Management access

Creating or updating controls, linking evidence, rebuilding recommendations and deciding recommendations requires `qms.settings.manage`.

The frontend mirrors this distinction, but backend permission checks remain authoritative.

## 6. Tenant isolation

All three new tables contain mandatory `amo_id` foreign keys.

PostgreSQL deployments additionally enforce:

- row-level security;
- forced row-level security;
- `app.tenant_id` read and write policies.

Every endpoint also applies tenant predicates and sets the PostgreSQL tenant context. Application filtering and RLS are intentionally layered rather than treated as alternatives.

## 7. Data integrity rules

- Control codes are unique per tenant.
- Evidence relationships are unique by control, source, source identifier and relationship.
- Intelligence source fingerprints are unique per tenant.
- Enumerated status and risk fields are protected by database check constraints.
- Intelligence decisions retain the deciding user and time.
- Evidence verification retains verifier and verification time.
- No readiness or intelligence operation writes to regulated source records.

## 8. API surface

Canonical prefix:

```text
/api/maintenance/{amo_code}/quality/excellence
```

Compatibility prefix:

```text
/api/maintenance/{amo_code}/qms/excellence
```

Endpoints:

```text
GET    /overview
GET    /controls
POST   /controls
PATCH  /controls/{control_id}
POST   /controls/{control_id}/evidence
GET    /evidence-graph
GET    /insights
POST   /insights
POST   /insights/rebuild
PATCH  /insights/{insight_id}
```

Static excellence routes are explicitly placed before the canonical QMS catch-all route.

## 9. Deployment

Apply all repository heads:

```bash
alembic -c backend/amodb/alembic.ini upgrade heads
```

Relevant new revisions:

```text
accounts_260804_portal_prefs
quality_260804_assurance_hub
quality_260804_assurance_rls
```

The bounded Quality service enforces repository-head alignment at startup unless strict schema validation is explicitly disabled for a test environment.

## 10. Validation contract

The Quality CI workflow now validates:

- Alembic revision chain and revision-length limits;
- Python compilation;
- SQLAlchemy mapper configuration;
- portal-preference contracts;
- assurance route existence and route precedence;
- shared metadata registration;
- readiness score bounds and pressure sensitivity;
- advisory recommendation fingerprints;
- frontend Quality regressions;
- TypeScript production build;
- focused Quality linting.

Playwright specifications additionally cover:

- Control Centre rendering;
- readiness visibility;
- control creation access;
- evidence-link workflow;
- inspector/auditor read-only intelligence behaviour;
- text-scale persistence and QMS live refresh.

## 11. Non-negotiable governance rules

1. An operational score is never presented as proof of compliance.
2. A recommendation never mutates a regulated record directly.
3. Audit dates are not silently moved to hide programme drift.
4. Evidence marked verified must identify the verifier and verification time.
5. Tenant isolation is enforced in both queries and PostgreSQL RLS.
6. Human decisions remain attributable.
7. Existing specialist registers remain the source of truth.
8. New intelligence features must degrade safely when a source is unavailable and disclose incomplete inputs.
