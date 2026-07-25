# Quality Audit War Room and Checklist Lifecycle Contract

**Status:** implementation reference and non-negotiable acceptance contract  
**Scope:** Quality module only  
**Branch:** `agent/quality-war-room-checklist-lifecycle`  
**Date:** 24 July 2026

## 1. Purpose

This document is the source of truth for the Quality audit workspace changes that follow the first audit-workflow repair. It exists to prevent the portal from drifting back into visually complete but operationally false states.

The intended user is an auditor. The workspace must answer four questions without forcing the auditor to interpret implementation details:

1. What is this audit and what is expected?
2. What must I do next?
3. What happened in the previous comparable audit?
4. What evidence proves that each controlled stage is complete?

The portal must never represent file presence, page navigation, or an empty register as proof that audit work has been completed.

## 2. Collision boundary

Only Quality-owned surfaces may be changed:

- `backend/amodb/apps/quality/**`
- `backend/amodb/alembic/versions/**` for Quality migrations
- `backend/docs/quality/**`
- `frontend/src/pages/QualityAuditRunHubPage.tsx`
- `frontend/src/pages/qualityAudits/**`
- `frontend/src/components/QMS/**`
- `frontend/src/services/qms.ts`
- `frontend/src/styles/quality-*.css`
- Quality-specific tests and the existing Quality host mount

Do not modify Rostering, Workforce, Planning, Production, Maintenance execution, Publications, SaaS control-plane, or shared platform behavior unless a narrowly scoped Quality integration contract requires a read-only call.

## 3. Core invariants

### 3.1 Authoritative state

- The backend is the only authority for stage state.
- The frontend may not mark earlier tabs complete merely because the user navigated forward.
- A workflow read failure places the workspace in explicit safe read-only mode.
- `percent_complete` is derived from completed controlled stages only.
- A future planned audit may show readiness, but it may not show fieldwork, findings, CAR, evidence, report, or closeout completion.

### 3.2 Stage order

The controlled lifecycle is:

1. War room
2. Checklist
3. Findings
4. CARs
5. Evidence
6. Report
7. Closeout

The report is produced after the audit team has completed fieldwork, issued required CARs, and assembled the evidence record. CAR responses may continue after report issue; final CAR closure is a closeout requirement.

### 3.3 Stage states

Every stage uses one of these states:

- `NOT_READY`
- `READY`
- `IN_PROGRESS`
- `BLOCKED`
- `COMPLETE`
- `LOCKED`

Each stage response includes:

- `state`
- `complete`
- `blockers[]`
- `warnings[]`
- `completed_at`
- `completed_by_user_id`
- `primary_action`
- `metric`

### 3.4 Stage rules

#### War room

Ready when scope, criteria, schedule, auditee, and lead auditor are present.

Complete only when the audit is formally started and the opening brief is recorded. Notice dispatch alone does not complete the War room.

#### Checklist

Ready when a controlled source or structured portal checklist exists.

Complete only when all required structured rows are answered or a committed fillable-PDF version exists and the assigned audit team explicitly marks the checklist complete.

Uploading a blank source document does not complete the checklist.

#### Findings

In progress while fieldwork is open.

Complete only after an explicit fieldwork-completion action records `actual_end` and confirms that all checklist exceptions have been dispositioned. Report upload must not complete Findings.

#### CARs

Ready when Findings is complete.

Complete for report progression when every Level 1-3 non-conformity has a valid issued CAR. Open CAR responses remain visible and continue after report issue.

#### Evidence

Complete only after mandatory checklist, finding, and CAR evidence has been reviewed. File presence alone is not verification.

Evidence uses `PENDING`, `ACCEPTED`, or `REJECTED` verification status.

#### Report

Complete when a controlled report version is formally issued. A raw uploaded draft does not equal an issued report.

Store issue number/version, issuer, issue time, filename, hash, and distribution state.

#### Closeout

Complete only when required CARs are closed, evidence and effectiveness are verified, closure approval is recorded, and an archive package is generated.

## 4. War room design

### 4.1 Context rail

The left rail is factual and compact. It contains only:

- Audit title and reference
- Lifecycle status
- Planned and actual dates
- Auditee
- Lead auditor and compact team avatars
- Scope code
- Location when available

Remove duplicated progress counters, percentage badges, and tab-derived “next best action” content from the rail.

### 4.2 Command strip

The War room begins with one compact command strip containing:

- Lifecycle state
- Start date/countdown
- Notice acknowledgement state
- Checklist readiness
- Previous-audit review state
- One authoritative primary action

No closeout shortcut is shown before the audit reaches closeout readiness.

### 4.3 Audit brief

The Audit brief panel exposes:

- Objective
- Scope
- Criteria
- Referenced regulations/manual procedures
- Auditee and location
- Planned sampling areas
- Team assignments
- Conflicts, leave, training, and availability warnings
- Opening meeting date/time

### 4.4 Previous audit intelligence

The War room must show the latest comparable completed audit when one exists.

Matching priority:

1. Same tenant
2. Same `audit_scope_id`
3. Same auditee user or normalized auditee organization/email domain
4. Most recent completed/closed audit with an issued report
5. Exclude the current and deleted audits

The panel shows:

- Audit reference and title
- Closure/report issue date
- Lead auditor
- Total findings
- Open carryovers
- Possible repeated findings
- Previous issued report action
- Compare findings action
- Carryover CAR action

Repeat-finding detection is advisory. It first matches normalized requirement references and may use conservative text similarity as a secondary signal. The portal must not automatically classify a finding as repeated without auditor confirmation.

### 4.5 Auditor action queue

The action queue includes owner, due state, and completion state for:

- Review previous report
- Review carryover findings/CARs
- Confirm scope and criteria
- Confirm team availability
- Confirm notice acknowledgement
- Confirm checklist source and revision
- Record opening meeting
- Begin fieldwork

