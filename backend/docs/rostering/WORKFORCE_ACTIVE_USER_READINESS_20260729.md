# Workforce active-user roster readiness correction

## Problem corrected

The Workforce and HR employee register previously started from effective employment contracts. Active tenant users without an effective contract were therefore omitted entirely, producing an empty `0 of 0 employees` register even when active user accounts existed.

## Canonical behavior

1. The register starts from every active, non-system user belonging to the current tenant.
2. Employment contracts, bases, work-pattern assignments and approved leave are joined as readiness data.
3. Missing Workforce records remain visible as actionable readiness blockers; they never remove the user from the register.
4. When no contract is currently effective, the next future ACTIVE, ONBOARDING, or SUSPENDED contract is surfaced for editing rather than offering an overlapping contract creation.
5. Future starters remain in the currently effective-contract gap count until their contract becomes effective.
6. Authorized Workforce managers can create a missing effective contract or edit an existing one from the same register.
7. The contract editor uses the exact backend enums and tenant-owned canonical bases.
8. An authorized manager may explicitly create or repair the reserved `DEFAULT-DAY` shift and `DEFAULT-DAY-5X2` Monday-to-Friday pattern.
9. The default pattern is assigned only to active or onboarding employees with effective contracts who do not already have a valid active pattern. Existing unrelated active patterns are preserved.
10. All effective-date decisions use the tenant timezone.
11. Replacing an inactive current pattern closes the historical assignment and creates a new row effective on the tenant-local current date; historical records are never rewritten.
12. An existing reserved default-day assignment with a non-Monday anchor is safely re-effective-dated to the tenant-local week's Monday.
13. The default baseline creates draft roster input only. A planner must still review, validate, submit, approve and publish the roster.

## Review corrections

The blocker reviews identified and corrected six readiness and effective-dating defects:

- inactive pattern assignments are no longer rewritten in place across their historical interval;
- the five-day duty cycle is anchored to Monday rather than the day on which the bootstrap action is executed;
- future ACTIVE and ONBOARDING contracts are surfaced and edited instead of misclassified as missing contracts that invite an overlapping creation;
- future SUSPENDED contracts are also surfaced because contract-overlap validation treats them as conflicting records;
- future starters remain included in the currently effective-contract gap metric and receive an edit-future-contract action; and
- existing reserved default-day assignments with non-Monday anchors are safely re-effective-dated to the canonical Monday anchor.

These invariants are covered by Workforce regression contracts and the complete Rostering and Workforce test suites.

## Workforce and assistant usability

- The Workforce workspace is bounded on wide displays, uses stronger theme-aware foreground contrast, and raises operational text to an all-day readable baseline.
- The employee register remains a compact table where space permits and changes to a two-column then single-column card layout before horizontal scrolling becomes necessary.
- The documentation assistant is a conventional right-side drawer with an explicit full-height left resize edge, pointer and keyboard resizing, a double-click reset, and persisted width.
- The assistant opens at the intended 460-pixel default when no saved width exists, remains within 360–760 pixels on desktop, and becomes a full-width non-resizable sheet on smaller screens.
- Mode-aware icons, a busy spinner, and restrained launcher motion provide state feedback while respecting `prefers-reduced-motion`.
- The resize grip is rendered with CSS rather than a separate icon chunk, preserving the visual control without adding a request to the Rostering planner's synthetic 2G waterfall.
- Reserved default-day definitions use deterministic tenant-scoped portal identities; a tenant-authored record using either reserved code causes an explicit collision error and is never rewritten.
- Every actual bootstrap definition or assignment mutation writes an append-only AuditEvent with the actor, before/after state, and one correlation ID inside the same transaction.
- Readiness labels the system baseline only when the assignment targets the deterministic managed pattern ID; a tenant-authored record that reuses the code is never presented as portal-owned.
- Definition audit snapshots include `updated_by_user_id` and `updated_at`, so administrator attribution changes cannot occur without matching audit evidence.
- The mobile assistant launcher keeps its icon visible and exposes an explicit accessible name while only the visual text label is collapsed.
- The assistant header remains fixed while its body scrolls independently, preventing page-wide overflow.

## Acceptance coverage

The rendered Playwright scenario authenticates an AMO administrator, opens Workforce > People and contracts, and verifies that:

- an active user without a contract is displayed with `No contract`, `Create contract`, and the authorized `Apply default day pattern` action; and
- an active user with a future contract is displayed with the future start date and an `Edit` action, without an overlapping `Create contract` action.

The focused correction workflows passed the complete Workforce and Rostering suites, frontend Rostering and assistant tests, changed-surface ESLint, the production build, the rendered role-access matrix, production bundle budgets, and the cold/warm synthetic 2G Rostering waterfall before removing their temporary validation machinery. The bootstrap-governance publisher additionally passed a clean PostgreSQL migration, both complete backend suites, deterministic ownership checks, collision-refusal checks, transactional audit checks, and clean-diff validation before publishing commit `6404a90a3e64f5464a5372abd941ed5408bd43ad`. The final-review publisher passed both complete backend suites, the assistant and Rostering frontend contracts, changed-surface ESLint, production build, managed-ID readiness checks, attribution-audit checks, mobile launcher accessibility checks, and clean-diff validation before publishing commit `d0648e7e18627e09e8f2c8a6118a3f8f6835454e`. PR333 Release Candidate Gate #866 and Publications Reader CI #386 passed completely on exact head `a85f1131cd245e37f6572a4995e80f88883c9711`; every review thread is resolved, the branch is synchronized with `main`, and the final blocker-only Codex review returned a positive review reaction with no new findings.

## Final main synchronization

PR #377 was merged with current `main` at base `e8e4cb1932568a51c76ed616b70f8629466e6884` on 2026-07-30. Git reported a clean merge with no overlapping changed files. The permanent release workflow was restored in the merge commit, and the branch comparison returned `behind_by: 0`. The synchronized exact head must pass the protected release gates and final blocker-only review before the PR is marked ready for merge.
