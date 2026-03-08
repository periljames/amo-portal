# QMS Audit Schedule Detail / Compliance Intelligence War Room

## Scope
This document describes the Schedule Detail implementation used at:

- `/maintenance/:amoCode/:department/qms/audits/schedules/:scheduleId`
- `/maintenance/:amoCode/quality/audits/schedules/:scheduleId`

The page is implemented by `QualityAuditScheduleDetailPage` + `qualityAudits/AuditDetailView` + `qualityAudits/FindingDrawer`.

## Tenant scoping
All data requests rely on the authenticated AMO context and include the active AMO code in React Query keys:

- `qms-audit-schedules` keyed by `amoCode`
- `qms-audits` keyed by `amoCode`
- `qms-cars` keyed by `amoCode`
- `qms-findings` keyed by `amoCode + scheduleId + audit ids`
- drawer CAP/attachments keyed by `amoCode + finding/car`

## Data mapping summary
The current backend schema does not expose the exact `finding_statement`, `immediate_cap`, `preventive_cap`, `DMS_Links`, `accepted_at`, `prep_checklists`, and `staged_documents` fields named in product notes. The UI maps equivalent live fields as follows:

- **Statement of Fact** ← `QMSFindingOut.description`
- **Accepted timestamp** ← `QMSFindingOut.acknowledged_at` fallback `created_at`
- **Root cause analysis** ← `CAROut.root_cause_text` fallback `CAROut.root_cause`
- **Immediate action** ← `CAROut.containment_action`
- **Preventive action** ← `CAROut.preventive_action`
- **Evidence Vault** ← `qmsListCarAttachments(car_id)` + `CAROut.evidence_ref` + finding objective evidence references
- **Verify & Close** ← `POST /quality/findings/{id}/verify` then `POST /quality/findings/{id}/close`

## CHI formula
CHI lives in `qualityAudits/chi.ts` and is intentionally explicit:

- Baseline score per audit = `100`
- Penalties per finding level:
  - `LEVEL_1` => `-5`
  - `LEVEL_2` => `-2`
  - `LEVEL_3` => `-0.5`
- Per-audit score is clamped to `[0, 100]`
- Schedule CHI is the average over audits in the last 12 months
- Trend sparkline shows up to the last 4 audits
- If no qualifying audits exist, CHI returns `null` and the UI displays a safe fallback

## Readiness formula
Readiness lives in `qualityAudits/readiness.ts` and is deterministic:

- checklist attached (`audit.checklist_file_ref`) = 40
- report attached (`audit.report_file_ref`) = 20
- lead auditor assigned (`schedule.lead_auditor_user_id`) = 20
- scope defined (`schedule.scope`) = 20
- total score range = `0..100`

Labels:

- `>= 85`: Ready for fieldwork
- `>= 60`: Partially ready
- `< 60`: Preparation incomplete

## Known gaps
- No dedicated read-only `GET /quality/findings/{id}/cap` endpoint exists today; drawer CAP blocks are currently sourced from linked CAR fields until a read-only CAP detail endpoint is introduced.
- Risk heatmap granularity is approximated from dashboard open-finding counts (L1/L2/L3) until a dedicated risk service is exposed.
