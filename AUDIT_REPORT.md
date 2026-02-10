# QMS/MPM Repository Audit Report

## 1) Stack Identification (Evidence-Based)

### Backend
- **Framework**: FastAPI app entrypoint with routers registered in `backend/amodb/main.py`. 
- **ORM**: SQLAlchemy models (e.g., `backend/amodb/models.py`, `backend/amodb/apps/*/models.py`).
- **Migrations**: Alembic (`backend/amodb/alembic` + `backend/amodb/alembic.ini`).
- **Auth**: JWT/OAuth2 password flow with Argon2/bcrypt hashing in `backend/amodb/security.py`.
- **Job Scheduler / Queue**: No queue system found. A cron/Task Scheduler script exists for billing maintenance (`backend/amodb/jobs/billing_maintenance.py`).
- **Email Provider**: Notification service abstraction with a no-op default provider and email log store exists (`backend/amodb/apps/notifications`). No external provider configuration detected in repo.
- **Storage for Attachments**: Local filesystem paths for CAR attachments (`backend/amodb/apps/quality/router.py`, `CAR_ATTACHMENT_DIR` under `backend/amodb/generated/quality`).

### Frontend
- **Framework**: React 19 + Vite (see `frontend/package.json`).
- **Routing**: React Router v7 in `frontend/src/router.tsx`.
- **State Management**: No external state library found in `frontend/package.json` (uses React hooks in pages).
- **UI / Components**: Custom components + Ag-Grid (`frontend/package.json`).

---

## 2) Capabilities Matrix (Evidence-Based)

> Legend: “Workflow states implemented?” refers to explicit status/state fields and transition endpoints in code. “Permissions enforced?” refers to explicit role checks or access guards in routers/services. “Automation present?” includes any background/automatic logic (reminders, reports, scheduled jobs, or idempotent automation).

