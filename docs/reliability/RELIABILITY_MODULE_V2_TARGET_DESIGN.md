# Reliability Module V2 — Governing Target Design

**Status:** Approved implementation contract
**Source:** Reliability Module V2 target design supplied by the product owner on 2026-08-03
**Applies to:** Reliability, Tech Records, Planning, Production, Maintenance Execution, QMS, SMS, Procurement and AI-assisted workflows

## 1. Product objective

Reliability is not a report gallery. It is the portal's closed-loop continuing-airworthiness intelligence system:

> Operational and maintenance data → detection → engineering investigation → FRACAS → corrective action → approved programme/planning change → maintenance execution → technical-record update → effectiveness monitoring.

Software assists compliance; it does not replace approved manuals, competent persons, organisational responsibility, authority approval or retained evidence.

## 2. Non-negotiable regulatory model

The platform shall not combine EASA, FAA, ICAO and national requirements into one false universal workflow.

Each tenant may activate one or more controlled regulatory profiles:

- EASA CAMO
- EASA Part-145
- FAA Part 121 operator
- FAA Part 135 operator
- FAA Part 145 repair station
- ICAO baseline
- National authority overlay, including KCAA
- Bilateral or dual-release profile

The selected profile controls responsibility, approval gates, terminology, mandatory records, retention and authority interfaces.

The platform must distinguish:

| Context | System responsibility |
|---|---|
| Part-145 AMO / repair station | Supply maintenance findings, removals, shop reports, NFF outcomes, labour, material and technical recommendations |
| CAMO / operator | Own the reliability programme, thresholds, decisions, AMP changes and authority submissions |
| Contracted reliability provider | Analyse controlled data and propose action without assuming the CAMO/operator's approval authority |
| Competent authority | Receive controlled submissions and evidence as required by the applicable profile |

## 3. Module authority boundaries

| Module | Authoritative responsibility |
|---|---|
| Tech Records | Actual configuration, FH/FC, log entries, accomplishments, CRS/release evidence and history |
| Planning | Future requirements, forecasts, due calculations, work scope, material, tooling, manpower and readiness |
| Production | Visit/check execution control, allocation, handover, constraints, progress, inspection and recovery |
| Maintenance Execution | Task performance, measurements, findings, part changes, inspections and certification |
| Reliability | Trend detection, technical investigation, FRACAS, recommendations, programme effectiveness and verification |
| QMS | Process compliance, audits, nonconformities, CAR/CAPA, supplier quality and independent assurance |
| SMS | Hazards, safety occurrences, operational risk and safety-performance monitoring |

Reliability consumes authoritative records from the other modules. It must not require manual re-entry of defects, removals, usage or work-order results.

## 4. Data architecture

### 4.1 Controlled reliability programme

Create a versioned `ReliabilityProgram` aggregate containing:

- regulatory profile;
- aircraft, engine, APU, component and ATA scope;
- applicability basis;
- programme objectives;
- source systems and freshness requirements;
- metric catalogue;
- threshold and statistical-method versions;
- report and meeting cadence;
- approval and effective dates;
- CAMO/AMO contractual responsibility;
- authority acceptance/approval references; and
- superseded versions.

No formula or threshold shall operate outside an approved programme version.

### 4.2 Canonical occurrence

`ReliabilityEvent` becomes the canonical occurrence header with subtype records for:

- operational interruption;
- technical defect;
- deferred defect;
- component removal;
- shop finding;
- engine health observation;
- maintenance finding;
- inspection finding;
- supplier failure; and
- safety occurrence.

Every occurrence shall retain tenant, source organisation, immutable source ID, configuration snapshot, ATA/failure mode, operational impact, exposure, linked work evidence, data-quality state and correction/supersession history.

### 4.3 Pipeline controls

```text
Source record
  → transactional outbox
  → ingestion worker
  → immutable raw payload
  → validation and reconciliation
  → normalized occurrence
  → occurrence clustering
  → KPI fact generation
  → threshold/control evaluation
  → alert or case recommendation
```

Required controls:

- idempotency;
- safe reprocessing;
- dead-letter handling;
- source freshness;
- reconciliation and nil returns;
- raw-to-metric provenance;
- calculation versions;
- effective dates; and
- tenant-isolation regression tests.

High-volume EHM samples remain in object/time-series/columnar storage. PostgreSQL stores controlled summaries and references.

## 5. Statistical service

Support exposure-aware rate monitoring, confidence intervals, p/u/c charts, EWMA, CUSUM, slope/change-point detection, Pareto, Weibull/survival analysis, life bands, cohorts, seasonal baselines, small-fleet methods and before/after effectiveness tests.

Every calculation run retains programme/formula version, data cut-off, included/excluded evidence, exposure, baseline, method, parameters, result, uncertainty, triggered rules, reviewer and disposition.

### Small-fleet mode

- Never treat zero events as proof of good reliability.
- Display data sufficiency and uncertainty.
- Require engineering review before escalation.
- Compare rolling exposure rather than arbitrary months.
- Pool only genuinely comparable data under controlled consent.
- Never expose another tenant's identifiable data.

## 6. FRACAS lifecycle

```text
Detected
  → Triage
  → Accepted / Rejected / Merged
  → Containment
  → Investigation
  → Root Cause Review
  → Action Plan Approval
  → Implementation
  → Effectiveness Monitoring
  → Closed
  → Reopened when recurrence or failed effectiveness is detected
```

Each case includes linked occurrences, a precise failure definition, investigation plan, evidence, hypotheses, test results, causal factors, risk, approvals, action dependencies and decision history.

