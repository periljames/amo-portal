# AMO Portal Deep Technical & Compliance Audit (Multi-Tenant AMO/AOC Focus)

Date: 2026-03-09  
Scope: Full repository (`backend/`, `frontend/`, infra/config/docs) with focus on AMO compliance-critical controls.

## 1) Executive Summary

### Current maturity
- **Overall maturity: medium for generic portal foundations; low-to-medium for enforceable AMO compliance workflows.**
- Strong baseline: modular FastAPI backend, broad QMS/Doc Control/Manuals surface, tenant-linked identifiers in many modules, event + notification primitives.
- Weakness: critical controls are often **informational rather than policy-enforced** (workflow gating, authority boundaries, immutable released records, postholder accountability, training-linked release blocks).

### Can current architecture support manual-controlled AMO compliance?
- **Partially**. It can store records and run basic workflows, but is **not yet sufficient for regulator-grade controlled manual operations** without redesign of authorization, state-machine enforcement, evidence gating, and immutable audit-chain controls.

### Top 10 risks
1. **Coarse role model** causes over-privilege/under-separation (`AMO_ADMIN` + global role checks).  
2. **Inconsistent tenant modeling** across modules (e.g., QMS domain keys without explicit `amo_id` on core tables).  
3. **Doc control endpoints rely only on authentication**, not role/authority checks.  
4. **State transitions are not uniformly enforced** as hard backend state machines.  
5. **Released/superseded record immutability is inconsistent**; edit pathways remain open in places.  
6. **Acknowledgement and transmittal controls exist but are not complete for deadline/escalation governance.**  
7. **RCA/CAPA/effectiveness linkage can be bypassed** by status manipulation patterns in some flows.  
8. **Restricted document security model is metadata-level**, not full access policy + crypto/provenance guardrails.  
9. **Audit/event logging is best-effort in non-critical paths**, not uniformly append-only + tamper-evident.  
10. **No single compliance orchestration engine** binding manuals, findings, training, and MOC gates end-to-end.

### Top 10 urgent architecture changes
1. Adopt **RBAC + scoped assignments + workflow capabilities** (not flat roles only).
2. Introduce **tenant-wide policy engine** for object/state-aware authorization.
3. Normalize all compliance entities on `amo_id` + lifecycle/status enums + immutable release snapshots.
4. Implement strict state machines for manual revisions, TRs, transmittals, CAR/CAPA/RCA/Effectiveness.
5. Add evidence-required transition guards for controlled milestones.
6. Add release gating: **training-required blocks effective implementation** when flagged.
7. Introduce event-driven compliance rules with escalations and SLA timers.
8. Enforce restricted document controls (policy, watermark/download controls, reason logging).
9. Harden audit trail as append-only event ledger with hash chaining/signature option.
10. Build compliance cockpit with “actionable queues” not just dashboards.

### Role model verdict
- **Current model is not acceptable as final AMO operating model.** It is usable for early MVP operation only.

---

## 2) Repo Discovery

### Backend stack
- **Framework**: FastAPI with many routers mounted in `main.py`.
- **ORM**: SQLAlchemy models + Alembic migrations.
- **DB**: relational SQL (Postgres-oriented patterns present).
- **Auth**: JWT bearer with `get_current_user` / `require_roles` dependencies.
- **Events**: internal event broker abstraction + SSE history endpoints.
- **Notifications**: notifications app + task runner reminder/escalation patterns.
- **Jobs**: script-like job runners (e.g., `qms_task_runner.py`, retention runner).

### Frontend stack
- React + TypeScript + Vite.
- Large route surface with dedicated pages for QMS, audits, doc control, manuals, training, admin.

### Auth model
- User has single primary `role` enum + booleans (`is_superuser`, `is_amo_admin`, `is_auditor`).
- Route enforcement primarily role-list based; mixed module gating via entitlement checks.

### Tenancy model
- Strong tenancy presence in accounts and doc-control models (`amo_id` / `tenant_id`).
- In QMS models, several core entities are keyed by `domain` and object IDs, with no explicit `amo_id` on all key tables (critical consistency gap).

### Existing major modules (backend)
- Accounts/admin/billing/entitlements
- Fleet, work orders, technical records, CRS
- Quality/QMS (documents, audits, findings, CAR)
- Manuals and dedicated doc control module
- Training
- Notifications/events/realtime
- Integrations, inventory, finance, reliability

