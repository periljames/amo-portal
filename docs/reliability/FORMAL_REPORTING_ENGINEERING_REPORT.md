# Formal Reliability Programme Reporting — Engineering Report

**Repository baseline:** `periljames/amo-portal`  
**Baseline commit:** `5e6f7cf0f259b49adc3cafde34beee92bfffa7ec`  
**Branch:** `agent/reliability-programme-formal-reporting`  
**Prepared:** 2026-08-07

## Purpose

This report is the mandatory pre-implementation checkpoint for the formal Reliability Programme reporting phase. It records the existing-state audit, current regulatory findings, gap analysis, target architecture, review-workspace concept and implementation sequence before major schema or UI changes are made.

It is an engineering and regulatory-traceability design record. It is **not** a declaration that AMO Portal, a tenant, or a generated report is compliant with any authority merely because a feature or report section exists.

---

## A. Existing-state audit

PR #465 is merged and provides the operational evidence and calculation foundation that the formal programme layer must reuse.

### Controlled operating evidence

The forward Reliability implementation already supports the 16 controlled source domains:

`AU`, `AI`, `FI`, `PM`, `OOS`, `RM`, `SM`, `SR`, `SB`, `CS`, `AS`, `UR`, `STRUCTURES`, `RECURRING`, `ECTM`, `ADD`.

Existing intake/governance includes:

- governed manual entry;
- canonical structured CSV/TSV intake;
- workbook compatibility intake;
- authoritative portal-source integrations;
- `DRAFT -> APPROVED -> CLOSED` source-record lifecycle;
- immutable approved evidence;
- superseding correction rather than destructive rewriting;
- source/row hashing and retained import evidence;
- tenant scoping and role-based access controls.

### Common analytics/calculation foundation

The merged Reliability analytics layer already provides:

- denominator-aware calculations;
- explicit missing/zero-denominator withholding rather than false zero rates;
- governed formula definitions and retained calculation evidence;
- exact-number support in the controlled calculation path;
- arbitrary date ranges and bounded chart buckets;
- fleet and aircraft analysis;
- dispatch reliability, event rates, utilisation, ATA Pareto, operational interruptions, component/shop/deferral/FRACAS/engine views;
- previous-equivalent-period comparisons;
- evidence drill-down.

The formal programme layer **must call this same analytical contract**. It must not duplicate dispatch, rate, MTBUR/MTBR, alert or exposure mathematics inside a report renderer.

### Retained management reporting already available

`management_reporting.py` already consumes `build_dashboard(...)`, combines it with controlled source-domain populations, and persists a retained `ReliabilityWorkbookReportSnapshot` containing:

- report period and aircraft filter;
- retained rendered data;
- retained HTML;
- SHA-256 of the retained HTML;
- generated-by identity/time;
- authenticated HTML/data/PDF routes.

This is the correct lower-level snapshot concept to extend. Formal reports require a richer governed publication aggregate around it rather than replacement of it.

### Existing structures that should be reused

- canonical `ReliabilityEvent` and source references;
- `ReliabilityAlert` and statistical-alert evidence;
- FRACAS cases/actions and the richer append-only FRACAS lifecycle/evidence records;
- `ReliabilityProgramme`;
- report layouts and retained management snapshots;
- formula/calculation snapshots;
- data-quality issues;
- existing tenant/user/role model;
- current Reliability CI and browser workflow.

### Structures that are not sufficient for formal publication

The older generic `ReliabilityReport` (`PENDING/READY/FAILED`) is only a generated-artifact concept and does not model formal review, approval, publication, supersession or requirement traceability. It should not be destructively repurposed.

The existing simple `ReliabilityRecommendation` (`OPEN/IN_PROGRESS/CLOSED`) also does not express the controlled maintenance-programme recommendation workflow required for escalation/de-escalation and authority review. A governed AMP-recommendation aggregate should be added without breaking the operational recommendation contract.

---

## B. Regulatory requirements audit

### Source-control rule

Every seeded regulatory requirement must carry its official source URL, source/revision date, controlled summary, applicability rule and verification status. Historical guidance must be labelled as historical/advisory where appropriate. A missing or unverified current paragraph is represented as a governed `GAP`/`WITHHELD` condition, never guessed.

