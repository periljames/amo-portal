# Audit Assurance — Tranche 2 final report

**Do not commit yet.** Working tree remains uncommitted pending acceptance of this report.

Live tenant exercised: **safarilink** · sample audit **QAR/MO/26/001** (Procurement Audit).

---

## A. Stage 404 root causes

| Stage | Class | Root cause |
| --- | --- | --- |
| Setup | Working | Already used tenant `resolveAuditOccurrence` |
| Prepare / Live / Closing / Archive | **A + B** (path/key) + earlier **wrong resolver** | Stages historically used non-tenant `qmsResolveAudit`-style resolve → API 404 walls. Unified to tenant resolve. |
| Follow-up | Same family | Same resolve mismatch; unified |
| Prepare blank `#root` (after resolve unify) | **H — render crash** | `AuditPrepareWorkspace`: `context?.regulatory_and_manual_basis.audit_scope` (nested optional missing) → `TypeError: Cannot read properties of undefined (reading 'audit_scope')` → React root unmounted |
| Live blank `#root` | **H — render crash** | `LiveAuditWorkspace`: `.replaceAll` on undefined checklist `canonical_response_status` |

Not fabricated stage payloads, auth bypass, or parallel backend engines.

---

## B. Stage 404 / crash fixes

1. Unified Prepare / Live / Closing / Follow-up / Archive on `resolveAuditOccurrence(amo, auditKey)`.
2. Recoverable stage load / prerequisite UI instead of generic Not Found where applicable.
3. Prepare: nested optional chaining + pending/error guards for sparse preparation context.
4. Live: `statusLabel()` helper; safe counts when status missing.
5. Closing / Archive: defensive optional chaining on nested composition / policy objects.
6. Non-null Suspense fallbacks for stage mounts (“Loading … workspace…”).

---

## C. Old Audits IA vs new Audits IA

| Before | After |
| --- | --- |
| Primary Audits landed on schedule-engine (“Create / run schedules”) | `/maintenance/{amo}/quality/audits/workspace` — H1 **Audits** |
| No audits-first operational register | Views: **Mine / Upcoming / Active / Completed** (labels may read Mine/Upcoming/Active/Completed in UI) |
| Manual Setup→Archive tab hopping | One row CTA from lifecycle (`Start audit`, `Follow up`, …) — open does not mutate lifecycle |
| Create/run in primary rail | Under **Tools** |

Live CTA examples seen: **Start audit**, **Follow up**.

---

## D. Planner controls removed / demoted

On `/maintenance/{amo}/quality/calendar/week`:

- Left rail + right control centre default collapsed; prefs key bumped.
- Quick schedule demoted.
- **Schedule** kept as primary toolbar CTA (live: present).
- Strategic / coverage planning demoted (not permanent chrome).
- Live chrome probe: `quick=false`, `strategic=false`, `control=false`, `scheduleBtn=true`, left rail not open.

**Remaining P1:** Quality top **Planner** control navigated to `/quality/calendar/month` → “Quality route not found”. AA Calendar rail correctly uses `/calendar/week`.

---

## E. Finding hydration root cause / fix

- **Cause:** `/quality/findings/:id/overview` was known to the shell but had no detail owner → register-style loader could spin indefinitely.
- **Fix:** `QualityFindingDetailPage` owns the route; query ends in loading / loaded / empty / unauthorized / error+Retry.
- Live invalid id: terminal **Finding could not be loaded** + **Retry** (no indefinite spinner). Source maps invalid UUID to a friendly register redirect message.

---

## F. Finding → CAR workflow before / after

| Before | After |
| --- | --- |
| Deep-link stuck loading | Detail page with terminal states |
| No single CAR handoff | **Continue corrective action** or **Create corrective action** when permitted |
| Separate Findings / CAR / Follow-up mental models | Primary **Findings & Actions** register with lifecycle filters |

Live: Findings & Actions H1 + filters **Needs review / With auditee / Implementation / Effectiveness / Closed**. Needs-review empty in session; linked-CAR continue not fully proven with a live UUID this pass.

---

## G. Programme / Overview contradiction root cause / fix

- **Cause:** Overview treated missing readiness as zero / invented client readiness %.
- **Fix:** Overview projects programme list readiness (`listedReadinessOf`); Unscheduled / Coverage → **Unavailable** when readiness incomplete; unscheduled uses `unscheduled_requirement_count`.

Live (safarilink):

- Overview: Unscheduled “No unscheduled requirements reported”; Coverage/readiness shows programme-blocker language / Unavailable path in code.
- Programme: draft programme **0 scheduled · 0 unscheduled**.

