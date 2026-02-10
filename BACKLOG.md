# QMS/MPM Backlog (Prioritized)

> This backlog is evidence-based from AUDIT_REPORT.md and aligned to the required QMS/MPM scope. Acceptance criteria are designed to be testable and incremental.

## P0 — Compliance-Critical

### [x] 1) Audit Log Foundation (immutable event log)
**Goal**: Provide immutable event logging across QMS/MPM records.

**Acceptance Criteria**
- Add a shared audit log writer that appends to `audit_events` with before/after values and correlation IDs.
- All changes to: QMS documents, revisions, distributions; audits; findings; CAPA/CAR; training records; FRACAS cases/actions; inventory movements are logged.
- Audit log is read-only in the UI; no delete/update endpoints.
- Tests: unit tests for log creation; integration tests verifying audit events on key flows.

### [x] 2) Workflow Engine (generic state + transition guards)
**Goal**: Enforce lifecycle rules and required-field gating.

**Acceptance Criteria**
- A shared workflow configuration model with allowed transitions + guard checks.
- For audits, findings, CAPA, FRACAS, training events: transitions are blocked if required fields are missing (evidence, verification, approvals).
- A clear error response for invalid transitions.
- Tests: unit tests for transition matrix and guard behavior.

### [x] 3) Task Engine (due dates + escalation)
**Goal**: Centralized tasks with due dates and escalation.

**Acceptance Criteria**
- Task model (owner, status, due date, escalation thresholds, record links).
- Auto-task creation on audit/finding/CAPA/investigation creation.
- Overdue escalation rules (notify owner → supervisor → QA).
- Tests: task generation and escalation logic.

### [x] 4) Notification Service + Email Logging
**Goal**: Notifications with email logs for compliance evidence.

**Acceptance Criteria**
- Outbound email service abstraction + retry handling.
- Email log table (recipient, subject, template, status, error, timestamps).
- Integration with task engine to send reminders.
- Tests: notification triggers and logging.

### [x] 5) Evidence Pack Export (PDF/ZIP)
**Goal**: Evidence packs per record type.

**Acceptance Criteria**
- Export service that gathers timeline/history, approvals, attachments, linked records into a ZIP/PDF bundle.
- Evidence pack endpoints for audits, CAPA/CAR, FRACAS cases, training records.
- Tests: export includes required evidence and audit log timeline.

### 6) Calibration Register + Concessions
**Goal**: Provide calibration register and concession workflows.

**Acceptance Criteria**
- Calibration assets model + due dates + calibration history.
- “Calibration due list” endpoint and export.
- Concessions captured with approvals and audit trail.
- Tests: due list generation and permissions.

### 7) Management Review + Action Tracking
**Goal**: Management review records, actions, and evidence.

**Acceptance Criteria**
- Management review meeting model with agenda, attendees, decisions, actions.
- Action tracking integrates with task engine.
- Evidence pack export for management reviews.
- Tests: action creation and audit log capture.

---

## P1 — High-Impact UX Automation (Single-Click)

### 8) One-click “Create CAPA from Finding”
**Acceptance Criteria**
- Button on finding view that creates a CAPA, links finding, assigns owner, creates tasks, and opens CAPA form prefilled.
- Idempotent backend action (same finding cannot create duplicates).
- Audit log records the action.

### 9) One-click “Close Finding” (evidence + verification gating)
**Acceptance Criteria**
- Close action only enabled if evidence uploaded + verification completed.
- Audit log records closure.

### 10) One-click “Publish Revision + Notify Distribution”
**Acceptance Criteria**
- Locks revision, sets document current version, marks prior revision superseded, sends distribution requests, logs notifications.
- Audit log and email log entries.

### 11) One-click “Start Investigation” (from occurrence/FRACAS)
**Acceptance Criteria**
- Creates investigation task with scope/objective template and reminders.
- Links to FRACAS case.

### 12) One-click “Generate Monthly Occurrence Review Pack”
**Acceptance Criteria**
- Generates reliability trend report + action list + evidence pack.
- Stores export with audit trail and notification.

### 13) One-click “Generate Calibration Due List + Send”
**Acceptance Criteria**
- Generates due list; sends distribution; logs email.

### 14) One-click “Run Shelf-life Control”
**Acceptance Criteria**
- Generates monthly expiry report; quarantines expiring items; creates procurement tasks.
- Audit log captures actions.

---

## P2 — Coverage Expansion

### 15) Supplier & Outsourcing Controls
**Acceptance Criteria**
- Supplier register with approval status, audit dates, and risk scoring.
- Outsourced function register + oversight tasks.

### 16) Exemptions/Deviations/Concessions
**Acceptance Criteria**
- Record type with lifecycle, approvals, and audit trail.
- Evidence pack export.

### 17) Records Retention Enforcement
**Acceptance Criteria**
- Retention schedules applied to QMS records with automated archival/purge workflows.
- Audit log entries for retention events.


## Changed in this run (2026-02-10)
- **Task realtime gap**: Increment completed toward P0/P1 operational loop.
  - Evidence: task lifecycle actions now emit normalized SSE-compatible events via audit (`backend/amodb/apps/tasks/services.py`), and frontend invalidates tasks/cockpit aggregate keys (`frontend/src/components/realtime/RealtimeProvider.tsx`).
- **Evidence upload hardening**: partial progress on compliance gating.
  - Evidence: CAR attachment hardening + Action Panel evidence controls (`backend/amodb/apps/quality/router.py`, `frontend/src/components/panels/ActionPanel.tsx`).
- **Security controls**: partial closure of top gaps.
  - Evidence: production secret guard + auth endpoint rate limiting (`backend/amodb/security.py`, `backend/amodb/apps/accounts/router_public.py`).

## Changed in this run (2026-02-10)
- **Files changed:**
  - `frontend/src/components/Layout/DepartmentLayout.tsx`
  - `frontend/src/components/realtime/RealtimeProvider.tsx`
  - `frontend/src/components/realtime/LiveStatusIndicator.tsx`
  - `frontend/src/components/dashboard/DashboardScaffold.tsx`
  - `frontend/src/dashboards/DashboardCockpit.tsx`
- **P0 (active):**
  - Implement backend user command actions (disable/enable/revoke/reset password/notify/schedule) with RBAC + audit + SSE emit.
  - Acceptance: every cockpit user drilldown action available and realtime-updating.
- **P1 (active):**
  - Virtualize cockpit activity feed and add targeted entity drilldowns for remaining entity types.
  - Acceptance: feed supports >1000 rows with smooth scroll and deterministic routing.
- **P1 (new):**
  - Add cursor halo/magnetic effect with reduced-motion and touch-device guards.
  - Acceptance: 60fps on desktop, auto-disabled on reduced-motion/touch.
- **P2 (moved):**
  - Expand chart set (2–4 per cockpit) with lazy-load + idle prefetch.
- **Commands run:** `npx tsc -b`
- **Verification:** cockpit focus mode + realtime stale refresh + KPI drilldowns.
- **Known issues:** activity feed virtualization pending.
- **Screenshots:** `browser:/tmp/codex_browser_invocations/19aa7325a4460d99/artifacts/artifacts/cockpit-shell-updates.png`
