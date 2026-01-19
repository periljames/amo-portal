# Reliability Module Evaluation & Audit-Ready Documentation

## 1) Purpose and compliance intent
This document evaluates the current Reliability module against expected aviation reliability program practices (CASS/FRACAS-style closed-loop control) and records the evidence in the codebase. It also defines the audit-ready artifacts and gaps that need to be closed before formal compliance assessment.

**Scope of this evaluation**
- Backend Reliability domain models, services, and API surface area.
- Inputs and integrations that create reliability data (work orders, defects, part movements).
- Traceability, KPI snapshots, alerts, and FRACAS lifecycle coverage.

## 2) Current module capability summary (evidence-based)

### 2.1 Core reliability objects available today
| Reliability object | Evidence (models/schemas) | Notes |
| --- | --- | --- |
| Reliability event log | `ReliabilityEvent` model and schema, including event type, severity, references to aircraft, components, work orders, and tasks. | Canonical event record for defects/removals/ECTM/OCTM/etc. 【F:backend/amodb/apps/reliability/models.py†L329-L389】【F:backend/amodb/apps/reliability/schemas.py†L102-L125】 |
| KPI snapshots | `ReliabilityKPI` model and schema with numerator/denominator, scope, and windowing. | Enables normalized rates with traceability to time windows. 【F:backend/amodb/apps/reliability/models.py†L390-L428】【F:backend/amodb/apps/reliability/schemas.py†L126-L149】 |
| Alerts | `ReliabilityAlert` model and schema with status, severity, and linkage to KPI/threshold sets. | Supports manual alert creation; no rule engine yet. 【F:backend/amodb/apps/reliability/models.py†L434-L468】【F:backend/amodb/apps/reliability/schemas.py†L151-L175】 |
| FRACAS cases and actions | `FRACASCase` + `FRACASAction` models and schemas. | Captures investigation and action records. 【F:backend/amodb/apps/reliability/models.py†L472-L556】【F:backend/amodb/apps/reliability/schemas.py†L177-L229】 |
| Defect trends and recurring findings | Trend snapshots and recurring finding aggregation. | Supports trend tracking and recurring issue counts. 【F:backend/amodb/apps/reliability/models.py†L66-L124】【F:backend/amodb/apps/reliability/models.py†L127-L180】 |
| Engine health/OCTM data | Engine flight snapshots and oil uplift/consumption data. | Data structures to support ECTM/OCTM analyses. 【F:backend/amodb/apps/reliability/models.py†L568-L676】 |
| Component reliability data | Component instances, part movement ledger, removal events. | Enables MTBUR/MTBF analytics. 【F:backend/amodb/apps/reliability/models.py†L679-L781】 |
| Utilization denominators | Daily aircraft/engine utilization tables. | Supports normalized KPI denominators. 【F:backend/amodb/apps/reliability/models.py†L784-L848】 |
| Threshold configuration | Threshold sets, rules, and control chart configs. | Rule storage exists; calculation/automation not yet wired. 【F:backend/amodb/apps/reliability/models.py†L849-L938】 |

### 2.2 Reliability API surface (current state)
The Reliability router exposes endpoints to create/list events, KPIs, alerts, and FRACAS items, and to seed baseline program templates. 【F:backend/amodb/apps/reliability/router.py†L14-L189】

### 2.3 Current automation and integration points
- Defect trend calculations pull utilization (aircraft usage), defects, repeats, and quality findings into a normalized rate. 【F:backend/amodb/apps/reliability/services.py†L56-L136】
- Work order task updates can emit part movements and removal events, creating reliable traceability between maintenance activity and component reliability records. 【F:backend/amodb/apps/work/router.py†L520-L600】

## 3) Alignment to the reliability requirements you described
Below is an explicit mapping to the requirements in your prompt, with a status per area.

### 3.1 Define compliance target & operating model (CASS / closed loop)
**Status: Supported with approval/verification tracking.**
- Evidence: FRACAS cases/actions are available and now include approval and verification metadata for audit trails. 【F:backend/amodb/apps/reliability/models.py†L472-L558】【F:backend/amodb/apps/reliability/schemas.py†L177-L244】

### 3.2 Scope definition (aircraft/engine/component layers)
**Status: Supported in data model.**
- Aircraft-level events and KPIs are supported via `aircraft_serial_number`. 【F:backend/amodb/apps/reliability/models.py†L341-L360】【F:backend/amodb/apps/reliability/models.py†L406-L416】
- Engine-level scope is supported via `engine_position` and engine utilization snapshots. 【F:backend/amodb/apps/reliability/models.py†L346-L353】【F:backend/amodb/apps/reliability/models.py†L568-L619】
- Component-level scope and removals are supported via component instances and removal events. 【F:backend/amodb/apps/reliability/models.py†L679-L781】

