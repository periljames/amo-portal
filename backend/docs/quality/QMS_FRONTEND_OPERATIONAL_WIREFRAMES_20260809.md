# QMS Frontend Operational Wireframes — 2026-08-09

## Purpose

This document is the implementation contract for the post-PR-488 frontend correction phase. The governed backend contracts introduced by PR #488 remain authoritative. This work changes information architecture, presentation, readability and interaction patterns without weakening lifecycle, tenancy, RLS, approval, revision, audit, CAR, Mission, People or Intelligence governance.

## Design baseline

### Typography

- Page title: 28–32px / 700–750.
- Section title: 18–20px / 700.
- Card title / primary row label: 14–15px / 650–700.
- Normal working text: 14px minimum.
- Form controls: 14px minimum.
- Secondary text: 12.5–13px.
- Metadata: 11.5–12px minimum and used sparingly.
- Operational meaning must never depend on 8–10px text.

### Interaction sizing

- Standard interactive control: 38–42px minimum height.
- Compact table/filter controls: 34–36px minimum height.
- Primary actions use one dominant treatment per surface.
- Secondary row actions collapse into an overflow menu or contextual action panel where practical.

### Layout

- Maximum working width: 1680px, centered.
- 20–24px desktop page padding.
- 16–20px section gaps.
- Dense information is achieved through hierarchy and disclosure, not microscopic typography.
- At 1366–1920px widths the principal task must remain readable without browser zoom.
- 4K relies on OS/browser scaling but must remain structurally usable at 100% zoom.

### Shared page anatomy

```text
┌───────────────────────────────────────────────────────────────────────────┐
│ Eyebrow / provenance                                      page actions    │
│ Page title                                                                 │
│ One-sentence operational purpose                                           │
└───────────────────────────────────────────────────────────────────────────┘
┌───────────────┬───────────────┬───────────────┬───────────────────────────┐
│ KPI / posture │ KPI / posture │ KPI / posture │ KPI / posture             │
└───────────────┴───────────────┴───────────────┴───────────────────────────┘
┌──────────────────────────────────────────┬────────────────────────────────┐
│ Primary work surface                     │ Context / next action           │
│                                          │ (collapsible / responsive)      │
└──────────────────────────────────────────┴────────────────────────────────┘
```

## 1. Control Room

### User question

What requires Quality attention now, what is due next, and what should I do?

### Wireframe

```text
┌───────────────────────────────────────────────────────────────────────────┐
│ ASSURANCE CONTROL ROOM                                  Refresh  Diagnostics│
│ Quality Control Room                                                       │
│ Source-backed priorities, obligations and owned work.                      │
└───────────────────────────────────────────────────────────────────────────┘
┌────────────────────────────────────────────┬────────────┬────────┬─────────┐
│ HIGHEST EXPOSURE                           │ Overdue    │ Due 14d│ Sources │
│ Expired training · 227 affected            │  12        │   8    │ Healthy │
│ Department owner · oldest 3,786 days       │            │        │         │
│ Review training exposure →                 │            │        │         │
└────────────────────────────────────────────┴────────────┴────────┴─────────┘
┌──────────────────────────────────────────┬────────────────────────────────┐
│ ACTION QUEUE                              │ MY QUALITY WORK                │
│ priority | exposure | owner | due | next │ assignment | due | next action │
└──────────────────────────────────────────┴────────────────────────────────┘
┌──────────────────────────────────────────┬────────────────────────────────┐
│ UPCOMING OBLIGATIONS                     │ ASSURANCE HEALTH               │
│ date | requirement | source | action     │ programme / CAR / audit state │
└──────────────────────────────────────────┴────────────────────────────────┘
<collapsed> Performance / diagnostics / source-health detail
```

### Rules

- Highest actionable exposure dominates visually.
- Diagnostics are progressive disclosure, not primary content.
- Source failure states must be explicit and must never render fabricated zeroes.

## 2. Planner

### User question

What is planned, what conflicts, and what should be scheduled or moved?

### Wireframe

```text
┌───────────────────────────────────────────────────────────────────────────┐
│ Quality Planner                 Today   < >   Month ▾   Filters   New audit │
└───────────────────────────────────────────────────────────────────────────┘
┌───────────────┬──────────────────────────────────────────────┬─────────────┐
│ Sources       │ Calendar / Year / Quarter / Week / Agenda   │ Context     │
│ □ Programme   │                                              │ selected    │
│ □ Missions    │                                              │ audit       │
│ □ Audits      │                                              │ conflicts   │
│ □ Obligations │                                              │ next action │
└───────────────┴──────────────────────────────────────────────┴─────────────┘
```