### Kenya / KCAA

Current official sources reviewed:

- KCAA Regulations 2025 transition/publication page: https://www.kcaa.or.ke/legislation-publications/regulations-2025
- KCAA Airworthiness Advisory Circular listing: https://www.kcaa.or.ke/legislation-publications/advisory-circulars
- KCAA `CAA-AC-AWS010D — Reliability Programme` PDF published through the KCAA site.

Current finding:

1. KCAA states that the revised 2025 regulations are binding and that regulated entities must align operations, systems and procedures, review the new requirements, and revise/submit affected manuals, programmes and other documents as required.
2. KCAA's current advisory-circular catalogue still lists `CAA-AC-AWS010D — Reliability Programme`, effective 01 July 2018.
3. `CAA-AC-AWS010D` itself references the 2018 regulatory framework. It therefore remains useful as KCAA reliability-programme advisory/analytical guidance, but it must not be treated by the application as conclusive evidence of compliance with the 2025 regulations.
4. The circular's periodic-report guidance includes fleet/service population, operating days, FH, utilisation, average flight duration, cycles/landings, delays/cancellations, incidents, technical-delay/cancellation rates and trends, diversions, engine shutdown/propeller events, MEL trends, long-term trend history, corrective action and report retention/distribution.
5. The circular specifies long-term trend examples with at least 12 consecutive months for specified displays and contains alert-level/statistical examples.
6. The formal KCAA profile therefore needs an explicit **KCARs 2025/operator-programme cross-reference gate**. Until the exact current KCAA paragraph/revision applicable to the tenant is captured and verified, the profile must not silently mark the legacy 2018 reference as satisfying the current mandatory requirement.

Implementation decision: seed legacy `CAA-AC-AWS010D` requirements as advisory/legacy evidence and seed a mandatory KCAA-current-regulation verification requirement that remains `GAP` until a verified 2025/operator-approved reference is recorded.

### EASA

Current official source reviewed:

- EASA Easy Access Rules for Continuing Airworthiness, current revision published September 2025: https://www.easa.europa.eu/en/document-library/easy-access-rules/easy-access-rules-continuing-airworthiness

Key implementation findings from Appendix I to AMC M.A.302 and associated continuing-airworthiness material:

- reliability-programme applicability depends on the maintenance-programme basis/configuration, including MSG-3 and condition-monitoring circumstances;
- the programme objective includes recognising the need for corrective action, determining the action and determining its effectiveness;
- the controlled population and systems/items must be identifiable, including separate engine/APU programmes where applicable;
- data sources are expected to cover relevant operational and maintenance evidence such as pilot/technical reports, onboard systems, maintenance findings, workshop findings, stores, delays/incidents and special-operation evidence where applicable;
- information must be displayed so trends/highlights can be identified; performance standards/alert levels and nil returns are contemplated;
- analysis should consider trends, repetitive defects, deterioration, maintenance findings, modifications, procedures, training and service information;
- corrective action may include maintenance-programme task additions, modifications, deletions and interval escalation/de-escalation, subject to the applicable approval path;
- organisational responsibility, routine reporting, report distribution and authority evaluation of programme changes must be defined;
- programme effectiveness is continuously reviewed, with routine/non-routine review periods that may be progressive, monthly, quarterly or annual;
- maintenance-programme amendment approval remains governed and is not an automatic consequence of a reliability recommendation.

Implementation decision: the EASA profile will version the applicable M.A.302/AMC/GM requirements and separately retain the authority/operator approval rule for any maintenance-programme change.

### FAA

Current official sources reviewed:

- FAA AC landing page for `AC 120-17B`: https://www.faa.gov/regulations_policies/advisory_circulars/index.cfm/go/document.information/documentid/1035253
- `AC 120-17B — Reliability Program Methods—Standards for Determining Time Limitations`, original 19 December 2018, **Editorial Update 9 July 2026**.

The FAA currently marks AC 120-17B active. The 9 July 2026 document identifies the change as editorial.

Key implementation findings:

