# Audit Assurance — Live Product Audit

**Date:** 2026-08-24  
**Environment:** `http://127.0.0.1:5173` (authenticated as James Muisyo / Safarilink)  
**Method:** Cursor Browser interactive navigation only (no mocked data, no Playwright-as-UX)  
**Screenshots:** `.runtime-logs/audit-assurance-live/*.png` (not for commit)

---

## Verdict

**Can a normal Quality Manager / Lead Auditor complete the full audit lifecycle without learning portal architecture?**

**No — not today.**

The product is operationally dense and governance-complete in places (Programme readiness gates, Setup form, Follow-up CAR loop language), but the **UI presents 4–5 navigation systems at once**, duplicates registers, exposes backend lifecycle stages as primary chrome, and several critical stages render as **“Not Found” / stuck loading overlays** that block fieldwork and closing.

---

## A. Current workflow map (as experienced)

```
Quality Control Room
  └─ (no obvious Audit Assurance entry)
Quality workspace “Cases” → Assurance Cases (?workspace=assurance)
  OR deep URL /quality/audits → Audit Assurance Overview
       ├─ Programme (Draft · Hybrid · empty coverage)
       ├─ Register (defaults to Findings; no Audits tab)
       ├─ Planner → /quality/calendar (when rail used correctly)
       ├─ Checklists (admin create+editor always visible)
       ├─ Evidence → /quality/evidence-vault/*
       ├─ Create / run (third scheduling lane)
       └─ Recycle bin
Open audit from Register “Open audit”
  └─ Lifecycle: Setup | Prepare | Live | Closing | Follow-up | Archive
       (duplicated as pills + stage rail)
Findings pill → /quality/findings (separate register)
Corrective action pill → /quality/cars/register (empty; 0 CARs)
```

**Lifecycle backend (unchanged):** SETUP → PREPARE → LIVE → CLOSING → FOLLOW-UP → ARCHIVE  
**UI problem:** stages are the main navigation, not “what to do next.”

---

## B. Current navigation layers (count per major screen)

| Layer | Example | Classification |
| --- | --- | --- |
| Portal sidebar / hamburger | Home, departments | GLOBAL PRODUCT NAV |
| Global header | Quality & Compliance, tenant, profile | GLOBAL PRODUCT NAV |
| Quality workspace tabs | Control Room, Planner, Missions, People, **Cases**, Intelligence | QUALITY WORKSPACE NAV |
| Assurance subnav pills | Cases, Audit Assurance, Findings, Corrective action, External…, Evidence vault | AUDIT ASSURANCE NAV (over-wide) |
| AA left rail | Overview, Programme, Register, Planner, Checks, Evidence, Create/run, Bin | PAGE NAV |
| Planner mini-rail + left tools + right control centre | AA icons, mini-cal, Quick schedule, filters | PAGE / CONTEXTUAL |
| Audit stage pills + stage rail | Setup…Archive (twice) | RECORD NAV |
| Workflows / overflow / My work / Live | chrome actions | CONTEXTUAL ACTION |

**Typical Audit Assurance screen: 5 simultaneous navigation systems.**  
**Planner at 1440: same + calendar chrome + right control centre.**

---

## C. Click / friction map (observed)

| Task | Current clicks (approx) | Unnecessary | Target |
| --- | --- | --- | --- |
| 1. Open current programme | 2–4 (must know `/audits` or rail) | Discoverability from Control Room | 1 |
| 2. Find unscheduled requirement | Programme → Coverage; empty; Overview also claims overdue Aircraft audit | KPI contradiction | 1–2 |
| 3. Schedule it | Blocked: Draft + “after approval” + empty universe | — | 2–3 |
| 4. Find scheduled audit | Register has **no Audits tab**; must open via finding row | 3+ | 1 |
| 5. Prepare audit | Open audit → Prepare | **P0 Not Found overlay** | 1 |
| 6. Start live audit | Live tab | **P0 Not Found** | 1 |
| 7. Record nonconformance | Blocked by Live | — | 2–3 |
| 8. Create finding | Blocked / separate Findings register | Dual registers | 1–2 |
| 9. Open linked CAR | Follow-up says 0 CARs; Closing says CAR linkage unavailable | Broken linkage | 1 |
| 10–15. RCA → evidence → close → report → archive | Partially blocked by overlays / empty CAR register | — | progressive |