### Missing or partial modules implied by requirements
- Formal postholder assignment engine with SoD constraints.
- Robust approval authority matrix by workflow state.
- OEM subscription verification lifecycle with expiry/validity controls (partial).
- Immutable regulator-facing evidence pack ledger with retention lock semantics.
- Unified compliance orchestration linking revision→training→effective release.

### Current API surface map (high level)
- Routers include: `/auth/*`, `/quality/*`, `/doc-control/*`, `/manuals/*`, `/training/*`, `/audit/*`, `/notifications/*`, `/tasks/*`, `/api/events*`, etc.

### Data model patterns
- Multiple overlapping document-control schemas exist (`manuals`, `doc_control`, `quality` docs/revisions) creating fragmentation risk.
- Many entities already have lifecycle/status fields, but cross-module referential integrity is limited.

### Current role/authorization implementation
- `require_roles(...)` and `require_admin` style checks dominate.
- Superuser override broad.
- Doc control router mostly only requires active auth + quality module entitlement.

### File/document storage strategy
- File refs stored as path strings / asset IDs in DB.
- Generated artifacts and uploads in filesystem-like storage paths.

### Eventing/notification
- Event publish hooks on selected actions.
- Task runner sends reminders/escalations (cron-style execution).
- No central workflow rules engine that spans all compliance domains.

### Background jobs/scheduler design
- Script runners available; likely external cron orchestration.
- No integrated, policy-driven workflow scheduler framework yet.

### Testing and CI/CD
- Backend has broad pytest test files by module.
- Frontend includes Playwright config and TypeScript build.
- No repository-native CI pipeline definitions found in `.github/workflows`.

---

## 3) As-Is vs Required Gap Analysis (Condensed)

Legend: **Implemented / Partial / Missing / Unsafe**

1. Multi-tenant data isolation: **Partial + Unsafe** (inconsistent `amo_id` strategy across quality domain).  
2. Postholder role model: **Missing** (no dedicated postholder assignment governance).  
3. Controlled document mgmt: **Partial** (rich metadata exists; enforcement uneven).  
4. Manual change request workflow: **Partial** (entities exist; authority routing not fully hardened).  
5. Revision workflow: **Partial** (states exist, but strict transition policy not universal).  
6. LEP/LOEP generation/reconciliation: **Partial** (LEP present; LOEP audit-grade cycle incomplete).  
7. Temporary revision control: **Partial** (TR lifecycle exists; expiry/SLA governance limited).  
8. Manual transmittal workflow: **Partial** (distribution events present).  
9. Holder acknowledgement tracking: **Partial** (acks present; robust overdue escalation and proof-chain incomplete).  
10. OEM subscription/access verification: **Partial/Missing** depending module path.  
11. Obsolete withdrawal/archive control: **Partial + Unsafe** (archive records exist; operational withdrawal confirmation not airtight).  
12. Restricted-access handling: **Unsafe** (restricted flags exist; policy enforcement/download controls limited).  
13. Audit finding workflow: **Partial**.  
14. CAPA workflow: **Partial**.  
15. RCA workflow: **Partial/Unsafe** (text fields exist; structured RCA quality gates missing).  
16. Effectiveness review/closure: **Partial/Unsafe** (can be bypassed in workflow combinations).  
17. Safety-quality integration: **Partial**.  
18. Management of Change: **Missing/Partial** (screening exists in places but not full formal MOC workflow).  
19. Training linkage to revisions/findings: **Partial/Unsafe** (no universal hard gate pre-implementation).  
20. Notification/escalation engine: **Partial** (task runner exists; domain-wide rules missing).  
21. Audit trail/evidence integrity: **Partial/Unsafe** (best-effort logging, non-uniform criticality).  
22. Record retention/retrieval: **Partial**.  
23. Dashboard/compliance visibility: **Partial** (many dashboards, variable actionability).  
24. Admin practicality: **Partial** (rich pages; governance complexity not encoded).

---

## 4) Role and Access Control Redesign

