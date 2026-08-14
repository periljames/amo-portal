# Training & Competence Operating System

## Canonical surface

The tenant Training administration surface is `/maintenance/:amoCode/training/competence/*`. It contains Control Room, People & Competence, Requirements Matrix, Training Plan, Sessions & Attendance, Assessments, Authorizations / Decisions, Certificates, Budget & Finance, Records & Reports, and Templates / Settings. Legacy Training administration deep links resolve through the same route tree. Employee self-service remains the separate `/maintenance/:amoCode/training` surface.

The API is rooted at `/training`. Existing course, requirement, record, event, certificate, workbook-import, batch, and public-verification APIs remain authoritative. New governed workflows are under `/training/operating` and orchestrate those sources instead of replacing them.

## Permissions and tenancy

Training uses `training.*` capabilities rather than QMS permissions. Default capability sets cover AMO administrators, authorized Quality roles, Training department roles, Finance, assessors/instructors, and employee self-service. Training department membership does not grant unrelated QMS or administration authority. Database role mappings can narrow or extend those defaults.

Every operating record carries `amo_id`; service queries scope by the active tenant. PostgreSQL row-level security policies use `app.tenant_id`. Platform support access fails closed unless an active, tenant-bound support session exists. Governed review, approval, committee, and issue actions enforce separation of duties where the initiator may not approve the same record.

## Source ownership

| Concern | Authoritative source |
| --- | --- |
| People, departments, authorization types, issued authorizations | Accounts |
| Course catalogue, requirements, records, events, participants, certificates | Existing Training domain |
| Role/course matrices and personnel licences | Training workbook domain |
| Audit observer/assistant evidence and postholder availability | QMS / Quality |
| User availability conflicts | Quality availability register |
| Follow-up work | Shared Tasks |
| Evidence files | Existing Training file records, with operating evidence links for cross-domain references |
| Change history | Shared audit event service plus immutable workflow records |

## Lifecycle

The system supports requirement → need → plan → budget → schedule → enrolment → attendance → assessment → completion → certificate → competence → authorization → performance/effectiveness review → remediation/renewal. The Control Room derives bounded action queues from current records and reports source failures instead of silently presenting incomplete compliance data.

Annual plans are revision controlled and personnel/expiry driven. Each latest active completion record is evaluated independently, with overdue work placed in the first actionable catch-up month and an in-year expiry placed in its calendar month. Required training with no completion record is included as `NOT_DONE`; completed one-off training and expiries after the plan year are excluded. Every planned person freezes name/staff snapshots, last completion, expiry, controlling due date, obligation status, source record ID, workbook `RecordID`/certificate reference, and matrix source. The lifecycle is Draft → Submitted → Reviewed → Approved. Revising an approved plan creates a new draft and preserves the approved revision.

A successful governed workbook commit automatically creates or recalculates the current-year draft from the imported People, Courses, Training, role-group, personnel-role, and course-matrix records. If the latest plan is approved, the sync first creates a new draft revision. If it is already Submitted or Reviewed, the import records `REVIEW_LOCKED` rather than silently changing evidence under review. Administrators can also recalculate a mutable draft explicitly from the frontend.

The Requirements Matrix screen provides direct administration for role groups, personnel-role assignments, and course/role rules. These records remain the same canonical workbook-domain rows used by compliance evaluation and workbook reconciliation; the frontend does not create a parallel applicability model.

Budgets are built from a selected plan. Every line stores unit cost, trainee count, original/reporting currency, Decimal amounts, exchange rate, rate date, and rate source. Quarterly and annual totals use stored values. The lifecycle is Draft → Submitted → Reviewed → Approved; approval snapshots the approved amounts. Revising creates a new draft without changing the historical approved revision. Approved outputs are real XLSX workbooks.

## Attendance and completion

An attendance window issues a random, short-lived credential. The attendance-window record stores only its hash; the expiring deep link is delivered to scheduled participants through both Training notifications and the global notification bell. Opening a replacement window closes the previous one and rotates the credential. Expired notification links cannot create evidence. Email/SMS delivery is not implied by this action; those channels remain subject to the tenant's separate messaging policy.

