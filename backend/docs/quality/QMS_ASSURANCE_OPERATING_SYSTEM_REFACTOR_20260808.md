# QMS Assurance Operating System Refactor

**Date:** 2026-08-08  
**Status:** Architecture contract and phased implementation plan  
**Branch:** `agent/qms-assurance-operating-system-refactor`  
**Base:** `main@1c7407f05dbbe47d18ab472de839a49e66440593`

## 1. Decision

The Quality module will no longer evolve as a menu of registers that mirrors the Maintenance Procedures Manual table of contents. It will become the aviation **assurance and decision layer** over the AMO.

Quality should continuously answer:

1. What changed?
2. What is deteriorating?
3. Which approval, capability, control, or personnel privilege is becoming exposed?
4. Why is it happening?
5. What decision or action is required next?
6. Did the corrective or preventive control actually work?

The primary navigation is therefore reduced to six workspaces:

```text
CONTROL ROOM | PLANNER | MISSIONS | PEOPLE | ASSURANCE | INTELLIGENCE
```

`My Work` becomes a global task drawer rather than a permanent full module. Settings remain administrative and do not compete with operational navigation.

The system keeps the specialist audit and CAR workflows already proven in the repository, but they become governed lenses inside Assurance instead of defining the information architecture of the entire QMS.

## 2. Source-of-truth principle

Quality must not duplicate data that another operational module owns.

| Domain | Authoritative owner | Quality responsibility |
|---|---|---|
| Tooling/calibration | Workshops / tooling | assurance state, exposure, OOT blast radius, control effectiveness |
| Work execution | Work orders / workpacks | surveillance, sampling, drift, evidence, findings |
| Personnel | Accounts / HR / Training | eligibility, competence, internal privilege, authorization decisions |
| Rosters | Rostering | future competent coverage and privilege demand |
| Suppliers / receipts | Procurement / Stores | approval decision, supplier quality trend, suspension/escalation |
| Controlled documents | Document Control | requirement/control mapping, currency exposure, change impact |
| Reliability | Reliability | quality signals where control or process performance is implicated |
| Safety occurrences | Safety / SMS | linked assurance evidence and shared investigation context |
| Aircraft capability / AMP | Fleet / Planning / Engineering | capability readiness, self-evaluation, approval assurance |
| Audits / findings / CAPA | Quality | governed execution, investigation, corrective action, effectiveness |

A Quality page must not exist merely because a table exists.

## 3. Regulatory and procedural anchors

The refactor is designed around the duties already present in the Safarilink MPM and KCAR 2025 transition material, including:

- Head of Quality continuous monitoring, audit scheduling, corrective-action follow-up and liaison duties;
- certifying staff qualification, records and company authorization;
- qualifying inspectors and technicians;
- competence assessment of AMO personnel;
- capability-list self-evaluation before adding an article or rating;
- exemptions and concessions;
- control of manufacturers' working teams and subcontracted activities;
- missing-tool, occurrence and Quality Work Instruction controls;
- supplier evaluation and monitoring;
- management review and continuous quality improvement.

The architecture must support globally applicable jurisdiction packs so Kenya, EASA, FAA and ICAO obligations can map to the same control graph without hard-coding a Kenya-only product model.

## 4. Core operating model: Assurance Graph

```text
REGULATION / MANUAL / CONTRACT / CUSTOMER REQUIREMENT
                         |
                         v
                  ASSURANCE REQUIREMENT
                         |
                         v
                    ASSURANCE CONTROL
                   /       |        \
                  /        |         \
              PEOPLE    PROCESS     ASSET
                  \        |         /
                   \       |        /
                         v
                    LIVE EVIDENCE
                         |
                         v
                   CONTROL HEALTH
                         |
              +----------+----------+
              |                     |
           HEALTHY               SIGNAL / DRIFT
                                    |
                        +-----------+-----------+
                        |           |           |
                      REVIEW    INVESTIGATE    MISSION
                                    |
                                    v
                                 ACTIONS
                                    |
                                    v
                           EFFECTIVENESS TEST
```

The graph is relational and auditable. AI may explain or suggest; AI may not approve, accept a root cause, grant a privilege, close a finding, authorize work, or declare compliance.

## 5. Canonical route tree

The new canonical user-facing route tree is deliberately small:

```text
/maintenance/:amoCode/quality
|
|-- /control-room
|-- /planner
|-- /missions
|    `-- /:missionId
|-- /people
|    `-- /:personId
|-- /assurance
|    |-- /:caseId
|    `-- /investigations/:investigationId
|-- /intelligence
|-- /controls/:controlId
`-- /settings
```