| Module | Backend: models/tables, services, endpoints (file paths) | Frontend: pages/components (file paths) | Workflow states implemented? | Permissions enforced? | Automation present? | Gaps and risks |
| --- | --- | --- | --- | --- | --- | --- |
| **Document Control** | `QMSDocument`, `QMSDocumentRevision`, `QMSDocumentDistribution` models and `/quality/qms/documents` + `/revisions` + `/distributions` endpoints (`backend/amodb/apps/quality/models.py`, `backend/amodb/apps/quality/router.py`) | `QMSDocumentsPage` (`frontend/src/pages/QMSDocumentsPage.tsx`) | **Yes**: `QMSDocStatus` fields + publish endpoint (`/qms/documents/{id}/publish`) | **Partial**: module gating only; no role checks on document create/update endpoints | **Partial**: distribution acknowledgement tracking | No evidence of approval workflow or electronic sign-offs; no evidence pack export; permissions too permissive for controlled docs. |
| **Records/Retention** | `retention_until` on `QMSAudit`; `ArchivedUser` retention model (`backend/amodb/apps/quality/models.py`, `backend/amodb/models.py`) | No explicit retention UI found | **Partial**: retention fields exist, no enforcement jobs | **No** explicit enforcement | **No** retention scheduling or purge jobs found | Retention policy enforcement and record purge missing. |
| **Audit Program** | `QMSAudit` model and `/quality/audits` endpoints (`backend/amodb/apps/quality/models.py`, `backend/amodb/apps/quality/router.py`) | `QMSAuditsPage` (`frontend/src/pages/QMSAuditsPage.tsx`) | **Yes**: `QMSAuditStatus` | **No** explicit role checks for audit CRUD | **Partial**: status change sets retention date on close | No audit program scheduling automation; permissions missing. |
| **Findings** | `QMSAuditFinding` model and `/audits/{id}/findings` endpoints (`backend/amodb/apps/quality/models.py`, `backend/amodb/apps/quality/router.py`) | Findings appear embedded in audit workflow; no dedicated page found | **Yes**: level/severity fields, open/closed via `closed_at` | **No** explicit role checks for findings | **Partial**: target close date computed | No enforced evidence gating on close; no audit trail for finding changes. |
| **CAPA** | `QMSCorrectiveAction` + `CorrectiveActionRequest` (CAR) models and `/findings/{id}/cap` + `/cars` endpoints (`backend/amodb/apps/quality/models.py`, `backend/amodb/apps/quality/router.py`) | `QualityCarsPage` + `PublicCarInvitePage` (`frontend/src/pages/QualityCarsPage.tsx`, `frontend/src/pages/PublicCarInvitePage.tsx`) | **Yes**: CAP status + CAR status | **Partial**: CAR write access enforced; CAPA update lacks role checks | **Partial**: CAR reminders computed; CAR PDF generation | Evidence pack export now available; CAPA closure not gated on evidence/verification. |
| **Occurrence + Investigation** | FRACAS cases/actions (`FRACASCase`, `FRACASAction`) with create/verify/approve endpoints (`backend/amodb/apps/reliability/models.py`, `backend/amodb/apps/reliability/services.py`, `backend/amodb/apps/reliability/router.py`) | No dedicated FRACAS UI found | **Yes**: FRACAS status enums | **Partial**: module gating only; no role checks | **Partial**: notifications for reliability alerts | Missing UI; no investigation templates or automatic task creation. |
| **Trend/Monthly Review** | Reliability trends + reports (`ReliabilityDefectTrend`, reports services) (`backend/amodb/apps/reliability/models.py`, `backend/amodb/apps/reliability/services.py`) | `ReliabilityReportsPage` (`frontend/src/pages/ReliabilityReportsPage.tsx`) | **Partial**: report status in backend | **Partial**: module gating only | **Yes**: report generation endpoints | Monthly occurrence review pack not implemented as a single-click pack. |
| **Supplier Management** | Vendors exist (`backend/amodb/apps/finance/models.py`), used in POs (`backend/amodb/apps/inventory/models.py`) | No supplier management UI found | **No** supplier workflow states | **No** | **No** | Supplier approval, monitoring, and outsourcing controls missing. |
| **Outsourced Functions** | **Not found** | **Not found** | **No** | **No** | **No** | Outsourcing register and oversight missing. |
| **Stores/Inventory/Parts + Shelf-life/Quarantine** | Inventory models incl. lots with expiry and condition (`backend/amodb/apps/inventory/models.py`) | No explicit inventory UI found | **Partial**: inventory movement conditions | **Partial**: module gating only | **No** shelf-life automation | Shelf-life/quarantine automation missing. |
| **Calibration + Concessions** | **Not found** (no calibration models/endpoints) | **Not found** | **No** | **No** | **No** | Calibration register, due list, and concessions missing. |
| **Training** | Training models, requirements, notifications (`backend/amodb/apps/training/models.py`, `backend/amodb/apps/training/router.py`) | `QMSTrainingPage`, `QMSTrainingUserPage`, `MyTrainingPage` (`frontend/src/pages/QMSTrainingPage.tsx`, `frontend/src/pages/QMSTrainingUserPage.tsx`, `frontend/src/pages/MyTrainingPage.tsx`) | **Yes**: training event + participant statuses | **Partial**: module gating only | **Yes**: in-app notifications | Annual update rules exist via recurrence fields, but no enforcement or escalation jobs. |
| **Authorizations** | **Not found** | **Not found** | **No** | **No** | **No** | Authorization/privilege register missing. |
| **Stamp Register/Quarantine** | CRS stamp fields (`backend/amodb/apps/crs/models.py`) | No dedicated stamp control UI found | **Partial**: stamp fields exist | **No** | **No** | No controlled stamp register with issuance/return/quarantine workflow. |
| **Exemptions/Deviations/Concessions** | **Not found** | **Not found** | **No** | **No** | **No** | No exemptions/deviations/concessions workflow. |
| **Management Review** | **Not found** | **Not found** | **No** | **No** | **No** | Management review records/actions missing. |
| **Task Engine** | Task model + escalation runner (`backend/amodb/apps/tasks`, `backend/amodb/jobs/qms_task_runner.py`) | Task list page (`frontend/src/pages/MyTasksPage.tsx`) | **Yes**: task statuses | **Partial**: role-gated admin list; owner controls | **Yes**: reminders + escalation runner | Task automation limited to QMS/FRACAS/training hooks. |
| **Notifications/Email Logging** | Email log model + service + admin API (`backend/amodb/apps/notifications/models.py`, `backend/amodb/apps/notifications/service.py`, `backend/amodb/apps/notifications/router.py`), in-app notifications for QMS/reliability/training | Email logs admin page (`frontend/src/pages/EmailLogsPage.tsx`) | **Partial**: read-only email log + in-app read/unread states | **Yes**: admin/QA role gate for email logs | **Partial**: email logging for task reminders/escalations | Provider abstraction defaults to no-op; outbound provider integration still needed. |
| **Evidence Packs/Exports** | Evidence pack ZIP export service for audits/CAR/FRACAS/training (`backend/amodb/apps/exports/evidence_pack.py`, new evidence-pack endpoints in `backend/amodb/apps/quality/router.py`, `backend/amodb/apps/reliability/router.py`, `backend/amodb/apps/training/router.py`) | Evidence pack actions in `QMSAuditsPage`, `QualityCarsPage`, `QMSTrainingUserPage`, `ReliabilityReportsPage` (`frontend/src/pages/*`) | **Yes**: ZIP packs + CAR PDF | **Yes**: role-gated exports | **Partial**: CAR PDF + ZIP packs | Evidence packs now available; ensure size limits align with deployment storage constraints. |

