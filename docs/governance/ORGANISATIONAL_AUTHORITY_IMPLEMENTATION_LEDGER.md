# Organisational authority implementation ledger

Repository: `periljames/amo-portal`. Branch: `feat/enterprise-organisation-authority-qms`.
Baseline: `d760894749bb9154ccf06c6fefb6046bdc3a197e`. Phase 1: IN PROGRESS.
PR: [#575](https://github.com/periljames/amo-portal/pull/575), DRAFT, targeting `main`. Frontend implementation/testing has not started.
User constraint: all frontend testing must use the live portal on this computer.

## Checkpoint changes

All listed changes are IMPLEMENTED â€” UNVERIFIED. No whole phase is complete.
Paths below are relative to `backend/amodb/apps/` unless stated otherwise.

| Change | Responsibility / canonical owner | Modified / created | Retired / replacement | Migration / consumers | Remaining work |
| --- | --- | --- | --- | --- | --- |
| C1 | Effective QMS grants; Accounts access_control | Modified `accounts/access_control.py`, `accounts/access_router.py`; created `accounts/tests/test_effective_capability.py` | Primary-only QMS lookup and administrative QMS overlay replaced with effective persisted grants | Existing tables reused. `quality/tenant_security.py`, session capability presentation and `user_has_capability` updated | Tenant grant reconciliation, wider scope model, explicit authorities/delegation, entitlements and domain decision gates |
| C2 | Shared QMS tenant permission boundary | Modified `quality/tenant_security.py`, `quality/__init__.py` and relevant Accounts/Quality contract tests | Deleted `quality/assurance_permissions.py`; removed `_QUALITY_ROLE_PERMISSIONS`, `_has_role_permission`, wildcard matching and role fallback; persisted Accounts evaluator replaces them | No schema change. Dependency/imperative checks share the evaluator; auditor read-only template grants consolidated into Accounts | Full domain-local bypass audit and passing tests required |
| C3 | Current reporting resolution; Workforce supervisor_governance | Modified `workforce/supervisor_governance.py`, `governance_schemas.py`, `governance_router.py`; created `workforce/tests/test_reporting_resolution.py` | No files deleted; adds resolution to existing supervisor owner | Existing units/positions/placements reused; `GET /workforce/hr/organogram` added to existing router | Historical topology, readiness detail, full placement-writer consolidation and integration with decision routing |
| C4 | Governed organisation mutations | Modified `workforce/governance_directory.py`, `governance_mutations.py`, `supervisor_governance.py` | Supervisor overwrite replaced with effective-dated placement replacement; fixes missing `access_control` import and replacement-date flush ordering | Existing fields reused; catalogue/bulk mutation writers acquire tenant lock; supervisor requires canonical parent/base/unit scope | Other onboarding/contract writers and PostgreSQL concurrency verification |
| C5 | Programme continuity | Created baseline, ledger, interim verification and PR metadata inventory under `docs/governance/` | No architecture proposal substituted for implementation | Documentation only | Keep updated on same branch/PR |

## API contracts introduced

- Existing Accounts context router: `GET /access-context/evaluate?capability=...&department_id=...`
  returns `{allowed, code, assignment_ids}` for the signed-in user. This explains
  grants; it does not authorize an actual record decision or bypass domain gates.
- Existing Workforce governance router: `GET /workforce/hr/organogram` returns current
  positions/holders/vacancies, resolved reporting chains, functional manager results
  and unresolved users. Uses existing sensitive-Workforce viewing permission.
- QMS permission functions now fail closed for undefined/unassigned capabilities,
  foreign/inactive profiles, expired assignments and unresolved binding constraints.
- Protected decisions require an active dated Workforce appointment whose position
  references the granting access profile. Admin/support privilege is insufficient.
- Department grants require explicit matching department context; no global flattening.

## Requirement tracking

Statuses apply to the complete numbered responsibility. A partial implementation
is IN PROGRESS even where one of C1â€“C5 exists. Verification is NOT STARTED throughout.

| Requirement | Responsibility | Owner / changes | Implementation | Verification | Remaining blocker or next responsibility |
| --- | --- | --- | --- | --- | --- |
| 1.1 | Establish authoritative ownership | C5; existing packages | IN PROGRESS | NOT STARTED | Complete remaining acceptance criteria; see C1â€“C5 and interim verification |
| 1.2 | Canonical organisation model | C3/C4; Workforce | IN PROGRESS | NOT STARTED | Complete remaining acceptance criteria; see C1â€“C5 and interim verification |
| 1.3 | Reconcile the competing organisational representations | C3/C4; Workforce | IN PROGRESS | NOT STARTED | Complete remaining acceptance criteria; see C1â€“C5 and interim verification |
| 1.4 | Organogram resolver | C3; Workforce | IN PROGRESS | NOT STARTED | Complete remaining acceptance criteria; see C1â€“C5 and interim verification |
| 1.5 | Organisation configuration templates | Existing domain owner to inspect | NOT STARTED | NOT STARTED | Implement in sequence after preceding responsibilities |
| 1.6 | Remodel RBAC into a unified effective-authority system | C1; Accounts | IN PROGRESS | NOT STARTED | Complete remaining acceptance criteria; see C1â€“C5 and interim verification |
| 1.7 | Critical correction â€” QMS tenant security | C1/C2; Quality | IN PROGRESS | NOT STARTED | Complete remaining acceptance criteria; see C1â€“C5 and interim verification |
| 1.8 | Effective access evaluation | C1; Accounts | IN PROGRESS | NOT STARTED | Complete remaining acceptance criteria; see C1â€“C5 and interim verification |
| 1.9 | Organisational authority and delegation | Existing domain owner to inspect | NOT STARTED | NOT STARTED | Implement in sequence after preceding responsibilities |
| 1.10 | Consolidate the existing workflow engine | Existing domain owner to inspect | NOT STARTED | NOT STARTED | Implement in sequence after preceding responsibilities |
| 1.11 | Workflow persistence | Existing domain owner to inspect | NOT STARTED | NOT STARTED | Implement in sequence after preceding responsibilities |
| 1.12 | Approval routing | Existing domain owner to inspect | NOT STARTED | NOT STARTED | Implement in sequence after preceding responsibilities |
| 1.13 | Workflow execution integrity | Existing domain owner to inspect | NOT STARTED | NOT STARTED | Implement in sequence after preceding responsibilities |
| 1.14 | Integrate audit programme approval | Existing domain owner to inspect | NOT STARTED | NOT STARTED | Implement in sequence after preceding responsibilities |
| 1.15 | Integrate live audit and controlled audit workflows | Existing domain owner to inspect | NOT STARTED | NOT STARTED | Implement in sequence after preceding responsibilities |
| 1.16 | Integrate CAR, CAPA and RCA workflows | Existing domain owner to inspect | NOT STARTED | NOT STARTED | Implement in sequence after preceding responsibilities |
| 1.17 | Integrate personnel authorisation and competence | Existing domain owner to inspect | NOT STARTED | NOT STARTED | Implement in sequence after preceding responsibilities |
| 1.18 | Integrate remaining controlled QMS decisions | Existing domain owner to inspect | NOT STARTED | NOT STARTED | Implement in sequence after preceding responsibilities |
| 1.19 | Integrate DMS authority without duplicating DMS lifecycle | Existing domain owner to inspect | NOT STARTED | NOT STARTED | Implement in sequence after preceding responsibilities |
| 1.20 | Organisation changes and pending workflow responsibility | Existing domain owner to inspect | NOT STARTED | NOT STARTED | Implement in sequence after preceding responsibilities |
| 1.21 | Approval task and notification delivery | Existing domain owner to inspect | NOT STARTED | NOT STARTED | Implement in sequence after preceding responsibilities |
| 1.22 | Role-aware dashboard APIs | Existing domain owner to inspect | NOT STARTED | NOT STARTED | Implement in sequence after preceding responsibilities |
| 1.23 | API contracts | C1/C3; existing routers | IN PROGRESS | NOT STARTED | Complete remaining acceptance criteria; see C1â€“C5 and interim verification |
| 1.24 | Migrations and data reconciliation | Existing domain owner to inspect | NOT STARTED | NOT STARTED | Implement in sequence after preceding responsibilities |
| 1.25 | Backend consolidation and deletion gate | C2; Quality | IN PROGRESS | NOT STARTED | Complete remaining acceptance criteria; see C1â€“C5 and interim verification |
| 1.26 | Phase 1 completion criteria | Existing domain owner to inspect | NOT STARTED | NOT STARTED | Implement in sequence after preceding responsibilities |
| 2.1 | Confirm backend continuity | Existing domain owner to inspect | NOT STARTED | NOT STARTED | Implement in sequence after preceding responsibilities |
| 2.2 | Inspect and remodel User Management | Existing domain owner to inspect | NOT STARTED | NOT STARTED | Implement in sequence after preceding responsibilities |
| 2.3 | Interactive organogram | Existing domain owner to inspect | NOT STARTED | NOT STARTED | Implement in sequence after preceding responsibilities |
| 2.4 | Guided employee onboarding | Existing domain owner to inspect | NOT STARTED | NOT STARTED | Implement in sequence after preceding responsibilities |
| 2.5 | Organisation readiness | Existing domain owner to inspect | NOT STARTED | NOT STARTED | Implement in sequence after preceding responsibilities |
| 2.6 | Effective-access inspector | Existing domain owner to inspect | NOT STARTED | NOT STARTED | Implement in sequence after preceding responsibilities |
| 2.7 | Approval policy editor | Existing domain owner to inspect | NOT STARTED | NOT STARTED | Implement in sequence after preceding responsibilities |
| 2.8 | Delegation and organisational changes interface | Existing domain owner to inspect | NOT STARTED | NOT STARTED | Implement in sequence after preceding responsibilities |
| 2.9 | Remodel the QMS application shell | Existing domain owner to inspect | NOT STARTED | NOT STARTED | Implement in sequence after preceding responsibilities |
| 2.10 | Remove redundant frontend role evaluation | Existing domain owner to inspect | NOT STARTED | NOT STARTED | Implement in sequence after preceding responsibilities |
| 2.11 | QMS Manager's workspace | Existing domain owner to inspect | NOT STARTED | NOT STARTED | Implement in sequence after preceding responsibilities |
| 2.12 | QMS Officer's workspace | Existing domain owner to inspect | NOT STARTED | NOT STARTED | Implement in sequence after preceding responsibilities |
| 2.13 | Accountable Executive workspace | Existing domain owner to inspect | NOT STARTED | NOT STARTED | Implement in sequence after preceding responsibilities |
| 2.14 | Multiple appointments and workspace selection | Existing domain owner to inspect | NOT STARTED | NOT STARTED | Implement in sequence after preceding responsibilities |
| 2.15 | Approval centre and work inbox | Existing domain owner to inspect | NOT STARTED | NOT STARTED | Implement in sequence after preceding responsibilities |
| 2.16 | Shared approval experience across QMS | Existing domain owner to inspect | NOT STARTED | NOT STARTED | Implement in sequence after preceding responsibilities |
| 2.17 | Wire audit programme interfaces | Existing domain owner to inspect | NOT STARTED | NOT STARTED | Implement in sequence after preceding responsibilities |
| 2.18 | Wire live audit interfaces | Existing domain owner to inspect | NOT STARTED | NOT STARTED | Implement in sequence after preceding responsibilities |
| 2.19 | Wire CAR and RCA interfaces | Existing domain owner to inspect | NOT STARTED | NOT STARTED | Implement in sequence after preceding responsibilities |
| 2.20 | Wire personnel authorisation and other QMS modules | Existing domain owner to inspect | NOT STARTED | NOT STARTED | Implement in sequence after preceding responsibilities |
| 2.21 | Wire DMS authority | Existing domain owner to inspect | NOT STARTED | NOT STARTED | Implement in sequence after preceding responsibilities |
| 2.22 | Frontend cache and context integrity | Existing domain owner to inspect | NOT STARTED | NOT STARTED | Implement in sequence after preceding responsibilities |
| 2.23 | UX and design standards | Existing domain owner to inspect | NOT STARTED | NOT STARTED | Implement in sequence after preceding responsibilities |
| 2.24 | Frontend route and ghost-page purge | Existing domain owner to inspect | NOT STARTED | NOT STARTED | Implement in sequence after preceding responsibilities |
| 2.25 | Phase 2 completion criteria | Existing domain owner to inspect | NOT STARTED | NOT STARTED | Implement in sequence after preceding responsibilities |
| 3.1 | Establish continuity | Existing domain owner to inspect | NOT STARTED | NOT STARTED | Implement in sequence after preceding responsibilities |
| 3.2 | Database and migration verification | Existing domain owner to inspect | NOT STARTED | NOT STARTED | Implement in sequence after preceding responsibilities |
| 3.3 | Backend testing | Existing domain owner to inspect | NOT STARTED | NOT STARTED | Implement in sequence after preceding responsibilities |
| 3.4 | Organisation and authority test matrix | Existing domain owner to inspect | NOT STARTED | NOT STARTED | Implement in sequence after preceding responsibilities |
| 3.5 | Approval workflow test matrix | Existing domain owner to inspect | NOT STARTED | NOT STARTED | Implement in sequence after preceding responsibilities |
| 3.6 | Aviation operational workflow verification | Existing domain owner to inspect | NOT STARTED | NOT STARTED | Implement in sequence after preceding responsibilities |
| 3.7 | External access verification | Existing domain owner to inspect | NOT STARTED | NOT STARTED | Implement in sequence after preceding responsibilities |
| 3.8 | Frontend verification | Existing domain owner to inspect | NOT STARTED | NOT STARTED | Implement in sequence after preceding responsibilities |
| 3.9 | Real browser acceptance | Existing domain owner to inspect | NOT STARTED | NOT STARTED | Implement in sequence after preceding responsibilities |
| 3.10 | Route, navigation and ghost-page verification | Existing domain owner to inspect | NOT STARTED | NOT STARTED | Implement in sequence after preceding responsibilities |
| 3.11 | Performance verification | Existing domain owner to inspect | NOT STARTED | NOT STARTED | Implement in sequence after preceding responsibilities |
| 3.12 | CI verification and repair | Existing domain owner to inspect | NOT STARTED | NOT STARTED | Implement in sequence after preceding responsibilities |
| 3.13 | Final architectural consolidation | Existing domain owner to inspect | NOT STARTED | NOT STARTED | Implement in sequence after preceding responsibilities |
| 3.14 | Final documentation | Existing domain owner to inspect | NOT STARTED | NOT STARTED | Implement in sequence after preceding responsibilities |

## Checks and continuation

Only repository/source inspection, dependency/reference inspection, AST syntax
parsing, a narrow router/package import check and `git diff --check` have run. No functional test result is claimed.
The removed role-map consumers were traced and updated; no frontend test ran.

Next: remain in Phase 1. Read this ledger and actual diff/HEAD first. Inspect all
remaining organisational writers and reconcile existing tenant grants before
strict QMS deployment. Extend the existing workflow package with persisted,
versioned approval orchestration and reuse Tasks/Notifications. Add migrations
and integrate canonical QMS/DMS domain decision owners. Complete Phase 1 before
starting frontend work. Phase 3 alone executes comprehensive backend/security
verification; frontend verification must be live on this computer.

No merge, deployment or production acceptance is authorized by this ledger.

## Committed checkpoints

- `2ce640c755a5472de24d38e2d46c231ded9fd693`: initial scoped-QMS/reporting implementation;
  pushed to the programme branch and opened as draft PR #575.
- `e94ad1eeaf65c62671211e779b234585f27550f8`: protected decisions also block
  overlapping effective primary appointments; organogram includes active people
  with missing appointments.
- Source API-contract comparison inspected 36 distinct QMS capability literals
  at shared gates; each appeared in the Accounts capability owner. This is source
  inspection only, not runtime authorization verification.
- No migration introduced. Existing tenant grant reconciliation remains a
  deployment blocker. No backend suite, frontend suite, CI polling or live UI
  acceptance was performed. Working HEAD is obtained from `git rev-parse HEAD`.
