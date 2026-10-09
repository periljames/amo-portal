# API / UI contract table (seed — Phase 3)

Rule: optional chaining is only valid when the contract says OPTIONAL. Otherwise fix the producing layer.

| FIELD / ENDPOINT | EXPECTED? | WHEN REQUIRED? | OBSERVED | FRONTEND BEHAVIOR | ROOT CAUSE (working) | FIX |
| --- | --- | --- | --- | --- | --- | --- |
| Overview “Active programmes” | REQUIRED clear definition | Always on Overview | `0` with “1 revision in 2026” | Shows contradictory KPI | Definition drift (active vs revisions) | One definition; align Overview to Programme SoT |
| Programme readiness / unscheduled | REQUIRED when programme list includes readiness | Programme year selected | 0 unscheduled on draft with 0 requirements | Shows 0 | Likely legitimate empty programme | Keep 0 only if requirements exist & readiness payload present; else Unavailable |
| Prepare `controlled_preparation` / checklist bindings | REQUIRED after prepare init OR explicit not-started | Entering Prepare | 0 bindings, Scope/Criteria “—” | Renders empty fields + **100% readiness** | Likely missing init **or** false readiness math on 0/0 | Do not show 100% on 0 required; show Not started / Needs setup |
| Live checklist items | REQUIRED for Live fieldwork OR explicit prerequisite | Live stage when fieldwork allowed | 0 items + **HTTP 500 toast** | Empty checklist + error banner | Backend 500 and/or stage not initialized | Trace Live checklist API; fix 500; if Prepare incomplete, block Live with next action (not empty workbench + 500) |
| Finding on Live vs Findings register | REQUIRED consistency | Finding exists on audit | Live shows F-001; register Needs Review empty | Dual truth | Filter/query/register read-model mismatch | Root-cause register query vs finding status mapping |
| Follow-up CAR queue | REQUIRED linkage when finding needs CAR | Follow-up / finding open | 0 CARs; “CAR linkage unavailable” on Closing | Empty queue + closing blocker | Missing CAR creation / link | Make Create CAR the next action; do not show Follow-up open without CARs unless intentional |
| Closing report generation | REQUIRED only after fieldwork complete | Closing | Blocked with orange prerequisite | Correct prerequisite text; passkey still interactive | UI allows later steps early | Disable/hide passkey until prior gates pass |
| Archive retention policy | OPTIONAL until configured | Disposition | “No retention policy” | Configure CTA | Likely expected sparse | Keep as deliberate incomplete governance |
| Checklist Create template enabled | REQUIRED to create | Library empty | Button disabled; Item 1 form still visible | Dead primary CTA + confusing editor | Validation without UX gate | Enable when form valid **or** hide editor until template exists |
| Audits list page size 250 | Bounded list OK only if intentional | Workspace | Cap 250, no page controls | Pseudo-bound | Product debt | AG Grid + 25/50/100 + server page if available |
| Stage resolve APIs | REQUIRED for stage mounts | All stage routes | Setup/Prepare/Closing/Follow-up/Archive mount | After Tranche 2 unify | Previously wrong resolver | Keep tenant resolve; verify Live 500 separately |
| Live `POST .../presence/heartbeat` | REQUIRED collaboration beacon OR silent failure | Live stage mount | **HTTP 500** toast “Action failed · Reference: 500” | Toast while empty checklist still renders | **BACKEND ROUTING** — presence routes behind canonical `/{module_path:path}` catch-all (GET returned audits module payload; POST 500) | **FIXED** — promote presence routes ahead of catch-all; silence heartbeat toasts as defense |
| Live `GET .../checklist-execution-governance` | REQUIRED items OR explicit prerequisite | Live fieldwork | **200** `{items:[]}` | Empty checklist · Progress 0/0 | **PREREQUISITE** — no checklist bindings / items; not the 500 source | Keep empty workbench + Prepare next action; do not invent items |
| Finding F-001 vs register `workflow_stage=needs_review` | REQUIRED stage continuity | Finding exists | Live shows F-001; Needs Review `total=0` | Dual truth | **FILTER** — finding has `closed_at` set; paged register correctly excludes from needs_review; appears under `closed` | **FIXED (UX)** — Live labels “· Closed”; not a register omit. Use Closed stage |
| Prepare readiness percent | REQUIRED honest empty state | 0 required requests | Was **100%** with “0 of 0” | Fake success | **FRONTEND STATE** — `total ? … : 100` | **FIXED** — show N/A / “0 required · Not started” |

---

## Error classifications observed

| Error | Class | Notes |
| --- | --- | --- |
| Live Internal Server Error 500 | BACKEND ROUTING (presence heartbeat) | Fixed route order + silent heartbeat toast |
| Live empty checklist | PREREQUISITE | Checklist GET 200 empty; Prepare incomplete |
| Findings register empty vs Live finding | FILTER (closed_at) — not omit | F-001 in Closed stage; Live now shows Closed |
| Prepare 100% on 0/0 | FRONTEND STATE (false readiness) | Fixed to N/A |
| Create template disabled | FRONTEND STATE / VALIDATION | Dead CTA |
| Full-page “Loading portal workspace…” on route change | FRONTEND STATE / TRANSITION | Violates stable shell |