- the reliability programme is part of the CAMP framework for the operators to which the AC applies;
- the programme should define data collection, performance standards, analysis/recommendation, approval/implementation and reporting/display;
- source applicability, fleet/type scope, data quality, responsibilities, standards, analysis, corrective-action recommendation/approval, report frequency, time-limit adjustment and self-audit controls must be defined;
- reporting/display should cover the controlled systems sufficiently to monitor maintenance-schedule effectiveness, provide enough data to portray operation, occur often enough to identify degrading trends, identify areas below standards, carry forward unresolved deficiencies/corrective actions, show planned/implemented recommendations and permit effectiveness monitoring;
- reporting method/frequency may vary with programme complexity, but distribution and timing must be defined and reports must reach senior maintenance management and the FAA oversight office as applicable;
- an accepted/authorised reliability programme may support maintenance task/interval adjustments within its approved authority, but restricted-source tasks remain subject to their controlling requirements and the operator's approval authority does not remove safety/FAA oversight obligations.

Implementation decision: store the FAA source as `AC 120-17B`, revision metadata `2018-12-19 / Editorial Update 2026-07-09`, plus applicable 14 CFR/OpSpecs references. The profile must distinguish guidance from binding regulatory/OpSpecs requirements.

### Regulatory source precedence

The application will use this precedence model:

1. applicable binding regulation / approval / OpSpecs / authority condition;
2. accepted/approved operator Reliability Programme and maintenance programme;
3. authority AMC/GM/AC/advisory material as applicable;
4. OEM/MRB/MSG-3 material within its approved effectivity and restrictions;
5. industry/operator benchmarking for presentation and analytical quality only.

No OEM/operator benchmark may silently override items 1–4.

---

## C. Gap analysis

### Monthly reporting

Operational data, analytics, arbitrary periods, alerts, drill-down and retained management snapshots already exist.

Missing for a formal monthly Reliability Programme issue:

- versioned regulatory/operator profile selection;
- report number/revision and formal document control;
- frozen data cutoff and effectivity;
- mandatory section/requirement completeness gate;
- controlled engineering commentary with evidence linkage;
- formal review/approval lifecycle;
- immutable publication record and retained PDF hash;
- controlled distribution/supersession.

### Quarterly reporting

In addition to monthly gaps:

- profile-controlled quarter obligations and authority/board schedule;
- quarterly completeness expectations;
- retained management/authority meeting decisions;
- carry-forward of unresolved alerts/FRACAS/actions;
- previous-period and longer-window requirements driven by profile rather than UI convention.

### Six-month / half-year review

Missing:

- first-class half-year period type and configurable January–June/July–December or operator cycle;
- longer-window trend snapshots;
- maintenance-programme effectiveness chapter;
- controlled AMP recommendation workflow;
- formal chapter engine/appendices/evidence index;
- review roles and separation of duties;
- publication-blocking regulatory traceability.

### Annual report

Missing:

- annual/YTD/custom programme-cycle model independent of a 731-day management UI guard;
- 12/24/36+ month governed trend windows backed by bounded server aggregation;
- annual programme-effectiveness assessment;
- long-term alert/defect/component/deferral/FRACAS trend pack;
- annual conclusion/recommendation/management-decision controls;
- retained exact approved PDF and rendered snapshot revision.

### Regulatory publication

Missing across all formal periods:

- machine-readable versioned requirement master;
- versioned KCAA/EASA/FAA/OPERATOR profiles;
- per-report applicability/evidence assessment;
- `SATISFIED`, `NOT_APPLICABLE`, `WITHHELD`, `GAP`, `SUPERSEDED` traceability;
- mandatory-gap publication blocker;
- explicitly governed override record where a profile permits an exceptional disposition;
- frozen source population/formula revisions/calculation/chart data;
- preparer/technical/quality/approval decisions bound to report revision/hash;
- publication and distribution audit trail;
- immutable supersession rather than overwriting a published report.

---

## D. Proposed architecture

### 1. Regulatory requirement master

Add versioned `ReliabilityRegulatoryRequirement` records containing:

- authority/jurisdiction/profile baseline;
- source type, reference, paragraph and URL;
- effective date and revision;
- controlled summary;
- applicability rules;
- mandatory/advisory status;
- report section mapping;
- authoritative source domains/calculation code;
- minimum analysis/history windows;
- evidence/completeness rule;
- approval role;
- lifecycle/supersession metadata.

