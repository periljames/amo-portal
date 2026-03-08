# Production Module Discovery Notes

## Existing backend endpoints to reuse (Fleet)

- `GET /aircraft` — fleet master list (tail/serial/type/status/home base/totals). Source: `backend/amodb/apps/fleet/router.py`.
- `GET /aircraft/{serial_number}/usage` — utilisation history including `date`, `techlog_no`, `block_hours`, `cycles`, and totals (`ttaf_after`, `tca_after`, `ttesn_after`, `tcesn_after`, `ttsoh_after`, `ttshsi_after`), plus `hours_to_mx`, `days_to_mx`, and optimistic concurrency field `updated_at`.
- `POST /aircraft/{serial_number}/usage` — create utilisation entries; uniqueness conflict returns `409` when date+techlog exists.
- `PUT /aircraft/usage/{usage_id}` — update utilisation with optimistic concurrency (`last_seen_updated_at`).
- `GET /aircraft/{serial_number}/usage/summary` — summary totals and 7-day avg hours.
- `GET /aircraft/{serial_number}/maintenance-status` — read-only inspection/hard-time due data.
- `GET /aircraft/{serial_number}/components` and `GET /aircraft/{serial_number}/components/{component_instance_id}/history` — component register + movement history.

## Existing Technical Records endpoints to reuse (canonical read views)

- `GET /records/airworthiness/AD` and `GET /records/airworthiness/SB` — AD/SB register rows.
- `GET /records/deferrals` — deferrals register.
- `GET /records/reconciliation` — exception queue.

## Existing frontend routes/pages/components discovered

- Department shell/nav: `frontend/src/components/Layout/DepartmentLayout.tsx`.
- Department root route pattern already present: `/maintenance/:amoCode/:department` in `frontend/src/router.tsx`.
- Existing production department exists as a top-level department option in `frontend/src/utils/departmentAccess.ts`.

## Reuse mapping for Production worksheet tabs

- Fleet Hours (summary + daily):
  - Source: `/aircraft`, `/aircraft/{tail}/usage`, `/aircraft/{tail}/usage/summary`, `POST/PUT /aircraft/.../usage`.
- Logbooks:
  - Source: existing technical records logbook concept; current implementation uses `GET /records/deferrals` as linked evidence/WO/CRS context and placeholders for dedicated logbook feed where unavailable.
- Compliance (AD/SB):
  - Source: `/records/airworthiness/AD`, `/records/airworthiness/SB`.
- Inspections & Hard Time:
  - Source: `/aircraft/{tail}/maintenance-status`.
- Modifications:
  - Source: read-only placeholder grid linked from production workspace (no duplicate store).
- Components (OC/CM):
  - Source: `/aircraft/{tail}/components`.
- Missing/Backfill:
  - Source: `/aircraft/{tail}/usage` + `POST /aircraft/{tail}/usage` (conflicts surfaced inline from 409 responses).

## Training & Competence module discovery (current iteration)

- Backend training domain already includes AMO-scoped courses, requirements, events, participants, records, deferrals, notifications, and audit logs under `backend/amodb/apps/training/*`.
- Existing operator routes reused:
  - `/maintenance/:amoCode/:department/qms/training`
  - `/maintenance/:amoCode/:department/qms/events`
  - `/maintenance/:amoCode/:department/training`
- New consolidated hub route:
  - `/maintenance/:amoCode/:department/training-competence`
- Sidebar integration now includes a dedicated top-level **Training & Competence** entry for faster cross-workflow navigation.