### Recommendation
Adopt **hybrid authorization**:
- **RBAC base** (role families)
- **Scoped assignments** (tenant, department, document, audit, finding)
- **Capability grants** (approve_release, verify_effectiveness, assign_training)
- **Workflow-state permissions** (who can transition what at which state)
- **SoD rules** (cannot approve own submission for controlled workflows)
- Optional ABAC policies for restricted document contexts and emergency overrides.

### Tenant-scoped role families
- Platform: `platform_super_admin`
- Tenant core: `tenant_admin`, `accountable_manager`
- Quality/Safety: `head_of_quality`, `quality_officer`, `quality_auditor`, `quality_inspector`, `head_of_safety`, `safety_officer`
- Document control: `doc_control_officer`, `technical_librarian`, `manual_owner`, `manual_holder`
- Maintenance ops: `head_base_maintenance`, `head_line_maintenance`, `head_workshop`, `certifying_engineer`, `technician`
- Support: `technical_records`, `stores`, `training_manager`, `training_coordinator`
- Audit access: `auditor_readonly_internal`, `auditor_external_readonly`
- Generic: `staff_general`, optional controlled external role.

### Object-level permissions (minimum)
- Manuals: create/edit/review/approve/release/archive
- TR: issue/approve/in-force/expire/incorporate
- Distribution: assign holders/issue transmittal/track ack/escalate
- Findings/CAPA: open/assign/respond/approve_plan/verify_effectiveness/close/reopen
- Training: assign/verify completion/block release override
- Restricted docs: view/download/export with reason and watermark policy
- Audit trail: export with privilege checks

### Separation of duties (examples)
- Proposer cannot final-approve own change package.
- CAP owner cannot be sole effectiveness verifier.
- Manual owner cannot bypass HOQ-required authority steps.

---

## 5) Target Domain/Data Model (Textual ERD)

### Core identity/org
- `tenant (amo)` 1..* `department`
- `user` *..* `membership`
- `membership` *..* `role_assignment`
- `postholder_assignment(user, postholder_type, dept, valid_from/to, delegated_to)`

### Document control/manuals
- `manual` 1..* `manual_revision`
- `manual_revision` 1..* `manual_section`
- `manual_revision` 1..* `lep_row` / optional `loep_entry`
- `manual_revision` 1..* `revision_transmittal`
- `revision_transmittal` 1..* `revision_acknowledgement`
- `manual` 1..* `manual_change_request`
- `manual_revision` 1..* `temporary_revision`
- `manual_copy(controlled_copy)` *..1 `manual_holder_assignment`
- `manual_revision` 1..* `obsolete_archive_record`

### OEM/publication
- `oem_publication` *..* `oem_subscription`
- `oem_subscription` 1..* `publication_access_verification`

### Audit/CAPA
- `audit` 1..* `audit_finding`
- `audit_finding` 1..1 `rca_record`
- `audit_finding` 1..* `corrective_action_plan` (or split action tables)
- `audit_finding` 1..* `effectiveness_review`
- `audit_finding` *..* `evidence_attachment`

### Safety/MOC/training
- `moc_record` 1..* `risk_assessment`
- `moc_record` *..* `hazard_link`
- `training_requirement` links from `manual_revision` and `audit_finding`
- `training_assignment` + `training_completion_record`

### Governance
- `approval_record` (typed approvals by object/state)
- `notification_event`
- `escalation_rule`
- `audit_event_ledger` (append-only)
- `retention_policy`

### Integrity rules
- Every compliance table: `amo_id`, `created_at`, `created_by`, status enum.
- Released records immutable: update blocked except supersession metadata.
- Hard FK from transmittal/ack to exact revision snapshot hash.
- Soft delete only for drafts; immutable retention for released/approved evidence.

---

## 6) Workflow / State Models

### Manual Change Request
- States: `DRAFT -> SUBMITTED -> DEPT_REVIEW -> QA_REVIEW -> APPROVED/REJECTED -> IMPLEMENTED`.
- Gate: required rationale + affected sections + proposer identity.

### Manual Revision
- `DRAFT -> REVIEW -> QA_APPROVAL -> AUTHORITY_APPROVAL(optional) -> RELEASED -> SUPERSEDED -> ARCHIVED`.
- Gate: LEP generated, transmittal package prepared, approvals captured.

### Temporary Revision
- `DRAFT -> APPROVED -> IN_FORCE -> INCORPORATED|EXPIRED`.
- Gate: expiry set, updated LEP/LOEP, holder notification complete.

