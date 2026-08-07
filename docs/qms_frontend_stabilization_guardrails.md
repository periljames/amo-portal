# QMS Frontend Stabilization Guardrails

## Purpose

This document is the acceptance framework for QMS frontend changes. It exists to prevent narrow fixes that leave adjacent workflow defects, duplicate implementations, unbounded data loading, or visually polished dead ends behind.

A QMS frontend change is not complete merely because the named control works or a local unit test passes. Every change must review the affected workflow from entry route through list, record, action, evidence, approval/review, and return navigation where those stages apply.

## Required review radius

For every QMS frontend change, review all of the following before declaring the work complete:

1. **Route ownership** — identify every route and alias that reaches the workflow. Exactly one live page should own each list, record, creation, review, or evidence experience.
2. **Adjacent workflow actions** — verify links and CTAs land in the authoritative governed workflow rather than a reduced duplicate form or explanatory dead end.
3. **Data scale** — list/search surfaces must use bounded server-side pagination or cursor/offset contracts. Do not bulk-load a tenant register and then paginate it in the browser.
4. **Filtering and navigation** — search and filters must be URL-stable where appropriate, requests should be debounced, and navigation should not be duplicated by a second competing tab bar.
5. **Operational hierarchy** — the first viewport should prioritize exceptions, assigned work, deadlines and actions. Secondary analytics belong behind drill-down or progressive disclosure.
6. **Governance** — AI or automation may rank, summarize and recommend, but approval, acceptance, verification, closure and other controlled decisions remain explicit human actions in the governed source record.
7. **Accessibility and density** — tables must remain usable with keyboard navigation, visible focus, sticky context where useful, responsive layouts, and bounded vertical growth.
8. **Failure states** — partial-source failure, empty results, authorization failure and retry paths must be understandable without exposing raw implementation detail to ordinary users.
9. **Regression radius** — run the QMS-specific CI plus any adjacent module CI whose shared route, shell, migration, data contract or component is touched.
10. **Deletion of superseded UI** — once canonical replacement ownership is proven, remove orphaned or competing pages rather than leaving multiple implementations available for future accidental routing.

## Current canonical ownership audit

| Area | Current intended owner | Stabilization status | Remaining concern |
| --- | --- | --- | --- |
| Control Centre | `QmsOperationalControlCentre` + governed assurance hubs | In progress in PR #480 | Validate browser behavior and continue drill-down review. |
| Calendar / planner | `QmsPlannerLivePage` / planner V2 | Established by #436 | Preserve as the only calendar owner; do not recreate scheduling UI elsewhere. |
| Audit planning / schedules | `QualityAuditPlanSchedulePage` and audit specialist pages | Specialist owner exists | Audit-plan deep links should open only capabilities the page actually supports. |
| Audit execution | `QualityAuditRunHubPage` | Specialist owner exists | Continue scale/density review of long execution workspaces. |
| Evidence Vault lists/search | bounded `QmsRegisterPage` | Consolidated in PR #480 | Record viewer remains `QualityEvidenceViewerPage`; verify every package/search route follows this split. |
| Evidence record viewer | `QualityEvidenceViewerPage` | Specialist owner exists | Keep viewer distinct from list/search ownership. |
| CAR / CAPA lists | bounded canonical register surface | In progress | Must not regress to the 1,000-row client load in `QualityCarsPage`. |
| CAR / CAPA authoring/review/evidence | `QualityCarsPage` | Existing specialist capability | Route ownership is split and creation routing still needs consolidation; page currently contains an unbounded register load that must be separated or corrected. |
| Findings | bounded canonical register + compatibility detail surface | Needs deeper review | Creation/detail ownership must be mapped before legacy fallback can be removed. |
| Risk & opportunities | bounded canonical register + compatibility detail surface | Needs deeper review | Confirm specialist actions and record detail ownership. |
| Change control | bounded canonical register + compatibility detail surface | Needs deeper review | Confirm controlled creation/approval route ownership. |
| System & processes | bounded canonical register + compatibility detail surface | Needs deeper review | Generic rows may be insufficient for objective/process management actions. |
| Controlled documents | bounded canonical register + document specialist routes | Needs deeper review | Avoid duplicating Document Control module capabilities inside QMS. |
| Suppliers | bounded canonical register + compatibility detail surface | Needs deeper review | Review evaluation/audit/approval workflows and data scale. |
| Equipment & calibration | bounded canonical register + compatibility detail surface | Needs deeper review | Review due/overdue/certificate lifecycle and data scale. |
| External interface | bounded canonical register + compatibility detail surface | Needs deeper review | Review commitments/responses and authority correspondence ownership. |
| Management review | bounded canonical register + compatibility detail surface | Needs deeper review | Dashboard/actions should become operational rather than report-only. |
| Reports & analytics | bounded canonical register / governed reports | Needs deeper review | Avoid rendering large undifferentiated metric inventories in one viewport. |
| QMS settings | canonical settings views + compatibility surface | Needs deeper review | Confirm one configuration owner per setting and remove duplicate controls. |
| AeroDoc | AeroDoc specialist pages | Specialist owner exists | Keep separate from generic canonical registers. |

## Known defects discovered during PR #480 audit

### CAR list contract misuse

`qmsListCarRegister` already supports `limit`, `offset` and returns `total`, but `QualityCarsPage` currently requests up to 1,000 rows and applies search/filter/page slicing in the browser. This must not become the canonical large-tenant register implementation.

### Generic-register contract mismatch corrected in PR #480

The canonical backend caps a page at 50 rows. The earlier frontend offered 60 and 100 rows, which advertised unsupported behavior. PR #480 limits the selector to server-supported values and exposes page/range state instead.

### Evidence duplication corrected in PR #480

The orphaned `QualityEvidenceLibraryPage` duplicated evidence browsing while performing broad client-side source loading. PR #480 removes it and gives Evidence Vault list/search/package routes one bounded owner while retaining the dedicated record viewer.

### Compatibility frontend remains transitional

`QmsCanonicalLegacyPage` remains only because some record/detail workflows still depend on it. It is not a license to add new functionality there. Each remaining path must be mapped to a specialist or bounded canonical owner before the corresponding legacy branch is removed.

## Control Centre UX rules

The QMS root is an operational cockpit, not a wall of analytics.

The default viewport should answer, in order:

1. What requires attention now?
2. What is assigned to me?
3. What is due soon?
4. What exposure is increasing?
5. Where do I open the governed source record to act?

Longer forecasts, KPI collections, diagnostics, source inventories and management-review material should use drill-down or disclosure unless the information is itself the current exception.

## Definition of done

A QMS frontend PR may be considered ready only when:

- every changed route has one identified owner;
- no affected list relies on unbounded tenant-wide client loading;
- duplicate or orphaned superseded UI has been removed when safe;
- controlled actions hand off to the authoritative workflow;
- URL/filter/navigation behavior remains deterministic;
- responsive, keyboard and empty/error states are covered;
- QMS Planner CI and Quality Module CI are green when their surfaces are affected;
- adjacent module CI is green when shared contracts are changed;
- the PR has been reviewed for regression outside the originally requested element.
