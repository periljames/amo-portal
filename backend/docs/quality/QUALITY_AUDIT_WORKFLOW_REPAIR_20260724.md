# Quality Audit Workflow Repair Contract

**Date:** 24 July 2026  
**Branch:** `agent/quality-audit-workflow-repair`  
**Scope:** Quality module only

## 1. Collision boundary

This branch may change only Quality-owned backend, frontend, tests and Quality documentation. It must not modify Rostering, Workforce, Planning, Production, Document Control or Publications work owned by concurrent agents unless a shared-file change is unavoidable and explicitly documented in the pull request.

Shared files currently touched are limited to `frontend/src/main.tsx`, where the Quality PDF editor host is lazy-mounted. Any later shared-router or shell edits must be rebased immediately before commit.

## 2. Confirmed anomalies from the deployed UI

1. Audit-stage counts contradict each other. The left summary, Findings register, CAR workbench and Evidence page can report different totals for the same audit.
2. The audit-run page silently manufactures a frontend workflow when the authoritative workflow endpoint fails. That fallback sets finding/CAR counts to zero, marks CAR complete and infers completion from weak proxies.
3. The repository delivery document and the visible seven-stage frontend order disagree about the position of Report, CAR and Evidence. The backend transition and closeout rules must decide the canonical order; the UI must not maintain a separate interpretation.
4. The Checklist page exposes server filesystem paths and uses an oversized document viewer beside a cramped data-entry column.
5. Fillable PDF checklists can be viewed in the browser, but form edits were not persisted into the controlled checklist stored by the portal.
6. The public CAR invitation page requires browser zoom near 50% to display the complete response flow. Multiple unlocked stages are expanded simultaneously, and the sidebar creates a competing scroll container.
7. A closed CAR can still display an overdue countdown and disabled Edit controls as prominent actions.
8. The CAR workbench can show a closed CAR inside a `pending review` summary.
9. The public CAR page can state that an audit report has not been issued even when the internal audit workspace reports it as uploaded.
10. Evidence and Closeout are status placeholders rather than operational registers. Evidence lacks file source, linked finding/CAR, hash, uploader, verification and retention status. Closeout lacks named blockers, approvals, distribution confirmation and sign-off.

## 3. Authoritative data rule

The backend workflow response is the only source permitted to declare a stage complete, blocked or closable. Frontend-derived values may be shown as local operational counts, but they must never replace an unavailable workflow response.

When the authoritative workflow endpoint fails:

- show an explicit degraded-state error;
- do not display a fabricated completion percentage;
- do not mark CAR, Evidence, Report or Closeout complete;
- disable closeout mutation controls;
- preserve verified audit metadata and allow retry.

## 4. Fillable checklist PDF contract

The Checklist stage must support two valid working modes:

### Portal checklist rows

Users create, assign, complete and link checklist rows to findings. Rows remain structured records and participate directly in workflow readiness.

### Controlled PDF/Word source

Users upload a controlled source document. For PDF files containing AcroForm controls:

1. Render the PDF inside the portal with form fields enabled.
2. Keep the PDF.js annotation storage attached to the loaded document.
3. Warn before discarding unsaved field changes.
4. Save the completed PDF bytes through the authenticated checklist upload endpoint.
5. Refresh the audit workflow and checklist source after save.
6. Preserve a downloadable working copy.
7. Warn when the form uses XFA or embedded JavaScript because browser behaviour may differ from a desktop PDF application.
8. Do not claim that a non-form PDF is editable; retain the standard viewer and portal checklist rows.

The first implementation is in `QualityChecklistPdfFormEditorHost.tsx` and uses the existing `react-pdf`/PDF.js dependencies. It does not add a second PDF library.

## 5. Public CAR invite layout contract

The public response page must be fully usable at 100% browser zoom on a 1366×768 display.

- Show one active response stage at a time; use the stage rail for navigation.
- Use one primary page scroll. Do not create a full-height nested sidebar scroll.
- Keep identity, containment, root cause, corrective action, evidence and preview available without shrinking text.
- When a CAR is closed, show the immutable submitted response and history but remove active overdue treatment and edit affordances.
- Keep mobile and tablet fallbacks without horizontal scrolling.

## 6. Backend review sequence

1. Map every audit route and mutation to its owning service and permission dependency.
2. Verify tenant scoping for audit, schedule, finding, CAR, attachment, report, evidence pack and archive queries.
3. Trace schedule creation → audit start → checklist → findings → report/CAR/evidence → closeout.
4. Compare backend workflow checks with UI stage labels and Next/Back gating.
5. Confirm report locking rules and whether report issuance legally/business-wise precedes CAR response.
6. Confirm CAR state transitions, evidence requirements, finding closure synchronization and task closure.
7. Remove production request-time DDL after strict migration preflight is enforced.
8. Add failure tests for cross-tenant access, illegal transitions, missing evidence and stale workflow data.

## 7. Frontend repair sequence

1. Remove silent workflow fabrication.
2. Extract a shared audit workspace shell and one component per stage.
3. Replace filesystem references with sanitized filenames and controlled metadata.
4. Make Checklist a full-width split workbench with resizable source and structured rows.
5. Rebuild Findings as a working register with creation, classification, evidence, CAR linkage and lock reasons.
6. Rebuild CARs around actual transition state and review queues.
7. Rebuild Evidence as a searchable inventory.
8. Rebuild Closeout as a backend-derived blocker checklist plus authorized sign-off.
9. Verify all buttons against capabilities and record state; do not expose dead or permanently disabled actions without explanation.
10. Add Playwright scenarios for an AMO administrator, auditor and external auditee.

## 8. Acceptance gate

The branch is not ready to merge until:

- Quality contract check passes;
- TypeScript production build passes;
- canonical Quality frontend tests pass;
- targeted Quality backend tests pass;
- the seven audit stages are exercised against PostgreSQL;
- the public CAR page is tested at 100% zoom on desktop and mobile;
- a fillable AcroForm PDF is edited, saved, downloaded again and verified to contain the entered values;
- an authenticated Tailnet browser run confirms the deployed AMO-admin workflow;
- the branch is rebased on current `main` and contains no unrelated module changes.