### Transmittal & acknowledgement
- `PREPARED -> ISSUED -> PARTIAL_ACK -> FULL_ACK -> OVERDUE_ESCALATED -> CLOSED`.
- Gate: recipient roster fixed at issue time; immutable issue snapshot.

### Obsolete withdrawal
- `MARKED_SUPERSEDED -> WITHDRAWAL_PENDING -> WITHDRAWAL_CONFIRMED -> ARCHIVED`.
- Gate: active library access disabled before archive closure.

### Audit finding / CAR / CAPA / RCA / Effectiveness
- Finding: `OPEN -> ACKNOWLEDGED -> RCA_IN_PROGRESS -> CAPA_IN_PROGRESS -> IMPLEMENTED -> EFFECTIVENESS_PENDING -> CLOSED`.
- Reopen allowed from closed if effectiveness fails.
- Gate: required evidence at each major transition.

### MOC
- `INITIATED -> IMPACT_ASSESSMENT -> RISK_REVIEW -> APPROVAL -> IMPLEMENTATION -> POST_REVIEW -> CLOSED`.

### Training from revision/finding
- Auto-create training requirements on release/finding severity rules.
- If policy says “training mandatory before effective date”: block effective implementation until completion threshold.

### OEM verification
- `SUBSCRIPTION_ACTIVE -> EXPIRING -> EXPIRED` + periodic access verification states.

---

## 7) Frontend Audit

### Existing screen coverage
- Extensive page set exists for QMS, audits, quality cars, doc control, manuals, training, admin and technical records.

### Main frontend control gaps
- Several workflows appear represented in UI but backend policy depth is inconsistent.
- Limited visible enforcement UX for:
  - immutable released states,
  - strict approval chain accountability,
  - evidence-required blockers,
  - training-linked release gates,
  - escalations with explicit SLA ownership.

### Required frontend additions/priorities
1. Controlled Manuals Register (compliance-first table + status chips)
2. Manual Change Request workspace with authority chain panel
3. Revision composer with LEP/LOEP diff preview + release checklist
4. Transmittal issuance + holder acknowledgement queue with escalation indicators
5. Obsolete withdrawal register with confirmation evidence upload
6. OEM subscription dashboard + verification tracker
7. Audit Findings board with RCA/CAPA/effectiveness timeline
8. MOC register with risk matrix and linked hazards
9. Training impact review (revision/finding-origin map)
10. Tenant role/postholder assignment matrix editor
11. Audit trail viewer (immutable event timeline)

---

## 8) Backend Audit Findings (selected high-impact)

1. **Severity: Critical**  
   Issue: Doc control router allows broad operations with only `get_current_active_user` (no role/capability checks per endpoint).  
   Impact: Any authenticated user in tenant can potentially mutate controlled documents/workflows.  
   Fix: Introduce per-action policy checks (`can_create_document`, `can_publish_revision`, `can_issue_tr`, etc.).  
   Type: Architectural + localized router hardening.

2. **Severity: Critical**  
   Issue: QMS core model uniqueness and keys rely heavily on `domain` values without pervasive tenant keying.  
   Impact: Cross-tenant collision/leakage risk and fragile isolation assumptions.  
   Fix: Add `amo_id` to all compliance-critical QMS entities; migrate unique constraints to include `amo_id`.  
   Type: Architectural.

3. **Severity: High**  
   Issue: Multiple overlapping document schemas (`manuals`, `doc_control`, `quality` docs).  
   Impact: Divergent truth sources, inconsistent policy enforcement, audit complexity.  
   Fix: Define canonical bounded contexts + integration events; de-duplicate lifecycle ownership.  
   Type: Architectural.

4. **Severity: High**  
   Issue: Audit logging is best-effort for non-critical actions.  
   Impact: Forensic gaps in regulator review.  
   Fix: Compliance actions must be fail-closed on audit-log failure; append-only ledger table for critical domains.  
   Type: Architectural.

5. **Severity: High**  
   Issue: Released revision immutability not universally enforced with DB constraints/service guards.  
   Impact: Silent post-release mutation risk.  
   Fix: status-aware service guard + DB trigger/check pattern for immutable fields after release.  
   Type: Architectural.

