# Reliability V2 Implementation Tracker

## Canonical implementation

- [x] One frontend route tree: `/maintenance/:amoCode/reliability/*`
- [x] One backend prefix: `/reliability/*`
- [x] One canonical frontend client and workspace
- [x] No aliases, duplicate pages, compatibility redirects or `/v2` routes

## Operational and compliance scope

- [x] Complete occurrence taxonomy, immutable provenance and automated source ingestion
- [x] Technical-log, delay, cancellation, interruption, MEL/CDL, EHM, shop, QMS, SMS and Procurement source workflows
- [x] Idempotency, replay-safe batches, duplicate detection, validation, data-quality resolution and freshness controls
- [x] Full FRACAS lifecycle, evidence, root-cause approval, actions, independent effectiveness approval, closure and reopening
- [x] Scheduled KPI engine with formula versions, source lineage, result hashes and retained evidence
- [x] Fleet, aircraft, ATA, component and engine analytics
- [x] Exposure-aware rates, confidence intervals, minimum exposure and small-fleet uncertainty controls
- [x] Versioned Reliability programmes and threshold governance
- [x] Review boards, immutable decisions and controlled programme changes
- [x] Planning, Production, Maintenance, Tech Records, QMS, SMS and Procurement handoffs
- [x] Authority-profile package, submission and decision workflows
- [x] Capability-based permissions, independent approvals and append-only evidence
- [x] Explainable advisory AI with citations and human disposition
- [x] Responsive frontend for every daily and advanced workflow

## Validation

- [x] Populated PostgreSQL upgrade/downgrade/upgrade
- [x] Alembic metadata parity
- [x] Existing-row default and provenance backfill
- [x] Full application import and mapper configuration
- [x] Reliability backend tests
- [x] Navigation and CSS contracts
- [x] Scoped lint
- [x] Complete portal production build
