# Formal Reliability Programme Reporting Architecture

**Baseline:** PR #465 merged at `5e6f7cf0f259b49adc3cafde34beee92bfffa7ec`  
**Implementation branch:** `agent/reliability-programme-formal-reporting`

## Architectural rule

Formal reports are a governed projection of the existing Reliability evidence/calculation system. They do not own a second mathematical engine.

`Operational source -> governed Reliability source/event -> build_dashboard/formula revision -> frozen formal calculation snapshot -> report chapter -> retained HTML/PDF -> publication/distribution`

The same calculation definition and governed source population must explain a number shown in live analytics, a formal chapter, the retained PDF and evidence drill-down.

## Core aggregates

### Regulatory intelligence

- `ReliabilityRegulatoryProfile`
- `ReliabilityRegulatoryRequirement`

Profiles are versioned `KCAA`, `EASA`, `FAA` or `OPERATOR` baselines. They configure chapters, KPIs, historical windows, evidence rules, approval workflow and publication gates. Requirements are independently versioned and superseded rather than overwritten.

### Formal report

- `ReliabilityFormalReport`
- `ReliabilityFormalReportSection`
- `ReliabilityFormalRequirementAssessment`
- `ReliabilityFormalReportSource`

A report revision freezes profile/version, regulatory manifest, data cutoff, effectivity, source-population identity, formula revisions, calculation snapshots, chart data, data-quality evidence, HTML and PDF hashes.

### Governance/audit

- `ReliabilityFormalApproval`
- `ReliabilityFormalLifecycleEvent`
- `ReliabilityFormalCompletenessOverride`
- `ReliabilityFormalDistribution`
- `ReliabilityReportingSchedule`
- `ReliabilityAmpRecommendation`

Lifecycle/approval records are append-only. PostgreSQL triggers protect published analytical evidence and child evidence from update/delete.

## Formal lifecycle

`DRAFT -> DATA_REVIEW -> TECHNICAL_REVIEW -> QUALITY_REVIEW -> APPROVAL_PENDING -> APPROVED -> PUBLISHED`

Retained terminal states:

- `SUPERSEDED`
- `WITHDRAWN`

Published content is immutable. A correction begins a new draft revision that references the prior report. The prior publication remains available and is explicitly superseded rather than overwritten.

## Frozen context

Entering controlled data review freezes:

- cutoff timestamp;
- selected fleet/effectivity;
- controlled source identities through cutoff;
- governed analytics snapshot;
- formula catalogue/version;
- data-quality warnings;
- chart payload.

The current implementation bounds retained workbook and canonical-event populations at 100,000 rows per source family. Larger populations must use indexed aggregation/materialised evidence rather than an unbounded application read.

## Completeness engine

Publication advancement checks at least:

- profile/version retained;
- effectivity frozen;
- cutoff frozen;
- source-population identity retained;
- calculation snapshot retained;
- formula revisions retained;
- required sections complete;
- mandatory applicable requirements not `GAP`;
- required `WITHHELD` conditions dispositioned;
- retained HTML/SHA-256;
- retained PDF/SHA-256.

A governed exceptional override is a separate audit record with justification, authority basis, approver identity/role and report hash. There is no silent bypass flag.

## Maintenance-programme recommendations

Formal Reliability recommendations use the controlled lifecycle:

`IDENTIFIED -> ANALYSIS -> RECOMMENDED -> TECHNICAL_REVIEW -> QUALITY_REVIEW -> AUTHORITY_APPROVAL_REQUIRED -> APPROVED -> IMPLEMENTED -> EFFECTIVENESS_MONITORING -> CLOSED`

Each formal recommendation is also represented in the existing `ReliabilityChangeProposal` foundation. Neither object directly changes an approved AMP task or interval.

## Reporting schedule

Tenant-scoped obligations define profile/programme, report period, due date, owner and status. Overdue is derived from due date/status; reaching a due date does not auto-publish a report.

## Review workspace

The `/reliability/formal-review` surface is a single preparation workspace:

- controlled report library;
- profile/period creation;
- effectivity/cutoff freeze;
- chapter navigator;
- analytical payload and evidence context;
- typed engineering commentary (`OBSERVED_FACT`, `STATISTICAL_INTERPRETATION`, `ENGINEERING_JUDGEMENT`, `RECOMMENDATION`, `MANAGEMENT_DECISION`);
- requirement assessment rail;
- completeness blockers;
- retained HTML/PDF generation;
- governed lifecycle actions.

## Publication rendering

The renderer consumes only the retained calculation/report snapshot. It does not recalculate a KPI. Missing values remain explicitly `WITHHELD`; a missing denominator is never converted to `0%`.

HTML and PDF are SHA-256 hashed. The PDF uses deterministic/invariant ReportLab generation. Reopen/download verifies the retained hash before returning the artifact.

## Performance

- interactive analysis remains bounded;
- formal source identity capture is bounded;
- historical 24/36+ month charts should use indexed backend aggregation rather than browser event populations;
- formal snapshots remain deterministic and tenant scoped;
- no cumulative aircraft/component utilisation is mutated to create a report.

## OEM/operator benchmark principles

Official material reviewed on 2026-08-07 supports several product principles without copying proprietary layouts:

- De Havilland Canada publicly describes customised Reliability/maintenance-cost analysis and optimised maintenance-programme/planning recommendations for Dash 8 support: https://dehavilland.com/aftermarket-support/
- Boeing Maintenance Performance Toolbox emphasises a single controlled source, connected maintenance requirements/task cards, revision control, traceability to approved technical source documents and mixed-fleet operation: https://services.boeing.com/maintenance-engineering/maintenance-optimization/maintenance-performance-toolbox

These references inform information architecture and traceability. They do not override regulation, an approved operator programme, OEM effectivity restrictions or authority approval conditions.