Existing deep links remain supported during migration:

```text
/audits/*                   -> Assurance · Audit lens
/findings/*                 -> Assurance · Finding lens
/cars/*                     -> Assurance · CAPA lens
/risk/*                     -> Intelligence · Risk lens
/change-control/*           -> Missions
/suppliers/*                -> Assurance · Supplier lens
/equipment-calibration/*    -> Assurance · Tooling lens
/external-interface/*       -> Assurance · External lens
/management-review/*        -> Intelligence · Management Review lens
/evidence-vault/*           -> contextual Evidence Room
/documents/*                -> Document Control handoff
```

No destructive URL migration is required in Phase 1. Bookmarks and regulated evidence references must continue to resolve.

## 6. Global Quality shell

Every Quality page uses one operational navigation row only.

```text
+--------------------------------------------------------------------------------+
| PORTAL HEADER                                              alerts  user menu   |
+--------------------------------------------------------------------------------+
| QUALITY  Control Room  Planner  Missions  People  Assurance  Intelligence     |
|                                                      My Work (6)   Settings    |
+--------------------------------------------------------------------------------+
| PAGE CONTENT                                                                   |
+--------------------------------------------------------------------------------+
```

Rules:

- no second `Operations / Controls / Evidence / Intelligence` tab strip;
- no DOM-injected duplicate navigation as a long-term architecture;
- specialist record tabs are allowed only inside the record workspace;
- route permissions hide unavailable navigation rather than producing dead links;
- mobile collapses navigation; it does not create an endlessly scrolling tab row.

## 7. Control Room wireframe

Purpose: show where Quality attention can change an outcome today. This is not a data-entry page.

```text
+ QUALITY ASSURANCE                                        LIVE 08 AUG 07:54 ----+
| Ask Quality: What can compromise our approval in the next 60 days?       [cmdK]|
+--------------------------------------------------------------------------------+
| DECISIONS DUE | EMERGING SIGNALS | APPROVAL EXPOSURE | MY ACTIONS              |
|       4       |        7         |         3         |      6                  |
+---------------------------------------+----------------------------------------+
| EMERGING ASSURANCE SIGNALS            | APPROVAL / PRIVILEGE OUTLOOK           |
| Repeat workpack omissions   HIGH      | DHC8 certifying coverage    AT RISK    |
| 4.2 sigma above baseline              | gap projected 28 Aug                   |
| Investigate ->                        |                                        |
| Supplier paperwork rejection HIGH     | Battery Shop capability     HEALTHY    |
| Review supplier ->                    |                                        |
| Tool use after expiry       CRITICAL  | AMO renewal                AT RISK     |
+---------------------------------------+----------------------------------------+
| CONTROL HEALTH: People | Capability | Maintenance | Tooling | Supplier | Data  |
+---------------------------------------+----------------------------------------+
| WHAT CHANGED SINCE MY LAST REVIEW     | UPCOMING DECISIONS                     |
| 2 regulatory impacts                  | 12 Aug Authorization Board              |
| 1 effectiveness test failed           | 15 Aug Capability gate review          |
| 3 new signals                         | 19 Aug QMS surveillance                 |
+---------------------------------------+----------------------------------------+
```

The Control Room must never repeat one count in multiple cards without adding a new denominator, trend or decision context.

## 8. Planner wireframe

The existing modern planner is retained and expanded into the temporal projection of the Assurance Graph.

```text
+ PLANNER                 AUGUST 2026          Month Week Agenda Timeline        |
| Sources: Audits Surveillance Missions Authorizations Training Reviews Tooling |
+------------------+-------------------------------------------+-----------------+
| mini calendar    | unified calendar / timeline               | selected item   |
| owners / filters | conflicts, due states, dependency marks   | decision/action |
+------------------+-------------------------------------------+-----------------+
| NEXT 7 DAYS                          | OVERDUE / DUE SOON                       |
+--------------------------------------------------------------------------------+
```

Planner events include audits, targeted surveillance, mission milestones, authorization boards, competence assessments, regulatory transition deadlines, concession/exemption expiry, effectiveness reviews and approval-renewal milestones.

The planner must compute conflicts such as competent-cover shortfalls or privilege expiry before a planned maintenance event.

## 9. Missions wireframe and semantics

A Mission is a controlled cross-department change/project with regulatory gates. It replaces generic change-control forms for high-value work.

Mission templates include:

- aircraft/type capability inclusion;
- component workshop capability addition;
- new line station;
- supplier/subcontractor approval;
- certifying privilege or authorization campaign;
- significant procedure/manual change;
- regulatory transition;
- AMO renewal;
- major corrective/preventive improvement project.

### Mission portfolio

```text
+ MISSIONS                                                    + New Mission      |
| Active | Planning | Completed | Templates                                      |
+--------------------------------------------------------------------------------+
| MISSION                 TYPE              OWNER        READY     RISK            |
| DHC8-400 inclusion      Capability        Quality       71%      HIGH       ->   |
| Battery shop expansion  Capability        Workshop      83%      MEDIUM     ->   |
| AMO renewal 2026        Regulatory        Quality       58%      HIGH       ->   |
+--------------------------------------------------------------------------------+
```

### Capability inclusion detail

```text
DHC-8-400 CAPABILITY INCLUSION                                      71% READY

Regulatory basis: KCAR AMO / MPM 1.8 / capability self-evaluation

GATE                          STATE        EVIDENCE / EXCEPTION            OWNER
Approval rating               PASS         within rating                   Quality
Facilities                    PASS         hangar verified                 Engineering
Technical data                PASS         AMM/IPC/SRM current             DMS/Planning
Tooling                       AT RISK      3 mandatory tools unresolved    Stores
Materials                     PASS         adequate                       Procurement
Personnel                     AT RISK      2 privileges missing            People
Training                      IN PROGRESS  3 type courses                  Training
Procedures                    PASS         current                        Quality/DMS
Contracted functions          PASS         NDT subcontractor approved     Quality
Manpower                      AT RISK      Sep coverage below demand       Rostering
Safety/change assessment      PASS         residual risk accepted         Safety
Quality self-evaluation       LOCKED       waits for hard gates           Quality
Accountable Executive         LOCKED       waits for QA sign-off          AE
Authority submission          LOCKED       waits for internal approval    Quality
```

Mission gates are not averaged into a legal-compliance score. A failed hard gate blocks readiness regardless of soft progress percentage.

## 10. People & Privileges wireframes

Purpose: answer whether a person can perform a task, on a given aircraft/component, at a location and time, under the AMO approval.

### Team view

```text
+ PEOPLE & PRIVILEGES                                Forecast next 90 days      |
| Role | Aircraft/Type | Location | Eligibility | Expiring                         |
+--------------------------------------------------------------------------------+
| James Engineer     B1 DHC8      NBO     94% evidence       Ground run 29 Aug  ->|
| Peter Technician   Mechanic     NBO     89% evidence       HF 18 Sep          ->|
+--------------------------------------------------------------------------------+
```

### Person assurance passport

```text
JAMES ENGINEER                                  ELIGIBLE · 94% evidence complete

CURRENT PRIVILEGES                 HARD GATES
Line CRS          VALID            AMEL                  VALID
Base CRS          VALID            Company authorization VALID
Duplicate Insp.   VALID            Human Factors         VALID
Engine Ground Run EXPIRES 29 AUG   SMS                    VALID
                                   Recent exercise        1/3 missing
                                   Competence review      VALID

DEMAND FORECAST
Required DHC8 B1 shifts  14
Qualified coverage       11
Predicted shortfall       3

Recommendation: renew ground-run privilege and obtain one recent-exercise record.
```

Hard eligibility gates are Boolean and fail closed. Predictive exposure is calculated separately from legal eligibility.

## 11. Assurance workspace

Assurance is a single workspace with lenses, not separate top-level modules.

Lenses:

- Signals
- Audits & Surveillance
- Findings
- CAPA
- Supplier
- Tooling / Calibration exposure
- External / Regulator
- Effectiveness
- Controls

### Signal list

```text
+ ASSURANCE SIGNALS                                    + New manual signal       |
| All | Mine | Investigations | Trends                                         |
+--------------------------------------------------------------------------------+
| SIGNAL                         SOURCE        SEVERITY  TREND   STATUS           |
| Workpack omissions rising      Maintenance   HIGH      up      Investigating ->|
| Tool used after calibration    Tooling       CRITICAL  new     Open          ->|
| Supplier paperwork rejects     Stores        MEDIUM    up      Open          ->|
+--------------------------------------------------------------------------------+
```

Quality should be able to create an assurance case from any signal while preserving source lineage.

## 12. Investigation Studio

The Investigation Studio is not a free-text `root cause` field.

Supported analysis methods:

- evidence-constrained 5 Whys;
- Ishikawa / causal map;
- MEDA / HFACS-ME classification where appropriate;
- BowTie / barrier analysis;
- fault tree / cause-consequence analysis;
- Pareto / recurrence clustering;
- statistical process-control analysis;
- change-impact analysis;
- supplier defect-pattern analysis.

```text
INVESTIGATION · CAR/26/033 · Tool control failure

SYSTEM CONTEXT
Aircraft 5Y-SLK | WO 2026-01771 | Tool TL-0041 | Calibration expired +3 days
Personnel 4 | Procedure QWI-003 Rev 2 | Shift Afternoon

Suggested method: MEDA + Barrier Analysis

CAUSAL MAP
Expired tool used
  |- calibration warning not surfaced
  |- issue process allowed release
  `- work order did not validate calibration state

SIMILAR EVENTS
89% CAR/25/018
76% OBS/26/041

HYPOTHESES
1. Tool-control gate absent at issue point         STRONG
2. Personnel knowledge deficiency                  WEAK
3. Calibration scheduling capacity                 INSUFFICIENT EVIDENCE
```

AI can suggest or challenge a hypothesis, but a named authorized human must accept the root cause.

## 13. Effectiveness engineering

A CAPA cannot close merely because an action was completed.

Every material corrective action should define:

- baseline metric;
- expected future state;
- leading indicator;
- observation window;
- source dataset;
- review date;
- pass/fail rule;
- accountable reviewer.

Example:

```text
Baseline:          8 tool-control deviations / 90 days
Expected:          <= 1 / 90 days
Leading indicator: 100% tool issues pass automatic validity gate
Observation:       90 days
Review:            15 Nov 2026
```

A recurrence inside the observation window creates an effectiveness challenge and reopens Quality review; it does not silently rewrite the original finding.

## 14. Intelligence workspace

Intelligence combines analysis, regulatory impact and management-review preparation.

Primary lenses:

- Executive
- Performance
- Risk
- Trends
- Regulatory
- Approval Digital Twin
- Management Review
- Exports

Statistical methods are preferred before AI:

| Problem | Method |
|---|---|
| process drift | EWMA / CUSUM |
| event frequency | exposure-normalised rates |
| low-volume supplier comparison | Bayesian shrinkage |
| recurring issues | clustering + similarity |
| CAR aging | survival / hazard model |
| privilege and resource exposure | constraint solving |
| surveillance targeting | risk-weighted sampling |
| change impact | graph traversal |
| anomaly discovery | statistical / ML anomaly detection |

All model outputs must retain source lineage, calculation version, inputs, as-of time and explanation.

## 15. Approval Digital Twin

A live approval graph is the long-term differentiator.

```text
AMO APPROVAL
|
|-- Rating / SOP
|    `-- aircraft / engine / component / specialized activity
|-- Capability
|    |-- technical data
|    |-- tools
|    |-- facilities
|    |-- materials
|    |-- procedures
|    `-- contracted services
|-- People
|    |-- competence
|    |-- licences
|    |-- training
|    `-- internal privileges
|-- Execution controls
|-- Quality controls
`-- Regulatory evidence
```

The target system question is:

> Can this AMO legally and practically perform this work at the requested time, location and scope?

The answer must explain blockers and evidence, not return an opaque score.

## 16. Regulatory intelligence

Requirements are versioned in jurisdiction packs and map to controls rather than living as a second document library.

Target jurisdictions:

- Kenya / KCAA / KCAR 2025;
- ICAO SARPs and guidance where applicable;
- EASA Part-145 / AMC / GM;
- FAA 14 CFR Part 145 and relevant advisory circulars;
- tenant/operator/customer contractual requirements.

A regulatory change can therefore produce an impact graph:

```text
Requirement changed
  -> 4 capability templates
  -> 2 MPM sections
  -> 1 QWI
  -> 17 capability nodes
  -> 6 personnel assessments
  -> create Regulatory Change Mission