Actions may be containment, corrective, preventive, AMP change, modification, inspection campaign, troubleshooting instruction, supplier action, training, tooling/test-equipment change or data-quality correction.

Before implementation is accepted, the case must define baseline, expected improvement, target, minimum exposure, monitoring period, verifier and reopen condition. **Completed is not equivalent to effective.**

FRACAS and QMS CAR/CAPA remain separate governed objects. They may link and share evidence without losing their different ownership and approval chains.

## 7. Frontend route contract

```text
/maintenance/:amoCode/reliability
/maintenance/:amoCode/reliability/workbench
/maintenance/:amoCode/reliability/events
/maintenance/:amoCode/reliability/events/:eventId
/maintenance/:amoCode/reliability/alerts
/maintenance/:amoCode/reliability/alerts/:alertId
/maintenance/:amoCode/reliability/cases
/maintenance/:amoCode/reliability/cases/:caseId
/maintenance/:amoCode/reliability/fleet
/maintenance/:amoCode/reliability/systems/:ataChapter
/maintenance/:amoCode/reliability/components
/maintenance/:amoCode/reliability/components/:partNumber
/maintenance/:amoCode/reliability/engines
/maintenance/:amoCode/reliability/engines/:engineId
/maintenance/:amoCode/reliability/program
/maintenance/:amoCode/reliability/program/metrics
/maintenance/:amoCode/reliability/program/thresholds
/maintenance/:amoCode/reliability/program/data-sources
/maintenance/:amoCode/reliability/changes
/maintenance/:amoCode/reliability/changes/:proposalId
/maintenance/:amoCode/reliability/meetings
/maintenance/:amoCode/reliability/meetings/:meetingId
/maintenance/:amoCode/reliability/reports
/maintenance/:amoCode/reliability/data-quality
```

The workbench answers four questions:

1. What needs attention now?
2. What changed since the last review?
3. Which aircraft, systems or components are deteriorating?
4. Which actions or decisions are overdue?

Use a full-width operational layout. Avoid nested cards and decorative KPI walls. Tables require sticky headers, compact density, saved views, column controls and direct evidence drilldown.

## 8. Core workflows

### Morning review

Workbench → prioritised item → evidence timeline → confirm/dismiss/merge → controlled case → assigned investigator → audited decision.

### Alert disposition

Alert → formula/source/baseline/uncertainty → monitor, correct data, open/link FRACAS, engineering review or QMS/SMS escalation → documented technical disposition.

Acknowledgement does not resolve an alert.

### Component investigation

Part-number cohort → serials/installations/removals/exposure/vendor/batch/shop/NFF → occurrence cluster → FRACAS → supplier/procurement/QMS/warranty actions → automatic post-action monitoring.

### Programme amendment

Case evidence → change proposal → planning impact simulation → CAMO/engineering/authority approvals → Planning implementation → Production/Maintenance execution → Tech Records validation → effectiveness window.

### Reliability meeting

Controlled data cut → generated agenda → decisions/rationale/dissent/actions → approval → controlled minutes/report → follow-up.

## 9. AI governance

AI appears as contextual engineering assistance, not the portal's primary interface.

Allowed assistance includes related-defect search, ATA/failure-mode suggestion, history summary, investigation-plan drafting, missing-evidence detection, alert explanation, meeting/report drafting and planning-impact explanation.

AI must never autonomously approve or amend an AMP, change an interval, defer a defect, close FRACAS, verify effectiveness, approve technical disposition, sign CRS, alter source records or submit to an authority.

Retain model/prompt version, retrieved sources, data cut-off, uncertainty, user acceptance/edit/rejection and final human approval. Obsolete or inapplicable technical references must be blocked.

## 10. Differentiators

- Reliability evidence graph from KPI to raw occurrence, maintenance evidence, supplier, action and measured effect.
- Decision-to-execution automation into Planning, Production, Maintenance, Procurement, Training, QMS and SMS.
- Small-fleet intelligence with visible uncertainty.
- “No data, no green” data-health status.
- Reliability meeting operating system.
- Programme-change impact simulation.

## 11. Delivery order

### Foundation blockers

1. Tenant isolation.
2. One authoritative effective tenant context.
3. Isolation regression tests.
4. Capability-based permissions.
5. Versioned programme, taxonomy and KPI definitions.
6. Filtered/paginated/idempotent APIs.
7. Controlled data dictionary.

### Operational reliability

Canonical occurrence, interruptions/MEL, data quality, workbench, detail routes, FRACAS state machine, component and engine investigation.

### Analytics and governance

Scheduled KPI engine, statistical evidence, meetings, report packs, threshold review and programme changes.

### Closed-loop integration

Planning implementation, Production work scope, Maintenance execution, Tech Records validation, supplier/QMS linkage and automatic effectiveness monitoring.

### AI and collaboration

Semantic clustering, evidence-grounded assistant, controlled drafting, planning impact, small-fleet analytics and consent-based benchmarking.

## 12. Definition of done

- Every metric drills into source evidence.
- Every significant alert receives a documented disposition.
- Every recurrence can enter controlled FRACAS.
- Every approved action creates work in the correct module.
- Every programme change flows through Planning and execution.
- Every accomplishment updates Tech Records.
- Every action has measurable effectiveness criteria.
- Every regulatory decision retains authority, rationale, evidence, approval and effective date.
- No tenant can influence or view another tenant's analytics.
- AI cannot bypass engineering, CAMO, quality or certification authority.

## 13. Implementation discipline

This design is cumulative. Reliability changes must preserve the canonical tenant shell, route boundary, navigation manifest, shared theme tokens and global layout delivered by the concurrent navigation work. Reliability-specific CSS must be scoped and must not reintroduce global page, button, table or typography overrides.
