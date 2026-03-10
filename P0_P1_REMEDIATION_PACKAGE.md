# AMO Portal P0/P1 Regulator-Grade Remediation Package

Date: 2026-03-09  
Scope: execution design for immediate implementation in the current `amo-portal` repo.

---

## 1) P0/P1 Remediation Blueprint

## P0 (must build now: safety/compliance blockers)

1. **Canonical authorization enforcement for compliance mutations**
   - Implement capability checks for all mutation endpoints in `doc_control`, `manuals`, and `quality`.
   - Replace direct `get_current_active_user` mutation access with `require_capability(...)` guards.
   - Why first: current mutation endpoints are broadly accessible within tenant and violate controlled document/accountability expectations.

2. **Tenant normalization on compliance-critical entities**
   - Add explicit `amo_id` to quality entities that currently rely on `domain` scoping.
   - Enforce compound uniqueness with `amo_id`.
   - Why first: tenant segregation is a foundational safety and legal boundary.

3. **Hard state-machine service layer (fail-closed)**
   - Move all status transitions to explicit service functions with transition maps and evidence checks.
   - Why first: regulator workflows cannot rely on UI conventions or ad-hoc router updates.

4. **Append-only immutable compliance ledger (transactional write)**
   - Add `compliance_event_ledger` with hash chain and mandatory writes for critical transitions.
   - Why first: approved/released actions must be non-repudiable and retrievable.

5. **Restricted + obsolete guardrails**
   - Block operational access to superseded revisions.
   - Enforce restricted document policy checks and justification logs for view/download.
   - Why first: active use of obsolete docs and unrestricted controlled access are immediate compliance failures.

6. **Training-gated implementation control**
   - Add hard block: when training is required by policy, revision implementation (effective state) and finding closure cannot complete until training threshold met.
   - Why first: explicit requirement from manuals and real-world operational risk.

## P1 (must build next: complete operational loop)

1. **Postholder assignment framework + separation-of-duties (SoD) rules**
2. **Unified transmittal/acknowledgement SLA/escalation engine**
3. **Canonical compliance domain consolidation (merge/deprecate overlap models)**
4. **RCA/CAPA/effectiveness full evidence workflow hardening**
5. **MOC workflow and cross-linking to findings/revisions/training**
6. **Compliance-focused frontend workspaces and queues**

### Sequencing rationale
- P0 secures legal boundaries and fail-closed controls before expanding UX/process breadth.
- P1 completes full-cycle operations once mutations, identity, tenancy, and audit integrity are guaranteed.

---

## 2) Canonical Authorization Design

### 2.1 Target layered model

1. **Platform roles** (global):
   - `platform_super_admin`
2. **Tenant-scoped roles**:
   - `tenant_admin`, `accountable_manager`, `head_of_quality`, `quality_officer`, `quality_auditor`, `doc_control_officer`, `technical_librarian`, `head_of_safety`, `safety_officer`, `training_manager`, `manual_owner`, `manual_holder`, etc.
3. **Postholder assignments** (time-bounded):
   - Role-like office appointments (e.g., HOQ, Head of Base Maintenance).
4. **Capabilities**:
   - Fine-grained verbs (`manual.release`, `tr.issue`, `finding.close`, `ledger.export`).
5. **Workflow-state checks**:
   - Capabilities allowed only for specific state transitions.
6. **SoD constraints**:
   - Prevent self-approval and conflicted closure verification.

### 2.2 Schema additions

Add tables in `backend/amodb/apps/accounts/models.py` (or new `apps/authorization/models.py`):
- `role_definitions(id, code, scope_type[platform|tenant], description, is_system)`
- `capability_definitions(id, code, module, description)`
- `role_capability_bindings(role_id, capability_id, constraints_json)`
- `user_role_assignments(id, amo_id, user_id, role_id, department_id?, valid_from, valid_to, assigned_by_user_id)`
- `postholder_assignments(id, amo_id, user_id, postholder_code, department_id?, delegated_to_user_id?, valid_from, valid_to, status)`
- `sod_policy_rules(id, amo_id?, rule_code, policy_json, active)`

### 2.3 Migration from current role model

