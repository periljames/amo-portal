# Quality Module — Standalone Delivery, Integration and Release Gate

**Date:** 2026-07-22  
**Delivery profile:** `quality`  
**ASGI entrypoint:** `amodb.quality_main:app`

## 1. Purpose and compliance position

This document defines the deployable Quality Management System profile, its process flow, calendar and planning sources, cross-module dependencies, report outputs, data integrity requirements, and release gate.

The software supports an organization in operating and evidencing a quality management system. It does **not** certify an organization and must not be marketed as automatically making a client ISO certified. Certification and conformity depend on the client's implemented processes, leadership, competence, records, internal audits, corrective actions, and external certification assessment.

As of 22 July 2026, the published ISO 9001 baseline remains **ISO 9001:2015 with ISO 9001:2015/Amd 1:2024**. ISO lists Edition 6 as under publication for September 2026. There is no published standard named “ISO 9001:2025”. Product and proposal wording must therefore use one of the following:

- `Supports ISO 9001:2015 and Amendment 1:2024 QMS workflows and evidence`; or
- `ISO 9001 readiness and transition-supporting QMS platform`.

Do not claim conformity with the 2026 edition until the final text is published, reviewed, mapped, implemented, and independently validated.

## 2. Bounded deployment profile

Start the QMS-only API surface with:

```bash
uvicorn amodb.quality_main:app --host 0.0.0.0 --port 8000
```

Production startup is schema-strict by default. The database must be at every repository Alembic head before the application starts:

```bash
alembic -c backend/amodb/alembic.ini upgrade heads
```

The entrypoint exposes only the Quality product and the foundations required to operate it.

### Included route families

| Capability | Why it is included |
|---|---|
| Accounts, authentication, onboarding and module administration | Tenant isolation, users, roles, permissions and Quality entitlement |
| Bootstrap | Portal session and tenant context |
| Quality/QMS | Documents, changes, schedules, audits, findings, CARs, CAPA, evidence, metrics and reports |
| Training/competence | Auditor and personnel competence evidence; calendar expiry and session sources |
| Audit event log | Immutable business-action traceability and evidence-pack history |
| Notifications | Audit notices, CAR assignments, reminders, report distribution and action links |
| Tasks | Follow-up ownership, due dates, CAPA verification and automatic closure |
| Integrations and events | Controlled integration/event surfaces required by the platform shell |
| Manuals and document control | Controlled content, branding and document lifecycle support |

### Omitted operational route families

The bounded entrypoint does not register Fleet, Work Orders, CRS, Reliability, Inventory, Finance, Billing, Technical Records, Rostering or Workforce routers. Quality can therefore be sold and exposed as a QMS product without presenting unrelated maintenance-operation screens.

This is a **bounded application profile inside the existing monorepo**, not a separately forked codebase. It still uses the repository's shared accounts, database and Alembic graph. That is intentional: one code line avoids drift while route registration and entitlements define the product boundary.

## 3. Canonical API ownership

The Quality module is the backend owner. New code must not target the deprecated legacy QMS application.

| Surface | Prefix | Status |
|---|---|---|
| Direct Quality API | `/quality/*` | Active compatibility and workflow API used by the current frontend |
| Canonical tenant API | `/api/maintenance/{amo_code}/quality/*` | Preferred tenant-scoped API |
| Legacy tenant alias | `/api/maintenance/{amo_code}/qms/*` | Deprecated compatibility alias only |

The canonical router applies tenant context and Quality permissions. The direct router must continue to scope every audit, schedule, finding and CAR query to the authenticated user's AMO.

## 4. End-to-end process flow

The audited workflow is represented as seven explicit stages. A workflow check and the audit workspace must calculate the same state.