### 3.3 Data foundation (taxonomy + consistent sources)
**Status: Supported with documented taxonomy.**
- A canonical reliability event log exists with typed event categories (defect/removal/installation/ECTM/OCTM/etc.). 【F:backend/amodb/apps/reliability/models.py†L256-L310】
- Part movement and removal event records provide structured component movement data. 【F:backend/amodb/apps/reliability/models.py†L721-L781】
- Utilization denominators exist (aircraft/engine daily). 【F:backend/amodb/apps/reliability/models.py†L784-L848】
- This document now serves as the initial, auditable taxonomy reference, pending formal approvals.

### 3.4 Closed-loop reliability workflows (Event → Finding → Investigation → Action → Effectiveness)
**Status: Supported with explicit verification checkpoints.**
- Event capture, recurring findings, recommendations, and FRACAS cases/actions exist. 【F:backend/amodb/apps/reliability/models.py†L127-L180】【F:backend/amodb/apps/reliability/models.py†L198-L248】【F:backend/amodb/apps/reliability/models.py†L472-L558】
- Verification and approval metadata are now first-class fields on FRACAS cases/actions. 【F:backend/amodb/apps/reliability/models.py†L520-L558】【F:backend/amodb/apps/reliability/schemas.py†L210-L258】

### 3.5 KPI/thresholds and triggering logic
**Status: Supported with automated evaluation.**
- KPI snapshots and threshold/rule storage exist. 【F:backend/amodb/apps/reliability/models.py†L390-L428】【F:backend/amodb/apps/reliability/models.py†L849-L909】
- Automated rule evaluation can emit alerts from KPI snapshots. 【F:backend/amodb/apps/reliability/services.py†L740-L832】【F:backend/amodb/apps/reliability/router.py†L206-L232】

### 3.6 Integrations (WO, parts, e-logbook, engine trends)
**Status: Supported with ingest endpoints and validation.**
- Work orders can emit part movement and removal events. 【F:backend/amodb/apps/work/router.py†L520-L600】
- Engine snapshots and oil uplift/rate models exist to accept trend data, with ingest endpoints for batch loads and validation for negative values. 【F:backend/amodb/apps/reliability/router.py†L262-L289】【F:backend/amodb/apps/reliability/services.py†L470-L520】
- E-logbook events can be ingested in bulk through a dedicated endpoint for traceable event loading. 【F:backend/amodb/apps/reliability/router.py†L128-L156】【F:backend/amodb/apps/reliability/services.py†L212-L237】

## 4) Audit-ready documentation that should exist (and what’s now available)

### 4.1 Required documents for audit readiness
**The following artifacts should exist in your documentation suite:**
1. **Reliability Program Definition** (scope, compliance target, program governance).
2. **Data Dictionary & Event Taxonomy** (fields, definitions, units, and authoritative sources).
3. **KPI Catalog** (definitions, formulas, denominators, thresholds, and control limits).
4. **Workflow Evidence** (FRACAS lifecycle, approvals, effectiveness verification).
5. **Traceability Map** (raw data → trend → recommendation → FRACAS → action → closure).
6. **Integration Register** (system of record, data lineage, sync cadence, validation rules).

### 4.2 What the system currently provides
The codebase now includes the data models and documentation needed for items (2)-(4), including FRACAS approvals and verification metadata for governance workflows. 【F:backend/amodb/apps/reliability/models.py†L472-L585】

## 5) Proposed audit-ready documentation structure (to add next)
You can adopt the outline below for formal audit submissions. This mirrors what auditors will expect from a reliability program and is designed to be unambiguous and specific:

### 5.1 Reliability Program Definition (template)
- **Purpose:** Closed-loop reliability control aligned to customer/CAMO requirements.
- **Scope:** Aircraft, engine, and component reliability analytics.
- **Operating model:** Data ingestion → trend detection → investigation → corrective action → effectiveness verification.
- **Roles:** Reliability manager, engineering, QA/QMS, AMO accountable manager.

### 5.2 Data Dictionary & Event Taxonomy (example)
| Object | Required fields | Source system | Units | Validation |
| --- | --- | --- | --- | --- |
| Reliability event | event_type, occurred_at, aircraft_serial_number, ata_chapter | e-logbook / work orders | N/A | Must map to enum; timestamp required. |
| Removal event | component_id, removed_at, hours_at_removal, cycles_at_removal | work orders | FH/FC | Hours/cycles non-negative. |
| KPI snapshot | kpi_code, window_start, window_end, value, denominator | analytics pipeline | depends | window_start <= window_end. |

