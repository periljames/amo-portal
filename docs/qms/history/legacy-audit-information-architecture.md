# Audit Assurance IA reconstruction — engineering report

Date: 2026-08-25  
Tenant: safarilink @ http://127.0.0.1:5173  
Commit status: **uncommitted** (per standing instruction)

## 1. Files changed

### Navigation / shell
- `frontend/src/pages/qualityAudits/QualityAuditsSectionLayout.tsx` — peer AA nav: Overview | Programme | Calendar | Audits | Findings & Actions; Schedule tools under Tools
- `frontend/src/components/QMS/QualityContextTabs.tsx` — Cases not dual-active on AA surfaces
- `frontend/src/pages/qms/QmsCanonicalPage.tsx` — Calendar chrome (title/subtitle)

### Programme
- `frontend/src/pages/qms/QmsAuditProgrammePageV2.tsx` — Summary | Coverage | Requirements | Risk & Frequency | Approval & Changes; *-based methodology labels; Calendar-owned date copy; risk/frequency table

### Occurrence shell / stages
- `frontend/src/features/qms/auditSession/AuditLifecycleRail.tsx` — progress rail + functional tabs; Fieldwork label
- `frontend/src/features/qms/auditSession/auditSessionRoutes.ts` — functional tab helpers
- `frontend/src/styles/qms-audit-session.css` — progress + functional tab styles
- `frontend/src/features/qms/auditSession/AuditPrepareWorkspace.tsx` — 0/0 → null percent / N/A
- `frontend/src/features/qms/auditSession/LiveAuditWorkspace.tsx` — empty checklist ≠ 100%
- `frontend/src/features/qms/auditSession/ExternalAuditorFieldworkWorkspace.tsx` — same guard
- `frontend/src/features/qms/auditSession/AuditClosingWorkspace.tsx` — progressive disclosure
- `frontend/src/styles/qms-audit-closing-workspace.css` — current/complete/locked card styles

### Audits / Findings / Overview
- `frontend/src/pages/qualityAudits/QualityAuditsWorkspacePage.tsx`, `auditsWorkspaceModel.ts` (+ tests)
- `frontend/src/pages/qualityAudits/auditNextAction.ts` (+ tests)
- `frontend/src/pages/qualityAudits/findingLifecycle.ts` (+ tests)
- `frontend/src/pages/qualityAudits/QualityAuditRegisterPage.tsx`
- `frontend/src/pages/qualityAudits/QualityAuditAssuranceDashboardPage.tsx` — Calendar-oriented CTAs

## 2. Routes changed

No new top-level routes. Canonical AA destinations:

| IA | Path |
| --- | --- |
| Overview | `/maintenance/:amo/quality/audits/dashboard` |
| Programme | `/maintenance/:amo/quality/audits/program` |
| Calendar | `/maintenance/:amo/quality/calendar/week` |
| Audits | `/maintenance/:amo/quality/audits/workspace` |
| Findings & Actions | `/maintenance/:amo/quality/audits/register?tab=findings` |

Occurrence stages unchanged: `…/audits/:key/{setup|prepare|live|closing|follow-up|archive}`.

## 3. Components added

- Occurrence functional tabs (Overview / Checklist / Evidence / Findings / Team / Report) on lifecycle rail
- Programme Risk & Frequency panel (reuses existing item/optimizer fields)
- Closing progressive-disclosure helpers (`activeClosingStep`, `closingCardClass`, `lockedReason`)

## 4. Components removed / demoted

- Plan→segment nesting removed (Programme + Calendar are peers)
- Create/run demoted to **Schedule tools** under Tools (route kept)
- Cases dual-active on AA surfaces removed (Tools / overflow only)

## 5. Backend / API changes

None. Existing programme, calendar (Planner V2 engine), occurrence resolver, findings/CAR APIs reused.

## 6. Schema / migrations

None.

## 7. Programme → Requirement → Calendar → Audit linkage

- Requirements remain independent of occurrences; scheduling opens Calendar/schedule flows
- UI copy treats Calendar as date authority
- Unscheduled-queue left panel polish is partial (engine exists; IA chrome updated)

## 8. Audit lifecycle UX

- Rail = progress + next-stage CTA; functional tabs underneath
- Prepare/Live never treat 0/0 as 100%
- Closing downstream gates locked until prerequisites met (UI)

