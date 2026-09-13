# QMS hardening: Phase 1

Base: `5ee2e088d4781b3c0d5bbad41c3a5cb44ef1f475` (main, merged Assurance Overview PR #533).
Feature branch: `feat/qms-foundation-hardening`. Existing ZIP edits are unrelated and excluded.

## Production decisions

- SQL source outcomes distinguish success, source/schema unavailability, access failure and query failure. Required failures return null metrics/series, explicit warnings, unavailable overall readiness and an incomplete queue message. Operational source errors do not become healthy zeroes.
- Tenant ownership is explicit. Counts/search never omit the tenant predicate; programme items and finding parents use same-tenant joins. Existing tenant_security, session actor and PostgreSQL RLS context remain authoritative.
- One responsibility helper covers assigned audit participants (including supporting auditors), programme owner/item participants, CAR assignees, control/document owners and finding parent audits. Creation/request provenance does not imply assignment. Unsupported personal aggregates remain unavailable; search returns no records for unsupported relationships.
- Programme coverage is for the selected programme year. Audit delivery uses the cohort's planned start (creation date fallback), with current lifecycle completion of that cohort. Finding creation uses an exclusive annual end boundary. CAR ageing/control exposure/readiness are explicitly current, not reconstructed snapshots.
- Canonical audit pages return rich established audit records plus total/limit/offset, server filters, actor view, annual cohort and stable sorting. The workspace requests its actual page. Existing collection consumers traverse every page, including selectors/recycle bin/launch duplicate detection.
- Findings/CAR registers and controls accept server-authoritative personal scope. Unscheduled requirements and controls have offset/total pagination. Search uses canonical evidence/audit/document destinations and source permissions.

## Compatibility and migrations

`GET /quality/audits` remains an external array adapter around the single audit query service. No live frontend list caller uses that adapter. The canonical endpoint adds fields while preserving its items envelope. `qmsListAllAudits` is an intentional complete-collection adapter for existing selectors/registers; it is not another query implementation.

`quality_260913_assurance_idx` follows `accounts_260907_access_profiles`, adds an active audit ordering index `(amo_id, domain, planned_start, id)` and an annual finding index `(amo_id, created_at)`, and reverses both on downgrade. Existing tenant/status/due/programme indexes were inspected in source and reused. No migration was applied and no business records were modified. Live database index/query-plan verification belongs to Phase 5.

## Production files created/changed

- `backend/amodb/alembic/versions/quality_20260913_assurance_query_indexes.py`
- `backend/amodb/apps/quality/assurance_cockpit_detail_router.py`
- `backend/amodb/apps/quality/assurance_cockpit_router.py`
- `backend/amodb/apps/quality/assurance_metrics_router.py`
- `backend/amodb/apps/quality/assurance_sources.py`
- `backend/amodb/apps/quality/assurance_wiring_router.py`
- `backend/amodb/apps/quality/audit_list_service.py`
- `backend/amodb/apps/quality/audit_risk_planning_router.py`
- `backend/amodb/apps/quality/canonical_core_router.py`
- `backend/amodb/apps/quality/models.py`
- `backend/amodb/apps/quality/register_pagination.py`
- `backend/amodb/apps/quality/router.py`
- `frontend/src/components/QMS/QmsCommandPalette.tsx`
- `frontend/src/components/QMS/QualityExcellenceCockpit.tsx`
- `frontend/src/pages/QMSAuditsPage.tsx`
- `frontend/src/pages/QMSEventsPage.tsx`
- `frontend/src/pages/QualityCarsPage.tsx`
- `frontend/src/pages/qualityAudits/AuditDetailView.tsx`
- `frontend/src/pages/qualityAudits/QualityAuditAssuranceDashboardPage.tsx`
- `frontend/src/pages/qualityAudits/QualityAuditPlanScheduleBasePage.tsx`
- `frontend/src/pages/qualityAudits/QualityAuditRecycleBinPage.tsx`
- `frontend/src/pages/qualityAudits/QualityAuditRegisterPage.tsx`
- `frontend/src/pages/qualityAudits/QualityAuditsWorkspacePage.tsx`
- `frontend/src/pages/qualityAudits/auditsWorkspaceModel.ts`
- `frontend/src/services/assuranceCockpit.ts`
- `frontend/src/services/qmsAuditPreparationContext.ts`
- `frontend/src/services/qmsAuditResolveDirect.ts`
- `frontend/src/services/qmsCore.ts`
- `frontend/src/services/qmsIntelligence.ts`
- `frontend/src/services/qmsRegisters.ts`
- `frontend/src/services/qualityExcellence.ts`

No production file was deleted. Removed obsolete false-zero helpers and AUDITS_LIST_BOUND from their owning files.

## Phase boundary

Phase 1 implementation is complete, subject to Phase 5 validation. Production syntax and diffs were inspected without importing/running the application. No unit tests, browser tests, builds, coverage or CI simulations were run; no tests were edited.

Phase 2 owns canonical frontend path adoption, full URL restoration, navigation ownership, command-palette modal/focus behavior and chart/touch accessibility. The existing Assurance and enterprise Control Room remain separate surfaces. Phases 3-5 must remain on this feature PR; do not merge before Phase 5 completes.