Current model in `User.role` + booleans (`is_superuser`, `is_amo_admin`, `is_auditor`):
1. Seed role definitions for all legacy enum values.
2. Backfill `user_role_assignments` from current users:
   - `is_superuser=true` -> platform role `platform_super_admin`
   - `is_amo_admin=true` or `role=AMO_ADMIN` -> `tenant_admin`
   - role mappings (`QUALITY_MANAGER` -> `head_of_quality`, etc.)
3. Keep legacy checks in compatibility mode for one release (feature flag).
4. Switch router dependencies from `require_roles` to `require_capability`.
5. Remove legacy booleans from enforcement paths after migration verification.

### 2.4 Core permission matrix (minimum)

| Workflow action | Platform SA | Tenant Admin | HOQ | Doc Control Officer | Manual Owner | Manual Holder | Quality Auditor | Training Manager |
|---|---|---|---|---|---|---|---|---|
| Create manual | Y | Y | Y | Y | Y | N | N | N |
| Edit draft revision | Y | Y | Y | Y | Y | N | N | N |
| Approve revision | Y | Optional | Y | Optional | N | N | N | N |
| Release revision | Y | Optional | Y | Y (if delegated) | N | N | N | N |
| Issue temporary revision | Y | Optional | Y | Y | Optional | N | N | N |
| Send transmittal | Y | Y | Y | Y | N | N | N | N |
| Acknowledge revision | Y | Y | Y | Y | Y | Y | N | N |
| Open finding/CAR | Y | Y | Y | N | N | N | Y | N |
| Approve CAPA | Y | Optional | Y | N | N | N | Optional | N |
| Verify effectiveness | Y | Optional | Y | N | N | N | Y | N |
| Assign training | Y | Y | Y | N | N | N | N | Y |
| Verify training completion | Y | Y | Optional | N | N | N | N | Y |
| View restricted doc | Y | policy | policy | policy | policy | policy | policy | policy |

---

## 3) Canonical Compliance Domain Model (Remain / Merge / Deprecate)

### 3.1 Current overlap problem
- `apps/manuals/models.py`: manual-centric domain with revisions/ack/print.
- `apps/doc_control/models.py`: controlled docs, drafts, proposals, LEP, TR, distribution, archive.
- `apps/quality/models.py`: QMS documents/revisions/distribution + audits/findings/CAR.

### 3.2 Canonical ownership decision

## Canonical now (P0/P1)
1. **Document control + revision distribution domain**: `apps/doc_control` becomes primary operational workflow owner.
2. **Quality audit/CAR/CAPA domain**: `apps/quality` remains owner for audits/findings/CAR.
3. **Manual reading/rendering/print presentation**: `apps/manuals` remains specialized presentation/reader domain.

## Merge/deprecate strategy
- `qms_documents` and `qms_document_revisions` become **secondary/read model** in P1 and eventually deprecated for controlled manual lifecycle.
- `manuals` ingestion/reader retains value; lifecycle authority routes to canonical doc-control workflow entities.
- Introduce integration events:
  - `doc_control.revision_released` -> update manual reader view materialization.
  - `doc_control.revision_released(training_required=true)` -> create training requirements.

### 3.3 Canonical entity ownership
- **Manual / Revision / TR / LEP / Transmittal / Ack / Obsolete**: `doc_control.*`
- **Finding/CAR/CAPA/RCA/Effectiveness**: `quality.*`
- **Training requirements/assignments/completions**: `training.*` plus linking tables
- **MOC**: new `quality_change` or `moc` module
- **Audit/event ledger**: new shared `compliance` module

---

## 4) State Machine Implementation Package

All transitions must be executed via services; direct router status assignment prohibited.

### 4.1 Manual revision

| From | To | Who | Required evidence | Fail-closed checks |
|---|---|---|---|---|
| Draft | InternalReview | Manual Owner / DCO | Change summary + impacted sections | revision exists in tenant |
| InternalReview | QAApproved | HOQ delegate | QA decision record | approver != creator |
| QAApproved | AuthorityApproved | HOQ/AM if regulated | authority evidence asset | regulated docs require evidence |
| QAApproved/AuthorityApproved | Released | HOQ/DCO with capability | LEP present, transmittal package, signatures | training gate pass if required |
| Released | Superseded | HOQ/DCO | replacement release reference | new release exists |
| Superseded | Archived | DCO | retention + archive marking | withdrawn confirmation complete |