---

## D. Defect list (severity)

### P0 — blocks workflow / corrupts UX state

| ID | Issue | Type | Evidence |
| --- | --- | --- | --- |
| P0-1 | **Prepare** shows full-viewport “Not Found” | WORKFLOW / ERROR | `05-audit-prepare.png`, `/audits/QAR-MO-26-001/prepare` |
| P0-2 | **Live** same | WORKFLOW / ERROR | `06-audit-live.png` |
| P0-3 | **Closing** content exists but **`qms-audit-closing--loading` fixed overlay (z-index 1195)** covers page with “Not Found” and intercepts clicks | WORKFLOW / LOADING / LAYOUT | CDP: fixed overlay 1385×906; `07-audit-closing.png` |
| P0-4 | **Archive** toast “Action failed / Not Found” + loading Not Found | WORKFLOW / ERROR | `09-audit-archive.png` |
| P0-5 | Finding deep-link `/findings/{id}/overview` stays on **Findings Register “Loading findings…”** (0 rows) | ROUTING / WORKFLOW | `15-finding-detail-stuck-loading.png` |

### P1 — serious operational problems

| ID | Issue | Type |
| --- | --- | --- |
| P1-1 | **Cases** Quality workspace tab stays `current` while inside Audit Assurance / audit lifecycle — user cannot tell Cases vs Audits apart | NAVIGATION / COPY |
| P1-2 | Audit Assurance **Register defaults to Findings**; label says “Audits, findings and corrective actions” but **no Audits list** | WORKFLOW / IA |
| P1-3 | **Three scheduling systems**: Programme scheduling, Planner Schedule/Quick schedule, Create/run schedules + first-time guide | DUPLICATION / WORKFLOW |
| P1-4 | Overview KPIs contradict Programme: Overview “Aircraft audit schedule overdue” vs Programme **0 requirements / 0 unscheduled** | DATA PRESENTATION |
| P1-5 | Closing: “CAR linkage unavailable”; Follow-up: “No CARs linked”; Findings exist — **issue lifecycle broken across surfaces** | WORKFLOW |
| P1-6 | Status column shows **CLOSED** above **IN PROGRESS / CAP OPEN** | DATA PRESENTATION / COPY |
| P1-7 | Frequent **“database recovery in progress”** banner during navigations; may contribute to Not Found | ERROR / BACKEND |
| P1-8 | Guessed/legacy paths (`/audits/planner`, `/audits/evidence`, `/capa`) 404 — easy to hit from memory/docs; recovery links help but prove naming confusion | ROUTING |

### P2 — significant UX friction

| ID | Issue | Type |
| --- | --- | --- |
| P2-1 | 4–5 nav layers on every AA screen | NAVIGATION / LAYOUT |
| P2-2 | Assurance pill row: 8 permanent destinations (External providers, Tooling, External & regulatory…) | NAVIGATION |
| P2-3 | AA rail descriptions are implementation prose (“Dated calendar — Planner V2 only”) | COPY |
| P2-4 | Lifecycle stages duplicated (header pills + occurrence rail) | DUPLICATION |
| P2-5 | Setup is a long governance form (definition, team, independence, meetings, notice) with weak primary “next” | WORKFLOW / LAYOUT |
| P2-6 | Planner: mini-cal + Quick schedule + Quality calendars + Saved views + right Control Centre + Strategic Planner always competing | LAYOUT / DUPLICATION |
| P2-7 | At ~1100px Quality workspace tabs collapse awkwardly; at ~860 Assurance pills wrap to 2 rows; calendar crushed by right panel | RESPONSIVE |
| P2-8 | Checklists: create template + full revision editor always visible (admin wall) | LAYOUT |
| P2-9 | Workflows drawers + workflow guidance + support diagnostics on many pages | DUPLICATION |
| P2-10 | Programme repeats identity/dates/IDs multiple times; optimizer scoring always prominent with 0 coverage | LAYOUT / COPY |
| P2-11 | Dual Findings registers (AA Register Findings tab + `/quality/findings`) | DUPLICATION |
| P2-12 | CAR register Responsible filter dumps ~70 people into one select | LAYOUT / A11Y |

