# Reliability authoritative adapters — stacked slice

## Scope

This slice is stacked on draft PR #449 at `18153ba1324d3b828e9eca2663ffe11d28ebc289`. It does not merge or broaden PR #449. It adds controlled adapter contracts and readiness reporting for the remaining Reliability sources.

## Implemented

### Flight Operations contract

`POST /reliability/authoritative-sources/flight-operations/ingest`

Accepts revisioned technical delays, cancellations, return-to-gate events, air turnbacks, diversions, in-flight shutdowns and aborted takeoffs. A technical delay requires a non-negative whole-minute delay value. Every record requires a stable upstream record ID and revision.

### MEL/CDL contract

`POST /reliability/authoritative-sources/mel-cdl/ingest`

Requires the applicable MEL or CDL reference, a control basis and an expiry that does not precede the occurrence. It deliberately does not hard-code category intervals because those are controlled by the tenant's approved regulatory and MEL profile.

### Scheduled-maintenance findings

Non-routine task cards raised under scheduled work orders remain sourced through `WORKPACK-TASKS`. They now receive explicit `scheduled_check_finding`, `maintenance_finding_context`, parent-task and mapping-revision provenance. The mapping change creates a new immutable source revision instead of rewriting an earlier Reliability event.

### Component-shop findings and NFF

`POST /reliability/authoritative-sources/component-shop/ingest`

Accepts shop findings and NFF dispositions. NFF records must explicitly state `confirmed_failure=false`. When an internal component ID is supplied, tenant, part-number, serial-number and aircraft consistency are checked.

### QMS linkage

`POST /reliability/authoritative-sources/qms/findings/{finding_id}/link`

Links a tenant-owned QMS finding only when a user supplies a Reliability relevance reason and chooses an allowed canonical occurrence type. QMS objective evidence, requirement reference, audit/finding identity, safety-sensitive state and finding revision are retained in the raw payload and provenance chain.

### SMS contract

`POST /reliability/authoritative-sources/sms/ingest`

Accepts revisioned safety occurrences selected by the authoritative SMS process for Reliability analysis. The route requires an SMS reference, risk classification and explicit Reliability linkage reason.

### Workbook historical reconciliation contract

`POST /reliability/authoritative-sources/workbook-history/ingest`

Accepts only rows that have reached `APPROVED` reconciliation state. It retains workbook, sheet, row, mapping-profile and reconciliation-note provenance. File parsing and tenant-specific mapping approval remain a separate implementation slice.

## Readiness and honest source health

- `POST /reliability/authoritative-sources/configure`
- `GET /reliability/authoritative-sources/readiness`

The readiness response distinguishes `WIRED`, `WIRED_VIA_WORKPACK`, `LINK_READY`, `UPSTREAM_REQUIRED`, `MAPPING_REQUIRED`, `NO_DATA` and `CONFIGURATION_REQUIRED`. Creating an adapter contract does not falsely claim that an upstream operational source exists or is connected.

## Deliberate boundaries

The repository currently has no authoritative Flight Operations, MEL/CDL or SMS source-of-record module, and no component-shop report register beyond removal evidence. This slice therefore provides strict canonical contracts and source-health truth, but it does not invent parallel editable operational registers inside Reliability.

Workbook binary parsing, tenant mapping profiles, row preview, reconciliation workbench and approval UI remain pending. Frontend controls for these new routes also remain pending and should be delivered only after the upstream ownership model is approved.
