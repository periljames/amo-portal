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

Annual plans are revision controlled. Demand generation evaluates current mandatory obligations and preserves explicit participant sets, due timing, source, justification, cost estimate, and manual reference snapshots. The lifecycle is Draft → Submitted → Reviewed → Approved. Revising an approved plan creates a new draft and preserves the approved revision.

Budgets are built from a selected plan. Every line stores unit cost, trainee count, original/reporting currency, Decimal amounts, exchange rate, rate date, and rate source. Quarterly and annual totals use stored values. The lifecycle is Draft → Submitted → Reviewed → Approved; approval snapshots the approved amounts. Revising creates a new draft without changing the historical approved revision. Approved outputs are real XLSX workbooks.

## Attendance and completion

An attendance window issues a random, short-lived credential whose hash—not the credential—is stored. Only a scheduled authenticated participant can self-sign, and idempotency plus per-event/user uniqueness prevents duplicate evidence. Trainers can mark attendance under a separate capability. Corrections retain the previous value, new value, actor, timestamp, and required reason. Certification closes the governed register and records certifier, timestamp, note, and revision.

Course configuration determines whether attendance, assessment, OJT sign-off, or approved evidence is required. Certificate issuance calls the completion gate. A present attendance entry is insufficient unless the event has a certified register. Assessment-required courses need an approved passing outcome. Existing certificate numbering, branded PDF generation, batch handling, QR/barcode values, revocation, and public verification remain in place.

## Assessment, competence, and authorization

Assessment templates are reusable, revision-aware records supporting written, oral, practical, OJT, observation, group exercise, course completion, and performance review methods. Numeric outcomes use tenant/template thresholds; approval-required outcomes require an independent review. Failed required assessment work creates shared remedial tasks.

Experience logs and periodic reviews record required period, review status, reviewer, last review, next due date, and evidence. Authorization readiness is recomputed from canonical mandatory training, current licences, recent satisfactory experience, approved required assessment types, and active postholder/delegate assignments. Missing or overdue evidence blocks progression. Committee decisions retain position, acting member, evidence snapshot, decision, comments, and time. Only the active postholder or recorded delegate can decide. A successful case issues the canonical Accounts `UserAuthorisation`; it does not create a competing authorization record.

Auditor development counts distinct closed QMS audits where the person was observer or assistant auditor. Qualification is evaluated against the tenant-configurable observer target. Training does not create duplicate audit participation evidence.

Effectiveness evaluations persist levels 1–4 independently. A Level 4 causation claim requires baseline, comparison, confounder, method, and conclusion evidence. Competence reviews and remedial actions create actionable shared tasks when gaps exist.

## Controlled references and reports

Plan, budget, attendance, assessment, and authorization form mappings are tenant settings. Manual-derived examples are not embedded as core workflow constants. Reports use full server-side tenant datasets and configured AMO branding/reference metadata. Plan and attendance reports are PDFs; budget reports are XLSX.

## Migration and compatibility

Alembic revision `training_20260813_operating_system` adds course completion-gate configuration, requirement source fields, operating settings, and the governed workflow tables. It seeds Training capabilities and bounded role mappings, enables PostgreSQL RLS on new tenant records, and provides a downgrade path. Deploy the backend migration before enabling the new frontend.

Workbook imports, existing Training routes, certificate verification URLs, and employee self-service remain compatible. No form reference is hard-coded, no fake operating data is seeded, and no Training role receives Quality authority merely by entering the Training workspace.

## Public verification boundary

Public certificate verification stays on the existing safe endpoint. It returns only the certificate validity/status projection intended for unauthenticated verification. Training operating endpoints require authentication and tenant capability checks; they do not expose personnel records, assessments, committee evidence, or internal files publicly.
