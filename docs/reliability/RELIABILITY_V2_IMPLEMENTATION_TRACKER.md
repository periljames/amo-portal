# Reliability V2 Implementation Tracker

## Branch baseline

This work is stacked on `feat/global-tenant-navigation-quality-home` (PR #398), not the older `main` shell. Reliability shall consume that canonical tenant shell and navigation work.

## Slice 1 — foundation read model and workspace

- [x] Governing target-design document
- [x] Tenant-scoped `/reliability/v2/workbench`
- [x] Filtered V2 occurrence, alert, FRACAS and engine-status reads
- [x] Tenant-filtered detail reads
- [x] FRACAS action read through tenant-owned case join
- [x] “No data, no green” freshness state
- [x] Route-aware Reliability workspace
- [x] Workbench, occurrence, alert, FRACAS, engine and data-quality views
- [x] Planned route surfaces for fleet, systems, components, programme, changes and meetings
- [x] Scoped Reliability CSS only
- [x] Existing report generation retained at `/reliability/reports`

## Remaining P0 blockers

- [ ] Repair legacy `compute_defect_trend()` tenant filtering
- [ ] Standardise all legacy endpoints on `effective_amo_id`
- [ ] Add database-backed multi-tenant regression fixtures
- [ ] Introduce capability gates for triage, investigation, approval, threshold control and authority submission
- [ ] Add server-side pagination envelopes and total counts
- [ ] Deprecate or redirect unsafe/unbounded legacy reads after consumers migrate

## Next operational increment

- [ ] Canonical occurrence taxonomy and subtypes
- [ ] Technical interruption and MEL/CDL ingestion
- [ ] Repeat-candidate triage and merge/dismiss decisions
- [ ] Expanded FRACAS lifecycle and evidence model
- [ ] Corrective-action effectiveness plan
- [ ] QMS/SMS/Procurement links
- [ ] Scheduled KPI calculations and calculation-run evidence

## Canonical replacement rule

Reliability has one active frontend route tree and one backend API prefix: `/maintenance/:amoCode/reliability/*` and `/reliability/*`. Development does not retain obsolete pages, `/v2` aliases, compatibility redirects, or duplicate service clients. Enhanced functionality replaces the old implementation in place, and unused code is deleted in the same change.
