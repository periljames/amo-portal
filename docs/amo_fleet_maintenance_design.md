
# AMO Portal – Fleet & Maintenance Planning Module Design

**Version:** 0.1 (Draft)  
**Date:** 2025‑11‑26  
**Owner:** James / XLK – AMO Portal  
**Stack:** FastAPI (Python), SQLAlchemy, PostgreSQL, React + TypeScript frontend

---

## 1. Purpose

This document defines the technical design for the **Fleet & Maintenance Planning** module in the AMO Portal. It translates the existing Excel‑based aircraft tracking (hours, cycles, components, logbooks) into a multi‑user web application that:

- Tracks aircraft hours, cycles, and utilisation events.
- Tracks major components (engines, props, etc.) and life limits.
- Supports work orders, task cards, assignments and work logs.
- Enables Planning and Production supervisors to allocate work per user.
- Provides collaboration, auditability, and role‑based access control.
- Aligns the data model with industry standards (ATA Spec 2000 / reliability data) and allows clean exports.

This document is a reference for backend and frontend implementation and for future AI‑generated code scaffolding.

---

## 2. Scope

**In scope:**

- Fleet data model: aircraft, usage (hours/cycles), components, maintenance program status.
- Planning & execution data model: work orders, task cards, assignments, work logs.
- Collaboration features: audit log, basic notifications, comments.
- Permissions for SUPERUSER, AMO_ADMIN, Planning and Production roles.
- High‑level API design (not every single endpoint yet).
- Frontend page structure (tabs/views) mirroring the existing Excel workflows.
- Export strategy for CSV/Excel and future Spec 2000‑style reliability exports.

**Out of scope (for this version):**

- Detailed UI/UX design (pixel‑perfect layouts).
- Full Spec 2000 message implementation.
- Integration with external MRO/ERP systems.
- Real‑time WebSocket collaboration.

---

## 3. Roles and Permissions

Roles are defined in the existing `AccountRole` enum (backend) and mirrored in the frontend. Key roles for this module:

- `SUPERUSER`
- `AMO_ADMIN`
- `PLANNING_ENGINEER`
- `PRODUCTION_ENGINEER`
- `CERTIFYING_ENGINEER`
- `CERTIFYING_TECHNICIAN`
- `TECHNICIAN`
- `VIEW_ONLY`

High‑level permission matrix for the Fleet & Maintenance Planning module:

- **SUPERUSER / AMO_ADMIN**
  - Full CRUD on aircraft, usage entries, components, maintenance program, work orders, tasks, assignments.
  - Configure standards, thresholds, codes (ATA chapters, reason codes).
- **PLANNING_ENGINEER / PRODUCTION_ENGINEER**
  - Create and update aircraft usage entries.
  - Manage components (install/remove/update life limits).
  - Create and manage work orders and task cards.
  - Assign tasks to users and adjust planning dates.
- **CERTIFYING_ENGINEER / CERTIFYING_TECHNICIAN / TECHNICIAN**
  - Read aircraft, usage, components, and their own tasks.
  - Update the status of tasks assigned to them.
  - Create work logs (time booked) and comments.
- **VIEW_ONLY**
  - Read‑only access to fleet, hours/cycles, components, work orders and tasks.

Permission enforcement will be done via FastAPI dependencies reusing the existing authentication and role‑check helpers (e.g. `get_current_active_user`, `require_roles`).

---

## 4. Domain Model

This section describes the main entities and how they relate. Existing models (`Aircraft`, `AircraftComponent`, `WorkOrder`) are extended with new models for usage, tasks, and collaboration.

### 4.1 Aircraft (existing)

Table: `aircraft` (already implemented)

Key fields (simplified):

- `serial_number` (PK, string) – internal aircraft identity, matches WinAir serial where possible.
- `registration` (unique, string).
- `template`, `make`, `model`, `home_base`, `owner`.
- `status` (e.g. OPEN, CLOSED).
- `is_active` (soft delete).
- `last_log_date`, `total_hours`, `total_cycles` – snapshot values.
- Timestamps: `created_at`, `updated_at`.

Relationships:

- `work_orders` → many `WorkOrder` records (via existing work module).
- `crs_list` → many CRS records.
- `components` → many `AircraftComponent`.
- `usage_entries` → many `AircraftUsage` (new; see below).

### 4.2 AircraftUsage (new)

Represents **daily utilisation / techlog entries** for each aircraft, equivalent to the Excel HOURS tab.

Table: `aircraft_usage`

Fields:

- `id` (PK, integer).
- `aircraft_serial_number` (FK → `aircraft.serial_number`, required).
- `date` (date, required).
- `techlog_no` (string, required).
- `station` (string, optional; ICAO or IATA code for base/station).
- `block_hours` (float, required) – total time added for the period.
- `cycles` (float or integer, required).
- Snapshot fields (optional but useful for fast reporting):
  - `ttaf_after` (float) – total time airframe after this entry.
  - `tca_after` (float) – total cycles airframe after this entry.
  - `ttesn_after`, `tcesn_after`, `ttsoh_after` – engine/prop totals if needed.
- `remarks` (text, optional) – brief description or notes.

Audit fields:

- `created_at`, `updated_at` (timestamps).
- `created_by_user_id`, `updated_by_user_id` (FK → accounts table).

Constraints:

- Unique `(aircraft_serial_number, date, techlog_no)` to prevent duplicate entries.
- Indexes on `aircraft_serial_number`, `date` for fast range queries.

Usage: All logbook/report and forecasting views will derive from this table, rather than storing usage only as static totals.

### 4.3 AircraftComponent (existing, extended)

Table: `aircraft_components` (already implemented)

Existing fields:

- `id` (PK).
- `aircraft_serial_number` (FK → `aircraft.serial_number`).
- `position` (e.g. L ENGINE, R ENGINE, APU, PROP LH).
- `ata`, `part_number`, `serial_number`, `description`.
- `installed_date`, `installed_hours`, `installed_cycles`.
- `current_hours`, `current_cycles`.
- `notes`.

Extensions for life limits and standards alignment:

- Life limit configuration:
  - `tbo_hours`, `tbo_cycles`, `tbo_calendar_months` – Time Between Overhaul.
  - `hsi_hours`, `hsi_cycles`, `hsi_calendar_months` – Hot Section Inspection (if applicable).
- Overhaul / inspection reference:
  - `last_overhaul_date`, `last_overhaul_hours`, `last_overhaul_cycles`.
- Standardised reliability fields (for Spec 2000 mapping):
  - `manufacturer_code` (string).
  - `operator_code` (string; airline/AMO code).
  - `unit_of_measure_hours` (default "H"), `unit_of_measure_cycles` (default "C").

Business rules:

- Validation to avoid overlapping installations: one component position per aircraft should not have two active records at the same time.
- For major positions (engines, props), enforce uniqueness via either a `position` constraint or an `is_active` flag.

### 4.4 MaintenanceProgramItem (new, template‑level)

Represents **maintenance program tasks** (checks, ADs, SBs, hard time items) for a given aircraft template (type).

Table: `maintenance_program_items`

Fields:

- `id` (PK).
- `aircraft_template` (string, e.g. C208B, DASH8‑315).
- `ata_chapter` (string, e.g. "05‑21", "27‑10").
- `task_code` (string; manufacturer or internal task ID).
- `category` (enum: AIRFRAME, ENGINE, PROP, AD, SB, HT, OTHER).
- `description` (text).
- Intervals:
  - `interval_hours` (float, nullable).
  - `interval_cycles` (float, nullable).
  - `interval_days` (integer, nullable).
- `is_mandatory` (boolean).

Use: This is the template; specific aircraft status is tracked in `MaintenanceStatus`.

### 4.5 MaintenanceStatus (new, aircraft‑level)

Tracks **last done / next due** for each MaintenanceProgramItem on a specific aircraft.

Table: `maintenance_status`

Fields:

- `id` (PK).
- `aircraft_serial_number` (FK → `aircraft`).
- `program_item_id` (FK → `maintenance_program_items`).
- Last done:
  - `last_done_date` (date).
  - `last_done_hours` (float).
  - `last_done_cycles` (float).
- Next due:
  - `next_due_date` (date).
  - `next_due_hours` (float).
  - `next_due_cycles` (float).
- Derived remaining values (optional denormalisation for performance):
  - `remaining_days` (integer).
  - `remaining_hours` (float).
  - `remaining_cycles` (float).

These fields can be recalculated whenever new `AircraftUsage` entries are added.

### 4.6 WorkOrder (existing)

Assumed to exist in `apps.work.models`. This document assumes:

- `WorkOrder` is linked to `Aircraft` via `aircraft_serial_number` or a FK to `aircraft.id`.
- Has fields such as `wo_number`, `type` (Periodic, Unscheduled, Mod), `status`, `opened_at`, `closed_at`.

Work orders are the parent container for specific tasks (TaskCards).

### 4.7 TaskCard (new)

Represents a specific **task** to be performed under a work order, assignable to users.

Table: `task_cards`

Fields:

- `id` (PK).
- `work_order_id` (FK → `work_orders`).
- `aircraft_serial_number` (FK → `aircraft.serial_number`).
- `aircraft_component_id` (FK → `aircraft_components.id`, nullable).
- `program_item_id` (FK → `maintenance_program_items.id`, nullable).
- `ata_chapter` (string).
- `task_code` (string, optional; override or additional identifier).
- `title` (string).
- `description` (text).
- `category` (enum: SCHEDULED, UNSCHEDULED, DEFECT, MODIFICATION).
- `priority` (enum: CRITICAL, HIGH, MEDIUM, LOW).
- Planning fields:
  - `planned_start` (datetime, nullable).
  - `planned_end` (datetime, nullable).
  - `estimated_manhours` (float, nullable).
- Execution fields:
  - `status` (enum: PLANNED, IN_PROGRESS, PAUSED, COMPLETED, DEFERRED, CANCELLED).
  - `actual_start` (datetime, nullable).
  - `actual_end` (datetime, nullable).
- Metadata:
  - `created_at`, `updated_at`.
  - `created_by_user_id`, `updated_by_user_id`.

Constraints:

- Optional uniqueness on `(work_order_id, task_code)` to prevent duplicate card numbers.

### 4.8 TaskAssignment (new)

Links TaskCards to users and controls who is responsible.

Table: `task_assignments`

Fields:

- `id` (PK).
- `task_id` (FK → `task_cards.id`).
- `user_id` (FK → accounts/users table).
- `role_on_task` (enum: LEAD, SUPPORT, INSPECTOR).
- `allocated_hours` (float, nullable).
- `status` (enum: ASSIGNED, ACCEPTED, REJECTED, COMPLETED).
- `created_at`, `updated_at`.

Usage: Planning / Production supervisors assign tasks to specific users; engineers see "My Tasks" based on this table.

### 4.9 WorkLogEntry (new)

Represents time booked against a TaskCard by a user.

Table: `work_logs`

Fields:

- `id` (PK).
- `task_id` (FK → `task_cards.id`).
- `user_id` (FK → accounts/users).
- `start_time` (datetime).
- `end_time` (datetime).
- `actual_hours` (float; can be derived from `end_time - start_time`).
- `description` (text; brief description of work performed).
- `station` (string, optional).
- `created_at`, `updated_at`.

Usage: Feeds planning calendars and productivity reporting; also supports auditing of work and potentially cost calculations.

### 4.10 ReliabilityEvent (new)

Captures events relevant to reliability and Spec 2000‑style exports (e.g. component removal, installation, defect, delay).

Table: `reliability_events`

Fields:

- `id` (PK).
- `aircraft_serial_number` (FK → `aircraft`).
- `aircraft_component_id` (FK → `aircraft_components`, nullable).
- `event_date` (date).
- `event_type` (enum: REMOVAL, INSTALLATION, DEFECT, DELAY, CANCELLATION, OTHER).
- `reason_code` (string; mapped to standard codes).
- Snapshot of part data at event time:
  - `part_number`, `serial_number`, `position`.
  - `manufacturer_code`, `operator_code`.
- Snapshot of time/cycles:
  - `tsn_hours`, `tsn_cycles`.
  - `tso_hours`, `tso_cycles`.
- Link to work structures:
  - `work_order_id` (FK, nullable).
  - `task_id` (FK → `task_cards.id`, nullable).
- `remarks` (text).
- `created_at`, `created_by_user_id`.

These records are the basis for reliability exports and can be generated automatically, for example when a component is removed or replaced.

### 4.11 ActivityLog (new)

Generic audit trail: “who changed what, when”.

Table: `activity_logs`

Fields:

- `id` (PK).
- `entity_type` (string; e.g. "Aircraft", "AircraftUsage", "TaskCard").
- `entity_id` (string/int; primary key value of the entity).
- `user_id` (FK → accounts/users).
- `action` (string; CREATED, UPDATED, DELETED, STATUS_CHANGED, ASSIGNED, COMMENTED).
- `timestamp` (datetime).
- `diff` (JSONB; optional; before/after values).

Backend will add entries for key operations to allow traceability and debugging.

### 4.12 Notification (new)

Simple in‑app notifications for events like task assignment, status changes, or upcoming due items.

Table: `notifications`

Fields:

- `id` (PK).
- `recipient_user_id` (FK).
- `notification_type` (string; TASK_ASSIGNED, DUE_SOON, OVERDUE, SYSTEM).
- `title` (string).
- `body` (text).
- `related_entity_type` (string; e.g. "TaskCard", "Aircraft").
- `related_entity_id` (string/int).
- `is_read` (boolean).
- `created_at`, `read_at` (nullable).