Remaining nuance: Overview still shows **operational** due/overdue and open-audit cards from schedules/audits lists — distinct concepts from Programme requirement counts (not invented readiness %).

---

## H. Duplicate findings surfaces removed / demoted

- Primary: **Findings & Actions** → `/quality/audits/register?tab=findings`.
- Legacy findings routes kept for deep-links; primary nav converges.
- Corrective action / CAR surfaces remain secondary for CAR-centric work.

---

## I. Click counts before / after (representative)

| Journey | Before (approx.) | After (live) |
| --- | --- | --- |
| Open audits list | 2–3 (wrong destination) | 1 → Audits workspace |
| Continue scheduled audit | 4–6 (stage tabs + recover from 404/blank) | 1 list CTA → correct stage |
| Finding → CAR | Failed (spinner) | 1–2 when data exists (UI ready) |
| Planner schedule intent | Many permanent chrome clicks | Schedule on toolbar; extras demoted |

---

## J. Live routes tested

- `/maintenance/safarilink/quality/audits/workspace`
- `/maintenance/safarilink/quality/audits/QAR-MO-26-001/setup`
- `.../prepare` · `.../live` · `.../closing` · `.../follow-up` · `.../archive`
- `/maintenance/safarilink/quality/audits/dashboard`
- `/maintenance/safarilink/quality/audits/program`
- `/maintenance/safarilink/quality/audits/register?tab=findings`
- `/maintenance/safarilink/quality/findings/not-a-real-finding-id/overview`
- `/maintenance/safarilink/quality/calendar/week`

---

## K. Before screenshot paths

Tranche 0 live product audit evidence under:

- `.runtime-logs/audit-assurance-live/` (and prior `LIVE_PRODUCT_AUDIT.md`)

---

## L. After screenshot paths

`.runtime-logs/audit-assurance-live/tranche2/`

| File | Subject |
| --- | --- |
| `t2-01-audits-workspace.png` | Audits-first workspace |
| `t2-02-setup-works.png` | Setup |
| `t2-03-prepare-works.png` | Prepare (post crash fix) |
| `t2-04-live-works.png` | Live (post crash fix) |
| `t2-05-closing.png` | Closing + prerequisites |
| `t2-06-follow-up.png` | Follow-up |
| `t2-07-archive.png` | Archive |
| `t2-08-planner-demoted.png` | Planner demoted chrome |
| `t2-09-finding-invalid-id.png` | Finding deep-link terminal error |

---

## M. Bounded test results

| Command | Result |
| --- | --- |
| `npx tsc -b --pretty false` | Pass |
| `npm run check:css` | Pass (118 stylesheets) |
| `npm run check:modals` | Pass (39 modal sources) |
| `npm run test:quality` | Pass — **76** tests |
| `npm run test:qms-planner` | Pass — **11** tests |
| Playwright `qms-audit-assurance-live.spec.ts` | `test.use` moved file-top (was invalid inside `describe`). Run: **6 skipped** (live gate `E2E_LIVE_QUALITY` / equivalent not enabled) |

---

## N. Remaining P0 / P1 defects

1. **P1** — Quality top-nav **Planner** → `/quality/calendar/month` shows “Quality route not found”; AA Calendar **week** works.
2. **P1** — Live may surface a global **500** toast while workspace still renders; checklist can be empty while authoritative stage is still Prepare (prerequisite messaging present).
3. **P1** — Findings stage filter: one observation of URL `stage=closed` while heading still “Needs review” — verify SegmentedControl sync.
4. **P2** — Cases / Assurance active-state collision residue on some routes.
5. **P2** — Real finding → linked CAR continue path not fully live-proven with a tenant UUID this session (Needs review empty).

---

## Acceptance checklist (live)

1. Audits primary opens audits-first workspace — **Yes**
2. Scheduled audit opens — **Yes**
3. Setup — **Yes**
4. Prepare — **Yes** (after crash fix)
5. Live — **Yes** / legitimate empty checklist + stage note
6. Closing — **Yes** / fieldwork prerequisite blockers (not Not Found)
7. Follow-up — **Yes**
8. Archive — **Yes** / retention prerequisite messaging
9. Finding deep-link resolves — **Yes** (terminal error for invalid id; no infinite spinner)
10. Finding → CAR path obvious — **Yes** in UI model; live linked row pending data
11. Planner less permanent chrome — **Yes** on week planner
12. Programme/Overview no longer invent readiness % — **Yes**; operational cards remain distinct
13. One primary Findings & Actions — **Yes**
14. No indefinite spinner — **Yes** on paths tested
15. No generic Not Found for normal lifecycle — **Yes** on six stages for `QAR/MO/26/001`

**Still not committed.**