---

## 3) Workflow Controls Audit (per workflow requirement)

Below, each requirement is marked as **Present** only if explicit code exists.

### Update: Workflow Gating Implemented (P0 #2)
- Workflow transitions now enforce required-field gating for document publish approvals, audit closure (all findings closed), finding closure (evidence + verification), CAPA closure (actions + evidence + verification), FRACAS verify/approve, and training event/participant status transitions. 
- Transition attempts that fail requirements return structured 400 errors with missing fields and log to the immutable audit_events timeline.

### Document Control
- **State machine / lifecycle**: **Present** (`QMSDocStatus` in `QMSDocument`).
- **Due dates and escalation**: **Missing** (no reminder/escalation jobs).
- **Required fields gating**: **Present** (publish requires approval metadata).
- **Immutable audit trail**: **Partial** (transition events logged).
- **Attachment/evidence support**: **Partial** (`current_file_ref` only; no upload service).
- **Exportable evidence pack**: **Missing**.

### Audit Program / Findings / CAPA
- **State machine / lifecycle**: **Present** (audit status; CAP status; CAR status).
- **Due dates and escalation**: **Partial** (finding target dates; CAR reminders, but no scheduling service).
- **Required fields gating**: **Present** (audit/finding/CAPA close gates).
- **Immutable audit trail**: **Partial** (transition events logged; other actions not yet covered).
- **Attachment/evidence support**: **Partial** (CAR attachments only).
- **Exportable evidence pack**: **Present** (ZIP evidence packs + CAR PDF).

### Occurrence / Investigation (FRACAS)
- **State machine / lifecycle**: **Present** (FRACAS statuses).
- **Due dates and escalation**: **Partial** (action due dates, no escalation service).
- **Required fields gating**: **Missing**.
- **Immutable audit trail**: **Partial** (transition events logged).
- **Attachment/evidence support**: **Missing**.
- **Exportable evidence pack**: **Present** (ZIP evidence packs).

### Training
- **State machine / lifecycle**: **Present** (training event/participant statuses).
- **Due dates and escalation**: **Partial** (recurrence, no automated escalation jobs).
- **Required fields gating**: **Partial** (attendance status requires verification stamps).
- **Immutable audit trail**: **Partial** (transition events logged; other actions not yet covered).
- **Attachment/evidence support**: **Partial** (training files exist but no export pack).
- **Exportable evidence pack**: **Present** (ZIP evidence packs).

### Inventory / Stores
- **State machine / lifecycle**: **Partial** (conditions and movement types).
- **Due dates and escalation**: **Missing** (no shelf-life automation).
- **Required fields gating**: **Missing**.
- **Immutable audit trail**: **Missing**.
- **Attachment/evidence support**: **Missing**.
- **Exportable evidence pack**: **Missing**.

---

## 4) Missing Items and Risks

### Compliance-critical (P0)
- **Audit trail** now logs workflow transitions for QMS/FRACAS/training; coverage remains partial for non-transition actions.
- **Workflow engine** now enforces state transitions and required-field gating for key QMS/FRACAS/training flows.
- **Task engine** now provides due-date reminders and escalation runner for QMS/FRACAS/training tasks.
- Email logging exists for task reminders/escalations, but external email provider integration is still pending.
- Evidence pack exports now cover audits, CARs, FRACAS cases, and training users; calibration/stores still missing.
- Missing **calibration register** and **concessions** workflow.
- Missing **management review** module and action tracking.
- Missing **exemptions/deviations/concessions** workflow.

### Efficiency improvements (P1/P2)
- No single-click workflow actions (CAPA from finding, close finding with evidence, publish revision + notify).
- No reliability monthly review pack generator.
- No shelf-life control automation or quarantine actions.
- No calibration due list generation/distribution.

---

## 5) Prioritized Backlog (High-Level)