```

Human review remains mandatory before requirements or controls are made authoritative.

## 17. Domain primitives

The final architecture should converge on these concepts. Some continuous-assurance equivalents already exist in the current repository and should be extended rather than duplicated.

| Primitive | Purpose |
|---|---|
| `AssuranceRequirement` | regulatory/manual/contract/customer obligation |
| `AssuranceControl` | how the organisation satisfies a requirement |
| `EvidencePointer` | typed pointer to authoritative evidence |
| `AssuranceSignal` | exception, drift, anomaly or emerging exposure |
| `AssuranceCase` | governed Quality review / investigation case |
| `Mission` | controlled cross-department project/change |
| `MissionGate` | hard or soft readiness dependency |
| `CapabilityNode` | approval/capability relationship and state |
| `PersonPrivilege` | internal authorization / scope / limitation |
| `CompetenceAssessment` | competence evidence and decision |
| `Decision` | explicit governed human decision |
| `Investigation` | structured RCA case |
| `CauseNode` / `Barrier` | causal model |
| `ImprovementAction` | corrective/preventive action |
| `EffectivenessTest` | proof an action/control worked |

No new duplicate operational register is to be introduced without an ownership analysis.

## 18. Phase plan

### Phase 0 — architecture lock

- commit this document;
- preserve current `main` deep links;
- create a six-workspace route/navigation registry;
- add route-contract tests;
- freeze creation of new generic QMS register pages.

### Phase 1 — shell and Control Room

- replace seven-item audit-centric top navigation with six workspaces;
- remove the duplicate Control Centre sub-navigation;
- reframe current `dashboard-v2` data as decisions, signals, exposure and control health;
- move diagnostics behind a data-health disclosure;
- retain audit planning and CAR deep links.

### Phase 2 — Missions

- mission model, templates, dependencies, gate engine and evidence pointers;
- first full template: aircraft/capability inclusion;
- capability self-evaluation orchestration across Fleet, Planning, Tooling, Training, Rostering, DMS and Quality;
- explicit Accountable Executive and Authority gates.

### Phase 3 — People & Privileges

- privilege model and scope;
- competence assessment workflow;
- internal authorization board;
- training/licence/recency/experience evidence;
- future demand / roster constraint checks;
- immutable decision history.

### Phase 4 — Assurance Cases and Investigation Studio

- unified signals/cases;
- audit/finding/CAPA lenses;
- method-driven RCA;
- evidence-linked causal nodes;
- similar-event retrieval;
- effectiveness plans and recurrence challenge.

### Phase 5 — Intelligence and Digital Twin

- statistical signal engine;
- risk-targeted surveillance recommendation;
- regulatory impact graph;
- approval/capability digital twin;
- management-review pack generation.

### Phase 6 — legacy consolidation

- convert obsolete register pages to lenses or redirects;
- remove generic QMS renderer from regulated workflows;
- remove DOM navigation injection after every specialist workspace mounts the shared shell directly;
- retain compatibility redirects and audit evidence links.

## 19. Phase 1 acceptance criteria

1. One permanent Quality navigation row.
2. Six operational destinations only: Control Room, Planner, Missions, People, Assurance, Intelligence.
3. Existing audit/CAR/document deep links continue to resolve.
4. No second `Operations / Controls / Evidence / Intelligence` navigation strip.
5. Root Control Room shows decisions/signals/exposure rather than duplicate count cards.
6. No red status without an actionable destination or explanation.
7. Diagnostics are not permanent primary content.
8. Permissions hide inaccessible destinations.
9. Every new canonical path is covered by route tests.
10. Unknown QMS paths fail safely.
11. Existing Planner behavior remains intact.
12. Audit and CAR specialist workflow ownership remains intact.
13. Generic register rendering is not expanded.
14. No AI-generated state change is introduced.

## 20. Test and release strategy

Every slice must run the applicable Quality CI on the exact head. Minimum checks:

- TypeScript route registry tests;
- frontend lint/typecheck/build for modified QMS surfaces;
- QMS route/deep-link browser contracts;
- existing modern planner Playwright suite;
- audit workflow browser suite;
- CAR governed workflow suite;
- backend QMS tests affected by new APIs/models;
- clean PostgreSQL Alembic upgrade for any schema slice;
- tenant isolation and permission tests;
- negative controls proving no hard compliance gate is converted to a weighted score.

The PR remains draft until exact-head CI is green for the slice being claimed. Later phases may remain intentionally incomplete, but no partially implemented screen may falsely advertise readiness or predictive confidence.

## 21. Immediate implementation scope on this branch

This branch begins with Phase 0 and the first Phase 1 frontend slice:

- establish the six-workspace navigation contract;
- add canonical top-level workspace routes while retaining legacy deep links;
- rebuild the root as `Control Room` rather than the current duplicate-navigation Control Centre;
- introduce purposeful placeholder surfaces for Missions, People, Assurance and Intelligence only where a governed source workflow does not yet exist;
- route Planner to the already proven modern planner;
- do not add new duplicate backend registers.

Subsequent commits will add Mission, People/Privilege, Assurance Case and Intelligence domain APIs only after their source ownership and migration contracts are explicit.
