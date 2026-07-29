# Workforce active-user roster readiness correction

## Problem corrected

The Workforce and HR employee register previously started from effective employment contracts. Active tenant users without an effective contract were therefore omitted entirely, producing an empty `0 of 0 employees` register even when active user accounts existed.

## Canonical behavior

1. The register starts from every active, non-system user belonging to the current tenant.
2. Employment contracts, bases, work-pattern assignments and approved leave are joined as readiness data.
3. Missing Workforce records remain visible as actionable readiness blockers; they never remove the user from the register.
4. When no contract is currently effective, the next future ACTIVE or ONBOARDING contract is surfaced for editing rather than offering an overlapping contract creation.
5. Authorized Workforce managers can create a missing effective contract or edit an existing one from the same register.
6. The contract editor uses the exact backend enums and tenant-owned canonical bases.
7. An authorized manager may explicitly create or repair the reserved `DEFAULT-DAY` shift and `DEFAULT-DAY-5X2` Monday-to-Friday pattern.
8. The default pattern is assigned only to active or onboarding employees with effective contracts who do not already have a valid active pattern. Existing active patterns are preserved.
9. All effective-date decisions use the tenant timezone.
10. Replacing an inactive current pattern closes the historical assignment and creates a new row effective on the tenant-local current date; historical records are never rewritten.
11. The `DEFAULT-DAY-5X2` cycle is anchored to the tenant-local week's Monday, regardless of the day the bootstrap is run.
12. The default baseline creates draft roster input only. A planner must still review, validate, submit, approve and publish the roster.

## Review corrections

The blocker reviews identified and corrected five readiness and effective-dating defects:

- inactive pattern assignments are no longer rewritten in place across their historical interval;
- the five-day duty cycle is anchored to Monday rather than the day on which the bootstrap action is executed; and
- future contracts are surfaced and edited instead of misclassified as missing contracts that invite an overlapping creation;
- future starters remain included in the currently effective-contract gap metric and receive an edit-future-contract action; and
- existing reserved default-day assignments with non-Monday anchors are safely re-effective-dated to the canonical Monday anchor.

These invariants are covered by Workforce regression contracts and the complete Rostering and Workforce test suites.

## Acceptance coverage

The rendered Playwright scenario authenticates an AMO administrator, opens Workforce > People and contracts, and verifies that:

- an active user without a contract is displayed with `No contract`, `Create contract`, and the authorized `Apply default day pattern` action; and
- an active user with a future contract is displayed with the future start date and an `Edit` action, without an overlapping `Create contract` action.

Backend Workforce and Rostering suites, frontend Rostering tests, ESLint, the production build and the complete role-access browser matrix are required before this correction is considered merge-ready.