> Detailed acceptance criteria are in BACKLOG.md.

- **P0**: Audit log foundation; workflow engine; task engine; notification/email logging; evidence pack service.
- **P1**: Single-click workflow automation (CAPA, finding close, doc publish/notify, investigation start, monthly review pack, calibration due list, shelf-life control).
- **P2**: Expand to supplier/outsourcing, management review, exemptions/deviations, calibration register UI.

---

## 6) Current vs Target Workflows (Top 5)

### A) Audit → Finding → CAPA → Close
**Current**
```
Audit (PLANNED/IN_PROGRESS)
  └─ Finding created (target_close_date auto)
     └─ CAPA via /findings/{id}/cap (status updates allowed)
        └─ Manual close (no evidence gating)
```
**Target**
```
Audit (PLANNED → IN_PROGRESS → CAP_OPEN → CLOSED)
  └─ Finding created → evidence required
     └─ CAPA created with tasks + due dates
        └─ Verification step required
           └─ Close gated by evidence + verification + approvals
```

### B) Document Control → Publish Revision → Distribute
**Current**
```
Document DRAFT → Revision created → Publish (ACTIVE)
  └─ Distribution records added (acks tracked)
```
**Target**
```
Document DRAFT → Review → Approve → Publish Revision
  └─ Auto-distribute + request acknowledgements
  └─ Supersede previous revision + lock edits
  └─ Evidence pack export
```

### C) Occurrence/FRACAS → Investigation → Actions
**Current**
```
FRACAS case OPEN → actions created → verify/approve
```
**Target**
```
Occurrence reported → Investigation task auto-created
  └─ Root cause required → CAPA/task plan
  └─ Verification/closure gating + evidence pack
```

### D) Training → Annual Update
**Current**
```
Course + events + participant statuses; notifications
```
**Target**
```
Annual/recurrent training engine auto-creates events + tasks
  └─ Escalations and overdue reporting
  └─ Evidence pack per staff member
```

### E) Inventory Shelf-Life / Quarantine
**Current**
```
Lots have expiry_date; no automation
```
**Target**
```
Monthly shelf-life job → expiring list
  └─ Auto-quarantine movements + procurement tasks
  └─ Evidence pack for controls
```

## Changed in this run (2026-02-10)
- **Files changed:**
  - `frontend/src/components/Layout/DepartmentLayout.tsx`
  - `frontend/src/components/realtime/RealtimeProvider.tsx`
  - `frontend/src/components/realtime/LiveStatusIndicator.tsx`
  - `frontend/src/components/dashboard/DashboardScaffold.tsx`
  - `frontend/src/dashboards/DashboardCockpit.tsx`
  - `frontend/src/styles/components/app-shell.css`
  - `frontend/src/styles/components/dashboard-cockpit.css`
- **Resolved findings:**
  - Focus-mode discoverability improved with keyboard shortcut (`Ctrl/⌘ + \`) and edge-peek launcher on cockpit pages.
  - Realtime stale-state UX added (stale indicator + targeted manual refresh button without full-page reload).
  - Cockpit KPI drilldowns now map to specific route + query filters for all visible tiles.
- **New findings:**
  - **P1 / Frontend owner:** Activity feed virtualization still missing (action queue is virtualized; feed remains static list).
  - **P1 / Backend owner:** user-management action endpoints required by command center (disable/enable/revoke/reset) still incomplete for cockpit workflows.
  - **P2 / Frontend owner:** cursor halo/magnetic interaction layer not implemented yet.
- **Commands run:** `npx tsc -b`, `npm run dev -- --host 0.0.0.0 --port 4173`, Playwright screenshot script.
- **Verification:**
  1. Open cockpit route with `VITE_UI_SHELL_V2=1`.
  2. Confirm sidebar is hidden by default (focus mode).
  3. Use edge-peek and `Ctrl/⌘ + \` to reveal module launcher.
  4. Force realtime disconnect and verify stale menu messaging + refresh action.
- **Known issues:** full cockpit “command center” backend action parity is still in-progress.
- **Screenshots:** `browser:/tmp/codex_browser_invocations/19aa7325a4460d99/artifacts/artifacts/cockpit-shell-updates.png`

### Next phase priorities
1. Add user action endpoints (disable/enable/revoke/reset/notify/schedule) with RBAC + audit + SSE.
2. Virtualize activity feed and add lazy-loaded charts with idle prefetch.
3. Implement attachment hardening regression tests across all evidence upload surfaces.