6. **Severity: High**  
   Issue: Training linkage to revision/finding not universally mandatory before effective implementation.  
   Impact: Operational non-compliance risk.  
   Fix: Add policy hook and release gate service check.

7. **Severity: Medium**  
   Issue: Escalation rules distributed in task runner patterns only; no central policy registry.  
   Impact: inconsistent overdue handling across domains.  
   Fix: `EscalationRule` table + event/scheduler executor.

8. **Severity: Medium**  
   Issue: Restricted docs are mostly represented by flags.  
   Impact: insufficient access reason tracking and download governance.  
   Fix: object policy records + access justification + watermark options.

---

## 9) Security / Guardrails Redesign

- Enforce tenant isolation at service layer + query helpers + tests; never rely only on client-side path scoping.
- Replace wide role checks with capability checks bound to object state.
- Add immutable release snapshots (`checksum`, signed approval record, append-only event ledger hash chain).
- Signed approvals (at least cryptographic digest over decision payload + actor/time).
- Mandatory reason capture for restricted document view/download/export.
- Prevent silent state changes: every transition emits auditable event with before/after.
- Retention lock for regulated records.
- Deep-link tokens in notifications must be short-lived and tenant-bound.

---

## 10) Automation / Notification Engine

### Event-driven (async)
- Revision released -> create transmittals + notify holders.
- Finding status changed -> spawn/update CAPA/RCA tasks.
- Evidence rejected -> notify owner and reset state as configured.

### Scheduled
- Ack overdue reminders/escalations.
- TR approaching 6-month or configured threshold.
- OEM subscription expiry warnings.
- CAR due-date approach/overdue escalation.
- Effectiveness review due reminders.

### Synchronous validation (request-time)
- Block release without required approvals/evidence/LEP.
- Block closure without effectiveness evidence when mandated.
- Block “effective implementation” if training completion policy unmet.

---

## 11) Implementation Strategy

### Phase 1 (critical controls, 4-8 weeks)
- Authorization redesign foundation (capabilities + assignments).
- Tenant key normalization plan for QMS tables.
- Hard state transitions + evidence gating for revision/TR/finding/CAPA.
- Immutable audit ledger for critical actions.

### Phase 2 (workflow completion, 6-10 weeks)
- Full transmittal/ack/escalation engine.
- Training linkage gating.
- MOC and OEM verification workflows.
- Obsolete withdrawal confirmation chain.

### Phase 3 (optimization/analytics, 4-6 weeks)
- Compliance cockpit KPIs and predictive escalations.
- Evidence pack exports with regulator-ready bundles.

### Migration notes
- Use feature flags per workflow engine.
- Migrate users to new role assignments with compatibility bridge from legacy roles.
- Dual-write audit logs during migration window.

---

## 12) Testing Strategy (high-value scenarios)

1. Tenant A cannot read/write Tenant B controlled docs via every endpoint.
2. Manual release blocked without required approval chain.
3. Restricted doc download denied without policy grant.
4. TR cannot enter `IN_FORCE` without LEP update evidence.
5. Superseded doc inaccessible from active library endpoints.
6. CAR closure blocked without RCA + CAPA + effectiveness evidence.
7. Training-required revision cannot become effective until completion threshold met.
8. Ack overdue escalation triggers in configured SLA steps.
9. Audit ledger record hash mismatch detection test.
10. SoD test: proposer cannot self-approve final release.
11. Reopen finding after failed effectiveness review.
12. Notification deep-link token tenant mismatch rejection.

---

## 13) Final Findings Register (abridged)

