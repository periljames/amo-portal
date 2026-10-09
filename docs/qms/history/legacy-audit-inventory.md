# Audit Assurance — Phase 1 live inventory (BEFORE reconstruction)

**Tenant:** safarilink · **App:** `http://127.0.0.1:5173` · **Viewport baseline:** 1400×906  
**Authority:** Cursor Browser live inspection (not code review).  
**Do not commit.**

Screenshots: `.runtime-logs/audit-assurance-redesign/screenshots/before/`

---

## Global geometry defects (all AA surfaces)

| Issue | Observation |
| --- | --- |
| Nav layers | Portal rail + Quality module bar + Assurance pills + AA local rail (+ lifecycle rail on records) = **4–5 concurrent navigations** |
| Content start | Useful work often begins after ~160–220px of chrome |
| Full-page route flash | Hard navigations show blank “Loading portal workspace…” / “Loading audit occurrence…” wiping shell |
| Width | Content often in padded card; Closing especially under-uses horizontal space |
| Duplicate destinations | Findings & Actions appears in pills **and** AA rail; Planner vs Calendar dual branding |

---

## A/B — Entry / Overview

| Field | Value |
| --- | --- |
| Route | `/maintenance/safarilink/quality/audits/dashboard` |
| H1 | Audit Assurance |
| ScrollH / VH | 906 / 906 (fits) |
| Primary CTAs | Programme · Planner · Register · CARs; Manage programme coverage; Create/run schedule |
| Secondary | Refresh, Tools overflow |
| Empty/zero risk | Many KPI zeros; **“0 Active programmes”** vs helper **“1 revision in 2026”** |
| Wasted space | Duplicate “Go to …” strip + KPI wall before “Needs attention” |
| Screenshot | `01-overview-1440.png` |

---

## C — Programme

| Field | Value |
| --- | --- |
| Route | `.../audits/program` |
| H1 | Audit Programme |
| ScrollH / VH | 906 / 906 |
| State | Draft AP-2026… · **0 requirements · 0 scheduled · 0 unscheduled** |
| Primary CTAs | New programme, Open in Planner, Details, Edit, Recalculate & sync, Approve (gated) |
| Notes | Dense chrome; Portfolio/Revisions/Requirements/Coverage/Universe/Entities/Readiness tabs |
| Screenshot | `02-programme-1440.png` (also `02-programme.png`) |

---

## D — Calendar / Planner

| Field | Value |
| --- | --- |
| Route | `.../quality/calendar/week` |
| H1 | Planner |
| ScrollH / VH | 906 / 906 (internal grid scroll) |
| Primary CTA | **Schedule** |
| Secondary | Month/5 days/Day/Agenda, Today, search, sidebar/context toggles |
| Notes | Top Quality **Planner** pill also active (nav collision). Demoted chrome mostly OK on week view. |
| Screenshot | `03-calendar-week-1440.png` |

---

## E — Audits workspace

| Field | Value |
| --- | --- |
| Route | `.../audits/workspace` |
| H1 | Audits |
| ScrollH / VH | 906 / 906 |
| Filters | Mine / Upcoming / Active / Completed (segmented) |
| Bound | “Showing up to **250** current tenant records” — not true page pagination |
| Rows | QAR/MO/26/001 (In progress → CTA **Start audit**), QAR/MO/26/002 (Follow-up open → **Follow up**) |
| Defects | CTA **Start audit** while lifecycle already **In progress** (should be Continue); not AG Grid; large empty band under 2 rows |
| Screenshot | `04-audits-workspace-1440.png` |

---

## F — Setup (`QAR/MO/26/001`)

| Field | Value |
| --- | --- |
| Route | `.../audits/QAR-MO-26-001/setup` |
| H1 | QAR/MO/26/001 · Procurement Audit |
| ScrollH / VH | **3290 / 906** — full document scroll (long form) |
| Primary CTAs | Save audit definition, Commit governed assignments, Create notice, **Go to Prepare** |
| Notes | Authoritative stage shows Prepare while viewing Setup; giant people dropdowns |
| Screenshot | `05-setup-1440.png` |

---

## G — Prepare

| Field | Value |
| --- | --- |
| Route | `.../prepare` |
| ScrollH / VH | 1021 / 906 |
| Primary CTAs | New request, Invite, **Open Live Audit**, Exit preparation |
| Contract risk | **Required evidence readiness 100%** with **0 of 0** required requests — fake-success readiness |
| Scope/Criteria | “—” empty; checklist bindings 0 |
| Screenshot | `06-prepare-1440.png` |