1. **War room / planning** — audit type, scope, criteria, dates, auditee, lead auditor and supporting auditors are assigned. Internal audit identity and schedule fields are locked after creation where required.
2. **Checklist** — a controlled checklist file is uploaded or portal checklist rows are created, assigned and completed.
3. **Fieldwork and findings** — actual fieldwork dates, objective evidence, observations and non-conformities are recorded. Finding references are unique within an audit.
4. **CAR/CAPA** — each required non-conformity receives a linked CAR. Root cause, containment, corrective action, preventive action, due dates, evidence and review decisions are tracked.
5. **Evidence** — checklist, report, finding attachments and CAR attachments form the evidence set. Evidence integrity includes file metadata and hashes where available.
6. **Report** — the issued audit report is uploaded, downloaded through an access-controlled endpoint, tracked against its due date and distributed to selected recipient groups with audit-log entries.
7. **Closeout and archive** — audit closure is blocked until required report/checklist or CAR acceptance/evidence conditions are satisfied. Retention and archive packages preserve the closure record.

### State integrity rules

- A closed, cancelled or escalated CAR is not editable through ordinary response flows.
- A submitted CAR response moves to pending verification.
- Rejected root cause or CAPA returns the CAR to active work with review notes.
- Accepted root cause and CAPA do not close a CAR until required evidence is present and verified.
- CAR acceptance closes the linked finding and related tasks through the centralized state synchronizer.
- Audit closure with no NC findings requires both checklist and report.
- Audit closure with NC findings requires issued CARs, accepted root cause/CAPA and verified evidence.

## 5. Planning and calendar mapping

The canonical Quality calendar is tenant-scoped and accepts date bounds, source filters, pagination and multiple views. It aggregates:

| Source | Date basis | User action |
|---|---|---|
| Audit schedules and planned audits | `next_due_date`, planned start/end | Open audit schedule or audit workspace |
| CAR deadlines | due date/target closure date | Open the CAR register or audit CAR tab |
| Training competence | training validity expiry | Open personnel course history |
| Training sessions | event start/end | Open competence schedule |

The calendar returns source-level errors instead of blanking the entire calendar. Training data is included only when the tenant has the Training module and the required tables are available. Audit and CAR data remain usable if Training is disabled.

### Recurrence and reminders

- Audit schedule recurrence supports one-time, monthly, quarterly, bi-annual and annual cycles.
- Running a schedule creates the audit and advances the next due date.
- Upcoming and day-of notices are idempotent using sent timestamps.
- CAR reminders and escalation dates are stored and audited.
- Tenant workflow settings govern report due days, report reminder days, CAR reminder percentages, final-reminder timing and auto-escalation policy.

## 6. Cross-module integration contract

### Required

- **Accounts/Auth:** users, AMO ownership, roles, active status, departments and module entitlement.
- **Audit events:** create/update/delete/status/share/export actions and critical transitions.
- **Notifications:** in-app action records and email delivery logs where configured.
- **Tasks:** CAPA and verification ownership plus entity-based closure.
- **Exports:** audit and CAR evidence packs, PDF/ZIP outputs and traceable export actions.
- **Document control/manuals:** controlled quality documents, revisions, distribution and branded outputs.

### Required for a complete competence-backed QMS offering

- **Training:** auditor eligibility, personnel competence evidence, expiry indicators and training sessions in the Quality calendar.

Training remains independently entitled. If a client buys only the core Quality product without Training, the calendar degrades explicitly and the client must maintain competence evidence through another controlled mechanism.

### Optional

- **Reliability:** Quality CARs support a Reliability program value, but the bounded Quality profile does not expose Reliability routes.
- **Realtime:** useful for live notification refresh but not required for correct workflow state.
- **External integrations:** may publish or consume events, but cannot bypass tenant, permission or workflow checks.

## 7. Frontend mapping and stability rules

The existing frontend remains the delivery UI. A Quality-only client is controlled through module entitlements and navigation visibility rather than a separate frontend fork.

- `/maintenance/:amoCode/quality` redirects to the Quality QMS overview.
- Quality schedule, audit workspace, findings, CAR, evidence, report, document and calendar pages use the same tenant context.
- The audit run hub uses the dedicated `qmsAuditHubActions` service boundary for CAR action history and report sharing.
- Requests have deterministic read/write timeouts, session-expiry handling, parsed backend error details and guaranteed loading-state cleanup.
- Production build and targeted regression tests are release gates.