### P3 — polish

| ID | Issue |
| --- | --- |
| P3-1 | Transition lag: URL changes while previous page content remains until next paint |
| P3-2 | “Please wait…” on Refresh during transitions |
| P3-3 | Portal sidebar expand/close buttons often `pointer-events: none` while overlay present |
| P3-4 | Create/run first-time guide is large and permanent-feeling |

---

## E. Screen-by-screen findings

### Audit Assurance entry / Overview (`/quality/audits`)
- Screenshot: `01-audit-assurance-entry.png`
- Useful “Needs attention” next action, but drowned in KPIs + Go-to links + rail + pills.
- “Create / run schedule” still primary CTA alongside programme coverage.

### Programme (`/audits/program`)
- Screenshot: `02-programme.png`
- Clear period (2026), Hybrid methodology weights, Draft status, readiness blockers — **good governance**.
- Empty universe/coverage; scheduling gated until approval — correct but user must understand approval machine.
- Tabs: Portfolio / Requirements / Universe / Readiness — fine as secondary once chrome reduced.

### Register (`/audits/register?tab=findings`)
- Screenshot: `03-register-findings.png`
- Findings-first; dense filters; conflicting status chips; Open audit works (navigates to Setup).

### Setup (`.../setup`)
- Screenshot: `04-audit-setup.png` (thin capture; interactive tree confirms long form)
- Authoritative next stage: Prepare — good copy, but buried under duplicate stage nav + long form.
- Lead auditor Unassigned; team assign disabled — next action unclear beyond “fill more governance”.

### Prepare / Live
- Screenshots: `05`, `06` — **blocked (Not Found)**.

### Closing
- Overlay P0; underlying form has narrative fields + “report generation blocked”.

### Follow-up
- Screenshot: `08-audit-follow-up.png` (also saw empty chrome during transition)
- Useful CAR queue concept; empty data; Archive handoff messaging present.

### Archive
- Screenshot: `09` — Not Found / Action failed.

### Planner (`/quality/calendar`)
- Screenshots: `11`–`13` (1440 / 1100 / 860)
- Canonical calendar works; training expiry event visible.
- Chrome overload matches user example: Quality nav + Assurance pills + AA rail + planner tools + control centre.
- Schedule + Quick schedule + Strategic Planner = concept collision.

### Findings (`/quality/findings`)
- Screenshot: `14` — clean register; open deep-link breaks (`15`).

### CARs (`/quality/cars/register`)
- Screenshot: `16` — empty; Create CAR prominent; enormous owner list.

### Evidence vault
- Wrong path `/audits/evidence` 404 (`17`); correct `/evidence-vault/search` works empty (`18`).

### Checklists
- Screenshot: `19` — admin template factory as daily destination.

### Assurance Cases
- Screenshot: `20` — separate product (good), but named **Cases** next to Quality workspace **Cases** and Assurance pill **Cases**.

### Create / run
- Screenshot: `21` — third schedule lane + 5-step guide; “Open Planner” acknowledges calendar ownership yet page remains permanent rail item.

---

## F. Broken / misleading buttons

| Control | Observed |
| --- | --- |
| Prepare / Live / Archive stage entry | Not Found / failed |
| Closing interaction | Overlay intercepts clicks |
| Finding “Open →” deep link | Stuck loading register |
| Quality “Cases” while in audits | Still marked current |
| Overview “Unscheduled = 0” vs overdue Aircraft audit card | Contradictory |
| Register as “Audits…” | No audits primary view |
| `/audits/planner`, `/audits/evidence`, `/capa` | Route not found (legacy/guess) |

---

## G. Duplicate actions

- Programme “Open in Planner” ×2  
- Planner Schedule vs Quick schedule vs Create/run Create schedule vs Programme Add coverage  
- Findings in AA Register **and** Findings module  
- CARs in Register tab **and** Corrective action module **and** Follow-up  
- Lifecycle pills **and** occurrence stage links  
- Workflows drawer **and** Workflow guidance footers  
- Quality workspace Planner **and** AA Planner rail  

---

## H. Transition / loading issues

