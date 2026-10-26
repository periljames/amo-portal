# QMS Assurance workspace review — 18 October 2026

## Confirmed faults and repairs

| Area | Confirmed fault | Repair |
|---|---|---|
| Findings register | The response contained four findings but the inner AG Grid measured zero height | Give the grid a definite, row-aware height; keep its scroll area bounded for larger pages |
| Finding navigation | With filters open, mouse-down closed the filter rail and rerendered the target before its click fired | Keep inline filters open until explicitly closed; first-click navigation works |
| Observations | An unlinked observation was labelled RCA/CAP with an instruction to create a CAR | Independent observation queue, labels and actions; closure remains based on the finding record |
| Finding due filters | Original due date was used even when a later agreed target existed | Use the agreed target first, consistently with the case workspace |
| Cancelled CARs | An unresolved finding with a cancelled CAR could fall out of Quality review | Keep it in the review queue, consistently with the frontend lifecycle |
| Finding rows | Dates and secondary lines were clipped by inherited grid line height | Explicit two-line cell layout, readable classification, lighter weights and concise stage labels |
| Analysis | Responsive chart container measured zero height | Definite responsive chart height and stable grid/register sizes |
| Analysis population | Only the first 100 records were used | Cancellable bounded pagination reads the complete population; incomplete/repeated/changing pages produce an error rather than incorrect totals |
| Analysis accounting | Department exposure counted overdue records twice; workload categories overlapped | Keep overdue a subset of open and make workload categories mutually exclusive |
| Analysis filtering | Finding metrics ignored CAR/report filters | Apply the displayed scope, date and search filters to finding metrics and conversion charts |
| Analysis outputs | A failed source could appear as zero; partial reports could be exported | Mark missing sources unavailable and disable incomplete output; preserve available independent data |
| People loading | One rejected section could discard all lists | Isolate section failures, retain the other successful lists and expose retry controls |
| People paging | Lists stopped at 500 records and case searches ran after limiting | Stable server paging, accurate total counts, server-side search and complete frontend page reads |
| People selection | A prior case's details could remain while another case loaded | Key detail queries by tenant/person/case, prevent mismatched decisions and participate in realtime invalidation |
| People preparation | Live PostgreSQL PATCH returned 500: FOR UPDATE attempted to lock the nullable side of the joined rule | Lock only the authorization-case row; explicitly scope privilege locks as well |
| People cancellation | Incorrect nominations had no cancellation workflow | Add an attributed, reasoned cancellation that retains the case and history without issuing authority |
| Forms/navigation | Filter labels were unstable; analysis tabs lacked arrow navigation; modal keyboard behavior was incomplete | Stable control names, arrow/Home/End tab navigation, focus containment, Escape and focus restoration |
| Evidence Vault | Search read only an unpopulated legacy table; current evidence was invisible | Index retained audit, finding, CAR and authorization evidence plus archive packages, with tenant/source permissions, accurate paging, source links and existing governed downloads |
| Shared UX | Inconsistent page identity, heavy typography, large headers/empty states and desktop-only finding rows | Compact titles, existing warm theme tokens, lighter weights, consistent controls and mobile finding cards |

Approval still requires a prepared case in READY_FOR_DECISION. That backend protection existed before this review and remains covered by tests. No new bypass or simulated approval is added to the application.

## Automated verification

- 60 backend tests passed (58 in the combined run, plus two additional legacy/archive cases; the five-test evidence suite was rerun successfully). Added ORM workflow tests exercise nomination, preparation, evidence, submission, return/resubmission, approval, periodic review, suspension, reinstatement, renewal, revocation and cancellation. Their database is isolated SQLite; email records remain zero.
- PostgreSQL-specific SQL compilation verifies FOR UPDATE OF quality_authorization_cases, excluding the nullable joined rule. The actual live PostgreSQL retry is recorded below.
- 68 frontend tests passed, including complete-population loading beyond 100 rows, duplicate/incomplete/changing pagination, cancelled reads, section failure isolation, policy visibility, observations, non-overlapping charts, routes and realtime invalidation.

## Live checks

- Analysis charts, filters, keyboard tabs, CSV output and 390 px layout passed against the four existing findings and three CARs.
- Findings stage filter returned the observation independently; its case view did not offer a mandatory CAR. First-click navigation with filters open passed. All four findings rendered as mobile cards without horizontal overflow.
- A clearly labelled simulated authorization nomination was created through the frontend as James Muisyo. Live preparation first exposed the PostgreSQL lock error above. The same case (`ID-FKHWPKWJ`) subsequently passed preparation (200), file upload (201), checksum-matching download and cancellation (200) through the frontend after the lock repair. The case remains in history as Cancelled; no authorization was issued.

No email actions are performed. No live authorization approval, renewal, revocation or CAR response is performed. The existing audit CARs remain for Elvin to action. Browser checks use the current authenticated administrator/auditor session; other roles are covered by permission and workflow tests, not separate live sign-ins.

Live receipts: `.artifacts/audit-workflow-run/assurance-live-case-created.json`, `assurance-live-case-verified.json`. The synthetic attachment retained its original SHA-256 (`71e3a7eff34f0657fb9e894e2614d1285fb291058a4d9a09a960c74a4340c96f`).

The PostgreSQL retry is confirmed by the live preparation PATCH 200, subsequent upload 201 and cancellation POST 200 for the same synthetic case. Mobile People/Case views now use a focused detail view with an explicit back action.

## Workspace and resilience checks

Nine live pages finished loading with no captured page exceptions or failed API reads: Overview, Programme, Calendar, Scopes, Audits, Checklists, Evidence Vault, Recycle bin and People. This is read/navigation coverage; it does not claim every destructive operation or every role was exercised live.

A fresh browser context with service workers disabled returned a controlled 503 for authorization reviews. Other People sections remained usable and retry recovered after removing the injected failure. A warm browser correctly used retained data, so the failure-isolation assertion was repeated in the clean context rather than inferred from cached success.

Evidence source tests verify tenant boundaries, source permissions, self-service authorization scope, search, stable paging, source deep links and exclusion of private storage paths. Downloads continue to enforce the existing source endpoint permissions; the vault verifies retained SHA-256 before saving files when a checksum is available. Files are not served through a new bypass endpoint.

The frontend modal-layer check passed for 49 source files. Live browser event blocking recorded zero email attempts. No auditee CAR action was taken.

## Final output verification

The production build passed TypeScript, modal-layer and heavy-route chunk checks. Vite retains its existing large-chunk advisory; the application entry is 989 KiB and PDF/grid engines remain outside the entry graph.

The live Evidence Vault returned three retained files across audit, CAR and authorization sources with no source errors. Desktop and 390 px layouts passed. The source action opened the exact cancelled nomination; downloading preserved `SIMULATED_WORKFLOW_TEST_audit_notice.pdf` and matched SHA-256. Receipt: `.artifacts/audit-workflow-run/assurance-vault-verified.json`.

Additional isolated tests confirm legacy file-name variants and exclusion of archive packages after an executed disposition. No live disposition was performed.

The production preview repeated finding/observation navigation, analysis charts/filtering/keyboard tabs/CSV, checksum-verified evidence download/source navigation and the nine-page scan successfully, with zero attempted email actions. The final phone filter refinement measures 244 px high and retains 44 px controls; file actions appear within the first screen at 390 × 844.

The final rebuilt production shell was reloaded and checked again: archive-package search returned 200 with no packages and no source errors, and the compact mobile toolbar measured 244 px with no horizontal body overflow. All browser test interception was removed after verification. `git diff --check` passed; the transient login file was deleted.