No broad visual redesign is part of this stability pass. Existing Quality layouts remain intact. Frontend changes are limited to unstable service behavior and test coverage.

## 8. Report and evidence outputs

The module supports the following controlled outputs:

- audit report upload and authorized download;
- report distribution to accountable manager, Quality manager, department heads, audited department, shop personnel and facility personnel;
- audit evidence ZIP pack;
- CAR PDF form and CAR evidence pack;
- archive package records and retention tracking;
- dashboard and audit metrics for operational review;
- document revision, distribution and custody records;
- audit-event history for material state changes and exports.

File storage references must point to an approved persistent storage location. Local ephemeral container paths are not acceptable for production retention. Backup, replication, access control and restore tests are deployment responsibilities.

## 9. Database integrity repair

Revision `quality_20260722_schema_integrity` hardens four tables that older request-time compatibility guards could create without full relational constraints:

- `quality_car_responses`;
- `quality_car_attachments`;
- `qms_finding_attachments`;
- `qms_corrective_actions`.

The migration backfills safe defaults, refuses to hide orphaned or duplicate data, adds required primary/foreign/unique constraints, applies status checks and restores not-null/default/index expectations. Equivalent existing foreign keys and unique constraints are detected by their columns rather than only by constraint name, preventing duplicate constraints on healthy databases.

A PostgreSQL probe recreates the degraded legacy shape, upgrades it, checks constraint/nullability/backfill results and confirms that an orphan CAR response is rejected.

Request-time compatibility code remains temporarily available for older environments, but production Quality deployments must rely on Alembic and strict startup preflight. Runtime DDL is not a substitute for deployment migrations.

## 10. ISO 9001 support map

This is a feature-support map, not a certification statement.

| ISO 9001 area | Product support | Position |
|---|---|---|
| Context and QMS scope | controlled manuals/documents, tenant scope, change records | Supported; client must define context, interested parties and scope content |
| Leadership and responsibilities | roles, approvals, accountable/Quality manager distribution, audit trail | Supported workflow evidence |
| Planning | audit programme, dates, due dates, reminders, actions | Supported; a dedicated enterprise risk/opportunity register is not established by this release |
| Support | competence records, controlled information, communication and notifications | Supported when Training and document control are enabled |
| Operation | controlled procedures, audit execution, findings, CAR/CAPA and evidence | Supported |
| Performance evaluation | dashboards, metrics, internal audits and reports | Supported; management-review meeting content and decisions remain client-controlled records |
| Improvement | non-conformity, root cause, correction, corrective action, verification and closure | Supported |

## 11. Release gate

The Quality profile is releasable only when all of the following pass:

1. Alembic graph is valid and contains `quality_20260722_schema_integrity` at the expected head.
2. Static backend/frontend contract check passes.
3. Full SQLAlchemy mapper configuration passes for both the main portal and bounded Quality entrypoint.
4. Quality workflow, enforcement, audit event, task integration, export and delivery-profile tests pass.
5. PostgreSQL degraded-schema migration probe passes.
6. Frontend Quality service regression tests pass.
7. TypeScript production build passes.
8. Changed Quality service files pass ESLint.
9. Deployment storage, SMTP/notification delivery, backup and restore are verified in the target environment.
10. Client-specific ISO clause mapping, procedures, responsibilities, records and certification claims receive Quality/legal review.

CI workflow: `.github/workflows/quality-module-ci.yml`.

## 12. Known boundaries

- The bounded profile limits the exposed API surface; it does not split the monorepo or Alembic history into an independent package.
- Existing frontend assets are still built as one portal bundle, while entitlements determine which modules the client sees.
- The current published ISO baseline and the upcoming 2026 edition must be tracked separately. The clause map must be revised after the final 2026 standard is published.
- Software test success proves the implemented contracts tested by CI. It does not prove client process conformity or ISO certification.