## 9. Findings / CAR integration

- Findings & Actions filters: All | Awaiting Response | RCA/CAP | Implementation | Effectiveness | Closed
- Default **All** so Live-raised OPEN CAR findings stay discoverable

## 10. Error-handling changes

- Stage resolve failures retain bounded error UI
- Closing locked reasons explain blocked steps
- Zero-denominator readiness messaging
- **Live HTTP 500 (resolved)** — root cause was presence heartbeat routed through Quality catch-all, not checklist serialization. Presence routes promoted; heartbeat toasts silenced. Checklist empty = prerequisite (no template bound), not a 500. See `contracts/ROOT_CAUSES.md` ([Root-cause Live 500 + findings gap](097cdf1d-499b-41ac-95bf-7b0972885ede)).
- **Findings “Needs review” empty** — filter correctness: closed findings (e.g. F-001) belong under Closed, not Needs review. Live list labels `· Closed`.
- **Prepare 0/0 → 100%** — fixed to N/A / Not started.

## 11. Responsive / accessibility

- Existing ResponsiveSegmentedControl for AA primary on compact widths
- Functional tabs horizontal scroll
- Closing `aria-current="step"` on active gate
- Full breakpoint audit not exhaustively re-shot

## 12. Tests run

| Command | Result |
| --- | --- |
| `npm run check:css` | PASS |
| `npm run check:modals` | PASS |
| Vitest findingLifecycle + auditsWorkspaceModel + auditNextAction | PASS 16/16 |
| `npm run test:quality` | PASS 76/76 |
| `npm run test:qms-planner` | PASS 11/11 |
| Playwright live AA | Not run (live gate) |

## 13. Pass / fail summary

- Unit/contract checks above: **PASS**
- Browser journeys: **PASS with notes** (§14)
- Backend suite / full `build`: **Not run this pass**

## 14. Browser journeys (safarilink)

| Journey | Result |
| --- | --- |
| Overview | PASS — AA peers; attention-oriented KPIs |
| Programme | PASS — five IA tabs visible; programme header |
| Calendar | PASS — Calendar selected; Schedule controls; session timeout dismissed |
| Audits workspace | PASS — AG Grid; Continue audit / Follow up |
| Prepare occurrence | PASS — progress + functional tabs |
| Findings & Actions | PASS — All default; stage filters; findings listed |
| Raise finding → full CAR chain | Not fully exercised |
| Closing progressive lock | Code done; not browser-verified on an active closing audit |

## 15. Remaining limitations

1. Quality chrome still exposes Planner / Cases at Assurance workspace level (shell retention); AA local rail is the demoted layer.
2. Calendar still runs Planner V2 engine underneath (correct) — wireframe-style unscheduled queue polish may still be needed.
3. Tenant programme may have 0 requirements — empty states OK.
4. Intermittent DB recovery banner during validation.
5. Run Playwright live gate + production build before release commit.
6. No commit created.

## DoD honesty

Canonical AA IA, Programme tab IA, Calendar-as-schedule language, Audits task CTAs, occurrence progress+functional tabs, readiness 0/0 fix, Findings continuity defaults, and closing progressive disclosure are **implemented and mostly browser-validated**.  
Full §55 DoD (every journey, every breakpoint, every failure mode) is **not** claimed complete.

---

## Addendum — Live 500 / findings / Prepare 0/0 (post root-cause pass)

Traced and fixed by [Root-cause Live 500 + findings gap](097cdf1d-499b-41ac-95bf-7b0972885ede). Contract detail: `contracts/ROOT_CAUSES.md`.

| Issue | Class | Resolution |
| --- | --- | --- |
| Live HTTP 500 toast | Backend routing | Presence routes promoted ahead of Quality catch-all (`audit_presence_route_order.py`); heartbeat silenced in `portalFetchErrorBridge.ts`. Checklist empty = prerequisite, not 500. |
| Needs review = 0 while Live shows F-001 | Filter (correct) | F-001 is closed; belongs under Closed. Live labels `· Closed`. |
| Prepare 100% on 0/0 | Frontend state | N/A / 0 required · Not started. |

Evidence on disk: presence route order module, silent heartbeat paths, ROOT_CAUSES.md. Pytest presence order + related Vitest reported passed by that pass. Still uncommitted.