### Rules

- Preserve current Planner architecture.
- Increase readable event/control typography.
- Left source rail and right detail rail are collapsible at laptop widths.
- Conflict and authoritative lineage remain first-class.

## 3. Missions

### User question

Which controlled change/capability projects are blocked, approaching target, awaiting review or ready for approval?

### Wireframe

```text
┌───────────────────────────────────────────────────────────────────────────┐
│ CONTROLLED CHANGE & CAPABILITY                           Refresh  New Mission│
│ Missions                                                                    │
│ Cross-department readiness evidence and approval gates.                    │
└───────────────────────────────────────────────────────────────────────────┘
┌─────────────┬──────────────┬───────────────┬───────────────────────────────┐
│ Active  12  │ Blocked  3   │ Gate review 4 │ Due within 30 days  5       │
└─────────────┴──────────────┴───────────────┴───────────────────────────────┘
┌───────────────────────────────────────────────────────────────────────────┐
│ Portfolio   [Search____________] [Status ▾] [Risk ▾]                      │
├──────────────┬───────────────────────┬────────────┬─────────┬──────────────┤
│ Mission/ref  │ Readiness / blockers  │ Owner      │ Target  │ Risk / next  │
│ QMS-M-026    │ 8/11 · 3 gates open   │ J. Doe     │ 18 Aug  │ HIGH Review→ │
└──────────────┴───────────────────────┴────────────┴─────────┴──────────────┘
```

### New Mission drawer

```text
┌─────────────────────────────── New Mission ────────────────────────────────┐
│ Mission title                                                              │
│ Capability / controlled change                                             │
│ Target date                  Initial risk                                   │
│ Description                                                                │
│ Source scope / aircraft type only through governed fields                  │
│                                               Cancel   Create Mission       │
└────────────────────────────────────────────────────────────────────────────┘
```

### Rules

- Portfolio is primary; creation is secondary.
- Mission detail keeps readiness gates, but uses 14px working text and readable evidence provenance.

## 4. People & Privileges

### User question

Who is authorized, expiring, blocked or conflicted, and can this person perform this Quality task?

### Wireframe

```text
┌───────────────────────────────────────────────────────────────────────────┐
│ PEOPLE & PRIVILEGES                                     Refresh  New Privilege│
│ Quality authorization board                                                │
└───────────────────────────────────────────────────────────────────────────┘
┌─────────────┬─────────────┬─────────────┬──────────────────────────────────┐
│ Active      │ Expiring    │ Suspended   │ Independence exceptions         │
└─────────────┴─────────────┴─────────────┴──────────────────────────────────┘
┌───────────────────────────────────────────────┬───────────────────────────┐
│ PEOPLE / AUTHORIZATION REGISTER               │ PERSON / PRIVILEGE DETAIL │
│ Search person...      Status ▾                │ Name / user ref            │
│ Person | privilege | scope | expiry | status │ training posture           │
│                                               │ independence               │
│                                               │ decision history           │
│                                               │ Check eligibility          │
│                                               │ Change privilege           │
└───────────────────────────────────────────────┴───────────────────────────┘
```

### Rules

- Full name is primary when supplied; raw user ID is metadata/fallback.
- Do not present four simultaneous engineering forms as the landing page.
- Create/decision/eligibility/independence actions are contextual panels launched from the selected person/privilege.

## 5. Assurance

### User question

Which assurance cases need triage, investigation, action or effectiveness review?

### Wireframe

```text
┌───────────────────────────────────────────────────────────────────────────┐
│ ASSURANCE CASES                                         Refresh  New Case  │
│ Investigation, action and effectiveness portfolio                         │
└───────────────────────────────────────────────────────────────────────────┘
┌────────────┬──────────────┬───────────────────┬────────────────────────────┐
│ Open       │ Investigating│ Action pending    │ Effectiveness review       │
└────────────┴──────────────┴───────────────────┴────────────────────────────┘
┌──────────────────────────────────────────┬────────────────────────────────┐
│ CASE PORTFOLIO                           │ SELECTED CASE                   │
│ Search... Status ▾ Severity ▾            │ ref · title · severity         │
│ severity | case | owner | age | stage   │ source / facts                 │
│                                          │ investigation timeline         │
│                                          │ next governed action           │
└──────────────────────────────────────────┴────────────────────────────────┘
```

### Rules

- Empty states explain what a case is and provide one New Case action.
- Network/save errors preserve form state and provide retry; technical diagnostics stay secondary.

## 6. Intelligence