### 4.6 Communications

The War room shows actual notice history:

- Notice issued
- Email/portal dispatch state
- Auditee acknowledgement
- Reminder events
- Actor and timestamps

Explanatory copy such as “notices are sent through the backend” is not a substitute for event state.

## 5. War room backend contract

Endpoint:

```http
GET /quality/audits/{audit_id}/war-room-context
```

Response includes:

```json
{
  "audit": {},
  "workflow": {},
  "readiness": {
    "ready": false,
    "blockers": [],
    "warnings": []
  },
  "previous_audits": [],
  "carryover_findings": [],
  "notice_history": [],
  "action_queue": []
}
```

The endpoint is tenant-scoped and uses existing Quality audit-access rules.

Required indexes:

- `(amo_id, audit_scope_id, actual_end)`
- `(amo_id, auditee_user_id, actual_end)`
- `(amo_id, status, actual_end)`

## 6. Controlled checklist lifecycle

### 6.1 No raw storage paths

No API response may expose a local filesystem path. Frontend contracts receive document metadata and controlled download URLs only.

### 6.2 Version model

A controlled checklist is versioned. Saving a filled PDF creates a new retained version and never deletes the original source.

Required fields:

- `id`
- `amo_id`
- `audit_id`
- `version_number`
- `parent_version_id`
- `filename`
- `storage_key`
- `content_type`
- `size_bytes`
- `sha256`
- `source_type`
- `fillable`
- `field_count`
- `lifecycle_status`
- `uploaded_by_user_id`
- `created_at`
- `committed_at`
- `superseded_at`

Lifecycle values:

- `SOURCE`
- `WORKING_DRAFT`
- `COMMITTED`
- `SUPERSEDED`
- `RETAINED`

### 6.3 Separate actions

These are distinct controlled actions:

- Upload controlled source
- Save working draft
- Commit checklist version
- Mark checklist complete
- View version history
- Download retained version

Do not use one overwrite endpoint for all actions.

### 6.4 Fillable PDF behavior

For a fillable PDF:

- The form editor is integrated into the checklist toolbar.
- AcroForm fields are interactive.
- Field count is visible in the parent page.
- Dirty state and save result are visible.
- Saving creates a retained working/committed version.
- The portal displays `PDF fields`, `portal notes`, and `checklist status` separately.

For a non-fillable source:

- Show source document plus structured portal responses.

For no source document:

- Hide the viewer and give the manual checklist builder full width.

### 6.5 Immutability

The UI and backend both prevent mutation when:

- Audit status is `CLOSED`
- The report is formally issued
- The current user lacks assigned audit-team or Quality-admin permission

The lock reason is shown before mutation is attempted.

## 7. Report lifecycle

A report document must distinguish:

- Uploaded draft
- Issued version
- Superseded version
- Retained version

Issue metadata includes:

- Filename
- Version/issue number
- SHA-256
- Issued at
- Issued by
- Distribution status

Previous-audit intelligence only exposes a report as “issued” when formal issue metadata exists.

## 8. Frontend layout contract

- Context rail: 260-280 px
- Main workspace: remaining width
- 12-column War room grid
- Main panel gap: 12 px
- Panel padding: 14-16 px
- One visible border per section
- No box-inside-box presentation where a simple row works
- One primary vertical page scroll
- Normal browser zoom target: 100%
- Desktop baseline: 1366×768 without forced page zoom

The PDF form launcher must not float independently at the top right of the page.

## 9. API compatibility

Legacy `checklist_file_ref` and `report_file_ref` may remain internal compatibility fields while migration is in progress, but new workspace APIs must return document DTOs and never render those raw values.

Existing routes remain functional until all callers have migrated. Compatibility routes must write version records and retain historical files.

## 10. Tests and acceptance criteria

The work is incomplete until all of the following pass:

1. A planned audit starting in the future cannot show Findings, CARs, Evidence, Report, or Closeout complete because files exist.
2. Browsing later tabs does not alter completion state.
3. The backend returns the seven-stage order defined here.
4. The War room shows the latest comparable previous audit when available.
5. The previous issued report can be opened through a tenant-scoped authenticated route.
6. Carryover findings and CARs are visible.
7. No API or screen exposes server filesystem paths.
8. A fillable PDF displays its actual interactive field count.
9. Saving a filled PDF creates a new retained version and does not delete the original.
10. The UI distinguishes source upload, draft save, commit, and checklist completion.
11. Report-issued and closed audits are visibly read-only before mutation.
12. The authoritative primary action is derived from backend lifecycle state, not the viewed tab.
13. Evidence verification state is explicit.
14. Report issue metadata is explicit.
15. Closeout requires CAR closure, evidence/effectiveness verification, approval, and archive generation.
16. Backend tests, Alembic upgrade, frontend typecheck/build, Quality tests, and lint pass.
17. Tailnet browser verification is completed at 100% zoom on the audit War room and Checklist.

## 11. Implementation checklist

- [ ] Add lifecycle stage states and authoritative blockers/warnings/actions
- [ ] Correct workflow stage order and completion rules
- [ ] Add War room context endpoint
- [ ] Add previous-audit matching and carryover summaries
- [ ] Add controlled report metadata
- [ ] Add versioned checklist document model and migration
- [ ] Preserve existing checklist files as retained versions
- [ ] Add checklist metadata/history/download routes
- [ ] Separate draft save, commit, and completion actions
- [ ] Remove raw paths from workspace DTOs
- [ ] Rebuild War room frontend
- [ ] Integrate PDF form controls into checklist toolbar
- [ ] Remove navigation-index completion logic
- [ ] Add backend and frontend regression tests
- [ ] Run full Quality verification and browser checks