---

## H — Live

| Field | Value |
| --- | --- |
| Route | `.../live` |
| ScrollH / VH | 1029 / 906 |
| Alert | **Action failed · Internal Server Error · Reference: 500** |
| Checklist | Empty (“No checklist items…”) · Progress 0/0 |
| Authoritative stage | **PREPARE** while route is Live |
| Findings panel | Shows **QAR/MO/26/001-F-001** |
| Primary CTAs | Exit field mode, Go to Prepare, Go to Closing |
| Screenshot | `07-live-1440.png` |

---

## I — Closing

| Field | Value |
| --- | --- |
| Route | `.../closing` |
| ScrollH / VH | **1911 / 906** — page scroll |
| Primary CTAs | Generate closing report draft, Save report narrative, Register passkey, Exit closing |
| Blockers | Fieldwork not complete; CAR linkage unavailable on finding; no closing meeting |
| Defect | Passkey UI interactive while step 1 blocked |
| Width | Narrow column, large unused right margin |
| Screenshot | `08-closing-1440.png` |

---

## J — Follow-up

| Field | Value |
| --- | --- |
| Route | `.../follow-up` |
| ScrollH / VH | 1767 / 906 |
| State | 0 CARs linked; gate says no unresolved blocker; Archive handoff still blocked by lifecycle/retention |
| Contradiction | Audits list shows **Follow-up open** for 002; 001 follow-up empty CARs while finding exists without CAR |
| Screenshot | `09-follow-up-1440.png` |

---

## K — Archive

| Field | Value |
| --- | --- |
| Route | `.../archive` |
| ScrollH / VH | 1602 / 906 |
| State | No manifest; no retention policy; disposition pending |
| CTAs | Generate governed archive, Configure retention policy |
| Screenshot | `10-archive-1440.png` |

---

## L — Findings & Actions

| Field | Value |
| --- | --- |
| Route | `.../audits/register?tab=findings` |
| H1 | Findings & Actions |
| Filters | Needs Review / With Auditee / Implementation / Effectiveness / Closed |
| Empty | **0–0 of 0** on Needs Review despite Live showing finding F-001 |
| Bound | Rows 25/50/100 controls present |
| Screenshot | `11-findings-register-1440.png` |

**P0 continuity break:** audit Live shows finding; primary Findings register does not.

---

## M — Finding detail

Prior evidence: stuck loading fixed in Tranche 2 for invalid IDs. Live linked finding→register→detail path **not proven** this pass because register empty.

---

## N/O — CAR register / detail

Reachable via `register?tab=cars` and Corrective action pill. Not fully click-tested this session after Findings empty blocked chain.

---

## P/Q — Evidence

| Field | Value |
| --- | --- |
| Route | `.../quality/evidence-vault` |
| H1 | Evidence |
| Pagination | 15/30/50 — bounded |
| Empty | No rows for filters |
| Screenshot | `12-evidence-vault-1440.png` |

---

## R/S — Checklists

| Field | Value |
| --- | --- |
| Route | `.../audits/checklists` |
| H1 | Audit checklists |
| Defects | **Create template** disabled; Item 1 editor still shown with “No templates yet”; tall form density |
| Screenshot | `13-checklists-1440.png` |

---

## T — Assurance Cases

| Field | Value |
| --- | --- |
| Route | `/maintenance/safarilink/quality?workspace=assurance` |
| H1 | Cases, investigation & effectiveness |
| State | 0 open cases; empty portfolio |
| Notes | Separate from Audit Assurance; pill collision risk with Cases |

---

## Responsive

Not fully re-run at 1100/860 in this pass. Prior planner evidence exists (`11-planner-w1440.png`, `12-planner-w1100.png`, `13-planner-w860.png`). **Must re-measure after geometry slice.**

---

## Phase 1 verdict

**Cannot start “done” claims.** Product is navigable but:

1. Multi-rail IA burns vertical space.
2. Audits CTA wrong for in-progress.
3. Prepare readiness 100% on 0/0 is false confidence.
4. Live 500 + empty checklist while finding exists.
5. Findings register does not show live finding (workflow break).
6. Closing/Follow-up/Archive are long scrolling forms with interactive-but-blocked controls.
7. Checklists Create CTA dead while editor visible.
8. Registers not AG Grid; Audits bound at 250 without true pagination UX.

Next: Phase 2 control matrix (click tests) + Phase 3 contracts + Phase 4 wireframes → then Slice 1.