### User question

Where should Quality focus surveillance and why?

### Wireframe

```text
┌───────────────────────────────────────────────────────────────────────────┐
│ QUALITY INTELLIGENCE                         Evaluate signals  Configure   │
│ Deterministic surveillance priorities with source-backed rationale         │
└───────────────────────────────────────────────────────────────────────────┘
┌─────────────┬──────────────┬──────────────────┬────────────────────────────┐
│ Mandatory   │ High priority│ New source change│ Unresolved blockers        │
└─────────────┴──────────────┴──────────────────┴────────────────────────────┘
┌───────────────────────────────────────────────────────────────────────────┐
│ SURVEILLANCE PRIORITIES                                                   │
│ 1 HIGH  Procurement / supplier surveillance                Schedule audit │
│   2 overdue CARs · 392 days since audit · repeat finding                  │
│   Sources: CAR-..., AUD-..., Supplier ...                                 │
│                                                                           │
│ 2 MANDATORY  DHC-8-400 capability introduction             Open Mission   │
│   Capability change · training gate incomplete                            │
└───────────────────────────────────────────────────────────────────────────┘
┌──────────────────────────────────────────┬────────────────────────────────┐
│ REQUIREMENT GRAPH / SIGNALS              │ APPROVAL IMPACT / BLOCKERS     │
└──────────────────────────────────────────┴────────────────────────────────┘
```

### Rules

- Ranked priorities are the hero content.
- Each item shows factor, source record, observation date and rationale without opening developer-style panels.
- No predictive probability language.

## 7. My Quality Work

### User question

What am I responsible for now?

### Wireframe

```text
┌───────────────────────────────────────────────────────────────────────────┐
│ MY QUALITY WORK                                           Refresh           │
│ Assigned audits, reviews, actions and decisions                              │
└───────────────────────────────────────────────────────────────────────────┘
┌─────────────┬──────────────┬───────────────────┬────────────────────────────┐
│ Overdue     │ Due this week│ Awaiting decision │ Open assignments           │
└─────────────┴──────────────┴───────────────────┴────────────────────────────┘
┌───────────────────────────────────────────────────────────────────────────┐
│ OVERDUE                                                                  │
│ Aircraft audit · Auditee                               6 Aug 2026  Open → │
│ Preparation pending · Lead auditor Stephen Mutambu                       │
├───────────────────────────────────────────────────────────────────────────┤
│ UPCOMING / OTHER                                                         │
└───────────────────────────────────────────────────────────────────────────┘
```

### Rules

- Raw UUIDs are never the main label.
- Each assignment has one obvious next action.

## 8. CAR Register and Create CAR

### Register

```text
┌───────────────────────────────────────────────────────────────────────────┐
│ CORRECTIVE ACTIONS                                      New CAR  Export    │
│ Open / overdue / effectiveness posture                                    │
└───────────────────────────────────────────────────────────────────────────┘
│ CAR | finding/source | owner | due | status | next action | ⋯             │
```

- One primary row action plus overflow for secondary actions.

### Create CAR

```text
┌──────────────────────── Create Corrective Action ──────────────────────────┐
│ Source finding                                                             │
│ [Finding ref + concise statement + audit source]                           │
│                                                                            │
│ Title                                                                      │
│ Summary                                                                    │
│                                                                            │
│ Responsible department             Responsible person                      │
│ Due date                           Priority / classification                │
│                                                                            │
│ Evidence / requirement context                                              │
│                                                  Cancel   Create CAR        │
└────────────────────────────────────────────────────────────────────────────┘
```

- Use a 680–760px dialog/drawer on desktop, full-screen sheet on small screens.
- Never render a tiny floating card in a blank page.

## Acceptance criteria

1. No QMS operational page uses less than 11.5px for meaningful text.
2. Normal working copy, tables, forms and event/task titles are at least 14px unless explicitly metadata.
3. All six permanent QMS workspaces share consistent header, metric, panel, button, table and empty-state language.
4. Missions is portfolio-first; People is person/authorization-first; Assurance is case-triage-first; Intelligence is priority-first.
5. Raw IDs are secondary metadata unless no human-readable identity exists.
6. At 1920×1080 / 100% zoom the user can read all primary information without magnification.
7. At 1366×768 the primary task remains usable through responsive collapse, not microscopic text.
8. Planner and Audit War Room patterns are preserved as the strongest existing interaction references.
9. CAR create/edit uses a proper bounded dialog/drawer with readable grouped fields.
10. Backend governance, audit lineage, RLS, immutable decisions and source ownership remain unchanged.