### 4.2 Temporary revision

| From | To | Who | Evidence | Fail-closed |
|---|---|---|---|---|
| Draft | Approved | HOQ/DCO | rationale, expiry_date | expiry <= policy max |
| Approved | InForce | DCO | updated LEP/LOEP, transmittal | holders assigned |
| InForce | Incorporated | DCO/HOQ | incorporation revision ref | revision exists + released |
| InForce | Expired | System job/DCO | expiry reached | auto or manual expiry only |

### 4.3 Transmittal

| From | To | Who | Evidence | Fail-closed |
|---|---|---|---|---|
| Draft | Issued | DCO | recipient roster snapshot | recipient set immutable post-issue |
| Issued | PartialAck | System | at least one ack | n/a |
| PartialAck | FullAck | System | all required acks | all recipients acked |
| Issued/PartialAck | OverdueEscalated | System job | overdue SLA event | escalation policy exists |
| FullAck | Closed | DCO/HOQ | completion note | unresolved overdue blocks closure |

### 4.4 Acknowledgement

| From | To | Who | Evidence | Fail-closed |
|---|---|---|---|---|
| Pending | Acknowledged | Holder / delegate | acknowledgement text/signature/evidence | actor must be assigned recipient |
| Pending | Overdue | System job | due-date breach | n/a |
| Overdue | Escalated | System job | escalation stage record | policy + supervisor mapping required |

### 4.5 Obsolete withdrawal

| From | To | Who | Evidence | Fail-closed |
|---|---|---|---|---|
| SupersededMarked | WithdrawalPending | DCO | replacement ref | active distribution revoked |
| WithdrawalPending | WithdrawnConfirmed | Holder/DCO | withdrawal acknowledgement/evidence | all controlled copies confirmed |
| WithdrawnConfirmed | Archived | DCO | retention policy stamp | no active copy remains |

### 4.6 Finding/CAR

| From | To | Who | Evidence | Fail-closed |
|---|---|---|---|---|
| Open | Acknowledged | Responsible manager | acknowledgement note | assignee required |
| Acknowledged | RCAInProgress | Owner/quality | initial RCA plan | n/a |
| RCAInProgress | CAPAInProgress | HOQ/quality | approved RCA | RCA record complete |
| CAPAInProgress | Implemented | Action owner | implementation evidence | required actions complete |
| Implemented | EffectivenessPending | Quality verifier | verification plan | independent verifier enforced |
| EffectivenessPending | Closed | HOQ/verifier | effectiveness evidence | training gate pass if applicable |
| Closed | Reopened | HOQ/auditor | reopen reason | always logged as critical |

### 4.7 CAPA/RCA/effectiveness subflows
- CAPA and RCA should be separate stateful records linked to finding/CAR.
- Closure blocked until:
  - RCA approved,
  - CAPA actions complete,
  - effectiveness verified,
  - mandatory evidence attached.

### 4.8 Training gate
- `NOT_REQUIRED`, `REQUIRED_PENDING`, `REQUIRED_IN_PROGRESS`, `REQUIRED_SATISFIED`, `WAIVED`.
- Effective release or finding closure blocked unless state in `{NOT_REQUIRED, REQUIRED_SATISFIED, WAIVED}`.

### 4.9 MOC
- `Draft -> ImpactAssessed -> RiskReviewed -> Approved -> Implemented -> PostReviewed -> Closed`
- Block `Approved` without risk assessment and assigned owners.

---

## 5) Tenant Normalization Package

### 5.1 Tables requiring explicit `amo_id` (compliance-critical)

Priority add/verify in `apps/quality/models.py`:
- `qms_documents`
- `qms_document_revisions`
- `qms_document_distributions`
- `qms_audits`
- `qms_audit_findings`
- `quality_cars`
- `qms_notifications`
- related CAP/CAR response/action tables where missing