- Full “Loading portal workspace…” on many hard navigations  
- URL updates before content (stale previous page)  
- Closing/Prepare/Live/Archive loading classes showing **Not Found** instead of spinner/retry  
- Persistent DB recovery chip during session  

---

## I. Responsive issues

- **1440:** usable but right control centre + left tools squeeze calendar  
- **1100:** Quality workspace icons collapse; Evidence vault label truncates; calendar narrower  
- **860:** Assurance pills wrap to 2 rows; planner days shrink; Strategic Planner floats over content  

---

## J. Backend / API blockers observed live

1. DB recovery banner: “Server reachable; database recovery in progress”  
2. Prepare/Live/Archive Not Found responses (likely session/resource 404 surfaced as page chrome)  
3. CAR linkage unavailable for finding at closing; Follow-up shows 0 CARs  
4. Finding overview deep-link never hydrates record  
5. Programme empty vs Overview overdue obligation — data/model inconsistency  

---

## K. What should be removed (from permanent chrome)

- Assurance pills for External providers, Tooling, External & regulatory (→ Tools menu)  
- Permanent Create / run + Recycle bin from primary rail (→ Tools / admin)  
- Duplicate lifecycle pill row (keep one contextual stage indicator)  
- Planner right “control centre” as always-open default  
- Permanent Quick schedule block if Schedule CTA exists  
- Implementation phrases (“Planner V2 only”, “governed lifecycle %”) from primary labels  
- Dual Workflows + Workflow guidance walls  

---

## L. What to demote to contextual / tools

- Checklists library  
- Evidence vault (prefer contextual evidence on audit/finding/CAR)  
- Recycle bin  
- Create / run schedule templates  
- Strategic Planner  
- Saved views / display density until needed  
- Independence / meeting / notice blocks on Setup until definition saved  

---

## M. What must remain primary

**Audit Assurance:** Overview · Plan (Programme + Calendar) · Audits · Findings & Actions  

**Audit record:** Summary · current state · **one primary next action** · Work / Findings / Evidence / Report as needed  

**Cases:** keep separate, rename Quality workspace tab away from colliding “Cases” if Assurance Cases stays.

---

## N. Screenshot locations

All under `.runtime-logs/audit-assurance-live/`:

01 entry · 02 programme · 03 register · 04 setup · 05 prepare · 06 live · 07 closing · 08 follow-up · 09 archive · 10 planner 404 (manual bad path) · 11–13 planner widths · 14 findings · 15 finding stuck · 16 cars · 17 evidence 404 · 18 evidence vault · 19 checklists · 20 cases · 21 create/run  

---

## Answer to review objective

Users currently must learn: Quality workspace vs Assurance pills vs AA rail vs Planner tools vs lifecycle stages vs which register owns findings/CARs vs which calendar owns dates.  
**That fails the enterprise SaaS bar.** Implementation should collapse chrome first, then fix P0 stage/loading failures, then reconnect Programme → Schedule → Audit → Finding → CAR as one path.

---

## AFTER — Implementation tranche 1 (2026-08-24)

### What changed
1. **AA rail** → Overview · Plan (Programme | Calendar) · Audits · Findings & Actions; Checklists / Evidence / Create-run / Bin under **Tools**
2. **Assurance pills** → Cases, Audit Assurance, Findings, Corrective action, Evidence + **Tools** overflow (External* demoted)
3. **Cases** no longer marked current on `/audits` / `/calendar`
4. **Duplicate lifecycle pills** removed; compact stage rail remains
5. **Prepare / Live / Closing / Archive** errors use recoverable UI (Retry + Exit) instead of bare “Not Found” wall

### After screenshots
- `22-after-aa-nav.png`
- `23-after-prepare-recoverable.png`

### Bounded tests
- `npm run check:css` — pass
- `npm run test:quality` — 74 passed

### Still open (next tranches)
- Backend 404s for Prepare/Live/Closing/Archive resources (UI recovers; data still missing)
- No true audits-first register tab
- Planner chrome (control centre / Quick schedule / Strategic Planner) still dense
- Finding deep-link stuck loading
- Overview KPI vs Programme data contradiction
- Dual Findings registers
- Not committed (per instruction)