### 5.3 KPI Catalog (starter list)
- **Defect rate per 100 FH** (defects / hours * 100).
- **Repeat defect rate** (repeat defects / hours * 100).
- **Removal rate** (unscheduled removals / hours * 1000).
- **NFF rate** (no fault found removals / total removals).
- **Dispatch reliability** (dispatches without technical delay / total dispatches).

### 5.4 FRACAS workflow standard
- **Event intake** → **Finding** → **Investigation** → **Corrective/Preventive actions** → **Verification** → **Closure**.
- Each transition must be time-stamped with accountable owner and approval role.

## 6) Gap list (concrete engineering backlog items)
1. **Extend KPI automation** to include control chart evaluation and scheduled execution, not just manual evaluation triggers.
2. **Expand reliability export formats** (ATA Spec 2000-style exports alongside CSV).
3. **Formalize data dictionary approvals** (versioned approvals and sign-off workflow in the portal).

## 6.1 Confirmed action plan (tasks + status)
The recommendations below have been reviewed and mapped into actionable engineering tasks:

| Task | Status | Notes |
| --- | --- | --- |
| Enforce tenant ownership for dependent reliability objects | ✅ Done | Alert rules, FRACAS actions, and component instances now enforce AMO ownership in services/routes. |
| Fix date vs datetime boundaries in defect trends | ✅ Done | Defect queries now use explicit datetime boundaries to avoid off-by-one behavior. |
| Implement repeat defect counting logic | ✅ Done | Repeat defects now count recurring defects by aircraft/ATA/task code within window. |
| Build automated KPI evaluation job | ⏳ Planned | Add scheduled worker to compute KPI snapshots and call alert evaluation. |
| Implement control chart calculations | ⏳ Planned | Add control chart run storage + EWMA/CUSUM computations. |
| Ingest operational interruptions + MEL deferrals | ⏳ Planned | Add delay/cancel/diversion and MEL deferral models + ingest pipelines. |
| Add dispatch reliability + chronic defect metrics | ⏳ Planned | Define KPIs and compute pipelines aligned with FAA/KCAA expectations. |
| Add reliability meeting/reporting records | ⏳ Planned | Period reports, agendas, action tracking, and effectiveness reviews. |

## 6.2 Notification routing & reporting gaps (audit-critical)
The current Reliability module does **not** yet route alerts/reports to specific AMO users or departments, nor does it produce PDF reports with figures/graphs. This is the highest-risk gap for audit readiness and operational adoption.

### 6.2.1 Notification routing requirements
**What is missing today:** no Reliability-specific notification table, no user/department routing rules, and no worker that evaluates KPI/alerts and notifies AMO staff.  
**Required tasks:**
1. **Define routing rules** per AMO: which roles (Reliability Manager, QA, Engineering) receive alerts by severity, scope (fleet/aircraft/ATA), and threshold.  
2. **Add a Reliability notification entity** (or extend a shared notifications table) with `amo_id`, `user_id`, `department`, `alert_id`, `severity`, `delivery_channel`, and `dedupe_key`.  
3. **Implement dispatch rules** so alerts only notify users within the same AMO and department (prevents cross-tenant false alerts).  
4. **Add background jobs** to evaluate KPIs and dispatch notifications on schedule (daily/weekly) with audit logs.

### 6.2.2 Reliability report outputs
**What is missing today:** no PDF report generation for reliability review packets, no saved report artifacts, and no graph/figure rendering pipeline.  
**Required tasks:**
1. **Add a Reliability report model** storing `amo_id`, `report_period`, `generated_by_user_id`, `file_ref`, and `status`.  
2. **Implement PDF generation** with tables for KPIs/trends and embedded charts (dispatch reliability, repeat defects, MTBUR).  
3. **Persist report artifacts** in a durable storage path and expose download endpoints to AMO users.  

### 6.2.3 Dependencies & packages
Report generation can leverage the existing PDF stack already present in the backend (ReportLab). No new dependencies are required until charting is introduced; if charts are required, a plotting package (e.g., Matplotlib) should be added to backend requirements and pinned per environment.

## 7) Next steps recommendation
1. Decide the compliance target(s) (FAA CASS, KCAA advisory circular, IOSA expectations) and codify them in a Reliability Program Definition document.
2. Publish formal sign-offs for the data dictionary and taxonomy and align ingestion workflows to it.
3. Expand alert automation to cover control chart evaluations and scheduled evaluations.

---

**Owner:** Reliability Engineering

**Document control:**
- Version: 0.1 (initial evaluation)
- Review cadence: Quarterly or after major reliability feature changes
- Approval: AMO Accountable Manager + Quality Manager