The instructor console renders a real QR code for classroom display, a countdown, copy/full-screen/rotate controls, the number of notifications issued, and a paginated live roster showing expected versus signed participants. Instructors and trainers receive attendance-management capability without receiving register-certification authority. Only a scheduled authenticated participant can self-sign, and idempotency plus per-event/user uniqueness prevents duplicate evidence. Trainers can mark present/absent under a separate action when a participant cannot scan. Corrections retain the previous value, new value, actor, timestamp, and required reason. Certification closes the governed register and records certifier, timestamp, note, and revision.

Course configuration determines whether attendance, assessment, OJT sign-off, or approved evidence is required. Certificate issuance calls the completion gate. A present attendance entry is insufficient unless the event has a certified register. Assessment-required courses need an approved passing outcome. Existing certificate numbering, branded PDF generation, batch handling, QR/barcode values, revocation, and public verification remain in place.

## Assessment, competence, and authorization

Assessment templates are reusable, revision-aware records supporting written, oral, practical, OJT, observation, group exercise, course completion, and performance review methods. Numeric outcomes use tenant/template thresholds; approval-required outcomes require an independent review. Failed required assessment work creates shared remedial tasks.

Experience logs and periodic reviews record required period, review status, reviewer, last review, next due date, and evidence. Authorization readiness is recomputed from canonical mandatory training, current licences, recent satisfactory experience, approved required assessment types, and active postholder/delegate assignments. Missing or overdue evidence blocks progression. Committee decisions retain position, acting member, evidence snapshot, decision, comments, and time. Only the active postholder or recorded delegate can decide. A successful case issues the canonical Accounts `UserAuthorisation`; it does not create a competing authorization record.

Auditor development counts distinct closed QMS audits where the person was observer or assistant auditor. Qualification is evaluated against the tenant-configurable observer target. Training does not create duplicate audit participation evidence.

Effectiveness evaluations persist levels 1–4 independently. A Level 4 causation claim requires baseline, comparison, confounder, method, and conclusion evidence. Competence reviews and remedial actions create actionable shared tasks when gaps exist.

## Controlled references and reports

Plan, budget, attendance, assessment, and authorization form mappings are tenant settings. Manual-derived examples are not embedded as core workflow constants. Reports use full server-side tenant datasets and configured AMO branding/reference metadata. Plan and attendance reports are PDFs; budget reports are XLSX.

## Frontend and scale controls

The administrative workspace uses a compact header and vertical desktop navigation, collapses to an icon rail on narrower laptops, and becomes a multi-row navigation grid on tablet/mobile. Forms are width-bounded, action icons carry accessible labels/tooltips, and attendance plus plan tables change to stacked mobile records where appropriate.

The frontend loads only the sources required by the active section. Session lists use existing server `limit`/`offset` bounds, plan list responses use aggregate summaries, person/month plan obligations use a paginated endpoint, and attendance rosters are paginated and polled only while an attendance window is open. The Control Room compliance totals use a tenant projection that reads users, requirements, role rules, records, deferrals, and bookings in bounded set-based queries instead of invoking the individual policy evaluator once per person.

## Migration and compatibility

Alembic revision `training_20260813_operating_system` adds course completion-gate configuration, requirement source fields, operating settings, and the governed workflow tables. Follow-up revision `training_20260813_expiry_plan` adds the participant-level expiry/provenance snapshots and due-date index idempotently for both fresh and already-upgraded installations. The migrations seed Training capabilities and bounded role mappings, enable PostgreSQL RLS on new tenant records, and provide downgrade paths. Deploy both backend revisions before enabling the new frontend.

Workbook imports, existing Training routes, certificate verification URLs, and employee self-service remain compatible. No form reference is hard-coded, no fake operating data is seeded, and no Training role receives Quality authority merely by entering the Training workspace.

## Public verification boundary

Public certificate verification stays on the existing safe endpoint. It returns only the certificate validity/status projection intended for unauthenticated verification. Training operating endpoints require authentication and tenant capability checks; they do not expose personnel records, assessments, committee evidence, or internal files publicly.