### 5.2 Migration plan
1. Add nullable `amo_id` columns + indexes.
2. Backfill logic:
   - Prefer direct source key (`audit.created_by_user_id -> users.amo_id`, `document.owner_user_id -> users.amo_id`).
   - For child rows inherit from parent entity.
   - Rows with unresolved tenant set to quarantine table and blocked from mutation.
3. Add not-null constraints after reconciliation.
4. Update uniques:
   - `uq_qms_doc_code` -> `uq_qms_doc_code_per_amo (amo_id, domain, doc_type, doc_code)`
   - `uq_qms_audit_ref` -> `uq_qms_audit_ref_per_amo (amo_id, domain, audit_ref)`
5. Update services/queries to include `amo_id` predicate always.

### 5.3 Rollback and risk
- Rollback: keep old columns untouched; drop added constraints/indexes first.
- Risks:
  - ambiguous historical rows without reliable actor linkage,
  - duplicate logical IDs across tenants revealed during unique migration.
- Mitigation: quarantine ambiguous rows + admin reconciliation tooling.

---

## 6) Immutable Audit Ledger Package

### 6.1 Table design
Create `compliance_event_ledger`:
- `id (uuid pk)`
- `amo_id`
- `entity_type`
- `entity_id`
- `action`
- `actor_user_id`
- `occurred_at`
- `payload_json`
- `payload_hash_sha256`
- `prev_hash_sha256`
- `signature_alg` (nullable)
- `signature_value` (nullable)
- `critical` boolean

Indexes:
- `(amo_id, occurred_at desc)`
- `(amo_id, entity_type, entity_id, occurred_at desc)`
- unique `(amo_id, id)`

### 6.2 Hash chaining
- `payload_hash = sha256(canonical_json(payload_json + metadata))`
- `prev_hash` is previous ledger hash for same `amo_id` stream (or partition per entity type for scale).
- Optional signature:
  - HMAC with server-managed key now,
  - future asymmetric signing for regulator export.

### 6.3 Transactional write policy
- For critical actions, DB transaction commits only if business row updates + ledger write both succeed.
- Critical actions include:
  - revision release/supersede/archive
  - TR in-force/incorporated/expired
  - transmittal issue/close
  - finding close/reopen
  - CAPA approve/close
  - effectiveness verify
  - restricted doc access override

### 6.4 Fail-on-ledger-write list (must fail)
- Any workflow action producing regulator-significant state change.

---

## 7) Restricted / Obsolete Document Guardrail Package

### 7.1 Restricted access controls
- Add `document_access_policies` + `document_access_grants`.
- Access decision requires:
  - capability check,
  - policy evaluation (role/postholder/state),
  - optional justification requirement.

### 7.2 Justification logging
- Add `document_access_justifications` table:
  - `amo_id, doc_id/revision_id, actor_user_id, action(view/download/export), reason_code, free_text, created_at`.
- Log to ledger as critical for restricted documents.

### 7.3 Watermark/download controls
- For restricted docs:
  - generate on-demand watermark overlay with user/time/copy notice,
  - disable raw direct-object links;
  - enforce signed short-lived URLs.

### 7.4 Obsolete operational lockout
- API list/read endpoints for active library must filter `status in active states only`.
- Superseded/archived served only from archive endpoints with elevated capability.
- UI must separate “Operational Library” and “Archive Register”.

---

## 8) Training-Gated Release Package

### 8.1 Schema additions
- `doc_control_revision_packages.requires_training` (bool)
- `doc_control_revision_packages.training_gate_policy` (enum: NONE, ALL_ASSIGNEES, ROLE_THRESHOLD, PERCENT_THRESHOLD)
- `training_requirements` link fields:
  - `source_type` (revision/finding)
  - `source_id`
  - `amo_id`
  - `required_by_date`
  - `blocking` bool

### 8.2 Enforcement checks
- On revision release/effective transition:
  - if `requires_training=true` and policy blocking -> verify `training_requirements` satisfied.
- On finding closure:
  - if finding references training requirement marked blocking, deny close until satisfied.

### 8.3 UI impact
- Revision pages show **Training Impact** panel.
- Closure/release actions show blocking reasons + unresolved assignees.
- Training pages show source-linked assignments and compliance status.

---

## 9) File-by-File Change Plan