Historical rows are not destructively edited when a regulation changes.

### 2. Regulatory profiles

Add versioned `ReliabilityRegulatoryProfile` records for:

- `KCAA`;
- `EASA`;
- `FAA`;
- `OPERATOR`.

A profile stores machine-readable required sections, mandatory KPIs, minimum periods, statistical methods, history windows, commentary/evidence rules, approval chain and publication rules. Operator profiles may derive from more than one baseline only when every applicable requirement remains traceable.

### 3. Formal report aggregate

Add a new formal-report aggregate separate from the old generic report artifact.

Core lifecycle:

`DRAFT -> DATA_REVIEW -> TECHNICAL_REVIEW -> QUALITY_REVIEW -> APPROVAL_PENDING -> APPROVED -> PUBLISHED`

Terminal/retained states:

`SUPERSEDED`, `WITHDRAWN`.

The report stores/finally freezes:

- report number/revision/title/programme;
- period type/start/end;
- data cutoff;
- effectivity snapshot;
- profile and requirement versions;
- source-population identity;
- formula/calculation snapshots;
- chart data;
- narrative/section content;
- completeness result;
- rendered HTML and hash;
- retained PDF reference/bytes according to the existing document-storage pattern and PDF SHA-256;
- publication/supersession metadata.

### 4. Chapter/section engine

Add ordered formal sections rather than a single hard-coded report. Section configuration comes from the selected profile and stores controlled user commentary separately from computed data.

Computed values come from the existing Reliability analytics/calculation services. A chapter renderer receives already-governed values and evidence references; it does not reimplement formulas.

### 5. Per-report requirement evidence

Add a report requirement-assessment table that freezes the exact requirement version and records:

- applicability;
- status (`SATISFIED`, `NOT_APPLICABLE`, `WITHHELD`, `GAP`, `SUPERSEDED`);
- linked section;
- evidence/calculation/source references;
- reviewer note;
- resolver identity/time.

This is the basis for the publication completeness gate.

### 6. Completeness engine

Before approval/publication, execute deterministic checks for:

- frozen effectivity/data cutoff;
- profile/version present;
- required sections present;
- required aircraft/source populations assessed;
- denominator availability and explanations;
- mandatory requirements not `GAP`;
- `WITHHELD` requirements explained/resolved according to profile;
- alerts/FRACAS/recommendations disposition;
- required commentary;
- approval-chain configuration;
- frozen calculations;
- successful deterministic render;
- retained PDF hash.

Publication is blocked on mandatory failure. Any exceptional override is a separate, explicit, authorised, reasoned and audited record; it is never a hidden bypass flag.

### 7. Effectivity and cutoff

Effectivity is stored as a frozen JSON snapshot at controlled-review entry and may represent tenant fleet, family/type/subtype, selected registrations, engines/positions, propellers, APU or component population.

The data cutoff is immutable once controlled review begins. Later source changes cannot alter an approved/published revision.

### 8. Review/approval events

Use append-only approval/lifecycle event records with:

- actor identity;
- role at decision time;
- decision;
- comment/rationale;
- timestamp;
- report revision;
- report/snapshot hash.

No personal names are hard-coded. Separation-of-duty rules are profile/tenant controlled.

### 9. AMP recommendation workflow

Add a formal maintenance-programme recommendation aggregate with lifecycle:

`IDENTIFIED -> ANALYSIS -> RECOMMENDED -> TECHNICAL_REVIEW -> QUALITY_REVIEW -> AUTHORITY_APPROVAL_REQUIRED -> APPROVED -> IMPLEMENTED -> EFFECTIVENESS_MONITORING -> CLOSED`.

The profile may omit/reorder stages only through governed configuration. A recommendation never directly mutates an approved AMP interval/task.

### 10. Reporting schedule and distribution

Add tenant-scoped reporting obligations and retained distribution events. Publication does not occur automatically when a due date passes.

### 11. Audit/evidence chain

Target navigation:

`Formal report -> chapter -> KPI/chart -> calculation snapshot -> formula revision -> numerator/denominator -> source records -> originating module`.