| ID | Domain | Finding | Severity | Evidence | Action | Priority | Complexity | Dependencies |
|---|---|---|---|---|---|---|---|---|
| F-001 | AuthZ | Coarse roles insufficient for compliance SoD | Critical | `security.py`, role enum | Hybrid policy model | P0 | High | Role migration |
| F-002 | Tenancy | Inconsistent tenant keying in quality entities | Critical | `quality/models.py` | Add `amo_id` + constraints | P0 | High | DB migration |
| F-003 | Doc Control | Mutation endpoints lack role/capability checks | Critical | `doc_control/router.py` | Add policy guards | P0 | Med | Policy service |
| F-004 | Audit | Best-effort non-critical audit logging | High | `audit/services.py` | Fail-closed for compliance actions | P1 | Med | Event ledger |
| F-005 | Lifecycle | Released immutability not uniformly enforced | High | manuals/doc/qms models+routers | Immutable guards + DB constraints | P1 | High | State machine layer |
| F-006 | Training | Revision/finding training gates incomplete | High | training + quality/doc flows | Implement release gating | P1 | Med | Policy rules |
| F-007 | Escalation | Rule logic fragmented | Medium | task runner/services | Central escalation engine | P2 | Med | event bus |
| F-008 | Archive | Obsolete withdrawal confirmation incomplete | High | doc control archive/publish flow | Add withdrawal state + proof | P1 | Med | workflow update |
| F-009 | Restricted docs | Policy not fully enforced | High | restricted flags/access fields | ABAC + justification logs | P1 | Med | policy engine |
| F-010 | CI Quality | No repo CI workflow definitions found | Medium | repo discovery | Add mandatory test gates | P2 | Low | DevOps |

---

## 14) Direct Next Code Change Proposals

### A. Authorization foundation
- Add `authorization/policy.py` with:
  - `Capability` enum,
  - `can(user, capability, obj, state)` evaluator,
  - SoD guard helpers.
- Incrementally apply to `doc_control/router.py` publish/TR/distribution endpoints.

### B. Tenant normalization migration
- New Alembic migration:
  - add `amo_id` to `qms_documents`, `qms_document_revisions`, `qms_audits`, `qms_audit_findings`, `quality_cars`, `qms_notifications` (where missing),
  - backfill from current user/domain ownership strategy,
  - enforce non-null + compound unique indexes with `amo_id`.

### C. Workflow transition guards
- New service layer (`compliance/workflows.py`) with explicit transition map dictionaries.
- Router endpoints call services only; no direct status mutation.

### D. Immutable ledger
- New `compliance_event_ledger` append-only table:
  - `id, amo_id, entity_type, entity_id, action, actor, payload_hash, prev_hash, created_at`.
- On critical transitions, write ledger record in same transaction.

### E. Training-release linkage
- Add `requires_training` + `training_gate_policy` to revision packages.
- On publish/effective transition, assert completion thresholds.

### Clarifications needed before direct implementation
1. Regulatory jurisdiction variants (FAA/EASA/KCAA) and whether workflows differ per tenant.
2. Whether external auditors need temporary elevated object access with expiration.
3. Whether e-signature standard required (simple cryptographic attestation vs advanced digital signature).

---

## Permission Matrix (starter)

| Capability | Platform SA | Tenant Admin | HOQ | Doc Control Officer | Manual Owner | Manual Holder | Quality Auditor | Training Manager |
|---|---:|---:|---:|---:|---:|---:|---:|---:|
| Create manual | Y | Y | Y | Y | Y | N | N | N |
| Approve/release revision | Y | Optional | Y | Optional | N | N | N | N |
| Issue TR | Y | Optional | Y | Y | Optional | N | N | N |
| Acknowledge revision | Y | Y | Y | Y | Y | Y | N | N |
| Open finding | Y | Y | Y | N | N | N | Y | N |
| Approve CAPA | Y | Optional | Y | N | N | N | Optional | N |
| Verify effectiveness | Y | Optional | Y | N | N | N | Y | N |
| Assign training | Y | Y | Y | N | N | N | N | Y |
| Verify training complete | Y | Y | Optional | N | N | N | N | Y |
| View restricted docs | Y | Policy | Policy | Policy | Policy | Policy | Policy | Policy |

---

## Engineering Ticket Backlog (initial)

1. **AUTH-001** Introduce capability-based authorization service and assignment tables.
2. **AUTH-002** Apply capability checks to doc-control mutation endpoints.
3. **TEN-001** Add `amo_id` normalization migration for quality entities.
4. **WF-001** Implement revision state machine service + tests.
5. **WF-002** Implement TR state machine + expiry/escalation jobs.
6. **WF-003** Implement CAR/RCA/CAPA/effectiveness transition engine.
7. **AUD-001** Append-only compliance ledger with hash chain.
8. **DOC-001** Restricted document access policy + reason logging + watermarking.
9. **TRN-001** Training gate linkage to revisions/findings.
10. **OPS-001** Add CI workflow running backend tests + frontend typecheck + selected E2E.
