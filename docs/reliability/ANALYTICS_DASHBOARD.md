# Reliability Analytics Dashboard

## Purpose

The Reliability workbench is the operator-facing analytical layer for canonical Reliability evidence. It does not calculate green status from raw counts alone. Rate-based indicators are shown only when the matching flight-hour or flight-cycle exposure exists.

## Data sources

The dashboard reads tenant-scoped records from:

- Canonical Reliability events.
- Aircraft daily flight-hour and flight-cycle exposure.
- Controlled Flight Operations, MEL/CDL and component-shop sources.
- FRACAS cases, actions, lifecycles and effectiveness reviews.
- Engine trend status and parsed engine-flight snapshots.
- Reliability source registers, ingestion batches and data-quality issues.

No demo series or fabricated fallback values are used.

## Main analytical surfaces

The default Reliability route now provides:

- Dispatch reliability and event-rate trends.
- Technical interruption, ATA, aircraft, station and route analysis.
- Component shop outcomes, NFF and exposure-normalised removal rates.
- MEL/CDL status, expiry forecast, category, extension, repeat-item and closure-duration analysis.
- FRACAS stage, ageing, root-cause, effectiveness, action-flow and reopening analysis.
- Engine status and selectable engine-parameter trends.
- Configured threshold overlays and trend-shift markers where controlled records exist.
- Source freshness, invalid-rate and data-quality analysis.

Every KPI and categorical chart exposes a controlled-record drill-down. Drill-down links return the user to the appropriate occurrence, FRACAS, ingestion, operational-source or data-quality workspace.

## Filters

Shared filters apply consistently to the dashboard and drill-down register:

- Date window and daily, weekly or monthly aggregation.
- Fleet or aircraft type.
- Aircraft serial number.
- ATA chapter.
- Station.
- Event type.
- Severity.
- Source system.

The dashboard compares the selected period with the immediately preceding period of equal length. Saved filter views are stored in the user’s browser and contain no Reliability records.

## Export

- Dashboard CSV contains KPI values and every chart dataset.
- Each graph can be exported as SVG.
- Print mode produces a controlled browser PDF without the interactive filter toolbar.
- Formal retained reports continue to use the existing controlled report generator.

## Integrity rules

- The event-rate denominator is recorded flight hours.
- Dispatch reliability uses recorded flight cycles as the available departure exposure.
- Rates are withheld when exposure is zero or absent.
- Fleet exposure per removal is explicitly labelled as fleet exposure; it is not represented as component MTBUR without component population exposure.
- Engine alert lines appear only from enabled controlled threshold rules matching the selected metric.
- Missing aircraft, ATA or source allocations remain visible as unallocated categories.
- Dashboard windows are limited to 731 days and large canonical-event scans are rejected with a request to narrow the filters.

## Routes

- `GET /reliability/analytics-dashboard`
- `GET /reliability/analytics-dashboard/engine-series`
- `GET /reliability/analytics-dashboard/drilldown`