### 9.1 Backend schema/migrations

1. `backend/amodb/alembic/versions/<new>_add_authorization_core_tables.py`
   - add role/capability/assignment/postholder/SoD tables.
   - non-breaking (additive), migration risk medium.

2. `backend/amodb/alembic/versions/<new>_normalize_quality_amo_id.py`
   - add/backfill `amo_id`, constraints, unique indexes.
   - breaking risk high if unresolved legacy rows.

3. `backend/amodb/alembic/versions/<new>_add_compliance_event_ledger.py`
   - append-only ledger table + indexes.
   - non-breaking (additive).

4. `backend/amodb/alembic/versions/<new>_add_training_gate_fields.py`
   - add training-gate fields and linkage tables.
   - non-breaking (additive).

### 9.2 Backend services

1. `backend/amodb/security.py`
   - add capability dependency factories and migration compatibility layer.
   - potentially breaking once routes switch to capability checks.

2. `backend/amodb/apps/doc_control/services.py` (new)
   - canonical state machines + evidence checks + ledger writes.
   - non-breaking if routes migrated incrementally.

3. `backend/amodb/apps/quality/services.py`
   - enforce CAR/RCA/CAPA/effectiveness transitions through strict services.
   - medium breaking risk if clients relied on direct status edits.

4. `backend/amodb/apps/audit/services.py`
   - integrate ledger writer for critical actions.
   - low breaking risk with fallback removed for critical paths.

5. `backend/amodb/apps/training/services.py` (new or extend)
   - resolve training gate checks and completion thresholds.
   - non-breaking additive.

### 9.3 Backend routers

1. `backend/amodb/apps/doc_control/router.py`
   - remove direct status mutation; call services; enforce capabilities.
   - breaking behavior change (intentional).

2. `backend/amodb/apps/quality/router.py`
   - route CAR/finding transitions through state machine service.
   - breaking behavior change (intentional).

3. `backend/amodb/apps/manuals/router.py`
   - align mutating actions to doc-control canonical workflow; read-only bridge where needed.
   - medium risk.

### 9.4 Frontend pages/components

1. `frontend/src/pages/DocControlPages.tsx`
   - action buttons state-aware, blocked actions show reasons.
2. `frontend/src/pages/QMSDocumentsPage.tsx`
   - remove unsupported direct edits; show canonical links.
3. `frontend/src/pages/QMSAuditsPage.tsx` and `QualityCarsPage.tsx`
   - enforce transition UX + evidence requirements.
4. `frontend/src/pages/QMSTrainingPage.tsx`
   - source-linked training gate visualization.
5. `frontend/src/pages/manuals/*`
   - display canonical status from doc-control release lifecycle.

### 9.5 Tests

1. `backend/amodb/apps/doc_control/tests/test_state_machine.py` (new)
2. `backend/amodb/apps/quality/tests/test_transition_guards.py` (new)
3. `backend/amodb/apps/accounts/tests/test_capability_authz.py` (new)
4. `backend/amodb/apps/audit/tests/test_compliance_ledger.py` (new)
5. `backend/amodb/apps/training/tests/test_training_gate.py` (new)
6. `frontend/tests/e2e/compliance-workflows.spec.ts` (new)

### 9.6 Jobs/worker/scheduler

1. `backend/amodb/jobs/compliance_escalation_runner.py` (new)
   - overdue ack/CAR/TR/OEM escalation rules.
2. Extend `backend/amodb/jobs/qms_task_runner.py`
   - call centralized escalation service.

---

## 10) Engineering Tickets (P0/P1 backlog)

## P0

1. **AUTHZ-P0-001: Introduce capability-based authorization core**
   - Objective: add role/capability/assignment tables and guard APIs.
   - Files: accounts models, security, new migration, key routers.
   - Acceptance: all compliance mutations require capabilities; legacy mode toggle works.
   - Dependencies: none.
   - Risks: migration mapping errors.

2. **TENANT-P0-002: Normalize `amo_id` across quality compliance tables**
   - Objective: enforce explicit tenant keys and constraints.
   - Files: quality models + migration + affected services.
   - Acceptance: no compliance query without `amo_id`; uniqueness enforced per tenant.
   - Dependencies: data backfill scripts.
   - Risks: ambiguous legacy rows.