---

## 5. API Design (High‑Level)

The module will reuse and extend the existing `fleet` and `work` FastAPI routers.

### 5.1 Fleet Router (`apps.fleet.router`)

Existing endpoints:

- `GET /aircraft/` – list aircraft.
- `GET /aircraft/{serial_number}` – get aircraft.
- `POST /aircraft/` – create aircraft.
- `PUT /aircraft/{serial_number}` – update aircraft.
- `DELETE /aircraft/{serial_number}` – deactivate (soft delete).
- `GET /aircraft/{serial_number}/components` – list components.
- `POST /aircraft/{serial_number}/components` – create component.
- `PUT /aircraft/components/{component_id}` – update component.
- `DELETE /aircraft/components/{component_id}` – delete component.
- Bulk import endpoints for aircraft and components.

Planned additions:

- `GET /aircraft/{serial_number}/usage`  
  List usage entries with filters: `skip`, `limit`, `start_date`, `end_date`.
- `POST /aircraft/{serial_number}/usage`  
  Create a new `AircraftUsage` entry.
- `PUT /aircraft/usage/{usage_id}`  
  Update an existing usage entry.
- `DELETE /aircraft/usage/{usage_id}`  
  Delete or deactivate a usage entry (configurable).

- `GET /aircraft/{serial_number}/maintenance-status`  
  List `MaintenanceStatus` items (program tasks with last done / next due).
- `GET /fleet/alerts`  
  Returns aircraft/components/tasks that are due soon or overdue based on thresholds (`hours_threshold`, `days_threshold`).

All write endpoints will be protected by role checks (Planning / Production / Admin only).

### 5.2 Work Router Extensions (`apps.work`)

Planned:

- `GET /work-orders` – list work orders (filters by aircraft, status, base).
- `POST /work-orders` – create work order (Planning / Production only).
- `GET /work-orders/{id}` – work order details.
- `PUT /work-orders/{id}` – update.
- `GET /work-orders/{id}/tasks` – list TaskCards under a work order.

TaskCard endpoints:

- `POST /work-orders/{id}/tasks` – create task.
- `GET /tasks/{task_id}` – get task detail.
- `PUT /tasks/{task_id}` – update task (status, planning dates, etc.).
- `DELETE /tasks/{task_id}` – cancel task (subject to business rules).

Assignments and work logs:

- `POST /tasks/{task_id}/assignments` – create assignment (Planning / Production).
- `GET /tasks/{task_id}/assignments` – list assignments.
- `POST /tasks/{task_id}/work-logs` – create work log (assigned users).
- `GET /tasks/{task_id}/work-logs` – list work logs.

Reliability:

- `GET /aircraft/{serial_number}/reliability-events` – list reliability events.
- `POST /reliability-events` – create event (may also be auto‑generated from component changes).

Notification and activity log views will be added as read‑only endpoints for the frontend.

---

## 6. Frontend Page Structure

The frontend will mirror the Excel workflows but in a multi‑tab, multi‑panel layout.

### 6.1 Fleet Overview Page

Route: `/fleet`

Features:

- Table of aircraft (reg, serial, type, base, status, total hours/cycles, next check due, alert indicators).
- Filters by base, status, template, “due within X hours/days”.
- Action buttons (depending on role): view, edit, open aircraft dashboard.

### 6.2 Aircraft Dashboard

Route: `/fleet/:serial`

Tabs:

1. **Summary**
   - Identity (registration, serial, owner, base).
   - Key totals: TTAF, TCA, TTESN, TCESN, TTSOH.
   - Next scheduled check and remaining hours/days.
   - Top upcoming maintenance items and alerts.

2. **Hours & Cycles**
   - Excel‑style grid of 60 rows per page.
   - Columns: Date, Techlog No, Station, Hours, Cycles, Totals after entry, Hrs to MX, Days to MX.
   - Filters by date range, techlog no.
   - Inline add/edit, with duplicate detection.

3. **Components**
   - List of positions (L ENGINE, R ENGINE, PROP LH, etc.).
   - Columns: PN, SN, TSN, CSN, TSO, CSO, TBO/HSI, remaining hours/cycles/days.
   - Visual alerts for due soon/overdue.

4. **Maintenance Program / Status**
   - Table derived from `MaintenanceProgramItem` + `MaintenanceStatus`.
   - Shows last done, next due and remaining values for each task.

5. **Work Orders**
   - List of work orders for this aircraft with status, type, opened/closed dates.
   - Quick link into a specific work order.

6. **Reliability**
   - List of reliability events for the aircraft (removals, defects, delays).
   - Export options.