Every link carries tenant scope and immutable publication context.

---

## E. Proposed UI — Reliability Review workspace

The formal preparation workflow should be one workspace, not twenty disconnected pages.

### Workspace frame

**Top control strip**

- report identity/revision/status;
- period selector (monthly/quarterly/half-year/annual/YTD/rolling/custom);
- profile/version selector;
- fleet/effectivity selector;
- data-cutoff state;
- completeness score/status;
- Preview / Submit for review actions.

**Left navigation — report chapters**

Ordered chapter list from the selected profile with status icons:

- complete;
- needs commentary;
- data warning;
- requirement gap;
- withheld;
- not applicable.

**Main engineering canvas**

For the selected chapter:

- KPI/graph/table pairing;
- current and historical comparison;
- alert/control thresholds where relevant;
- bounded evidence table;
- drill-down links;
- controlled engineering commentary;
- linked FRACAS/actions/AMP recommendations;
- data-quality limitations.

**Right review rail**

- applicable requirements;
- evidence status;
- unresolved completeness items;
- reviewer notes;
- approval history for the revision.

**Bottom publication bar**

- render health;
- HTML/PDF hashes after freeze;
- review-stage actions allowed for the current role;
- publish control only when all mandatory gates pass.

### Dedicated supporting views

Keep secondary pages only for administration that does not belong in daily report assembly:

- Regulatory profile/version administration;
- Requirement library and source revisions;
- Reporting schedule/calendar;
- Published report library/distribution history;
- AMP recommendation register.

---

## F. Implementation phases

### Phase 1 — governance/data model

1. Add regulatory requirement/profile models and enums.
2. Add formal report/revision/section/effectivity/requirement-assessment models.
3. Add approval/lifecycle/distribution/audit records.
4. Add AMP recommendation and reporting-schedule records.
5. Add indexed Alembic migration and immutability protections for published evidence.

### Phase 2 — profile/completeness services

1. Seed controlled baseline profiles without claiming unverified applicability.
2. Add requirement versioning/supersession services.
3. Add profile resolver/applicability evaluation.
4. Add completeness engine and blocking rules.
5. Add role/separation-of-duty checks.

### Phase 3 — formal snapshot/report builder

1. Reuse `build_dashboard` and controlled source/calculation evidence.
2. Freeze effectivity/data cutoff/source population/formula revisions.
3. Build chapter data contracts.
4. Retain chart data/narrative/evidence index.
5. Render retained HTML and retained PDF; hash both.

### Phase 4 — review/publication workflow

1. Implement stage transitions.
2. Add commentary/evidence linkage.
3. Add approvals bound to revision/hash.
4. Add publication, supersession and withdrawal rules.
5. Add authenticated retained permalink and distribution history.

### Phase 5 — frontend Reliability Review workspace

1. Add the single report-preparation workspace.
2. Add chapter navigation and completeness rail.
3. Add effectivity/profile/period controls.
4. Add graph/table/evidence drill-down and commentary controls.
5. Add role-aware review/approval/publication actions.

### Phase 6 — tests and regression

Add dedicated formal-reporting backend/calculation/frontend/Playwright coverage, then rerun the entire existing Reliability regression suite. The existing 16-domain workflow, intake, approvals, analytics, denominator handling, retained manager reports and PDFs remain release gates.

### Phase 7 — final reconciliation

Sync with current `main`, resolve integration/migration conflicts, run exact-head CI, inspect review threads and update the draft PR description with actual implementation evidence. The PR remains draft while any mandatory gate is red.

---

## Non-negotiable implementation rules

- No duplicate Reliability mathematics in report code.
- No false `0%` where a denominator is absent.
- No destructive rewrite of regulations or published evidence.
- No automatic AMP change from a reliability recommendation.
- No automatic publication at period end.
- No hard-coded personal approvers.
- No client-side unbounded historical populations.
- No IEEE-754 float for new controlled cumulative exposure/life calculations where exact decimal/integer representation is required.
- No KCAA-2025 compliance claim derived solely from the 2018 advisory circular.
- No AI-generated report content becomes controlled content until an authorised user explicitly accepts it.