3. **WF-P0-003: Implement doc-control revision/TR/transmittal state machines**
   - Objective: fail-closed transitions with evidence validation.
   - Files: new doc_control services + router updates.
   - Acceptance: invalid transitions/evidence missing => 4xx and no mutation.
   - Dependencies: AUTHZ-P0-001.
   - Risks: client flow breakage.

4. **LEDGER-P0-004: Add append-only compliance ledger with transactional critical writes**
   - Objective: immutable chain for regulator-significant events.
   - Files: migration + compliance service + integration points.
   - Acceptance: critical action fails if ledger write fails.
   - Dependencies: WF-P0-003.
   - Risks: performance overhead.

5. **GUARD-P0-005: Restricted and obsolete document hard lockout**
   - Objective: enforce restricted policy + archive-only access for obsolete docs.
   - Files: doc_control router/services, manuals read endpoints, frontend pages.
   - Acceptance: superseded docs absent from operational views; restricted access logged.
   - Dependencies: AUTHZ-P0-001, LEDGER-P0-004.
   - Risks: user friction if policies misconfigured.

6. **TRAIN-P0-006: Training-gated implementation/closure checks**
   - Objective: block revision effective implementation and finding closure when required training incomplete.
   - Files: doc_control/quality/training services + schema.
   - Acceptance: policy-blocking scenarios enforced by backend tests.
   - Dependencies: WF-P0-003.
   - Risks: migration of existing open findings/revisions.

## P1

7. **POST-P1-007: Postholder assignment and SoD policy engine**
8. **ESC-P1-008: Unified escalation scheduler and rule registry**
9. **DOM-P1-009: Canonical domain consolidation and deprecation adapters**
10. **CAR-P1-010: Full RCA/CAPA/effectiveness records and closure hardening**
11. **MOC-P1-011: Implement MOC workflow with risk/hazard linking**
12. **UI-P1-012: Compliance workbench UX for queues, blockers, evidence timelines**

---

## 11) Test Plan (automated)

### Tenant isolation
1. Cross-tenant read deny for each compliance endpoint.
2. Cross-tenant mutation deny for each transition endpoint.

### Authorization
3. Capability matrix tests per workflow action.
4. SoD tests: creator cannot self-approve/verify where prohibited.

### State machine/evidence
5. Invalid transition rejection tests for all state machines.
6. Evidence-required transition deny tests.

### Ledger integrity
7. Critical action fails when ledger insert fails.
8. Hash chain continuity test and tamper detection test.

### Training gate
9. Revision release/effective blocked when training incomplete.
10. Finding closure blocked when training requirement blocking=true and incomplete.

### Restricted/obsolete
11. Restricted doc requires justification and access grant.
12. Superseded doc hidden from operational endpoints, available only via archive endpoint + capability.

### Acknowledgement/escalation
13. Ack overdue transition/escalation job test.
14. CAR overdue escalation stage progression test.

### Frontend E2E
15. End-to-end revision release with training gate block then unblock.
16. End-to-end finding closure with RCA/CAPA/effectiveness evidence chain.

---

## 12) Build Now / Next / Defer

## Must build now (P0)
- Capability authz core, tenant normalization, state machines, immutable ledger, restricted/obsolete guardrails, training gate.

## Should build next (P1)
- Postholder/SoD full engine, escalation registry, canonical model consolidation, MOC, richer compliance UI.

## Can defer (post-P1)
- Advanced signature providers, regulator export pack automation, analytics/predictive compliance scoring.

### Known repo ambiguities and safe assumptions
1. **QMS vs Doc-Control canonical boundary** is currently overlapping.  
   Safe assumption: `doc_control` owns controlled-manual lifecycle; `manuals` is reader/presentation; `quality` owns audits/findings/CAR.
2. **Historical tenant attribution gaps** may exist in quality tables.  
   Safe assumption: quarantine unresolved rows and prevent mutation until reconciled.
3. **Role naming mismatch with requested business terms**.  
   Safe assumption: keep current enum for compatibility but enforce via new capability/postholder layers.