### 6.3 Planning Board & Calendar

Route: `/planning`

Views:

- **Board view** – Kanban of tasks by status (Planned, In Progress, Completed).
- **Calendar view** – tasks laid out by planned start/end; filters by aircraft, base and user.
- **My Schedule** – per‑user view showing assigned tasks and booked hours.

### 6.4 My Tasks

Route: `/my-tasks`

For engineers and technicians:

- List of tasks assigned to the logged‑in user.
- Quick update of status (start, pause, complete).
- Quick logging of work (start/stop timer or manual entry).

---

## 7. Collaboration & Concurrency Strategy

To support many users working on the same aircraft and work orders:

1. **Unique constraints**
   - Prevent duplicate `AircraftUsage` entries per `aircraft_serial_number` + `date` + `techlog_no`.
   - Prevent duplicate task codes per work order.
   - Prevent overlapping active component positions.

2. **Optimistic locking**
   - Include `updated_at` (or a `version` field) in all critical tables: `Aircraft`, `AircraftUsage`, `AircraftComponent`, `TaskCard`, `WorkOrder`.
   - API updates require a matching `updated_at` from the client; otherwise return HTTP 409 with a concurrency error.

3. **Soft locks (optional enhancement)**
   - When a user opens a TaskCard for edit, store an `editing_user_id` + `editing_started_at` for short‑lived locks and show a UI warning to other users.

4. **Activity logs**
   - All important changes (status changes, assignment changes, usage edits) write to `activity_logs`, so supervisors can see who did what.

5. **Comments**
   - Extend TaskCard and WorkOrder models with a simple comments thread to separate chat from core fields.

---

## 8. Standards Alignment (ATA Spec 2000 – Reliability Focus)

The design aims to make it straightforward later to produce ATA Spec 2000‑style reliability exports by:

- Maintaining **reliability events** with clear event types (removal, installation, defect, delay).
- Storing **standardised data elements** for part numbers, manufacturer codes, operator codes, and time/cycle values (TSN, TSO, CSN, CSO).
- Keeping **aircraft and component master data** normalised so that exports can be built as views or ETL processes without cleaning Excel sheets.

The application will not attempt to fully implement all Spec 2000 messages in the first phase, but the database schema and naming will make that future work simpler.

---

## 9. Export and Data Migration

To support data migration and reporting:

1. **CSV / Excel exports**
   - Usage: export `AircraftUsage` per aircraft/date range, matching current Excel layout.
   - Components: export component lists including TSN/TSO, remaining values and life limits.
   - Maintenance program/status: export program tasks and their current status.

2. **ASCII / structured exports**
   - For reliability events, eventually provide a Spec‑style ASCII file compatible with external analysis tools.
   - File naming and record formats can follow a standard convention (`operator` + period + revision).

3. **Bulk import**
   - Keep and refine existing bulk import endpoints for aircraft and components.
   - Add bulk import for `AircraftUsage` to support historical migration from Excel.

---

## 10. Security and Audit

Security will reuse the existing AMO Portal authentication and token system.

Key points:

- All write operations guarded by role checks with clear minimum roles.
- All endpoints require authentication except specific public health checks.
- `activity_logs` provide traceability.
- Optional IP/station tagging for work logs and usage entries (later).

---

## 11. Implementation Roadmap (Phased)

**Phase 1 – Core Fleet + Usage**

- Implement `AircraftUsage` model, routes and frontend Hours & Cycles tab.
- Extend `AircraftComponent` with life‑limit fields.
- Add simple alerts for due soon/overdue components (based on current hours/cycles).
- Apply role checks to fleet routes.

**Phase 2 – Maintenance Program and Components**

- Implement `MaintenanceProgramItem` and `MaintenanceStatus`.
- Create Maintenance Program / Status tab on aircraft dashboard.
- Integrate component remaining values with the program.

**Phase 3 – Work Orders, TaskCards, Assignments, Work Logs**

- Extend `apps.work` with TaskCard, TaskAssignment and WorkLogEntry.
- Implement Work Orders tab on aircraft and Planning Board / My Tasks views.
- Add basic notification and activity logging.

**Phase 4 – Reliability Events and Exports**

- Implement `ReliabilityEvent` and event creation hooks on component changes and key tasks.
- Implement CSV and first Spec‑style export for reliability data.

**Phase 5 – Enhancements**

- Soft locks, improved comments, email notifications.
- Refinements based on real‑world usage and QA feedback.

---

This document should be kept in the repository (e.g. `docs/fleet-maintenance-design.md`) and updated as models and endpoints evolve.
